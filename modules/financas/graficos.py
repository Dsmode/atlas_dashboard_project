"""Os quatro gráficos do Dashboard em Altair. Recebem as linhas prontas de `financas.calculos` e só desenham:
Decimal vira float aqui, na hora de desenhar, e os textos dos tooltips já chegam formatados em R$."""

import altair as alt
import pandas as pd

from database.cores import COR_NEUTRA, COR_PADRAO, cor_valida
from database.dinheiro import fmt_brl
from database.financas.calculos import fmt_pct, mes_curto, nome_mes
from modules.financas.comum import COR_ENTRADA, COR_SAIDA
from modules.graficos_base import degrade, eixo_x_discreto, tema

# Mesma altura nos quatro cartões, para a grade alinhar.
ALTURA = 230
ROSCA_LARGURA = 190

_TEXTO = "#c9c9d6"
_TEXTO_FRACO = COR_NEUTRA
_GRADE = "rgba(255,255,255,.06)"
_ROXO = COR_PADRAO

# Rótulo curto do eixo em reais no formato brasileiro: R$ 800, R$ 1,5 mil, R$ 2,3 mi.
_RS_CURTO = (
    "(datum.value < 0 ? '-' : '') + 'R$ ' + ("
    "abs(datum.value) >= 1e6 ? replace(format(abs(datum.value) / 1e6, '.1~f'), '.', ',') + ' mi' : "
    "abs(datum.value) >= 1e3 ? replace(format(abs(datum.value) / 1e3, '.1~f'), '.', ',') + ' mil' : "
    "format(abs(datum.value), '.0f'))"
)


def _rotulo_mes(mes, primeiro):
    """'nov' no eixo; janeiro e o primeiro mês da janela levam o ano ('jan/26') para marcar a virada."""
    return mes_curto(mes, com_ano=primeiro or mes.month == 1)


def _eixo_x(rotulos, escala=None):
    """Meses em ordem. O domínio fixo mantém a ordem mesmo com camadas e meses zerados."""
    return alt.X(
        "rotulo:N", sort=None, title=None,
        scale=escala or alt.Scale(domain=rotulos, paddingInner=0.32, paddingOuter=0.2),
        axis=eixo_x_discreto(),
    )


def _eixo_y_rs():
    return alt.Axis(labelExpr=_RS_CURTO, tickCount=4, grid=True, gridColor=_GRADE, domain=False, ticks=False,
                    labelColor=_TEXTO_FRACO, labelFontSize=10, labelPadding=6, title=None)


def _finalizar(grafico, largura="container"):
    return tema(grafico.properties(height=ALTURA, width=largura))


def entradas_saidas(linhas):
    series = (("Entradas", "entradas", "#7dedc4", COR_ENTRADA), ("Saídas", "saidas", "#ffa0aa", COR_SAIDA))
    rotulos, dados = [], []
    for i, mes_linha in enumerate(linhas):
        rotulo = _rotulo_mes(mes_linha["mes"], i == 0)
        rotulos.append(rotulo)
        for nome, campo, _, _ in series:
            dados.append({
                "rotulo": rotulo, "serie": nome, "valor": float(mes_linha[campo]),
                "opacidade": 1 if i == len(linhas) - 1 else 0.62,
                "mes_nome": nome_mes(mes_linha["mes"]), "entradas_txt": fmt_brl(mes_linha["entradas"]),
                "saidas_txt": fmt_brl(mes_linha["saidas"]), "saldo_txt": fmt_brl(mes_linha["saldo"], sinal=True),
            })
    preenchimento = alt.condition(
        "datum.serie == 'Entradas'", alt.value(degrade(series[0][2], series[0][3])),
        alt.value(degrade(series[1][2], series[1][3])),
    )
    barras = alt.Chart(pd.DataFrame(dados)).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
        x=_eixo_x(rotulos),
        xOffset=alt.XOffset("serie:N", scale=alt.Scale(domain=[s[0] for s in series], paddingInner=0.18)),
        y=alt.Y("valor:Q", axis=_eixo_y_rs(), scale=alt.Scale(nice=True)),
        color=preenchimento,
        opacity=alt.Opacity("opacidade:Q", legend=None, scale=None),
        tooltip=[
            alt.Tooltip("mes_nome:N", title="Mês"), alt.Tooltip("entradas_txt:N", title="Entradas"),
            alt.Tooltip("saidas_txt:N", title="Saídas"), alt.Tooltip("saldo_txt:N", title="Saldo"),
        ],
    )
    return _finalizar(barras)


def rosca(grupos, total):
    dados = [
        {"nome": g["nome"], "valor": float(g["valor"]), "ordem": i, "valor_txt": fmt_brl(g["valor"]),
         "pct_txt": fmt_pct(g["pct"])}
        for i, g in enumerate(grupos) if g["valor"] > 0
    ]
    # O nome serve de chave: categorias de gasto não repetem nome (UNIQUE no banco).
    escala = alt.Scale(domain=[g["nome"] for g in grupos if g["valor"] > 0],
                       range=[cor_valida(g["cor"]) for g in grupos if g["valor"] > 0])
    raio = ROSCA_LARGURA / 2 - 8
    fatias = alt.Chart(pd.DataFrame(dados)).mark_arc(
        innerRadius=raio * 0.7, outerRadius=raio, cornerRadius=4, padAngle=0.02,
        stroke="#15151b", strokeWidth=1,
    ).encode(
        theta=alt.Theta("valor:Q", stack=True),
        color=alt.Color("nome:N", scale=escala, legend=None),
        order=alt.Order("ordem:Q", sort="ascending"),
        tooltip=[
            alt.Tooltip("nome:N", title="Grupo"), alt.Tooltip("valor_txt:N", title="Valor"),
            alt.Tooltip("pct_txt:N", title="Do total"),
        ],
    )
    centro = pd.DataFrame([{"total": fmt_brl(total), "legenda": "em gastos"}])
    valor = alt.Chart(centro).mark_text(dy=-6, color="#f1f1f6", fontSize=16, fontWeight=600).encode(
        text="total:N")
    rotulo = alt.Chart(centro).mark_text(dy=14, color=_TEXTO_FRACO, fontSize=11).encode(text="legenda:N")
    return _finalizar(fatias + valor + rotulo, largura=ROSCA_LARGURA)


def fluxo_caixa(linhas):
    rotulos, dados = [], []
    for i, mes_linha in enumerate(linhas):
        rotulo = _rotulo_mes(mes_linha["mes"], i == 0)
        rotulos.append(rotulo)
        dados.append({
            "rotulo": rotulo, "saldo": float(mes_linha["saldo"]), "negativo": mes_linha["saldo"] < 0,
            "tamanho": 70 if i == len(linhas) - 1 else 34,
            "mes_nome": nome_mes(mes_linha["mes"]), "saldo_txt": fmt_brl(mes_linha["saldo"]),
            "resultado_txt": fmt_brl(mes_linha["resultado"], sinal=True),
        })
    base = alt.Chart(pd.DataFrame(dados)).encode(
        x=_eixo_x(rotulos, alt.Scale(type="point", domain=rotulos, padding=0.4)),
        y=alt.Y("saldo:Q", axis=_eixo_y_rs(), scale=alt.Scale(zero=True, nice=True)),
    )
    area = base.mark_area(
        interpolate="monotone", line=False,
        color=degrade("rgba(180,76,255,0.42)", "rgba(180,76,255,0.02)"),
    ).encode(y2=alt.datum(0))
    linha = base.mark_line(interpolate="monotone", color=_ROXO, strokeWidth=2.4, strokeCap="round")
    zero = alt.Chart(pd.DataFrame([{"zero": 0}])).mark_rule(
        color="rgba(255,255,255,.28)", strokeDash=[4, 4], strokeWidth=1,
    ).encode(y="zero:Q")
    pontos = base.mark_point(filled=True, opacity=1, stroke="#15151b", strokeWidth=1.5).encode(
        color=alt.condition("datum.negativo", alt.value(COR_SAIDA), alt.value("#d68bff")),
        size=alt.Size("tamanho:Q", legend=None, scale=None),
        tooltip=[
            alt.Tooltip("mes_nome:N", title="Mês"), alt.Tooltip("saldo_txt:N", title="Saldo no fim do mês"),
            alt.Tooltip("resultado_txt:N", title="Resultado do mês"),
        ],
    )
    return _finalizar(area + zero + linha + pontos)


def top_categorias(grupos):
    maior = max(float(g["valor"]) for g in grupos)
    nomes = [g["nome"] for g in grupos]
    dados = [
        {"nome": g["nome"], "valor": float(g["valor"]), "trilho": maior, "valor_txt": fmt_brl(g["valor"]),
         "pct_txt": fmt_pct(g["pct"])}
        for g in grupos
    ]
    # Folga à direita para o valor escrito depois da maior barra.
    escala_x = alt.Scale(domain=[0, maior * 1.42])
    eixo_y = alt.Y(
        "nome:N", sort=nomes, title=None, scale=alt.Scale(domain=nomes, paddingInner=0.5, paddingOuter=0.3),
        axis=alt.Axis(ticks=False, domain=False, labelColor=_TEXTO, labelFontSize=12, labelLimit=120,
                      labelPadding=10),
    )
    base = alt.Chart(pd.DataFrame(dados)).encode(y=eixo_y)
    trilho = base.mark_bar(cornerRadius=6, color="rgba(255,255,255,.045)").encode(
        x=alt.X("trilho:Q", axis=None, scale=escala_x))
    barras = base.mark_bar(cornerRadiusEnd=6).encode(
        x=alt.X("valor:Q", axis=None, scale=escala_x),
        color=alt.Color("nome:N", legend=None,
                        scale=alt.Scale(domain=nomes, range=[cor_valida(g["cor"]) for g in grupos])),
        tooltip=[
            alt.Tooltip("nome:N", title="Categoria"), alt.Tooltip("valor_txt:N", title="Gasto"),
            alt.Tooltip("pct_txt:N", title="Dos gastos do mês"),
        ],
    )
    valores = base.mark_text(align="left", dx=8, color="#e4e4ee", fontSize=12, fontWeight=500).encode(
        x=alt.X("valor:Q", axis=None, scale=escala_x), text="valor_txt:N")
    return _finalizar(trilho + barras + valores)
