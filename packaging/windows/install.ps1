<#
.SYNOPSIS
Installs the Cimian Web Studio worker from this folder.

.DESCRIPTION
Copies the worker, with its own Python, to -Prefix. Keeps its config, token
and log in -DataDir, which only SYSTEM, Administrators and the worker's
account can read. Registers a scheduled task that starts the worker at boot
as NT AUTHORITY\LOCAL SERVICE, never as SYSTEM or an administrator. Run it
from an elevated PowerShell. Running it again upgrades the worker and keeps
the config and token.

-NoTask installs without the scheduled task, as the current user, for a test
install that does not need elevation.
#>
[CmdletBinding()]
param(
    [string]$Prefix = (Join-Path $env:ProgramFiles 'Cimian Web Studio Worker'),
    [string]$DataDir = (Join-Path $env:ProgramData 'Cimian Web Studio Worker'),
    [string]$Url,
    [string]$Id,
    [string]$TokenFile,
    [switch]$NoTask
)
$ErrorActionPreference = 'Stop'
$TaskPath = '\Cimian Web Studio\'
$TaskName = 'Worker'
$ServiceAccount = 'NT AUTHORITY\LOCAL SERVICE'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$elevated = ([Security.Principal.WindowsPrincipal]$identity).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $NoTask -and -not $elevated) {
    throw 'Run this from an elevated PowerShell, or pass -NoTask for a test install.'
}
$account = if ($NoTask) { $identity.Name } else { $ServiceAccount }
$source = Join-Path $PSScriptRoot 'worker'
if (-not (Test-Path (Join-Path $source 'venv'))) {
    throw "No worker found next to this script at $source."
}

function Write-Utf8([string]$Path, [string[]]$Lines) {
    [IO.File]::WriteAllLines($Path, $Lines, [Text.UTF8Encoding]::new($false))
}

function Set-Access([string]$Path, [string[]]$Grants) {
    & icacls.exe $Path /inheritance:r /grant:r @Grants | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "icacls failed on $Path" }
}

if (-not $NoTask) {
    $existing = Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) { Stop-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName }
}

# The program folder: replaced whole, so an upgrade leaves nothing behind.
if (Test-Path $Prefix) { Remove-Item -Recurse -Force $Prefix }
Copy-Item -Recurse $source $Prefix
$python = Get-ChildItem (Join-Path $Prefix 'python') -Directory -Filter 'cpython-*' |
    Select-Object -First 1
if (-not $python) { throw "No bundled Python under $Prefix\python." }
$venvConfig = Join-Path $Prefix 'venv\pyvenv.cfg'
$lines = Get-Content $venvConfig | ForEach-Object {
    if ($_ -match '^home\s*=') { "home = $($python.FullName)" } else { $_ }
}
Write-Utf8 $venvConfig $lines

# The data folder: config, token and log. Kept across upgrades and uninstalls.
$logs = Join-Path $DataDir 'logs'
New-Item -ItemType Directory -Force -Path $DataDir, $logs | Out-Null
$conf = Join-Path $DataDir 'worker.conf'
Copy-Item (Join-Path $Prefix 'worker.conf.example') (Join-Path $DataDir 'worker.conf.example') -Force
if ($Url -and $Id) {
    Write-Utf8 $conf @(
        '# Written by install.ps1. The token goes in worker.token.',
        "url = `"$Url`"",
        "id = `"$Id`""
    )
}
$token = Join-Path $DataDir 'worker.token'
if ($TokenFile) {
    Write-Utf8 $token @((Get-Content -Raw $TokenFile).Trim())
} elseif (-not (Test-Path $token)) {
    Write-Utf8 $token @()
}

# The worker's account reads its config and token and writes only its log. A
# test install's own user keeps change rights, so it can install again.
$read = if ($NoTask) { 'M' } else { 'RX' }
$admins = '*S-1-5-32-544:(OI)(CI)F'
$system = '*S-1-5-18:(OI)(CI)F'
Set-Access $DataDir @($system, $admins, "${account}:(OI)(CI)$read")
Set-Access $logs @($system, $admins, "${account}:(OI)(CI)M")
Set-Access $token @('*S-1-5-18:F', '*S-1-5-32-544:F', "${account}:$(if ($NoTask) { 'M' } else { 'R' })")

$interpreter = Join-Path $Prefix 'venv\Scripts\python.exe'
$launcher = Join-Path $Prefix 'run_worker.py'
if ($NoTask) {
    Write-Output "Installed without a task. Start it with:"
    Write-Output "& '$interpreter' '$launcher' --data '$DataDir'"
    return
}

$action = New-ScheduledTaskAction -Execute $interpreter `
    -Argument "`"$launcher`" --data `"$DataDir`"" -WorkingDirectory $DataDir
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId $ServiceAccount -LogonType ServiceAccount -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -Action $action `
    -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName
Write-Output "Installed to $Prefix and started the task $TaskPath$TaskName."
Write-Output "Config and token: $DataDir. Log: $logs\worker.log."
