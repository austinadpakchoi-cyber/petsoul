"""Create a verified source archive, excluding local data, credentials and caches."""
from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import Path
import subprocess
import tarfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
TREES = (
    "PetJourneyBackend/app", "PetJourneyBackend/tests",
    "PetJourneyWeb/src", "PetJourneyWeb/public", "PetJourneyWeb/tests",
    "docs/contracts", "deploy/web/hk-v1",
)
FILES = (
    "PetJourneyBackend/requirements.txt", "PetJourneyBackend/Dockerfile",
    "PetJourneyWeb/package.json", "PetJourneyWeb/package-lock.json",
    "PetJourneyWeb/index.html", "PetJourneyWeb/vite.config.ts",
    "PetJourneyWeb/tsconfig.json", "PetJourneyWeb/tsconfig.app.json",
    "PetJourneyWeb/tsconfig.node.json", "PetJourneyWeb/.env.live",
    "scripts/gen_web_contract.py", "deploy/web/scripts/smoke.sh",
    "deploy/web/scripts/backup.sh",
)


def files() -> list[Path]:
    found = {ROOT / name for name in FILES if (ROOT / name).is_file()}
    for name in TREES:
        found.update(p for p in (ROOT / name).rglob("*") if p.is_file())
    return sorted(p for p in found if not p.is_symlink()
                  and not any(part in {"__pycache__", "node_modules", "data", ".git"}
                              for part in p.relative_to(ROOT).parts)
                  and p.suffix not in {".pyc", ".pem", ".key", ".sqlite", ".sqlite3"}
                  and (not p.name.startswith(".env") or p.name == ".env.live"))


def main() -> None:
    captured = {p.relative_to(ROOT).as_posix(): p.read_bytes() for p in files()}
    hashes = {name: hashlib.sha256(body).hexdigest() for name, body in captured.items()}
    current = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in files()}
    if hashes != current:
        raise SystemExit("Source changed during capture; retry after coordination.")
    for name, body in captured.items():
        if re.search(rb"-----BEGIN(?: RSA| OPENSSH| EC)? PRIVATE KEY-----\s+[A-Za-z0-9+/]{32,}", body):
            raise SystemExit(f"Private-key marker in {name}; abort.")
    now = datetime.now(timezone.utc)
    release = "team-v1-" + now.strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "PetJourneyBackend/data/deployments" / release
    out.mkdir(parents=True, exist_ok=False)
    manifest = {
        "release": release, "captured_at": now.isoformat(),
        "base_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_state": "uncommitted working-tree snapshot; file hashes define the release",
        "files": hashes,
    }
    manifest_body = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
    archive = out / "source.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for name, body in {**captured, "RELEASE-MANIFEST.json": manifest_body}.items():
            entry = tarfile.TarInfo(name)
            entry.size, entry.mtime, entry.mode = len(body), int(now.timestamp()), 0o644
            tar.addfile(entry, io.BytesIO(body))
    (out / "RELEASE-MANIFEST.json").write_bytes(manifest_body)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (out / "source.sha256").write_text(f"{digest}  source.tar.gz\n", encoding="ascii")
    print(json.dumps({"release": release, "archive": str(archive), "sha256": digest,
                      "files": len(hashes), "bytes": archive.stat().st_size}))


if __name__ == "__main__":
    main()
