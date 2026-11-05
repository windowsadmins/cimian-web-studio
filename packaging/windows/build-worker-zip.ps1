<#
.SYNOPSIS
Builds the Windows worker installer: a zip holding the worker, with its own
Python and a venv with cwsctl, plus install.ps1 and uninstall.ps1.

.DESCRIPTION
Needs uv, and pnpm when the web assets have not been built yet. Writes
dist\CimianWebStudioWorker-<version>-win-x64.zip and prints its path. The zip
and scripts are unsigned.

-StageOnly leaves the unzipped folder in -Stage instead, for tests.
#>
[CmdletBinding()]
param(
    [string]$PythonVersion = '3.14',
    [string]$Stage,
    [switch]$StageOnly
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $repo

function Invoke-Checked([string]$Command, [string[]]$Arguments) {
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Command $($Arguments -join ' ') failed" }
}

$version = (& uv version --short).Trim()
$work = Join-Path ([IO.Path]::GetTempPath()) "cws-worker-$([Guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Path $work | Out-Null
try {
    # The web assets go in the wheel even though a worker never serves them, so
    # the one package is the same everywhere.
    if (-not (Test-Path 'src\cimian_web_studio\static\index.html')) {
        Push-Location web
        try {
            Invoke-Checked pnpm @('install', '--frozen-lockfile')
            Invoke-Checked pnpm @('build')
        } finally { Pop-Location }
    }
    Invoke-Checked uv @('build', '--wheel', '--out-dir', "$work\dist", '--quiet')
    $wheel = Get-ChildItem "$work\dist\*.whl" | Select-Object -First 1

    if (-not $Stage) { $Stage = Join-Path $work 'stage' }
    if (Test-Path $Stage) { Remove-Item -Recurse -Force $Stage }
    $tree = Join-Path $Stage 'worker'
    New-Item -ItemType Directory -Path $tree | Out-Null
    Invoke-Checked uv @('python', 'install', $PythonVersion, '--install-dir', "$tree\python", '--quiet')
    # Keep only the interpreter, not uv's own bookkeeping in the install folder.
    Get-ChildItem -Force "$tree\python" | Where-Object { $_.Name -notlike 'cpython-*' } |
        Remove-Item -Recurse -Force
    $interpreter = Get-ChildItem "$tree\python\cpython-*\python.exe" | Select-Object -First 1
    if (-not $interpreter) { throw "No python.exe under $tree\python" }
    Invoke-Checked uv @('venv', '--relocatable', '--python', $interpreter.FullName, "$tree\venv", '--quiet')
    Invoke-Checked uv @('pip', 'install', '--python', "$tree\venv\Scripts\python.exe", $wheel.FullName, '--quiet')

    $here = $PSScriptRoot
    Copy-Item "$here\run_worker.py", "$here\worker.conf.example", "$here\uninstall.ps1" $tree
    Copy-Item "$here\install.ps1", "$here\uninstall.ps1" $Stage
    if ($StageOnly) {
        Write-Output $Stage
        return
    }
    New-Item -ItemType Directory -Force -Path dist | Out-Null
    $zip = Join-Path $repo "dist\CimianWebStudioWorker-$version-win-x64.zip"
    if (Test-Path $zip) { Remove-Item $zip }
    Compress-Archive -Path "$Stage\*" -DestinationPath $zip -CompressionLevel Optimal
    Write-Output $zip
} finally {
    if (-not $StageOnly) { Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue }
}
