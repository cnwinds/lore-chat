# 兼容旧路径：转发到项目根目录 lorechat.ps1
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$rootScript = Join-Path (Split-Path $PSScriptRoot -Parent) "lorechat.ps1"
if ($Rest.Count -gt 0) {
    & $rootScript @Rest
} else {
    & $rootScript help
}
exit $LASTEXITCODE
