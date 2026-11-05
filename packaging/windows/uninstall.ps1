<#
.SYNOPSIS
Removes the Cimian Web Studio worker.

.DESCRIPTION
Stops and removes the scheduled task and deletes the program folder. The data
folder, with the config, token and log, stays unless -RemoveData is given.
Run it from an elevated PowerShell; -NoTask skips the task, for a test
install made with install.ps1 -NoTask.
#>
[CmdletBinding()]
param(
    [string]$Prefix = (Join-Path $env:ProgramFiles 'Cimian Web Studio Worker'),
    [string]$DataDir = (Join-Path $env:ProgramData 'Cimian Web Studio Worker'),
    [switch]$RemoveData,
    [switch]$NoTask
)
$ErrorActionPreference = 'Stop'
$TaskPath = '\Cimian Web Studio\'
$TaskName = 'Worker'

if (-not $NoTask) {
    $task = Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        Stop-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName
        Unregister-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -Confirm:$false
    }
}
# The worker's Python may take a moment to exit after the task stops.
for ($i = 0; $i -lt 10 -and (Test-Path $Prefix); $i++) {
    try { Remove-Item -Recurse -Force $Prefix } catch { Start-Sleep -Seconds 1 }
}
if (Test-Path $Prefix) { throw "Could not remove $Prefix; is the worker still running?" }
if ($RemoveData -and (Test-Path $DataDir)) { Remove-Item -Recurse -Force $DataDir }
Write-Output "Removed $Prefix$(if ($RemoveData) { " and $DataDir" })."
