param([switch]$Rebuild)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $projectRoot
try {
    if ($Rebuild) {
        & (Join-Path $PSScriptRoot 'build.ps1') -SkipArchive
        if ($LASTEXITCODE -ne 0) { throw '桌面程序构建失败' }
    }
    $projectPython = Join-Path $projectRoot '.venv-cpython/Scripts/python.exe'
    if (!(Test-Path -LiteralPath $projectPython)) { throw '请先运行项目 setup.ps1 准备固定构建环境' }
    & $projectPython (Join-Path $PSScriptRoot 'make_release.py')
    if ($LASTEXITCODE -ne 0) { throw '安装包生成或完整性校验失败，详见上方错误' }
} finally { Pop-Location }
