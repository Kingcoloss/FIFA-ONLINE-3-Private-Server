@echo off
rem Phase 1 of the .NET move (strangler): the .NET host (dotnetVersion\src\FO3.Host) owns
rem https://APSEODESK172:443 and the messenger, and forwards every game request to the Python
rem server, which then listens on 127.0.0.1:18080 only (its admin page stays on :8088).
rem Setup as for play.bat (docs\3sea-client.md), plus the .NET 10 SDK. Each server gets its own
rem window; close both to stop. Unhandled requests: https://127.0.0.1/_fo3/fallbacks
cd /d "%~dp0"
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'start_all\.py|http_config\.py|messenger\.py|FO3\.Host' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
if "%FO3_HTTP_BIND%"=="" set FO3_HTTP_BIND=0.0.0.0
if "%FO3_MESSENGER_PORT%"=="" set FO3_MESSENGER_PORT=28002
set FO3_HOST_BIND=%FO3_HTTP_BIND%
dotnet build -c Release -v q dotnetVersion\src\FO3.Host || (echo .NET build failed & pause & exit /b 1)
start "FO3 python (backend)" cmd /c "set FO3_HTTP_BIND=127.0.0.1&& python http_config.py 18080"
start "FO3 .NET host" dotnet run --no-build -c Release --project dotnetVersion\src\FO3.Host -- --Fo3:Https:Bind=%FO3_HOST_BIND% --Fo3:Messenger:Port=%FO3_MESSENGER_PORT%
timeout /t 6 /nobreak >nul
set __COMPAT_LAYER=RunAsInvoker
start "" "%~dp0launcher\fifalauncher.exe"
