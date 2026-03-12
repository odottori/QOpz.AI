[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)]
  [ValidateSet('dev','paper','live')]
  [string]$Profile,

  [Parameter(Mandatory=$false)]
  [string]$Config = $null,

  [Parameter(Mandatory=$true)]
  [string]$Symbol,

  [Parameter(Mandatory=$true)]
  [ValidateSet('BUY','SELL')]
  [string]$Side,

  [Parameter(Mandatory=$true)]
  [int]$Qty,

  [Parameter(Mandatory=$false)]
  [string]$RunId = $null,

  [Parameter(Mandatory=$false)]
  [string]$ClientOrderId = $null
)

# Ensure we run from repo root even when invoked via a new powershell.exe instance.
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $repoRoot
try {
  $argsList = @(
    ".\scripts\submit_order.py",
    "--profile", $Profile,
    "--symbol", $Symbol,
    "--side", $Side,
    "--qty", $Qty
  )

  if ($Config) { $argsList += @("--config", $Config) }
  if ($RunId) { $argsList += @("--run-id", $RunId) }
  if ($ClientOrderId) { $argsList += @("--client-order-id", $ClientOrderId) }

  & py @argsList
  exit $LASTEXITCODE
} finally {
  Pop-Location
}
