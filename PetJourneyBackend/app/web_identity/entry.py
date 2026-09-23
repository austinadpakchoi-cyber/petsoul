"""注册入口与待确认的选择（0.4.0）：先逛逛 / 接我的宠物入住 / 认识新伙伴 / 家庭邀请直达。

只记录，不替用户做决定：注册完成后页面读出这里恢复选择，重新校验（伙伴还在不在、邀请有没有过期），再请用户确认。
邀请只记邀请编号（令牌原文不落库）。用户完成对应动作（领养/建宠/接受邀请）后标记已处理。
"""

from __future__ import annotations

from datetime import datetime

from ..storage import JourneyStorage
from ..utils import iso, parse_dt


class EntryStore:
    def __init__(self, storage: JourneyStorage) -> None:
        self.storage = storage

    def record(self, user_id: str, kind: str, target_pet_id: str | None, invite_id: str | None, now: datetime) -> None:
        with self.storage.connect() as conn:
            conn.execute(
                "INSERT INTO web_user_entry (user_id, kind, target_pet_id, invite_id, created_at, resolved_at) VALUES (?, ?, ?, ?, ?, NULL) "
                "ON CONFLICT(user_id) DO UPDATE SET kind = excluded.kind, target_pet_id = excluded.target_pet_id, invite_id = excluded.invite_id, "
                "created_at = excluded.created_at, resolved_at = NULL",
                (user_id, kind, target_pet_id, invite_id, iso(now)),
            )

    def pending(self, user_id: str) -> dict | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM web_user_entry WHERE user_id = ? AND resolved_at IS NULL", (user_id,)).fetchone()
        if row is None:
            return None
        return {"kind": row["kind"], "target_pet_id": row["target_pet_id"], "invite_id": row["invite_id"], "created_at": parse_dt(row["created_at"])}

    def resolve(self, user_id: str, now: datetime) -> None:
        with self.storage.connect() as conn:
            conn.execute("UPDATE web_user_entry SET resolved_at = ? WHERE user_id = ? AND resolved_at IS NULL", (iso(now), user_id))
