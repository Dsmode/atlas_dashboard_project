"""Seção "Histórico": tudo o que o ATLAS fez no seu Gmail, com desfazer."""
import io

import pandas as pd
import streamlit as st

from database.triagem import limpeza, repo
from database.triagem.estado import fmt_int

from . import acoes, dados

TIPOS = {"marcar": "Marcou", "arquivar": "Arquivou", "lixeira": "Lixeira"}


def _desfazer(acao_id):
    with st.spinner("Desfazendo no Gmail…"):
        restaurados = acoes._com_cliente(lambda cliente: limpeza.desfazer(cliente, acao_id))
    dados.renovar_tabelas()
    if restaurados is not None:
        acoes.avisar(f"Desfeito: {fmt_int(restaurados)} e-mails voltaram ao estado anterior. E-mails que o Gmail já "
                     "esvaziou da lixeira não voltam.")


def secao():
    historico = repo.listar_acoes()
    with st.container(key="tri_card_historico"):
        st.markdown('<div class="tri-card-titulo">Histórico e desfazer</div>'
                    '<div class="tri-texto">Cada marcação, arquivamento e movimento para a lixeira fica aqui. '
                    '"Desfazer" devolve os marcadores e a caixa de entrada como estavam. A lixeira do Gmail se '
                    'esvazia sozinha em 30 dias: depois disso o que já sumiu não volta.</div>', unsafe_allow_html=True)
        if not historico:
            st.markdown('<div class="tri-texto tri-vazio">Nenhuma ação ainda.</div>', unsafe_allow_html=True)
            return
        tabela = pd.DataFrame({
            "Quando": [a["criada_em"].strftime("%d/%m/%Y %H:%M") for a in historico],
            "Tipo": [TIPOS[a["tipo"]] for a in historico],
            "O que foi feito": [a["descricao"] for a in historico],
            "E-mails": [a["quantidade"] for a in historico],
            "Situação": ["feita" if a["status"] == "feita" else "desfeita" for a in historico],
        })
        evento = st.dataframe(
            tabela, hide_index=True, width="stretch", height=min(480, 50 + 35 * len(tabela)), on_select="rerun",
            selection_mode="single-row", key=dados.chave_tabela("tri_tabela_historico"),
            column_config={"Quando": st.column_config.TextColumn(width=130), "Tipo": st.column_config.TextColumn(width=80),
                           "E-mails": st.column_config.NumberColumn(format="%d", width=80),
                           "Situação": st.column_config.TextColumn(width=90),
                           "O que foi feito": st.column_config.TextColumn(width="large")})
        linhas = list(evento.selection.rows)
        escolhida = historico[linhas[0]] if linhas else None
        with st.container(horizontal=True, gap="small"):
            st.button("Desfazer a ação selecionada", key="tri_desfazer", icon=":material/undo:", type="primary",
                      disabled=escolhida is None or escolhida["status"] != "feita",
                      on_click=_desfazer, args=(escolhida["id"],) if escolhida else (0,))
            buffer = io.StringIO()
            tabela.to_csv(buffer, index=False)
            st.download_button("Exportar histórico (CSV)", data=buffer.getvalue().encode("utf-8-sig"),
                               file_name="atlas_historico.csv", mime="text/csv", icon=":material/download:",
                               key="tri_csv_historico")
