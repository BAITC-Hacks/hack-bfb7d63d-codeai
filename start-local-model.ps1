param([switch]$Foreground)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$manifestPath = Join-Path $PSScriptRoot '.local/model-manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw 'Run python scripts/install_local_model.py first.'
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$modelServer = Join-Path $PSScriptRoot $manifest.server_path
$modelWeights = Join-Path $PSScriptRoot $manifest.model_path
$keyPath = Join-Path $PSScriptRoot '.local/model-key.txt'
if (-not (Test-Path -LiteralPath $keyPath)) {
    $randomBytes = New-Object byte[] 32
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $generator.GetBytes($randomBytes)
    $generator.Dispose()
    [System.IO.File]::WriteAllText($keyPath, [Convert]::ToBase64String($randomBytes))
}
$modelHeaders = @{ Authorization = 'Bearer ' + [System.IO.File]::ReadAllText($keyPath).Trim() }
try {
    $current = Invoke-RestMethod -Uri 'http://127.0.0.1:8766/v1/models' -Headers $modelHeaders -TimeoutSec 2
    if ($current.data.id -contains 'aqsha-local') { Write-Output 'AQSHA local model is already running.'; return }
} catch { }
$env:TEMP = Join-Path $PSScriptRoot '.build-temp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
$env:LLAMA_CACHE = Join-Path $PSScriptRoot '.local/cache'
if ($Foreground) {
    & $modelServer --model $modelWeights --alias aqsha-local --host 127.0.0.1 --port 8766 --ctx-size 4096 --threads 4 --threads-batch 4 --parallel 1 --no-webui --api-key-file $keyPath
    return
}
$arguments = @('--model', ('"' + $modelWeights + '"'), '--alias', 'aqsha-local', '--host', '127.0.0.1', '--port', '8766', '--ctx-size', '4096', '--threads', '4', '--threads-batch', '4', '--parallel', '1', '--no-webui', '--api-key-file', ('"' + $keyPath + '"'))
$modelProcess = Start-Process -FilePath $modelServer -ArgumentList $arguments -WindowStyle Hidden -PassThru -WorkingDirectory (Split-Path -Parent $modelServer) -RedirectStandardOutput (Join-Path $PSScriptRoot '.local/model.stdout.log') -RedirectStandardError (Join-Path $PSScriptRoot '.local/model.stderr.log')
[System.IO.File]::WriteAllText((Join-Path $PSScriptRoot '.local/model.pid'), [string]$modelProcess.Id)
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Milliseconds 500
    if ($modelProcess.HasExited) { throw 'Local model stopped. Inspect .local/model.stderr.log.' }
    try {
        $ready = Invoke-RestMethod -Uri 'http://127.0.0.1:8766/v1/models' -Headers $modelHeaders -TimeoutSec 1
        if ($ready.data.id -contains 'aqsha-local') { break }
    } catch { }
}
Write-Output ('Local CPU model started, PID ' + $modelProcess.Id + '. Status: http://127.0.0.1:8765/api/assistant/status')
