@echo off
rem One click: start the private server (own window; close it to stop the server)
rem and then the game. Needs Python + cryptography and, once, the hosts entry
rem "127.0.0.1 APSEODESK172" (as administrator). Everything else comes from prepare.py:
rem it finds this PC's client (3Sea or FO3 ID, any folder), extracts gamedata\fifadb.sqlite,
rem makes certs\server.pem and builds launcher\fifalauncher.exe when they are missing.
rem Another client folder: python fo3conf.py set "<client folder>"   (kept in fo3.local.env)
rem 443 taken by another program: hosts "127.0.0.2 APSEODESK172" and
rem set FO3_HTTP_BIND=127.0.0.2
cd /d "%~dp0"
rem a server still running from an earlier play.bat holds the old code: stop it first
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'start_all\.py|http_config\.py|messenger\.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
call python prepare.py > "%TEMP%\fo3_prepare.env" || (echo. & echo Fix what is listed above, then run play.bat again. & pause & exit /b 1)
for /f "usebackq tokens=1,* delims==" %%a in ("%TEMP%\fo3_prepare.env") do set "%%a=%%b"
start "FO3 server" python start_all.py
timeout /t 4 /nobreak >nul
rem RunAsInvoker: start the game without the UAC prompt (it runs fine unelevated)
set __COMPAT_LAYER=RunAsInvoker
start "" "%~dp0launcher\fifalauncher.exe"
