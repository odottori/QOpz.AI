param()
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$id = Get-Date -Format 'yyyyMMdd-HHmmss'
$copy = Join-Path $repo ".tmp\protected-$id"
$venv = Join-Path $repo '.venv_protected'
$log = Join-Path $repo "logs\protected-$id.log"
if (-not (Test-Path "$venv\Scripts\python.exe")) {
  throw 'Run py tools/opz_env_setup.py --venv-name .venv_protected --only all first.'
}
New-Item -ItemType Directory -Force (Split-Path -Parent $copy) | Out-Null
& git clone --quiet --no-hardlinks $repo $copy
if ($LASTEXITCODE -ne 0) { throw 'Cannot create isolated source checkout' }
# Copy only source changes, never runtime DBs, logs, secrets or node_modules.
$files = @(& git -C $repo diff --name-only HEAD)
$files += @(& git -C $repo ls-files --others --exclude-standard)
$files += @('planner/active_step.json', 'planner/maintenance_steps.json')
foreach ($rel in ($files | Sort-Object -Unique)) {
  $source = Join-Path $repo $rel
  $target = Join-Path $copy $rel
  if (Test-Path -LiteralPath $source -PathType Leaf) {
    New-Item -ItemType Directory -Force (Split-Path -Parent $target) | Out-Null
    Copy-Item -LiteralPath $source -Destination $target -Force
  } elseif (Test-Path -LiteralPath $target -PathType Leaf) {
    Remove-Item -LiteralPath $target
  }
}
# Isolate dependencies too: validation must not update the operator's venv.
Copy-Item -LiteralPath $venv -Destination (Join-Path $copy '.venv_protected') -Recurse
& git -C $copy add --all
if ($LASTEXITCODE -ne 0) { throw 'Cannot stage isolated source for real index scope check' }
Push-Location $copy
try {
  & cmd.exe /d /c "py tools/opz_protected_validate.py --setup --skip-vm-sync > `"$log`" 2>&1"
  $rc = $LASTEXITCODE
} finally { Pop-Location }
Get-Content $log -Tail 35
Write-Output "ISOLATED_VALIDATION rc=$rc source=$copy log=$log"
exit $rc
