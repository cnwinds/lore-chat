@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "RUNTIME=%ROOT%\.lorechat"
set "BACKEND_DIR=%ROOT%\backend"
set "FRONTEND_DIR=%ROOT%\frontend"
set "BACKEND_LOG=%RUNTIME%\backend.log"
set "FRONTEND_LOG=%RUNTIME%\frontend.log"
set "PID_FILE=%RUNTIME%\pids.json"
set "STOP_PID_FILE=%RUNTIME%\.lorechat_stop_pids.tmp"
set "MODE_FILE=%RUNTIME%\mode.txt"

if not defined LORECHAT_BACKEND_PORT set "LORECHAT_BACKEND_PORT=8000"
if not defined LORECHAT_FRONTEND_PORT set "LORECHAT_FRONTEND_PORT=5173"
if not defined LORECHAT_WEB_PORT set "LORECHAT_WEB_PORT=8080"

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

:do_dev
cd /d "%ROOT%"
if not exist "%RUNTIME%" mkdir "%RUNTIME%"
call :resolve_node_tooling
if errorlevel 1 exit /b 1
if not exist "%FRONTEND_DIR%\node_modules" (
    echo Frontend node_modules missing. Run: lorechat.bat setup
    exit /b 1
)
if not exist "%PYTHON%" (
    echo Backend venv missing. Run: lorechat.bat setup
    exit /b 1
)
call :check_dev_ports_busy
if not errorlevel 1 (
    echo Dev stack already running or ports %LORECHAT_BACKEND_PORT%/%LORECHAT_FRONTEND_PORT% occupied. Use: lorechat.bat stop
    exit /b 1
)
call :reset_log "%BACKEND_LOG%"
call :reset_log "%FRONTEND_LOG%"
echo.
echo [Lore Chat] Starting dev stack (hot reload)
echo   Backend  http://127.0.0.1:%LORECHAT_BACKEND_PORT%   uvicorn --reload
echo   Frontend http://127.0.0.1:%LORECHAT_FRONTEND_PORT%   Vite HMR
echo   Logs     lorechat.bat log
echo.
start "" /b cmd /c "cd /d "%BACKEND_DIR%" && "%PYTHON%" -m uvicorn app.main:app --reload --host 0.0.0.0 --port %LORECHAT_BACKEND_PORT% --log-config uvicorn_log.json >> "%BACKEND_LOG%" 2>>&1"
set "VITE=%FRONTEND_DIR%\node_modules\vite\bin\vite.js"
start "" /b cmd /c "cd /d "%FRONTEND_DIR%" && "%NODE_CMD%" "%VITE%" --host 0.0.0.0 --port %LORECHAT_FRONTEND_PORT% >> "%FRONTEND_LOG%" 2>>&1"
powershell -NoProfile -Command "Start-Sleep -Seconds 2" >nul 2>&1
call :save_dev_pids
call :wait_dev_ready
if errorlevel 1 (
    echo [Lore Chat] Startup failed. Run: lorechat.bat log
    call :do_stop_dev
    exit /b 1
)
echo dev> "%MODE_FILE%"
echo [Lore Chat] Ready -^> http://127.0.0.1:%LORECHAT_FRONTEND_PORT%
for /f "usebackq tokens=*" %%i in (`powershell -NoProfile -Command "Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown' } | Select-Object -First 1 -ExpandProperty IPAddress" 2^>nul`) do set "LAN_IP=%%i"
if defined LAN_IP echo [Lore Chat] LAN     -^> http://!LAN_IP!:%LORECHAT_FRONTEND_PORT%
exit /b 0

:do_start
cd /d "%ROOT%"
if not exist "%RUNTIME%" mkdir "%RUNTIME%"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.Encoding]::UTF8;" ^
  ". '%ROOT%\scripts\env-setup.ps1'; Setup-DockerEnvironment '%ROOT%'"
if errorlevel 1 exit /b 1
where docker >nul 2>&1
if errorlevel 1 (
    echo Error: Docker not found. Install Docker Desktop or use: lorechat.bat dev
    exit /b 1
)
docker compose ps --status running 2>nul | findstr /I /C:"lorechat-web" /C:"lorechat-backend" >nul 2>&1
if not errorlevel 1 (
    echo Docker stack already running. Use: lorechat.bat stop
    exit /b 1
)
echo.
echo [Lore Chat] Starting production stack (Docker) ...
docker compose up -d --build
if errorlevel 1 (
    echo Error: docker compose up failed.
    exit /b 1
)
echo docker> "%MODE_FILE%"
echo [Lore Chat] Production ready -^> http://127.0.0.1:%LORECHAT_WEB_PORT%
for /f "usebackq tokens=*" %%i in (`powershell -NoProfile -Command "Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown' } | Select-Object -First 1 -ExpandProperty IPAddress" 2^>nul`) do set "LAN_IP=%%i"
if defined LAN_IP echo [Lore Chat] LAN          -^> http://!LAN_IP!:%LORECHAT_WEB_PORT%
echo Logs: docker compose logs -f
exit /b 0

:do_stop
cd /d "%ROOT%"
call :is_docker_running
if not errorlevel 1 goto :do_stop_docker
call :check_dev_ports_busy
if errorlevel 1 goto :stop_not_running
goto :do_stop_dev

:do_stop_docker
echo Stopping Docker stack ...
docker compose down
if errorlevel 1 exit /b 1
del /f "%MODE_FILE%" >nul 2>&1
echo [Lore Chat] Docker stack stopped.
exit /b 0

:do_stop_dev
call :collect_dev_pids
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
        call :kill_listeners_on_port %LORECHAT_BACKEND_PORT%
        call :kill_listeners_on_port %LORECHAT_FRONTEND_PORT%
        powershell -NoProfile -Command "Start-Sleep -Seconds 1" >nul 2>&1
    )
)
del /f "%PID_FILE%" >nul 2>&1
del /f "%MODE_FILE%" >nul 2>&1
if not "!STOPPED!"=="" (
    call :collect_dev_pids
    set "LEFTOVER="
    if exist "%STOP_PID_FILE%" (
        for /f "usebackq tokens=*" %%p in ("%STOP_PID_FILE%") do (
            if not "%%p"=="" set "LEFTOVER=!LEFTOVER! %%p"
        )
        del /f "%STOP_PID_FILE%" >nul 2>&1
    )
    if not "!LEFTOVER!"=="" (
        echo Stop attempted [PIDs!STOPPED!], but process still present [PIDs!LEFTOVER!]
        exit /b 2
    )
    echo [Lore Chat] Dev stack stopped [PIDs!STOPPED!]
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
set "RESTART_MODE=dev"
if exist "%MODE_FILE%" (
    set /p RESTART_MODE=<"%MODE_FILE%"
)
call :do_stop
powershell -NoProfile -Command "Start-Sleep -Seconds 1" >nul 2>&1
if /i "!RESTART_MODE!"=="docker" (
    call :do_start
) else (
    call :do_dev
)
exit /b %ERRORLEVEL%

:do_log
cd /d "%ROOT%"
if not exist "%RUNTIME%" (
    echo No logs yet. Run: lorechat.bat dev
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='SilentlyContinue'; [Console]::OutputEncoding=[Text.Encoding]::UTF8;" ^
  "$sources=@(@{Path='%BACKEND_LOG%';Tag='backend'},@{Path='%BACKEND_LOG%.err';Tag='backend.err'}," ^
  "@{Path='%FRONTEND_LOG%';Tag='frontend'},@{Path='%FRONTEND_LOG%.err';Tag='frontend.err'});" ^
  "Write-Host '[Lore Chat] Log tail (Ctrl+C to exit)' -ForegroundColor Cyan;" ^
  "$offset=@{}; foreach($s in $sources){ if(-not(Test-Path $s.Path)){continue}; $lines=Get-Content $s.Path -Tail 40 -Encoding UTF8 -ErrorAction SilentlyContinue; if($lines){ Write-Host ('--- '+$s.Tag+' ---') -ForegroundColor DarkGray; $lines }; $offset[$s.Path]=(Get-Item $s.Path).Length };" ^
  "while($true){ Start-Sleep -Milliseconds 400; foreach($s in $sources){ if(-not(Test-Path $s.Path)){continue}; $path=$s.Path; $file=Get-Item $path; if($file.Length -le $offset[$path]){continue};" ^
  "$stream=[IO.File]::Open($path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite); try{ $stream.Position=$offset[$path]; $reader=[IO.StreamReader]::new($stream,[Text.Encoding]::UTF8,$true);" ^
  "while($null -ne ($line=$reader.ReadLine())){ Write-Host ('['+$s.Tag+'] '+$line) }; $offset[$path]=$stream.Position } finally { $stream.Close() } } }"
exit /b %ERRORLEVEL%

:reset_log
if not exist "%RUNTIME%" mkdir "%RUNTIME%"
if exist "%~1" del /f "%~1" >nul 2>&1
type nul > "%~1"
if exist "%~1.err" del /f "%~1.err" >nul 2>&1
type nul > "%~1.err"
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

:save_dev_pids
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$bp=%LORECHAT_BACKEND_PORT%; $fp=%LORECHAT_FRONTEND_PORT%; $root=(Resolve-Path '%ROOT%').Path;" ^
  "$backend=0; $frontend=0;" ^
  "$b=Get-NetTCPConnection -LocalPort $bp -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess;" ^
  "if($b){$backend=[int]$b};" ^
  "$f=Get-NetTCPConnection -LocalPort $fp -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess;" ^
  "if($f){$frontend=[int]$f};" ^
  "$out=Join-Path $root '.lorechat\pids.json';" ^
  "if($backend -gt 0 -or $frontend -gt 0){ @{backend=$backend;frontend=$frontend} | ConvertTo-Json | Set-Content -Path $out -Encoding ASCII }"
exit /b 0

:wait_dev_ready
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$bp=%LORECHAT_BACKEND_PORT%; $fp=%LORECHAT_FRONTEND_PORT%;" ^
  "function Test-Port([int]$port){ $c=$null; try{ $c=[Net.Sockets.TcpClient]::new(); $a=$c.BeginConnect('127.0.0.1',$port,$null,$null); if(-not $a.AsyncWaitHandle.WaitOne(500)){return $false}; $c.EndConnect($a); return $true } catch { return $false } finally { if($c){$c.Close()} } };" ^
  "$deadline=(Get-Date).AddSeconds(30); $b=$false; $f=$false;" ^
  "while((Get-Date) -lt $deadline){ if(-not $b){$b=Test-Port $bp}; if(-not $f){$f=Test-Port $fp}; if($b -and $f){ exit 0 }; Start-Sleep -Milliseconds 400 }; exit 1"
exit /b %ERRORLEVEL%

:kill_listeners_on_port
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":%~1 .*LISTENING"') do (
    if not "%%p"=="0" (
        taskkill /pid %%p /t /f >nul 2>&1
        set "STOPPED=!STOPPED! %%p"
    )
)
goto :eof

:check_dev_ports_busy
if exist "%PID_FILE%" exit /b 0
netstat -ano | findstr /R /C:":%LORECHAT_BACKEND_PORT% .*LISTENING" /C:":%LORECHAT_FRONTEND_PORT% .*LISTENING" >nul 2>&1 && exit /b 0
exit /b 1

:is_docker_running
where docker >nul 2>&1
if errorlevel 1 exit /b 1
cd /d "%ROOT%"
docker compose ps --status running 2>nul | findstr /I /C:"lorechat-web" /C:"lorechat-backend" >nul 2>&1
exit /b !ERRORLEVEL!

:collect_dev_pids
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = (Resolve-Path '%ROOT%').Path; $runtime = Join-Path $root '.lorechat'; $pidFile = Join-Path $runtime 'pids.json'; $out = Join-Path $runtime '.lorechat_stop_pids.tmp';" ^
  "$roots = New-Object 'System.Collections.Generic.HashSet[int]';" ^
  "if (Test-Path $pidFile) { try { $saved = Get-Content $pidFile -Raw | ConvertFrom-Json; foreach ($k in @('backend','frontend')) { $n = 0; if ([int]::TryParse([string]$saved.$k, [ref]$n) -and $n -gt 0) { [void]$roots.Add($n) } } } catch {} }" ^
  "foreach ($devPort in @(%LORECHAT_BACKEND_PORT%, %LORECHAT_FRONTEND_PORT%)) { Get-NetTCPConnection -LocalPort $devPort -State Listen -ErrorAction SilentlyContinue | ForEach-Object { [void]$roots.Add([int]$_.OwningProcess) } };" ^
  "$escaped = [regex]::Escape($root);" ^
  "Get-CimInstance Win32_Process -Filter \"Name = 'node.exe' OR Name = 'python.exe'\" -ErrorAction SilentlyContinue | Where-Object { $cmd = [string]$_.CommandLine; $cmd -and $cmd -match $escaped -and ($cmd -match 'uvicorn.*app\.main:app' -or $cmd -match 'app\.main:app' -or $cmd -match 'vite\.js' -or $cmd -match '\\vite\\bin\\vite') } | ForEach-Object { [void]$roots.Add([int]$_.ProcessId) };" ^
  "$seen = New-Object 'System.Collections.Generic.HashSet[int]'; $queue = New-Object System.Collections.Queue;" ^
  "foreach ($r in $roots) { if ($r -gt 0 -and $r -ne $PID -and $seen.Add($r)) { $queue.Enqueue($r) } };" ^
  "while ($queue.Count -gt 0) { $cur = [int]$queue.Dequeue(); Get-CimInstance Win32_Process -Filter \"ParentProcessId = $cur\" -ErrorAction SilentlyContinue | ForEach-Object { $child = [int]$_.ProcessId; if ($child -gt 0 -and $child -ne $PID -and $seen.Add($child)) { $queue.Enqueue($child) } } };" ^
  "$lines = @($seen | Sort-Object | ForEach-Object { [string]$_ }); [System.IO.File]::WriteAllLines($out, $lines, [System.Text.Encoding]::ASCII)"
goto :eof

:usage
echo.
echo Lore Chat
echo.
echo   lorechat.bat setup    Detect / install Python, Node, dependencies
echo   lorechat.bat dev      Dev mode: uvicorn --reload :%LORECHAT_BACKEND_PORT% + Vite :%LORECHAT_FRONTEND_PORT%
echo   lorechat.bat start    Production: Docker Compose on :%LORECHAT_WEB_PORT%
echo   lorechat.bat stop     Stop dev stack or Docker
echo   lorechat.bat restart  Restart last mode (dev or docker)
echo   lorechat.bat log      Tail dev logs
echo.
echo Env: LORECHAT_BACKEND_PORT, LORECHAT_FRONTEND_PORT, LORECHAT_WEB_PORT
echo.
exit /b 1
