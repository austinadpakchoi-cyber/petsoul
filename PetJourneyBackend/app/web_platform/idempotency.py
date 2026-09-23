"""统一幂等：按 (user_id, scope, Idempotency-Key) 绑定请求摘要。

- 同键同请求 → 返回首个成功结果（replayed=True），不重复执行副作用；
- 同键不同请求 → 409 IDEMPOTENCY_KEY_REUSED；
- 执行中重入 → 409 IDEMPOTENCY_IN_PROGRESS（retryable）；
- handler 抛错 → 删除占位记录，允许用同键重试；
- 占位超过 IN_PROGRESS_TTL 还没写回结果（进程在写回执之前挂了）→ 视为被遗弃，由这次请求接手重跑，
  不再永远卡在 409（验收 CR-Q5 / 合同 C3a）。
- 接手时换一个新的领取令牌；被接手的那一次醒过来写回执会因为令牌对不上而**写不进去**，
  不会用过期结果覆盖接手者的结果（合同 Q-C3d）。

局限（如实记录）：幂等记录与业务写入不在同一 SQLite 事务中。所以领域侧必须另有稳定唯一键做第二道保险：
金额走 economy_transactions.idempotency_key（唯一），**出门的行程编号由这里的 Idempotency-Key 算出**
（`web_journey.service.stable_journey_id`），卖菜/交订单/农场动作的领域键都带上它——接手重跑时靠它们保证
结果不会变成两份。只靠“一只宠物同时只有一段进行中旅程”这道约束是不够的：原来那趟结束之后它就不拦了。
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable

from fastapi import Request

from ..schemas.web.common import WebErrorCode
from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow
from .errors import WebAPIError

IDEMPOTENCY_HEADER = "Idempotency-Key"
IN_PROGRESS_TTL = timedelta(minutes=5)  # 占位这么久还没写回结果，就认为上一次尝试已经死了，允许接手重跑
_KEY_RE = re.compile(r"^[A-Za-z0-9_\-:.]{8,128}$")


def require_idempotency_key(request: Request) -> str:
    key = request.headers.get(IDEMPOTENCY_HEADER, "").strip()
    if not key:
        raise WebAPIError(WebErrorCode.idempotency_key_required, "缺少 Idempotency-Key 请求头。", 400)
    if not _KEY_RE.match(key):
        raise WebAPIError(WebErrorCode.validation_failed, "Idempotency-Key 格式不正确。", 400)
    return key


def request_digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class IdempotentOutcome:
    response: dict[str, Any]
    replayed: bool


class IdempotencyStore:
    def __init__(self, storage: JourneyStorage) -> None:
        self.storage = storage

    def run(
        self,
        *,
        user_id: str,
        scope: str,
        key: str,
        payload: Any,
        handler: Callable[[], dict[str, Any]],
    ) -> IdempotentOutcome:
        digest = request_digest(payload)
        now = iso(utcnow())
        token = uuid.uuid4().hex  # 这次领取的令牌：写回执时要对得上，被接手过就作废
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT request_hash, status, response_json, updated_at FROM web_idempotency_keys "
                "WHERE user_id = ? AND scope = ? AND idem_key = ?",
                (user_id, scope, key),
            ).fetchone()
            if row is not None:
                if row["request_hash"] != digest:
                    raise WebAPIError(
                        WebErrorCode.idempotency_key_reused, "同一个 Idempotency-Key 被用于不同的请求。", 409
                    )
                if row["status"] == "completed":
                    return IdempotentOutcome(response=json.loads(row["response_json"]), replayed=True)
                if utcnow() - parse_dt(row["updated_at"]) < IN_PROGRESS_TTL:
                    raise WebAPIError(
                        WebErrorCode.idempotency_in_progress, "相同请求正在处理中。", 409, retryable=True
                    )
                # 上一次尝试没能写回结果（进程挂了）：接手重跑。领域侧的稳定键保证结果不会变成两份
                conn.execute(
                    "UPDATE web_idempotency_keys SET updated_at = ?, claim_token = ? WHERE user_id = ? AND scope = ? AND idem_key = ?",
                    (now, token, user_id, scope, key),
                )
            else:
                conn.execute(
                    "INSERT INTO web_idempotency_keys (user_id, scope, idem_key, request_hash, status, response_json, created_at, updated_at, claim_token) "
                    "VALUES (?, ?, ?, ?, 'in_progress', NULL, ?, ?, ?)",
                    (user_id, scope, key, digest, now, now, token),
                )
        try:
            response = handler()
        except BaseException:
            with self.storage.connect() as conn:
                conn.execute(  # 只清自己那次领取：被接手之后失败，不能把接手者的占位也删掉
                    "DELETE FROM web_idempotency_keys WHERE user_id = ? AND scope = ? AND idem_key = ? "
                    "AND status = 'in_progress' AND claim_token = ?",
                    (user_id, scope, key, token),
                )
            raise
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            written = conn.execute(
                "UPDATE web_idempotency_keys SET status = 'completed', response_json = ?, updated_at = ? "
                "WHERE user_id = ? AND scope = ? AND idem_key = ? AND claim_token = ?",
                (json.dumps(response, ensure_ascii=False, default=str), iso(utcnow()), user_id, scope, key, token),
            ).rowcount
            if written == 0:  # 这次领取已经被接手：别人的结果才算数，不用过期结果覆盖它
                row = conn.execute(
                    "SELECT status, response_json FROM web_idempotency_keys WHERE user_id = ? AND scope = ? AND idem_key = ?",
                    (user_id, scope, key),
                ).fetchone()
            else:
                row = None
        if row is not None and row["status"] == "completed" and row["response_json"] is not None:
            return IdempotentOutcome(response=json.loads(row["response_json"]), replayed=True)
        return IdempotentOutcome(response=response, replayed=False)
