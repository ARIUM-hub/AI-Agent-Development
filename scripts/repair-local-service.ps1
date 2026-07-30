param(
    [string]$TaskName = "CustomerIssueAgentLocalService",
    [string]$PythonExe = "",
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 58623,
    [switch]$DryRun
)

$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$StartScript = Join-Path $PSScriptRoot "start-local-service.ps1"
$HealthcheckUrl = ("http://{0}:{1}/api/records/summary" -f $BindHost, $Port)

function Write-Status {
    param(
        [string]$Name,
        [string]$Value
    )

    Write-Output ("{0}={1}" -f $Name, $Value)
}

function Test-Healthcheck {
    try {
        $response = Invoke-WebRequest -Uri $HealthcheckUrl -UseBasicParsing -TimeoutSec 3
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Ensure-ScheduledTaskExists {
    $task = Get-ScheduledTask | Where-Object { $_.TaskName -eq $TaskName }
    if ($task) {
        Write-Status "TASK_PRESENT" "true"
        return
    }

    Write-Status "TASK_PRESENT" "false"
    Write-Status "TASK_ACTION" "register_missing_task"

    if ($DryRun) {
        return
    }

    $registerArgs = @(
        "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $PSScriptRoot "register-local-service-task.ps1")
    )
    if ($PythonExe) {
        $registerArgs += @("-PythonExe", $PythonExe)
    }

    & powershell @registerArgs
}

Write-Status "PROJECT_ROOT" $ProjectRoot
Write-Status "TASK_NAME" $TaskName
Write-Status "HEALTHCHECK_URL" $HealthcheckUrl
Write-Status "START_SCRIPT" $StartScript

Write-Status "TASK_ACTION" "verify_scheduled_task"
Ensure-ScheduledTaskExists

Write-Status "TASK_ACTION" "verify_service_health"
$healthy = Test-Healthcheck
Write-Status "SERVICE_HEALTHY" ($(if ($healthy) { "true" } else { "false" }))

if ($DryRun) {
    Write-Status "TASK_ACTION" "repair_via_start_script"
    if ($healthy) {
        Write-Status "TASK_ACTION" "service_already_running"
    }
    return
}

if ($healthy) {
    Write-Status "TASK_ACTION" "service_already_running"
    return
}

Write-Status "TASK_ACTION" "repair_via_start_script"

$startArgs = @(
    "-ExecutionPolicy", "Bypass",
    "-File", $StartScript,
    "-ForceRestart",
    "-BindHost", $BindHost,
    "-Port", "$Port"
)
if ($PythonExe) {
    $startArgs += @("-PythonExe", $PythonExe)
}

& powershell @startArgs
