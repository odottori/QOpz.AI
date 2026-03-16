#Requires -Version 5.1
# QOpz.AI - Oracle Cloud VM Creator

$ErrorActionPreference = "Continue"
$env:PATH = "C:\Program Files (x86)\Oracle\oci_cli;" + $env:PATH

$TENANCY   = "ocid1.tenancy.oc1..aaaaaaaadkfov52k6kpasdueycyctxna6gkwgpa7drqlktuwffgarfssp2vq"
$REGION    = "eu-frankfurt-1"
$SSHKEY    = "C:\Users\odott\.ssh\qopz_vm_key.pub"
$SHAPE     = "VM.Standard.A1.Flex"
$OCPUS     = 4
$MEM_GB    = 24
$VM_NAME   = "qopz-server"
$VCN_NAME  = "qopz-vcn"
$SUB_NAME  = "qopz-subnet"
$VCN_CIDR  = "10.0.0.0/16"
$SUB_CIDR  = "10.0.0.0/24"
$MAX_TRIES = 4320   # ~24h a 20s/tentativo
$DELAY_SEC = 20

$OCI = "C:\Program Files (x86)\Oracle\oci_cli\oci.exe"
function Run-OCI { & $OCI @args 2>$null }
function Log { param($c,$m)
    $col = switch($c){ ' OK '{'Green'} 'WARN'{'Yellow'} 'FAIL'{'Red'} default{'Cyan'} }
    Write-Host "[$c] $m" -ForegroundColor $col
}

Write-Host "`n============================================================" -ForegroundColor Blue
Write-Host "   QOpz.AI - Oracle Cloud VM Creator" -ForegroundColor Blue
Write-Host "============================================================`n" -ForegroundColor Blue

if (-not (Test-Path $SSHKEY)) { Log FAIL "SSH key non trovata: $SSHKEY"; exit 1 }
Log ' OK ' "SSH key OK"

# 1. Availability Domains
Log INFO "1/6 Availability Domains..."
$ADs = (Run-OCI iam availability-domain list --compartment-id $TENANCY --region $REGION | ConvertFrom-Json).data | ForEach-Object { $_.name }
Log ' OK ' "ADs: $($ADs -join ', ')"

# 2. Immagine
Log INFO "2/6 Immagine Ubuntu 22.04 ARM64..."
$imgData = (Run-OCI compute image list --compartment-id $TENANCY --operating-system "Canonical Ubuntu" --operating-system-version "22.04" --shape $SHAPE --region $REGION | ConvertFrom-Json).data
$IMG_ID = ($imgData | Where-Object { $_.'lifecycle-state' -eq "AVAILABLE" } | Select-Object -First 1).id
if (-not $IMG_ID) { Log FAIL "Immagine non trovata"; exit 1 }
Log ' OK ' "Image trovata"

# 3. Rete
Log INFO "3/6 Setup rete..."

$vcnData = (Run-OCI network vcn list --compartment-id $TENANCY --region $REGION | ConvertFrom-Json).data
$VCN_ID = ($vcnData | Where-Object { $_.'display-name' -eq $VCN_NAME } | Select-Object -First 1).id
if (-not $VCN_ID) {
    $raw = Run-OCI network vcn create --compartment-id $TENANCY --cidr-block $VCN_CIDR --display-name $VCN_NAME --dns-label qopzvcn --region $REGION --wait-for-state AVAILABLE 2>&1
    $VCN_ID = ($raw | Where-Object { $_ -match '^\s*\{' } | Out-String | ConvertFrom-Json).data.id
    Log ' OK ' "VCN creata"
} else { Log WARN "VCN esistente - riuso" }

$igwData = (Run-OCI network internet-gateway list --compartment-id $TENANCY --vcn-id $VCN_ID --region $REGION | ConvertFrom-Json).data
$IGW_ID = ($igwData | Select-Object -First 1).id
if (-not $IGW_ID) {
    Run-OCI network internet-gateway create --compartment-id $TENANCY --vcn-id $VCN_ID --is-enabled true --display-name qopz-igw --region $REGION --wait-for-state AVAILABLE 2>&1 | Out-Null
    Start-Sleep -Seconds 3
    $IGW_ID = ((Run-OCI network internet-gateway list --compartment-id $TENANCY --vcn-id $VCN_ID --region $REGION | ConvertFrom-Json).data | Select-Object -First 1).id
    Log ' OK ' "IGW creato"
} else { Log WARN "IGW esistente - riuso" }

$rtData = (Run-OCI network route-table list --compartment-id $TENANCY --vcn-id $VCN_ID --region $REGION | ConvertFrom-Json).data
$RT_ID = ($rtData | Where-Object { $_.'display-name' -match "Default" } | Select-Object -First 1).id
if (-not $RT_ID) { $RT_ID = ($rtData | Select-Object -First 1).id }
# Route table: scrivi JSON su file temporaneo
$routeFile = [System.IO.Path]::GetTempFileName() + ".json"
'[{"destination":"0.0.0.0/0","destinationType":"CIDR_BLOCK","networkEntityId":"' + $IGW_ID + '"}]' | Set-Content -Path $routeFile -Encoding ASCII
& $OCI network route-table update --rt-id $RT_ID --route-rules "file://$routeFile" --region $REGION --force 2>&1 | Out-Null
Remove-Item $routeFile -ErrorAction SilentlyContinue
Log ' OK ' "Route table aggiornata"

$slData = (Run-OCI network security-list list --compartment-id $TENANCY --vcn-id $VCN_ID --region $REGION | ConvertFrom-Json).data
$SL_ID = ($slData | Where-Object { $_.'display-name' -match "Default" } | Select-Object -First 1).id
if (-not $SL_ID) { $SL_ID = ($slData | Select-Object -First 1).id }
# Ingress rules: scrivi JSON su file temporaneo
$ingressFile = [System.IO.Path]::GetTempFileName() + ".json"
'[{"protocol":"6","source":"0.0.0.0/0","tcpOptions":{"destinationPortRange":{"min":22,"max":22}},"isStateless":false},{"protocol":"6","source":"0.0.0.0/0","tcpOptions":{"destinationPortRange":{"min":8765,"max":8765}},"isStateless":false},{"protocol":"6","source":"0.0.0.0/0","tcpOptions":{"destinationPortRange":{"min":8080,"max":8080}},"isStateless":false}]' | Set-Content -Path $ingressFile -Encoding ASCII
& $OCI network security-list update --security-list-id $SL_ID --ingress-security-rules "file://$ingressFile" --region $REGION --force 2>&1 | Out-Null
Remove-Item $ingressFile -ErrorAction SilentlyContinue
Log ' OK ' "Security list: 22, 8765, 8080"

$subData = (Run-OCI network subnet list --compartment-id $TENANCY --vcn-id $VCN_ID --region $REGION | ConvertFrom-Json).data
$SUB_ID = ($subData | Where-Object { $_.'display-name' -eq $SUB_NAME } | Select-Object -First 1).id
if (-not $SUB_ID) {
    # Su Windows OCI CLI vuole JSON via file per array
    $secIdsFile = [System.IO.Path]::GetTempFileName() + ".json"
    '["' + $SL_ID + '"]' | Set-Content -Path $secIdsFile -Encoding ASCII
    & $OCI network subnet create --compartment-id $TENANCY --vcn-id $VCN_ID --cidr-block $SUB_CIDR --display-name $SUB_NAME --dns-label qopzsubnet --route-table-id $RT_ID --security-list-ids "file://$secIdsFile" --region $REGION --wait-for-state AVAILABLE 2>&1 | Out-Null
    Remove-Item $secIdsFile -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
    $SUB_ID = ((Run-OCI network subnet list --compartment-id $TENANCY --vcn-id $VCN_ID --region $REGION | ConvertFrom-Json).data | Where-Object { $_.'display-name' -eq $SUB_NAME } | Select-Object -First 1).id
    Log ' OK ' "Subnet creata"
} else { Log WARN "Subnet esistente - riuso" }

if (-not $SUB_ID) { Log FAIL "Subnet ID non trovato"; exit 1 }
Log ' OK ' "Rete pronta | SUB_ID: $($SUB_ID.Substring(0,40))..."

# 4. Crea VM con retry
Log INFO "4/6 Creazione VM (retry ogni ${DELAY_SEC}s, max $MAX_TRIES tentativi)..."
$INST_ID = $null
$AD_USED = $null
$shapeFile = [System.IO.Path]::GetTempFileName() + ".json"
'{"ocpus":' + $OCPUS + ',"memoryInGBs":' + $MEM_GB + '}' | Set-Content -Path $shapeFile -Encoding ASCII
$attempt = 0

while ($attempt -lt $MAX_TRIES -and (-not $INST_ID)) {
    foreach ($ad in $ADs) {
        $attempt++
        $ts = Get-Date -Format "HH:mm:ss"
        Write-Host "  [$ts] Tentativo $attempt/$MAX_TRIES - $ad" -ForegroundColor White

        $raw = & $OCI compute instance launch `
            --availability-domain $ad `
            --compartment-id $TENANCY `
            --shape $SHAPE `
            --shape-config "file://$shapeFile" `
            --image-id $IMG_ID `
            --subnet-id $SUB_ID `
            --display-name $VM_NAME `
            --ssh-authorized-keys-file $SSHKEY `
            --assign-public-ip true `
            --region $REGION `
            --wait-for-state RUNNING `
            --max-wait-seconds 300 2>&1

        $errText = ($raw -join " ")
        $jsonLines = $raw | Where-Object { $_ -match '^\s*[\{\[]' }

        if ($jsonLines) {
            try {
                $obj = ($jsonLines | Out-String) | ConvertFrom-Json
                if ($obj.data.id) {
                    $INST_ID = $obj.data.id
                    $AD_USED = $ad
                    Log ' OK ' "VM CREATA! AD: $ad"
                    break
                }
            } catch {}
        }

        if ($errText -match "Out of capacity|out of host capacity") {
            Log WARN "$ad - Out of capacity"
        } elseif ($errText -match "LimitExceeded") {
            Log FAIL "Limite Free Tier superato"; exit 1
        } elseif ($errText -match "NotAuthenticated") {
            Log FAIL "Errore autenticazione"; exit 1
        } else {
            $short = $errText.Substring(0, [Math]::Min(100, $errText.Length))
            Log WARN "$ad - $short"
        }
    }

    if ((-not $INST_ID) -and ($attempt -lt $MAX_TRIES)) {
        Log WARN "Retry tra ${DELAY_SEC}s..."
        Start-Sleep -Seconds $DELAY_SEC
    }
}

if (-not $INST_ID) { Log FAIL "VM non creata dopo $attempt tentativi"; exit 1 }

# 5. IP Pubblico
Log INFO "5/6 IP pubblico..."
Start-Sleep -Seconds 8
$vnicList = (Run-OCI compute vnic-attachment list --compartment-id $TENANCY --instance-id $INST_ID --region $REGION | ConvertFrom-Json).data
$VNIC_ID = ($vnicList | Select-Object -First 1).'vnic-id'
$vnic = (Run-OCI network vnic get --vnic-id $VNIC_ID --region $REGION | ConvertFrom-Json).data
$PUBLIC_IP  = $vnic.'public-ip'
$PRIVATE_IP = $vnic.'private-ip'
if (-not $PUBLIC_IP) {
    $PUBLIC_IP = (Run-OCI network public-ip create --compartment-id $TENANCY --lifetime EPHEMERAL --private-ip-id $PRIVATE_IP --region $REGION | ConvertFrom-Json).data.'ip-address'
}
Log ' OK ' "IP Pubblico: $PUBLIC_IP | Privato: $PRIVATE_IP"

# 6. Summary
$privKey = $SSHKEY -replace '\.pub$', ''
@"
INSTANCE_OCID = $INST_ID
PUBLIC_IP     = $PUBLIC_IP
AD            = $AD_USED
SSH_KEY       = $privKey
SSH_CMD       = ssh -i "$privKey" ubuntu@$PUBLIC_IP
"@ | Out-File "$PSScriptRoot\vm_connection.txt" -Encoding UTF8

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host "   VM ORACLE PRONTA" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  IP    : $PUBLIC_IP" -ForegroundColor Cyan
Write-Host "  AD    : $AD_USED" -ForegroundColor White
Write-Host "  Shape : $SHAPE ($OCPUS OCPU / $MEM_GB GB)" -ForegroundColor White
Write-Host ""
Write-Host "  Sync : .\sync_to_vm.ps1 -PublicIp $PUBLIC_IP" -ForegroundColor Cyan
Write-Host "  SSH  : ssh -i `"$privKey`" ubuntu@$PUBLIC_IP" -ForegroundColor Cyan
Write-Host "  Setup: sudo bash ~/qopz/scripts/vm_setup.sh" -ForegroundColor Cyan
Write-Host "============================================================`n" -ForegroundColor Green
