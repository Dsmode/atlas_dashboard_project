from datetime import timedelta


def inicio_semana(dia):
    return dia - timedelta(days=(dia.weekday() + 1) % 7)


def intervalo_semana(dia):
    inicio = inicio_semana(dia)
    return inicio, inicio + timedelta(days=6)


def intervalo_mes(dia):
    inicio = dia.replace(day=1)
    proximo = (inicio + timedelta(days=32)).replace(day=1)
    return inicio, proximo - timedelta(days=1)
