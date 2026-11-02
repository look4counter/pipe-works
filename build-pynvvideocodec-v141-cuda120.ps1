[CmdletBinding()]
param(
    [string]$Python,
    [string]$SourceArchive,
    [string]$WorkDirectory,
    [string]$OutputDirectory,
    [switch]$PrepareOnly,
    [string]$VisualStudioDirectory,
    [string]$CudaDirectory = "$env:ProgramFiles/NVIDIA GPU Computing Toolkit/CUDA/v12.0",
    [string]$Pybind11SourceDirectory,
    [string]$DLPackSourceDirectory
)

$ErrorActionPreference = 'Stop'
if (-not $Python) { $Python = Join-Path $PSScriptRoot 'build/pynvvideocodec-env/Scripts/python.exe' }
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw '빌드 Python이 없습니다. docs/pynvvideocodec-build.md의 준비 명령을 실행하세요.' }
$Python = (Resolve-Path -LiteralPath $Python).Path
& $Python -c 'import sys; assert sys.version_info[:2] == (3,11) and sys.maxsize > 2**32'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 x64를 지정하세요.' }
if (-not $SourceArchive) { $SourceArchive = Join-Path $PSScriptRoot 'PyNvVideoCodec_2.2.2.zip' }
if (-not $WorkDirectory) { $WorkDirectory = Join-Path $PSScriptRoot 'build/pynvvideocodec-patched-v141-cuda120' }
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $PSScriptRoot 'dist/pynvvideocodec-patched-v141-cuda120' }
$buildArguments = @("$PSScriptRoot/tools/build_pynvvideocodec.py", '--source-archive', $SourceArchive, '--work-dir', $WorkDirectory, '--wheel-dir', $OutputDirectory)
if ($PrepareOnly) { $buildArguments += '--prepare-only' }
$savedEnvironment = @{}
Get-ChildItem Env: | ForEach-Object { $savedEnvironment[$_.Name] = $_.Value }
try {
    if (-not $PrepareOnly) {
        if (-not $VisualStudioDirectory) {
            $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
            if (-not (Test-Path -LiteralPath $vswhere)) { throw 'Visual Studio Installer의 vswhere.exe가 없습니다.' }
            $VisualStudioDirectory = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.v141.x86.x64 -property installationPath
        }
        if (-not $VisualStudioDirectory) { throw 'MSVC v141(14.16) x64/x86 빌드 도구를 설치하세요.' }
        $developerCommand = Join-Path $VisualStudioDirectory 'Common7/Tools/VsDevCmd.bat'
        if (-not (Test-Path -LiteralPath $developerCommand)) { throw "개발자 환경 파일이 없습니다: $developerCommand" }
        $compilerEnvironment = & $env:ComSpec /d /c "call `"$developerCommand`" -arch=x64 -host_arch=x64 -vcvars_ver=14.16 >nul && set"
        if ($LASTEXITCODE -ne 0) { throw 'MSVC v141 개발자 환경 선택에 실패했습니다.' }
        foreach ($line in $compilerEnvironment) {
            if ($line -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') }
        }
        if ($env:VCToolsVersion -notlike '14.16.*') { throw "v141 대신 다른 도구가 선택됐습니다: $env:VCToolsVersion" }
        $compiler = (Get-Command cl.exe -ErrorAction Stop).Source
        if ((Get-Item -LiteralPath $compiler).VersionInfo.FileVersion -notmatch '^19\.16\.') { throw "컴파일러가 19.16 계열이 아닙니다: $compiler" }
        $CudaDirectory = (Resolve-Path -LiteralPath $CudaDirectory).Path
        $nvcc = Join-Path $CudaDirectory 'bin/nvcc.exe'
        $cudaVersion = & $nvcc --version
        if ($LASTEXITCODE -ne 0 -or ($cudaVersion -join "`n") -notmatch 'release 12\.0,') { throw 'CUDA Toolkit 12.0이 필요합니다.' }
        $env:CUDA_PATH = $env:CUDAToolkit_ROOT = $CudaDirectory
        $env:CUDACXX = $nvcc
        $env:CC = $env:CXX = $compiler
        $env:CMAKE_GENERATOR = 'Ninja Multi-Config'
        $env:CMAKE_BUILD_TYPE = 'Release'
        $env:CL = '/utf-8'
        $env:_CL_ = ''
        $env:LINK = ''
        $env:CMAKE_ARGS = ''
        $env:SKBUILD_CONFIGURE_OPTIONS = ''
        $env:CMAKE_GENERATOR_TOOLSET = ''
        $env:CMAKE_GENERATOR_PLATFORM = ''
        $env:PATH = "$(Split-Path $Python);$CudaDirectory/bin;$env:PATH"
        Write-Host "빌드 도구: $compiler / CUDA: $CudaDirectory / Release"
        if (-not $Pybind11SourceDirectory -and (Test-Path "$PSScriptRoot/build/deps/pybind11-2.10.0")) { $Pybind11SourceDirectory = "$PSScriptRoot/build/deps/pybind11-2.10.0" }
        if (-not $DLPackSourceDirectory -and (Test-Path "$PSScriptRoot/build/deps/dlpack-0.8")) { $DLPackSourceDirectory = "$PSScriptRoot/build/deps/dlpack-0.8" }
    }
    if ($Pybind11SourceDirectory) { $buildArguments += @('--pybind11-source-dir', $Pybind11SourceDirectory) }
    if ($DLPackSourceDirectory) { $buildArguments += @('--dlpack-source-dir', $DLPackSourceDirectory) }
    & $Python @buildArguments
    if ($LASTEXITCODE -ne 0) { throw 'PyNvVideoCodec v141·CUDA 12.0 빌드에 실패했습니다.' }
}
finally {
    Get-ChildItem Env: | Where-Object { -not $savedEnvironment.ContainsKey($_.Name) } | ForEach-Object { [Environment]::SetEnvironmentVariable($_.Name, $null, 'Process') }
    foreach ($name in $savedEnvironment.Keys) { [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], 'Process') }
}
