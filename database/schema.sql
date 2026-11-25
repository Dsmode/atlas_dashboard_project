CREATE TABLE IF NOT EXISTS metas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    titulo VARCHAR(150) NOT NULL,
    descricao TEXT NULL,
    prioridade ENUM('baixa', 'media', 'alta') NOT NULL DEFAULT 'media',
    prazo DATE NULL,
    status ENUM('ativa', 'concluida', 'arquivada') NOT NULL DEFAULT 'ativa',
    data_criacao DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    data_conclusao DATETIME NULL,
    tipo_progresso ENUM('tarefas', 'quantidade', 'valor') NOT NULL DEFAULT 'tarefas',
    objetivo ENUM('aumentar', 'reduzir') NOT NULL DEFAULT 'aumentar',
    unidade VARCHAR(30) NULL,
    valor_inicial DECIMAL(14, 2) NULL,
    valor_alvo DECIMAL(14, 2) NULL,
    valor_atual DECIMAL(14, 2) NULL
);

CREATE TABLE IF NOT EXISTS tarefas_meta (
    id INT AUTO_INCREMENT PRIMARY KEY,
    meta_id INT NOT NULL,
    descricao VARCHAR(255) NOT NULL,
    prazo DATE NULL,
    ordem INT NOT NULL DEFAULT 0,
    concluida TINYINT(1) NOT NULL DEFAULT 0,
    data_conclusao DATETIME NULL,
    data_criacao DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (meta_id) REFERENCES metas (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS categorias_meta (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(30) NOT NULL UNIQUE,
    cor CHAR(7) NOT NULL DEFAULT '#b44cff'
);

CREATE TABLE IF NOT EXISTS metas_categorias (
    meta_id INT NOT NULL,
    categoria_id INT NOT NULL,
    PRIMARY KEY (meta_id, categoria_id),
    FOREIGN KEY (meta_id) REFERENCES metas (id) ON DELETE CASCADE,
    FOREIGN KEY (categoria_id) REFERENCES categorias_meta (id) ON DELETE CASCADE
);

-- Controle Financeiro: tabelas fin_*, sem ligação com as Metas Pessoais

CREATE TABLE IF NOT EXISTS fin_categorias (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tipo ENUM('entrada', 'gasto') NOT NULL,
    nome VARCHAR(30) NOT NULL,
    cor CHAR(7) NOT NULL DEFAULT '#b44cff',
    protegida TINYINT(1) NOT NULL DEFAULT 0,
    UNIQUE KEY uq_fin_categoria (tipo, nome)
);

CREATE TABLE IF NOT EXISTS fin_bancos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(30) NOT NULL UNIQUE,
    sigla VARCHAR(3) NOT NULL,
    cor CHAR(7) NOT NULL DEFAULT '#b44cff',
    ativo TINYINT(1) NOT NULL DEFAULT 1
);

-- Importação de extratos (OFX): histórico das importações e regras aprendidas na revisão

CREATE TABLE IF NOT EXISTS fin_importacoes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    data_hora DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    arquivo VARCHAR(255) NOT NULL,
    banco_id INT NULL,
    origem ENUM('conta', 'cartao') NOT NULL,
    observacao VARCHAR(255) NULL,
    periodo_inicio DATE NOT NULL,
    periodo_fim DATE NOT NULL,
    qtd_lidas INT NOT NULL DEFAULT 0,
    qtd_importadas INT NOT NULL DEFAULT 0,
    qtd_duplicadas INT NOT NULL DEFAULT 0,
    qtd_ignoradas INT NOT NULL DEFAULT 0,
    status ENUM('concluida', 'desfeita') NOT NULL DEFAULT 'concluida',
    FOREIGN KEY (banco_id) REFERENCES fin_bancos (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS fin_regras (
    id INT AUTO_INCREMENT PRIMARY KEY,
    padrao VARCHAR(80) NOT NULL UNIQUE,
    categoria_id INT NULL,
    tipo ENUM('fixo', 'variavel') NULL,
    ignorar TINYINT(1) NOT NULL DEFAULT 0,
    FOREIGN KEY (categoria_id) REFERENCES fin_categorias (id)
);

CREATE TABLE IF NOT EXISTS fin_lancamentos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tipo ENUM('entrada', 'fixo', 'variavel') NOT NULL,
    data DATE NOT NULL,
    descricao VARCHAR(80) NULL,
    categoria_id INT NOT NULL,
    -- NULL em item que só tem previsão
    valor DECIMAL(14, 2) NULL,
    valor_previsto DECIMAL(14, 2) NULL,
    forma ENUM('pix', 'debito', 'credito', 'dinheiro') NOT NULL,
    banco_id INT NULL,
    observacao VARCHAR(255) NULL,
    data_criacao DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    importacao_id INT NULL,
    chave_externa VARCHAR(64) NULL,
    -- Como a previsão estava antes de a importação preencher o valor (JSON), para o Desfazer
    previsao_anterior TEXT NULL,
    INDEX idx_fin_lancamentos_data (data),
    INDEX idx_fin_lancamentos_chave (banco_id, chave_externa),
    FOREIGN KEY (categoria_id) REFERENCES fin_categorias (id),
    FOREIGN KEY (banco_id) REFERENCES fin_bancos (id) ON DELETE SET NULL,
    FOREIGN KEY (importacao_id) REFERENCES fin_importacoes (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS fin_config (
    chave VARCHAR(40) PRIMARY KEY,
    valor VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS tri_config (
    chave VARCHAR(40) PRIMARY KEY,
    valor VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS tri_marcadores (
    id VARCHAR(80) PRIMARY KEY,
    nome VARCHAR(255) NOT NULL,
    tipo ENUM('sistema', 'usuario') NOT NULL DEFAULT 'usuario'
);

CREATE TABLE IF NOT EXISTS tri_importacoes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tipo ENUM('completa', 'incremental') NOT NULL,
    status ENUM('rodando', 'concluida', 'erro', 'interrompida') NOT NULL DEFAULT 'rodando',
    fase TINYINT NOT NULL DEFAULT 1,
    page_token VARCHAR(255) NULL,
    total_estimado INT NOT NULL DEFAULT 0,
    processados INT NOT NULL DEFAULT 0,
    history_id_inicial VARCHAR(40) NULL,
    pid INT NULL,
    iniciada_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizada_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    finalizada_em DATETIME NULL,
    mensagem_erro VARCHAR(500) NULL
);

CREATE TABLE IF NOT EXISTS tri_emails (
    id VARCHAR(32) PRIMARY KEY,
    thread_id VARCHAR(32) NOT NULL,
    remetente_nome VARCHAR(255) NULL,
    remetente_email VARCHAR(320) NULL,
    dominio VARCHAR(255) NULL,
    assunto VARCHAR(1000) NULL,
    snippet VARCHAR(600) NULL,
    data_email DATETIME NULL,
    tamanho INT NOT NULL DEFAULT 0,
    lido TINYINT(1) NOT NULL DEFAULT 0,
    categoria VARCHAR(20) NULL,
    list_unsubscribe TEXT NULL,
    list_unsubscribe_post VARCHAR(255) NULL,
    spf VARCHAR(20) NULL,
    dkim VARCHAR(20) NULL,
    dmarc VARCHAR(20) NULL,
    auth_resultado VARCHAR(1500) NULL,
    history_id VARCHAR(40) NULL,
    importacao_id INT NULL,
    atualizado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_tri_emails_remetente (remetente_email(191)),
    INDEX idx_tri_emails_dominio (dominio(191)),
    INDEX idx_tri_emails_data (data_email),
    INDEX idx_tri_emails_categoria (categoria),
    INDEX idx_tri_emails_importacao (importacao_id)
);

CREATE TABLE IF NOT EXISTS tri_email_marcadores (
    email_id VARCHAR(32) NOT NULL,
    marcador_id VARCHAR(80) NOT NULL,
    PRIMARY KEY (email_id, marcador_id),
    INDEX idx_tri_email_marcadores_marcador (marcador_id),
    FOREIGN KEY (email_id) REFERENCES tri_emails (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tri_email_campos (
    email_id VARCHAR(32) NOT NULL,
    campo VARCHAR(40) NOT NULL,
    valor VARCHAR(500) NOT NULL,
    PRIMARY KEY (email_id, campo),
    FOREIGN KEY (email_id) REFERENCES tri_emails (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tri_ruido (
    termo VARCHAR(120) PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS tri_protegidos (
    valor VARCHAR(320) PRIMARY KEY,
    tipo ENUM('dominio', 'email') NOT NULL,
    origem ENUM('padrao', 'usuario') NOT NULL DEFAULT 'usuario',
    criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tri_palavras_salvam (
    termo VARCHAR(120) PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS tri_cards (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(60) NOT NULL,
    cor VARCHAR(20) NOT NULL DEFAULT 'teal',
    entra_no_resumo TINYINT(1) NOT NULL DEFAULT 0,
    ordem INT NOT NULL DEFAULT 0,
    criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tri_card_criterios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    card_id INT NOT NULL,
    operador ENUM('e', 'ou', 'nao') NOT NULL,
    campo VARCHAR(20) NOT NULL,
    valor VARCHAR(255) NOT NULL,
    INDEX idx_tri_card_criterios_card (card_id),
    FOREIGN KEY (card_id) REFERENCES tri_cards (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tri_bloqueados (
    valor VARCHAR(320) PRIMARY KEY,
    tipo ENUM('dominio', 'email') NOT NULL,
    motivo VARCHAR(255) NULL,
    criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tri_acoes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tipo ENUM('marcar', 'arquivar', 'lixeira') NOT NULL,
    descricao VARCHAR(255) NOT NULL,
    quantidade INT NOT NULL DEFAULT 0,
    status ENUM('feita', 'desfeita') NOT NULL DEFAULT 'feita',
    criada_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    desfeita_em DATETIME NULL
);

CREATE TABLE IF NOT EXISTS tri_acao_itens (
    acao_id INT NOT NULL,
    email_id VARCHAR(32) NOT NULL,
    adicionados VARCHAR(500) NOT NULL DEFAULT '',
    removidos VARCHAR(500) NOT NULL DEFAULT '',
    PRIMARY KEY (acao_id, email_id),
    FOREIGN KEY (acao_id) REFERENCES tri_acoes (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tri_desinscricoes (
    remetente VARCHAR(320) PRIMARY KEY,
    dominio VARCHAR(255) NULL,
    metodo VARCHAR(20) NOT NULL,
    status ENUM('ok', 'falhou') NOT NULL,
    http_status INT NULL,
    mensagem VARCHAR(255) NULL,
    feita_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tri_card_modos (
    chave VARCHAR(20) PRIMARY KEY,
    modo ENUM('sugerir', 'marcar', 'quarentena') NOT NULL DEFAULT 'sugerir'
);

CREATE TABLE IF NOT EXISTS tri_execucoes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    origem ENUM('agendada', 'manual') NOT NULL,
    iniciada_em DATETIME NOT NULL,
    finalizada_em DATETIME NULL,
    status ENUM('ok', 'erro') NOT NULL DEFAULT 'ok',
    novos INT NOT NULL DEFAULT 0,
    resumo TEXT NULL,
    erro VARCHAR(500) NULL
);
