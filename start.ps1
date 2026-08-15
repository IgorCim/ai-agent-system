# Запуск AI Agent
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AI Agent - Запуск" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Выбери вариант:" -ForegroundColor Yellow
Write-Host "  1 — Десктоп-приложение (WebView2 окно)" -ForegroundColor Green
Write-Host "  2 — Локальный сервер + браузер" -ForegroundColor Green
Write-Host ""

$choice = Read-Host "Вариант (1/2, Enter = 1)"

Set-Location -LiteralPath "C:\Users\lesya\my_agent"
$env:AI_MODE = "zen"
$env:DEBUG = "false"

if ($choice -eq "2") {
    Write-Host ""
    Write-Host "Сервер: http://127.0.0.1:5000" -ForegroundColor Yellow
    Write-Host "Остановить: Ctrl+C" -ForegroundColor Yellow
    Start-Process "http://127.0.0.1:5000"
    python server.py
} else {
    python desktop_app.py
}

Write-Host ""
Write-Host "Сервер остановлен." -ForegroundColor Cyan
Read-Host "Нажми Enter, чтобы закрыть окно"
