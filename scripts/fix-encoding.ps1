$files = @(
    (Join-Path (Split-Path $PSScriptRoot -Parent) "lorechat.bat")
    (Join-Path $PSScriptRoot "env-setup.ps1")
)
foreach ($f in $files) {
    $t = [IO.File]::ReadAllText($f)
    [IO.File]::WriteAllText($f, $t, (New-Object System.Text.UTF8Encoding $true))
}
Write-Host "UTF-8 BOM applied"
