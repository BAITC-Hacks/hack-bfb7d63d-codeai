param([ValidateRange(1, 65535)][int]$Port = 8501)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    Write-Host 'Virtual environment is missing. Run setup.ps1 first (use -PythonPath if Python is not on PATH).' -ForegroundColor Red
    exit 1
}
try {
    & $taskPython -c 'import streamlit' 2>$null
    $taskStreamlitReady = $LASTEXITCODE -eq 0
} catch {
    $taskStreamlitReady = $false
}
if (-not $taskStreamlitReady) {
    Write-Host 'Streamlit is unavailable in .venv. Run setup.ps1 to install the pinned dependencies.' -ForegroundColor Red
    exit 1
}
Write-Host "Open http://127.0.0.1:$Port in your browser. Stop the server with Ctrl+C."
& $taskPython -m streamlit run app.py --server.address 127.0.0.1 --server.port $Port --server.headless true
exit $LASTEXITCODE

