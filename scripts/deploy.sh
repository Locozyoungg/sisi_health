#!/bin/sh
# SISI Health — one-command staging/prod deploy (Linux/macOS/CI).
#
#   ./scripts/deploy.sh staging
#   ./scripts/deploy.sh prod --dry-run
#
# What it does, in order:
#   1. resolves the target environment (argument, else $SISI_DEPLOY_ENV)
#   2. loads .env.prod.<env> when present, otherwise .env.prod
#   3. REFUSES to continue if a development flag or a development-default secret is
#      still in place (non-negotiables 3 and 7) or a required secret is empty
#   4. docker compose -f docker-compose.prod.yml --profile <env> up -d --build
#   5. docker compose ... run --rm backend alembic upgrade head
#   6. waits for the backend/gateway/ai health checks, then prints the URLs
#
# --dry-run performs steps 1-3 and prints the commands instead of running them.
# See docs/runbook.md for rollback, backups and incident escalation.
set -eu

REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
COMPOSE_FILE="docker-compose.prod.yml"
DRY_RUN=0
DEPLOY_ENV=""

for arg in "$@"; do
    case "$arg" in
        staging|prod) DEPLOY_ENV="$arg" ;;
        --dry-run)    DRY_RUN=1 ;;
        -h|--help)
            echo "usage: $0 <staging|prod> [--dry-run]"
            exit 0
            ;;
        *)
            echo "[deploy] unknown argument: $arg" >&2
            echo "usage: $0 <staging|prod> [--dry-run]" >&2
            exit 2
            ;;
    esac
done

[ -n "$DEPLOY_ENV" ] || DEPLOY_ENV="${SISI_DEPLOY_ENV:-}"
case "$DEPLOY_ENV" in
    staging|prod) ;;
    "")
        echo "[deploy] REFUSING: pass staging|prod (or set SISI_DEPLOY_ENV)." >&2
        echo "         Nothing was deployed." >&2
        exit 2
        ;;
    *)
        echo "[deploy] REFUSING: SISI_DEPLOY_ENV='$DEPLOY_ENV' is not staging|prod." >&2
        exit 2
        ;;
esac
export SISI_DEPLOY_ENV="$DEPLOY_ENV"

refuse() {
    echo "[deploy] REFUSING: $1" >&2
    echo "         Nothing was deployed. Fix the value in your env file and re-run." >&2
    exit 1
}

# --- 2. environment file ---------------------------------------------------
ENV_FILE="$REPO_ROOT/.env.prod.$DEPLOY_ENV"
[ -f "$ENV_FILE" ] || ENV_FILE="$REPO_ROOT/.env.prod"
if [ ! -f "$ENV_FILE" ]; then
    echo "[deploy] REFUSING: no .env.prod.$DEPLOY_ENV or .env.prod in $REPO_ROOT." >&2
    echo "         Copy .env.prod.example and fill every value first." >&2
    exit 2
fi

# The file is source'd, so it must be plain KEY=value lines (no inline comments with
# spaces, no shell syntax). .env.prod.example follows that format.
set -a
# shellcheck disable=SC1090  # path is computed above
. "$ENV_FILE"
set +a

echo "[deploy] environment: $DEPLOY_ENV"
echo "[deploy] env file:    $ENV_FILE (values not printed)"

# --- 3. safety gates -------------------------------------------------------
[ "${SISI_ALLOW_UNVALIDATED_RULES:-false}" = "true" ] && \
    refuse "SISI_ALLOW_UNVALIDATED_RULES=true — unvalidated clinical rules must never run for real users (non-negotiable 3)."
[ "${SISI_OTP_DEV_RETURN:-false}" = "true" ] && \
    refuse "SISI_OTP_DEV_RETURN=true — returning OTPs in API responses is dev/demo only."

for flag in SISI_ALLOW_UNVALIDATED_RULES SISI_OTP_DEV_RETURN; do
    eval "value=\${$flag:-}"
    if [ -n "$value" ] && [ "$value" != "false" ]; then
        refuse "$flag='$value' — only 'false' is accepted in staging/prod."
    fi
done

[ "${SISI_JWT_SECRET:-}" = "dev-only-secret-change-me-32-bytes-minimum!" ] && \
    refuse "SISI_JWT_SECRET is still the development default."
[ "${SISI_PHONE_PEPPER:-}" = "dev-only-pepper-change-me" ] && \
    refuse "SISI_PHONE_PEPPER is still the development default."
[ "${SISI_JITSI_APP_SECRET:-}" = "dev-only-jitsi-secret-change-me" ] && \
    refuse "SISI_JITSI_APP_SECRET is still the development default."
[ "${SISI_AI_INTERNAL_TOKEN:-}" = "dev-only-ai-token-change-me" ] && \
    refuse "SISI_AI_INTERNAL_TOKEN is still the development default."

REQUIRED="SISI_DOMAIN SISI_DB_PASSWORD SISI_JWT_SECRET SISI_PHONE_PEPPER"
REQUIRED="$REQUIRED SISI_MASTER_KEY_B64 SISI_JITSI_APP_SECRET SISI_AI_INTERNAL_TOKEN"
for key in $REQUIRED; do
    eval "value=\${$key:-}"
    [ -n "$value" ] || refuse "$key is empty — it is required in staging/prod."
done

# =============================================================================
# The compose invocations. Kept in one place so the dry run and the real run can
# never drift apart.
COMPOSE="docker compose -f $COMPOSE_FILE --profile $DEPLOY_ENV"

if [ "$DRY_RUN" = "1" ]; then
    echo "[deploy] DRY RUN — safety gates passed. Would run:"
    echo "  cd $REPO_ROOT"
    echo "  $COMPOSE up -d --build"
    echo "  $COMPOSE run --rm backend alembic upgrade head"
    echo "  (then wait for health: backend /v1/health, gateway /health, ai /health)"
    echo "[deploy] URLs that would be printed: https://${SISI_DOMAIN}/ , https://${SISI_DOMAIN}/v1/health"
    exit 0
fi

cd "$REPO_ROOT"

# --- 4. build and start ----------------------------------------------------
echo "[deploy] building and starting the $DEPLOY_ENV stack..."
# shellcheck disable=SC2086  # COMPOSE is a deliberate word-split command line
$COMPOSE up -d --build

# --- 5. migrations ---------------------------------------------------------
echo "[deploy] applying migrations (alembic upgrade head)..."
# shellcheck disable=SC2086
$COMPOSE run --rm backend alembic upgrade head

# --- 6. health checks ------------------------------------------------------
echo "[deploy] waiting for container health checks (up to 300s)..."
SERVICES="backend gateway ai"
WAITED=0
while [ "$WAITED" -lt 300 ]; do
    PENDING=""
    for svc in $SERVICES; do
        # shellcheck disable=SC2086
        cid=$($COMPOSE ps -q "$svc" 2>/dev/null || true)
        if [ -z "$cid" ]; then
            PENDING="$PENDING $svc(not-running)"
            continue
        fi
        status=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid" 2>/dev/null || echo unknown)
        [ "$status" = "healthy" ] || [ "$status" = "running" ] || PENDING="$PENDING $svc($status)"
    done
    [ -z "$PENDING" ] && break
    sleep 5
    WAITED=$((WAITED + 5))
    echo "[deploy]   waiting:$PENDING"
done

if [ -n "${PENDING:-}" ]; then
    echo "[deploy] WARNING: services not healthy after 300s:$PENDING" >&2
    echo "[deploy] Inspect with: $COMPOSE ps ; $COMPOSE logs --tail=100 <service>" >&2
    exit 1
fi

echo "[deploy] $DEPLOY_ENV is up."
echo "[deploy]   console:      https://${SISI_DOMAIN}/"
echo "[deploy]   API health:   https://${SISI_DOMAIN}/v1/health"
echo "[deploy]   edge health:  https://${SISI_DOMAIN}/health"
echo "[deploy]   rollback:     docker compose -f $COMPOSE_FILE --profile $DEPLOY_ENV down"
