# FPV Drone — запуск дашборду + відео з антени
# .\start.ps1

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

Write-Host "=== FPV Drone ===" -ForegroundColor Green
Write-Host "[1/3] Dashboard (Docker)..."

Set-Location $Root
docker compose up -d --build dashboard

Write-Host "[2/3] Чекаю дашборд..."
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:5000/api/targets" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {}
    Start-Sleep -Seconds 1
}

if (-not $ready) {
    Write-Host "Дашборд не відповідає на порту 5000" -ForegroundColor Red
    exit 1
}

Write-Host "[3/3] Відео з антени..." -ForegroundColor Green
Write-Host "Камера: USB Video (не вебкамера ноута)" -ForegroundColor Yellow
Write-Host "ARM/DISARM: Wi-Fi Drone_Companion_AP / 123456789_FPV" -ForegroundColor Yellow
Write-Host "Браузер: http://127.0.0.1:5000" -ForegroundColor Cyan

$videoDir = Join-Path $Root "Computer_program"
Set-Location $videoDir

$env:DASHBOARD_HOST = "http://127.0.0.1:5000"
$env:CAMERA_NAME = "USB Video"
$env:ALLOW_WEBCAM_FALLBACK = "0"
$env:HEADLESS = "0"

$venvPython = Join-Path $Root "venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    & $venvPython video_get.py
} else {
    python video_get.py
}
