"""Opt-in public smoke: only dedicated QA accounts, no provider calls.

Usage: python check-public.py URL credential-json evidence-json [--persist-only]
The UI account must have completed move-in; credentials never enter reports.
"""
import json
import struct
import sys
import uuid
import zlib
from datetime import datetime, timezone
from pathlib import Path

import httpx

base, credential_path, evidence_path = sys.argv[1:4]
credentials = json.loads(Path(credential_path).read_text(encoding="utf-8-sig"))
prefix = base.rstrip("/") + "/api/v1/web"
checks = []


def expect(response, status, label):
    assert response.status_code == status, f"{label}: HTTP {response.status_code}"
    checks.append(label)
    return response.json() if response.content and response.headers.get("content-type", "").startswith("application/json") else None


def headers(client, key=None):
    return {"X-CSRF-Token": client.cookies.get("petsoul_csrf", ""), "Idempotency-Key": key or "hkqa-" + uuid.uuid4().hex}


def post(client, path, body, status=200, key=None):
    return expect(client.post(prefix + path, json=body, headers=headers(client, key)), status, path)


def get(client, path, status=200):
    return expect(client.get(prefix + path), status, path)


def png():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + chunk(b"tEXt", b"GPS\0QA metadata") + chunk(b"IDAT", zlib.compress(b"\0\xff\0\0")) + chunk(b"IEND", b"")


with httpx.Client(timeout=30) as a, httpx.Client(timeout=30) as b, httpx.Client(timeout=30) as anon:
    response = a.post(prefix + "/auth/login", json=credentials["ui"])
    expect(response, 200, "ui_account_login")
    cookies = response.headers.get_list("set-cookie")
    assert any("petsoul_session=" in x and "httponly" in x.lower() and "secure" in x.lower() for x in cookies)
    checks.append("secure_httponly_session")
    home = get(a, "/home")
    pet_id = home["pet"]["pet_id"]
    if "--persist-only" in sys.argv:
        prior = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
        assert home["home_id"] == prior["home_id"] and pet_id == prior["pet_id"]
        assert home["wallet"]["balance"] == prior["balance"]
        thread = get(a, f"/communicator/{pet_id}/messages")
        assert prior["message_id"] in json.dumps(thread)
        prior["restart_persistence"] = {"passed": True, "checked_at": datetime.now(timezone.utc).isoformat()}
        Path(evidence_path).write_text(json.dumps(prior, ensure_ascii=False, indent=2), encoding="utf-8")
        print("PASS: login, same home/pet/wallet, and message survived backend restart")
        sys.exit(0)

    # Do not touch adoption candidates, other users, or any paid APIs.
    registered = b.post(prefix + "/auth/register", json=credentials["isolation"])
    if registered.status_code == 409:
        expect(b.post(prefix + "/auth/login", json=credentials["isolation"]), 200, "qa_isolation_login")
    else:
        expect(registered, 201, "qa_isolation_register")
    session = get(b, "/session")
    if not session["onboarding"]["pet_id"]:
        pet = expect(b.post(prefix + "/pets", data={"name": "隔离验收猫", "species": "cat"}, files={"photo": ("qa.png", png(), "image/png")}, headers=headers(b)), 201, "qa_private_photo_upload")
        post(b, "/onboarding/move-in", {"public_posts": False})
    other_home = get(b, "/home")
    other_pet = other_home["pet"]["pet_id"]
    private_photo = b.get(prefix + f"/media/pets/{other_pet}/photo")
    assert private_photo.status_code == 200 and "private" in private_photo.headers["cache-control"]
    assert b"QA metadata" not in private_photo.content
    checks.append("own_photo_readable_metadata_stripped")
    get(a, f"/media/pets/{other_pet}/photo", 404)
    get(anon, f"/media/pets/{other_pet}/photo", 401)
    get(b, f"/communicator/{pet_id}/messages", 404)
    get(b, "/journey/map?pet_id=" + pet_id, 404)
    get(anon, "/home", 401)
    expect(a.post(prefix + "/journey/depart", json={"destination_key": "harbour_cafe"}), 403, "csrf_required")
    message_id = "hkqa-" + uuid.uuid4().hex
    message = {"client_message_id": message_id, "text": "上线验收测试：在家晒太阳开心吗？"}
    first = post(a, f"/communicator/{pet_id}/messages", message)
    repeat = post(a, f"/communicator/{pet_id}/messages", message)
    assert first == repeat
    saved_message_id = first["message_id"]
    checks.append("message_retry_idempotent")
    ripe = next((p for p in home["plots"] if p["stage"] == "ripe"), None)
    if ripe:
        action = {"home_id": home["home_id"], "plot_id": ripe["plot_id"], "cycle_id": ripe["cycle_id"], "action": "harvest"}
        key = "hkqa-" + uuid.uuid4().hex
        first = post(a, "/farm/actions", action, key=key)
        repeat = post(a, "/farm/actions", action, key=key)
        assert first == repeat
        checks.append("harvest_retry_idempotent")
    for path in ["/farm/crops", "/neighbors", "/journey/destinations", "/circle/feed", "/settings"]:
        get(a, path)
    home = get(a, "/home")
    report = {"base_url": base, "checked_at": datetime.now(timezone.utc).isoformat(), "checks": checks, "home_id": home["home_id"], "pet_id": pet_id, "balance": home["wallet"]["balance"], "message_id": saved_message_id, "client_message_id": message_id, "limitations": ["QA accounts only", "No real provider calls", "No fake clock", "No physical-phone or load test"]}
    thread = get(a, f"/communicator/{pet_id}/messages")
    assert saved_message_id in json.dumps(thread)
    Path(evidence_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PASS: {len(checks)} public checks; report: {evidence_path}")
