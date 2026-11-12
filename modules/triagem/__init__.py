import json
import os
import subprocess
import sys
import time
from datetime import datetime
from html import escape
from pathlib import Path

import streamlit as st

from database.triagem import repo
from database.triagem.estado import estado_importacao, fmt_int
from integracoes.gmail import autenticacao, config

from . import cards, protegidos, termos

RAIZ = Path(__file__).resolve().parents[2]
CSS_DIR = RAIZ / "assets" / "triagem"
GUIA_CLOUD = "https://console.cloud.google.com/"
ESPERA_DO_PROCESSO = 20  # segundos até desistir de esperar o processo assumir a trava
PASSOS_GOOGLE = (
    "Entre em console.cloud.google.com com a conta Gmail que será triada e crie um projeto chamado ATLAS Triagem.",
    "Em APIs e serviços, ative a Gmail API.",
    "Na tela de permissão OAuth, escolha o público Externo e preencha o nome (ATLAS) e o seu e-mail.",
    "Em Acesso a dados, adicione só o escopo gmail.modify. Ele não permite exclusão permanente.",
    "Em Público, clique em Publicar app (status Em produção). Isso evita que a autorização expire em 7 dias.",
    "Em Clientes, crie um ID de cliente OAuth do tipo App para computador e baixe o JSON.",
    "Envie esse arquivo aqui, no campo abaixo.",
)


@st.cache_resource(max_entries=1)
def _ler_css(versao):
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(CSS_DIR.glob("*.css")))


def _css():
    versao = tuple((p.name, p.stat().st_mtime_ns) for p in sorted(CSS_DIR.glob("*.css")))
    st.markdown(f"<style>{_ler_css(versao)}</style>", unsafe_allow_html=True)


def _data_br(texto):
    try:
        return datetime.strptime(texto, "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y às %H:%M")
    except (TypeError, ValueError):
        return None


def _abrir_processo(*argumentos):
    sinalizador = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.Popen(
        [sys.executable, "-m", *argumentos], cwd=RAIZ, creationflags=sinalizador,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
    )


# ---------- ações ----------

def sincronizar_agora():
    if repo.em_execucao():
        return
    ultima = repo.ultima_importacao()
    st.session_state.tri_pedido = {
        "em": time.time(), "job": ultima["id"] if ultima else 0, "erro": repo.obter_config("ultimo_erro_em"),
    }
    st.session_state.tri_rerun = True
    _abrir_processo("database.triagem.executor")


def pedir_pausa():
    repo.gravar_config("pedido_pausa", "1")


def _dispensar_erro():
    for chave in ("ultimo_erro_tipo", "ultimo_erro", "ultimo_erro_em"):
        repo.gravar_config(chave, None)


def _iniciar_conexao():
    config.caminho_resultado_conexao().unlink(missing_ok=True)
    st.session_state.tri_conexao = _abrir_processo("integracoes.gmail.autenticacao", "conectar")


def _cancelar_conexao():
    processo = st.session_state.pop("tri_conexao", None)
    if processo and processo.poll() is None:
        processo.terminate()
    config.caminho_resultado_conexao().unlink(missing_ok=True)


def _desconectar():
    autenticacao.desconectar()
    repo.gravar_config("email_conta", None)
    st.session_state.pop("tri_conexao", None)


def _iniciando():
    """O processo leva um ou dois segundos para assumir a trava; nesse intervalo a tela já mostra "iniciando"."""
    pedido = st.session_state.get("tri_pedido")
    if not pedido or time.time() - pedido["em"] > ESPERA_DO_PROCESSO:
        return False
    ultima = repo.ultima_importacao()
    novo_job = (ultima["id"] if ultima else 0) != pedido["job"]
    novo_erro = repo.obter_config("ultimo_erro_em") != pedido["erro"]
    return not novo_job and not novo_erro


# ---------- peças ----------

def _cabecalho():
    st.markdown(
        '<div class="atlas-title">Central de Triagem</div>'
        '<div class="atlas-sub">Organize sua caixa do Gmail sem apagar nada de vez.</div>',
        unsafe_allow_html=True,
    )


def _estatistica(numero, rotulo):
    return f'<div class="tri-stat"><strong>{numero}</strong><span>{rotulo}</span></div>'


def _faixa_erro():
    mensagem = repo.obter_config("ultimo_erro")
    if not mensagem:
        return
    precisa_reconectar = repo.obter_config("ultimo_erro_tipo") == "autorizacao"
    quando = _data_br(repo.obter_config("ultimo_erro_em")) or ""
    with st.container(key="tri_faixa_erro"):
        st.markdown(
            f'<div class="tri-erro-titulo">A última sincronização falhou</div>'
            f'<div class="tri-erro-texto">{escape(mensagem)}</div>'
            f'<div class="tri-erro-quando">{escape(quando)}</div>',
            unsafe_allow_html=True,
        )
        with st.container(horizontal=True, gap="small"):
            if precisa_reconectar:
                st.button("Reconectar o Gmail", key="tri_reconectar", type="primary", on_click=_iniciar_conexao)
            else:
                st.button("Tentar de novo", key="tri_tentar", type="primary", on_click=sincronizar_agora)
            st.button("Dispensar", key="tri_dispensar", on_click=_dispensar_erro)


def _configurar_google():
    with st.container(key="tri_card_google"):
        st.markdown('<div class="tri-card-titulo">Conecte o ATLAS ao seu Gmail</div>'
                    '<div class="tri-texto">Você cria um projeto no Google Cloud só seu, uma vez. '
                    'O ATLAS pede a menor permissão possível e nunca exclui e-mails de vez.</div>',
                    unsafe_allow_html=True)
        with st.expander("Passo a passo no Google Cloud", expanded=True):
            st.markdown("\n".join(f"{numero}. {passo}" for numero, passo in enumerate(PASSOS_GOOGLE, 1)))
            st.link_button("Abrir o Google Cloud", GUIA_CLOUD, icon=":material/open_in_new:")
        enviado = st.file_uploader("Enviar client_secret.json", type=["json"], key="tri_secret")
        if enviado is not None:
            conteudo = enviado.getvalue()
            erro = autenticacao.validar_client_secret(conteudo.decode("utf-8", "replace"))
            if erro:
                st.error(erro)
            else:
                autenticacao.gravar_client_secret(conteudo)
                st.rerun()


def _acompanhar_conexao():
    processo = st.session_state.get("tri_conexao")
    caminho = config.caminho_resultado_conexao()
    resultado = {}
    if caminho.exists():
        try:
            resultado = json.loads(caminho.read_text(encoding="utf-8"))
        except ValueError:
            pass
    if resultado.get("estado") == "ok":
        st.session_state.pop("tri_conexao", None)
        _dispensar_erro()
        st.rerun()
    if resultado.get("estado") == "erro" or (processo and processo.poll() not in (None, 0) and not resultado):
        st.session_state.pop("tri_conexao", None)
        st.error(f"Não foi possível conectar: {resultado.get('erro', 'o processo terminou sem autorizar')}")
        st.button("Tentar de novo", key="tri_conexao_de_novo", on_click=_iniciar_conexao)
        return
    st.markdown('<div class="tri-texto">Aguardando você autorizar no navegador. Na tela "O Google não verificou '
                'este app", clique em <b>Avançado</b> e depois em <b>Acessar ATLAS</b>.</div>',
                unsafe_allow_html=True)
    st.button("Cancelar", key="tri_conexao_cancelar", on_click=_cancelar_conexao)


def _conectar():
    with st.container(key="tri_card_conectar"):
        st.markdown('<div class="tri-card-titulo">Autorize o acesso ao Gmail</div>', unsafe_allow_html=True)
        if "tri_conexao" in st.session_state:
            st.fragment(run_every=2)(_acompanhar_conexao)()
        else:
            st.markdown('<div class="tri-texto">O navegador vai abrir a tela de permissão do Google. '
                        'O ATLAS só lê e organiza: não consegue excluir e-mails de vez.</div>',
                        unsafe_allow_html=True)
            st.button("Conectar ao Gmail", key="tri_conectar", type="primary", icon=":material/link:",
                      on_click=_iniciar_conexao)


def _painel_importacao():
    """Fragmento: enquanto há importação rodando, relê o estado a cada 2 segundos.

    Um botão dentro do fragmento só reexecuta o próprio fragmento, e o intervalo de 2 segundos é decidido na
    execução completa; por isso quem inicia a sincronização pede uma execução completa (`tri_rerun`)."""
    if st.session_state.pop("tri_rerun", False):
        st.rerun()
    estado = estado_importacao(
        rodando=repo.em_execucao() or _iniciando(), ultima=repo.ultima_importacao(),
        pendente=repo.importacao_pendente(), historico=repo.obter_config("history_id"),
    )
    anterior = st.session_state.get("tri_fase_anterior")
    st.session_state.tri_fase_anterior = estado["fase"]
    if anterior == "rodando" and estado["fase"] != "rodando":
        st.rerun()

    fase = estado["fase"]
    total, feitos = fmt_int(estado["total"]), fmt_int(estado["processados"])
    with st.container(key="tri_card_importacao"):
        if fase == "rodando":
            if estado["fracao"] is not None and estado["processados"]:
                st.markdown(f'<div class="tri-card-titulo">Importando: {feitos} de {total} e-mails</div>',
                            unsafe_allow_html=True)
                st.progress(estado["fracao"])
            else:
                st.markdown('<div class="tri-card-titulo">Sincronizando com o Gmail</div>', unsafe_allow_html=True)
                st.progress(0.0 if estado["fracao"] is None else estado["fracao"])
            st.button("Pausar", key="tri_pausar", icon=":material/pause:", on_click=pedir_pausa)
        elif fase == "nunca":
            st.markdown(
                '<div class="tri-card-titulo">Importe sua caixa de entrada</div>'
                '<div class="tri-texto">O ATLAS lê remetente, assunto, data, tamanho, marcadores, cabeçalhos de '
                'lista e um trecho curto de cada e-mail. O corpo das mensagens não é baixado. A primeira carga '
                'pode levar alguns minutos e pode ser pausada e retomada.</div>', unsafe_allow_html=True)
            st.button("Importar caixa de entrada", key="tri_importar", type="primary",
                      icon=":material/download:", on_click=sincronizar_agora)
        elif fase == "pausada":
            st.markdown(f'<div class="tri-card-titulo">Importação pausada em {feitos} de {total} e-mails</div>'
                        '<div class="tri-texto">O progresso está salvo. Retome quando quiser: nada será '
                        'importado duas vezes.</div>', unsafe_allow_html=True)
            st.progress(estado["fracao"] or 0.0)
            st.button("Retomar importação", key="tri_retomar", type="primary", icon=":material/play_arrow:",
                      on_click=sincronizar_agora)
        elif fase == "erro":
            st.markdown(f'<div class="tri-card-titulo">A importação parou em {feitos} de {total} e-mails</div>'
                        '<div class="tri-texto">O progresso está salvo. Corrija o que a faixa acima mostra e '
                        'retome.</div>', unsafe_allow_html=True)
            st.button("Retomar importação", key="tri_retomar_erro", type="primary", icon=":material/play_arrow:",
                      on_click=sincronizar_agora)
        else:
            quando = _data_br(repo.obter_config("ultima_sincronizacao"))
            st.markdown('<div class="tri-card-titulo">Caixa sincronizada</div>'
                        f'<div class="tri-texto">Última sincronização: {escape(quando) if quando else "agora há pouco"}.'
                        '</div>', unsafe_allow_html=True)
            st.button("Sincronizar agora", key="tri_sincronizar", icon=":material/sync:", on_click=sincronizar_agora)


def _resumo_caixa():
    dados = repo.resumo()
    with st.container(key="tri_card_resumo"):
        st.markdown('<div class="tri-card-titulo">Sua caixa</div>', unsafe_allow_html=True)
        if not dados["total"]:
            st.markdown('<div class="tri-texto tri-vazio">Nenhum e-mail importado ainda.</div>',
                        unsafe_allow_html=True)
            return
        antigo = dados["mais_antigo"].strftime("%m/%Y") if dados["mais_antigo"] else "-"
        st.markdown(
            '<div class="tri-stats">'
            + _estatistica(fmt_int(dados["total"]), "e-mails importados")
            + _estatistica(fmt_int(dados["nao_lidos"]), "não lidos")
            + _estatistica(fmt_int(dados["remetentes"]), "remetentes")
            + _estatistica(antigo, "e-mail mais antigo")
            + "</div>", unsafe_allow_html=True)


def _conta():
    email = repo.obter_config("email_conta")
    with st.container(key="tri_card_conta"):
        st.markdown('<div class="tri-card-titulo">Conta conectada</div>'
                    f'<div class="tri-texto">{escape(email) if email else "Gmail"}</div>'
                    '<div class="tri-nota">Permissão: ler, marcar e mover para a lixeira. '
                    'Nenhuma exclusão permanente.</div>', unsafe_allow_html=True)
        with st.popover("Desconectar", icon=":material/link_off:"):
            st.markdown("Isso apaga o token deste computador e revoga o acesso do ATLAS no Google. "
                        "Os e-mails já importados continuam no banco.")
            st.button("Desconectar o Gmail", key="tri_desconectar", on_click=_desconectar)


SECOES = ("Cards", "Explorar termos", "Protegidos", "Caixa e conta")


def _caixa_e_conta():
    with st.container(horizontal=False, key="tri_grade"):
        colunas = st.columns(2)
        with colunas[0]:
            _resumo_caixa()
        with colunas[1]:
            _conta()


def render():
    st.session_state.pop("tri_rerun", None)
    _css()
    with st.container(key="tri_raiz"):
        _cabecalho()
        situacao = autenticacao.status()
        if situacao["conectado"]:
            _faixa_erro()
        if not situacao["client_secret"]:
            _configurar_google()
        elif not situacao["conectado"] or "tri_conexao" in st.session_state:
            _conectar()
        else:
            ativo = repo.em_execucao() or _iniciando()
            st.fragment(run_every=2 if ativo else None)(_painel_importacao)()
            secao = st.segmented_control("Seção", SECOES, default=SECOES[0], key="tri_secao",
                                         label_visibility="collapsed") or SECOES[0]
            if secao == "Cards":
                cards.secao()
            elif secao == "Explorar termos":
                termos.secao()
            elif secao == "Protegidos":
                protegidos.secao()
            else:
                _caixa_e_conta()
