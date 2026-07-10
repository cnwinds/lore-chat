# Lore Chat environment setup: detect / install Python, Node.js, backend venv, frontend deps

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function Write-Info([string]$msg) { Write-Host "[提示] $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg) { Write-Host "[完成] $msg" -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "[警告] $msg" -ForegroundColor Yellow }
function Write-Err([string]$msg) { Write-Host "[错误] $msg" -ForegroundColor Red }

function Refresh-PathFromRegistry {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($machine -and $user) {
        $env:Path = "$machine;$user"
    } elseif ($machine) {
        $env:Path = $machine
    }
}

function Get-NodeSearchPaths([string]$toolsDir) {
    $paths = [System.Collections.Generic.List[string]]::new()
    if ($env:ProgramFiles) { $paths.Add((Join-Path $env:ProgramFiles "nodejs")) | Out-Null }
    if (${env:ProgramFiles(x86)}) { $paths.Add((Join-Path ${env:ProgramFiles(x86)} "nodejs")) | Out-Null }
    if ($env:LOCALAPPDATA) { $paths.Add((Join-Path $env:LOCALAPPDATA "Programs\nodejs")) | Out-Null }
    if ($toolsDir) { $paths.Add((Join-Path $toolsDir "node")) | Out-Null }
    return $paths.ToArray()
}

function Find-Executable([string]$name, [string[]]$extraPaths) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cmd) {
        $path = if ($cmd.Path) { $cmd.Path } elseif ($cmd.Source) { $cmd.Source } else { $null }
        if (-not [string]::IsNullOrWhiteSpace($path)) { return $path }
    }

    foreach ($dir in $extraPaths) {
        if ([string]::IsNullOrWhiteSpace($dir)) { continue }
        if ($name -eq "npm") {
            $npmCmd = Join-Path $dir "npm.cmd"
            if (Test-Path $npmCmd) { return $npmCmd }
        }
        foreach ($suffix in @("", ".exe", ".cmd")) {
            $candidate = Join-Path $dir ($name + $suffix)
            if (Test-Path $candidate) { return $candidate }
        }
    }
    return $null
}

function Install-PortableNode([string]$toolsDir) {
    $nodeRoot = Join-Path $toolsDir "node"
    $marker = Join-Path $nodeRoot ".installed"
    if (Test-Path $marker) {
        $nodeDir = Get-Content $marker -Raw
        $nodeDir = $nodeDir.Trim()
        if (Test-Path (Join-Path $nodeDir "npm.cmd")) {
            $env:Path = "$nodeDir;$env:Path"
            return (Join-Path $nodeDir "npm.cmd")
        }
    }

    $version = "v20.18.1"
    $zipName = "node-$version-win-x64.zip"
    $url = "https://nodejs.org/dist/$version/$zipName"
    $zipPath = Join-Path $toolsDir $zipName

    Write-Info "正在下载便携版 Node.js $version ..."
    New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null
    Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing

    $extractDir = Join-Path $toolsDir "node-extract"
    if (Test-Path $extractDir) { Remove-Item -Recurse -Force $extractDir }
    Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force

    $extracted = Get-ChildItem $extractDir -Directory | Select-Object -First 1
    if (-not $extracted) { throw "Node.js 解压失败" }

    if (Test-Path $nodeRoot) { Remove-Item -Recurse -Force $nodeRoot }
    Move-Item $extracted.FullName $nodeRoot
    Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
    Remove-Item $extractDir -Recurse -Force -ErrorAction SilentlyContinue

    $nodeDir = $nodeRoot
    Set-Content -Path $marker -Value $nodeDir -Encoding UTF8
    $env:Path = "$nodeDir;$env:Path"
    Write-Ok "便携版 Node.js 已安装到 $nodeDir"
    return (Join-Path $nodeDir "npm.cmd")
}

function Ensure-Node([string]$toolsDir) {
    Refresh-PathFromRegistry
    $nodePaths = Get-NodeSearchPaths $toolsDir

    $npm = Find-Executable "npm" $nodePaths
    if ($npm) {
        $env:Path = "$(Split-Path $npm -Parent);$env:Path"
        return $npm
    }

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Info "未检测到 Node.js，正在通过 winget 安装 OpenJS.NodeJS.LTS ..."
        try {
            winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements --disable-interactivity | Out-Null
            Refresh-PathFromRegistry
            $nodePaths = Get-NodeSearchPaths $toolsDir
            $npm = Find-Executable "npm" $nodePaths
            if ($npm) {
                $env:Path = "$(Split-Path $npm -Parent);$env:Path"
                Write-Ok "Node.js 安装成功"
                return $npm
            }
        } catch {
            Write-Warn "winget 安装 Node.js 失败: $_"
        }
    }

    Write-Info "尝试安装便携版 Node.js（无需管理员权限）..."
    $npm = Install-PortableNode $toolsDir
    if ([string]::IsNullOrWhiteSpace($npm)) { throw "Node.js 安装失败" }
    return $npm
}

function Ensure-Python {
    Refresh-PathFromRegistry

    foreach ($py in @("python", "py")) {
        $cmd = Get-Command $py -ErrorAction SilentlyContinue
        if ($cmd) {
            if ($py -eq "py") { return "py -3" }
            & $cmd.Source --version 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { return $cmd.Source }
        }
    }

    $pyPaths = @()
    if ($env:ProgramFiles) { $pyPaths += (Join-Path $env:ProgramFiles "Python312\python.exe") }
    if ($env:LocalAppData) { $pyPaths += (Join-Path $env:LocalAppData "Programs\Python\Python312\python.exe") }
    foreach ($p in $pyPaths) {
        if (Test-Path $p) { return $p }
    }

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Info "未检测到 Python，正在通过 winget 安装 Python 3.12 ..."
        try {
            winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements --disable-interactivity
            Refresh-PathFromRegistry
            foreach ($p in $pyPaths) {
                if (Test-Path $p) { return $p }
            }
            $cmd = Get-Command python -ErrorAction SilentlyContinue
            if ($cmd) { return $cmd.Source }
        } catch {
            Write-Warn "winget 安装 Python 失败: $_"
        }
    }

    throw "未找到 Python。请安装 Python 3.11+ 或运行: winget install Python.Python.3.12"
}

function Ensure-BackendVenv([string]$backendDir) {
    $venvPython = Join-Path $backendDir ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) { return $venvPython }

    $python = Ensure-Python
    Write-Info "正在创建 Python 虚拟环境..."
    Push-Location $backendDir
    try {
        if ($python -eq "py -3") {
            & py -3 -m venv .venv
        } else {
            & $python -m venv .venv
        }
        if (-not (Test-Path $venvPython)) { throw "虚拟环境创建失败" }

        & $venvPython -m pip install --upgrade pip | Out-Null
        & $venvPython -m pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "部分依赖安装失败，尝试仅安装 chromadb 预编译包..."
            & $venvPython -m pip install "chromadb==0.5.*" --only-binary :all:
        }
        Write-Ok "后端虚拟环境就绪"
        return $venvPython
    } finally {
        Pop-Location
    }
}

function Ensure-FrontendDeps([string]$frontendDir, [string]$npmCmd) {
    if ([string]::IsNullOrWhiteSpace($npmCmd)) { throw "npm 路径无效" }
    if ([string]::IsNullOrWhiteSpace($frontendDir)) { throw "frontend 目录无效" }
    $nodeModules = Join-Path $frontendDir "node_modules"
    if (Test-Path $nodeModules) { return }

    Write-Info "正在安装前端依赖 (npm install)..."
    Push-Location $frontendDir
    try {
        & $npmCmd install
        if ($LASTEXITCODE -ne 0) { throw "npm install 失败" }
        Write-Ok "前端依赖安装完成"
    } finally {
        Pop-Location
    }
}

function Ensure-Docker {
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) {
        Write-Err "未检测到 Docker。请安装 Docker Desktop: https://www.docker.com/products/docker-desktop/"
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            Write-Info "可尝试: winget install Docker.DockerDesktop"
        }
        exit 1
    }
    & docker version *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Docker 已安装但未运行，请先启动 Docker Desktop"
        exit 1
    }
}

function Setup-DevEnvironment([string]$root) {
    $toolsDir = Join-Path $root ".lorechat\tools"
    $backendDir = Join-Path $root "backend"
    $frontendDir = Join-Path $root "frontend"

    Write-Host ""
    Write-Host "=== Lore Chat 环境检测 ===" -ForegroundColor White
    Write-Host ""

    $npm = Ensure-Node $toolsDir
    if ([string]::IsNullOrWhiteSpace($npm)) { throw "未找到 npm，请运行 lorechat.bat setup" }
    $nodeDir = Split-Path $npm -Parent
    $nodeVer = & (Join-Path $nodeDir "node.exe") --version 2>$null
    Write-Ok "Node.js: $nodeVer ($nodeDir)"

    $venvPy = Ensure-BackendVenv $backendDir
    $pyVer = & $venvPy --version
    Write-Ok "Python: $pyVer (venv)"

    Ensure-FrontendDeps $frontendDir $npm
    Write-Ok "前端依赖: OK"

    $backendEnv = Join-Path $backendDir ".env"
    if (-not (Test-Path $backendEnv)) {
        $example = Join-Path $backendDir ".env.example"
        if (Test-Path $example) {
            Copy-Item $example $backendEnv
            Write-Info "已从 backend\.env.example 创建 .env，请填入 API Key"
        }
    }

    Write-Host ""
    Write-Ok "开发环境就绪"
    Write-Host ""
}

function Setup-DockerEnvironment([string]$root) {
    Ensure-Docker
    $envFile = Join-Path $root ".env"
    $example = Join-Path $root ".env.docker.example"
    if (-not (Test-Path $envFile) -and (Test-Path $example)) {
        Copy-Item $example $envFile
        Write-Info "已从 .env.docker.example 创建 .env，请填入 OPENAI_API_KEY"
    }
    Write-Ok "Docker 环境就绪"
}

# Export for dot-sourcing
if ($MyInvocation.InvocationName -ne '.') {
  # script run directly for testing
}
