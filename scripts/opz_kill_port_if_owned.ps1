param(
  [Parameter(Mandatory=$true)][int]$Port,
  [string]$AllowedNamesCsv = 'python,powershell,cmd,node'
)

$allowed = $AllowedNamesCsv.Split(',') | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ }
$lines = netstat -ano | Select-String -Pattern 'LISTENING' | Where-Object { $_.Line -match (":" + $Port + "\s") }
$killed = 0
$skipped = 0
$seen = @{}

foreach($l in $lines){
  $parts = ($l.ToString() -split '\s+') | Where-Object { $_ -ne '' }
  if($parts.Count -lt 5){ continue }

  $pidVal = 0
  if(-not [int]::TryParse($parts[-1], [ref]$pidVal)){ continue }
  if($pidVal -le 0){ continue }
  if($seen.ContainsKey($pidVal)){ continue }
  $seen[$pidVal] = $true

  $p = Get-Process -Id $pidVal -ErrorAction SilentlyContinue
  if(-not $p){ continue }

  $name = ''
  if($p.ProcessName){
    $name = $p.ProcessName.ToLowerInvariant()
  }

  if($allowed -contains $name){
    Stop-Process -Id $pidVal -Force -ErrorAction SilentlyContinue
    $killed++
  } else {
    $skipped++
  }
}

Write-Output ("OPZ_KILL_PORT port={0} killed={1} skipped={2}" -f $Port, $killed, $skipped)
exit 0
