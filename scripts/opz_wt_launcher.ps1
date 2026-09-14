param(
  [Parameter(Mandatory=$true)]
  [ValidateSet('start','stop')]
  [string]$Mode,
  [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$StateDir = Join-Path $RepoRoot 'logs'
$WtPidPath = Join-Path $StateDir 'opz_wt_pid.txt'
$ApiPort = 8765
$UiPort = 8173
$ApiUrl = 'http://127.0.0.1:8765/health'
$UiUrl = 'http://127.0.0.1:8173/'
$WindowName = 'qopz-ai'

function Write-StatePid([int]$Pid) {
  New-Item -ItemType Directory -Path $StateDir -Force | Out-Null
  Set-Content -LiteralPath $WtPidPath -Encoding ascii -Value ([string]$Pid)
}

function Remove-StatePid() {
  if (Test-Path -LiteralPath $WtPidPath) {
    Remove-Item -LiteralPath $WtPidPath -Force -ErrorAction SilentlyContinue
  }
}

function Get-ListeningPids([int]$Port) {
  $found = @()
  try {
    $conns = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    if ($conns) {
      $found = @($conns | Select-Object -ExpandProperty OwningProcess -Unique)
    }
  } catch {
  }
  if (-not $found -or $found.Count -eq 0) {
    try {
      $lines = netstat -ano -p tcp | Select-String (":$Port")
      foreach ($line in $lines) {
        if ($line.Line -match 'LISTENING\s+(\d+)\s*$') {
          $found += [int]$Matches[1]
        }
      }
    } catch {
    }
  }
  return @($found | Sort-Object -Unique)
}

function Stop-ProcessTree([int[]]$Pids) {
  $killed = 0
  foreach ($candidate in @($Pids | Sort-Object -Unique)) {
    if ($candidate -le 0) { continue }
    try {
      Stop-Process -Id $candidate -Force -ErrorAction Stop
      $killed += 1
    } catch {
    }
  }
  return $killed
}

function Test-PortOpen([int]$Port) {
  $client = New-Object System.Net.Sockets.TcpClient
  try {
    $iar = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
    $ok = $iar.AsyncWaitHandle.WaitOne(500)
    if (-not $ok) { return $false }
    $client.EndConnect($iar)
    return $true
  } catch {
    return $false
  } finally {
    $client.Close()
  }
}

function Wait-PortClosed([int]$Port, [double]$TimeoutSec) {
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  while ((Get-Date) -lt $deadline) {
    if (-not (Test-PortOpen -Port $Port)) { return $true }
    Start-Sleep -Milliseconds 250
  }
  return (-not (Test-PortOpen -Port $Port))
}

function Wait-HttpOk([string]$Url, [double]$TimeoutSec) {
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  while ((Get-Date) -lt $deadline) {
    try {
      $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2 -ErrorAction Stop
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
        return $true
      }
    } catch {
    }
    Start-Sleep -Milliseconds 500
  }
  return $false
}

function Stop-TerminalWindow() {
  $stopped = $false
  if (Test-Path -LiteralPath $WtPidPath) {
    try {
      $pidText = (Get-Content -LiteralPath $WtPidPath -Raw -ErrorAction Stop).Trim()
      if ($pidText) {
        $pidValue = [int]$pidText
        if ($pidValue -gt 0) {
          try {
            Stop-Process -Id $pidValue -Force -ErrorAction Stop
            $stopped = $true
          } catch {
          }
        }
      }
    } catch {
    }
  }
  Remove-StatePid
  return $stopped
}

function Resolve-PythonExe() {
  $venvPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
  if (Test-Path -LiteralPath $venvPython) {
    return $venvPython
  }
  return 'py'
}

function Resolve-WtExe() {
  $wtCmd = Get-Command wt.exe -ErrorAction SilentlyContinue
  if (-not $wtCmd) { $wtCmd = Get-Command wt -ErrorAction SilentlyContinue }
  if (-not $wtCmd) {
    throw 'wt.exe not found in PATH'
  }
  return $wtCmd.Source
}

function Build-ApiPaneCommand() {
  $pythonExe = Resolve-PythonExe
  $repoEsc = $RepoRoot.Replace("'", "''")
  $pyEsc = $pythonExe.Replace("'", "''")
  return "Set-Location -LiteralPath '$repoEsc'; & '$pyEsc' -m uvicorn api.opz_api:app --host 127.0.0.1 --port 8765"
}

function Build-UiPaneCommand() {
  $uiDir = (Join-Path $RepoRoot 'ui').Replace("'", "''")
  return "Set-Location -LiteralPath '$uiDir'; & npm.cmd run dev -- --host 127.0.0.1 --port 8173"
}

function Start-TerminalWindow() {
  $wtExe = Resolve-WtExe
  $uiDir = Join-Path $RepoRoot 'ui'
  $argList = @(
    '-w', $WindowName,
    'new-tab', '--title', 'QOPZ API', '--startingDirectory', $RepoRoot,
    'powershell.exe', '-NoLogo', '-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', (Build-ApiPaneCommand),
    ';',
    'split-pane', '-H', '--title', 'QOPZ UI', '--startingDirectory', $uiDir,
    'powershell.exe', '-NoLogo', '-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', (Build-UiPaneCommand)
  )
  $proc = Start-Process -FilePath $wtExe -ArgumentList $argList -PassThru
  if ($proc -and $proc.Id) {
    Write-StatePid -Pid $proc.Id
  }
}

function Invoke-StopCore() {
  $killed = 0
  $killed += Stop-ProcessTree -Pids (Get-ListeningPids -Port $ApiPort)
  $killed += Stop-ProcessTree -Pids (Get-ListeningPids -Port $UiPort)
  [void](Wait-PortClosed -Port $ApiPort -TimeoutSec 5)
  [void](Wait-PortClosed -Port $UiPort -TimeoutSec 5)
  $windowClosed = Stop-TerminalWindow
  $apiOpen = Test-PortOpen -Port $ApiPort
  $uiOpen = Test-PortOpen -Port $UiPort
  Write-Output ("LAUNCHER_STOP killed_count={0} api_open={1} ui_open={2} window_closed={3}" -f $killed, $apiOpen, $uiOpen, $windowClosed)
  if ($apiOpen -or $uiOpen) {
    return 3
  }
  return 0
}

if ($Mode -eq 'stop') {
  exit (Invoke-StopCore)
}

$stopRc = Invoke-StopCore
if ($stopRc -ne 0 -and $stopRc -ne 3) {
  exit $stopRc
}

Start-TerminalWindow
Write-Output ("LAUNCHER_START mode=wt window={0} layout=split" -f $WindowName)

if (-not (Wait-HttpOk -Url $ApiUrl -TimeoutSec 25)) {
  Write-Output ("LAUNCHER_FAIL api health timeout url={0}" -f $ApiUrl)
  exit 10
}
Write-Output ("LAUNCHER_OK api url={0}" -f $ApiUrl)

if (-not (Wait-HttpOk -Url $UiUrl -TimeoutSec 35)) {
  Write-Output ("LAUNCHER_FAIL ui readiness timeout url={0}" -f $UiUrl)
  exit 11
}
Write-Output ("LAUNCHER_OK ui url={0}" -f $UiUrl)
exit 0
