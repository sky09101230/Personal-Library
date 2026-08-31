[CmdletBinding()]
param(
    [string]$BindAddress = "127.0.0.1",
    [ValidateRange(1, 65535)]
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$python = "C:\Python314\python.exe"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Project Python was not found: $python"
}

Push-Location $PSScriptRoot
try {
    & $python manage.py check
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    Write-Host "Starting AgentSys at http://${BindAddress}:$Port"
    & $python -m uvicorn config.asgi:application --host $BindAddress --port $Port
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
