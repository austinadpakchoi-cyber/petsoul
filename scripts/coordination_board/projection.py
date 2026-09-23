"""Read only coordination documents; never import the application or infer acceptance.

Timestamps describe recorded events. File mtime describes changes to a document.
Corrections remain visible alongside their original records, without an LLM guessing
which historical claim they supersede. The reviewed snapshot is never overwritten.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ZONE = timezone(timedelta(hours=8))
MAX_BYTES = 4 * 1024 * 1024
LOG_NAME = re.compile(r"WINDOW-[A-Za-z0-9_-]+\.log\.md\Z")
KINDS = re.compile(r"\b(CORRECTION|CHANGE_REQUEST|SCOPE_CHANGE|HANDOFF|RELEASE|ACCEPT|INTEGRATED|PROGRESS|START|CLAIM|VERIFY|BLOCKED|WAITING)\b")
STAMP = re.compile(r"(20\d{2}-\d{2}-\d{2})[ T](\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)(?![\dXx:])\s*(Z|[+-]\d{2}:?\d{2})?")
TASK = re.compile(r"\bpkg-[A-Z]-[a-zA-Z0-9_-]+\b")
WINDOWS = {
    "claude-20260922-014933-307b": ("I", "总集成"),
    "claude-20260922-234337-4bef": ("A", "任务与额度"),
    "claude-20260922-234415-fed3": ("B", "世界时钟与心跳"),
    "claude-20260922-234408-91f2": ("C", "DNA 与自主决策"),
    "claude-20260922-234631-4d18": ("Q", "独立验收"),
    "codex-20260922-product-refresh-c84a": ("监管", "协作看板"),
    "codex-20260922-131657-petsoul-visual-r7k": ("UI", "前端与视觉"),
}


def redact(text: str) -> str:
    text = re.sub(r"-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----", "[私钥已隐藏]", text)
    text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{16,}", r"\1[已隐藏]", text)
    return re.sub(r"(?i)((?:api[_-]?key|secret[_-]?key|access[_-]?token|password)\s*[=:]\s*)[^\s,;]{8,}", r"\1[已隐藏]", text)


def read_document(root: Path, name: str) -> tuple[str, dict]:
    if not (LOG_NAME.fullmatch(name) or name == "petsoul-agent-oversight.snapshot.json"):
        raise ValueError("document is not allowlisted")
    path = (root / name).resolve()
    if path.parent != root.resolve() or not path.is_file():
        raise ValueError("document must be a file inside coordination")
    for _ in range(2):
        before = path.stat()
        if before.st_size > MAX_BYTES:
            raise ValueError("document exceeds 4 MiB")
        raw = path.read_bytes()
        after = path.stat()
        if (before.st_mtime_ns, before.st_size) == (after.st_mtime_ns, after.st_size):
            text = raw.decode("utf-8-sig", errors="strict")
            return redact(text), {
                "name": name, "modifiedAt": datetime.fromtimestamp(after.st_mtime, ZONE).isoformat(),
                "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            }
    raise ValueError("document changed while reading; refresh to retry")


def recorded_time(title: str, lines: list[str], now: datetime) -> tuple[str | None, str, list[str]]:
    candidates = [title] if title.startswith("CORRECTION") else [line.strip() for line in lines if re.match(r"^\s*时间(?:[（(:：]|\s)", line)]
    if not candidates:
        candidates = [title]
    raw = candidates[0] if candidates else ""
    match = STAMP.search(raw)
    if not match:
        return None, raw, ["记录时间缺失或不完整，按文件追加顺序展示"]
    zone = match[3] or "+08:00"
    try:
        moment = datetime.fromisoformat(f"{match[1]}T{match[2]}{zone.replace('Z', '+00:00')}")
    except ValueError:
        return None, raw, ["记录时间无法解析"]
    notes = [] if match[3] else ["未写时区；按项目约定 +08:00 显示"]
    if moment > now + timedelta(minutes=5):
        return None, raw, notes + ["记录时间晚于读取时间，未用于最新事件排序"]
    return moment.astimezone(ZONE).isoformat(), raw, notes


def task_id(title: str, lines: list[str]) -> str | None:
    for line in lines[:14]:
        if "任务" in line and ("ID" in line or "编号" in line):
            found = TASK.search(line)
            if found:
                return found[0]
            parts = re.split(r"\s+/\s+", re.split(r"[：:]", line, maxsplit=1)[-1])
            if len(parts) >= 2 and re.fullmatch(r"[\w-]+", parts[1]):
                return parts[1]
    found = TASK.search(title)
    if found:
        return found[0]
    tail = re.split(r"\s+[—–]\s+", title, maxsplit=1)[-1].strip()
    return tail if tail != title and re.fullmatch(r"[a-zA-Z][\w-]+", tail) else None


def parse_events(text: str, filename: str, now: datetime) -> list[dict]:
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if re.match(r"^##\s+|^CORRECTION[（(\s]", line)]
    if not starts:
        starts = [0] if lines else []
    events = []
    for pos, start in enumerate(starts):
        end = starts[pos + 1] if pos + 1 < len(starts) else len(lines)
        chunk = lines[start:end]
        title = re.sub(r"^##\s+", "", chunk[0]).strip()
        lead = re.split(r"[（(：]|\s+[—–]\s+", title, maxsplit=1)[0]
        kinds = list(dict.fromkeys(KINDS.findall(lead.upper()))) or ["NOTE"]
        at, raw_time, notes = recorded_time(title, chunk[1:], now)
        fields = [line.strip() for line in chunk[1:] if re.match(
            r"\s*(?:[-*]\s*)?(?:用户任务|任务[：:]|结果[：:]|结论[：:]|下一步[：:]|未完成|未验证|需要|优先|是否.*释放|实际修改|运行资源|验证[（：:]|领取范围|冲突)", line)]
        release = next((line.strip() for line in reversed(chunk) if re.match(r"\s*是否.*释放", line)), None)
        events.append({
            "id": f"{filename}:L{start + 1}", "file": filename, "line": start + 1,
            "endLine": end, "title": title, "kinds": kinds, "taskId": task_id(title, chunk[1:]),
            "recordedAt": at, "timeText": raw_time, "timeNotes": notes,
            "summary": fields[:5], "releaseStatement": release,
            "body": "\n".join(chunk).strip(), "tier": "窗口原文 · 未自动验收",
            "mentions": list(dict.fromkeys(re.findall(r"\b(?:CR-[A-Z]\d+|Q-C\d+[a-z]?|pkg-[A-Z]-[\w-]+)\b", "\n".join(chunk)))),
        })
    return events


def build_board(repo: Path, now: datetime | None = None) -> dict:
    now = now or datetime.now(ZONE)
    root = repo / "docs" / "coordination"
    errors, windows, all_events, versions = [], [], [], []
    review = None
    try:
        raw, meta = read_document(root, "petsoul-agent-oversight.snapshot.json")
        review = json.loads(raw)
        versions.append(meta["sha256"])
        if not isinstance(review, dict) or not isinstance(review.get("packages"), list):
            raise ValueError("invalid reviewed snapshot")
    except (OSError, ValueError, UnicodeError) as exc:
        review = None
        errors.append({"source": "petsoul-agent-oversight.snapshot.json", "reason": type(exc).__name__, "message": "人工快照暂不可读，未沿用缓存冒充最新"})
    paths = sorted(root.glob("WINDOW-*.log.md"))
    for path in paths:
        if not LOG_NAME.fullmatch(path.name):
            continue
        owner = path.name[7:-7]
        code, name = WINDOWS.get(owner, ("其他", owner.replace("codex-20260922-", "")))
        try:
            raw, meta = read_document(root, path.name)
            events = parse_events(raw, path.name, now)
        except (OSError, ValueError, UnicodeError) as exc:
            errors.append({"source": path.name, "reason": type(exc).__name__, "message": "日志读取失败，本次状态未知"})
            continue
        versions.append(meta["sha256"])
        for event in events:
            event.update({"owner": owner, "package": code})
        substantive = [event for event in events if "CORRECTION" not in event["kinds"] and event["recordedAt"]]
        latest = max(substantive, key=lambda e: (e["recordedAt"], e["line"])) if substantive else (events[-1] if events else None)
        reviewed = next((p for p in (review or {}).get("packages", []) if p.get("owner") == owner), None)
        snapshot_at = (review or {}).get("snapshotAt")
        changed = bool(snapshot_at and datetime.fromisoformat(meta["modifiedAt"]) > datetime.fromisoformat(snapshot_at))
        windows.append({
            "owner": owner, "package": code, "name": name, "source": meta,
            "latestEventId": latest["id"] if latest else None,
            "lastAppendedId": events[-1]["id"] if events else None,
            "recordCount": len(events), "changedSinceReview": changed,
            "reviewed": reviewed, "processState": "未探测；日志沉默不代表停止",
        })
        all_events.extend(events)
    if not paths:
        errors.append({"source": "WINDOW-*.log.md", "reason": "Missing", "message": "没有找到窗口日志"})
    modified = {w["owner"]: w["source"]["modifiedAt"] for w in windows}
    all_events.sort(key=lambda e: (e["recordedAt"] or modified[e["owner"]], e["line"]), reverse=True)
    order = ["I", "A", "B", "C", "Q", "监管", "UI"]
    windows.sort(key=lambda w: (order.index(w["package"]) if w["package"] in order else 99, w["owner"]))
    return {
        "schemaVersion": 1, "application": "petsoul-live-blackboard", "repo": str(repo.resolve()),
        "readAt": now.isoformat(), "revision": hashlib.sha256("".join(versions).encode()).hexdigest(),
        "windows": windows, "events": all_events, "review": review, "errors": errors,
        "policy": "每次请求读取本地黑板；自动聚合不等于核验，不改变领取、释放、验收或进程状态。",
    }
