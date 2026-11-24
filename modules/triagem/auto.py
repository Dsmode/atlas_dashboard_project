"""Seção "Automático e histórico": modo de cada card na triagem agendada, estado do agendamento e relatório das
execuções."""
import json
import subprocess
from datetime import UTC
from html import escape

import pandas as pd
import streamlit as st

from database.triagem import automatico, repo
from database.triagem.estado import fmt_int

from . import dados, historico

NOME_DA_TAREFA = "ATLAS Triagem"
COMANDO_CRIAR = r"powershell -ExecutionPolicy Bypass -File launcher\criar_tarefa_triagem.ps1"
COMANDO_REMOVER = COMANDO_CRIAR + " -Remover"


def tarefa_instalada():
    """True se a tarefa do Agendador existe (consulta só leitura). None se não deu para saber."""
    sinalizador = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    try:
        resultado = subprocess.run(["schtasks", "/Query", "/TN", NOME_DA_TAREFA], capture_output=True, timeout=10,
                                   creationflags=sinalizador, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return resultado.returncode == 0


def _hora_local(momento):
    return momento.replace(tzinfo=UTC).astimezone().strftime("%d/%m/%Y %H:%M") if momento else ""


def _mudar_modo(chave):
    repo.gravar_modo(chave, st.session_state[f"tri_modo_{chave}"])


def _agendamento():
    instalada = tarefa_instalada()
    with st.container(key="tri_card_agendamento"):
        st.markdown('<div class="tri-card-titulo">Triagem automática</div>', unsafe_allow_html=True)
        if instalada:
            st.markdown('<div class="tri-texto">Agendamento <b>ativo</b>: a cada 2 horas o Windows sincroniza o Gmail e '
                        'faz a triagem, com o PC ligado e você logado. Se o PC estava desligado, roda ao ligar. Erros '
                        'aparecem numa faixa ao abrir a Central.</div>', unsafe_allow_html=True)
        else:
            estado = "não foi possível consultar o Agendador" if instalada is None else "ainda não está ativo"
            st.markdown(f'<div class="tri-texto">O agendamento {estado}. Para ativar, rode uma vez no PowerShell, na '
                        'pasta do ATLAS (o ATLAS não cria a tarefa sozinho):</div>', unsafe_allow_html=True)
            st.code(COMANDO_CRIAR, language="powershell")
        st.markdown(f'<div class="tri-nota">Para desativar: <code>{escape(COMANDO_REMOVER)}</code>. "Sincronizar agora" '
                    'também faz a triagem.</div>', unsafe_allow_html=True)


def _modos(caixa):
    modos = repo.obter_modos()
    cards = [("lixo", "Lixo"), ("spam", "Spam e suspeitos"), ("revisar", "Revisar")]
    cards += [(automatico.chave_do_card(c["id"]), c["nome"]) for c in caixa["cards"]]
    with st.container(key="tri_card_modos"):
        st.markdown(
            '<div class="tri-card-titulo">O que fazer com os e-mails novos de cada card</div>'
            '<div class="tri-texto"><b>Só sugerir</b> (padrão) não muda nada no Gmail: o relatório mostra o que cairia '
            'em cada card. <b>Marcar sozinho</b> põe o marcador ATLAS/&lt;card&gt;. <b>Arquivar na quarentena</b> marca e '
            'tira da caixa de entrada, em ATLAS/Quarentena. Nunca vai para a lixeira sozinho, nunca mexe em protegidos '
            'nem em e-mail que você já leu (na quarentena) e só age em e-mail que chegou depois da última triagem. A '
            'primeira execução só marca o ponto de partida. Tudo fica no histórico, com desfazer.</div>',
            unsafe_allow_html=True)
        for chave, titulo in cards:
            colunas = st.columns([2, 3], vertical_alignment="center")
            colunas[0].markdown(f'<div class="tri-texto">{escape(titulo)}</div>', unsafe_allow_html=True)
            permitidos = list(automatico.modos_permitidos(chave))
            atual = automatico.modo_do_card(modos, chave)
            colunas[1].selectbox(f"Modo de {titulo}", permitidos, index=permitidos.index(atual),
                                 format_func=automatico.MODOS.get, key=f"tri_modo_{chave}",
                                 label_visibility="collapsed", on_change=_mudar_modo, args=(chave,))


def _execucoes():
    execucoes = repo.listar_execucoes()
    with st.container(key="tri_card_execucoes"):
        st.markdown('<div class="tri-card-titulo">Execuções</div>'
                    '<div class="tri-texto">Cada sincronização com triagem, agendada ou manual, e o que ela fez.</div>',
                    unsafe_allow_html=True)
        if not execucoes:
            st.markdown('<div class="tri-texto tri-vazio">Nenhuma execução ainda.</div>', unsafe_allow_html=True)
            return
        resumos = [json.loads(e["resumo"]) if e["resumo"] else None for e in execucoes]
        tabela = pd.DataFrame({
            "Quando": [_hora_local(e["iniciada_em"]) for e in execucoes],
            "Origem": ["agendada" if e["origem"] == "agendada" else "manual" for e in execucoes],
            "Situação": ["ok" if e["status"] == "ok" else "erro" for e in execucoes],
            "Novos": [e["novos"] for e in execucoes],
            "O que fez": [("; ".join(automatico.descrever(r)) if r else (e["erro"] or "")) for e, r in zip(execucoes, resumos, strict=True)],
        })
        st.dataframe(tabela, hide_index=True, width="stretch", height=min(420, 50 + 35 * len(tabela)),
                     column_config={"Quando": st.column_config.TextColumn(width=130),
                                    "Origem": st.column_config.TextColumn(width=80),
                                    "Situação": st.column_config.TextColumn(width=80),
                                    "Novos": st.column_config.NumberColumn(format="%d", width=70),
                                    "O que fez": st.column_config.TextColumn(width="large")})
        ultima = execucoes[0]
        st.markdown(f'<div class="tri-nota">Última execução: {_hora_local(ultima["iniciada_em"])}, '
                    f'{fmt_int(ultima["novos"])} e-mails novos.</div>', unsafe_allow_html=True)


def secao():
    caixa = dados.caixa(dados.versao())
    _agendamento()
    _modos(caixa)
    _execucoes()
    historico.secao()
