[CmdletBinding()]
param(
    [ValidateNotNullOrEmpty()]
    [string]$OutputDirectory = "dist",
    [switch]$Offline
)

$ErrorActionPreference = "Stop"

$uvCommand = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue
if ($null -eq $uvCommand) {
    throw "uv를 찾을 수 없습니다. uv를 설치하고 PATH에 등록한 후 다시 실행하세요."
}

if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot "pyproject.toml") -PathType Leaf)) {
    throw "스크립트 위치에서 pyproject.toml을 찾을 수 없습니다."
}

if ([System.IO.Path]::IsPathRooted($OutputDirectory)) {
    $resolvedOutput = [System.IO.Path]::GetFullPath($OutputDirectory)
} else {
    $resolvedOutput = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot $OutputDirectory))
}

$buildArguments = @(
    "build", "--wheel", "--python", "3.11.9", "--out-dir", $resolvedOutput,
    "--config-setting=--build-option=--python-tag=py311",
    "--config-setting=--build-option=--plat-name=win_amd64"
)
if ($Offline) {
    $buildArguments += "--offline"
}

Push-Location -LiteralPath $PSScriptRoot
try {
    & $uvCommand.Source @buildArguments
    if ($LASTEXITCODE -ne 0) {
        throw "wheel 빌드에 실패했습니다. uv 종료 코드: $LASTEXITCODE"
    }
    Write-Host "wheel 빌드 완료: $resolvedOutput"
} finally {
    Pop-Location
}
