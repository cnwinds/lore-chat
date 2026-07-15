@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "RUNTIME=%ROOT%\.lorechat"
set "BACKEND_DIR=%ROOT%\backend"
set "FRONTEND_DIR=%ROOT%\frontend"
set "LOG=%RUNTIME%\web.log"
set "PID_FILE=%RUNTIME%\web.pid"
set "STOP_PID_FILE=%RUNTIME%\.lorechat_stop_pids.tmp"
set "MODE_FILE=%RUNTIME%\mode.txt"

if not defined LORECHAT_WEB_HOST set "LORECHAT_WEB_HOST=0.0.0.0"
if not defined LORECHAT_WEB_PORT set "LORECHAT_WEB_PORT=8080"
if not defined LORECHAT_BACKEND_PORT set "LORECHAT_BACKEND_PORT=8000"
if not defined LORECHAT_FRONTEND_PORT set "LORECHAT_FRONTEND_PORT=5173"

if exist "%BACKEND_DIR%\.venv\Scripts\python.exe" (
    set "PYTHON=%BACKEND_DIR%\.venv\Scripts\python.exe"
) else (
    set "PYTHON=%BACKEND_DIR%\.venv\bin\python"
)

if "%~1"=="" goto :usage
if /i "%~1"=="setup"   goto :do_setup
if /i "%~1"=="start"   goto :do_start
if /i "%~1"=="dev"     goto :do_dev
if /i "%~1"=="stop"    goto :do_stop
if /i "%~1"=="restart" goto :do_restart
if /i "%~1"=="log"     goto :do_log
if /i "%~1"=="logs"    goto :do_log
if /i "%~1"=="help"    goto :usage
goto :usage

:do_setup
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.Encoding]::UTF8;" ^
  ". '%ROOT%\scripts\env-setup.ps1'; Setup-DevEnvironment '%ROOT%'"
exit /b %ERRORLEVEL%

:do_start
cd /d "%ROOT%"
if not exist "%RUNTIME%" mkdir "%RUNTIME%"
if not exist "%PYTHON%" (
    echo Backend venv missing. Run: lorechat.bat setup
    exit /b 1
)
call :check_ports_busy
if not errorlevel 1 (
    echo Already running or port occupied. Use: lorechat.bat stop
    exit /b 1
)
call :ensure_frontend_build
if errorlevel 1 exit /b 1
echo.
echo [Lore Chat] Starting production server on %LORECHAT_WEB_HOST%:%LORECHAT_WEB_PORT% ...
cd /d "%BACKEND_DIR%"
start "" /b "!PYTHON!" -m uvicorn app.prod_app:app --host %LORECHAT_WEB_HOST% --port %LORECHAT_WEB_PORT% >> "%LOG%" 2>&1
powershell -NoProfile -Command "Start-Sleep -Seconds 3" >nul 2>&1
for /f "tokens=*" %%p in ('powershell -NoProfile -Command "$p = Get-NetTCPConnection -LocalPort %LORECHAT_WEB_PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess; if ($p) { [string][int]$p }" 2^>nul') do (
    if not "%%p"=="" (
        echo %%p> "%PID_FILE%"
        echo start> "%MODE_FILE%"
        for /f "usebackq tokens=*" %%i in (`powershell -NoProfile -Command "Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown' } | Select-Object -First 1 -ExpandProperty IPAddress" 2^>nul`) do set "LAN_IP=%%i"
        echo [Lore Chat] Ready -^> http://127.0.0.1:%LORECHAT_WEB_PORT%
        if defined LAN_IP echo [Lore Chat] LAN     -^> http://!LAN_IP!:%LORECHAT_WEB_PORT%
        echo [Lore Chat] Log      -^> lorechat.bat log
        goto :eof
    )
)
echo [Lore Chat] Started on %LORECHAT_WEB_HOST%:%LORECHAT_WEB_PORT%. Log: %LOG%
echo start> "%MODE_FILE%"
goto :eof

:do_dev
cd /d "%ROOT%"
if not exist "%RUNTIME%" mkdir "%RUNTIME%"
if not exist "%PYTHON%" (
    echo Backend venv missing. Run: lorechat.bat setup
    exit /b 1
)
call :resolve_node_tooling
if errorlevel 1 exit /b 1
if not exist "%FRONTEND_DIR%\node_modules" (
    echo Frontend node_modules missing. Run: lorechat.bat setup
    exit /b 1
)
call :check_ports_busy
if not errorlevel 1 (
    echo Already running or port occupied. Use: lorechat.bat stop
    exit /b 1
)
echo dev> "%MODE_FILE%"
cd /d "%FRONTEND_DIR%"
"!NODE_CMD!" scripts\dev.mjs
set "DEV_EXIT=!ERRORLEVEL!"
echo.
echo [Lore Chat] Dev stack stopped.
call :do_stop
exit /b !DEV_EXIT!

:do_stop
cd /d "%ROOT%"
call :check_ports_busy
if errorlevel 1 goto :stop_not_running
call :collect_pids
set "STOPPED="
if exist "%STOP_PID_FILE%" (
    for /f "usebackq tokens=*" %%p in ("%STOP_PID_FILE%") do (
        if not "%%p"=="" (
            for /f "tokens=* delims= " %%q in ("%%p") do (
                taskkill /pid %%q /t /f >nul 2>&1
                set "STOPPED=!STOPPED! %%q"
            )
        )
    )
    del /f "%STOP_PID_FILE%" >nul 2>&1
)
if not "!STOPPED!"=="" (
    for /l %%r in (1,1,5) do (
        call :kill_listeners_on_port %LORECHAT_WEB_PORT%
        call :kill_listeners_on_port %LORECHAT_BACKEND_PORT%
        call :kill_listeners_on_port %LORECHAT_FRONTEND_PORT%
        powershell -NoProfile -Command "Start-Sleep -Seconds 1" >nul 2>&1
    )
)
del /f "%PID_FILE%" >nul 2>&1
del /f "%MODE_FILE%" >nul 2>&1
if not "!STOPPED!"=="" (
    echo [Lore Chat] Stopped [PIDs!STOPPED!]
) else (
    echo [Lore Chat] Not running [no matching process or port listener]
)
exit /b 0

:stop_not_running
del /f "%PID_FILE%" >nul 2>&1
del /f "%STOP_PID_FILE%" >nul 2>&1
del /f "%MODE_FILE%" >nul 2>&1
echo [Lore Chat] Not running [no matching process or port listener]
exit /b 0

:do_restart
cd /d "%ROOT%"
set "RESTART_MODE=start"
if exist "%MODE_FILE%" (
    set /p RESTART_MODE=<"%MODE_FILE%"
)
call :do_stop
powershell -NoProfile -Command "Start-Sleep -Seconds 1" >nul 2>&1
if /i "!RESTART_MODE!"=="dev" (
    call :do_dev
) else (
    call :do_start
)
exit /b %ERRORLEVEL%

:do_log
cd /d "%ROOT%"
if not exist "%LOG%" (
    echo No log file: %LOG%
    echo Run: lorechat.bat start
    exit /b 1
)
powershell -command "Get-Content '%LOG%' -Wait -Tail 50"
exit /b %ERRORLEVEL%

:ensure_frontend_build
call :resolve_node_tooling
if errorlevel 1 exit /b 1
set "BUILD_NEEDED=0"
if not exist "%FRONTEND_DIR%\node_modules" (
    echo Frontend node_modules missing. Running npm install ...
    pushd "%FRONTEND_DIR%"
    call "!NPM_CMD!" install
    if errorlevel 1 (
        echo Error: npm install failed.
        popd
        exit /b 1
    )
    popd
    set "BUILD_NEEDED=1"
)
if "!BUILD_NEEDED!"=="0" if not exist "%FRONTEND_DIR%\dist\index.html" (
    set "BUILD_NEEDED=1"
) else if "!BUILD_NEEDED!"=="0" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "$root = (Resolve-Path '%ROOT%').Path; $dist = Join-Path $root 'frontend\dist\index.html';" ^
      "$distTime = (Get-Item $dist).LastWriteTimeUtc;" ^
      "$paths = @('frontend\src', 'frontend\index.html', 'frontend\vite.config.ts', 'frontend\tsconfig.json', 'frontend\tsconfig.app.json', 'frontend\tsconfig.node.json', 'frontend\package.json', 'frontend\package-lock.json');" ^
      "foreach ($rel in $paths) { $p = Join-Path $root $rel; if (-not (Test-Path $p)) { continue }; $items = if ((Get-Item -LiteralPath $p).PSIsContainer) { Get-ChildItem -LiteralPath $p -Recurse -File -ErrorAction SilentlyContinue } else { @(Get-Item -LiteralPath $p) }; foreach ($f in $items) { if ($f.LastWriteTimeUtc -gt $distTime) { exit 2 } } };" ^
      "exit 0"
    if errorlevel 2 set "BUILD_NEEDED=1"
)
if "!BUILD_NEEDED!"=="1" (
    echo Frontend build required. Running npm run build ...
    pushd "%FRONTEND_DIR%"
    call "!NPM_CMD!" run build
    set "BUILD_EXIT=!ERRORLEVEL!"
    popd
    if not "!BUILD_EXIT!"=="0" (
        echo Error: npm run build failed.
        exit /b 1
    )
    echo Frontend build completed.
) else (
    echo Frontend build up to date.
)
exit /b 0

:resolve_node_tooling
set "NPM_CMD="
set "NODE_CMD=node"
for /f "delims=" %%I in ('where npm.cmd 2^>nul') do (
    if not defined NPM_CMD set "NPM_CMD=%%I"
)
if defined NPM_CMD goto :resolve_node_tooling_done
set "PORTABLE_NODE=%RUNTIME%\tools\node"
if exist "%PORTABLE_NODE%\npm.cmd" (
    set "NPM_CMD=%PORTABLE_NODE%\npm.cmd"
    set "NODE_CMD=%PORTABLE_NODE%\node.exe"
    set "PATH=%PORTABLE_NODE%;%PATH%"
    goto :resolve_node_tooling_done
)
echo Error: npm not found. Run: lorechat.bat setup
exit /b 1
:resolve_node_tooling_done
exit /b 0

:kill_listeners_on_port
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":%~1 .*LISTENING"') do (
    if not "%%p"=="0" (
        taskkill /pid %%p /t /f >nul 2>&1
        set "STOPPED=!STOPPED! %%p"
    )
)
goto :eof

:check_ports_busy
if exist "%PID_FILE%" exit /b 0
netstat -ano | findstr /R /C:":%LORECHAT_WEB_PORT% .*LISTENING" /C:":%LORECHAT_BACKEND_PORT% .*LISTENING" /C:":%LORECHAT_FRONTEND_PORT% .*LISTENING" >nul 2>&1 && exit /b 0
exit /b 1

:collect_pids
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = (Resolve-Path '%ROOT%').Path; $runtime = Join-Path $root '.lorechat'; $pidFile = Join-Path $runtime 'web.pid'; $out = Join-Path $runtime '.lorechat_stop_pids.tmp';" ^
  "$roots = New-Object 'System.Collections.Generic.HashSet[int]';" ^
  "if (Test-Path $pidFile) { $raw = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1); $n = 0; if ([int]::TryParse([string]$raw, [ref]$n) -and $n -gt 0) { [void]$roots.Add($n) } }" ^
  "foreach ($port in @(%LORECHAT_WEB_PORT%, %LORECHAT_BACKEND_PORT%, %LORECHAT_FRONTEND_PORT%)) { Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | ForEach-Object { [void]$roots.Add([int]$_.OwningProcess) } };" ^
  "$escaped = [regex]::Escape($root);" ^
  "Get-CimInstance Win32_Process -Filter \"Name = 'node.exe' OR Name = 'python.exe'\" -ErrorAction SilentlyContinue | Where-Object { $cmd = [string]$_.CommandLine; $cmd -and $cmd -match $escaped -and ($cmd -match 'uvicorn.*app\.prod_app:app' -or $cmd -match 'app\.prod_app:app' -or $cmd -match 'dev_server\.py' -or $cmd -match 'app\.main:app' -or $cmd -match 'scripts[\\/]dev\.mjs' -or $cmd -match 'vite\.js' -or $cmd -match '\\vite\\bin\\vite') } | ForEach-Object { [void]$roots.Add([int]$_.ProcessId) };" ^
  "$seen = New-Object 'System.Collections.Generic.HashSet[int]'; $queue = New-Object System.Collections.Queue;" ^
  "foreach ($r in $roots) { if ($r -gt 0 -and $r -ne $PID -and $seen.Add($r)) { $queue.Enqueue($r) } };" ^
  "while ($queue.Count -gt 0) { $cur = [int]$queue.Dequeue(); Get-CimInstance Win32_Process -Filter \"ParentProcessId = $cur\" -ErrorAction SilentlyContinue | ForEach-Object { $child = [int]$_.ProcessId; if ($child -gt 0 -and $child -ne $PID -and $seen.Add($child)) { $queue.Enqueue($child) } } };" ^
  "$lines = @($seen | Sort-Object | ForEach-Object { [string]$_ }); [System.IO.File]::WriteAllLines($out, $lines, [System.Text.Encoding]::ASCII)"
goto :eof

:usage
echo.
echo Lore Chat
echo.
echo   lorechat.bat setup     Detect / install Python, Node, dependencies
echo   lorechat.bat start     Production: build frontend, serve on :%LORECHAT_WEB_PORT%
echo   lorechat.bat dev       Development: API :%LORECHAT_BACKEND_PORT% + Vite :%LORECHAT_FRONTEND_PORT% (foreground)
echo   lorechat.bat stop      Stop production or dev stack
echo   lorechat.bat restart   Restart last mode (start or dev)
echo   lorechat.bat log       Tail production log
echo.
echo Env: LORECHAT_WEB_HOST, LORECHAT_WEB_PORT, LORECHAT_BACKEND_PORT, LORECHAT_FRONTEND_PORT
echo.
exit /b 1
