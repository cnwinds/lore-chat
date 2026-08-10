# Lore Chat 单文件安装（Windows PowerShell）
#   irm https://raw.githubusercontent.com/cnwinds/lore-chat/master/deploy/get-lorechat.ps1 | iex
#   带模式: 先下载再 .\lorechat.ps1 start --work
#   或: & ([scriptblock]::Create((irm .../get-lorechat.ps1))) -Mode --work
param(
  [string]$Mode = "",
  [string]$Dir = ""
)

$ErrorActionPreference = "Stop"
$RepoRaw = if ($env:LORECHAT_REPO_RAW) { $env:LORECHAT_REPO_RAW } else { "https://raw.githubusercontent.com/cnwinds/lore-chat/master" }
$Dest = if ($Dir) { $Dir } elseif ($env:LORECHAT_DIR) { $env:LORECHAT_DIR } else { Join-Path (Get-Location) "lore-chat" }

function Test-CanPrompt {
  if (-not [Environment]::UserInteractive) { return $false }
  try { if ([Console]::IsInputRedirected) { return $false } } catch { return $false }
  return $true
}

Write-Host "[Lore Chat] Install dir: $Dest"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
$launcher = Join-Path $Dest "lorechat.ps1"
Write-Host "[Lore Chat] Downloading lorechat.ps1 (single-file launcher)"
Invoke-WebRequest -Uri "$RepoRaw/deploy/lorechat.ps1" -OutFile $launcher -UseBasicParsing

Set-Location $Dest
Write-Host "[Lore Chat] Ready. Only lorechat.ps1 is required in this folder."
if ($Mode) {
  & $launcher start $Mode
} elseif (Test-CanPrompt) {
  # 交互终端：交给启动器弹 chat / Work 菜单
  & $launcher start
} else {
  # 管道安装（irm|iex）stdin 非交互 → 默认聊天模式
  & $launcher start --chat
}
