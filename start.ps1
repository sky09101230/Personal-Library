[CmdletBinding()]
param(
    [string]$BindAddress = "127.0.0.1",
    [ValidateRange(1, 65535)]
    [int]$Port = 8001
)

$ErrorActionPreference = "Stop"
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

function Get-DotEnvValue([string]$name) {
    $envPath = Join-Path $PSScriptRoot ".env"
    if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) { return "" }
    $line = Get-Content -LiteralPath $envPath | Where-Object { $_ -match "^\s*$([regex]::Escape($name))\s*=" } | Select-Object -First 1
    if (-not $line) { return "" }
    return (($line -split "=", 2)[1]).Trim().Trim('"').Trim("'")
}

$dataRoot = Get-DotEnvValue "LOCAL_STORAGE_ROOT"
if (-not $dataRoot) { $dataRoot = "E:\Personal-Library\data" }
if (-not [IO.Path]::IsPathRooted($dataRoot)) { $dataRoot = Join-Path $PSScriptRoot $dataRoot }
$workerStateRoot = $dataRoot
$workerPidPath = Join-Path $workerStateRoot "worker.pid"
$workerStdout = Join-Path $workerStateRoot "worker.stdout.log"
$workerStderr = Join-Path $workerStateRoot "worker.stderr.log"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Project Python was not found: $python. Run python -m venv .venv and install requirements.txt first."
}

Push-Location $PSScriptRoot
try {
    New-Item -ItemType Directory -Force -Path $dataRoot | Out-Null
    try {
        $probePath = Join-Path $workerStateRoot ".worker-write-test"
        Set-Content -LiteralPath $probePath -Value "ok" -NoNewline -Force
        Remove-Item -LiteralPath $probePath -Force -ErrorAction SilentlyContinue
        if (Test-Path -LiteralPath $workerPidPath -PathType Leaf) {
            Add-Content -LiteralPath $workerPidPath -Value "" -ErrorAction Stop
        }
    } catch {
        $workerStateRoot = Join-Path $PSScriptRoot ".runtime"
        New-Item -ItemType Directory -Force -Path $workerStateRoot | Out-Null
        $workerPidPath = Join-Path $workerStateRoot "worker.pid"
        $workerStdout = Join-Path $workerStateRoot "worker.stdout.log"
        $workerStderr = Join-Path $workerStateRoot "worker.stderr.log"
        Write-Warning "Worker state directory is not writable; using $workerStateRoot."
    }
    & $python manage.py check
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    function Test-WorkerProcessId([int]$processId) {
        if ($processId -le 0) { return $false }
        try {
            $process = Get-Process -Id $processId -ErrorAction Stop
            return $process.ProcessName -in @("python", "python3")
        } catch {
            return $false
        }
    }

    $workerRunning = $false
    if (Test-Path -LiteralPath $workerPidPath -PathType Leaf) {
        $savedPid = 0
        if ([int]::TryParse((Get-Content -LiteralPath $workerPidPath -Raw).Trim(), [ref]$savedPid)) {
            $workerRunning = Test-WorkerProcessId $savedPid
        }
        if (-not $workerRunning) { Remove-Item -LiteralPath $workerPidPath -Force -ErrorAction SilentlyContinue }
    }

    if ($workerRunning) {
        Write-Host "Literature worker is already running."
    } elseif (Get-DotEnvValue "MINERU_API_TOKEN") {
        $worker = Start-Process -FilePath $python -ArgumentList @("-u", "manage.py", "plab", "literature", "worker") -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput $workerStdout -RedirectStandardError $workerStderr -PassThru
        Set-Content -LiteralPath $workerPidPath -Value $worker.Id -NoNewline
        Write-Host "Started literature worker (PID $($worker.Id))."
    } else {
        Write-Warning "MINERU_API_TOKEN is not configured; website will start without the literature worker."
    }

    Write-Host "Starting Personal Library at http://${BindAddress}:$Port"
    & $python -m uvicorn config.asgi:application --host $BindAddress --port $Port
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
