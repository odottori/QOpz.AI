param(
  [Parameter(Mandatory=$true)]
  [ValidateSet('api','ui')]
  [string]$Role
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot

if ($Role -eq 'api') {
  Write-Host '[QOPZ API] starting on 127.0.0.1:8765'
  $PythonExe = Join-Path $RepoRoot '.venv\Scripts\python.exe'
  if (-not (Test-Path $PythonExe)) {
    $PythonExe = 'py'
  }
  & $PythonExe -m uvicorn api.opz_api:app --host 127.0.0.1 --port 8765
  exit $LASTEXITCODE
}

Write-Host '[QOPZ UI] starting on 127.0.0.1:8173'
Set-Location (Join-Path $RepoRoot 'ui')
& npm.cmd run dev -- --host 127.0.0.1 --port 8173
exit $LASTEXITCODE
