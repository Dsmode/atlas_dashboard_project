# ATLAS

Dashboard pessoal modular (Python + Streamlit + MySQL).

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

