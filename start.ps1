$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (Test-Path -LiteralPath $venvPython) {
    $launcher = $venvPython
} elseif ($pythonCommand) {
    $launcher = $pythonCommand.Source
} elseif (Test-Path -LiteralPath $bundledPython) {
    $launcher = $bundledPython
} else {
    throw 'Python 3.12 is required. Follow the installation steps in README.md.'
}
$challengeReady = @('nodes.parquet', 'edges.parquet', 'transactions.parquet') | ForEach-Object { Test-Path -LiteralPath (Join-Path $PSScriptRoot ('data\challenge\' + $_)) }
$launchArgs = if ($args.Count -gt 0) { $args } elseif ($challengeReady -notcontains $false) { @('--data', 'data/challenge', '--output', 'output/challenge', '--serve') } else { @('--demo', '--serve') }
if (($launchArgs -contains '--serve') -and (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.local/model-manifest.json'))) {
    try { & (Join-Path $PSScriptRoot 'start-local-model.ps1') }
    catch { Write-Warning ('Optional local model: ' + $_.Exception.Message) }
}
& $launcher (Join-Path $PSScriptRoot 'run.py') @launchArgs
exit $LASTEXITCODE
