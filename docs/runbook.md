# SISI Health — operations runbook

Audience: whoever holds the VPS, the secrets and the pager. Read
`docs/backup-restore-drill.md` before your first restore and
`docs/breach-runbook.md` before your first incident.

> **Scope note.** Phases 1–7 and the Phase 8 ops tooling are built and verified on a
> development machine. **No VPS has been provisioned and no staging/prod stack has been
> deployed yet** (human task H17). Everything below is the procedure; the commands are
> real and have been validated with `docker compose config`, but the live deployment is
> still a human task. Nothing in this document should be read as evidence that a
> production environment exists.

## 1. What runs where

| Service | Image / build | Port | Public path | Notes |
|---|---|---|---|---|
| `caddy` | `caddy:2` | 80, 443 | everything | Only service with published ports. TLS 1.3. |
| `web` | `./web` (node build → nginx) | 80 (internal) | `/` | Staff console SPA. |
| `backend` | `./backend` | 8000 (internal) | `/v1/*`, `/api/*` | FastAPI + Alembic. |
| `gateway` | `./ussd-whatsapp` (repo-root context) | 8001 (internal) | `/ussd/*`, `/whatsapp/*`, `/gateway/*` | USSD + WhatsApp. |
| `ai` | `./ai_service` (repo-root context) | 8002 (internal) | `/v1/ai/*`, `/ai/*` | Internal, bearer-token gated. |
| `db` | `pgvector/pgvector:pg16-alpine` | 5432 (internal only) | — | No host port. |
| `redis` | `redis:7-alpine` | 6379 (internal only) | — | USSD session state. |

The ontology directory (`./ontology`) is bind-mounted read-only into `backend`,
`gateway` and `ai` at `/srv/ontology` (`SISI_ONTOLOGY_DIR`). It is deployment content,
not code: updating rules or education content is a content release, not an image build.

## 2. Prerequisites

- A Linux host with Docker Engine and the Compose plugin.
- DNS: an A/AAAA record for `SISI_DOMAIN` pointing at the host, ports 80 and 443 open
  (Caddy needs 80 for the ACME HTTP challenge and the HTTPS redirect).
- A filled `.env.prod` (see `.env.prod.example`). Store it in the operator's secret
  manager, not in the repo checkout if you can avoid it.
- The master key (`SISI_MASTER_KEY_B64`) backed up **separately** from any database
  backup. See §6.

## 3. First provisioning (human task H17)

1. Create the host, install Docker, point DNS.
2. Clone the repo at the release tag, `cp .env.prod.example .env.prod`, fill every value.
3. Generate the secrets with a CSPRNG — never reuse a dev default:
   ```sh
   python3 -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"
   ```
   Use a different value per secret. `SISI_MASTER_KEY_B64` must be 32 bytes, base64.
4. Confirm the hotline numbers (§9) and set `SISI_HELPLINE_CHILD` / `SISI_HELPLINE_GBV`.
5. Run `./scripts/deploy.sh staging` and execute the smoke test in §5.
6. Only after staging is green: `./scripts/deploy.sh prod`.

## 4. Deploy

### One command

```sh
./scripts/deploy.sh staging          # Linux/macOS/CI
# --dry-run shows what it would do and runs the safety gates without touching Docker

.\scripts\deploy.ps1 staging         # Windows
.\scripts\deploy.ps1 prod -DryRun
```

The script:

1. resolves the environment (`staging`/`prod` argument or `SISI_DEPLOY_ENV`);
2. loads `.env.prod.<env>` if present, else `.env.prod`;
3. **refuses** if `SISI_ALLOW_UNVALIDATED_RULES=true`, `SISI_OTP_DEV_RETURN=true`, a
   development-default secret is still in place, or a required secret is empty;
4. `docker compose -f docker-compose.prod.yml --profile <env> up -d --build`;
5. `docker compose ... run --rm backend alembic upgrade head`;
6. polls the container health checks for up to 300 s, then prints the URLs.

> The `SISI_ALLOW_UNVALIDATED_RULES=false` and `SISI_OTP_DEV_RETURN=false` values are
> **hard-coded** in `docker-compose.prod.yml`, not taken from the environment. A filled
> `.env.prod` cannot turn unvalidated clinical rules on for real users.

### Manual equivalent

```sh
export SISI_DEPLOY_ENV=staging
set -a; . ./.env.prod; set +a
docker compose -f docker-compose.prod.yml --profile staging up -d --build
docker compose -f docker-compose.prod.yml --profile staging run --rm backend alembic upgrade head
docker compose -f docker-compose.prod.yml --profile staging ps
```

### Validate before deploying

`docker compose config` needs no daemon and no secrets:

```sh
docker compose -f docker-compose.prod.yml config >/dev/null                 # platform only
docker compose -f docker-compose.prod.yml --profile staging config >/dev/null
docker compose -f docker-compose.prod.yml --profile prod    config >/dev/null
docker compose -f docker-compose.yml config >/dev/null                       # dev stack
```

Validate the edge config after any Caddyfile edit:

```sh
docker run --rm -e SISI_DOMAIN=localhost -e SISI_ACME_EMAIL=ops@example.org \
  -v "$PWD/deploy/Caddyfile:/etc/caddy/Caddyfile:ro" \
  caddy:2 caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker compose -f docker-compose.prod.yml exec caddy caddy reload --config /etc/caddy/Caddyfile
```

## 5. Post-deploy smoke test

```sh
curl -fsS https://$SISI_DOMAIN/health              # edge: Caddy answers "ok"
curl -fsS https://$SISI_DOMAIN/v1/health           # backend: {"success":true,...}
curl -fsS https://$SISI_DOMAIN/ | head -5          # staff console HTML

# The AI service is internal-only: without the bearer token it must never answer 200.
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://$SISI_DOMAIN/v1/ai/ask
# expected: 401 (missing/invalid SISI_AI_INTERNAL_TOKEN)
```

Then, in a browser:

1. open `https://$SISI_DOMAIN/`, log in as a staff user (password + TOTP);
2. confirm the dashboard loads;
3. confirm the USSD sandbox callback reaches `/ussd/callback` if the channel is live.

Check container health:

```sh
docker compose -f docker-compose.prod.yml --profile staging ps
docker compose -f docker-compose.prod.yml --profile staging logs --tail=100 backend
```

## 6. Backup and restore

### Schedule (human task H17)

Nightly, on the host, from cron/systemd-timer:

```sh
cd /srv/sisi && backend/.venv/bin/python scripts/backup_db.py
# then copy .backups/sisi-<ts>.dump.enc off-host (object storage) with a retention
# window that matches the policy in docs/assumptions.md
```

The backup is `pg_dump --format=custom`, AES-256-GCM encrypted under the envelope
master key, written to `.backups/sisi-<utc-ts>.dump.enc`. `.backups/` is gitignored.

**Key custody:** the dump is useless without `SISI_MASTER_KEY_B64`. Store the master key
in the secret manager / Vault, and keep the off-host backups in a different trust domain
from the key. Restore the key first.

### Restore

```sh
# 1. Rehearse against a scratch database FIRST (this is the drill, repeated):
backend/.venv/bin/python scripts/restore_db.py --yes --create-db \
  --target-url "postgresql+psycopg://sisi:<pw>@db:5432/sisi_restore_test"

# 2. Compare row counts per table, and verify the audit chain:
SISI_DATABASE_URL="postgresql+psycopg://sisi:<pw>@db:5432/sisi_restore_test" \
  backend/.venv/bin/python backend/scripts/verify_audit_chain.py

# 3. Only then restore over the live database:
backend/.venv/bin/python scripts/restore_db.py --yes
```

`restore_db.py` uses `pg_restore --clean --if-exists`: it drops and recreates every
object in the target. It refuses without `--yes` and prints the redacted target first.
The full procedure with observed counts is in `docs/backup-restore-drill.md`.

The Make targets wrap the same scripts: `make backup`, `make restore`.

## 7. Migrations

- Alembic, forward-only. Every migration is reviewed with a rollback note
  (`AGENTS.md` §2).
- `docker compose ... run --rm backend alembic upgrade head` is part of the deploy.
- Never edit an applied migration. To roll back a bad release, restore the previous
  image **and** the database backup taken immediately before the migration if the
  migration was destructive.

## 8. Logs

| What | Where |
|---|---|
| Container stdout/stderr | `docker compose -f docker-compose.prod.yml logs -f <service>` |
| Caddy access log (JSON) | `caddy_data` volume → `/data/access.log` (100 MB × 10 rotations) |
| Application structured logs | stdout of each container, collected by the host's log driver |
| Audit trail (not a log) | `audit.audit_events` in PostgreSQL, hash-chained |

**Never log:** diary content, phone numbers, names, condition names, risk scores tied
to a person. Non-negotiable 4. The audit writer scrubs phone-like digit runs and
forbidden keys (`backend/app/audit/service.py:39` `sanitize_payload`); the edge access
log records method/path/status only.

Nightly audit-chain verification:

```sh
docker compose -f docker-compose.prod.yml --profile prod exec backend \
  python scripts/verify_audit_chain.py
```

A non-zero exit means a chain break — treat it as a security incident (§10).

## 9. Hotline configuration checks — UNVERIFIED

`SISI_HELPLINE_CHILD=116` and `SISI_HELPLINE_GBV=1195` are the numbers recorded in the
spec and shipped in config. **Both are UNVERIFIED.** Before launch, and at every
release that touches them:

1. Call each number from a Kenyan phone and confirm the service and language coverage.
2. Confirm the number that is shown to a **minor in a safeguarding escalation** is the
   child helpline, and the GBV number for sexual-violence flows.
3. Confirm the numbers still work out of hours.
4. Record the date, who verified, and the result in `docs/human-tasks.md`.
5. Update `SISI_HELPLINE_CHILD` / `SISI_HELPLINE_GBV` in `.env.prod` (config, never
   code) and redeploy.

An unverified number shown to a child in crisis is a safety defect, not a cosmetic one.

## 10. Incident escalation

**Severity 1 — suspected data breach, audit-chain break, or a safety failure**
(a wrong band assigned, a red-flag script not firing, an unvalidated rule enabled).
1. Page the maintainer immediately.
2. Preserve evidence: do **not** restart containers that would discard logs, do not
   prune volumes; snapshot the database (`pg_dump`) to a secure location.
3. Follow `docs/breach-runbook.md` for the 72-hour ODPC notification path, evidence
   preservation and comms templates.
4. Rotate any secret that may have been exposed (`SISI_JWT_SECRET`,
   `SISI_MASTER_KEY_B64`, `SISI_AI_INTERNAL_TOKEN`, provider tokens) — rotating the
   master key requires a re-wrap of `core.data_keys`; treat it as a planned operation,
   not a hotfix.

**Severity 2 — service down or degraded.** Check `docker compose ps`, then the service
logs, then `db`/`redis` health. Roll back per §11 if the failure followed a deploy.

**Severity 3 — single-channel failure** (e.g. Africa's Talking outage). The app keeps
serving; note it and inform the maintainer.

Escalation contacts belong in the operator's on-call system, not in this repository.
The maintainer is the final escalation point for anything touching safety or privacy
(`AGENTS.md` §1.9: when in doubt, ask the maintainer — do not guess).

## 11. Rollback

Images are built locally by compose, so "the previous image" means **the previous git
tag plus the previous `.env.prod`** — there is no registry tag to re-pull in this
deployment model.

### Case A — the failed release applied no new migration

```sh
git checkout <previous-release-tag>
./scripts/deploy.sh prod
```

`alembic upgrade head` is a no-op because the older code's head is already applied.

### Case B — the failed release applied a new migration

Migrations are forward-only, so rolling the image back does **not** roll the schema
back, and `alembic upgrade head` under the older code will fail because the database is
ahead of the code's head. Restore the database backup taken immediately before the
deploy (`scripts/restore_db.py`, rehearsed first per §6), **then** check out the
previous tag and redeploy.

If you must run the previous code against the newer schema (only safe when the migration
was additive), skip the migration step entirely:

```sh
git checkout <previous-release-tag>
export SISI_DEPLOY_ENV=prod
set -a; . ./.env.prod; set +a
docker compose -f docker-compose.prod.yml --profile prod up -d --build
# intentionally NOT running: run --rm backend alembic upgrade head
```

The deploy script does not expose a skip-migration flag: migrating is the safe default,
and skipping it is a deliberate manual act.

### Stop everything

```sh
docker compose -f docker-compose.prod.yml --profile prod down       # keeps volumes
docker compose -f docker-compose.prod.yml --profile prod down -v    # DESTROYS pgdata
```

`down -v` deletes the database volume. **Only** use it on a scratch stack, or after a
verified backup and with the maintainer's explicit approval.

## 12. Admin surface

Caddy proxies `/v1/admin/**` to the backend like any other route. Those endpoints are
protected by the backend's RBAC (`super_admin`) and staff TOTP — not by network
policy. If you want to block them at the edge instead, add a `handle /v1/admin/*`
that returns 403 **above** the `/v1/*` block in `deploy/Caddyfile`, and note that the
admin tooling then needs a different access path (VPN/bastion). This is a deliberate
maintainer decision, not a default.

## 13. Common boot failures (prod guards)

The application refuses to start rather than serving traffic with a dev default. The
error name tells you what to fix:

| Container log | Meaning |
|---|---|
| `SISI_ALLOW_UNVALIDATED_RULES must be false in staging/prod` | A dev flag leaked in. Compose hard-codes it false — check you are not overriding it. |
| `SISI_OTP_DEV_RETURN must be false in staging/prod` | Same. |
| `SISI_JWT_SECRET must be set in staging/prod` | Empty or dev default in `.env.prod`. |
| `SISI_PHONE_PEPPER must be set in staging/prod` | Same. |
| `SISI_JITSI_APP_SECRET must be set in staging/prod` | Same. |
| `SISI_MASTER_KEY_B64 must be set in staging/prod` | Empty. Generate 32 random bytes, base64. |
| `SISI_CORS_ORIGINS must be set in staging/prod` | Empty comma list. |
| `SISI_AI_LLM_PROVIDER must not be 'stub' in staging/prod` | AI service still on the deterministic stub. |
| `SISI_AI_INTERNAL_TOKEN must be set in staging/prod` | Empty or dev default. |
| `Database is uninitialized and superuser password is not specified` | `SISI_DB_PASSWORD` is empty. |
| Caddy: `parsing caddyfile tokens for 'email'` | `SISI_ACME_EMAIL` was passed as an empty string. Compose supplies a placeholder default; do not blank it. |

## 14. What is not yet proven

- **No live deploy has been performed.** `docker compose config` and `caddy validate`
  pass, the images build from the Dockerfiles in this repo, but nothing has been run on
  a VPS.
- **Backups are not scheduled and not off-host.** The scripts and the drill are real;
  the cron job, object-storage copy and retention policy are H17.
- **Third-party penetration test is outstanding** — human task H8. See
  `docs/pen-test-checklist.md` for the self-assessment that will hand over to it.
- **Load testing**: see `docs/load-test-report.md` when Agent E's run is recorded.
- **Provider go-live** (Africa's Talking, Turn.io/WhatsApp, Jitsi, LLM/embedding) are
  human tasks H2–H4, H12, H15. The prod guards refuse to start with stub providers.
