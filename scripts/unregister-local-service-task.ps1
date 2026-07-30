param(
    [string]$TaskName = "CustomerIssueAgentLocalService",
    [switch]$DryRun
)

$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ErrorActionPreference = "Stop"

Write-Output "TASK_NAME=$TaskName"

if ($DryRun) {
    return
}

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Output "UNREGISTERED_TASK=$TaskName"
} else {
    Write-Output "UNREGISTERED_TASK=<missing>"
}
