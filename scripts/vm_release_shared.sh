#!/usr/bin/env bash
# Run from an immutable Git worktree; never pull/reset the historical checkout.
set -euo pipefail
MODE="${1:-prepare}"
[[ "$MODE" == prepare || "$MODE" == activate ]] || exit 2
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REV="$(git -C "$ROOT" rev-parse HEAD)"
[[ "$ROOT" == "/opt/qopz/releases/$REV" ]] || { echo 'Invalid release path'; exit 2; }
[[ -z "$(git -C "$ROOT" status --porcelain --untracked-files=no)" ]] || { echo 'Dirty release source'; exit 2; }
BASE=/opt/qopz
ENV="$BASE/runtime/$REV.env"
mkdir -p "$BASE/runtime"
chmod 700 "$BASE/runtime"
exec 9> "$BASE/runtime/release.lock"
flock -n 9 || { echo 'Another QOpz release is running'; exit 75; }
[[ ! -e "$BASE/runtime/recovery-required.json" ]] || { echo 'Previous recovery incomplete; operator review required'; exit 2; }
ATTEMPT="$REV-$(date -u +%Y%m%dT%H%M%SZ)-$(openssl rand -hex 4)"
BACKUP="$BASE/backups/$ATTEMPT"
if [[ ! -f "$ENV" ]]; then
  umask 077
  cp "$BASE/.env" "$ENV"
  if ! grep -q '^CONTROL_API_TOKEN=.' "$ENV" || grep -q '^CONTROL_API_TOKEN=qopz-control-local$' "$ENV"; then
    printf '\nCONTROL_API_TOKEN=%s\n' "$(openssl rand -hex 32)" >> "$ENV"
  fi
  printf '\nNGINX_PORT=8080\nOPZ_RELEASE=%s\n' "$REV" >> "$ENV"
  chmod 600 "$ENV"
fi
for name in data ops; do
  [[ -d "$BASE/$name" ]] || { echo "Missing existing $name"; exit 2; }
  if [[ ! -e "$ROOT/$name" ]]; then ln -s "$BASE/$name" "$ROOT/$name"; fi
  # data/ contains tracked fixtures: use the existing data bind through override below.
done
OVERRIDE="$BASE/runtime/$REV.binds.yml"
printf 'services:\n  api:\n    volumes:\n      - /opt/qopz/data:/app/data\n      - /opt/qopz/ops:/app/ops\n  control-plane:\n    volumes:\n      - /opt/qopz/data:/app/data\n' > "$OVERRIDE"
compose() { docker compose -p qopz --env-file "$ENV" -f "$ROOT/docker-compose.yml" -f "$ROOT/docker/compose.shared.yml" -f "$OVERRIDE" "$@"; }
compose config --quiet
if [[ "$MODE" == prepare ]]; then
  compose build api nginx broker-proxy
  docker run --rm --network none --tmpfs /app/db --tmpfs /app/logs -e OPZ_PROFILE=dev --entrypoint python "qopz-api:$REV" \
    -c 'from execution.storage import init_execution_schema; from execution.wheel_storage import init_wheel_schema; init_execution_schema(); init_wheel_schema(); from api.opz_api import health; assert health()["status"] == "ok"; print("IMAGE_PREFLIGHT OK")'
  echo "PREPARED $REV"
  exit 0
fi
docker image inspect "qopz-api:$REV" "qopz-nginx:$REV" "qopz-broker-proxy:$REV" >/dev/null
docker exec qopz-api-1 python -c 'import json,urllib.request; d=json.load(urllib.request.urlopen("http://127.0.0.1:8765/opz/session/status")); assert not d.get("running"), "Session active; retry after completion"'
mkdir -p "$BACKUP"
chmod 700 "$BACKUP"
docker ps --format '{{.ID}}|{{.Names}}|{{.Image}}' > "$BACKUP/containers.before"
previous=(qopz-api-1 qopz-nginx-1 qopz-control-plane-1)
had_proxy=0
if docker container inspect qopz-broker-proxy-1 >/dev/null 2>&1; then
  previous+=(qopz-broker-proxy-1)
  had_proxy=1
fi
docker inspect "${previous[@]}" > "$BACKUP/containers.json"
for svc in api nginx control-plane; do
  docker image tag "$(docker inspect -f '{{.Image}}' "qopz-$svc-1")" "qopz-$svc:rollback-$ATTEMPT"
done
python3 "$ROOT/scripts/opz_deploy_snapshot.py" "$BACKUP/containers.json" "$BACKUP/rollback.compose.json"
docker compose -p qopz -f "$BACKUP/rollback.compose.json" config --quiet
if [[ -e "$BASE/current" && ! -L "$BASE/current" ]]; then echo 'current is not a symlink'; exit 2; fi
readlink "$BASE/current" > "$BACKUP/current-link.before" || true
if [[ -f "$BASE/current-release.json" ]]; then cp -p "$BASE/current-release.json" "$BACKUP/current-release.before.json"; fi
changed=0
rollback() {
  rc=$?
  trap - ERR
  echo "RELEASE FAILED rc=$rc; restoring previous services ($BACKUP)"
  recovered=1
  if [[ -f "$BACKUP/proxy-manifest.json" ]]; then python3 "$ROOT/scripts/install_shared_proxy.py" --backup "$BACKUP" --restore || recovered=0; fi
  if [[ "$changed" == 1 ]]; then
    docker compose -p qopz -f "$BACKUP/rollback.compose.json" up -d --no-deps --no-build --pull never || recovered=0
    if [[ "$had_proxy" == 0 ]]; then compose rm -s -f broker-proxy || recovered=0; fi
    if [[ "$recovered" == 1 ]]; then
      python3 "$ROOT/scripts/opz_deploy_snapshot.py" "$BACKUP/containers.json" --verify-running || recovered=0
    fi
  fi
  if [[ "$recovered" == 1 ]]; then
    python3 "$ROOT/scripts/opz_release_state.py" restore "$BASE" "$BACKUP" "$ROOT" || recovered=0
  fi
  if [[ "$recovered" != 1 ]]; then
    umask 077
    printf '{"status":"recovery_required","candidate":"%s","backup":"%s"}\n' "$REV" "$BACKUP" > "$BASE/runtime/recovery-required.json.tmp"
    mv "$BASE/runtime/recovery-required.json.tmp" "$BASE/runtime/recovery-required.json"
    echo 'ROLLBACK INCOMPLETE: release metadata is not authoritative; operator review required' >&2
  fi
  exit "$rc"
}
trap rollback ERR
changed=1
compose stop api
DB="$(docker volume inspect qopz_qopz-db -f '{{.Mountpoint}}')"
[[ "$DB" == /var/lib/docker/volumes/qopz_qopz-db/_data ]]
tar -czf "$BACKUP/db.tgz" -C "$DB" .
docker run --rm --network none --tmpfs /app/db --tmpfs /app/logs \
  -v "$BACKUP/db.tgz:/tmp/db.tgz:ro" -e OPZ_PROFILE=dev --entrypoint sh "qopz-api:$REV" \
  -c 'tar -xzf /tmp/db.tgz -C /app/db && python -c '\''from execution.storage import init_execution_schema; from execution.wheel_storage import init_wheel_schema; init_execution_schema(); init_wheel_schema(); print("EXISTING_DB_PREFLIGHT OK")'\'''
compose up -d --no-deps --no-build broker-proxy
compose up -d --no-deps --no-build api control-plane nginx
for svc in api control-plane nginx; do
  ready=0
  for ((n=0;n<90;n++)); do
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "qopz-$svc-1")"
    if [[ "$status" == healthy ]]; then ready=1; break; fi
    sleep 2
  done
  [[ "$ready" == 1 ]]
done
python3 "$ROOT/scripts/install_shared_proxy.py" --backup "$BACKUP"
curl --fail --silent http://127.0.0.1/qopz/health -H 'Host: 178.104.94.34' | python3 -c 'import json,sys; assert json.load(sys.stdin)["status"] == "ok"'
python3 "$ROOT/scripts/opz_release_state.py" publish "$BASE" "$BACKUP" "$ROOT" "$ENV"
trap - ERR
echo "RELEASE OK commit=$REV backup=$BACKUP"
