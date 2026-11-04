# ATLAS

Dashboard pessoal modular (Python + Streamlit + MySQL), com interface HUD em tema escuro, roxo neon e efeito de vidro (glassmorphism).

## Módulos (ferramentas)
- **Início:** logo, data e hora atuais, resumo do painel (Metas Semanais e gráfico empilhado de metas concluídas, pendentes e atrasadas por semana ou por mês, ambos com dados reais) e blocos reservados para as próximas ferramentas.
- **Metas Pessoais:** cadastro, edição e exclusão de metas com três tipos de progresso (checklist de tarefas com arrastar para reordenar, quantidade com botões −/+ e valor em R$ com adicionar/remover, inclusive metas de redução, aviso de meta atingida e ritmo até o prazo), prazos, prioridade, categorias coloridas criadas pelo usuário (várias por meta), painéis de métricas (semanais, mensais e atrasadas), busca por título e descrição, filtro por categorias e exportação/importação dos dados em JSON (com mesclagem e tratamento de duplicadas).
- **Controle Financeiro:** entradas, gastos fixos e gastos variáveis por mês (data, descrição, categoria, valor, forma de pagamento, banco e observação), com seletor de mês, filtros, edição/exclusão e cópia dos gastos fixos do mês anterior. Dashboard com resumo do mês, entradas × saídas (6 meses), fluxo de caixa acumulado (12 meses), rosca por categoria ou tipo e ranking das 5 categorias com mais gastos. Configurações de categorias (renomear, cores, criar e excluir), bancos e saldo inicial. A aba Importar é uma prévia (em desenvolvimento).

## Instalação (Windows 10/11)
Pré-requisitos: Python 3.13 e MySQL Server em execução (`net start MySQL80` em terminal administrador, se o serviço estiver parado).

```
git clone https://github.com/Dsmode/atlas_dashboard_project.git
cd atlas_dashboard_project
powershell -ExecutionPolicy Bypass -File instalar.ps1
```
O script cria o `.venv`, instala as dependências, cria o `.env` (preencha `DB_PASSWORD`) e coloca o atalho **ATLAS** na área de trabalho e no menu Iniciar. O banco `atlas_db` e as tabelas são criados automaticamente na primeira execução.

## Executar
- **Atalho ATLAS:** abre o app numa janela própria. Só uma instância por vez; fechar a janela encerra o servidor.
- **Modo desenvolvimento:** `.venv\Scripts\streamlit run app.py` (abre no navegador).

## Estrutura
- `app.py`: configuração da página, CSS, menu lateral e roteamento dos módulos.
- `modules/`: um arquivo por módulo, cada um com `render()`; módulos maiores viram pacote (`modules/financas/`, um arquivo por aba).
- `database/`: conexão, `schema.sql` e consultas.
- `components/`: componente próprio do checklist arrastável.
- `launcher/`: `launcher.py` (janela pywebview + servidor Streamlit), `criar_atalho.ps1` e `atlas.ico`. `instalar.ps1` fica na raiz.
- `assets/`: `style.css` (tema e vidro), `financas/` (estilos do Controle Financeiro), `rede.svg` (fundo), `logo.png` e `favicon.png`.

## Novo módulo
Crie `modules/<nome>.py` com uma função `render()` e registre em `MODULOS` no `app.py`.
