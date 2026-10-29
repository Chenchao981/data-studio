param([switch]$SkipArchive)
$ErrorActionPreference = 'Stop'
$studioRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (!(Test-Path -LiteralPath (Join-Path $studioRoot 'engines/manifest.json'))) { throw '请先准备固定版本计算组件（packaging/prepare_engines.py）' }
Push-Location (Join-Path $studioRoot 'apps/web')
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw '前端依赖安装失败' }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw '前端构建失败' }
} finally { Pop-Location }
Push-Location $studioRoot
$previousPath = $env:PATH
try {
    # Isolate DLL discovery from unrelated tools (Conda, Poppler, etc.).
    $env:PATH = (Join-Path $studioRoot '.venv-cpython/Scripts') + ';' + $env:SystemRoot + '\System32;' + $env:SystemRoot
    & '.venv-cpython/Scripts/python.exe' 'packaging/collect_notices.py'
    if ($LASTEXITCODE -ne 0) { throw '依赖说明收集失败' }
    & '.venv-cpython/Scripts/python.exe' -m PyInstaller --clean --noconfirm --workpath 'build/cpython' 'packaging/studio.spec'
    if ($LASTEXITCODE -ne 0) { throw 'Windows打包失败' }
    & '.venv-cpython/Scripts/python.exe' 'packaging/copy_engine_kit.py' 'engines' 'dist/DesktopDataStudio/engines'
    if ($LASTEXITCODE -ne 0) { throw '计算组件完整性校验失败' }
    Copy-Item -LiteralPath (Join-Path $studioRoot 'README.md') -Destination (Join-Path $studioRoot 'dist/DesktopDataStudio/README.md')
    Copy-Item -LiteralPath (Join-Path $studioRoot 'docs') -Destination (Join-Path $studioRoot 'dist/DesktopDataStudio/docs') -Recurse
    $archive = Join-Path $studioRoot ('dist/DesktopDataStudio-M1-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.zip')
    if (!$SkipArchive) {
        & '.venv-cpython/Scripts/python.exe' 'packaging/archive_bundle.py' 'dist/DesktopDataStudio' $archive
        if ($LASTEXITCODE -ne 0) { throw 'Archive build failed' }
    }
} finally { $env:PATH = $previousPath; Pop-Location }
