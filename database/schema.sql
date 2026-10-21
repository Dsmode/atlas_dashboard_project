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
    data_conclusao DATETIME NULL
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
