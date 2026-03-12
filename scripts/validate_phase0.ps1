param(
  [Parameter(Mandatory=$true)][ValidateSet("dev","paper","live")] [string]$Profile,
  [Parameter(Mandatory=$true)] [string]$Config,
  [double]$Capital = 0
)
$py = "py"
& $py .\validator.py --profile $Profile --config $Config --capital $Capital
exit $LASTEXITCODE
