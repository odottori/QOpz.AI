param(
  [int]$Pid = 0,
  [string]$Role = "",
  [string]$Owner = ""
)

$repo = Split-Path -Parent $PSScriptRoot
$regPath = Join-Path $repo "logs\codex_process_registry.json"
if(-not (Test-Path $regPath)){
  Write-Output "TRACKED_STOP no registry"
  exit 0
}

if([string]::IsNullOrWhiteSpace($Owner)){
  $Owner = $env:OPZ_AGENT_OWNER
}
if([string]::IsNullOrWhiteSpace($Owner)){
  $Owner = "assistant"
}

try {
  $data = Get-Content $regPath -Raw | ConvertFrom-Json
} catch {
  Write-Error "invalid registry json"
  exit 1
}

$entries = @($data.entries)
$entries = @($entries | Where-Object { [string]$_.owner -eq $Owner })
if($Pid -gt 0){
  $entries = @($entries | Where-Object { [int]$_.pid -eq $Pid })
}
if(-not [string]::IsNullOrWhiteSpace($Role)){
  $entries = @($entries | Where-Object { [string]$_.role -eq $Role })
}

$stopped = 0
foreach($e in $entries){
  $id = [int]$e.pid
  if($id -le 0){ continue }
  try {
    Stop-Process -Id $id -Force -ErrorAction Stop
    & py "$repo\scripts\opz_process_registry.py" unregister --owner $Owner --pid $id | Out-Null
    $stopped += 1
    Write-Output "TRACKED_STOP owner=$Owner pid=$id role=$($e.role)"
  } catch {
    Write-Output "TRACKED_STOP_SKIP owner=$Owner pid=$id reason=$($_.Exception.Message)"
  }
}

Write-Output "TRACKED_STOP_DONE owner=$Owner count=$stopped"
