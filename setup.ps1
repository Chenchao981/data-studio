$ErrorActionPreference = 'Stop'
$studioRoot = $PSScriptRoot
$lock = Get-Content -LiteralPath (Join-Path $studioRoot 'runtime-lock.json') -Raw | ConvertFrom-Json
$runtimeRoot = Join-Path $studioRoot '.runtime/python313'
$runtimeExe = Join-Path $runtimeRoot 'tools/python.exe'
if (-not (Test-Path -LiteralPath $runtimeExe)) {
    $downloads = Join-Path $studioRoot 'artifacts'
    New-Item -ItemType Directory -Force -Path $downloads | Out-Null
    $archive = Join-Path $downloads ('python.' + $lock.version + '.nupkg')
    if (-not (Test-Path -LiteralPath $archive)) {
        & curl.exe --fail --location --retry 3 --output $archive $lock.source
        if ($LASTEXITCODE -ne 0) { throw 'CPython便携包下载失败，请稍后重试' }
    }
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLower() -ne $lock.sha256) { throw 'CPython便携包校验不一致' }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($archive)
    try {
        $resolvedRoot = [IO.Path]::GetFullPath($runtimeRoot)
        foreach ($entry in $zip.Entries) {
            $resolvedEntry = [IO.Path]::GetFullPath((Join-Path $resolvedRoot $entry.FullName))
            if (-not $resolvedEntry.StartsWith($resolvedRoot + [IO.Path]::DirectorySeparatorChar)) { throw '压缩包包含越界路径' }
        }
    } finally { $zip.Dispose() }
    [IO.Compression.ZipFile]::ExtractToDirectory($archive, $runtimeRoot)
}
$version = & $runtimeExe -c 'import platform; print(platform.python_version())'
if ($version -ne $lock.version) { throw '本地CPython版本与锁定文件不符' }
& $runtimeExe -m venv (Join-Path $studioRoot '.venv-cpython')
if ($LASTEXITCODE -ne 0) { throw '独立环境创建失败' }
& (Join-Path $studioRoot '.venv-cpython/Scripts/python.exe') -m pip install -r (Join-Path $studioRoot 'environments/studio.lock')
if ($LASTEXITCODE -ne 0) { throw '项目依赖安装失败' }
& (Join-Path $studioRoot '.venv-cpython/Scripts/python.exe') (Join-Path $studioRoot 'packaging/check_runtime_lock.py') --profile (Join-Path $studioRoot 'environments/studio.lock')
if ($LASTEXITCODE -ne 0) { throw '统一环境版本检查失败' }
Write-Output 'CPython项目环境准备完成；未改变系统PATH或原Anaconda环境。'
