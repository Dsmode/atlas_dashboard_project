# Cria o atalho "ATLAS" na área de trabalho e no menu Iniciar.
# Uso: powershell -ExecutionPolicy Bypass -File launcher\criar_atalho.ps1
$ErrorActionPreference = "Stop"

$raiz = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $raiz ".venv\Scripts\pythonw.exe"
$launcher = Join-Path $raiz "launcher\launcher.py"
$icone = Join-Path $raiz "launcher\atlas.ico"

if (-not (Test-Path $pythonw)) {
    throw "Ambiente virtual não encontrado em $raiz\.venv. Rode instalar.ps1 primeiro."
}

$destinos = @(
    [Environment]::GetFolderPath("Desktop"),
    (Join-Path ([Environment]::GetFolderPath("Programs")) "")
)

$shell = New-Object -ComObject WScript.Shell
foreach ($pasta in $destinos) {
    $atalho = $shell.CreateShortcut((Join-Path $pasta "ATLAS.lnk"))
    $atalho.TargetPath = $pythonw
    $atalho.Arguments = "`"$launcher`""
    $atalho.WorkingDirectory = $raiz
    $atalho.IconLocation = $icone
    $atalho.Description = "ATLAS - dashboard pessoal"
    $atalho.Save()
    Write-Host "Atalho criado em $pasta"
}
