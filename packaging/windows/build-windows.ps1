# Build the Scriptorum setup program for Windows.
# Usage (in PowerShell, from the kit folder):
#   powershell -ExecutionPolicy Bypass -File windows\build-windows.ps1 C:\Users\you\Downloads\M6-0.6.5
# Everything else is in build.py; see docs\BUILD-WINDOWS.md.
$ErrorActionPreference = "Stop"
$Kit = Split-Path -Parent $PSScriptRoot
$Py = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3.13 -c "import sys" 2>$null
    if ($LASTEXITCODE -eq 0) { $Py = @("py", "-3.13") }
}
if (-not $Py -and (Get-Command python3.13 -ErrorAction SilentlyContinue)) { $Py = @("python3.13") }
if (-not $Py) {
    Write-Error "Python 3.13 was not found. See docs\BUILD-WINDOWS.md, section 1."
    exit 1
}
$Exe = $Py[0]
$PyArgs = @()
if ($Py.Length -gt 1) { $PyArgs = $Py[1..($Py.Length - 1)] }
& $Exe @PyArgs (Join-Path $Kit "build.py") @args
exit $LASTEXITCODE
