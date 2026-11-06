from database.cores import COR_NEUTRA

# Existe uma "Outros" em cada tipo: recebe os lançamentos das categorias excluídas e não pode ser excluída.
NOME_OUTROS = "Outros"
COR_OUTROS = COR_NEUTRA

CATEGORIAS_GASTO = [
    ("Casa", "#4dd2a0"),
    ("Alimentação", "#ff6b7a"),
    ("Transporte", "#8f7bff"),
    ("Saúde", "#4da3ff"),
    ("Educação", "#ffd166"),
    ("Lazer", "#ffa94d"),
    ("Família", "#ff7ad9"),
    ("Assinaturas", "#5ce1e6"),
    ("Compras", "#c38bff"),
    (NOME_OUTROS, COR_OUTROS),
]
CATEGORIAS_ENTRADA = [
    ("Salário", "#4dd2a0"),
    ("Rescisão", "#ffd166"),
    ("Freelance", "#4da3ff"),
    ("Rendimento", "#c38bff"),
    ("Presente", "#ff7ad9"),
    (NOME_OUTROS, COR_OUTROS),
]
# (nome, sigla, cor): a sigla colorida faz o papel da logo.
BANCOS = [
    ("Nubank", "Nu", "#8a2be2"),
    ("Sicoob", "Sc", "#00a091"),
    ("PicPay", "Pp", "#21c25e"),
    ("Caixa", "Cx", "#1c6fd1"),
]


def criar_padroes(cur):
    """Grava os padrões uma única vez; depois disso, renomear ou excluir um deles não o traz de volta."""
    cur.execute("SELECT 1 FROM fin_config WHERE chave = 'padroes_criados'")
    if cur.fetchone():
        return
    for tipo, lista in (("gasto", CATEGORIAS_GASTO), ("entrada", CATEGORIAS_ENTRADA)):
        for nome, cor in lista:
            cur.execute(
                "INSERT IGNORE INTO fin_categorias (tipo, nome, cor, protegida) VALUES (%s, %s, %s, %s)",
                (tipo, nome, cor, int(nome == NOME_OUTROS)),
            )
    for nome, sigla, cor in BANCOS:
        cur.execute("INSERT IGNORE INTO fin_bancos (nome, sigla, cor) VALUES (%s, %s, %s)", (nome, sigla, cor))
    cur.execute("INSERT INTO fin_config (chave, valor) VALUES ('padroes_criados', '1')")
