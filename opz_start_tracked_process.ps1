param(
  [Parameter(Mandatory=$true)][string]$FilePath,
  [string[]]$ArgumentList = @(),
  [string]$Role = "generic",
  [string]$WorkingDirectory = "",
  [string]$Owner = "",
  [string]$StdoutPath = "",
  [string]$StderrPath = ""
)

$repo = Split-Path -Parent $PSScriptRoot
if([string]::IsNullOrWhiteSpace($WorkingDirectory)){ $WorkingDirectory = $repo }
if([string]::IsNullOrWhiteSpace($Owner)){
  $Owner = $env:OPZ_AGENT_OWNER
}
if([string]::IsNullOrWhiteSpace($Owner)){
  $Owner = "assistant"
}

$repoPython = Join-Path $repo ".venv\Scripts\python.exe"
$registryPython = if(Test-Path $repoPython){ $repoPython } else { "py" }

$psi = @{
  FilePath = $FilePath
  ArgumentList = $ArgumentList
  WorkingDirectory = $WorkingDirectory
  PassThru = $true
}
if(-not [string]::IsNullOrWhiteSpace($StdoutPath)){
  $stdoutDir = Split-Path -Parent $StdoutPath
  if(-not [string]::IsNullOrWhiteSpace($stdoutDir)){
    New-Item -ItemType Directory -Force -Path $stdoutDir | Out-Null
  }
  $psi.RedirectStandardOutput = $StdoutPath
}
if(-not [string]::IsNullOrWhiteSpace($StderrPath)){
  $stderrDir = Split-Path -Parent $StderrPath
  if(-not [string]::IsNullOrWhiteSpace($stderrDir)){
    New-Item -ItemType Directory -Force -Path $stderrDir | Out-Null
  }
  $psi.RedirectStandardError = $StderrPath
}
$p = Start-Process @psi
if(-not $p){
  Write-Error "failed to start process"
  exit 1
}

$cmd = "$FilePath " + ($ArgumentList -join " ")
& $registryPython "$repo\scripts\opz_process_registry.py" register --owner $Owner --pid $p.Id --role $Role --command $cmd --cwd $WorkingDirectory --note "started via opz_start_tracked_process.ps1"
if($LASTEXITCODE -ne 0){
  Write-Warning "process started but registry update failed pid=$($p.Id)"
}

Write-Output "TRACKED_START owner=$Owner pid=$($p.Id) role=$Role file=$FilePath"
