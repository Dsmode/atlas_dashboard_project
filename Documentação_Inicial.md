# Atlas - Dashboard Pessoal Modular

O **Atlas** é um dashboard pessoal modular e interativo projetado para centralizar e abrigar diversas ferramentas de produtividade, acompanhamento e gestão pessoal desenvolvidas ao longo do tempo. Inspirado no titã que sustenta o mundo, o Atlas serve como a fundação e o suporte para o ecossistema de dados e metas do usuário.

---

## Tecnologias Utilizadas

* **Linguagem Principal:** Python 3.x
* **Ambiente de Desenvolvimento (IDE):** Visual Studio Code (VSCode)
* **Banco de Dados:** MySQL
* **Framework Web/GUI (Recomendado):** Streamlit (ou solução equivalente em Python)

---

## Arquitetura da Interface (HUD)

O sistema possui uma interface estilo **HUD (Heads-Up Display)** dividida em dois blocos centrais:

1. **Barra Lateral Esquerda (Sidebar Navigation):**
   * Menu fixo de navegação entre as diferentes ferramentas/módulos do ecossistema.
   * Inicialmente conta com duas opções clicáveis: **Início** e **Metas Pessoais**.
2. **Painel Principal Direita (Main View Area):**
   * Área dinâmica que renderiza os dados e ferramentas referentes à aba selecionada no menu lateral.

---

## Funcionalidades da Fase Inicial (V1.0)

### 1. 🏠 Aba "Início"
* **Objetivo:** Exibir a identidade visual do sistema e atuar como *landing page* interna.
* **Recursos V1.0:** Exibição do logo/símbolo oficial do **Atlas**.
* **Evolução Futura:** Painel de resumos (*widgets*), métricas consolidadas das outras ferramentas e notificações.

### 2. Aba "Metas Pessoais"
* **Objetivo:** Gestão, edição e acompanhamento do progresso de objetivos de curto, médio e longo prazo.
* **Recursos do Módulo:**
  * **Cadastro e Edição:** Inclusão de novas metas com título, descrição, prioridade (*Baixa*, *Média*, *Alta*) e prazo final.
  * **Checklist e Progresso Dinâmico:** Cada meta possui sub-tarefas (checklist). O progresso da meta é calculado e exibido dinamicamente por meio de barras de progresso (ex: 3/5 tarefas concluídas = 60%).
  * **Filtros e Visualização:** Opção de chaveamento de visualização **Mensal** vs. **Semanal** para organização de prazos.

---

## Modelagem Simplificada do Banco de Dados (`atlas_db`)

### Tabela: `metas`


### Tabela: `tarefas_meta`


---

## Estrutura de Diretórios do Projeto

```text
atlas/
│
├── .env                  # Variáveis de ambiente (credenciais MySQL)
├── requirements.txt      # Dependências do projeto
├── README.md             # Documentação de execução
│
├── database/
│   ├── connection.py     # Gerenciamento de conexão com o MySQL
│   └── schema.sql        # Scripts de criação das tabelas
│
├── modules/
│   ├── home.py           # Interface e lógica da aba Início
│   └── metas.py          # Interface e lógica da aba Metas Pessoais
│
├── assets/
│   └── logo.png          # Logo do projeto Atlas
│
└── app.py                # Arquivo principal (Configuração do HUD e Sidebar)
```