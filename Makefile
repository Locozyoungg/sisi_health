# SISI Health — Makefile (Linux/macOS/CI). Windows: use .\make.ps1 (same targets).
PY      := python3.12
VENV    := backend/.venv
PYTHON  := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip
COMPOSE := docker compose

.PHONY: help setup db-up db-down migrate seed test coverage coverage-rules demo-phase1 openapi audit-verify purge-retention backup restore lint typecheck phase5-demo phase7-demo ai-setup ai-test ai-demo ai-eval ai-compare clean

help:
	@echo "Targets: setup db-up db-down migrate seed test coverage coverage-rules demo-phase1 openapi audit-verify purge-retention backup restore lint typecheck phase5-demo phase7-demo ai-setup ai-test ai-demo ai-eval ai-compare clean"

setup:
	$(PY) -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -e "backend[dev]"

db-up:
	$(COMPOSE) up -d db redis
	@echo "Waiting for postgres..."
	@until docker exec $$(docker compose ps -q db) pg_isready -U sisi -d sisi >/dev/null 2>&1; do sleep 1; done
	@echo "postgres ready"

db-down:
	$(COMPOSE) down

migrate:
	cd backend && $(abspath $(PYTHON)) -m alembic upgrade head

seed:
	cd backend && $(abspath $(PYTHON)) scripts/seed_demo.py

test:
	cd backend && $(abspath $(PYTHON)) -m pytest

coverage:
	cd backend && $(abspath $(PYTHON)) -m pytest --cov=app --cov-report=term-missing --cov-fail-under=70

# Rules coverage gate (plan §5): app/rules >= 80%; engine/bands/redflags 100%.
coverage-rules:
	cd backend && $(abspath $(PYTHON)) scripts/check_coverage.py

demo-phase1: migrate seed
	cd backend && $(abspath $(PYTHON)) scripts/demo_phase1.py

# Corridor demo world. The school demo seeds first so the whole web e2e suite
# (console.spec.ts + corridor.spec.ts) runs from a fresh database. The backend
# must already be running on :8000 (it is not started here).
phase5-demo:
	cd backend && $(abspath $(PYTHON)) scripts/seed_school_demo.py
	cd backend && $(abspath $(PYTHON)) scripts/seed_corridor_demo.py
	cd web && npm run e2e

# Employer demo world (Phase 7). Seeds only the employer seed (the school seeds
# are not needed by employer.spec.ts). The backend must already be running on
# :8000 (it is not started here).
phase7-demo:
	cd backend && $(abspath $(PYTHON)) scripts/seed_school_demo.py
	cd backend && $(abspath $(PYTHON)) scripts/seed_corridor_demo.py
	cd backend && $(abspath $(PYTHON)) scripts/seed_employer_demo.py
	cd web && npm run e2e

ai-setup:
	$(abspath $(PYTHON)) -m pip install -e "ai_service[dev]"

ai-test:
	cd ai_service && $(abspath $(PYTHON)) -m pytest

ai-demo:
	cd ai_service && $(abspath $(PYTHON)) scripts/demo_phase6.py

ai-eval:
	cd ai_service && $(abspath $(PYTHON)) scripts/eval_guardrails.py

ai-compare:
	cd ai_service && $(abspath $(PYTHON)) scripts/eval_compare.py

openapi:
	cd backend && $(abspath $(PYTHON)) scripts/export_openapi.py

audit-verify:
	cd backend && $(abspath $(PYTHON)) scripts/verify_audit_chain.py

# Retention purge (spec 6, A3): diary data past SISI_RETENTION_DIARY_DAYS and
# lapsed vouchers. Never touches the append-only audit chain (see CC-6).
purge-retention:
	cd backend && $(abspath $(PYTHON)) scripts/purge_retention.py

# Encrypted backup of SISI_DATABASE_URL -> .backups/sisi-<utc-ts>.dump.enc
# (AES-256-GCM under the envelope master key). Restore it with `make restore`.
backup:
	$(abspath $(PYTHON)) scripts/backup_db.py

# Destructive: --clean --if-exists wipes every object in the target database, so the
# script requires --yes. Rehearse against a scratch database first:
#   make restore RESTORE_ARGS='--target-url postgresql+psycopg://sisi:sisi_dev_pw@localhost:5432/sisi_restore_test --create-db'
RESTORE_ARGS ?=
restore:
	$(abspath $(PYTHON)) scripts/restore_db.py --yes $(RESTORE_ARGS)

lint:
	cd backend && $(abspath $(VENV)/bin/ruff) check app tests scripts

typecheck:
	cd backend && $(abspath $(VENV)/bin/mypy) app

clean:
	rm -rf backend/.venv backend/.pytest_cache backend/.mypy_cache backend/.ruff_cache backend/htmlcov backend/.coverage
