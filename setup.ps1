param(
    [ValidateNotNullOrEmpty()][string]$VenvDir = '.venv',
    [string]$Wheelhouse = '',
    [string]$PythonPath
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskRequirements = Join-Path $PSScriptRoot 'requirements.txt'

function Test-TaskPython {
    param([string]$Executable, [string[]]$PrefixArguments = @())
    try {
        & $Executable @PrefixArguments -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

try {
    $taskEnvironmentPath = $VenvDir
    if (-not [System.IO.Path]::IsPathRooted($taskEnvironmentPath)) {
        $taskEnvironmentPath = Join-Path $PSScriptRoot $taskEnvironmentPath
    }
    $taskEnvironment = [System.IO.Path]::GetFullPath($taskEnvironmentPath)
    $taskPython = Join-Path $taskEnvironment 'Scripts\python.exe'
    $taskWheels = $null
    if ($Wheelhouse) {
        if (-not (Test-Path -LiteralPath $Wheelhouse -PathType Container)) {
            throw "Wheelhouse directory not found: $Wheelhouse"
        }
        $taskWheels = (Resolve-Path -LiteralPath $Wheelhouse).Path
    }

    $taskBasePython = $null
    $taskBaseArguments = @()
    if ($PythonPath) {
        if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
            throw "Python executable not found: $PythonPath"
        }
        $taskBasePython = (Resolve-Path -LiteralPath $PythonPath).Path
        if (-not (Test-TaskPython -Executable $taskBasePython)) {
            throw '-PythonPath must point to a working Python 3.12 or newer executable.'
        }
    }

    if (-not (Test-Path -LiteralPath $taskPython -PathType Leaf)) {
        if (-not $taskBasePython) {
            foreach ($taskCommandName in @('python', 'python3', 'py')) {
                $taskCommand = Get-Command $taskCommandName -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
                if (-not $taskCommand) { continue }
                # Windows Store aliases are not an installed Python runtime.
                if ($taskCommand.Source -match '\\Microsoft\\WindowsApps\\') { continue }
                $taskCandidateArguments = @()
                if ($taskCommandName -eq 'py') { $taskCandidateArguments = @('-3') }
                if (Test-TaskPython -Executable $taskCommand.Source -PrefixArguments $taskCandidateArguments) {
                    $taskBasePython = $taskCommand.Source
                    $taskBaseArguments = $taskCandidateArguments
                    break
                }
            }
        }
        if (-not $taskBasePython) {
            throw 'Python 3.12 or newer is required. Install Python with venv support, then rerun setup.ps1, or pass -PythonPath "C:\path\to\python.exe". No Python installation or system settings were changed.'
        }
        & $taskBasePython @taskBaseArguments -m venv $taskEnvironment
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } else {
        Write-Host "Reusing the existing environment: $taskEnvironment"
        if ($PythonPath) { Write-Host '-PythonPath is used only when creating a new environment.' }
    }
    if (-not (Test-TaskPython -Executable $taskPython)) {
        throw "The existing environment cannot run Python 3.12 or newer: $taskEnvironment. Recreate it with a working Python installation, then run setup.ps1 again."
    }

    # A satisfied, pinned environment needs no network access or reinstallation.
    $taskDependencyCheck = @'
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import sys

missing = []
for raw in Path(sys.argv[1]).read_text(encoding='utf-8-sig').splitlines():
    line = raw.strip()
    if not line or line.startswith('#'):
        continue
    name, separator, expected = line.partition('==')
    try:
        satisfied = bool(separator) and version(name) == expected
    except PackageNotFoundError:
        satisfied = False
    if not satisfied:
        missing.append(line)
if missing:
    print(f'Dependencies to install or update: {len(missing)}')
sys.exit(1 if missing else 0)
'@
    & $taskPython -c $taskDependencyCheck $taskRequirements
    if ($LASTEXITCODE -ne 0) {
        $taskInstallArgs = @('-m', 'pip', 'install', '--disable-pip-version-check', '-r', $taskRequirements)
        if ($taskWheels) {
            $taskInstallArgs += @('--no-index', '--find-links', $taskWheels)
        }
        & $taskPython @taskInstallArgs
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } else {
        Write-Host 'All pinned dependencies are already installed.'
    }
    & $taskPython -m pip check
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "Environment ready: $taskEnvironment"
    exit 0
} catch {
    Write-Host "Setup failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
