param([string]$DataRoot)
$ErrorActionPreference = 'Stop'
$studioRoot = $PSScriptRoot
$runtimePath = Join-Path $studioRoot '.venv-cpython/Scripts/pythonw.exe'
if (-not (Test-Path -LiteralPath $runtimePath)) { throw '请先按README建立本项目的独立运行环境，或使用完整便携包。' }
$launchArgs = @('"' + (Join-Path $studioRoot 'apps/desktop/main.py') + '"')
if ($DataRoot) { $launchArgs += @('--home', '"' + $DataRoot + '"') }
Start-Process -FilePath $runtimePath -ArgumentList $launchArgs -WorkingDirectory $studioRoot -WindowStyle Hidden
