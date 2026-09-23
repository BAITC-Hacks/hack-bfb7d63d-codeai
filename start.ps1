param([int]$Port = 8501)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    Write-Error 'Virtual environment is missing. Run setup.ps1 first.'
    exit 1
}
& $taskPython -m streamlit run app.py --server.address 127.0.0.1 --server.port $Port --server.headless true
exit $LASTEXITCODE

