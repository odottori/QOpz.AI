param(
    [string]$VmHost = "178.104.94.34",
    [string]$VmUser = "root",
    [string]$SshKeyPath = "$HOME/.ssh/qopz_vm_key",
    [string]$WebUser = "opz",
    [string]$WebPassword = $env:QOPZ_WEB_PASSWORD,
    [int]$ServerLoopCount = 10,
    [int]$ServerLoopSleepSec = 1,
    [switch]$SkipUi
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($WebPassword)) {
    throw "Missing web password. Set -WebPassword or QOPZ_WEB_PASSWORD env var."
}

$root = Split-Path -Parent $PSScriptRoot
$reportsDir = Join-Path $root "reports"
if (-not (Test-Path $reportsDir)) {
    New-Item -Path $reportsDir -ItemType Directory | Out-Null
}
$stamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$reportPath = Join-Path $reportsDir "remote_runtime_audit_$stamp.json"

function Invoke-SshCommand {
    param([string]$RemoteCommand)

    $output = & ssh -i $SshKeyPath -o StrictHostKeyChecking=no "$VmUser@$VmHost" $RemoteCommand 2>&1
    return [pscustomobject]@{
        ExitCode = $LASTEXITCODE
        Output = ($output -join "`n")
    }
}

Write-Host "[audit] Checking VM docker services..." -ForegroundColor Cyan
$psCmd = "cd /opt/qopz && docker compose ps"
$psResult = Invoke-SshCommand -RemoteCommand $psCmd

Write-Host "[audit] Checking server-side /health..." -ForegroundColor Cyan
$healthCmd = [string]::Format(
    "curl -s -o /dev/null -w '%{{http_code}}' -u '{0}:{1}' http://127.0.0.1/health",
    $WebUser,
    $WebPassword
)
$healthResult = Invoke-SshCommand -RemoteCommand $healthCmd
$healthCode = ($healthResult.Output.Trim() -split "`r?`n")[-1]

Write-Host "[audit] Running server-side IBKR account stability loop..." -ForegroundColor Cyan
$loopTemplate = "count={0}; i=1; while [ `$i -le `$count ]; do code=`$(curl -s -o /dev/null -w '%{{http_code}}' -u '{1}:{2}' http://127.0.0.1/opz/ibkr/account || echo 000); echo `$code; i=`$((i+1)); sleep {3}; done"
$loopCmd = [string]::Format($loopTemplate, $ServerLoopCount, $WebUser, $WebPassword, $ServerLoopSleepSec)
$loopResult = Invoke-SshCommand -RemoteCommand $loopCmd
$loopCodes = @(
    $loopResult.Output -split "`r?`n" |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_ -match "^\d{3}$" }
)
$loopOk = ($loopCodes | Where-Object { $_ -eq "200" }).Count

$uiExit = $null
$uiRaw = $null
$uiParsed = $null
if (-not $SkipUi) {
    Write-Host "[audit] Running Playwright UI read-only validation..." -ForegroundColor Cyan
    $uiRawLines = & node .tmp\ui_full_validation_readonly.mjs 2>&1
    $uiExit = $LASTEXITCODE
    $uiRaw = ($uiRawLines -join "`n")
    if ($uiExit -eq 0) {
        try {
            $uiParsed = $uiRaw | ConvertFrom-Json -ErrorAction Stop
        } catch {
            $uiParsed = $null
        }
    }
}

$result = [ordered]@{
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    host = $VmHost
    vm = [ordered]@{
        docker_compose_ps_exit = $psResult.ExitCode
        docker_compose_ps = $psResult.Output
        health_exit = $healthResult.ExitCode
        health_code = $healthCode
        account_loop_exit = $loopResult.ExitCode
        account_loop_count = $ServerLoopCount
        account_loop_codes = $loopCodes
        account_loop_ok_200 = $loopOk
    }
    ui = [ordered]@{
        skipped = [bool]$SkipUi
        exit = $uiExit
        parsed = $uiParsed
        raw = $uiRaw
    }
}

$vmHealthy = ($healthResult.ExitCode -eq 0 -and $healthCode -eq "200")
$loopHealthy = ($loopResult.ExitCode -eq 0 -and $loopCodes.Count -eq $ServerLoopCount -and $loopOk -eq $ServerLoopCount)
$uiHealthy = $true
if (-not $SkipUi) {
    if ($uiExit -ne 0 -or $null -eq $uiParsed) {
        $uiHealthy = $false
    } else {
        $sum = $uiParsed.summary
        $uiHealthy = (
            $sum.actionFailed -eq 0 -and
            $sum.opzHttpNon2xx -eq 0 -and
            $sum.consoleErrors -eq 0 -and
            $sum.pageErrors -eq 0 -and
            $sum.failedRequests -eq 0
        )
    }
}

$result["overall_ok"] = ($vmHealthy -and $loopHealthy -and $uiHealthy)

$result | ConvertTo-Json -Depth 10 | Set-Content -Path $reportPath -Encoding utf8

Write-Host ""
Write-Host "Report: $reportPath"
Write-Host "overall_ok=$($result.overall_ok) vmHealthy=$vmHealthy loopHealthy=$loopHealthy uiHealthy=$uiHealthy"
if (-not $result.overall_ok) {
    exit 2
}
