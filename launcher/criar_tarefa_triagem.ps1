# Cria no Agendador de Tarefas do Windows a tarefa "ATLAS Triagem", que sincroniza o Gmail e faz a triagem dos
# e-mails novos a cada 2 horas. Roda só com você logado e, se o PC estava desligado na hora, roda ao ligar.
# Uso:     powershell -ExecutionPolicy Bypass -File launcher\criar_tarefa_triagem.ps1
# Remover: powershell -ExecutionPolicy Bypass -File launcher\criar_tarefa_triagem.ps1 -Remover
param([switch]$Remover)
$ErrorActionPreference = "Stop"

$nome = "ATLAS Triagem"
$raiz = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $raiz ".venv\Scripts\pythonw.exe"

if ($Remover) {
    if (Get-ScheduledTask -TaskName $nome -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $nome -Confirm:$false
        Write-Host "Tarefa '$nome' removida."
    } else {
        Write-Host "A tarefa '$nome' não existe."
    }
    return
}

if (-not (Test-Path $pythonw)) {
    throw "Ambiente virtual não encontrado em $raiz\.venv. Rode instalar.ps1 primeiro."
}

$acao = New-ScheduledTaskAction -Execute $pythonw -Argument "-m database.triagem.executor --agendada" -WorkingDirectory $raiz
$gatilho = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) `
    -RepetitionInterval (New-TimeSpan -Hours 2) -RepetitionDuration (New-TimeSpan -Days 3650)
$configuracao = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive

Register-ScheduledTask -TaskName $nome -Action $acao -Trigger $gatilho -Settings $configuracao -Principal $principal `
    -Description "ATLAS: sincroniza o Gmail e faz a triagem dos e-mails novos (a cada 2 horas)" -Force | Out-Null
Write-Host "Tarefa '$nome' criada: a primeira execução é em 5 minutos e depois a cada 2 horas."
Write-Host "O MySQL precisa estar ligado. Erros aparecem em uma faixa ao abrir a Central de Triagem."
