"""SISI Health — encrypted PostgreSQL backup (Phase 8 ops).

Takes a `pg_dump --format=custom` archive of the configured database and encrypts
it with the envelope master key (AES-256-GCM, 12-byte nonce prefix — the same byte
layout `app.crypto.key_provider.DatabaseKeyProvider.wrap()` uses) into
`.backups/sisi-<utc-ts>.dump.enc`.

Run it with the backend venv:

    backend/.venv/Scripts/python.exe scripts/backup_db.py
    make backup          # or:  .\\make.ps1 backup

`pg_dump` is taken from PATH when available and otherwise from the portable
PostgreSQL install at `.tools/pgsql/pgsql/bin` (same fallback `make db-up` uses).

The output is never committed — `.backups/` is gitignored. Restore it with
`scripts/restore_db.py`; see docs/runbook.md and docs/backup-restore-drill.md.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
PORTABLE_PG_BIN = REPO_ROOT / ".tools" / "pgsql" / "pgsql" / "bin"
DEFAULT_BACKUP_DIR = REPO_ROOT / ".backups"
NONCE_BYTES = 12

# The backup/restore helpers import the backend app (settings + master key), so the
# package has to be importable before the rest of the top-level imports run.
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings  # noqa: E402
from app.crypto.key_provider import DatabaseKeyProvider  # noqa: E402
from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: E402


def find_pg_tool(name: str) -> str:
    """Resolve a PostgreSQL client binary: PATH first, portable install second."""
    found = shutil.which(name) or shutil.which(f"{name}.exe")
    if found:
        return found
    suffix = ".exe" if os.name == "nt" else ""
    portable = PORTABLE_PG_BIN / f"{name}{suffix}"
    if portable.exists():
        return str(portable)
    raise SystemExit(
        f"[backup] {name} not found on PATH or at {portable}. "
        "Install PostgreSQL client tools or run `make db-up` once to unpack them."
    )


def libpq_url(sqlalchemy_url: str) -> str:
    """Strip the SQLAlchemy driver suffix so libpq (pg_dump/pg_restore) accepts the URL."""
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://", "postgres+psycopg://"):
        if sqlalchemy_url.startswith(prefix):
            return "postgresql://" + sqlalchemy_url[len(prefix) :]
    return sqlalchemy_url


def redact(url: str) -> str:
    """`postgresql://user:pw@host/db` -> `postgresql://user@host/db` (never print secrets)."""
    if "@" not in url:
        return url
    scheme, rest = url.split("://", 1)
    credentials, location = rest.rsplit("@", 1)
    user = credentials.split(":", 1)[0]
    return f"{scheme}://{user}@{location}"


def password_of(url: str) -> str:
    """Extract the password from a URL, or '' when the URL carries none."""
    if "@" not in url:
        return ""
    rest = url.split("://", 1)[-1]
    credentials = rest.rsplit("@", 1)[0]
    return credentials.split(":", 1)[1] if ":" in credentials else ""


def encrypt(plain: bytes, key: bytes) -> bytes:
    """AES-256-GCM with a 12-byte nonce prefix (matches KeyProvider.wrap)."""
    nonce = os.urandom(NONCE_BYTES)
    return nonce + AESGCM(key).encrypt(nonce, plain, None)


def utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Encrypted SISI Health database backup.")
    parser.add_argument(
        "--database-url",
        default=None,
        help="source database (default: SISI_DATABASE_URL, i.e. the dev `sisi` database)",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="directory for the encrypted dump (default: <repo>/.backups)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])

    settings = get_settings()
    source_url = args.database_url or settings.database_url
    out_dir = Path(args.out_dir) if args.out_dir else DEFAULT_BACKUP_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"sisi-{utc_stamp()}.dump.enc"

    pg_dump = find_pg_tool("pg_dump")
    env = {**os.environ, "PGPASSWORD": password_of(source_url)} if password_of(source_url) else None

    print(f"[backup] pg_dump:  {pg_dump}")
    print(f"[backup] source:   {redact(libpq_url(source_url))}")
    command = [
        pg_dump,
        "--format=custom",
        "--no-password",
        f"--dbname={libpq_url(source_url)}",
    ]
    # The command is a fixed argv (no shell); only the URL comes from configuration.
    completed = subprocess.run(  # noqa: S603
        command, capture_output=True, env=env, check=False
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr.decode("utf-8", "replace"))
        print(f"[backup] FAILED: pg_dump exited {completed.returncode}", file=sys.stderr)
        return completed.returncode

    plain = completed.stdout
    if not plain:
        print("[backup] FAILED: pg_dump produced an empty archive", file=sys.stderr)
        return 1

    key_provider = DatabaseKeyProvider(settings)
    key = key_provider.master()
    if len(key) != 32:
        print(f"[backup] FAILED: master key is {len(key)} bytes, expected 32", file=sys.stderr)
        return 1
    blob = encrypt(plain, key)

    # Write-then-rename so an interrupted run never leaves a half-written backup
    # that a later restore would silently accept.
    partial = target.with_suffix(target.suffix + ".partial")
    partial.write_bytes(blob)
    partial.replace(target)
    try:
        os.chmod(target, 0o600)
    except OSError:  # pragma: no cover — best effort on Windows
        pass

    key_source = "SISI_MASTER_KEY_B64" if settings.master_key_b64 else str(settings.master_key_file)
    print(f"[backup] archive:  {len(plain):,} bytes (pg_dump custom format)")
    print(f"[backup] encrypted {len(blob):,} bytes -> {target}")
    print(f"[backup] cipher:   AES-256-GCM (12-byte nonce prefix), key from {key_source}")
    print("[backup] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
