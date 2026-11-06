import altair as alt

from database.cores import COR_NEUTRA


def degrade(topo, base):
    return alt.Gradient(
        gradient="linear", x1=1, y1=0, x2=1, y2=1,
        stops=[alt.GradientStop(color=topo, offset=0), alt.GradientStop(color=base, offset=1)],
    )


def eixo_x_discreto():
    return alt.Axis(labelAngle=0, labelOverlap="parity", labelColor=COR_NEUTRA, labelFontSize=10,
                    ticks=False, domainColor="rgba(255,255,255,.12)", labelPadding=6)


def tema(grafico):
    return grafico.configure(background="transparent", font="Outfit, sans-serif").configure_view(stroke=None)
