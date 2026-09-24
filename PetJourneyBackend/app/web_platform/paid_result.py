"""已付费结果的认领：付费调用成功了、结果却没写进去，**自动重试时认领那张已经付过钱的图**，不再付第二次。

用户 2026-09-24 派单「修角色、插画的成功结果恢复，Q 用禁网故障注入复验」。缺口是 A 登记、Q 核实的：
重试前的"不重发"闸只把预占停在 `reserved / unknown / expired` 当成"可能发过"，**`settled ＋ succeeded` 不算**——
于是发布事务里任何一个异常、丢了租约、进程在写库前崩溃，重试都会**再调一次供应商**。
Q 在 C29 的数据里见过一次活体：同一个任务 `:1`、`:2` 两笔预占都是 settled/succeeded，两次都真的付了钱。
**续租治不了它**：续租本身就要写锁；而且丢租约只是触发条件之一，根因是"付费的副作用已经发生、记录它的写入还没提交"这个窗口。

补法分两半，**两条链路（角色、插画）共用这一份**：

  - **落盘时写小票**（`write_receipt`）：在图旁边写 `<stem>.receipt.json`，记图的相对路径、sha256、mime、provider、model。
    先写图、后写小票；小票先写临时文件再替换，半截的小票不会被读到。
  - **自动重试时先问上一次**（`resume`）：看这个任务**代数最大**的那一笔预占——

        reserved / unknown / expired  → 可能发过、结果不明 → 不重发（与原先相同）
        settled ＋ succeeded          → 凭小票认领：图在、sha256 对得上 → **不预占、不发送**，直接拿去发布
                                        小票或图找不到、对不上 → 按"结果不明"停下，**不自动再付一次**
        其余（released 确定没发出、settled ＋ failed）→ 照常重试

**"不重发"只管自动重试，"认领"不分自动还是显式**：

  - 角色链路只在自动重试（`task.last_error` 非空）时问这里——「调整形象」是新建任务，本就没有上一次；
  - 插画链路在**重新执行**时都问（自动重试，或主人点「重画」）：重画只对 failed 的任务开放，
    那张付过钱的图主人从没见过，认领它就是主人要的那张，没有理由再付一次；
    但重画会清掉 `last_error`，"可能发过就不重发"那一条**不拦重画**——没有可认领的图时，那是主人明确要的一次新的付费尝试。
    角色与插画的任务都最多跑 2 次：第二次认领后发布又失败，插画还能靠重画第三次认领；角色则进终态（不重付，图留在磁盘上）。

修复之前发生的 settled/succeeded 没有小票——按"结果不明"停下。**宁可这一张不画，也不重复付费**；主人可以显式重画。
这是取舍：**"不重复付费"做到了，"不浪费已付费的结果"在这一支没做到**——那张图若还在磁盘上，也不会被发布。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from ..image_provider.models import GeneratedImage

logger = logging.getLogger("petsoul.web.paid_result")

# 预占停在这几种状态＝**可能已经发出、结果不明**：恢复回来也不重发。两条链路都从这里取，不各抄一份。
MAYBE_SENT = ("reserved", "unknown", "expired")
RECEIPT_SUFFIX = ".receipt.json"


@dataclass(frozen=True, slots=True)
class Resumed:
    """上一次尝试留下的结局。`image` 非空＝认领到了那张已付费的图；`blocked` 非空＝这一次不许再发。"""

    attempt: int | None
    image: GeneratedImage | None = None
    rel: str | None = None
    extra: dict = field(default_factory=dict)
    blocked: str | None = None


def write_receipt(root: Path, stem: str, rel: str, image: GeneratedImage, **extra) -> None:
    """图已经写到 `root/rel` 之后调用，在同一个 stem 上写小票。

    **写小票失败不往外抛**：这一次的图就在内存里，照样可以发布；小票只在"发布失败之后的重试"才用得上。
    为一张写不下的小票让一次成功的付费尝试失败，就是自己制造一次重试。
    """
    receipt = {"rel": rel, "sha256": hashlib.sha256(image.image_bytes).hexdigest(), "mime_type": image.mime_type,
               "provider": image.provider, "model": image.model, "extra": extra}
    path = Path(root) / (stem + RECEIPT_SUFFIX)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)
    except OSError as exc:
        logger.warning("paid result receipt not written stem=%s: %s", stem, type(exc).__name__)


def resume(storage, prefix: str, root: Path, stem_template: str) -> Resumed | None:
    """自动重试之前问上一次。返回 None＝没有需要接手的，照常执行。

    `prefix` 是这个任务的预占编号前缀（如 `character:<task_id>:`），编号末尾是那一次领取的代数；
    `stem_template` 含 `{attempt}`，按**那一次的代数**找小票——不是按这一次的。
    """
    last = _last_reservation(storage, prefix)
    if last is None:
        return None
    if isinstance(last, str):
        return Resumed(None, blocked=last)  # 读不到账本：不敢再发一次
    status, outcome, attempt = last
    if status in MAYBE_SENT:
        return Resumed(attempt, blocked=f"previous_{status}")
    if status != "settled" or outcome != "succeeded":
        return None  # 确定没发出（released），或发出去但供应商说失败了：照常重试，与原先相同
    found = _reclaim(Path(root), stem_template.format(attempt=attempt)) if attempt is not None else None
    if found is None:
        # 钱付了、图找不到（写图前崩了、小票没写下、文件被换过）：**不自动再付一次**
        return Resumed(attempt, blocked="paid_result_missing")
    image, rel, extra = found
    return Resumed(attempt, image=image, rel=rel, extra=extra)


def _last_reservation(storage, prefix: str) -> tuple[str, str | None, int | None] | str | None:
    """这个任务**代数最大**的那一笔预占：(status, outcome, 代数)。没有记录返回 None，读不到账本返回原因串。"""
    escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    # 按编号末尾的代数取最近一次；代数不是数字时 CAST 得 0，排在最后，不会被误判成最近
    sql = ("SELECT status, outcome, operation_id FROM web_budget_reservations WHERE operation_id LIKE ? ESCAPE '\\' "
           "ORDER BY CAST(substr(operation_id, ?) AS INTEGER) DESC, rowid DESC LIMIT 1")
    try:
        with storage.connect() as conn:
            row = conn.execute(sql, (escaped + "%", len(prefix) + 1)).fetchone()
    except sqlite3.Error as exc:
        if isinstance(exc, sqlite3.OperationalError) and "no such table" in str(exc).lower():
            return None  # 迁移 0050 之前的库：没有额度表，无从判断，维持原来的重试行为
        logger.warning("paid result ledger lookup failed prefix=%s: %s", prefix, type(exc).__name__)
        return "ledger_unreadable"
    if row is None:
        return None
    suffix = row["operation_id"][len(prefix):]
    return row["status"], row["outcome"], int(suffix) if suffix.isdigit() else None


def _reclaim(root: Path, stem: str) -> tuple[GeneratedImage, str, dict] | None:
    """按小票找回那张图，**字节现算 sha256** 与小票比对。任何一处对不上都返回 None——不认一张说不清来历的图。"""
    try:
        receipt = json.loads((root / (stem + RECEIPT_SUFFIX)).read_text(encoding="utf-8"))
        rel = receipt["rel"]
        if not isinstance(rel, str) or not rel.startswith(stem + "."):
            return None  # 小票指向的不是这一次那张图
        path = (root / rel).resolve()
        path.relative_to(root.resolve())
        data = path.read_bytes()
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if hashlib.sha256(data).hexdigest() != receipt.get("sha256"):
        return None
    image = GeneratedImage(image_bytes=data, mime_type=receipt.get("mime_type") or "image/png",
                           model=receipt.get("model") or "", provider=receipt.get("provider") or "", source="reclaimed")
    extra = receipt.get("extra") if isinstance(receipt.get("extra"), dict) else {}
    return image, rel, extra
