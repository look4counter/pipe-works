[CmdletBinding()]
param(
    [string]$Python,
    [string]$SourceArchive,
    [string]$WorkDirectory,
    [string]$OutputDirectory,
    [switch]$PrepareOnly,
    [string[]]$CMakeArgument = @(),
    [string]$Pybind11SourceDirectory,
    [string]$DLPackSourceDirectory
)

$ErrorActionPreference = "Stop"
if (-not $Python) { $Python = Join-Path $PSScriptRoot ".venv/Scripts/python.exe" }
if (-not $SourceArchive) { $SourceArchive = Join-Path $PSScriptRoot "PyNvVideoCodec_2.2.2.zip" }
if (-not $WorkDirectory) { $WorkDirectory = Join-Path $PSScriptRoot "build/pynvvideocodec" }
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $PSScriptRoot "dist" }
$buildArguments = @(
    "$PSScriptRoot/tools/build_pynvvideocodec.py",
    "--source-archive", $SourceArchive,
    "--work-dir", $WorkDirectory,
    "--wheel-dir", $OutputDirectory
)
if ($PrepareOnly) { $buildArguments += "--prepare-only" }
foreach ($argument in $CMakeArgument) { $buildArguments += "--cmake-arg=$argument" }
if ($Pybind11SourceDirectory) {
    $buildArguments += @("--pybind11-source-dir", $Pybind11SourceDirectory)
}
if ($DLPackSourceDirectory) {
    $buildArguments += @("--dlpack-source-dir", $DLPackSourceDirectory)
}
& $Python @buildArguments
if ($LASTEXITCODE -ne 0) { throw "PyNvVideoCodec wheel build failed." }
