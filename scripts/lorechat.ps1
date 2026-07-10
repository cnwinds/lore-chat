# Lore Chat control script
param(
    [Parameter(Position = 0)]
    [ValidateSet("start", "stop", "restart", "log", "dev", "setup", "help")]
    [string]$Command = "help"
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$Root = Split-Path $PSScriptRoot -Parent
$RunDir = Join-Path $Root ".lorechat"
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$BackendPort = 8000
$FrontendPort = 5173
$BackendLog = Join-Path $RunDir "backend.log"
$FrontendLog = Join-Path $RunDir "frontend.log"
$ModeFile = Join-Path $RunDir "mode"
$PidFile = Join-Path $RunDir "pids.json"
$ComposeFile = Join-Path $Root "docker-compose.yml"

# 后台进程句柄（同一会话内 stop 时可清理）
$script:ProcessHandles = @{}

if ($Command -in @("setup", "dev", "start", "restart")) {
    . (Join-Path $PSScriptRoot "env-setup.ps1")
}

function Ensure-RunDir {
    if (-not (Test-Path $RunDir)) { New-Item -ItemType Directory -Path $RunDir | Out-Null }
}

function Write-Mode([string]$mode) {
    Ensure-RunDir
    Set-Content -Path $ModeFile -Value $mode -Encoding ASCII
}

function Get-Mode {
    if (Test-Path $ModeFile) { return (Get-Content $ModeFile -Raw).Trim() }
    return "none"
}

function Write-PidFile([int]$backendPid, [int]$frontendPid) {
    Ensure-RunDir
    @{ backend = $backendPid; frontend = $frontendPid } | ConvertTo-Json |
        Set-Content -Path $PidFile -Encoding ASCII
}

function Remove-PidFile {
    if (Test-Path $PidFile) { Remove-Item $PidFile -Force -ErrorAction SilentlyContinue }
}

function Stop-ProcessTree([int]$procId) {
    if ($procId -le 0) { return }
    & taskkill.exe /PID $procId /T /F 2>$null | Out-Null
}

function Get-PortListenerPids([int]$port, $netstatLines = $null) {
    $pids = [System.Collections.Generic.List[int]]::new()
    if (-not $netstatLines) { $netstatLines = netstat -ano }
    $lines = $netstatLines | Select-String ":$port\s+.*LISTENING"
    foreach ($m in $lines) {
        $parts = ($m.Line.Trim() -split '\s+')
        $procId = 0
        if (-not [int]::TryParse($parts[-1], [ref]$procId)) { continue }
        if ($procId -gt 0 -and (Get-Process -Id $procId -ErrorAction SilentlyContinue)) {
            $pids.Add($procId) | Out-Null
        }
    }
    return $pids
}

function Test-PortOpen([int]$port, [int]$timeoutMs = 800) {
    $client = $null
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $connect = $client.BeginConnect("127.0.0.1", $port, $null, $null)
        if (-not $connect.AsyncWaitHandle.WaitOne($timeoutMs)) { return $false }
        $client.EndConnect($connect)
        return $true
    } catch {
        return $false
    } finally {
        if ($client) { $client.Close() }
    }
}

function Test-PortAliveListening([int]$port, $netstatLines = $null) {
    if (Test-PortOpen $port 300) { return $true }
    return (Get-PortListenerPids $port $netstatLines).Count -gt 0
}

function Stop-Ports([int[]]$ports) {
    $netstatLines = netstat -ano
    foreach ($port in $ports) {
        foreach ($procId in (Get-PortListenerPids $port $netstatLines)) {
            Stop-ProcessTree $procId
        }
    }
}

function Stop-Port([int]$port) {
    Stop-Ports @($port)
}

function Stop-RelatedProcesses {
    # 兜底：仅清理本项目目录下的 uvicorn / vite 残留
    $rootPattern = [regex]::Escape($Root)
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            ($_.Name -eq 'python.exe' -and $_.CommandLine -match 'uvicorn' -and $_.CommandLine -match $rootPattern) -or
            ($_.Name -eq 'node.exe' -and $_.CommandLine -match 'vite' -and $_.CommandLine -match $rootPattern)
        } |
        ForEach-Object { Stop-ProcessTree $_.ProcessId }
}

function Wait-PortsClosed([int[]]$ports, [int]$timeoutSec = 2) {
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    while ((Get-Date) -lt $deadline) {
        $open = $false
        foreach ($port in $ports) {
            if (Test-PortOpen $port 300) { $open = $true; break }
        }
        if (-not $open) { return $true }
        Start-Sleep -Milliseconds 200
    }
    return $false
}

function Reset-LogFile([string]$path) {
    $errPath = "$path.err"
    foreach ($p in @($path, $errPath)) {
        try {
            if (Test-Path $p) { Remove-Item -LiteralPath $p -Force -ErrorAction Stop }
        } catch { }
        try { New-Item -ItemType File -Path $p -Force | Out-Null } catch { }
    }
}

function Start-LoggedProcess([string]$exe, [string[]]$procArgs, [string]$wd, [string]$log) {
    if (-not (Test-Path $wd)) { throw "工作目录不存在: $wd" }
    if (-not $procArgs -or $procArgs.Count -eq 0) { throw "启动参数为空: $exe" }
    if (-not (Test-Path $exe)) { throw "可执行文件不存在: $exe" }
    Ensure-RunDir

    $errLog = "$log.err"
    Reset-LogFile $log

    # uvicorn 使用 uvicorn_log.json 避免 DefaultFormatter 在重定向 stdout 时崩溃
    $process = Start-Process -FilePath $exe `
        -ArgumentList $procArgs `
        -WorkingDirectory $wd `
        -WindowStyle Hidden `
        -PassThru `
        -RedirectStandardOutput $log `
        -RedirectStandardError $errLog

    $script:ProcessHandles[$process.Id] = $process
    return $process
}

function Test-PortListening([int]$port, [int]$timeoutSec = 20) {
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-PortOpen $port) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Show-LogTail([string]$logPath, [int]$lines = 15) {
    foreach ($p in @($logPath, "$logPath.err")) {
        if (Test-Path $p) {
            Write-Host "--- $p (最近 $lines 行) ---" -ForegroundColor DarkGray
            Get-Content $p -Tail $lines -Encoding UTF8 -ErrorAction SilentlyContinue
        }
    }
}

function Stop-Dev {
    if (Test-Path $PidFile) {
        try {
            $saved = Get-Content $PidFile -Raw | ConvertFrom-Json
            foreach ($procId in @([int]$saved.backend, [int]$saved.frontend)) {
                if ($procId -gt 0) { Stop-ProcessTree $procId }
            }
        } catch { }
    }

    foreach ($p in $script:ProcessHandles.Values) {
        try { if (-not $p.HasExited) { Stop-ProcessTree $p.Id } } catch { }
    }
    $script:ProcessHandles = @{}

    Stop-Ports @($BackendPort, $FrontendPort)

    if (-not (Wait-PortsClosed @($BackendPort, $FrontendPort) 2)) {
        Stop-RelatedProcesses
        Stop-Ports @($BackendPort, $FrontendPort)
        Wait-PortsClosed @($BackendPort, $FrontendPort) 1 | Out-Null
    }

    Remove-PidFile
    if (Test-Path $ModeFile) { Remove-Item $ModeFile -Force }
}

function Stop-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { return }
    if (Test-Path $ComposeFile) {
        Push-Location $Root
        docker compose -f $ComposeFile down 2>$null
        Pop-Location
    }
    if (Test-Path $ModeFile) { Remove-Item $ModeFile -Force }
}

function Get-WebPort {
    $envFile = Join-Path $Root ".env"
    if (Test-Path $envFile) {
        $line = Get-Content $envFile | Where-Object { $_ -match '^\s*WEB_PORT\s*=' } | Select-Object -First 1
        if ($line -match '=\s*(\d+)') { return $Matches[1] }
    }
    return "8080"
}

function Start-Dev {
    Stop-Docker
    Stop-Dev
    Ensure-RunDir

    Setup-DevEnvironment $Root

    $toolsDir = Join-Path $RunDir "tools"
    $npm = Ensure-Node $toolsDir
    $npmDir = Split-Path $npm -Parent
    $env:Path = "$npmDir;$env:Path"

    $venvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
    $nodeExe = Join-Path (Split-Path $npm -Parent) "node.exe"
    $viteJs = Join-Path $FrontendDir "node_modules\vite\bin\vite.js"

    if (-not (Test-Path $viteJs)) {
        Write-Err "未找到 Vite，请先运行: lorechat.bat setup"
        exit 1
    }

    # 日志在 Start-LoggedProcess 内重置（子进程直接写入，避免文件锁）
    Write-Host ""
    Write-Host "[Lore Chat] 启动开发模式 (热更新)..." -ForegroundColor Green
    Write-Host "  后端: http://localhost:$BackendPort  (uvicorn --reload)"
    Write-Host "  前端: http://localhost:$FrontendPort  (Vite HMR)"
    Write-Host "  日志: lorechat.bat log"
    Write-Host ""

    $backendProc = Start-LoggedProcess -exe $venvPython -procArgs @(
        "-m", "uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "$BackendPort",
        "--log-config", "uvicorn_log.json"
    ) -wd $BackendDir -log $BackendLog

    # 直接用 node 启动 vite，避免 npm.cmd 参数在 PowerShell 中被误解析
    $frontendProc = Start-LoggedProcess -exe $nodeExe -procArgs @(
        $viteJs, "--host", "0.0.0.0", "--port", "$FrontendPort"
    ) -wd $FrontendDir -log $FrontendLog

    Write-PidFile $backendProc.Id $frontendProc.Id
    Write-Mode "dev"

    $backendOk = Test-PortListening $BackendPort 25
    $frontendOk = Test-PortListening $FrontendPort 25

    if ($backendOk -and $frontendOk) {
        Write-Host "[Lore Chat] 开发环境已启动。浏览器打开 http://localhost:$FrontendPort" -ForegroundColor Green
        exit 0
    }

    Write-Err "服务启动失败或未能在预期时间内就绪"
    if (-not $backendOk) {
        Write-Host "  后端端口 $BackendPort 未监听" -ForegroundColor Red
        Show-LogTail $BackendLog
        if (-not (Get-Content $BackendLog -ErrorAction SilentlyContinue) -and -not (Get-Content "$BackendLog.err" -ErrorAction SilentlyContinue)) {
            Write-Host "  (后端日志为空，请检查 backend\.venv 是否存在)" -ForegroundColor Yellow
        }
    }
    if (-not $frontendOk) {
        Write-Host "  前端端口 $FrontendPort 未监听" -ForegroundColor Red
        Show-LogTail $FrontendLog
    }
    exit 1
}

function Start-Prod {
    Setup-DockerEnvironment $Root
    Stop-Dev

    Write-Host "[Lore Chat] 正在构建并启动生产环境 (Docker)..." -ForegroundColor Green
    Push-Location $Root
    docker compose -f $ComposeFile up -d --build
    $code = $LASTEXITCODE
    Pop-Location

    if ($code -ne 0) {
        Write-Err "Docker 启动失败"
        exit 1
    }

    Write-Mode "docker"
    $webPort = Get-WebPort
    Write-Host ""
    Write-Host "[Lore Chat] 生产环境已启动" -ForegroundColor Green
    Write-Host "  访问地址: http://localhost:$webPort"
    Write-Host "  查看日志: .\lorechat.bat log"
    Write-Host ""
}

function Show-DevLogs([int]$tailLines = 50) {
    Ensure-RunDir
    $sources = @(
        @{ Path = $BackendLog; Label = "backend" },
        @{ Path = "$BackendLog.err"; Label = "backend.err" },
        @{ Path = $FrontendLog; Label = "frontend" },
        @{ Path = "$FrontendLog.err"; Label = "frontend.err" }
    )

    Write-Host "[Lore Chat] 开发日志 (Ctrl+C 退出)..." -ForegroundColor Cyan

    $positions = @{}
    $anyContent = $false
    foreach ($src in $sources) {
        if (-not (Test-Path $src.Path)) { continue }
        $lines = Get-Content $src.Path -Tail $tailLines -Encoding UTF8 -ErrorAction SilentlyContinue
        if ($lines) {
            $anyContent = $true
            Write-Host "--- $($src.Label) ---" -ForegroundColor DarkGray
            $lines | Write-Host
        }
        $positions[$src.Path] = (Get-Item $src.Path).Length
    }
    if (-not $anyContent) {
        Write-Host "(暂无日志，服务可能未启动或刚重置过日志文件)" -ForegroundColor Yellow
    }

    # Get-Content -Wait 多文件在 Windows PS 5.1 下常不显示已有内容，改用轮询
    while ($true) {
        Start-Sleep -Milliseconds 400
        foreach ($src in $sources) {
            if (-not (Test-Path $src.Path)) { continue }
            $path = $src.Path
            $start = $positions[$path]
            $file = Get-Item $path
            if ($file.Length -le $start) { continue }

            $stream = [System.IO.File]::Open(
                $path,
                [System.IO.FileMode]::Open,
                [System.IO.FileAccess]::Read,
                [System.IO.FileShare]::ReadWrite)
            try {
                $stream.Position = $start
                $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8, $true)
                while ($null -ne ($line = $reader.ReadLine())) {
                    Write-Host "[$($src.Label)] $line"
                }
                $positions[$path] = $stream.Position
            } finally {
                $stream.Close()
            }
        }
    }
}

function Show-Log {
    $mode = Get-Mode
    if ($mode -eq "docker") {
        Write-Host "[Lore Chat] Docker 日志 (Ctrl+C 退出)..." -ForegroundColor Cyan
        Push-Location $Root
        docker compose -f $ComposeFile logs -f --tail 100
        Pop-Location
        return
    }
    if ($mode -eq "dev") {
        Show-DevLogs
        return
    }
    Write-Host "[提示] 服务未运行。先执行 .\lorechat.bat start 或 .\lorechat.bat dev" -ForegroundColor Yellow
    exit 1
}

function Show-Help {
    Write-Host ""
    Write-Host "Lore Chat 控制命令" -ForegroundColor White
    Write-Host ""
    Write-Host "  lorechat.bat setup    检测并自动安装运行环境"
    Write-Host "  lorechat.bat dev      开发模式 (热更新)"
    Write-Host "  lorechat.bat start    生产模式 (Docker)"
    Write-Host "  lorechat.bat stop     停止服务"
    Write-Host "  lorechat.bat restart  重启服务"
    Write-Host "  lorechat.bat log      查看日志"
    Write-Host ""
    Write-Host "  (请使用 lorechat.bat，避免 PowerShell 执行策略限制)"
}

switch ($Command) {
    "setup" { Setup-DevEnvironment $Root }
    "dev" { Start-Dev }
    "start" { Start-Prod }
    "stop" {
        $mode = Get-Mode
        if ($mode -eq "dev") { Stop-Dev; Write-Host "[Lore Chat] 开发服务已停止" -ForegroundColor Green }
        elseif ($mode -eq "docker") { Stop-Docker; Write-Host "[Lore Chat] Docker 服务已停止" -ForegroundColor Green }
        else {
            Stop-Dev
            if (Get-Command docker -ErrorAction SilentlyContinue) { Stop-Docker }
            Write-Host "[Lore Chat] 已尝试停止所有服务" -ForegroundColor Green
        }
    }
    "restart" {
        $mode = Get-Mode
        if ($mode -eq "dev") { Stop-Dev; Start-Dev }
        elseif ($mode -eq "docker") { Stop-Docker; Start-Prod }
        else { Stop-Dev; Stop-Docker; Start-Prod }
    }
    "log" { Show-Log }
    default { Show-Help; exit 1 }
}
