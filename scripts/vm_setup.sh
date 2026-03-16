#!/usr/bin/env bash
# =============================================================================
# QOpz.AI — Oracle Cloud VM Setup Script
# Ubuntu 22.04 LTS | ARM64 (VM.Standard.A1.Flex)
#
# USO:
#   chmod +x vm_setup.sh && sudo bash vm_setup.sh
#
# Eseguire DOPO aver copiato il progetto in ~/qopz (vedi sync_to_vm.ps1)
# =============================================================================

set -euo pipefail

# ── Colori ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

log()  { echo -e "${CYAN}[SETUP]${NC} $*"; }
ok()   { echo -e "${GREEN}[  OK  ]${NC} $*"; }
warn() { echo -e "${YELLOW}[ WARN ]${NC} $*"; }
fail() { echo -e "${RED}[ FAIL ]${NC} $*"; exit 1; }

# ── Configurazione ────────────────────────────────────────────────────────────
APP_USER="${APP_USER:-ubuntu}"
APP_DIR="/home/${APP_USER}/qopz"
VENV_DIR="${APP_DIR}/.venv"
PYTHON_BIN="python3.11"
FASTAPI_PORT=8765        # public (nginx → uvicorn)
FASTAPI_INTERNAL=18765  # uvicorn binds 127.0.0.1 only
DOCS_PORT=8080
MKDOCS_SITE_DIR="${APP_DIR}/docs_site"
TOKEN_FILE="/etc/qopz-api.env"

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║        QOpz.AI — Oracle Cloud VM Setup                  ║${NC}"
echo -e "${BLUE}║        Ubuntu 22.04 ARM64 | $(date +%Y-%m-%d)                  ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# ── 1. System update ─────────────────────────────────────────────────────────
log "1/9 · Aggiornamento pacchetti sistema..."
apt-get update -qq
apt-get upgrade -y -qq
ok "Sistema aggiornato"

# ── 2. Python 3.11 ───────────────────────────────────────────────────────────
log "2/9 · Installazione Python 3.11..."
apt-get install -y -qq software-properties-common
add-apt-repository -y ppa:deadsnakes/ppa
apt-get update -qq
apt-get install -y -qq \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    build-essential \
    git \
    curl \
    htop \
    unzip \
    rsync \
    nginx

PYTHON_VERSION=$(python3.11 --version 2>&1)
ok "Installato: ${PYTHON_VERSION}"

# ── 3. Firewall UFW ──────────────────────────────────────────────────────────
log "3/9 · Configurazione firewall UFW..."
ufw --force reset > /dev/null 2>&1
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment "SSH"
ufw allow ${FASTAPI_PORT}/tcp comment "QOpz FastAPI"
ufw allow ${DOCS_PORT}/tcp comment "MkDocs docs"
ufw --force enable
ok "UFW attivo: SSH(22), FastAPI(${FASTAPI_PORT}), Docs(${DOCS_PORT})"
ufw status numbered

# ── 3b. Token API + nginx ────────────────────────────────────────────────────
log "3b · Generazione token API e configurazione nginx..."

# Genera token casuale 32 byte hex
API_TOKEN=$(python3 -c "import secrets; print(secrets.token_hex(32))")
echo "OPZ_API_TOKEN=${API_TOKEN}" > "${TOKEN_FILE}"
chmod 600 "${TOKEN_FILE}"
chown root:root "${TOKEN_FILE}"
ok "Token API generato → ${TOKEN_FILE}"

# nginx: reverse proxy su porta pubblica ${FASTAPI_PORT} → uvicorn interno ${FASTAPI_INTERNAL}
cat > /etc/nginx/sites-available/qopz << NGINX_EOF
limit_req_zone \$binary_remote_addr zone=qopz_api:10m rate=30r/m;

server {
    listen ${FASTAPI_PORT};
    server_name _;

    client_max_body_size 1m;

    location / {
        limit_req zone=qopz_api burst=10 nodelay;
        proxy_pass         http://127.0.0.1:${FASTAPI_INTERNAL};
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_set_header   X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_read_timeout 30s;
        proxy_send_timeout 30s;
    }
}
NGINX_EOF

# Disabilita default site, abilita qopz
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/qopz /etc/nginx/sites-enabled/qopz
nginx -t && systemctl enable nginx && systemctl restart nginx
ok "nginx configurato: :${FASTAPI_PORT} → 127.0.0.1:${FASTAPI_INTERNAL} (rate 30r/min)"

# ── 4. Virtual environment ───────────────────────────────────────────────────
log "4/9 · Creazione virtual environment..."
if [ ! -d "${APP_DIR}" ]; then
    warn "Directory ${APP_DIR} non trovata — la creo vuota"
    mkdir -p "${APP_DIR}"
    chown "${APP_USER}:${APP_USER}" "${APP_DIR}"
fi

sudo -u "${APP_USER}" ${PYTHON_BIN} -m venv "${VENV_DIR}"
ok "Venv creato in ${VENV_DIR}"

# ── 5. Dipendenze Python ─────────────────────────────────────────────────────
log "5/9 · Installazione dipendenze Python..."

PIP="${VENV_DIR}/bin/pip"
sudo -u "${APP_USER}" ${PIP} install --upgrade pip -q

if [ -f "${APP_DIR}/requirements-core.txt" ]; then
    log "  → requirements-core.txt"
    sudo -u "${APP_USER}" ${PIP} install -r "${APP_DIR}/requirements-core.txt" -q
    ok "  Core OK"
else
    warn "  requirements-core.txt non trovato — skip"
fi

if [ -f "${APP_DIR}/requirements-web.txt" ]; then
    log "  → requirements-web.txt"
    sudo -u "${APP_USER}" ${PIP} install -r "${APP_DIR}/requirements-web.txt" -q
    ok "  Web (FastAPI/Uvicorn) OK"
else
    warn "  requirements-web.txt non trovato — skip"
fi

# MkDocs per la documentazione
log "  → MkDocs + Material theme"
sudo -u "${APP_USER}" ${PIP} install mkdocs mkdocs-material -q
ok "  MkDocs OK"

# ── 5b. Directory operative runtime ─────────────────────────────────────────
log "5b · Creazione directory runtime (db, ops, logs, reports)..."
for d in db ops logs reports; do
    mkdir -p "${APP_DIR}/${d}"
    chown "${APP_USER}:${APP_USER}" "${APP_DIR}/${d}"
done
ok "Directory runtime pronte"

# ── 6. Build documentazione ──────────────────────────────────────────────────
log "6/9 · Build documentazione MkDocs..."
if [ -f "${APP_DIR}/mkdocs.yml" ]; then
    sudo -u "${APP_USER}" bash -c "cd ${APP_DIR} && ${VENV_DIR}/bin/mkdocs build -d ${MKDOCS_SITE_DIR} -q"
    ok "Docs build → ${MKDOCS_SITE_DIR}"
else
    warn "mkdocs.yml non trovato — skip build docs"
    mkdir -p "${MKDOCS_SITE_DIR}"
fi

# ── 7. Systemd — FastAPI service ─────────────────────────────────────────────
log "7/9 · Systemd service: qopz-api..."
cat > /etc/systemd/system/qopz-api.service << EOF
[Unit]
Description=QOpz.AI FastAPI Backend
After=network.target nginx.service
StartLimitIntervalSec=0

[Service]
Type=simple
Restart=always
RestartSec=5
User=${APP_USER}
WorkingDirectory=${APP_DIR}
Environment="PATH=${VENV_DIR}/bin"
Environment="PYTHONPATH=${APP_DIR}"
EnvironmentFile=${TOKEN_FILE}
ExecStart=${VENV_DIR}/bin/uvicorn api.opz_api:app \\
    --host 127.0.0.1 \\
    --port ${FASTAPI_INTERNAL} \\
    --workers 1 \\
    --log-level info
StandardOutput=journal
StandardError=journal
SyslogIdentifier=qopz-api

[Install]
WantedBy=multi-user.target
EOF
ok "Service qopz-api creato"

# ── 8. Systemd — MkDocs docs server ─────────────────────────────────────────
log "8/9 · Systemd service: qopz-docs..."
cat > /etc/systemd/system/qopz-docs.service << EOF
[Unit]
Description=QOpz.AI MkDocs Documentation Server
After=network.target

[Service]
Type=simple
Restart=always
RestartSec=5
User=${APP_USER}
WorkingDirectory=${APP_DIR}
Environment="PATH=${VENV_DIR}/bin"
ExecStart=${VENV_DIR}/bin/python3 -m http.server ${DOCS_PORT} --directory ${MKDOCS_SITE_DIR}
StandardOutput=journal
StandardError=journal
SyslogIdentifier=qopz-docs

[Install]
WantedBy=multi-user.target
EOF
ok "Service qopz-docs creato"

# ── 9. Abilita e avvia services ──────────────────────────────────────────────
log "9/9 · Abilitazione servizi systemd..."
systemctl daemon-reload
systemctl enable qopz-api qopz-docs
systemctl start qopz-docs  # FastAPI parte solo se il codice è presente

# Verifica stato
sleep 2
if systemctl is-active --quiet qopz-docs; then
    ok "qopz-docs RUNNING su :${DOCS_PORT}"
else
    warn "qopz-docs non avviato — verifica: journalctl -u qopz-docs -n 20"
fi

# Mostra info finale
PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || echo "N/A")

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║               SETUP COMPLETATO  ✓                       ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║${NC}  IP Pubblico   : ${CYAN}${PUBLIC_IP}${NC}"
echo -e "${GREEN}║${NC}  FastAPI       : ${CYAN}http://${PUBLIC_IP}:${FASTAPI_PORT}${NC}"
echo -e "${GREEN}║${NC}  Docs          : ${CYAN}http://${PUBLIC_IP}:${DOCS_PORT}${NC}"
echo -e "${GREEN}║${NC}  App dir       : ${APP_DIR}"
echo -e "${GREEN}║${NC}  Venv          : ${VENV_DIR}"
echo -e "${GREEN}║${NC}  Token file    : ${TOKEN_FILE}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  API TOKEN (conserva in luogo sicuro!):                  ║${NC}"
echo -e "${YELLOW}║  ${API_TOKEN}  ${GREEN}║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  Comandi utili:                                          ║${NC}"
echo -e "${GREEN}║${NC}  systemctl start qopz-api      → avvia FastAPI"
echo -e "${GREEN}║${NC}  systemctl status qopz-api     → stato"
echo -e "${GREEN}║${NC}  journalctl -u qopz-api -f     → log live"
echo -e "${GREEN}║${NC}  systemctl restart qopz-docs   → rebuild docs"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}PROSSIMO PASSO:${NC} Sincronizza il codice da Windows con sync_to_vm.ps1"
echo -e "poi: ${CYAN}systemctl start qopz-api${NC}"
