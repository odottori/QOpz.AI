#Requires -Version 5.1
# QOpz.AI - VM Watch Loop
# Controlla se la VM e' RUNNING; se no, rilancia create_oci_vm.ps1 e ripete.
# Termina solo quando la VM e' confermata RUNNING.
#
# USO:
#   powershell -ExecutionPolicy Bypass -File scripts\vm_watch.ps1

$ErrorActionPreference = "Continue"
$env:PATH = "C:\Program Files (x86)\Oracle\oci_cli;" + $env:PATH

$CREATOR   = "$PSScriptRoot\create_oci_vm.ps1"
$OCI       = "C:\Program Files (x86)\Oracle\oci_cli\oci.exe"
$TENANCY   = "ocid1.tenancy.oc1..aaaaaaaadkfov52k6kpasdueycyctxna6gkwgpa7drqlktuwffgarfssp2vq"
$REGION    = "eu-frankfurt-1"
$VM_NAME   = "qopz-server"

function Log { param($c,$m)
    $col = switch($c){ ' OK '{'Green'} 'WARN'{'Yellow'} 'FAIL'{'Red'} default{'Cyan'} }
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')][$c] $m" -ForegroundColor $col
}

function Get-VMState {
    $raw = & $OCI compute instance list `
        --compartment-id $TENANCY `
        --region $REGION `
        --display-name $VM_NAME `
        --output json 2>$null
    if (-not $raw) { return $null }
    try {
        $items = ($raw | ConvertFrom-Json).data |
                 Where-Object { $_.'lifecycle-state' -ne 'TERMINATED' }
        if ($items) { return $items[0].'lifecycle-state' }
    } catch {}
    return $null
}

function Get-CreatorProcess {
    Get-Process powershell,pwsh -ErrorAction SilentlyContinue | Where-Object {
        try {
            (Get-WmiObject Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine `
                -like "*create_oci_vm*"
        } catch { $false }
    } | Select-Object -First 1
}

# ── Main loop ────────────────────────────────────────────────────────────────
Log INFO "=== vm_watch.ps1 avviato - ciclo finche VM e' RUNNING ==="
$round = 0

while ($true) {
    $round++

    # 1. VM gia' attiva?
    $state = Get-VMState
    if ($state -eq 'RUNNING') {
        Log ' OK ' "VM '$VM_NAME' e' RUNNING dopo $round round(s). Uscita."
        break
    }
    if ($state) {
        Log INFO "VM trovata in stato '$state' - attendo RUNNING (30s)..."
        Start-Sleep -Seconds 30
        continue
    }

    # 2. Il creator e' gia' in esecuzione?
    $proc = Get-CreatorProcess
    if ($proc) {
        Log INFO "Round $round - create_oci_vm.ps1 attivo (PID $($proc.Id)), attendo fine..."
        $proc | Wait-Process -Timeout 90000 -ErrorAction SilentlyContinue
        Log INFO "Processo terminato. Ricontrollo VM..."
        Start-Sleep -Seconds 15
        continue
    }

    # 3. Niente VM, niente processo -> rilancio
    Log WARN "Round $round - VM assente, nessun creator attivo. Rilancio..."
    Start-Process powershell -ArgumentList `
        "-NoProfile -ExecutionPolicy Bypass -File `"$CREATOR`"" `
        -WindowStyle Normal
    Start-Sleep -Seconds 30
}
