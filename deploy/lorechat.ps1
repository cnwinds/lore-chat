# Lore Chat 单文件启动器（Windows PowerShell）
# 用法: .\lorechat.ps1 start [--chat|--work]
# 自包含：运行时在脚本旁写出 compose / 沙箱配置。
# 生成: python3 scripts/gen-deploy-launchers.py
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Runtime = Join-Path $Root ".lorechat"
$ModeFile = Join-Path $Runtime "run-mode"
$DefaultSandboxImage = "ghcr.io/cnwinds/lore-chat-sandbox-agent:latest"
$OpensandboxServerImage = "opensandbox/server:latest"
$OpensandboxExecdImage = "opensandbox/execd:v1.0.18"
$OpensandboxEgressImage = "opensandbox/egress:v1.1.0"

function Show-Usage {
  @"
Usage: .\lorechat.ps1 <command> [options]

Commands:
  start [--chat|--work]   Start (chat or Work mode)
  stop                    Stop
  update [--chat|--work]  Pull images and start
  prepare                 Write compose/config only
  log                     Tail logs
  help                    Help
"@
}

function Write-BundleFile([string]$RelPath, [string]$Content) {
  $path = Join-Path $Root $RelPath
  $dir = Split-Path -Parent $path
  if ($dir) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
  $utf8 = New-Object System.Text.UTF8Encoding $false
  [System.IO.File]::WriteAllText($path, $Content.TrimEnd() + "`n", $utf8)
}

function Materialize-Bundle {
  New-Item -ItemType Directory -Force -Path $Runtime | Out-Null
  New-Item -ItemType Directory -Force -Path (Join-Path $Root "data\knowledge") | Out-Null
  New-Item -ItemType Directory -Force -Path (Join-Path $Root "data\backups") | Out-Null
  Write-BundleFile 'docker-compose.yml' @'
name: lore-chat

services:
  backend:
    image: ${LORECHAT_BACKEND_IMAGE:-ghcr.io/cnwinds/lore-chat-backend:latest}
    container_name: lorechat-backend
    env_file:
      - .env
    environment:
      KB_PATH: /data/knowledge
      BACKUP_DIR: /data/backups
      SANDBOX_ENABLED: ${SANDBOX_ENABLED:-false}
      HTTP_PROXY: ${HTTP_PROXY:-}
      HTTPS_PROXY: ${HTTPS_PROXY:-}
      http_proxy: ${http_proxy:-${HTTP_PROXY:-}}
      https_proxy: ${https_proxy:-${HTTPS_PROXY:-}}
      NO_PROXY: ${NO_PROXY:-localhost,127.0.0.1}
      no_proxy: ${no_proxy:-${NO_PROXY:-localhost,127.0.0.1}}
    volumes:
      - ./data/knowledge:/data/knowledge
      - ./data/backups:/data/backups
    extra_hosts:
      - "host.docker.internal:host-gateway"
    restart: unless-stopped
    networks:
      - lorechat
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  web:
    image: ${LORECHAT_WEB_IMAGE:-ghcr.io/cnwinds/lore-chat-web:latest}
    container_name: lorechat-web
    ports:
      - "${WEB_PORT:-8080}:80"
    depends_on:
      backend:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - lorechat

networks:
  lorechat:
    name: lorechat-net
'@
  Write-BundleFile 'docker-compose.sandbox.yml' @'
# Work overlay for prebuilt images (default SANDBOX_IMAGE=ghcr.io/cnwinds/lore-chat-sandbox-agent:latest).
# Embedded by gen-deploy-launchers.py from docker/docker-compose.sandbox.yml.
# 带执行能力（OpenSandbox）的叠加编排。
# 默认 docker-compose.yml 不含沙箱；需要执行能力时额外 -f 本文件。
# 预构建单文件启动器由 scripts/gen-deploy-launchers.py 嵌入本文件（并把 SANDBOX_IMAGE 默认改为 GHCR）。
#
# 启动示例（项目根）：
#   docker compose --project-directory docker --env-file .env \
#     -f docker/docker-compose.yml -f docker/docker-compose.sandbox.yml up -d --build
#
# 沙箱 Agent 镜像（hn-video-report 默认环境）须先构建：
#   docker build -t lorechat-sandbox-agent:local \
#     -f docker/opensandbox/Dockerfile.agent docker/opensandbox

services:
  backend:
    environment:
      SANDBOX_ENABLED: "true"
      OPENSANDBOX_DOMAIN: opensandbox-server:8090
      OPENSANDBOX_PROTOCOL: http
      # server 内嵌 proxy 在本机 Docker 下会挂死；backend 经 host.docker.internal 直连 sandbox 端口
      OPENSANDBOX_USE_SERVER_PROXY: "false"
      OPENSANDBOX_API_KEY: ${OPENSANDBOX_API_KEY:-}
      OPENSANDBOX_WORKSPACE_VOLUME: lorechat-sandbox-workspace
      SANDBOX_IMAGE: ${SANDBOX_IMAGE:-ghcr.io/cnwinds/lore-chat-sandbox-agent:latest}
      # 默认信任：沙箱命令不征询；可在设置里关闭
      SANDBOX_TRUST_MODE: ${SANDBOX_TRUST_MODE:-true}
      SANDBOX_MIRROR_REGION: ${SANDBOX_MIRROR_REGION:-cn}
    extra_hosts:
      - "host.docker.internal:host-gateway"
    depends_on:
      opensandbox-server:
        condition: service_started

  opensandbox-server:
    image: opensandbox/server:latest
    container_name: lorechat-opensandbox
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./opensandbox/config.toml:/etc/opensandbox/config.toml:ro
    environment:
      SANDBOX_CONFIG_PATH: /etc/opensandbox/config.toml
      # 生产务必在 .env 设置 OPENSANDBOX_API_KEY，并改 OPENSANDBOX_INSECURE_SERVER=NO
      OPENSANDBOX_INSECURE_SERVER: ${OPENSANDBOX_INSECURE_SERVER:-YES}
    ports:
      # 可选：宿主机调试；backend 走内网 opensandbox-server:8090
      - "${OPENSANDBOX_HOST_PORT:-18090}:8090"
    networks:
      - lorechat
    extra_hosts:
      - "host.docker.internal:host-gateway"
    restart: unless-stopped

volumes:
  # OpenSandbox PVC claimName 对应的 Docker named volume（须预先存在）
  lorechat-sandbox-workspace:
    name: lorechat-sandbox-workspace
'@
  Write-BundleFile 'opensandbox/config.toml' @'
[server]
host = "0.0.0.0"
port = 8090

[log]
level = "INFO"

[runtime]
type = "docker"
execd_image = "opensandbox/execd:v1.0.18"

[egress]
image = "opensandbox/egress:v1.1.0"

[docker]
network_mode = "bridge"
# server 跑在容器里时须用宿主机可达地址（官方 compose 示例同此）；
# backend 走 use_server_proxy，不直连 host_ip。宿主机直连调试请用 spike 的 127.0.0.1。
host_ip = "host.docker.internal"
drop_capabilities = ["AUDIT_WRITE", "MKNOD", "NET_ADMIN", "NET_RAW", "SYS_ADMIN", "SYS_MODULE", "SYS_PTRACE", "SYS_TIME", "SYS_TTY_CONFIG"]
no_new_privileges = true
pids_limit = 4096

[ingress]
mode = "direct"
'@
  Write-BundleFile '.env.example' @'
# 由单文件启动器写出。模型与 API Key 请在网页「设置 → 模型」自行添加。

WEB_PORT=8080

# OPENAI_API_KEY=
# OPENAI_BASE_URL=
# SMALL_MODEL=
# BIG_MODEL=
# EMBED_MODEL=

SANDBOX_IMAGE=ghcr.io/cnwinds/lore-chat-sandbox-agent:latest

# LORECHAT_BACKEND_IMAGE=ghcr.io/cnwinds/lore-chat-backend:latest
# LORECHAT_WEB_IMAGE=ghcr.io/cnwinds/lore-chat-web:latest
'@

  $envPath = Join-Path $Root ".env"
  $example = Join-Path $Root ".env.example"
  if (-not (Test-Path $envPath)) {
    Copy-Item $example $envPath
    Write-Host "[Lore Chat] Created .env (set API Key in the web UI if needed)"
  }
}

function Read-SavedMode {
  if (Test-Path $ModeFile) { return ((Get-Content $ModeFile -Raw).Trim()) }
  return "chat"
}

function Save-Mode([string]$Mode) {
  New-Item -ItemType Directory -Force -Path $Runtime | Out-Null
  Set-Content -Path $ModeFile -Value $Mode -NoNewline
}

function Test-CanPrompt {
  if (-not [Environment]::UserInteractive) { return $false }
  try { if ([Console]::IsInputRedirected) { return $false } } catch { return $false }
  return $true
}

function Resolve-Mode([string]$Flag) {
  switch -Regex ($Flag) {
    "^(--chat|chat)$" { return "chat" }
    "^(--work|work)$" { return "work" }
    "^$" {
      if (-not (Test-CanPrompt)) { return (Read-SavedMode) }
      $saved = Read-SavedMode
      $default = if ($saved -eq "work") { "2" } else { "1" }
      Write-Host "[Lore Chat] Choose mode:"
      Write-Host "  1) Chat - knowledge base conversation"
      Write-Host "  2) Work - plus sandbox execution"
      $choice = Read-Host "Enter 1 or 2 [default $default]"
      if ([string]::IsNullOrWhiteSpace($choice)) { $choice = $default }
      if ($choice -eq "2") { return "work" }
      return "chat"
    }
    default { throw "Unknown mode: $Flag (use --chat or --work)" }
  }
}

function Get-SandboxImageRef {
  $envPath = Join-Path $Root ".env"
  if (Test-Path $envPath) {
    $line = Get-Content $envPath | Where-Object { $_ -match "^SANDBOX_IMAGE=" } | Select-Object -First 1
    if ($line) {
      $val = ($line -split "=", 2)[1].Trim()
      if ($val) { return $val }
    }
  }
  if ($env:SANDBOX_IMAGE) { return $env:SANDBOX_IMAGE }
  return $DefaultSandboxImage
}

function Test-DockerImage([string]$Image) {
  docker image inspect $Image 2>$null | Out-Null
  return ($LASTEXITCODE -eq 0)
}

function Test-WorkImagesCached {
  $agent = Get-SandboxImageRef
  return (Test-DockerImage $OpensandboxServerImage) `
    -and (Test-DockerImage $agent) `
    -and (Test-DockerImage $OpensandboxExecdImage) `
    -and (Test-DockerImage $OpensandboxEgressImage)
}

function Warn-WorkImages {
  if (Test-WorkImagesCached) {
    Write-Host "[Lore Chat] Work mode: sandbox images already present; will check for updates."
    return
  }
  Write-Host "[Lore Chat] Work mode will pull extra sandbox images (server, execd, egress, sandbox-agent)."
  Write-Host "[Lore Chat] First download may take a while."
}

function Get-ComposeArgs([string]$Mode) {
  $a = @("--project-directory", $Root, "--env-file", (Join-Path $Root ".env"), "-f", (Join-Path $Root "docker-compose.yml"))
  if ($Mode -eq "work") {
    $a += @("-f", (Join-Path $Root "docker-compose.sandbox.yml"))
  }
  return $a
}

function Invoke-Compose([string]$Mode, [string[]]$ComposeCommand) {
  if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker not found. Install Docker Desktop first."
  }
  $a = (Get-ComposeArgs $Mode) + $ComposeCommand
  & docker compose @a
  if ($LASTEXITCODE -ne 0) { throw "docker compose failed ($LASTEXITCODE)" }
}

function Teardown-All {
  try { Invoke-Compose "work" @("down", "--remove-orphans") | Out-Null } catch { }
  try { Invoke-Compose "chat" @("down", "--remove-orphans") | Out-Null } catch { }
}

function Get-WebPort {
  $envPath = Join-Path $Root ".env"
  $line = Get-Content $envPath | Where-Object { $_ -match "^WEB_PORT=" } | Select-Object -First 1
  if ($line) { return ($line -split "=", 2)[1].Trim() }
  return "8080"
}

function Start-Lore([string]$Flag) {
  Materialize-Bundle
  $mode = Resolve-Mode $Flag
  if ($mode -eq "work") { Warn-WorkImages }
  Write-Host "[Lore Chat] Starting (mode: $mode)..."
  Teardown-All
  Invoke-Compose $mode @("pull")
  Invoke-Compose $mode @("up", "-d")
  Save-Mode $mode
  $port = Get-WebPort
  Write-Host "[Lore Chat] Ready -> http://localhost:$port"
  Write-Host "[Lore Chat] Mode -> $mode; logs -> .\lorechat.ps1 log"
  Write-Host "[Lore Chat] If API Key is missing, the web UI will guide you."
}

$cmd = if ($args.Count -ge 1) { $args[0] } else { "help" }
$opt = if ($args.Count -ge 2) { $args[1] } else { "" }

switch ($cmd) {
  "start" { Start-Lore $opt }
  "stop" {
    Materialize-Bundle
    Teardown-All
    Write-Host "[Lore Chat] Stopped"
  }
  "update" {
    if ($opt) { Start-Lore $opt } else { Start-Lore (Read-SavedMode) }
  }
  "prepare" {
    Materialize-Bundle
    Write-Host "[Lore Chat] Wrote compose / sandbox / opensandbox/config.toml / .env.example"
    Write-Host "[Lore Chat] Dir: $Root"
  }
  "log" { Materialize-Bundle; Invoke-Compose (Read-SavedMode) @("logs", "-f", "--tail=50") }
  "logs" { Materialize-Bundle; Invoke-Compose (Read-SavedMode) @("logs", "-f", "--tail=50") }
  "help" { Show-Usage }
  "-h" { Show-Usage }
  "--help" { Show-Usage }
  default {
    Show-Usage
    exit 1
  }
}
