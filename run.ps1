param(
    [string]$DataDir = 'data/case',
    [string]$Out = 'output/stage3',
    [string]$PythonPath,
    [ValidateRange(20, 2147483647)][int]$TopN = 30,
    [string]$Config,
    [switch]$Extended,
    [ValidateNotNullOrEmpty()][string]$VenvDir = '.venv',
    [string]$Wheelhouse = ''
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskSetupArguments = @{ VenvDir = $VenvDir }
if ($PythonPath) { $taskSetupArguments.PythonPath = $PythonPath }
if ($Wheelhouse) { $taskSetupArguments.Wheelhouse = $Wheelhouse }
& (Join-Path $PSScriptRoot 'setup.ps1') @taskSetupArguments
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$taskEnvironmentPath = $VenvDir
if (-not [System.IO.Path]::IsPathRooted($taskEnvironmentPath)) {
    $taskEnvironmentPath = Join-Path $PSScriptRoot $taskEnvironmentPath
}
$taskPython = Join-Path ([System.IO.Path]::GetFullPath($taskEnvironmentPath)) 'Scripts\python.exe'
$taskArguments = @('-m', 'moneymap', 'run', '--data-dir', $DataDir, '--out', $Out, '--top-n', $TopN)
if ($Config) { $taskArguments += @('--config', $Config) }
if ($Extended) { $taskArguments += '--extended' }
& $taskPython @taskArguments
exit $LASTEXITCODE
