param(
    [string]$TaskName = "CustomerIssueAgentLocalService",
    [string]$PythonExe = "",
    [int]$RestartCount = 3,
    [timespan]$RestartInterval = (New-TimeSpan -Minutes 1),
    [switch]$DryRun
)

$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BootstrapScript = Join-Path $PSScriptRoot "start-local-service.ps1"
$ResolvedPython = ""
if ($PythonExe) {
    $ResolvedPython = $PythonExe
} else {
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "python.exe was not found. Pass -PythonExe explicitly."
    }
    $resolved = & $command.Source "-c" "import sys; print(sys.executable)"
    $ResolvedPython = ($resolved | Select-Object -First 1).Trim()
}
$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$PowerShellExe = (Get-Command powershell.exe).Source
$Argument = '-ExecutionPolicy Bypass -File "' + $BootstrapScript + '" -PythonExe "' + $ResolvedPython + '"'
$RestartIntervalText = $RestartInterval.ToString("c")

Write-Output "TASK_NAME=$TaskName"
Write-Output "TRIGGER=AtLogOn"
Write-Output "BOOTSTRAP_SCRIPT=$BootstrapScript"
Write-Output "PYTHON_EXE=$ResolvedPython"
Write-Output "POWERSHELL_EXE=$PowerShellExe"
Write-Output "TASK_ARGUMENT=$Argument"
Write-Output "RESTART_COUNT=$RestartCount"
Write-Output "RESTART_INTERVAL=$RestartIntervalText"

if ($DryRun) {
    return
}

$action = New-ScheduledTaskAction -Execute $PowerShellExe -Argument $Argument
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $CurrentUser
$principal = New-ScheduledTaskPrincipal -UserId $CurrentUser -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount $RestartCount `
    -RestartInterval $RestartInterval

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Output "REGISTERED_TASK=$TaskName"
