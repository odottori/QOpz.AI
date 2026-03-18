#!/usr/bin/env bash
# QOpz.AI - VM Watch Multi-Region v2 (Cloud Shell)
# Fix: --availability-domain obbligatorio + multi-region (auto-skip non sottoscritte) + timing-aware
#
# USO (OCI Cloud Shell):
#   bash vm_watch_cloudshell.sh
#
# Per aggiungere regioni: OCI Console → Governance → Regions → Subscribe
# Regioni EU disponibili: eu-amsterdam-1, eu-london-1, eu-zurich-1

set -uo pipefail

TENANCY="ocid1.tenancy.oc1..aaaaaaaadkfov52k6kpasdueycyctxna6gkwgpa7drqlktuwffgarfssp2vq"
VM_NAME="qopz-server"
SHAPE="VM.Standard.A1.Flex"
OCPUS=4
MEM_GB=24
SSH_PUB_KEY="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDdl3is1l3QFSWQrPtvPVk1c96TcvUTMrbgn5QpTHE9SrsNDTv6W9KT2qAKJvYmo/i4YAYB+LOPDcGFqkHjJDkdIFfJPZkecdpWrl2aFXWDikcKC8ubzKGVUSTv2kj/ghCXXupYIOgrUroxgLBitnfybis+UVssJIsXrGCtyGhpMrxZ7O+9usTWjjdVHkYbLM26vreGIPQnArxiC7siVjym/1Ahp1sKVKekqHgUlxlRFyTnc4wtswYyLmO8xOxKhFzXyVxvcL3EedvJyWMqCjOeVyt4IN76TFOyvThLJKQuNaC/L5tjVjwgJpXbTe6eC+q3kvairluFVbTAX6Lxl5QGeBlR4S5NpoRMKREjeY6/LMyX9z2qmJyM8uDCjsndtrv8YO0RcxZB0Wejf05PHMnEiig9tjjPTr/ByvLKdtbJVpXtnfZWWjYCwe3c9OOfS75qsKTmgpD8eD3bYJeU7PiS/p7bL9fti942yZgbGhf1gyhIeh3nyCBCXtKCjFaHnzWZJu7H4XlYCdBdQhnHFiNgGAMz5/uOF3sdmed3qUD3mHNhQ22krjJAd6GuHXI54Ijdg4xMtRFtlDh3MVDw4jgO+ASYMOqRZ/gHhrs2a9dKjoroTFEoa2UfqqKQ20VtlrjtifOBWRIauRHg/yva/1i95aVETKpARIAFiYrjLlgFRQ== odott@pc-oreste"

# Regioni candidate in ordine di preferenza.
# Lo script skippa automaticamente quelle non ancora sottoscritte.
# Per aggiungerne: OCI Console → Governance → Regions → Subscribe (gratis, ~2min)
CANDIDATE_REGIONS=("eu-amsterdam-1" "eu-london-1" "eu-zurich-1" "eu-frankfurt-1")

# Delay: 15s nella finestra d'oro 05-09 UTC (= 06-10 CET), 45s altrimenti
DELAY_GOLDEN=15
DELAY_NORMAL=45

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${CYAN}[$(date '+%H:%M:%S')][INFO]${NC} $*"; }
ok()   { echo -e "${GREEN}[$(date '+%H:%M:%S')][ OK ]${NC} $*"; }
warn() { echo -e "${YELLOW}[$(date '+%H:%M:%S')][WARN]${NC} $*"; }
fail() { echo -e "${RED}[$(date '+%H:%M:%S')][FAIL]${NC} $*"; }

# Ritorna lista regioni sottoscritte (READY)
get_subscribed_regions() {
    oci iam region-subscription list \
        --tenancy-id "$TENANCY" 2>/dev/null \
    | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)['data']
    for r in data:
        if r.get('status') == 'READY':
            print(r['region-name'])
except Exception:
    pass
" 2>/dev/null | tr -d '\r' || true
}

get_delay() {
    local h; h=$(printf '%d' "$(date -u +%H)")
    if [[ $h -ge 5 && $h -le 9 ]]; then echo $DELAY_GOLDEN; else echo $DELAY_NORMAL; fi
}

# Lista ADs per regione, uno per riga
get_ads() {
    local region=$1
    oci iam availability-domain list \
        --compartment-id "$TENANCY" \
        --region "$region" 2>/dev/null \
    | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)['data']
    for ad in data:
        print(ad['name'])
except Exception:
    pass
" 2>/dev/null | tr -d '\r' || true
}

# Image ID Ubuntu 22.04 ARM per la regione
get_image() {
    local region=$1
    oci compute image list \
        --compartment-id "$TENANCY" \
        --region "$region" \
        --operating-system "Canonical Ubuntu" \
        --operating-system-version "22.04" \
        --shape "$SHAPE" \
        --sort-by TIMECREATED --sort-order DESC \
        --all 2>/dev/null \
    | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)['data']
    avail = [x['id'] for x in data if x.get('lifecycle-state') == 'AVAILABLE']
    print(avail[0] if avail else '')
except Exception:
    pass
" 2>/dev/null | tr -d '\r' || true
}

# Assicura VCN + subnet, ritorna subnet_id (vuoto se fallisce)
ensure_network() {
    local region=$1

    # Subnet già esistente?
    local sub_id
    sub_id=$(oci network subnet list \
        --compartment-id "$TENANCY" --region "$region" \
        --display-name "qopz-subnet" 2>/dev/null \
    | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)['data']
    print(d[0]['id'] if d else '')
except Exception:
    pass
" 2>/dev/null | tr -d '\r' || true)
    if [[ -n "$sub_id" ]]; then echo "$sub_id"; return 0; fi

    log "[$region] Bootstrap rete (VCN + IGW + subnet)..."

    # VCN
    local vcn_id
    vcn_id=$(oci network vcn list \
        --compartment-id "$TENANCY" --region "$region" \
        --display-name "qopz-vcn" 2>/dev/null \
    | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)['data']
    print(d[0]['id'] if d else '')
except Exception:
    pass
" 2>/dev/null | tr -d '\r' || true)

    if [[ -z "$vcn_id" ]]; then
        vcn_id=$(oci network vcn create \
            --compartment-id "$TENANCY" --region "$region" \
            --cidr-block "10.0.0.0/16" \
            --display-name "qopz-vcn" \
            --dns-label qopzvcn \
            --wait-for-state AVAILABLE 2>/dev/null \
        | python3 -c "
import sys, json
try:
    print(json.load(sys.stdin)['data']['id'])
except Exception:
    pass
" 2>/dev/null | tr -d '\r' || true)
    fi
    [[ -z "$vcn_id" ]] && { warn "[$region] VCN fallita"; echo ""; return 1; }

    # Internet Gateway
    local igw_id
    igw_id=$(oci network internet-gateway list \
        --compartment-id "$TENANCY" --vcn-id "$vcn_id" --region "$region" 2>/dev/null \
    | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)['data']
    print(d[0]['id'] if d else '')
except Exception:
    pass
" 2>/dev/null | tr -d '\r' || true)

    if [[ -z "$igw_id" ]]; then
        igw_id=$(oci network internet-gateway create \
            --compartment-id "$TENANCY" --vcn-id "$vcn_id" --region "$region" \
            --is-enabled true --display-name qopz-igw \
            --wait-for-state AVAILABLE 2>/dev/null \
        | python3 -c "
import sys, json
try:
    print(json.load(sys.stdin)['data']['id'])
except Exception:
    pass
" 2>/dev/null | tr -d '\r' || true)
    fi

    # Route table (default)
    local rt_id
    rt_id=$(oci network route-table list \
        --compartment-id "$TENANCY" --vcn-id "$vcn_id" --region "$region" 2>/dev/null \
    | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)['data']
    print(d[0]['id'] if d else '')
except Exception:
    pass
" 2>/dev/null | tr -d '\r' || true)

    oci network route-table update --rt-id "$rt_id" --region "$region" --force \
        --route-rules "[{\"destination\":\"0.0.0.0/0\",\"destinationType\":\"CIDR_BLOCK\",\"networkEntityId\":\"$igw_id\"}]" \
        2>/dev/null >/dev/null || true

    # Security list
    local sl_id
    sl_id=$(oci network security-list list \
        --compartment-id "$TENANCY" --vcn-id "$vcn_id" --region "$region" 2>/dev/null \
    | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)['data']
    print(d[0]['id'] if d else '')
except Exception:
    pass
" 2>/dev/null | tr -d '\r' || true)

    oci network security-list update --security-list-id "$sl_id" --region "$region" --force \
        --ingress-security-rules \
        '[{"protocol":"6","source":"0.0.0.0/0","tcpOptions":{"destinationPortRange":{"min":22,"max":22}},"isStateless":false},{"protocol":"6","source":"0.0.0.0/0","tcpOptions":{"destinationPortRange":{"min":8765,"max":8765}},"isStateless":false},{"protocol":"6","source":"0.0.0.0/0","tcpOptions":{"destinationPortRange":{"min":8080,"max":8080}},"isStateless":false}]' \
        2>/dev/null >/dev/null || true

    # Subnet
    sub_id=$(oci network subnet create \
        --compartment-id "$TENANCY" --vcn-id "$vcn_id" --region "$region" \
        --cidr-block "10.0.0.0/24" \
        --display-name "qopz-subnet" \
        --dns-label qopzsubnet \
        --route-table-id "$rt_id" \
        --security-list-ids "[\"$sl_id\"]" \
        --wait-for-state AVAILABLE 2>/dev/null \
    | python3 -c "
import sys, json
try:
    print(json.load(sys.stdin)['data']['id'])
except Exception:
    pass
" 2>/dev/null | tr -d '\r' || true)

    echo "$sub_id"
}

# lifecycle-state della VM (vuoto se non esiste o TERMINATED)
get_vm_state() {
    local region=$1
    oci compute instance list \
        --compartment-id "$TENANCY" \
        --region "$region" \
        --display-name "$VM_NAME" 2>/dev/null \
    | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)['data']
    active = [x['lifecycle-state'] for x in data if x['lifecycle-state'] != 'TERMINATED']
    print(active[0] if active else '')
except Exception:
    pass
" 2>/dev/null | tr -d '\r' || true
}

# Tenta il launch in region+AD specifici
try_launch() {
    local region=$1 ad=$2 subnet=$3 image=$4
    local tmpkey; tmpkey=$(mktemp)
    printf '%s\n' "$SSH_PUB_KEY" > "$tmpkey"
    oci compute instance launch \
        --compartment-id "$TENANCY" \
        --region "$region" \
        --availability-domain "$ad" \
        --display-name "$VM_NAME" \
        --shape "$SHAPE" \
        --shape-config "{\"ocpus\":$OCPUS,\"memoryInGBs\":$MEM_GB}" \
        --subnet-id "$subnet" \
        --image-id "$image" \
        --ssh-authorized-keys-file "$tmpkey" \
        --assign-public-ip true \
        --wait-for-state RUNNING \
        --max-wait-seconds 30 2>/dev/null
    local rc=$?
    rm -f "$tmpkey"
    return $rc
}

# IP pubblico via VNIC
get_public_ip() {
    local region=$1
    local inst_id
    inst_id=$(oci compute instance list \
        --compartment-id "$TENANCY" --region "$region" \
        --display-name "$VM_NAME" 2>/dev/null \
    | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)['data']
    print(d[0]['id'] if d else '')
except Exception:
    pass
" 2>/dev/null | tr -d '\r' || true)
    [[ -z "$inst_id" ]] && { echo "N/A"; return; }

    local vnic_id
    vnic_id=$(oci compute vnic-attachment list \
        --compartment-id "$TENANCY" --instance-id "$inst_id" --region "$region" 2>/dev/null \
    | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)['data']
    print(d[0]['vnic-id'] if d else '')
except Exception:
    pass
" 2>/dev/null | tr -d '\r' || true)
    [[ -z "$vnic_id" ]] && { echo "N/A"; return; }

    oci network vnic get --vnic-id "$vnic_id" --region "$region" 2>/dev/null \
    | python3 -c "
import sys, json
try:
    print(json.load(sys.stdin)['data'].get('public-ip', 'N/A'))
except Exception:
    print('N/A')
" 2>/dev/null || echo "N/A"
}

# ── Startup ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  QOpz.AI VM Watch Multi-Region v2 - $(date '+%Y-%m-%d %H:%M')${NC}"
echo -e "${GREEN}  Shape : $SHAPE (${OCPUS} OCPU / ${MEM_GB}GB)${NC}"
echo -e "${GREEN}============================================================${NC}"

# Filtra solo regioni sottoscritte
log "Verifico regioni sottoscritte..."
mapfile -t SUBSCRIBED < <(get_subscribed_regions)
ACTIVE_REGIONS=()
for r in "${CANDIDATE_REGIONS[@]}"; do
    for s in "${SUBSCRIBED[@]}"; do
        if [[ "$r" == "$s" ]]; then
            ACTIVE_REGIONS+=("$r")
            break
        fi
    done
done

if [[ ${#ACTIVE_REGIONS[@]} -eq 0 ]]; then
    fail "Nessuna regione sottoscritta trovata. Verifica OCI config."
    exit 1
fi

ok "Regioni attive: ${ACTIVE_REGIONS[*]}"
if [[ ${#ACTIVE_REGIONS[@]} -lt ${#CANDIDATE_REGIONS[@]} ]]; then
    warn "Per aggiungere regioni: OCI Console → Governance → Regions → Subscribe"
    warn "Suggerite: eu-amsterdam-1, eu-london-1 (gratis, ~2min)"
fi
echo ""

# ── Main loop ────────────────────────────────────────────────────────────────
round=0
FOUND_REGION=""

while [[ -z "$FOUND_REGION" ]]; do
    round=$((round + 1))
    delay=$(get_delay)
    h_utc=$(printf '%d' "$(date -u +%H)")
    if [[ $h_utc -ge 5 && $h_utc -le 9 ]]; then
        window="GOLDEN 05-09UTC"
    else
        window="normale"
    fi
    log "=== Round $round | UTC=${h_utc}h | finestra=${window} | delay=${delay}s ==="

    for region in "${ACTIVE_REGIONS[@]}"; do

        # VM già presente?
        state=$(get_vm_state "$region")
        if [[ "$state" == "RUNNING" ]]; then
            ok "[$region] VM '$VM_NAME' già RUNNING!"
            FOUND_REGION="$region"
            break 2
        fi
        if [[ -n "$state" ]]; then
            log "[$region] VM in stato=$state — attendo..."
            continue
        fi

        # Rete
        subnet=$(ensure_network "$region")
        if [[ -z "$subnet" ]]; then
            warn "[$region] Subnet non pronta — skip"
            continue
        fi

        # Image
        image=$(get_image "$region")
        if [[ -z "$image" ]]; then
            warn "[$region] Immagine Ubuntu 22.04 ARM non trovata — skip"
            continue
        fi

        # Tenta tutti gli AD della regione
        while IFS= read -r ad; do
            [[ -z "$ad" ]] && continue
            log "[$region][$ad] → launch..."
            if try_launch "$region" "$ad" "$subnet" "$image"; then
                ok "[$region][$ad] VM CREATA!"
                FOUND_REGION="$region"
                break 3
            else
                warn "[$region][$ad] Out of capacity"
            fi
        done < <(get_ads "$region")

    done

    if [[ -z "$FOUND_REGION" ]]; then
        warn "Nessuna regione disponibile. Prossimo round tra ${delay}s..."
        sleep "$delay"
    fi
done

# ── Summary ──────────────────────────────────────────────────────────────────
if [[ -n "$FOUND_REGION" ]]; then
    sleep 8
    pub_ip=$(get_public_ip "$FOUND_REGION")
    echo ""
    echo -e "${GREEN}============================================================${NC}"
    echo -e "${GREEN}  VM ORACLE PRONTA${NC}"
    echo -e "${GREEN}  Regione : $FOUND_REGION${NC}"
    echo -e "${GREEN}  IP      : $pub_ip${NC}"
    echo -e "${GREEN}  SSH     : ssh -i ~/.ssh/qopz_vm_key ubuntu@$pub_ip${NC}"
    echo -e "${GREEN}  Setup   : sudo bash ~/qopz/scripts/vm_setup.sh${NC}"
    echo -e "${GREEN}============================================================${NC}"
fi
