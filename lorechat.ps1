# Lore Chat 开发环境启停管理（uvicorn --reload + Vite HMR）
param(
    [Parameter(Position = 0)]
    [ValidateSet("start", "stop", "restart", "log", "setup", "dev", "help")]
    [string]$Command = "help"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# --- paths & ports ---
$Root         = $PSScriptRoot
$RunDir       = Join-Path $Root ".lorechat"
$BackendDir   = Join-Path $Root "backend"
$FrontendDir  = Join-Path $Root "frontend"
$BackendPort  = 8000
$FrontendPort = 5173
$BackendLog   = Join-Path $RunDir "backend.log"
$FrontendLog  = Join-Path $RunDir "frontend.log"
$PidFile      = Join-Path $RunDir "pids.json"
$EnvSetup     = Join-Path $Root "scripts\env-setup.ps1"

# --- output helpers ---
function Write-Info([string]$msg)  { Write-Host $msg -ForegroundColor Cyan }
function Write-Ok([string]$msg)    { Write-Host $msg -ForegroundColor Green }
function Write-Warn([string]$msg)  { Write-Host $msg -ForegroundColor Yellow }
function Write-Err([string]$msg)   { Write-Host $msg -ForegroundColor Red }

# --- runtime state ---
function Ensure-RunDir {
    if (-not (Test-Path $RunDir)) {
        New-Item -ItemType Directory -Path $RunDir | Out-Null
    }
}

function Save-Pids([int]$backendPid, [int]$frontendPid) {
    Ensure-RunDir
    @{ backend = $backendPid; frontend = $frontendPid } | ConvertTo-Json |
        Set-Content -Path $PidFile -Encoding ASCII
}

function Clear-Pids {
    if (Test-Path $PidFile) { Remove-Item $PidFile -Force }
}

function Get-SavedPids {
    if (-not (Test-Path $PidFile)) { return $null }
    try { return Get-Content $PidFile -Raw | ConvertFrom-Json } catch { return $null }
}

# --- process / port utilities ---
function Stop-Tree([int]$procId) {
    if ($procId -gt 0) {
        & taskkill.exe /PID $procId /T /F 2>$null | Out-Null
    }
}

function Get-Listeners([int]$port) {
    $pids = [System.Collections.Generic.List[int]]::new()
    netstat -ano | Select-String ":$port\s+.*LISTENING" | ForEach-Object {
        $parts = ($_.Line.Trim() -split '\s+')
        $id = 0
        if ([int]::TryParse($parts[-1], [ref]$id) -and $id -gt 0) {
            if (Get-Process -Id $id -ErrorAction SilentlyContinue) { $pids.Add($id) }
        }
    }
    return $pids
}

function Test-Port([int]$port, [int]$timeoutMs = 500) {
    $client = $null
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $async = $client.BeginConnect("127.0.0.1", $port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne($timeoutMs)) { return $false }
        $client.EndConnect($async)
        return $true
    } catch {
        return $false
    } finally {
        if ($client) { $client.Close() }
    }
}

function Stop-Port([int]$port) {
    foreach ($id in (Get-Listeners $port)) { Stop-Tree $id }
}

function Stop-ProjectProcesses {
    $pattern = [regex]::Escape($Root)
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            ($_.Name -eq 'python.exe' -and $_.CommandLine -match 'uvicorn' -and $_.CommandLine -match $pattern) -or
            ($_.Name -eq 'node.exe' -and $_.CommandLine -match 'vite' -and $_.CommandLine -match $pattern)
        } |
        ForEach-Object { Stop-Tree $_.ProcessId }
}

function Wait-PortsClosed([int[]]$ports, [int]$seconds = 3) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        $busy = $false
        foreach ($p in $ports) { if (Test-Port $p 200) { $busy = $true; break } }
        if (-not $busy) { return $true }
        Start-Sleep -Milliseconds 200
    }
    return $false
}

function Wait-PortReady([int]$port, [int]$seconds = 30) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Port $port) { return $true }
        Start-Sleep -Milliseconds 400
    }
    return $false
}

function Test-Running {
    return (Test-Port $BackendPort 200) -or (Test-Port $FrontendPort 200)
}

function Reset-Log([string]$path) {
    Ensure-RunDir
    foreach ($p in @($path, "$path.err")) {
        try {
            if (Test-Path $p) {
                [System.IO.File]::WriteAllText($p, "", [System.Text.UTF8Encoding]::new($false))
            } else {
                New-Item -ItemType File -Path $p -Force | Out-Null
            }
        } catch {
            # 文件被占用时跳过，Start-Process 会追加写入
            if (-not (Test-Path $p)) {
                New-Item -ItemType File -Path $p -Force | Out-Null
            }
        }
    }
}

function Start-Background([string]$exe, [string[]]$procArgs, [string]$workDir, [string]$logPath) {
    if (-not (Test-Path $exe)) { throw "找不到可执行文件: $exe" }
    if (-not (Test-Path $workDir)) { throw "工作目录不存在: $workDir" }
    Reset-Log $logPath
    $proc = Start-Process -FilePath $exe `
        -ArgumentList $procArgs `
        -WorkingDirectory $workDir `
        -WindowStyle Hidden `
        -PassThru `
        -RedirectStandardOutput $logPath `
        -RedirectStandardError "$logPath.err"
    return $proc
}

function Show-LogTail([string]$path, [int]$lines = 20) {
    foreach ($p in @($path, "$path.err")) {
        if (-not (Test-Path $p)) { continue }
        Write-Host "--- $p ---" -ForegroundColor DarkGray
        Get-Content $p -Tail $lines -Encoding UTF8 -ErrorAction SilentlyContinue
    }
}

# --- commands ---
function Invoke-Setup {
    if (-not (Test-Path $EnvSetup)) { throw "缺少 scripts\env-setup.ps1" }
    . $EnvSetup
    Setup-DevEnvironment $Root
}

function Stop-Services {
    $saved = Get-SavedPids
    if ($saved) {
        Stop-Tree ([int]$saved.backend)
        Stop-Tree ([int]$saved.frontend)
    }
    Stop-Port $BackendPort
    Stop-Port $FrontendPort
    if (-not (Wait-PortsClosed @($BackendPort, $FrontendPort) 2)) {
        Stop-ProjectProcesses
        Stop-Port $BackendPort
        Stop-Port $FrontendPort
        Wait-PortsClosed @($BackendPort, $FrontendPort) 1 | Out-Null
    }
    Clear-Pids
}

function Invoke-Stop {
    Stop-Services
    Write-Ok "[Lore Chat] 开发服务已停止"
}

function Invoke-Start {
    if (Test-Running) {
        Write-Warn "[Lore Chat] 服务已在运行。如需重启请执行: lorechat.bat restart"
        exit 0
    }

    Stop-Services
    Ensure-RunDir

    if (-not (Test-Path $EnvSetup)) { throw "缺少 scripts\env-setup.ps1" }
    . $EnvSetup
    Setup-DevEnvironment $Root

    $toolsDir = Join-Path $RunDir "tools"
    $npm = Ensure-Node $toolsDir
    $nodeDir = Split-Path $npm -Parent
    $env:Path = "$nodeDir;$env:Path"

    $python = Join-Path $BackendDir ".venv\Scripts\python.exe"
    $node   = Join-Path $nodeDir "node.exe"
    $vite   = Join-Path $FrontendDir "node_modules\vite\bin\vite.js"

    if (-not (Test-Path $python)) {
        Write-Err "后端虚拟环境不存在，请先运行: lorechat.bat setup"
        exit 1
    }
    if (-not (Test-Path $vite)) {
        Write-Err "前端依赖未安装，请先运行: lorechat.bat setup"
        exit 1
    }

    Write-Host ""
    Write-Ok "[Lore Chat] 启动开发环境（热更新）"
    Write-Host "  后端  http://localhost:$BackendPort   uvicorn --reload"
    Write-Host "  前端  http://localhost:$FrontendPort   Vite HMR"
    Write-Host "  日志  lorechat.bat log"
    Write-Host ""

    $backend = Start-Background $python @(
        "-m", "uvicorn", "app.main:app",
        "--reload", "--host", "0.0.0.0", "--port", "$BackendPort",
        "--log-config", "uvicorn_log.json"
    ) $BackendDir $BackendLog

    $frontend = Start-Background $node @(
        $vite, "--host", "0.0.0.0", "--port", "$FrontendPort"
    ) $FrontendDir $FrontendLog

    Save-Pids $backend.Id $frontend.Id

    $backendOk  = Wait-PortReady $BackendPort
    $frontendOk = Wait-PortReady $FrontendPort

    if ($backendOk -and $frontendOk) {
        Write-Ok "[Lore Chat] 已就绪 → http://localhost:$FrontendPort"
        exit 0
    }

    Write-Err "[Lore Chat] 启动失败"
    if (-not $backendOk) {
        Write-Host "  后端端口 $BackendPort 未就绪" -ForegroundColor Red
        Show-LogTail $BackendLog
    }
    if (-not $frontendOk) {
        Write-Host "  前端端口 $FrontendPort 未就绪" -ForegroundColor Red
        Show-LogTail $FrontendLog
    }
    Stop-Services
    exit 1
}

function Invoke-Log {
    if (-not (Test-Path $RunDir)) {
        Write-Warn "暂无日志。请先执行 lorechat.bat start"
        exit 1
    }

    $sources = @(
        @{ Path = $BackendLog;  Tag = "backend" },
        @{ Path = "$BackendLog.err"; Tag = "backend.err" },
        @{ Path = $FrontendLog; Tag = "frontend" },
        @{ Path = "$FrontendLog.err"; Tag = "frontend.err" }
    )

    Write-Info "[Lore Chat] 日志跟踪（Ctrl+C 退出）"
    $offset = @{}

    foreach ($src in $sources) {
        if (-not (Test-Path $src.Path)) { continue }
        $lines = Get-Content $src.Path -Tail 40 -Encoding UTF8 -ErrorAction SilentlyContinue
        if ($lines) {
            Write-Host "--- $($src.Tag) ---" -ForegroundColor DarkGray
            $lines | Write-Host
        }
        $offset[$src.Path] = (Get-Item $src.Path).Length
    }

    while ($true) {
        Start-Sleep -Milliseconds 400
        foreach ($src in $sources) {
            if (-not (Test-Path $src.Path)) { continue }
            $path = $src.Path
            $file = Get-Item $path
            if ($file.Length -le $offset[$path]) { continue }

            $stream = [System.IO.File]::Open(
                $path,
                [System.IO.FileMode]::Open,
                [System.IO.FileAccess]::Read,
                [System.IO.FileShare]::ReadWrite)
            try {
                $stream.Position = $offset[$path]
                $reader = [System.IO.StreamReader]::new($stream, [System.Text.Encoding]::UTF8, $true)
                while ($null -ne ($line = $reader.ReadLine())) {
                    Write-Host "[$($src.Tag)] $line"
                }
                $offset[$path] = $stream.Position
            } finally {
                $stream.Close()
            }
        }
    }
}

function Show-Help {
    Write-Host ""
    Write-Host "Lore Chat 开发环境" -ForegroundColor White
    Write-Host ""
    Write-Host "  lorechat.bat setup    检测并安装 Python / Node / 依赖"
    Write-Host "  lorechat.bat start    启动 uvicorn --reload + Vite HMR"
    Write-Host "  lorechat.bat dev      同 start（兼容旧命令）"
    Write-Host "  lorechat.bat stop     停止服务"
    Write-Host "  lorechat.bat restart  重启服务"
    Write-Host "  lorechat.bat log      跟踪日志"
    Write-Host ""
    Write-Host "  建议使用 lorechat.bat，避免 PowerShell 执行策略限制"
    Write-Host ""
}

# --- entry ---
try {
    switch ($Command) {
        "setup"   { Invoke-Setup }
        "start"   { Invoke-Start }
        "dev"     { Invoke-Start }
        "stop"    { Invoke-Stop }
        "restart" { Invoke-Stop; Invoke-Start }
        "log"     { Invoke-Log }
        "help"    { Show-Help }
        default   { Show-Help; exit 1 }
    }
} catch {
    Write-Err $_.Exception.Message
    exit 1
}
