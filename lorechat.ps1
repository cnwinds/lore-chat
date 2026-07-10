# 入口转发到 scripts\lorechat.ps1
# 若直接运行报“禁止运行脚本”，请改用: .\lorechat.bat dev
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$scriptPath = Join-Path $PSScriptRoot "scripts\lorechat.ps1"
if ($Rest.Count -gt 0) {
    & $scriptPath @Rest
} else {
    & $scriptPath help
}
exit $LASTEXITCODE
