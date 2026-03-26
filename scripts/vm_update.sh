#!/usr/bin/env bash
# =============================================================================
# QOpz.AI - Oracle Cloud VM Update Script
# Ubuntu 22.04 LTS | ARM64
#
# Usage:
#   chmod +x scripts/vm_update.sh && sudo bash scripts/vm_update.sh
#
# Performs OS updates, Git/Docker updates, docs rebuild, service reload,
# and installs/updates cron for automatic morning and EOD sessions.
# =============================================================================

set -euo pipefail

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

log()  { echo -e "${CYAN}[UPDATE]${NC} $*"; }
ok()   { echo -e "${GREEN}[  OK  ]${NC} $*"; }
warn() { echo -e "${YELLOW}[ WARN ]${NC} $*"; }
fail() { echo -e "${RED}[ FAIL ]${NC} $*"; exit 1; }

# Config
APP_USER="${APP_USER:-ubuntu}"
APP_DIR="/home/${APP_USER}/qopz"
VENV_DIR="${APP_DIR}/.venv"
DOCS_PORT=8080
FASTAPI_PORT=8765
CRON_FILE="/etc/cron.d/qopz-sessions"
SESSION_SCHEDULER_MODE="${SESSION_SCHEDULER_MODE:-internal}"  # internal | external

echo ""
echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE} QOpz.AI - VM Update${NC}"
echo -e "${BLUE} Ubuntu 22.04 ARM64 | $(date +%Y-%m-%d)${NC}"
echo -e "${BLUE}============================================================${NC}"
echo ""

# 1) OS packages
log "1/7 - OS update..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq
ok "OS updated"

# 2) Git update (ppa:git-core/ppa)
log "2/7 - Git update..."
if ! apt-cache policy | grep -q "ppa.launchpadcontent.net/git-core/ppa"; then
  apt-get install -y -qq software-properties-common
  add-apt-repository -y ppa:git-core/ppa
  apt-get update -qq
fi
apt-get install -y -qq git
ok "Git: $(git --version 2>/dev/null || echo 'installed')"

# 3) Docker engine + compose plugin
log "3/7 - Docker update..."
if ! command -v docker >/dev/null 2>&1; then
  apt-get install -y -qq ca-certificates curl gnupg
  install -d -m 0755 /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
fi
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable docker
systemctl restart docker
usermod -aG docker "${APP_USER}" || true
ok "Docker updated and running"

# 4) Rebuild docs
log "4/7 - Rebuild docs..."
if [ -d "${VENV_DIR}" ] && [ -f "${APP_DIR}/mkdocs.yml" ]; then
  sudo -u "${APP_USER}" bash -lc "cd '${APP_DIR}' && '${VENV_DIR}/bin/mkdocs' build -d '${APP_DIR}/docs_site' -q"
  ok "Docs rebuilt"
else
  warn "Missing venv or mkdocs.yml - skip docs build"
fi

# 5) Reload/restart services
log "5/7 - Reload/restart services..."
systemctl daemon-reload
if systemctl list-units --type=service | grep -q qopz-docs.service; then
  systemctl restart qopz-docs || warn "restart qopz-docs failed"
fi
if systemctl list-units --type=service | grep -q qopz-api.service; then
  systemctl restart qopz-api || warn "restart qopz-api failed"
fi
ok "Services reloaded"

# 6) Automatic sessions scheduling mode
log "6/7 - Configure automatic sessions mode (${SESSION_SCHEDULER_MODE})..."
if [ "${SESSION_SCHEDULER_MODE}" = "external" ]; then
  cat > "${CRON_FILE}" << CRON_EOF
# QOpz.AI - Automatic sessions (UTC), weekdays only.
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Morning - 14:15 UTC (09:15 EST)
15 14 * * 1-5 curl -s -X POST -H "Content-Type: application/json" -d '{"type":"morning","profile":"paper"}' http://127.0.0.1:${FASTAPI_PORT}/opz/session/run >/var/log/qopz_cron_morning.log 2>&1
# EOD - 21:15 UTC (16:15 EST)
15 21 * * 1-5 curl -s -X POST -H "Content-Type: application/json" -d '{"type":"eod","profile":"paper"}' http://127.0.0.1:${FASTAPI_PORT}/opz/session/run >/var/log/qopz_cron_eod.log 2>&1
CRON_EOF
  chmod 644 "${CRON_FILE}"
  ok "External cron installed at ${CRON_FILE}"
else
  if [ -f "${CRON_FILE}" ]; then
    rm -f "${CRON_FILE}"
    ok "Removed legacy external cron (${CRON_FILE}); internal scheduler will be used"
  else
    ok "No external cron file present; internal scheduler remains active"
  fi
fi

# 7) Summary
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN} UPDATE COMPLETED${NC}"
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN} FastAPI:${NC} http://127.0.0.1:${FASTAPI_PORT}"
echo -e "${GREEN} Docs:${NC}    http://127.0.0.1:${DOCS_PORT}"
echo -e "${GREEN} Docker:${NC}  $(docker --version 2>/dev/null || echo 'installed')"
echo -e "${GREEN} Git:${NC}     $(git --version 2>/dev/null || echo 'installed')"
echo -e "${GREEN} Note:${NC} docker group membership is effective after next login"
echo -e "${GREEN} Scheduler mode:${NC} ${SESSION_SCHEDULER_MODE}"
echo -e "${GREEN} Cron file:${NC} ${CRON_FILE}"
echo ""
