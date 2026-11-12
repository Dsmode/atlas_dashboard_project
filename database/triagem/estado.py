"""Em que pé está a importação, para a tela. Regra pura: recebe o que o banco e a trava dizem e devolve o estado."""


def fmt_int(n):
    return f"{int(n):,}".replace(",", ".")


def estado_importacao(*, rodando, ultima, pendente, historico):
    """`rodando`: a trava do MySQL está em uso. `ultima`: última linha de tri_importacoes. `pendente`: carga
    completa que não terminou. `historico`: historyId guardado (só existe depois da primeira carga).

    Devolve {"fase": ..., "processados", "total", "fracao"}. Fases:
      nunca     ainda não importou nada
      rodando   há um processo sincronizando agora
      pausada   a carga completa parou no meio (pausa, queda ou processo encerrado) e pode ser retomada
      erro      a última tentativa falhou
      em_dia    a caixa está sincronizada
    """
    base = {"processados": 0, "total": 0, "fracao": None}
    job = pendente if pendente else ultima
    if job and job["tipo"] == "completa":
        total = max(job["total_estimado"], job["processados"], 1)
        base.update(processados=job["processados"], total=total, fracao=min(1.0, job["processados"] / total))
    if rodando:
        return {**base, "fase": "rodando"}
    if pendente:
        return {**base, "fase": "erro" if pendente["status"] == "erro" else "pausada"}
    if ultima and ultima["status"] == "erro":
        return {**base, "fase": "erro"}
    return {**base, "fase": "em_dia" if historico else "nunca"}
