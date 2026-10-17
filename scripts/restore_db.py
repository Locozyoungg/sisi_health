"""SISI Health — decrypt and restore a backup produced by `scripts/backup_db.py`.

Decrypts the AES-256-GCM archive with the envelope master key and replays it with
`pg_restore --clean --if-exists` into the target database
(`SISI_RESTORE_DATABASE_URL`, default: the dev `sisi` database).

Run it with the backend venv:

    backend/.venv/Scripts/python.exe scripts/restore_db.py --yes [backup.dump.enc]
    make restore         # or:  .\\make.ps1 restore

`--clean --if-exists` DROPS every object in the target database before recreating
it from the archive, so the restore is destructive by design and refuses to run
without `--yes`. Point `--target-url` at a scratch database (e.g.
`sisi_restore_test`) to rehearse a restore without touching the live one — that is
exactly the drill recorded in docs/backup-restore-drill.md.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
SCRIPTS_DIR = Path(__file__).resolve().parent

# `backup_db` holds the shared helpers (tool lookup, URL handling, backup dir), and
# the backend app supplies the settings + master key; both must be importable
# before the remaining top-level imports run.
for _extra in (str(BACKEND_DIR), str(SCRIPTS_DIR)):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from app.config import get_settings  # noqa: E402
from app.crypto.key_provider import DatabaseKeyProvider  # noqa: E402
from backup_db import (  # noqa: E402
    DEFAULT_BACKUP_DIR,
    find_pg_tool,
    libpq_url,
    password_of,
    redact,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: E402

NONCE_BYTES = 12
DEFAULT_RESTORE_URL = "postgresql+psycopg://sisi:sisi_dev_pw@localhost:5432/sisi"


def decrypt(blob: bytes, key: bytes) -> bytes:
    """Inverse of `backup_db.encrypt`: split the 12-byte nonce prefix, then AES-GCM open."""
    nonce, ciphertext = blob[:NONCE_BYTES], blob[NONCE_BYTES:]
    return AESGCM(key).decrypt(nonce, ciphertext, None)


def newest_backup(backup_dir: Path) -> Path:
    candidates = sorted(backup_dir.glob("sisi-*.dump.enc"))
    if not candidates:
        raise SystemExit(f"[restore] no sisi-*.dump.enc found in {backup_dir}")
    return candidates[-1]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Decrypt and restore a SISI backup.")
    parser.add_argument(
        "backup",
        nargs="?",
        default=None,
        help="encrypted backup file (default: newest in <repo>/.backups)",
    )
    parser.add_argument(
        "--target-url",
        default=None,
        help="destination database (default: SISI_RESTORE_DATABASE_URL, else the dev `sisi`)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="required: confirms the destructive --clean restore into the target database",
    )
    parser.add_argument(
        "--create-db",
        action="store_true",
        help="create the target database first when it does not exist (e.g. a scratch DB)",
    )
    return parser.parse_args(argv)


def create_database(url: str) -> bool:
    """Create the database named in `url`; the CREATE itself runs against `postgres`."""
    parts = urlsplit(libpq_url(url))
    database = parts.path.lstrip("/")
    if not database:
        print("[restore] FAILED: target URL has no database name", file=sys.stderr)
        return False

    command = [find_pg_tool("createdb"), "--no-password"]
    if parts.hostname:
        command += ["--host", parts.hostname]
    if parts.port:
        command += ["--port", str(parts.port)]
    if parts.username:
        command += ["--username", parts.username]
    command.append(database)

    password = password_of(url)
    env = {**os.environ, "PGPASSWORD": password} if password else None
    completed = subprocess.run(command, capture_output=True, env=env, check=False)  # noqa: S603
    if completed.returncode == 0:
        print(f"[restore] created database {database}")
        return True
    stderr = completed.stderr.decode("utf-8", "replace")
    if "already exists" in stderr:
        print(f"[restore] database {database} already exists")
        return True
    sys.stderr.write(stderr)
    return False


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])

    settings = get_settings()
    source = Path(args.backup) if args.backup else newest_backup(DEFAULT_BACKUP_DIR)
    if not source.exists():
        raise SystemExit(f"[restore] backup not found: {source}")

    target_url = (
        args.target_url or os.environ.get("SISI_RESTORE_DATABASE_URL") or DEFAULT_RESTORE_URL
    )

    if not args.yes:
        print(
            "[restore] refusing to run: this drops and recreates every object in\n"
            f"[restore]   {redact(libpq_url(target_url))}\n"
            "[restore] re-run with --yes once you are sure that is the intended target.",
            file=sys.stderr,
        )
        return 2

    blob = source.read_bytes()
    if len(blob) <= NONCE_BYTES:
        print(f"[restore] FAILED: {source} is too small to be a valid archive", file=sys.stderr)
        return 1
    plain = decrypt(blob, DatabaseKeyProvider(settings).master())
    print(f"[restore] source:     {source} ({len(blob):,} bytes encrypted)")

    if args.create_db and not create_database(target_url):
        print("[restore] FAILED: could not create the target database", file=sys.stderr)
        return 1

    pg_restore = find_pg_tool("pg_restore")
    target_pg_url = libpq_url(target_url)
    print(f"[restore] pg_restore: {pg_restore}")
    print(f"[restore] target:     {redact(target_pg_url)} (--clean --if-exists)")

    password = password_of(target_url)
    env = {**os.environ, "PGPASSWORD": password} if password else None

    # The decrypted archive is plaintext, so it only ever touches a temp dir that is
    # removed as soon as pg_restore returns.
    with tempfile.TemporaryDirectory(prefix="sisi-restore-") as tmp:
        archive = Path(tmp) / "sisi.dump"
        archive.write_bytes(plain)
        completed = subprocess.run(  # noqa: S603 — fixed argv, no shell
            [
                pg_restore,
                "--clean",
                "--if-exists",
                "--no-password",
                f"--dbname={target_pg_url}",
                str(archive),
            ],
            capture_output=True,
            env=env,
            check=False,
        )

    stderr = completed.stderr.decode("utf-8", "replace")
    errors = [line for line in stderr.splitlines() if " error:" in line]
    warnings = [line for line in stderr.splitlines() if " warning:" in line]
    print(f"[restore] archive:    {len(plain):,} bytes replayed")
    if warnings:
        print(f"[restore] warnings:   {len(warnings)} (ignored by --if-exists)")
    if errors:
        print(f"[restore] errors:     {len(errors)} (first 10 below)")
        for line in errors[:10]:
            print(f"[restore]   {line}")
        print(f"[restore] FAILED: pg_restore exited {completed.returncode}", file=sys.stderr)
        return completed.returncode or 1
    if completed.returncode != 0:
        sys.stderr.write(stderr)
        print(f"[restore] FAILED: pg_restore exited {completed.returncode}", file=sys.stderr)
        return completed.returncode
    print("[restore] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
