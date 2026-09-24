"""运营内容：草稿 → 校验 → 预览 → 发布（不可变版本）→ 撤下 / 回退。

五种内容，**每一种都真的被玩家侧消费**，不是只存个表、也不建空菜单：

| 类型 | 玩家侧谁在读 | 为什么改了不会改写既有事实 |
|---|---|---|
| `announcement` 公告 | `GET /api/v1/web/announcements` 按 `live_revision` 读 | 公告本来就是"此刻的通知"，没有既有事实 |
| `adventure` 冒险模板 | 世界引擎在冒险事件**发生时**取模板 | 标题/勋章/故事写进事件数据并落库，已发生的一条都不改 |
| `crop` 作物与物资 | 菜园地块、仓库、杂货铺收购价、居民订单 | 只开放 label / unit_value / grow_seconds，见下 |
| `job` 打工岗位 | 世界引擎在 `work_done` 事件发生时取工钱 | 工钱写进事件数据并入账，已结算的工资一分不动 |
| `resident` 原创待领养居民 | 访客公开页与 `/adoption/candidates` | 只改 `availability='available'` 的居民，且只改文案不改身份 |

**字段白名单是这套设计的核心**，不是补充说明。能不能发布某个字段，取决于"它会不会被进行中的事实实时读到"：

- 作物的 `yield_units` / `steal_total` 在收获与地块摘要里是**实时读**的，改了就等于静默改写进行中的批次，
  所以**不开放**；`grow_seconds` 只在种下那一刻读（成熟时间落在地块行上），所以安全。
- 居民的 `name` / `species` 属于身份，产品规则要求领养前后身份连续，所以**不开放**；性格、梦想、来源说明属于文案，开放。

校验不是走形式：活动故事里的占位符只允许 `{pet}` 与 `{keepsake}`，因为世界引擎会对它做 `str.format`，
多一个未知占位符会在真实运行时抛 KeyError。所以「缺必要事实」在这里被挡下，不是提示，是拒绝发布。

回退＝把旧正文复制成**一个新版本号**再发布。版本号只增不减，发布历史仅追加，世界时钟与既有事实一概不动。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow
from ..web_platform.uow import unit_of_work
from .errors import AdminAPIError, AdminErrorCode
from .labels import ADOPTION_AVAILABILITY

# 词表、字段白名单、结构校验与发布流水里的说明文字搬到了 content_types.py（架构门禁的定义数上限）。
# 这里重新导出，既有 `from .content import validate / CONTENT_TYPES` 的调用方不受影响。
from .content_types import (  # noqa: F401
    ADVENTURE_PLACEHOLDERS,
    ANNOUNCEMENT_AUDIENCES,
    ANNOUNCEMENT_SEVERITIES,
    CONTENT_TYPES,
    NUMERIC_BOUNDS,
    OVERLAY_TYPES,
    ValidationIssue,
    builtin_body,
    builtin_keys,
    builtin_name,
    resident_apply_note,
    validate,
)
from .content_types import _SLUG_RE, _diff_summary

# 覆盖层缓存的存活时间：`CROPS[key]`、`JOBS.values()` 会被世界推进反复调用，不能每次打库。
# 多进程下最多陈旧这么久；发布/撤下/回退时本进程立刻失效。
OVERLAY_CACHE_SECONDS = 2.0


@dataclass(frozen=True, slots=True)
class ContentItem:
    item_id: str
    content_type: str
    slug: str
    title: str
    status: str
    live_revision: int | None
    draft_revision: int | None
    version: int
    effective_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


def _item(row) -> ContentItem:
    return ContentItem(
        item_id=row["item_id"], content_type=row["content_type"], slug=row["slug"], title=row["title"], status=row["status"],
        live_revision=None if row["live_revision"] is None else int(row["live_revision"]),
        draft_revision=None if row["draft_revision"] is None else int(row["draft_revision"]),
        version=int(row["version"]),
        effective_at=parse_dt(row["effective_at"]) if row["effective_at"] else None,
        expires_at=parse_dt(row["expires_at"]) if row["expires_at"] else None,
        created_at=parse_dt(row["created_at"]), created_by=row["created_by"],
        updated_at=parse_dt(row["updated_at"]), updated_by=row["updated_by"],
    )


def _hash(body: dict) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


class AdminContent:
    def __init__(self, storage: JourneyStorage) -> None:
        self.storage = storage
        self._tables_ready: bool | None = None
        # 覆盖层缓存：(content_type, slug) -> (取到的时刻, 正文或 None)
        self._overlay_cache: dict[tuple[str, str], tuple[float, dict | None]] = {}
        self._cache_lock = threading.Lock()

    def invalidate(self) -> None:
        """发布 / 撤下 / 回退之后立刻让本进程的覆盖层缓存失效。别的进程最多陈旧 OVERLAY_CACHE_SECONDS。"""
        with self._cache_lock:
            self._overlay_cache.clear()

    # ---- 草稿 ----
    def create(self, *, content_type: str, slug: str, title: str, body: dict, actor: str, note: str | None = None) -> ContentItem:
        if content_type not in CONTENT_TYPES:
            raise AdminAPIError.validation(f"不支持的内容类型：{content_type}", field="content_type")
        slug = (slug or "").strip().lower()
        if content_type != "resident" and not _SLUG_RE.match(slug):
            raise AdminAPIError.validation("标识只能是小写字母、数字、下划线或连字符，2–49 位。", field="slug")
        if content_type in OVERLAY_TYPES:
            keys = builtin_keys(content_type)
            if slug not in keys:
                names = "、".join(builtin_name(content_type, key) for key in sorted(keys))
                raise AdminAPIError.validation(f"只支持给已有条目发新版本；可选：{names}。", field="slug")
        if content_type == "resident":
            # slug ＝ 居民的 candidate_id。只允许给**还没被领养**的居民改文案：
            # 已领养的身份与经历必须连续，运营不能事后改写。
            with self.storage.connect() as conn:
                row = conn.execute("SELECT availability FROM web_adoption_candidates WHERE candidate_id = ?", (slug,)).fetchone()
            if row is None:
                raise AdminAPIError.validation("没有这位待领养居民。", field="slug")
            if row["availability"] != "available":
                state = ADOPTION_AVAILABILITY.get(row["availability"], row["availability"])
                raise AdminAPIError.validation(
                    f"这位居民当前是「{state}」，已经不在可领养名单里，运营不能再改它的文案。", field="slug")
        item_id = f"CT-{uuid.uuid4().hex[:12].upper()}"
        now = iso(utcnow())
        try:
            with unit_of_work(self.storage) as conn:
                conn.execute(
                    "INSERT INTO admin_content_items (item_id, content_type, slug, title, status, live_revision, draft_revision, version, "
                    "created_at, created_by, updated_at, updated_by) VALUES (?, ?, ?, ?, 'draft', NULL, 1, 1, ?, ?, ?, ?)",
                    (item_id, content_type, slug, title.strip()[:120], now, actor, now, actor),
                )
                self._insert_revision(conn, item_id, 1, body, actor, note, None, now)
        except sqlite3.IntegrityError as exc:
            shown = builtin_name(content_type, slug) if content_type in OVERLAY_TYPES else slug
            raise AdminAPIError(AdminErrorCode.conflict, f"「{shown}」已经有一条内容了：去那一条里改草稿、发新版本。", 409,
                                details={"content_type": content_type, "slug": slug}) from exc
        item = self.item(item_id)
        assert item is not None
        return item

    def save_draft(self, item_id: str, *, body: dict, actor: str, expected_version: int, note: str | None = None) -> ContentItem:
        now = iso(utcnow())
        with unit_of_work(self.storage) as conn:
            row = self._locked(conn, item_id, expected_version)
            revision = int(conn.execute("SELECT COALESCE(MAX(revision), 0) AS m FROM admin_content_revisions WHERE item_id = ?",
                                        (item_id,)).fetchone()["m"]) + 1
            self._insert_revision(conn, item_id, revision, body, actor, note, None, now)
            title = body.get("title") if isinstance(body, dict) and isinstance(body.get("title"), str) else row["title"]
            conn.execute("UPDATE admin_content_items SET draft_revision = ?, title = ?, version = version + 1, updated_at = ?, updated_by = ? "
                         "WHERE item_id = ?", (revision, str(title)[:120], now, actor, item_id))
        item = self.item(item_id)
        assert item is not None
        return item

    def _insert_revision(self, conn: sqlite3.Connection, item_id: str, revision: int, body: dict, actor: str,
                         note: str | None, source_revision: int | None, now: str) -> None:
        payload = json.dumps(body, ensure_ascii=False, sort_keys=True)
        conn.execute(
            "INSERT INTO admin_content_revisions (item_id, revision, body_json, body_hash, note, source_revision, created_at, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (item_id, revision, payload, _hash(body), note, source_revision, now, actor),
        )

    def _locked(self, conn: sqlite3.Connection, item_id: str, expected_version: int):
        """拿到写锁之后再读版本；对不上就整笔不写。"""
        row = conn.execute("SELECT * FROM admin_content_items WHERE item_id = ?", (item_id,)).fetchone()
        if row is None:
            raise AdminAPIError.not_found("这条内容")
        if int(row["version"]) != expected_version:
            raise AdminAPIError.version_conflict(expected_version, int(row["version"]))
        return row

    # ---- 读 ----
    def item(self, item_id: str) -> ContentItem | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM admin_content_items WHERE item_id = ?", (item_id,)).fetchone()
        return None if row is None else _item(row)

    def list_items(self, content_type: str | None = None) -> list[ContentItem]:
        sql = "SELECT * FROM admin_content_items"
        params: tuple = ()
        if content_type:
            sql += " WHERE content_type = ?"
            params = (content_type,)
        with self.storage.connect() as conn:
            return [_item(row) for row in conn.execute(sql + " ORDER BY updated_at DESC", params)]

    def revision_body(self, item_id: str, revision: int) -> dict | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT body_json FROM admin_content_revisions WHERE item_id = ? AND revision = ?",
                               (item_id, revision)).fetchone()
        return None if row is None else json.loads(row["body_json"])

    def revisions(self, item_id: str) -> list[dict]:
        with self.storage.connect() as conn:
            return [{"revision": int(r["revision"]), "body": json.loads(r["body_json"]), "body_hash": r["body_hash"],
                     "note": r["note"], "source_revision": None if r["source_revision"] is None else int(r["source_revision"]),
                     "created_at": parse_dt(r["created_at"]), "created_by": r["created_by"]}
                    for r in conn.execute("SELECT * FROM admin_content_revisions WHERE item_id = ? ORDER BY revision DESC", (item_id,))]

    def publications(self, item_id: str) -> list[dict]:
        with self.storage.connect() as conn:
            return [{"publication_id": r["publication_id"], "revision": int(r["revision"]), "action": r["action"],
                     "effective_at": parse_dt(r["effective_at"]), "expires_at": parse_dt(r["expires_at"]) if r["expires_at"] else None,
                     "reason": r["reason"], "staff_id": r["staff_id"], "operation_id": r["operation_id"],
                     "diff_summary": r["diff_summary"], "created_at": parse_dt(r["created_at"])}
                    for r in conn.execute("SELECT * FROM admin_content_publications WHERE item_id = ? ORDER BY created_at DESC", (item_id,))]

    # ---- 发布 ----
    def publish(self, item_id: str, *, revision: int, reason: str, actor: str, operation_id: str, expected_version: int,
                effective_at: datetime | None, expires_at: datetime | None, audit, audit_kwargs: dict) -> dict:
        now_dt = utcnow()
        effective = effective_at or now_dt
        if expires_at is not None and expires_at <= effective:
            raise AdminAPIError.validation("下线时间要晚于生效时间。", field="expires_at")
        now = iso(now_dt)
        with unit_of_work(self.storage) as conn:
            self._locked(conn, item_id, expected_version)
            result = self._publish_in(conn, item_id, revision=revision, reason=reason, actor=actor, operation_id=operation_id,
                                      effective=effective, expires_at=expires_at, now=now, audit=audit, audit_kwargs=audit_kwargs)
        return result

    def _publish_in(self, conn: sqlite3.Connection, item_id: str, *, revision: int, reason: str, actor: str, operation_id: str,
                    effective: datetime, expires_at: datetime | None, now: str, audit, audit_kwargs: dict) -> dict:
        """发布的全部写入都在调用方的事务里；回退复用它，所以"复制旧正文 + 发布"是一笔，不会留半截。"""
        row = conn.execute("SELECT * FROM admin_content_items WHERE item_id = ?", (item_id,)).fetchone()
        body = self._body_in(conn, item_id, revision)
        if body is None:
            raise AdminAPIError.not_found(f"版本 v{revision}")
        issues = validate(row["content_type"], body)
        asset_id = body.get("image_asset_id") if isinstance(body, dict) else None
        if not issues and asset_id:
            # 草稿存着的这段时间里素材可能被下架或改成内部素材：发布这一刻再查一次库。
            asset = conn.execute("SELECT usage_scope, status FROM admin_assets WHERE asset_id = ?", (asset_id,)).fetchone()
            if asset is None:
                issues = [ValidationIssue("image_asset_id", "素材库里没有这个素材。")]
            elif asset["status"] != "active":
                issues = [ValidationIssue("image_asset_id", "这个素材已经下架了，换一张再发。")]
            elif asset["usage_scope"] != "public":
                issues = [ValidationIssue("image_asset_id", "这是内部素材，不能出现在玩家能看到的公告里。")]
        if issues:
            # 校验不通过就不发布，也不留"发布过"的痕迹；审计记一条 denied（整笔回滚时它也跟着回滚，
            # 所以 denied 的那条由路由层在事务外补记，见 routers/admin/content.py）。
            raise AdminAPIError(AdminErrorCode.validation_failed, "这一版没通过校验，不能发布。", 422,
                                details={"issues": [{"field": i.field, "message": i.message} for i in issues]})
        previous = None if row["live_revision"] is None else int(row["live_revision"])
        diff = _diff_summary(self._body_in(conn, item_id, previous), body)
        try:
            conn.execute(
                "INSERT INTO admin_content_publications (publication_id, item_id, revision, action, effective_at, expires_at, reason, "
                "staff_id, operation_id, diff_summary, created_at) VALUES (?, ?, ?, 'publish', ?, ?, ?, ?, ?, ?, ?)",
                (f"PB-{uuid.uuid4().hex[:16]}", item_id, revision, iso(effective), iso(expires_at) if expires_at else None,
                 reason, actor, operation_id, diff, now),
            )
        except sqlite3.IntegrityError as exc:
            raise AdminAPIError(AdminErrorCode.idempotency_key_reused, "这个操作号已经发布过了。", 409) from exc
        conn.execute("UPDATE admin_content_items SET status = 'published', live_revision = ?, effective_at = ?, expires_at = ?, "
                     "version = version + 1, updated_at = ?, updated_by = ? WHERE item_id = ?",
                     (revision, iso(effective), iso(expires_at) if expires_at else None, now, actor, item_id))
        new_version = int(conn.execute("SELECT version FROM admin_content_items WHERE item_id = ?", (item_id,)).fetchone()["version"])
        # 居民不是覆盖层：发布要真的写进待领养名单，与这笔发布同一个事务。
        applied = self.apply_resident(conn, row["slug"], body) if row["content_type"] == "resident" else None
        audit.record_in(conn, status="succeeded", outcome=f"v{revision}",
                        changes={"revision": revision, "previous_revision": previous, "diff": diff,
                                 "effective_at": iso(effective), "expires_at": iso(expires_at) if expires_at else None,
                                 **({"resident_apply": applied} if applied is not None else {})},
                        **audit_kwargs)
        self.invalidate()
        return {"item_id": item_id, "live_revision": revision, "previous_revision": previous, "version": new_version,
                "effective_at": effective, "expires_at": expires_at, "diff_summary": diff,
                **({"resident_apply": applied, "resident_apply_note": resident_apply_note(applied)} if applied is not None else {})}

    def withdraw(self, item_id: str, *, reason: str, actor: str, operation_id: str, expected_version: int, audit, audit_kwargs: dict) -> dict:
        now = iso(utcnow())
        with unit_of_work(self.storage) as conn:
            row = self._locked(conn, item_id, expected_version)
            if row["live_revision"] is None:
                raise AdminAPIError(AdminErrorCode.conflict, "这条内容当前没有已发布的版本。", 409)
            live = int(row["live_revision"])
            try:
                conn.execute(
                    "INSERT INTO admin_content_publications (publication_id, item_id, revision, action, effective_at, expires_at, reason, "
                    "staff_id, operation_id, diff_summary, created_at) VALUES (?, ?, ?, 'withdraw', ?, NULL, ?, ?, ?, ?, ?)",
                    (f"PB-{uuid.uuid4().hex[:16]}", item_id, live, now, reason, actor, operation_id, "撤下", now),
                )
            except sqlite3.IntegrityError as exc:
                raise AdminAPIError(AdminErrorCode.idempotency_key_reused, "这个操作号已经处理过了。", 409) from exc
            conn.execute("UPDATE admin_content_items SET status = 'withdrawn', live_revision = NULL, version = version + 1, "
                         "updated_at = ?, updated_by = ? WHERE item_id = ?", (now, actor, item_id))
            new_version = int(conn.execute("SELECT version FROM admin_content_items WHERE item_id = ?", (item_id,)).fetchone()["version"])
            audit.record_in(conn, status="succeeded", outcome=f"withdraw:v{live}",
                            changes={"withdrawn_revision": live}, **audit_kwargs)
        self.invalidate()
        return {"item_id": item_id, "withdrawn_revision": live, "live_revision": None, "version": new_version,
                "note": "玩家侧立刻读不到这条内容；已发生的事实与发布历史都保留。"}

    def rollback(self, item_id: str, *, to_revision: int, reason: str, actor: str, operation_id: str, expected_version: int,
                 audit, audit_kwargs: dict) -> dict:
        """回退＝把旧正文复制成一个**新版本号**再发布。历史版本与发布流水一条都不改、不删。"""
        now_dt = utcnow()
        now = iso(now_dt)
        with unit_of_work(self.storage) as conn:
            self._locked(conn, item_id, expected_version)
            body = self._body_in(conn, item_id, to_revision)
            if body is None:
                raise AdminAPIError.not_found(f"版本 v{to_revision}")
            new_revision = int(conn.execute("SELECT COALESCE(MAX(revision), 0) AS m FROM admin_content_revisions WHERE item_id = ?",
                                            (item_id,)).fetchone()["m"]) + 1
            self._insert_revision(conn, item_id, new_revision, body, actor, f"回退到 v{to_revision}", to_revision, now)
            conn.execute("UPDATE admin_content_items SET draft_revision = ?, version = version + 1, updated_at = ?, updated_by = ? WHERE item_id = ?",
                         (new_revision, now, actor, item_id))
            # 复制旧正文与发布新版本在**同一笔**事务里：不会出现"复制好了却没发出去"的半截状态。
            published = self._publish_in(conn, item_id, revision=new_revision, reason=reason, actor=actor, operation_id=operation_id,
                                         effective=now_dt, expires_at=None, now=now, audit=audit,
                                         audit_kwargs={**audit_kwargs, "action": "content.rollback"})
        return {**published, "rolled_back_from": to_revision, "new_revision": new_revision,
                "note": "回退是发布了一个采用旧正文的新版本；历史版本与发布流水都保留，世界时钟与既有事实没有改动。"}

    def _body_in(self, conn: sqlite3.Connection, item_id: str, revision: int | None) -> dict | None:
        if revision is None:
            return None
        row = conn.execute("SELECT body_json FROM admin_content_revisions WHERE item_id = ? AND revision = ?", (item_id, revision)).fetchone()
        return None if row is None else json.loads(row["body_json"])

    # ---- 玩家侧消费 ----
    def _ready(self, conn: sqlite3.Connection) -> bool:
        if self._tables_ready is None:
            self._tables_ready = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN ('admin_content_items','admin_content_revisions')"
            ).fetchone()[0] == 2
        return self._tables_ready

    def live_announcements(self, now: datetime | None = None, *, signed_in: bool = False) -> list[dict]:
        """玩家 API 读这里。只返回**已发布、已生效、未过期**的版本，并带上 revision 以便证明消费的是哪一版。"""
        now = now or utcnow()
        stamp = iso(now)
        with self.storage.connect() as conn:
            if not self._ready(conn):
                return []
            rows = conn.execute(
                "SELECT i.item_id, i.slug, i.live_revision, i.effective_at, i.expires_at, r.body_json "
                "FROM admin_content_items i JOIN admin_content_revisions r ON r.item_id = i.item_id AND r.revision = i.live_revision "
                "WHERE i.content_type = 'announcement' AND i.status = 'published' AND i.live_revision IS NOT NULL "
                "AND i.effective_at <= ? AND (i.expires_at IS NULL OR i.expires_at > ?) ORDER BY i.effective_at DESC",
                (stamp, stamp),
            ).fetchall()
        out = []
        for row in rows:
            body = json.loads(row["body_json"])
            if body.get("audience") == "signed_in" and not signed_in:
                continue
            asset_id = body.get("image_asset_id")
            out.append({"item_id": row["item_id"], "slug": row["slug"], "revision": int(row["live_revision"]),
                        "title": body.get("title", ""), "body": body.get("body", ""), "severity": body.get("severity", "info"),
                        "link": body.get("link"), "image_asset_id": asset_id,
                        # 只给受控入口的地址；素材下架后这个地址会 404，玩家侧不会拿到别处的图。
                        "image_url": f"/api/v1/web/assets/{asset_id}" if asset_id else None,
                        "effective_at": parse_dt(row["effective_at"]),
                        "expires_at": parse_dt(row["expires_at"]) if row["expires_at"] else None})
        return out

    def live(self, content_type: str, slug: str, now: datetime | None = None) -> dict | None:
        """内置目录在取条目时调用（`app/content_overlay.py` 注册的解析器就是它）。

        没有已发布版本就返回 None（走内置值）。带一个很短的进程内缓存：世界推进会反复取目录，
        不能每次都打库。发布 / 撤下 / 回退会立刻让本进程的缓存失效。
        """
        import time

        key = (content_type, slug)
        stamp_now = time.monotonic()
        with self._cache_lock:
            hit = self._overlay_cache.get(key)
            if hit is not None and stamp_now - hit[0] < OVERLAY_CACHE_SECONDS:
                return hit[1]
        body = self._live_uncached(content_type, slug, now)
        with self._cache_lock:
            self._overlay_cache[key] = (stamp_now, body)
        return body

    def _live_uncached(self, content_type: str, slug: str, now: datetime | None) -> dict | None:
        stamp = iso(now or utcnow())
        try:
            with self.storage.connect() as conn:
                if not self._ready(conn):
                    return None
                row = conn.execute(
                    "SELECT i.live_revision, r.body_json FROM admin_content_items i "
                    "JOIN admin_content_revisions r ON r.item_id = i.item_id AND r.revision = i.live_revision "
                    "WHERE i.content_type = ? AND i.slug = ? AND i.status = 'published' AND i.live_revision IS NOT NULL "
                    "AND i.effective_at <= ? AND (i.expires_at IS NULL OR i.expires_at > ?)",
                    (content_type, slug, stamp, stamp),
                ).fetchone()
        except sqlite3.Error:
            return None  # 读不到发布表就用内置值，绝不让后台故障拖垮世界推进
        if row is None:
            return None
        return {"revision": int(row["live_revision"]), **json.loads(row["body_json"])}

    # ---- 居民：发布要真的写进待领养名单（它不是覆盖层，是一张业务表）----
    def apply_resident(self, conn: sqlite3.Connection, slug: str, body: dict | None) -> str:
        """把已发布的居民文案写回 `web_adoption_candidates`；`body=None`（撤下）则还原成内置文案。

        **只动 `availability='available'` 的行**：已被预留或领养的居民，身份与经历必须连续，运营改不了。
        与发布写在同一个事务里，所以"发布成功了但玩家看到的还是旧文案"不会出现。
        """
        row = conn.execute("SELECT availability FROM web_adoption_candidates WHERE candidate_id = ?", (slug,)).fetchone()
        if row is None:
            return "missing"
        if row["availability"] != "available":
            return f"skipped:{row['availability']}"
        if body is None:
            return "withdrawn_noop"  # 撤下不改回原文：原文已经不在别处保存了，强行"还原"会造出一份假事实
        fields = {name: body[name] for name in ("personality", "dream", "source_note") if body.get(name) is not None}
        if not fields:
            return "noop"
        assignments = ", ".join(f"{name} = ?" for name in fields)
        conn.execute(f"UPDATE web_adoption_candidates SET {assignments} WHERE candidate_id = ? AND availability = 'available'",
                     (*fields.values(), slug))
        return "applied"

    def resident_candidates(self, *, only_available: bool = True) -> list[dict]:
        """给后台新建草稿时挑人用。不含任何家庭信息。"""
        sql = ("SELECT candidate_id, name, species, personality, dream, source_note, availability "
               "FROM web_adoption_candidates")
        if only_available:
            sql += " WHERE availability = 'available'"
        with self.storage.connect() as conn:
            return [dict(row) for row in conn.execute(sql + " ORDER BY candidate_id")]
