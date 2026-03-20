#!/usr/bin/env bash
# =============================================================================
# QOpz.AI — VM deploy script (Hetzner / any Ubuntu 22.04+)
# Usage: bash deploy_vm.sh [TWS_HOST] [NGINX_PASSWORD]
#   TWS_HOST:       IP of the machine running TWS/IBG (default: 127.0.0.1)
#   NGINX_PASSWORD: password for basic auth (generated if omitted)
# =============================================================================
set -euo pipefail

TWS_HOST="${1:-127.0.0.1}"
REPO_URL="https://github.com/odottori/QOpz.AI.git"
APP_DIR="/opt/qopz"
IMAGE_API="qopz-api:latest"
IMAGE_NGINX="qopz-nginx:latest"

echo "=== QOpz.AI deploy ==="
echo "TWS host: $TWS_HOST"
echo "App dir:  $APP_DIR"
echo ""

# ── 1. Docker + Compose ───────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
  echo "[1/5] Installing Docker..."
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
else
  echo "[1/5] Docker already installed: $(docker --version)"
fi

if ! docker compose version &>/dev/null; then
  echo "[1/5] Installing docker-compose plugin..."
  apt-get install -y docker-compose-plugin
fi

# ── 2. Clone / update repo ────────────────────────────────────────────────────
echo "[2/5] Cloning/updating repo..."
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull --ff-only
else
  git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

# ── 3. Patch paper.toml broker host ───────────────────────────────────────────
echo "[3/5] Setting broker host → $TWS_HOST"
TOML="$APP_DIR/config/paper.toml"
sed -i "s|^host\s*=.*|host      = \"$TWS_HOST\"|" "$TOML"
grep "^host" "$TOML"

# ── 4. Genera .env ────────────────────────────────────────────────────────────
echo "[4/5] Configuring .env..."
ENV_FILE="$APP_DIR/.env"

if [ -f "$ENV_FILE" ] && grep -q "NGINX_PASSWORD=" "$ENV_FILE"; then
  NGINX_PASSWORD=$(grep "NGINX_PASSWORD=" "$ENV_FILE" | cut -d= -f2-)
else
  NGINX_PASSWORD="${2:-$(openssl rand -hex 16)}"
  cat > "$ENV_FILE" <<EOF
OPZ_PROFILE=paper
OPZ_DATA_MODE=VENDOR_REAL_CHAIN
NGINX_USER=opz
NGINX_PASSWORD=${NGINX_PASSWORD}
NGINX_PORT=80
EOF
fi

# ── 5. Build + avvia con docker compose ───────────────────────────────────────
echo "[5/6] Ensuring IBG settings permissions..."
mkdir -p "$APP_DIR/data/ibg-settings"
chown -R 1000:1000 "$APP_DIR/data/ibg-settings" || true
chmod -R ug+rwX "$APP_DIR/data/ibg-settings" || true

echo "[6/6] Building images and starting services..."
docker compose build
docker compose up -d

wait_service_healthy() {
  local svc="$1"
  local timeout="${2:-180}"
  local elapsed=0

  while [ "$elapsed" -lt "$timeout" ]; do
    local cid
    cid="$(docker compose ps -q "$svc" 2>/dev/null || true)"
    if [ -n "$cid" ]; then
      local state health
      state="$(docker inspect -f '{{.State.Status}}' "$cid" 2>/dev/null || true)"
      health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cid" 2>/dev/null || true)"
      if [ "$state" = "running" ] && { [ "$health" = "healthy" ] || [ "$health" = "none" ]; }; then
        echo "  [ok] ${svc} ready (state=${state}, health=${health})"
        return 0
      fi
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done

  echo "  [fail] ${svc} not ready within ${timeout}s"
  docker compose ps "$svc" || true
  return 1
}

echo "[6/6] Waiting service health..."
wait_service_healthy api 180
wait_service_healthy ibg 240
wait_service_healthy nginx 120

echo ""
echo "=== Done ==="
PUBLIC_IP=$(hostname -I | awk '{print $1}')
echo "Console:  http://${PUBLIC_IP}/console"
echo "Guida:    http://${PUBLIC_IP}/guide"
echo "Health:   http://${PUBLIC_IP}/health"
echo ""
echo "Credenziali accesso:"
echo "  Utente:   opz"
echo "  Password: ${NGINX_PASSWORD}"
echo ""
echo "Logs: docker compose logs -f"
echo ""
echo "IMPORTANT: TWS paper must be running on $TWS_HOST"
echo "           with API connections enabled (port 7496)"
