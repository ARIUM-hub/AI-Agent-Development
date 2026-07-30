param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 58623,
    [string]$PythonExe = "",
    [switch]$DryRun,
    [switch]$ForceReinstall,
    [switch]$ForceRestart
)

$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ExpectedSrc = Join-Path $ProjectRoot "src"
$LogDir = Join-Path $ProjectRoot "work"
$BootstrapLog = Join-Path $LogDir "service-bootstrap.log"
$StdoutLog = Join-Path $LogDir "service-stdout.log"
$StderrLog = Join-Path $LogDir "service-stderr.log"
$PipIndexUrl = "https://pypi.tuna.tsinghua.edu.cn/simple"
$ServiceUrl = "http://{0}:{1}" -f $BindHost, $Port
$HealthUrl = "$ServiceUrl/api/records/summary"
$ProcessPattern = "uvicorn\s+customer_issue_agent\.app:create_app"

function Write-Status {
    param(
        [string]$Name,
        [string]$Value
    )

    Write-Output ("{0}={1}" -f $Name, $Value)
}

function Write-BootstrapLog {
    param([string]$Message)

    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $BootstrapLog -Encoding UTF8 -Value ("[{0}] {1}" -f $timestamp, $Message)
}

function Resolve-PythonExecutable {
    if ($PythonExe) {
        return $PythonExe
    }

    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $resolved = & $pythonCommand.Source "-c" "import sys; print(sys.executable)"
        return ($resolved | Select-Object -First 1).Trim()
    }

    throw "python.exe was not found. Pass -PythonExe explicitly."
}

function Get-EditablePthPath {
    param([string]$ResolvedPython)

    $pythonCode = 'import site; paths = site.getsitepackages() + [site.getusersitepackages()]; print(chr(10).join(dict.fromkeys(paths)))'
    $pythonArgs = @("-c", $pythonCode)
    $sitePathsOutput = & $ResolvedPython @pythonArgs
    foreach ($sitePath in ($sitePathsOutput -split "`r?`n")) {
        if (-not $sitePath) {
            continue
        }
        $candidate = Join-Path $sitePath "__editable__.customer_issue_agent-0.1.0.pth"
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }
    return $null
}

function Test-ServiceHealthy {
    try {
        $response = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 3
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Get-ServiceProcesses {
    return @(
        Get-CimInstance Win32_Process |
            Where-Object { $_.CommandLine -and $_.CommandLine -match $ProcessPattern }
    )
}

function Stop-ServiceProcesses {
    param([object[]]$Processes)

    if (-not $Processes -or $Processes.Count -eq 0) {
        return
    }

    Write-Status "TASK_ACTION" "stop_existing_customer_issue_agent_processes"
    Write-BootstrapLog ("Stopping stale processes: {0}" -f (($Processes | ForEach-Object { $_.ProcessId }) -join ","))

    if ($DryRun) {
        return
    }

    foreach ($process in $Processes) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

$ResolvedPython = Resolve-PythonExecutable
$EditablePthPath = Get-EditablePthPath -ResolvedPython $ResolvedPython
$EditableTarget = ""
if ($EditablePthPath) {
    $EditableTarget = (Get-Content -LiteralPath $EditablePthPath -Raw -Encoding UTF8).Trim()
}
$ExpectedSrcNormalized = [System.IO.Path]::GetFullPath($ExpectedSrc)
$EditableMatches = $EditableTarget -and ([System.IO.Path]::GetFullPath($EditableTarget) -eq $ExpectedSrcNormalized)
$ServiceProcesses = Get-ServiceProcesses
$ServiceProcessIds = @($ServiceProcesses | ForEach-Object { $_.ProcessId })
$PortListeners = @(
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
)
$PortOwnedByService = $PortListeners.Count -gt 0 -and (@($PortListeners | Where-Object { $_ -in $ServiceProcessIds }).Count -eq $PortListeners.Count)

Write-Status "PROJECT_ROOT" $ProjectRoot
Write-Status "EXPECTED_SRC" $ExpectedSrc
Write-Status "SERVICE_URL" $ServiceUrl
Write-Status "PYTHON_EXE" $ResolvedPython
if ($EditablePthPath) {
    Write-Status "EDITABLE_PTH" $EditablePthPath
} else {
    Write-Status "EDITABLE_PTH" "<missing>"
}
if ($EditableTarget) {
    Write-Status "EDITABLE_TARGET" $EditableTarget
} else {
    Write-Status "EDITABLE_TARGET" "<missing>"
}

if ($PortListeners.Count -gt 0 -and -not $PortOwnedByService) {
    throw ("Port {0} is already in use by another process: {1}" -f $Port, ($PortListeners -join ","))
}

if ($EditableMatches -and -not $ForceReinstall -and -not $ForceRestart -and $PortOwnedByService -and (Test-ServiceHealthy)) {
    Write-Status "TASK_ACTION" "service_already_running"
    Write-BootstrapLog "Current worktree service is already healthy. Skipping restart."
    return
}

if ($ForceReinstall -or -not $EditableMatches) {
    Write-Status "TASK_ACTION" "repair_editable_install"
    Write-Status "PIP_INDEX_URL" $PipIndexUrl
    Write-BootstrapLog "Editable install does not point at the current src directory. Reinstalling."

    if (-not $DryRun) {
        Push-Location $ProjectRoot
        try {
            & $ResolvedPython "-m" "pip" "install" "-e" ".[dev]" "-i" $PipIndexUrl
        } finally {
            Pop-Location
        }
    }
}

if ($ForceRestart -or $ServiceProcesses.Count -gt 0 -or $PortOwnedByService) {
    Stop-ServiceProcesses -Processes $ServiceProcesses
}

Write-Status "TASK_ACTION" "start_uvicorn"
Write-Status "UVICORN_ARGS" ("-m uvicorn customer_issue_agent.app:create_app --factory --app-dir src --host {0} --port {1}" -f $BindHost, $Port)
Write-BootstrapLog "Starting a new uvicorn service instance."

if ($DryRun) {
    return
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$process = Start-Process -FilePath $ResolvedPython `
    -ArgumentList @("-m", "uvicorn", "customer_issue_agent.app:create_app", "--factory", "--app-dir", "src", "--host", $BindHost, "--port", "$Port") `
    -WorkingDirectory $ProjectRoot `
    -RedirectStandardOutput $StdoutLog `
    -RedirectStandardError $StderrLog `
    -WindowStyle Hidden `
    -PassThru

Write-Status "STARTED_PID" "$($process.Id)"
Write-BootstrapLog ("Service started. PID={0}" -f $process.Id)
