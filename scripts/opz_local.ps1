param(
  [ValidateSet('start', 'stop', 'status')][string]$Action = 'start',
  [ValidateSet('all', 'api', 'ui')][string]$Role = 'all',
  [ValidateRange(1, 300)][int]$BuildTimeoutSec = 180
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $repo 'logs\local'
$statePath = Join-Path $logDir 'processes.json'
New-Item -ItemType Directory -Force $logDir | Out-Null
$lock = $null
$started = @()
$state = @{}
$stage = $null
$previousBuild = $null
$restoreUi = $false

function Remove-Stage {
  if (-not $script:stage -or -not (Test-Path -LiteralPath $script:stage)) { return }
  $full = [IO.Path]::GetFullPath($script:stage)
  $ui = [IO.Path]::GetFullPath((Join-Path $repo 'ui')) + [IO.Path]::DirectorySeparatorChar
  if (-not $full.StartsWith($ui, [StringComparison]::OrdinalIgnoreCase) -or
      (Split-Path -Leaf $full) -notmatch '^\.opz-build-[a-f0-9]+$') { throw 'Unsafe build cleanup path' }
  if ((Get-Item -LiteralPath $full).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Build stage must not be a link' }
  Remove-Item -LiteralPath $full -Recurse -Force
}

function Save-State {
  $tmp = "$statePath.tmp"
  $script:state | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $tmp
  Move-Item -LiteralPath $tmp -Destination $statePath -Force
}

function Get-BuildHash([string]$directory) {
  $hash = [Security.Cryptography.SHA256]::Create()
  try {
    $rows = @(Get-ChildItem -LiteralPath $directory -File -Recurse | Sort-Object FullName | ForEach-Object {
      $_.FullName.Substring($directory.Length) + ':' + [BitConverter]::ToString($hash.ComputeHash([IO.File]::ReadAllBytes($_.FullName)))
    })
    return [BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes(($rows -join "`n"))))
  } finally { $hash.Dispose() }
}

function Get-ApiSourceHash {
  $hash = [Security.Cryptography.SHA256]::Create()
  try {
    $files = @()
    foreach ($directory in @('api', 'execution', 'strategy', 'scripts', 'tools', 'config')) {
      $files += @(Get-ChildItem -LiteralPath (Join-Path $repo $directory) -File -Recurse | Where-Object { $_.Extension -in @('.py', '.toml') })
    }
    $files += @(Get-ChildItem -LiteralPath $repo -Filter 'requirements*.txt' -File)
    $rows = @($files | Sort-Object FullName | ForEach-Object {
      $_.FullName.Substring($repo.Length) + ':' + [BitConverter]::ToString($hash.ComputeHash([IO.File]::ReadAllBytes($_.FullName)))
    })
    return [BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes(($rows -join "`n"))))
  } finally { $hash.Dispose() }
}

function Get-OwnedProcess([string]$name) {
  $entry = $script:state[$name]
  if (-not $entry) { return $null }
  $proc = Get-Process -Id ([int]$entry.pid) -ErrorAction SilentlyContinue
  if (-not $proc) { return $null }
  # PID alone is unsafe: Windows can reuse it for an unrelated application.
  if ($proc.StartTime.ToUniversalTime().Ticks.ToString() -ne [string]$entry.startTicks) { return $null }
  if ($proc.Path -ne [string]$entry.executable) { return $null }
  return $proc
}

function Stop-Owned([string]$name) {
  $proc = Get-OwnedProcess $name
  if ($proc) {
    & taskkill.exe /PID $proc.Id /T /F | Out-Null
    if ($LASTEXITCODE -ne 0 -and (Get-OwnedProcess $name)) { throw "Cannot stop owned $name process" }
    $proc.WaitForExit(10000) | Out-Null
    Write-Output "STOP $name pid=$($proc.Id)"
  }
  $script:state.Remove($name)
  Save-State
}

function Get-Listener([int]$port) {
  # Avoid Test-NetConnection's slow ICMP fallback and never kill by port.
  return @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
}

function Test-ListenerOwned([string]$name, [int]$port) {
  $proc = Get-OwnedProcess $name
  if (-not $proc) { return $false }
  $ids = @($proc.Id)
  # A Windows venv python launcher may own the actual interpreter as a child.
  $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$($proc.Id)")
  $ids += @($children | ForEach-Object { [int]$_.ProcessId })
  $listeners = @(Get-Listener $port)
  return ($listeners.Count -gt 0 -and @($listeners | Where-Object { $_.OwningProcess -notin $ids }).Count -eq 0)
}

function Test-Ready([string]$name, [int]$port) {
  if (-not (Test-ListenerOwned $name $port)) { return $false }
  try {
    $path = if ($name -eq 'api') { '/health' } else { '/' }
    $content = & curl.exe --noproxy '*' --fail --silent --max-time 3 "http://127.0.0.1:$port$path"
    if ($LASTEXITCODE -ne 0) { return $false }
    $body = $content -join "`n"
    if ($name -eq 'api') { return (($body | ConvertFrom-Json).status -eq 'ok') }
    $expected = Get-Content (Join-Path $repo 'ui\dist\index.html') -Raw
    return (($body -replace '\s', '') -eq ($expected -replace '\s', ''))
  } catch { return $false }
}

function Start-Owned([string]$name, [int]$port, [string]$exe, [string]$arguments, [string]$sourceHash = '') {
  if ((Test-Ready $name $port) -and (-not $sourceHash -or $script:state[$name].sourceHash -eq $sourceHash)) {
    Write-Output "READY $name (reused verified process)"
    return
  }
  if (@(Get-Listener $port).Count -gt 0 -and -not (Test-ListenerOwned $name $port)) {
    throw "Port $port is occupied by an unowned process. Nothing was stopped."
  }
  Stop-Owned $name
  $request = Join-Path $logDir ('spawn-' + [guid]::NewGuid().ToString('N') + '.json')
  @{executable=$exe; arguments=$arguments; cwd=$repo; stdout=(Join-Path $logDir "$name.stdout.log"); stderr=(Join-Path $logDir "$name.stderr.log")} | ConvertTo-Json | Set-Content -Encoding UTF8 $request
  $bootstrap = Join-Path $repo '.venv\Scripts\python.exe'
  if (-not (Test-Path $bootstrap)) { $bootstrap = 'py' }
  try {
    $childId = & $bootstrap (Join-Path $PSScriptRoot 'opz_spawn_detached.py') $request
    if ($LASTEXITCODE -ne 0) { throw "$name process creation failed" }
    $p = Get-Process -Id ([int]$childId)
  } finally { Remove-Item -LiteralPath $request -Force }
  $script:started += $name
  $identity = Get-Process -Id $p.Id
  $script:state[$name] = @{ pid = $p.Id; startTicks = $identity.StartTime.ToUniversalTime().Ticks.ToString(); executable = $exe; sourceHash = $sourceHash }
  Save-State
  $deadline = (Get-Date).AddSeconds(60)
  while ((Get-Date) -lt $deadline) {
    if (-not (Get-OwnedProcess $name)) { throw "$name exited during startup. See $logDir\$name.stderr.log" }
    if (Test-Ready $name $port) { Write-Output "READY $name pid=$($p.Id)"; return }
    Start-Sleep -Milliseconds 350
  }
  throw "$name readiness timeout. See $logDir\$name.stderr.log"
}

try {
  $lock = [IO.File]::Open((Join-Path $logDir 'launcher.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
  if (Test-Path $statePath) {
    $loaded = Get-Content $statePath -Raw | ConvertFrom-Json
    foreach ($property in $loaded.PSObject.Properties) { $state[$property.Name] = $property.Value }
  }
  $roles = if ($Role -eq 'all') { @('api', 'ui') } else { @($Role) }
  if ($Action -eq 'stop') {
    foreach ($name in $roles) { Stop-Owned $name }
  } elseif ($Action -eq 'status') {
    foreach ($name in $roles) {
      $port = if ($name -eq 'api') { 8765 } else { 8173 }
      if (-not (Test-Ready $name $port)) { throw "$name is not ready (or is not owned by this launcher)" }
      if ($name -eq 'api' -and $state[$name].sourceHash -ne (Get-ApiSourceHash)) { throw 'API source changed; rerun QOPZ_START.bat to reload it' }
      Write-Output "READY $name http://127.0.0.1:$port/"
    }
  } else {
    foreach ($name in $roles) {
      $port = if ($name -eq 'api') { 8765 } else { 8173 }
      if (@(Get-Listener $port).Count -gt 0 -and -not (Test-ListenerOwned $name $port)) {
        throw "Port $port is occupied by an unowned process. Nothing was stopped."
      }
    }
    if ('ui' -in $roles) {
      $node = (Get-Command node.exe -ErrorAction Stop).Source
      $npm = (Get-Command npm.cmd -ErrorAction Stop).Source
      # Never serve a stale fallback build. Preserve errors and fail the launcher.
      $env:VITE_BASE_PATH = '/'
      $env:VITE_API_BASE = '/'
      $uiRoot = Join-Path $repo 'ui'
      $stage = Join-Path $uiRoot ('.opz-build-' + [guid]::NewGuid().ToString('N'))
      $buildArgs = '/d /s /c ""{0}" run build -- --outDir "{1}""' -f $npm, $stage
      $build = Start-Process -FilePath $env:ComSpec -ArgumentList $buildArgs -WorkingDirectory $uiRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logDir 'ui-build.log') -RedirectStandardError (Join-Path $logDir 'ui-build.stderr.log')
      $null = $build.Handle
      if (-not $build.WaitForExit($BuildTimeoutSec * 1000)) {
        & taskkill.exe /PID $build.Id /T /F | Out-Null
        throw "UI build exceeded $BuildTimeoutSec seconds; owned build process tree stopped."
      }
      $buildRc = $build.ExitCode
      if ($buildRc -ne 0) { throw "UI build failed ($buildRc). See $logDir\ui-build.log" }
      $index = Join-Path $stage 'index.html'
      if (-not (Test-Path $index)) { throw 'Build produced no index.html' }
      $dist = Join-Path $uiRoot 'dist'
      $oldIndex = Join-Path $dist 'index.html'
      $changed = -not (Test-Path $oldIndex)
      if (-not $changed) { $changed = (Get-BuildHash $stage) -ne (Get-BuildHash $dist) }
      if ($changed) {
        $restoreUi = Test-Ready 'ui' 8173
        Stop-Owned 'ui'
        if (Test-Path $dist) {
          $previousBuild = Join-Path $logDir ('ui-previous-' + [guid]::NewGuid().ToString('N'))
          Move-Item -LiteralPath $dist -Destination $previousBuild
        }
        Move-Item -LiteralPath $stage -Destination $dist
      }
      Remove-Stage
    }
    if ('api' -in $roles) {
      $python = Join-Path $repo '.venv\Scripts\python.exe'
      if (-not (Test-Path $python)) { throw 'Missing .venv. Run py tools/opz_env_setup.py --venv-name .venv --only all' }
      Start-Owned 'api' 8765 $python '-m uvicorn api.opz_api:app --host 127.0.0.1 --port 8765 --no-use-colors' (Get-ApiSourceHash)
    }
    if ('ui' -in $roles) {
      $vite = Join-Path $repo 'ui\node_modules\vite\bin\vite.js'
      $uiRoot = Join-Path $repo 'ui'
      Start-Owned 'ui' 8173 $node "`"$vite`" preview `"$uiRoot`" --host 127.0.0.1 --port 8173 --strictPort"
    }
    Write-Output 'STARTUP OK - UI http://127.0.0.1:8173/ - API http://127.0.0.1:8765/health'
  }
} catch {
  $failure = $_
  foreach ($name in $started) { try { Stop-Owned $name } catch { Write-Warning $_ } }
  if ($previousBuild -and (Test-Path $previousBuild)) {
    try {
      $dist = Join-Path $repo 'ui\dist'
      if (Test-Path $dist) { Move-Item -LiteralPath $dist -Destination (Join-Path $logDir ('ui-failed-' + [guid]::NewGuid().ToString('N'))) }
      Move-Item -LiteralPath $previousBuild -Destination $dist
      if ($restoreUi) {
        $vite = Join-Path $repo 'ui\node_modules\vite\bin\vite.js'
        Start-Owned 'ui' 8173 $node "`"$vite`" preview `"$uiRoot`" --host 127.0.0.1 --port 8173 --strictPort"
      }
      Write-Output 'UI_ROLLBACK restored previous build'
    } catch { Write-Warning "Previous UI restore failed: $_" }
  }
  Write-Error $failure -ErrorAction Continue
  exit 1
} finally {
  try { Remove-Stage } catch { Write-Warning $_ }
  if ($lock) { $lock.Dispose() }
}
