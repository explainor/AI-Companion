$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Frontend = Join-Path $Root "frontend"
$Url = "http://127.0.0.1:5173/"

function Test-PortListening {
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $conn
}

function Start-Backend {
    if (Test-PortListening 8000) {
        Write-Host "Backend already running on 127.0.0.1:8000"
        return
    }
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-Command",
        "Set-Location -LiteralPath '$Root'; python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000"
    ) -WindowStyle Normal
}

function Start-Frontend {
    if (Test-PortListening 5173) {
        Write-Host "Frontend already running on 127.0.0.1:5173"
        return
    }
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-Command",
        "Set-Location -LiteralPath '$Frontend'; npm.cmd run dev -- --port 5173"
    ) -WindowStyle Normal
}

Start-Backend
Start-Frontend

for ($i = 0; $i -lt 20; $i++) {
    if (Test-PortListening 5173) { break }
    Start-Sleep -Milliseconds 500
}

Start-Process $Url
