#!/usr/bin/env bash
set -euo pipefail
ROOT="$(pwd)"
RELEASE="$(python3 -c 'import json; print(json.load(open("RELEASE-MANIFEST.json"))["release"])')"
mkdir -p verification
docker build -t "petsoul-backend:$RELEASE" PetJourneyBackend > verification/backend-build.log 2>&1
docker run --rm --network none -e TZ=UTC -e PETJOURNEY_SCHEDULER_ENABLED=false -e PETJOURNEY_WEB_PROVIDERS=false \
  -v "$ROOT/PetJourneyBackend/tests:/srv/petjourney/tests:ro" \
  "petsoul-backend:$RELEASE" python -m unittest discover -s tests > verification/backend-tests.log 2>&1
docker run --rm --network none -e TZ=UTC -e PETJOURNEY_SCHEDULER_ENABLED=false -e PETJOURNEY_WEB_PROVIDERS=false \
  -e PYTHONPATH=/source/PetJourneyBackend -v "$ROOT:/source" -w /source \
  "petsoul-backend:$RELEASE" python scripts/gen_web_contract.py --check > verification/contracts.log 2>&1
docker run --rm -e VITE_PETSOUL_DATA_MODE=live -e VITE_PETSOUL_API_BASE=/api/v1/web \
  -v "$ROOT/PetJourneyWeb:/web" -w /web node:22-bookworm-slim \
  sh -c 'npm ci --no-audit --no-fund && npm run typecheck && npm test && npm run build' > verification/frontend.log 2>&1
docker image inspect "petsoul-backend:$RELEASE" --format '{{.Id}}' > verification/backend-image-id.txt
docker run --rm --network none "petsoul-backend:$RELEASE" pip freeze > verification/python-dependencies.txt
python3 - <<'PY'
import hashlib, json
from pathlib import Path
manifest = json.loads(Path('RELEASE-MANIFEST.json').read_text())
for name, digest in manifest['files'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
dist = Path('PetJourneyWeb/dist')
assert (dist/'index.html').is_file()
files = {str(p.relative_to(dist)): hashlib.sha256(p.read_bytes()).hexdigest()
         for p in dist.rglob('*') if p.is_file()}
Path('verification/frontend-sha256.json').write_text(json.dumps(files, indent=2))
print('VERIFIED_RELEASE', manifest['release'], 'source files', len(manifest['files']), 'static files', len(files))
PY
