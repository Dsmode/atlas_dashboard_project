# ATLAS

Dashboard pessoal modular (Python + Streamlit + MySQL), com interface HUD em tema escuro, roxo neon e efeito de vidro (glassmorphism).

## Módulos (ferramentas)
- **Início:** logo, data e hora atuais, resumo do painel (Metas Semanais com dados reais da semana) e blocos reservados para as próximas ferramentas.
- **Metas Pessoais:** cadastro, edição e exclusão de metas, checklist de tarefas com arrastar para reordenar, prazos, prioridade, categorias coloridas criadas pelo usuário (várias por meta), painéis de métricas (semanais, mensais e atrasadas), busca por título e descrição e filtro por categorias.

## Executar
1. Inicie o MySQL (`net start MySQL80` em terminal administrador).
2. Copie `.env.example` para `.env` e preencha `DB_PASSWORD`.
3. Instale e rode:
```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\streamlit run app.py
```
O banco `atlas_db` e as tabelas são criados automaticamente na primeira execução.

## Estrutura
- `app.py`: configuração da página, CSS, menu lateral e roteamento dos módulos.
- `modules/`: um arquivo por módulo, cada um com `render()`.
- `database/`: conexão, `schema.sql` e consultas.
- `components/`: componente próprio do checklist arrastável.
- `assets/`: `style.css` (tema e vidro), `rede.svg` (fundo), `logo.png` e `favicon.png`.

## Novo módulo
Crie `modules/<nome>.py` com uma função `render()` e registre em `MODULOS` no `app.py`.
