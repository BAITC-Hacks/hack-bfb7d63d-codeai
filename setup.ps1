param(
    [string]$VenvDir = '.venv',
    [string]$Wheelhouse = ''
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskEnvironment = [System.IO.Path]::GetFullPath($VenvDir)
$taskPython = Join-Path $taskEnvironment 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    python -m venv $taskEnvironment
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
$taskInstallArgs = @('-m', 'pip', 'install', '--disable-pip-version-check', '-r', (Join-Path $PSScriptRoot 'requirements.txt'))
if ($Wheelhouse) {
    $taskWheels = (Resolve-Path -LiteralPath $Wheelhouse).Path
    $taskInstallArgs += @('--no-index', '--find-links', $taskWheels)
}
& $taskPython @taskInstallArgs
exit $LASTEXITCODE
