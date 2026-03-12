param(
  [Parameter(Mandatory = $true)][string]$Url,
  [Parameter(Mandatory = $true)][string]$TitleHint,
  [Parameter(Mandatory = $true)][string]$EdgeExe,
  [Parameter(Mandatory = $true)][string]$ProfileDir,
  [switch]$SingletonStrict
)

$ErrorActionPreference = 'SilentlyContinue'

if (-not (Test-Path -LiteralPath $EdgeExe)) {
  Start-Process $Url | Out-Null
  exit 0
}

$all = @(Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" |
  Where-Object {
    $_.CommandLine -and
    $_.CommandLine -like "*$ProfileDir*" -and
    $_.CommandLine -like "*--app=*" -and
    $_.CommandLine -like "*$Url*"
  })

if ($SingletonStrict -and $all.Count -gt 1) {
  $keep = $all[0].ProcessId
  $all | Where-Object { $_.ProcessId -ne $keep } | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  }
  Start-Sleep -Milliseconds 180
  $all = @(Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" |
    Where-Object {
      $_.CommandLine -and
      $_.CommandLine -like "*$ProfileDir*" -and
      $_.CommandLine -like "*--app=*" -and
      $_.CommandLine -like "*$Url*"
    })
}

$ws = New-Object -ComObject WScript.Shell
if ($all.Count -ge 1 -and $ws.AppActivate($TitleHint)) {
  Start-Sleep -Milliseconds 150
  $ws.SendKeys('^r')
  exit 0
}

if ($SingletonStrict -and $all.Count -ge 1) {
  $all | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  }
  Start-Sleep -Milliseconds 180
}

New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null
Start-Process -FilePath $EdgeExe -ArgumentList @(
  "--user-data-dir=$ProfileDir",
  '--new-window',
  "--app=$Url"
) | Out-Null

exit 0
