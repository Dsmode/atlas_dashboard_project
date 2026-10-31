CREATE DATABASE IF NOT EXISTS atlas_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE atlas_db;

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

-- Controle Financeiro: tabelas próprias, sem ligação com as Metas Pessoais

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

CREATE TABLE IF NOT EXISTS fin_lancamentos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tipo ENUM('entrada', 'fixo', 'variavel') NOT NULL,
    data DATE NOT NULL,
    descricao VARCHAR(80) NULL,
    categoria_id INT NOT NULL,
    valor DECIMAL(14, 2) NOT NULL,
    forma ENUM('pix', 'debito', 'credito', 'dinheiro') NOT NULL,
    banco_id INT NULL,
    observacao VARCHAR(255) NULL,
    data_criacao DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_fin_lancamentos_data (data),
    FOREIGN KEY (categoria_id) REFERENCES fin_categorias (id),
    FOREIGN KEY (banco_id) REFERENCES fin_bancos (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS fin_config (
    chave VARCHAR(40) PRIMARY KEY,
    valor VARCHAR(255) NOT NULL
);
