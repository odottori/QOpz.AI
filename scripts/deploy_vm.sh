#!/usr/bin/env bash
# =============================================================================
# QOpz.AI — VM deploy script (Hetzner / any Ubuntu 22.04+)
# Usage: bash deploy_vm.sh [TWS_HOST]
#   TWS_HOST: IP of the machine running TWS/IBG (default: 127.0.0.1)
#             Use your local PC public IP if TWS runs locally.
# =============================================================================
set -euo pipefail

TWS_HOST="${1:-127.0.0.1}"
REPO_URL="https://github.com/odottori/QOpz.AI.git"
APP_DIR="/opt/qopz"
DB_DIR="/data/qopz/db"
LOGS_DIR="/data/qopz/logs"
IMAGE="qopz-api:latest"
CONTAINER="qopz-api"
PORT=8765

echo "=== QOpz.AI deploy ==="
echo "TWS host: $TWS_HOST"
echo "App dir:  $APP_DIR"
echo ""

# ── 1. Docker ─────────────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
  echo "[1/6] Installing Docker..."
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
else
  echo "[1/6] Docker already installed: $(docker --version)"
fi

# ── 2. Clone / update repo ────────────────────────────────────────────────────
echo "[2/6] Cloning/updating repo..."
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull --ff-only
else
  git clone "$REPO_URL" "$APP_DIR"
fi

# ── 3. Create persistent dirs ─────────────────────────────────────────────────
echo "[3/6] Creating data directories..."
mkdir -p "$DB_DIR" "$LOGS_DIR"

# ── 4. Patch paper.toml broker host ───────────────────────────────────────────
echo "[4/6] Setting broker host → $TWS_HOST"
TOML="$APP_DIR/config/paper.toml"
# Replace host line under [broker] section
sed -i "s|^host\s*=.*|host      = \"$TWS_HOST\"|" "$TOML"
grep "^host" "$TOML"

# ── 5. Build Docker image ─────────────────────────────────────────────────────
echo "[5/6] Building Docker image (this takes ~2-3 min on first run)..."
docker build -t "$IMAGE" "$APP_DIR"

# ── 6. Run container ──────────────────────────────────────────────────────────
echo "[6/6] Starting container..."
docker stop "$CONTAINER" 2>/dev/null || true
docker rm   "$CONTAINER" 2>/dev/null || true

# Genera token se non già presente in .env
TOKEN_FILE="$APP_DIR/.env"
if [ -f "$TOKEN_FILE" ] && grep -q "OPZ_API_TOKEN=" "$TOKEN_FILE"; then
  API_TOKEN=$(grep "OPZ_API_TOKEN=" "$TOKEN_FILE" | cut -d= -f2)
else
  API_TOKEN=$(openssl rand -hex 24)
  echo "OPZ_API_TOKEN=$API_TOKEN" >> "$TOKEN_FILE"
fi

docker run -d \
  --name "$CONTAINER" \
  --restart unless-stopped \
  -p "${PORT}:${PORT}" \
  -v "${DB_DIR}:/app/db" \
  -v "${LOGS_DIR}:/app/logs" \
  -e OPZ_PROFILE=paper \
  -e OPZ_DATA_MODE=VENDOR_REAL_CHAIN \
  -e "OPZ_API_TOKEN=${API_TOKEN}" \
  "$IMAGE"

echo ""
echo "=== Done ==="
echo "Container: $CONTAINER"
echo "API:       http://$(hostname -I | awk '{print $1}'):${PORT}/health"
echo "Console:   http://$(hostname -I | awk '{print $1}'):${PORT}/console"
echo "Token:     $API_TOKEN"
echo "Logs:      docker logs -f $CONTAINER"
echo ""
echo "IMPORTANT: TWS paper must be running on $TWS_HOST"
echo "           with API connections enabled (port 7496)"
