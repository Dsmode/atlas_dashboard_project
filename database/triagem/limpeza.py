"""Ações no Gmail: marcar com marcadores ATLAS/..., arquivar para a quarentena e mover para a lixeira, tudo com
registro (`tri_acoes`) para desfazer. Nunca exclui de vez: só marcadores e a lixeira (30 dias no Gmail).

O cliente do Gmail é injetado, então tudo isto roda nos testes com um Gmail de mentira."""
import re
from collections import defaultdict

from . import repo

RAIZ = "ATLAS"
QUARENTENA = f"{RAIZ}/Quarentena"
NOMES_FIXOS = {"lixo": f"{RAIZ}/Lixo", "spam": f"{RAIZ}/Suspeitos", "revisar": f"{RAIZ}/Revisar"}
TAMANHO_MAXIMO_NOME = 200


class ProtegidoNaSelecao(Exception):
    """A seleção tem e-mails de remetentes protegidos e a confirmação extra não foi dada."""


def nome_do_marcador(nome_do_card):
    """"Vagas de Emprego" -> "ATLAS/Vagas de Emprego". Tira o que o Gmail não aceita em nome de marcador."""
    limpo = re.sub(r"[\\/\r\n\t]+", " ", nome_do_card or "")
    limpo = " ".join(limpo.split())[:TAMANHO_MAXIMO_NOME] or "Sem nome"
    return f"{RAIZ}/{limpo}"


def planejar_lixeira(ids, emails_por_id, classificacao, permitir_protegidos=False):
    """Quais ids realmente vão para a lixeira. Protegidos ficam de fora (a menos que a confirmação extra tenha
    sido dada) e o que já está na lixeira não se repete. Devolve {ids, protegidos_fora, ja_na_lixeira, remetentes}."""
    vao, protegidos_fora, ja = [], 0, 0
    for i in ids:
        e = emails_por_id.get(i)
        if e is None:
            continue
        if e.get("lixeira"):
            ja += 1
        elif classificacao.get(i, ("",))[0] == "protegido" and not permitir_protegidos:
            protegidos_fora += 1
        else:
            vao.append(i)
    remetentes = {(emails_por_id[i]["remetente_email"] or "").lower() for i in vao}
    return {"ids": vao, "protegidos_fora": protegidos_fora, "ja_na_lixeira": ja, "remetentes": len(remetentes)}


def _agrupar(itens):
    grupos = defaultdict(list)
    for email_id, adicionados, removidos in itens:
        grupos[(tuple(adicionados), tuple(removidos))].append(email_id)
    return grupos


def _aplicar(cliente, itens):
    """Aplica os deltas grupo a grupo (um batchModify por grupo e por 1.000 e-mails) e reflete no banco local.
    Devolve os itens concluídos; se algo falhar no meio, levanta o erro junto com o que já foi feito."""
    feitos = []
    por_id = {e: (a, r) for e, a, r in itens}
    for (adicionar, remover), ids in _agrupar(itens).items():
        try:
            cliente.alterar_marcadores(ids, adicionar=adicionar, remover=remover)
        except Exception as erro:
            raise ErroParcial(feitos, erro) from erro
        repo.aplicar_marcadores_local(ids, adicionar, remover)
        feitos.extend((i, *por_id[i]) for i in ids)
    return feitos


class ErroParcial(Exception):
    def __init__(self, feitos, causa):
        super().__init__(str(causa))
        self.feitos, self.causa = feitos, causa


def _registrar(tipo, descricao, feitos, erro=None):
    if not feitos:
        if erro:
            raise erro.causa
        return None
    acao_id = repo.criar_acao(tipo, descricao + (" (parcial: o Gmail parou no meio)" if erro else ""), feitos)
    if erro:
        raise erro.causa
    return acao_id


def _executar(cliente, tipo, descricao, itens):
    try:
        feitos = _aplicar(cliente, itens)
    except ErroParcial as erro:
        return _registrar(tipo, descricao, erro.feitos, erro)
    return _registrar(tipo, descricao, feitos)


def _id_do_marcador(cliente, nome):
    marcador_id = cliente.garantir_marcador(nome)
    repo.gravar_marcadores([{"id": marcador_id, "name": nome, "type": "user"}])
    return marcador_id


def marcar(cliente, nome_marcador, ids_com, ids_sem=()):
    """Põe `nome_marcador` nos `ids_com` e o tira dos `ids_sem` (e-mails que saíram do card). Só etiqueta: nada
    sai da caixa de entrada."""
    marcador_id = _id_do_marcador(cliente, nome_marcador)
    ja_tem = repo.ids_com_marcador(marcador_id)
    itens = [(i, [marcador_id], []) for i in ids_com if i not in ja_tem]
    itens += [(i, [], [marcador_id]) for i in ids_sem if i in ja_tem]
    if not itens:
        return None
    return _executar(cliente, "marcar", f"Marcou {len(itens)} e-mails com {nome_marcador}", itens)


def arquivar(cliente, ids, origem):
    """Tira da caixa de entrada e põe em ATLAS/Quarentena (sem prazo: você revisa e manda para a lixeira)."""
    quarentena = _id_do_marcador(cliente, QUARENTENA)
    atuais = repo.marcadores_dos_emails(ids)
    itens = [(i, [quarentena] if quarentena not in m else [], ["INBOX"] if "INBOX" in m else [])
             for i, m in atuais.items() if "TRASH" not in m and (quarentena not in m or "INBOX" in m)]
    if not itens:
        return None
    return _executar(cliente, "arquivar", f"Arquivou {len(itens)} e-mails na quarentena ({origem})", itens)


def mover_para_lixeira(cliente, ids, origem, protegidos_na_selecao=(), confirmou_protegidos=False):
    """Move para a lixeira do Gmail. Se algum id for de remetente protegido, exige `confirmou_protegidos`."""
    ids = list(dict.fromkeys(ids))
    if set(ids) & set(protegidos_na_selecao) and not confirmou_protegidos:
        raise ProtegidoNaSelecao
    atuais = repo.marcadores_dos_emails(ids)
    itens = [(i, ["TRASH"], ["INBOX"] if "INBOX" in m else []) for i, m in atuais.items() if "TRASH" not in m]
    if not itens:
        return None
    return _executar(cliente, "lixeira", f"Moveu {len(itens)} e-mails para a lixeira ({origem})", itens)


def desfazer(cliente, acao_id):
    """Inverte uma ação: tira o que ela pôs e devolve o que ela tirou. Para a lixeira só vale até o Gmail
    esvaziá-la (30 dias); e-mails que já sumiram são ignorados. Devolve quantos e-mails foram restaurados."""
    acao = repo.obter_acao(acao_id)
    if acao is None or acao["status"] != "feita":
        return 0
    inversos = [(e, r, a) for e, a, r in repo.itens_da_acao(acao_id)]
    existentes = repo.ids_existentes(e for e, _, _ in inversos)
    inversos = [(e, a, r) for e, a, r in inversos if e in existentes]
    try:
        feitos = _aplicar(cliente, inversos)
    except ErroParcial as erro:
        raise erro.causa from erro
    repo.marcar_acao_desfeita(acao_id)
    return len(feitos)
