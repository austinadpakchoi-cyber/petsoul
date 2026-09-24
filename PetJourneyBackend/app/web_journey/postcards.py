"""店内“合影”没有生成照片时的纸质卡片（SVG，程序排版，私有存储）。

用户 2026-09-22：不把宠物卡通化。所以这里不画任何动物形象，只是一张邮戳、地点和日期的卡片；
写实照片由生图服务（主人开启“生成照片”后）另行生成。文字全部经过 XML 转义，响应带严格 CSP。
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from ..storage import JourneyStorage
from ..utils import iso
from ..web_platform.tasks import WebTaskQueue
from .repository import JourneyRecord, VisitRecord

PALETTES = [("#F4EAD5", "#B9553B", "#3B2F22"), ("#E9F1EC", "#2F7D5E", "#203129"), ("#EEF3FA", "#3F8FB1", "#1F2B38")]


def local_date(moment: datetime, timezone: str | None) -> str:
    """把拍摄那一刻换算成 TA **当时所在地**的墙上日期。

    途中所在地会变：拿出发地或 UTC 换算，夜里寄出的卡片会被写成前一天。时区不明就按 UTC 写，不假装知道。
    """
    if timezone:
        try:
            return moment.astimezone(ZoneInfo(timezone)).strftime("%Y.%m.%d")
        except Exception:  # noqa: BLE001 - 时区名不认识：退回 UTC，不要因为一张卡片让这次拍照失败
            pass
    return moment.strftime("%Y.%m.%d")


def render_svg(pet_name: str, place_name: str, city: str, seed: str, date_text: str | None = None) -> str:
    bg, accent, ink = PALETTES[int(hashlib.sha1(seed.encode()).hexdigest(), 16) % len(PALETTES)]
    pet = escape(pet_name[:12])
    place = escape(place_name[:24])
    city_text = escape(city[:12])
    date = escape((date_text or "")[:16])
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 400" width="600" height="400">
<rect width="600" height="400" rx="24" fill="{bg}"/>
<rect x="24" y="24" width="552" height="352" rx="16" fill="none" stroke="{accent}" stroke-width="3" stroke-dasharray="10 8"/>
<rect x="470" y="48" width="86" height="104" rx="6" fill="#FFFDF8" stroke="{accent}" stroke-width="3" stroke-dasharray="4 4"/>
<text x="513" y="108" font-size="22" font-weight="700" text-anchor="middle" fill="{accent}" font-family="sans-serif">{city_text}</text>
<circle cx="430" cy="120" r="46" fill="none" stroke="{ink}" stroke-width="2" opacity="0.45"/>
<text x="430" y="116" font-size="13" text-anchor="middle" fill="{ink}" opacity="0.6" font-family="sans-serif">{city_text}</text>
<text x="430" y="134" font-size="11" text-anchor="middle" fill="{ink}" opacity="0.6" font-family="sans-serif">{date}</text>
<line x1="60" y1="250" x2="540" y2="250" stroke="{ink}" stroke-width="1.5" opacity="0.25"/>
<line x1="60" y1="300" x2="540" y2="300" stroke="{ink}" stroke-width="1.5" opacity="0.25"/>
<text x="60" y="110" font-size="30" font-weight="700" fill="{ink}" font-family="sans-serif">{place}</text>
<text x="60" y="150" font-size="20" fill="{ink}" opacity="0.75" font-family="sans-serif">来自 {pet}</text>
<text x="60" y="340" font-size="16" fill="{ink}" opacity="0.6" font-family="sans-serif">{city_text} · 纸质卡片（没有照片）</text>
</svg>"""


class PostcardService:
    def __init__(self, storage: JourneyStorage, media_root: Path, tasks: WebTaskQueue) -> None:
        self.storage = storage
        self.root = media_root
        self.tasks = tasks
        self.can_view_pet = None  # (user_id, pet_id) → 是否是这只宠物所在家庭的有效成员

    def make(self, conn, visit: VisitRecord, journey: JourneyRecord, pet_name: str, *, captured_at: datetime) -> str:
        """纸质卡片：卡片记录写在**调用方的写事务**里，和 visit 更新、`photo_taken` 事件同生共死（CR-C11）。

        `captured_at` 是主人按下"拍一张"的那一刻；卡片上的日期按 `visit.place["timezone"]`
        （TA **当时所在地**）换算，不是渲染时刻、也不是出发地时区。
        同一次到访只做一张：在这个写事务里先查后写，`BEGIN IMMEDIATE` 保证没有并发写者，
        不再需要原来那把"排一个任务当去重锁、随即完成它"的空转（没有任何消费者读它）。
        文件写在事务之外——文件系统没有事务。整笔回滚时留下的只是一个没人引用的 SVG；
        反过来（库里有卡片、文件却不在）才是用户看得见的坏结果，所以先写文件、后写库。
        """
        existing = conn.execute("SELECT photo_id FROM web_postcards WHERE visit_id = ?", (visit.visit_id,)).fetchone()
        if existing is not None:
            return self.url(existing["photo_id"])
        photo_id = f"pc-{uuid.uuid4().hex[:12]}"
        folder = self.root / "postcards" / visit.user_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{photo_id}.svg").write_text(
            render_svg(pet_name, visit.place["name"], journey.city, photo_id, local_date(captured_at, visit.place.get("timezone"))), encoding="utf-8")
        conn.execute(
            "INSERT OR IGNORE INTO web_postcards (photo_id, user_id, pet_id, visit_id, rel_path, is_public, created_at) VALUES (?, ?, ?, ?, ?, 0, ?)",
            (photo_id, visit.user_id, visit.pet_id, visit.visit_id, f"postcards/{visit.user_id}/{photo_id}.svg", iso(captured_at)),
        )
        return self.url(photo_id)

    @staticmethod
    def url(photo_id: str) -> str:
        return f"/api/v1/web/media/postcards/{photo_id}"

    def _by_visit(self, visit_id: str) -> str | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT photo_id FROM web_postcards WHERE visit_id = ?", (visit_id,)).fetchone()
        return row["photo_id"] if row else None

    def mark_public(self, photo_id: str) -> None:
        with self.storage.connect() as conn:
            conn.execute("UPDATE web_postcards SET is_public = 1 WHERE photo_id = ?", (photo_id,))

    def file_for(self, viewer_user_id: str | None, photo_id: str) -> Path | None:
        """家庭成员可以看自家宠物的明信片；公开的（发成了公开动态）谁都可以看。被移出家庭后立即看不到非公开的。"""
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM web_postcards WHERE photo_id = ?", (photo_id,)).fetchone()
        if row is None:
            return None
        if not row["is_public"]:
            if viewer_user_id is None:
                return None
            allowed = self.can_view_pet(viewer_user_id, row["pet_id"]) if self.can_view_pet is not None else row["user_id"] == viewer_user_id
            if not allowed:
                return None
        path = (self.root / row["rel_path"]).resolve()
        try:
            path.relative_to(self.root.resolve())
        except ValueError:
            return None
        return path if path.is_file() else None
