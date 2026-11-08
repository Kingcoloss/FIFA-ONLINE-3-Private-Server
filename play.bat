@echo off
rem One click: start the private server (own window; close it to stop the server)
rem and then the game. Setup first (README, docs\3sea-client.md): Python + cryptography,
rem hosts entry "127.0.0.1 APSEODESK172", certs\server.pem, gamedata\fifadb.sqlite and
rem launcher\fifalauncher.exe built from launcher\fifalauncher.cs.
rem The client is the 3Sea one at F:\FOServer\3Sea FIFA Online 3 unless set here (fo3conf.py):
rem set FO3_GAME=F:\FOServer\3Sea FIFA Online 3
rem set FO3_CLIENT=fo3id
rem 443 taken by another program: hosts "127.0.0.2 APSEODESK172" and
rem set FO3_HTTP_BIND=127.0.0.2
cd /d "%~dp0"
rem a server still running from an earlier play.bat holds the old code: stop it first
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'start_all\.py|http_config\.py|messenger\.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
start "FO3 server" python start_all.py
timeout /t 4 /nobreak >nul
rem RunAsInvoker: start the game without the UAC prompt (it runs fine unelevated)
set __COMPAT_LAYER=RunAsInvoker
start "" "%~dp0launcher\fifalauncher.exe"
