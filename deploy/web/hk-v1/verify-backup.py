"""Verify a backup by restoring a copy into a fresh scratch directory, never live data."""
import hashlib
import json
import shutil
import sqlite3
import sys
import tarfile
import tempfile
from pathlib import Path

backup = Path(sys.argv[1]).resolve(strict=True)
for line in (backup / "SHA256SUMS").read_text().splitlines():
    digest, filename = line.split(maxsplit=1)
    path = (backup / filename.lstrip("*")).resolve(strict=True)
    assert path.parent == backup
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
with tempfile.TemporaryDirectory(prefix="petsoul-restore-check-", dir="/opt/petsoul/backups") as scratch:
    restored = Path(scratch)
    shutil.copy2(backup / "petjourney.sqlite3", restored / "petjourney.sqlite3")
    for archive in backup.glob("*.tgz"):
        with tarfile.open(archive) as tar:
            tar.extractall(restored, filter="data")
    with sqlite3.connect(f"file:{restored / 'petjourney.sqlite3'}?mode=ro", uri=True) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        migrations = db.execute("SELECT COUNT(*) FROM web_schema_migrations").fetchone()[0]
        tables = db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
    print(json.dumps({"backup": str(backup), "sha256": "pass", "scratch_restore_integrity": "ok", "migration_count": migrations, "table_count": tables, "restored_media_files": sum(1 for p in restored.rglob('*') if p.is_file()) - 1, "live_database_modified": False}))
