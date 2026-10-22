param()
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$controller = Join-Path $repo 'scripts\opz_local.ps1'
$temp = Join-Path $repo ('.tmp\lifecycle-' + [guid]::NewGuid().ToString('N'))
$foreign = $null
$checks = @()
New-Item -ItemType Directory -Force "$temp\scripts", "$temp\ui\dist", "$temp\ui\node_modules\vite\bin" | Out-Null
Copy-Item -LiteralPath $controller -Destination "$temp\scripts\opz_local.ps1"
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'opz_spawn_detached.py') -Destination "$temp\scripts\opz_spawn_detached.py"
$builder = @'
const fs = require('fs');
const path = require('path');
const root = __dirname;
const mode = fs.readFileSync(path.join(root, 'build-mode'), 'utf8').trim();
if (mode === 'fail') process.exit(9);
if (mode === 'hang') {
  fs.writeFileSync(path.join(root, 'hang-child.pid'), String(process.pid));
  setInterval(() => {}, 1000);
} else {
  const output = process.argv[process.argv.indexOf('--outDir') + 1];
  fs.mkdirSync(path.join(output, 'assets'), {recursive:true});
  fs.writeFileSync(path.join(output, 'index.html'), '<html><script src="/assets/app.js"></script></html>');
  fs.writeFileSync(path.join(output, 'assets/app.js'), 'version-' + mode);
}
'@
$preview = @'
const fs = require('fs');
const path = require('path');
const http = require('http');
const root = process.argv[3];
const marker = path.join(root, 'fail-next-preview');
if (fs.existsSync(marker)) {
  fs.unlinkSync(marker);
  fs.writeFileSync(path.join(root, 'preview-failure-observed'), 'yes');
  process.exit(13);
}
const port = Number(process.argv[process.argv.indexOf('--port') + 1]);
http.createServer((req, res) => {
  const name = req.url === '/' ? 'index.html' : req.url.replace(/^\//, '');
  const file = path.join(root, 'dist', name);
  try { res.end(fs.readFileSync(file)); } catch { res.writeHead(404); res.end('missing'); }
}).listen(port, '127.0.0.1');
'@
[IO.File]::WriteAllText("$temp\ui\build.cjs", $builder)
[IO.File]::WriteAllText("$temp\ui\node_modules\vite\bin\vite.js", $preview)
@{ scripts=@{build='node build.cjs'} } | ConvertTo-Json | Set-Content -Encoding UTF8 "$temp\ui\package.json"

function Expected-Failure([string]$file, [string]$options, [string]$log) {
  & cmd.exe /d /c "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$file`" $options > `"$log`" 2>&1"
  return $LASTEXITCODE
}
function Assert-True($condition, [string]$message) {
  if (-not $condition) { throw $message }
  $script:checks += $message
  Write-Output "PASS $message"
}

try {
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $controller -Action stop
  if ($LASTEXITCODE -ne 0) { throw 'Cannot stop existing owned session' }
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $controller -Action stop
  Assert-True ($LASTEXITCODE -eq 0) 'second stop is harmless'
  [IO.File]::WriteAllText("$temp\health", '{"status":"ok"}')
  $foreign = Start-Process -FilePath "$repo\.venv\Scripts\python.exe" -ArgumentList "-m http.server 8765 --bind 127.0.0.1 --directory `"$temp`"" `
    -PassThru -WindowStyle Hidden -RedirectStandardOutput "$temp\foreign.log" -RedirectStandardError "$temp\foreign.err"
  $identity = Get-Process -Id $foreign.Id
  $ticks = $identity.StartTime.ToUniversalTime().Ticks.ToString()
  $deadline = (Get-Date).AddSeconds(15)
  do {
    & curl.exe --noproxy '*' -fsS --max-time 1 http://127.0.0.1:8765/health > $null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Milliseconds 200
  } while ((Get-Date) -lt $deadline)
  Assert-True ($LASTEXITCODE -eq 0) 'foreign server deliberately mimics healthy API'
  $watch = [Diagnostics.Stopwatch]::StartNew()
  $rc = Expected-Failure $controller '-Action start' "$temp\conflict.log"
  Assert-True ($rc -ne 0 -and $watch.Elapsed.TotalSeconds -lt 25) 'healthy foreign listener rejected within bounded time'
  $state = @{ api = @{ pid=$foreign.Id; startTicks='1'; executable=$identity.Path } }
  $state | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 "$repo\logs\local\processes.json"
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $controller -Action stop
  Assert-True ((Get-Process -Id $foreign.Id).StartTime.ToUniversalTime().Ticks.ToString() -eq $ticks) 'stale PID identity cannot terminate foreign process'
  & taskkill.exe /PID $foreign.Id /T /F | Out-Null
  $foreign = $null

  [IO.File]::WriteAllText("$temp\ui\dist\index.html", 'previous-build-sentinel')
  [IO.File]::WriteAllText("$temp\ui\build-mode", 'fail')
  $rc = Expected-Failure "$temp\scripts\opz_local.ps1" '-Action start -Role ui' "$temp\build-failed.log"
  Assert-True ($rc -ne 0 -and [IO.File]::ReadAllText("$temp\ui\dist\index.html") -eq 'previous-build-sentinel' -and
    (Get-Content "$temp\build-failed.log" -Raw).Contains('UI build failed (9)')) 'failed build preserves previous dist and reports exact build failure'
  [IO.File]::WriteAllText("$temp\ui\build-mode", 'hang')
  $watch.Restart()
  $rc = Expected-Failure "$temp\scripts\opz_local.ps1" '-Action start -Role ui -BuildTimeoutSec 2' "$temp\build-timeout.log"
  Assert-True ($rc -ne 0 -and $watch.Elapsed.TotalSeconds -ge 2 -and $watch.Elapsed.TotalSeconds -lt 25 -and
    (Get-Content "$temp\build-timeout.log" -Raw).Contains('UI build exceeded 2 seconds')) 'genuinely hung build reaches the configured timeout'
  $childId = [int][IO.File]::ReadAllText("$temp\ui\hang-child.pid")
  Assert-True (-not (Get-Process -Id $childId -ErrorAction SilentlyContinue)) 'timed out build leaves no fixture node child'

  [IO.File]::WriteAllText("$temp\ui\build-mode", '1')
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$temp\scripts\opz_local.ps1" -Action start -Role ui
  Assert-True ($LASTEXITCODE -eq 0) 'lock reacquired after timeout and fixture UI starts'
  Remove-Item -LiteralPath "$temp\ui\dist\assets\app.js"
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$temp\scripts\opz_local.ps1" -Action start -Role ui
  Assert-True ($LASTEXITCODE -eq 0 -and [IO.File]::ReadAllText("$temp\ui\dist\assets\app.js") -eq 'version-1') 'missing asset repaired even when index is unchanged'
  [IO.File]::WriteAllText("$temp\ui\dist\assets\app.js", 'corrupted')
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$temp\scripts\opz_local.ps1" -Action start -Role ui
  Assert-True ($LASTEXITCODE -eq 0 -and [IO.File]::ReadAllText("$temp\ui\dist\assets\app.js") -eq 'version-1') 'corrupt asset repaired even when index is unchanged'
  [IO.File]::WriteAllText("$temp\ui\build-mode", '2')
  [IO.File]::WriteAllText("$temp\ui\fail-next-preview", 'fail once')
  $rc = Expected-Failure "$temp\scripts\opz_local.ps1" '-Action start -Role ui' "$temp\publish-rollback.log"
  Assert-True ($rc -ne 0 -and (Test-Path "$temp\ui\preview-failure-observed") -and
    [IO.File]::ReadAllText("$temp\ui\dist\assets\app.js") -eq 'version-1' -and
    (Get-Content "$temp\publish-rollback.log" -Raw).Contains('UI_ROLLBACK restored previous build')) 'startup failure after directory swap restores previous UI'
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$temp\scripts\opz_local.ps1" -Action status -Role ui
  Assert-True ($LASTEXITCODE -eq 0) 'restored previous UI is actually serving HTTP'
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$temp\scripts\opz_local.ps1" -Action stop -Role ui

  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $controller -Action start
  Assert-True ($LASTEXITCODE -eq 0) 'normal start succeeds after negative cases'
  $before = Get-Content "$repo\logs\local\processes.json" -Raw | ConvertFrom-Json
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $controller -Action start
  $after = Get-Content "$repo\logs\local\processes.json" -Raw | ConvertFrom-Json
  Assert-True ($LASTEXITCODE -eq 0 -and $before.api.pid -eq $after.api.pid -and $before.ui.pid -eq $after.ui.pid) 'repeated start reuses both identities'
  $argsLine = "-NoProfile -ExecutionPolicy Bypass -File `"$controller`" -Action start"
  $first = Start-Process powershell.exe -ArgumentList $argsLine -PassThru -WindowStyle Hidden -RedirectStandardOutput "$temp\first.log" -RedirectStandardError "$temp\first.err"
  $null = $first.Handle
  $second = Start-Process powershell.exe -ArgumentList $argsLine -PassThru -WindowStyle Hidden -RedirectStandardOutput "$temp\second.log" -RedirectStandardError "$temp\second.err"
  $null = $second.Handle
  Assert-True ($first.WaitForExit(120000) -and $second.WaitForExit(120000)) 'concurrent invocations finish within limit'
  Assert-True (@(@($first.ExitCode,$second.ExitCode) | Where-Object { $_ -eq 0 }).Count -eq 1) 'exactly one concurrent start succeeds'
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $controller -Action status
  Assert-True ($LASTEXITCODE -eq 0) 'final API and UI remain ready'
} finally {
  if ($foreign) {
    $p = Get-Process -Id $foreign.Id -ErrorAction SilentlyContinue
    if ($p -and $p.StartTime.ToUniversalTime().Ticks.ToString() -eq $ticks) { & taskkill.exe /PID $p.Id /T /F | Out-Null }
  }
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$temp\scripts\opz_local.ps1" -Action stop -Role ui
  $report = @{timestamp=(Get-Date).ToUniversalTime().ToString('o'); checks=$checks; evidence=$temp}
  $report | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 "$repo\logs\local-lifecycle.json"
}
