#!/usr/bin/env bash
# QOpz.AI - VM Watch Loop per Oracle Cloud Shell
# Gira nel browser OCI, nessun costo, OCI CLI gia' configurato.
# Termina solo quando la VM e' RUNNING.
#
# USO (incolla in Cloud Shell):
#   bash <(cat vm_watch_cloudshell.sh)
#   oppure copia-incolla direttamente

set -uo pipefail

TENANCY="ocid1.tenancy.oc1..aaaaaaaadkfov52k6kpasdueycyctxna6gkwgpa7drqlktuwffgarfssp2vq"
REGION="eu-frankfurt-1"
VM_NAME="qopz-server"
SHAPE="VM.Standard.A1.Flex"
OCPUS=4
MEM_GB=24
SSH_PUB_KEY="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDdl3is1l3QFSWQrPtvPVk1c96TcvUTMrbgn5QpTHE9SrsNDTv6W9KT2qAKJvYmo/i4YAYB+LOPDcGFqkHjJDkdIFfJPZkecdpWrl2aFXWDikcKC8ubzKGVUSTv2kj/ghCXXupYIOgrUroxgLBitnfybis+UVssJIsXrGCtyGhpMrxZ7O+9usTWjjdVHkYbLM26vreGIPQnArxiC7siVjym/1Ahp1sKVKekqHgUlxlRFyTnc4wtswYyLmO8xOxKhFzXyVxvcL3EedvJyWMqCjOeVyt4IN76TFOyvThLJKQuNaC/L5tjVjwgJpXbTe6eC+q3kvairluFVbTAX6Lxl5QGeBlR4S5NpoRMKREjeY6/LMyX9z2qmJyM8uDCjsndtrv8YO0RcxZB0Wejf05PHMnEiig9tjjPTr/ByvLKdtbJVpXtnfZWWjYCwe3c9OOfS75qsKTmgpD8eD3bYJeU7PiS/p7bL9fti942yZgbGhf1gyhIeh3nyCBCXtKCjFaHnzWZJu7H4XlYCdBdQhnHFiNgGAMz5/uOF3sdmed3qUD3mHNhQ22krjJAd6GuHXI54Ijdg4xMtRFtlDh3MVDw4jgO+ASYMOqRZ/gHhrs2a9dKjoroTFEoa2UfqqKQ20VtlrjtifOBWRIauRHg/yva/1i95aVETKpARIAFiYrjLlgFRQ== odott@pc-oreste"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${CYAN}[$(date +%H:%M:%S)][INFO]${NC} $*"; }
ok()   { echo -e "${GREEN}[$(date +%H:%M:%S)][ OK ]${NC} $*"; }
warn() { echo -e "${YELLOW}[$(date +%H:%M:%S)][WARN]${NC} $*"; }

get_vm_state() {
    oci compute instance list \
        --compartment-id "$TENANCY" \
        --region "$REGION" \
        --display-name "$VM_NAME" \
        --query "data[?\"lifecycle-state\"!='TERMINATED'] | [0].\"lifecycle-state\"" \
        --raw-output 2>/dev/null || echo ""
}

get_subnet_id() {
    oci network subnet list \
        --compartment-id "$TENANCY" \
        --region "$REGION" \
        --display-name "qopz-subnet" \
        --query "data[0].id" --raw-output 2>/dev/null || echo ""
}

get_image_id() {
    oci compute image list \
        --compartment-id "$TENANCY" \
        --region "$REGION" \
        --operating-system "Canonical Ubuntu" \
        --operating-system-version "22.04" \
        --shape "$SHAPE" \
        --sort-by TIMECREATED --sort-order DESC \
        --query "data[0].id" --raw-output 2>/dev/null || echo ""
}

launch_vm() {
    local subnet image
    subnet=$(get_subnet_id)
    image=$(get_image_id)
    if [[ -z "$subnet" || -z "$image" ]]; then
        warn "subnet o image non trovati - skip launch"
        return 1
    fi
    log "Launch VM: shape=$SHAPE ocpus=$OCPUS mem=${MEM_GB}GB"
    oci compute instance launch \
        --compartment-id "$TENANCY" \
        --region "$REGION" \
        --display-name "$VM_NAME" \
        --shape "$SHAPE" \
        --shape-config "{\"ocpus\":$OCPUS,\"memoryInGBs\":$MEM_GB}" \
        --subnet-id "$subnet" \
        --image-id "$image" \
        --ssh-authorized-keys-file <(echo "$SSH_PUB_KEY") \
        --assign-public-ip true \
        --wait-for-state RUNNING \
        --max-wait-seconds 300 2>/dev/null && return 0 || return 1
}

# ── Main loop ────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}   QOpz.AI - VM Watch (Cloud Shell) - $(date '+%Y-%m-%d %H:%M')${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""

round=0
while true; do
    round=$((round+1))
    state=$(get_vm_state)

    if [[ "$state" == "RUNNING" ]]; then
        ok "VM '$VM_NAME' e' RUNNING dopo $round round(s)!"
        # Stampa IP pubblico
        ip=$(oci compute instance list \
            --compartment-id "$TENANCY" --region "$REGION" \
            --display-name "$VM_NAME" \
            --query "data[0].\"primary-private-ip-address\"" \
            --raw-output 2>/dev/null || echo "N/A")
        ok "IP: $ip"
        break
    fi

    if [[ -n "$state" ]]; then
        log "VM in stato '$state' - attendo 30s..."
        sleep 30
        continue
    fi

    warn "Round $round - VM non trovata. Tentativo launch..."
    if launch_vm; then
        ok "Launch avviato con successo"
    else
        warn "Launch fallito (Out of Capacity?) - riprovo tra 20s..."
        sleep 20
    fi
done
