# Prepara o ATLAS numa máquina nova: ambiente virtual, dependências, .env e atalho.
# Uso: powershell -ExecutionPolicy Bypass -File instalar.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 1. Python 3.13
$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command python -ErrorAction SilentlyContinue }
if (-not $py) {
    throw "Python não encontrado. Instale o Python 3.13 em https://www.python.org/downloads/ e rode de novo."
}
$versao = if ($py.Name -eq "py.exe") { & py -3.13 --version 2>$null } else { & python --version }
if ($versao -notmatch "3\.13") {
    throw "O ATLAS foi desenvolvido para Python 3.13 (encontrado: $versao). Instale a versão 3.13."
}

# 2. Ambiente virtual e dependências
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Criando o ambiente virtual..."
    if ($py.Name -eq "py.exe") { & py -3.13 -m venv .venv } else { & python -m venv .venv }
}
Write-Host "Instalando dependências..."
& .venv\Scripts\python.exe -m pip install --quiet -r requirements.txt

# 3. Arquivo .env
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Arquivo .env criado. Abra-o e preencha DB_PASSWORD com a senha do seu MySQL."
}

# 4. Atalho
& powershell -ExecutionPolicy Bypass -File launcher\criar_atalho.ps1

Write-Host ""
Write-Host "Pronto. Confira se o MySQL está ativo e a senha no .env, depois abra o ATLAS pelo atalho."
