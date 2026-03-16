# =============================================================================
# QOpz.AI — Sync codice Windows → Oracle VM
# Trasferisce il progetto via SCP/rsync (usa OpenSSH nativo di Windows)
#
# USO:
#   .\sync_to_vm.ps1 -PublicIp 130.61.XX.XX
#   .\sync_to_vm.ps1   (legge IP da vm_connection.txt se presente)
# =============================================================================

param(
    [string]$PublicIp = "",
    [string]$SshKeyPath = "C:\Users\odott\.ssh\qopz_vm_key",
    [string]$RemoteUser = "ubuntu",
    [string]$RemoteDir = "~/qopz"
)

$ErrorActionPreference = "Stop"

# Leggi IP da file se non passato
if (-not $PublicIp) {
    $connFile = "$PSScriptRoot\vm_connection.txt"
    if (Test-Path $connFile) {
        $content = Get-Content $connFile -Raw
        if ($content -match 'PUBLIC_IP\s*=\s*(\S+)') {
            $PublicIp = $matches[1]
            Write-Host "[INFO] IP letto da vm_connection.txt: $PublicIp" -ForegroundColor Cyan
        }
    }
}

if (-not $PublicIp) {
    Write-Host "[ERRORE] Specifica l'IP: .\sync_to_vm.ps1 -PublicIp <IP>" -ForegroundColor Red
    exit 1
}

$ProjectRoot = Split-Path $PSScriptRoot -Parent
$Remote = "${RemoteUser}@${PublicIp}:${RemoteDir}"

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════╗" -ForegroundColor Blue
Write-Host "║         QOpz.AI — Sync a Oracle VM                      ║" -ForegroundColor Blue
Write-Host "╠══════════════════════════════════════════════════════════╣" -ForegroundColor Blue
Write-Host "║  Sorgente  : $ProjectRoot" -ForegroundColor White
Write-Host "║  Destino   : $Remote" -ForegroundColor White
Write-Host "║  Chiave    : $SshKeyPath" -ForegroundColor White
Write-Host "╚══════════════════════════════════════════════════════════╝" -ForegroundColor Blue
Write-Host ""

# Crea directory remota
Write-Host "[1/3] Creazione directory remota..." -ForegroundColor Cyan
ssh -i $SshKeyPath -o StrictHostKeyChecking=no `
    "${RemoteUser}@${PublicIp}" "mkdir -p $RemoteDir"
Write-Host "    ✓ Directory pronta" -ForegroundColor Green

# Lista esclusioni
$excludes = @(
    ".venv", "__pycache__", "*.pyc", ".git",
    ".tmp_test", ".zip", "db/*.duckdb",
    "logs/*", "reports/*", "*.egg-info",
    "node_modules", ".DS_Store", "Thumbs.db"
)

# Trasferimento via scp (compatibile con Windows OpenSSH nativo)
Write-Host "[2/3] Trasferimento file..." -ForegroundColor Cyan

# Costruisci exclude options per scp non supporta --exclude,
# usiamo robocopy per creare uno staging dir temporaneo e poi scp
$stagingDir = "$env:TEMP\qopz_staging"
if (Test-Path $stagingDir) { Remove-Item $stagingDir -Recurse -Force }
New-Item -ItemType Directory -Path $stagingDir | Out-Null

$robocopyExcludes = @("/XD", ".venv", "__pycache__", ".git", ".tmp_test", ".zip", "node_modules") +
                   @("/XF", "*.pyc", "*.duckdb", "*.log", "schema_applied.ok")

$robocopyArgs = @($ProjectRoot, $stagingDir, "/E", "/NFL", "/NDL", "/NJH", "/NJS") + $robocopyExcludes
$rc = Start-Process robocopy -ArgumentList $robocopyArgs -Wait -PassThru -WindowStyle Hidden
# robocopy exit codes: 0=no change, 1=files copied, <8=OK
if ($rc.ExitCode -ge 8) {
    Write-Host "    ⚠ Robocopy warning (code $($rc.ExitCode))" -ForegroundColor Yellow
}

# Conta file
$fileCount = (Get-ChildItem $stagingDir -Recurse -File).Count
$sizeKb = [Math]::Round((Get-ChildItem $stagingDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1KB)
Write-Host "    → $fileCount file ($sizeKb KB) da trasferire..." -ForegroundColor White

# SCP ricorsivo
scp -i $SshKeyPath -o StrictHostKeyChecking=no -r `
    "$stagingDir\*" "${RemoteUser}@${PublicIp}:${RemoteDir}/"

if ($LASTEXITCODE -eq 0) {
    Write-Host "    ✓ Trasferimento completato" -ForegroundColor Green
} else {
    Write-Host "    ✗ Errore SCP (code $LASTEXITCODE)" -ForegroundColor Red
    exit 1
}

# Pulizia staging
Remove-Item $stagingDir -Recurse -Force

Write-Host "[3/3] Verifica remota..." -ForegroundColor Cyan
$remoteCheck = ssh -i $SshKeyPath -o StrictHostKeyChecking=no `
    "${RemoteUser}@${PublicIp}" "ls $RemoteDir | head -10 && echo '---' && du -sh $RemoteDir"
Write-Host $remoteCheck -ForegroundColor White
Write-Host "    ✓ Sync completato" -ForegroundColor Green

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║  Sync completato! Prossimo passo:                       ║" -ForegroundColor Green
Write-Host "╠══════════════════════════════════════════════════════════╣" -ForegroundColor Green
Write-Host "║  ssh -i `"$SshKeyPath`"" -ForegroundColor White
Write-Host "║      ubuntu@$PublicIp" -ForegroundColor Cyan
Write-Host "║" -ForegroundColor Green
Write-Host "║  sudo bash ~/qopz/scripts/vm_setup.sh" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
