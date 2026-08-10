# Lore Chat single-file install (Windows PowerShell)
#   irm https://raw.githubusercontent.com/cnwinds/lore-chat/master/deploy/get-lorechat.ps1 | iex
#   With mode: download then .\lorechat.ps1 start --work
#   Or: & ([scriptblock]::Create((irm .../get-lorechat.ps1))) -Mode --work
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

function Save-Utf8Bom([string]$Path, [string]$Content) {
  $utf8Bom = New-Object System.Text.UTF8Encoding $true
  [System.IO.File]::WriteAllText($Path, $Content, $utf8Bom)
}

Write-Host "[Lore Chat] Install dir: $Dest"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
$launcher = Join-Path $Dest "lorechat.ps1"
Write-Host "[Lore Chat] Downloading lorechat.ps1 (single-file launcher)"
# Download as text and rewrite with UTF-8 BOM so Windows PowerShell 5.1
# does not mis-decode the script as system ANSI (GBK) on Chinese Windows.
$launcherText = (Invoke-WebRequest -Uri "$RepoRaw/deploy/lorechat.ps1" -UseBasicParsing).Content
Save-Utf8Bom $launcher $launcherText

Set-Location $Dest
Write-Host "[Lore Chat] Ready. Only lorechat.ps1 is required in this folder."
if ($Mode) {
  & $launcher start $Mode
} elseif (Test-CanPrompt) {
  # Interactive: let launcher prompt for chat / Work
  & $launcher start
} else {
  # Piped install (irm|iex): stdin not interactive -> default chat
  & $launcher start --chat
}
