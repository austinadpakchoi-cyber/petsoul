"""星球通讯器：主人 ↔ 专属宠物的私密通讯。

- 主人消息以 client_message_id 幂等：断网重发不产生重复消息；
- 何时回复由 TA 此刻的真实状态决定（web_agent.reply_policy）：在家很快；在路上/店里晚几分钟；
  睡着等到醒来、飞行等到落地——这些推迟的消息排队，到点一定回复，多条合并成一次；不伪装“正在输入”；
- 主人情绪危机时立即以固定关怀回应接住，并给出求助渠道（不经模型）；
- 回复读取宠物 DNA 与经 MemoryPolicy(private_chat) 投影的已确认叮嘱；主人原话不写入任何宠物记忆；
- 意图判断层默认关闭；开启 assist 时只影响回复措辞，不会据此改旅程、删记忆或执行操作；
- 世界事件（出发/到港/到店/合影/回家）生成宠物来信，按 source_event_id 只生成一次；
- TA 主动发来的消息（早安/分享/晚安）由 web_agent.proactive 决定时机，这里只负责写入（按话题+日期幂等）。

0.4.0 家庭共同照顾：两个频道放在同一张表里。
- private：某位家人与 TA 的私聊（主人消息、TA 的回复、TA 主动找这位家人说的话），只有这位家人看得到；
- family：家庭频道（user_id='*'）——出发/到港/到店/合影/回家/打工这些世界事件来信、寄明信片、写攻略、菜园守护与遇到朋友的新鲜事，
  全家成员都看得到，同一件事只有一条（UNIQUE(pet_id, source_event_id)）；待领养居民还没有家庭，不产生家庭来信；
- 每位成员看到的会话＝自己的私聊 + 家庭频道，已读状态各自保存；主人私聊原话不会出现在别的家人那里。
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta
from typing import Callable

from ..schemas.web.common import DataOrigin
from ..schemas.web.pets import PetPresence
from ..schemas.web.social import (
    MessageChannel,
    MessageComposer,
    MessageDeliveryState,
    MessageSender,
    MessageSummary,
    MessageThread,
    MessageTopic,
    PhotoStatus,
)
from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow
from ..web_platform.tasks import redraw_ticket
from ..web_platform.uow import execute_in, unit_of_work
from ..web_agent import is_distress, plan_reply
from ..web_agent.moment import PetMoment
from .persona import PetPersona, build_messages, care_reply, clean_reply, template_reply

WORLD_SOURCE = re.compile(r"^jn-[0-9a-f]+:[a-z_]+(:[0-9a-z_-]+)?$")  # 世界事件来源：<journey_id>:<事件键>
REPLY_CLAIM = timedelta(minutes=5)  # 待回复的领取期限：领取者崩溃后，过期就能被别的进程重新领取
# 还没兑现的待回复：没人领取，或者领取已过期（旧数据没有期限的 claim-* 也算过期）
OPEN_PENDING = "(delivered_message_id IS NULL OR (delivered_message_id LIKE 'claim-%' AND (claimed_until IS NULL OR claimed_until <= ?)))"

EVENT_TEXT = {
    "departed": "出发啦！这次去{title}，路上看到好玩的就告诉你。",
    "leg_arrived": "{place}到了，我还好，接着往前走。",
    "visit_started": "到{venue}啦，我先找个位置坐下。",
    "returned_home": "我回来啦！带了点东西给你，放在回忆柜里了。",
}
# 家附近的日常出门与打工（destination_key 以 local:/work: 开头）
DAILY_TEXT = {
    ("departed", "local:stroll"): "我出门走走，一会儿就回来。",
    ("departed", "local:cafe"): "我去附近喝一杯，到了告诉你是哪家。",
    ("departed", "local:city_trip"): "我进城逛逛去啦！",
    ("departed", "work"): "我去{title}啦，今天要好好干活赚钱！",
    ("returned_home", "local"): "我回来啦，外面挺好玩的。",
    ("returned_home", "work"): "干完活回到家啦，有点累，但是很开心。",
    ("work_done", "work"): "{title}干完啦，赚了 {pay}，已经存进我的银行卡。",
}
STAY_HOME = re.compile(r"(别出门|不要出门|别出去|不要出去|今天在家|待在家|呆在家|别乱跑|今天休息)")
CATCH_UP = {
    "asleep": "你刚睡醒，才看到主人在你睡着时发来的消息。",
    "in_flight": "你刚落地，才看到主人在你飞行时发来的消息。",
}
CATCH_UP_TEMPLATE = {"asleep": "刚睡醒，看到你的消息啦。", "in_flight": "刚落地，看到你的消息啦。"}
FAMILY = "*"  # 家庭频道消息的 user_id
# 插画已经结束、但没有图的两种状态：failed＝确定没画成；unknown＝可能已受理、结果没确认。两者都给“重画”入口
UNRESOLVED_PHOTO = (PhotoStatus.failed.value, PhotoStatus.unknown.value)
VISIBLE = "(channel = 'family' OR (channel = 'private' AND user_id = ?))"  # 某位家人能看到的消息


class WebCommunicatorService:
    def __init__(self, storage: JourneyStorage) -> None:
        self.storage = storage
        self.presence_of: Callable[[str], PetPresence] = lambda pet_id: PetPresence.at_home
        self.moment_of: Callable[[str, datetime], PetMoment | None] = lambda pet_id, now: None
        self.owner_title_of: Callable[[str, str], str | None] = lambda user_id, pet_id: None
        self.reply_style_of: Callable[[str, str], str | None] = lambda user_id, text: None
        self.on_owner_activity: Callable[[str, datetime], None] = lambda user_id, now: None
        # 模型回信（主人在设置里开启且供应商可用时）；失败/超限回到模板回应，并如实标注来源
        self.chat = None
        self.model_replies_of: Callable[[str], bool] = lambda user_id: False
        self.persona_of: Callable[[str, str], PetPersona | None] = lambda user_id, pet_id: None
        # 冒险插画：返回任务号表示已排队（主人开启“生成冒险插画”且供应商可用）
        self.illustration_request: Callable[[object], str | None] = lambda event: None
        # 宠物所在的家庭（待领养居民为 None：没有家庭频道）
        self.household_of: Callable[[str], str | None] = lambda pet_id: None
        # 这张图的终态口径，**必须在调用方的那个 conn 上读**（装配注入
        # `lambda conn, task_id: illustrations.outcome_of(task_id, conn)`）："failed"＝确定没画成、"unknown"＝可能已受理。
        # 不能用另开连接的版本：那既读不到本事务的快照，也会和自己的写事务争锁。
        # 没接线时按 failed 记——比永远停在“正在画”好，但那样分不出“还没确认”那一档。
        self.illustration_outcome_in: Callable[..., str | None] | None = None

    # ---- 写入 ----
    def _insert(self, conn, *, user_id, pet_id, sender, text, created_at, available_at, client_message_id=None, source_event_id=None,
                reply_to=None, photo_url=None, composed_by=None, topic=None, status_note=None, expected_at=None) -> str:
        message_id = f"msg-{uuid.uuid4().hex[:12]}"
        conn.execute(
            "INSERT INTO web_messages (message_id, user_id, pet_id, sender, client_message_id, source_event_id, reply_to, text, photo_url, created_at, available_at, "
            "composed_by, topic, status_note, expected_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (message_id, user_id, pet_id, sender, client_message_id, source_event_id, reply_to, text, photo_url, iso(created_at), iso(available_at), composed_by,
             topic, status_note, iso(expected_at) if expected_at else None),
        )
        return message_id

    def _history(self, user_id: str, pet_id: str, now: datetime, exclude: set[str] | None = None) -> list[tuple[str, str]]:
        """这位家人能看到的最近几条（自己的私聊 + 家庭频道的事件来信），给模型当上下文；看不到别的家人的私聊。"""
        with self.storage.connect() as conn:
            rows = conn.execute(f"SELECT message_id, sender, text FROM web_messages WHERE pet_id = ? AND {VISIBLE} AND available_at <= ? "
                                "ORDER BY available_at DESC, rowid DESC LIMIT 12", (pet_id, user_id, iso(now))).fetchall()
        return [(r["sender"], r["text"]) for r in reversed(rows) if not exclude or r["message_id"] not in exclude][-8:]

    def _persona(self, user_id: str, pet_id: str) -> PetPersona:
        return self.persona_of(user_id, pet_id) or PetPersona(name="TA", species="other", owner_title=self.owner_title_of(user_id, pet_id))

    def _compose_reply(self, user_id: str, pet_id: str, text: str, style: str | None, now: datetime, seed: str,
                       history: list[tuple[str, str]], catch_up: str | None = None) -> tuple[str, str]:
        """(回复文字, 来源)。模型不可用、超限、超时或输出不合格时回到模板，不改用其他供应商。"""
        persona = self._persona(user_id, pet_id)
        chat = self.chat
        if chat is not None and getattr(chat, "available", False) and self.model_replies_of(user_id):
            messages = build_messages(persona, history, text, style)
            if catch_up in CATCH_UP:
                messages[0]["content"] += f"\n{CATCH_UP[catch_up]}"
            try:
                result = chat.complete(messages, max_tokens=160, temperature=0.8)
                reply = clean_reply(result.text)
                if reply:
                    return reply, MessageComposer.model.value
            except Exception:  # noqa: BLE001 - ChatUnavailable 等：回到模板回应
                pass
        presence = self.presence_of(pet_id)
        reply = template_reply(persona, presence.value, style, seed)
        if catch_up in CATCH_UP_TEMPLATE:
            reply = f"{CATCH_UP_TEMPLATE[catch_up]}{reply}"
        return reply, MessageComposer.template.value

    def send(self, user_id: str, pet_id: str, client_message_id: str, text: str, now: datetime | None = None) -> MessageSummary:
        now = now or utcnow()
        with self.storage.connect() as conn:
            existing = conn.execute("SELECT * FROM web_messages WHERE pet_id = ? AND client_message_id = ?", (pet_id, client_message_id)).fetchone()
            if existing is not None:
                if existing["user_id"] != user_id:
                    raise PermissionError("not your message")
                return self._summary(existing, now)
        self.on_owner_activity(user_id, now)
        clean = text.strip()
        distress = is_distress(clean)
        moment = self.moment_of(pet_id, now)
        seed = f"{pet_id}:{client_message_id}"
        plan = plan_reply(moment, now, distress=distress, seed=seed) if moment else None
        due_at = plan.due_at if plan else now
        note = plan.note if plan else None
        reason = plan.reason if plan else "at_home"
        queued_until, scheduled_until = self._queue_state(user_id, pet_id, now)
        compose_now = plan is None or plan.compose_now(now)
        if queued_until is not None and not distress:
            # 前面还有排队中的消息（例如 TA 还没醒）：这条并入同一批，到时一起回
            due_at, compose_now = queued_until, False
        elif scheduled_until is not None and scheduled_until >= due_at:
            due_at = scheduled_until + timedelta(seconds=2)  # 回复按主人发送的先后出现
        reply = None
        if compose_now:
            if distress:
                reply = (care_reply(self._persona(user_id, pet_id)), MessageComposer.template.value)
            else:
                reply = self._compose_reply(user_id, pet_id, clean, self.reply_style_of(user_id, clean), now, seed, self._history(user_id, pet_id, now))
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            message_id = self._insert(conn, user_id=user_id, pet_id=pet_id, sender="owner", text=clean, created_at=now, available_at=now,
                                      client_message_id=client_message_id, status_note=note, expected_at=due_at)
            if reply is not None:
                self._insert(conn, user_id=user_id, pet_id=pet_id, sender="pet", text=reply[0], created_at=now, available_at=due_at,
                             reply_to=message_id, composed_by=reply[1])
            else:
                conn.execute("INSERT INTO web_pending_replies (owner_message_id, user_id, pet_id, due_at, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                             (message_id, user_id, pet_id, iso(due_at), reason, iso(now)))
            row = conn.execute("SELECT * FROM web_messages WHERE message_id = ?", (message_id,)).fetchone()
        return self._summary(row, now)

    def _queue_state(self, user_id: str, pet_id: str, now: datetime) -> tuple[datetime | None, datetime | None]:
        """(排队中回复的最晚到点时间, 已排定但还没出现的回复的最晚时间)。"""
        with self.storage.connect() as conn:
            queued = conn.execute("SELECT MAX(due_at) AS t FROM web_pending_replies WHERE user_id = ? AND pet_id = ? AND delivered_message_id IS NULL",
                                  (user_id, pet_id)).fetchone()
            scheduled = conn.execute("SELECT MAX(available_at) AS t FROM web_messages WHERE user_id = ? AND pet_id = ? AND sender = 'pet' AND reply_to IS NOT NULL "
                                     "AND available_at > ?", (user_id, pet_id, iso(now))).fetchone()
        return (parse_dt(queued["t"]) if queued["t"] else None, parse_dt(scheduled["t"]) if scheduled["t"] else None)

    # ---- 排队回复：到点一定回复，多条合并成一次 ----
    def deliver_due(self, now: datetime | None = None, user_id: str | None = None, pet_id: str | None = None) -> int:
        now = now or utcnow()
        where, params = f"{OPEN_PENDING} AND due_at <= ?", [iso(now), iso(now)]
        if pet_id is not None:
            where += " AND pet_id = ? AND user_id = ?"
            params += [pet_id, user_id]
        with self.storage.connect() as conn:
            groups = conn.execute(f"SELECT DISTINCT user_id, pet_id FROM web_pending_replies WHERE {where}", params).fetchall()
        delivered = 0
        for group in groups:
            delivered += self._deliver_group(group["user_id"], group["pet_id"], now)
        return delivered

    def pending_summary(self, pet_id: str, now: datetime | None = None) -> list[dict]:
        """只读：这只宠物每个会话里还没兑现的回复承诺（给心跳当“到期事项”）。不含正文，也不兑现任何回复。"""
        now = now or utcnow()
        with self.storage.connect() as conn:
            rows = conn.execute(f"SELECT user_id, MIN(due_at) AS due_at, COUNT(*) AS inputs FROM web_pending_replies "
                                f"WHERE pet_id = ? AND {OPEN_PENDING} GROUP BY user_id", (pet_id, iso(now))).fetchall()
        return [{"ref": f"reply:{row['user_id']}:{pet_id}", "user_id": row["user_id"], "due_at": parse_dt(row["due_at"]), "inputs": int(row["inputs"])}
                for row in rows]

    def _deliver_group(self, user_id: str, pet_id: str, now: datetime) -> int:
        """领取（带期限的令牌）→ 事务外组织回复（可能调模型）→ 同一事务里复核成员关系与领取令牌后发布。
        领取者崩溃：期限一过别人重新领取；旧领取者晚到的回复按令牌作废，不会发两条；这位家人已被移除：记为 suppressed，不再回复。"""
        claim = f"claim-{uuid.uuid4().hex[:10]}"
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(f"UPDATE web_pending_replies SET delivered_message_id = ?, claimed_until = ? WHERE user_id = ? AND pet_id = ? AND due_at <= ? AND {OPEN_PENDING}",
                         (claim, iso(now + REPLY_CLAIM), user_id, pet_id, iso(now), iso(now)))
            pending = conn.execute("SELECT p.owner_message_id, p.due_at, p.reason, m.text FROM web_pending_replies p JOIN web_messages m ON m.message_id = p.owner_message_id "
                                   "WHERE p.delivered_message_id = ? ORDER BY m.created_at, m.rowid", (claim,)).fetchall()
        if not pending:
            return 0
        ids = {r["owner_message_id"] for r in pending}
        texts = [r["text"] for r in pending]
        due_at = max(parse_dt(r["due_at"]) for r in pending)
        reason = pending[-1]["reason"]
        combined = "\n".join(texts)
        if is_distress(combined):
            reply = (care_reply(self._persona(user_id, pet_id)), MessageComposer.template.value)
        else:
            history = self._history(user_id, pet_id, now, exclude=ids)
            reply = self._compose_reply(user_id, pet_id, combined, self.reply_style_of(user_id, texts[-1]), now, f"{pet_id}:{claim}", history, catch_up=reason)
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if not self._member_in(conn, user_id, pet_id):
                conn.execute("UPDATE web_pending_replies SET delivered_message_id = 'suppressed', outcome = 'suppressed', claimed_until = NULL "
                             "WHERE delivered_message_id = ?", (claim,))
                return 0
            message_id = self._insert(conn, user_id=user_id, pet_id=pet_id, sender="pet", text=reply[0], created_at=now, available_at=min(due_at, now),
                                      reply_to=pending[-1]["owner_message_id"], composed_by=reply[1])
            kept = conn.execute("UPDATE web_pending_replies SET delivered_message_id = ?, outcome = 'delivered', claimed_until = NULL WHERE delivered_message_id = ?",
                                (message_id, claim)).rowcount
            if kept != len(pending):
                conn.rollback()  # 领取已过期并被别人重新领取：这次的回复作废，不发布
                return 0
        return 1

    @staticmethod
    def _member_in(conn, user_id: str, pet_id: str) -> bool:
        """发布前在同一个事务里复核：宠物有家庭时，这位家人必须仍是有效成员（被移除、已退出就不再回复）。"""
        household = conn.execute("SELECT household_id FROM web_household_pets WHERE pet_id = ?", (pet_id,)).fetchone()
        if household is None:
            return True  # 旧数据或居民：没有家庭关系可复核，沿用发送时的权限检查
        return conn.execute("SELECT 1 FROM web_household_members WHERE household_id = ? AND user_id = ? AND status = 'active'",
                            (household["household_id"], user_id)).fetchone() is not None

    # ---- TA 主动发来的消息（时机由 web_agent.proactive 决定）----
    def post_pet_message(self, user_id: str, pet_id: str, text: str, *, topic: MessageTopic, composed_by: str, now: datetime, dedupe_key: str) -> bool:
        """user_id='*'：发到家庭频道（全家可见）；否则是发给这位家人的私聊。

        写入前在同一个事务里复核成员关系：内容是几十秒前按当时的权限生成的，这期间家人可能已被移出家庭，这时不发布。
        """
        if user_id == FAMILY:
            return self.post_family_note(pet_id, text, dedupe_key=dedupe_key, now=now, topic=topic, composed_by=composed_by)
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if not self._member_in(conn, user_id, pet_id):
                return False
            cursor = conn.execute(
                "INSERT OR IGNORE INTO web_messages (message_id, user_id, pet_id, sender, source_event_id, text, created_at, available_at, composed_by, topic) "
                "VALUES (?, ?, ?, 'pet', ?, ?, ?, ?, ?, ?)",
                (f"msg-{uuid.uuid4().hex[:12]}", user_id, pet_id, dedupe_key, text, iso(now), iso(now), composed_by, topic.value),
            )
        return cursor.rowcount == 1

    def post_family_note(self, pet_id: str, text: str, *, dedupe_key: str, now: datetime, topic: MessageTopic | None = None,
                         composed_by: str = "template") -> bool:
        """家庭频道里 TA 的一条消息（全家可见，同一件事只写一次）。待领养居民没有家庭，不写。"""
        household_id = self.household_of(pet_id)
        if household_id is None:
            return False
        with self.storage.connect() as conn:
            return conn.execute(
                "INSERT OR IGNORE INTO web_messages (message_id, user_id, pet_id, sender, source_event_id, text, created_at, available_at, composed_by, topic, "
                "channel, household_id) VALUES (?, '*', ?, 'pet', ?, ?, ?, ?, ?, ?, 'family', ?)",
                (f"msg-{uuid.uuid4().hex[:12]}", pet_id, dedupe_key, text, iso(now), iso(now), composed_by, topic.value if topic else None, household_id),
            ).rowcount == 1

    def proactive_state(self, user_id: str, pet_id: str, since: datetime) -> tuple[int, set[str], datetime | None, datetime | None]:
        """(since 之后的主动消息条数, 已用过的去重键, 主人最后一条消息时间, TA 最后一条消息时间)。"""
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT source_event_id FROM web_messages WHERE pet_id = ? AND user_id = ? AND topic IS NOT NULL AND created_at >= ?",
                                (pet_id, user_id, iso(since))).fetchall()
            owner = conn.execute("SELECT MAX(created_at) AS t FROM web_messages WHERE pet_id = ? AND user_id = ? AND sender = 'owner'", (pet_id, user_id)).fetchone()
            pet = conn.execute("SELECT MAX(available_at) AS t FROM web_messages WHERE pet_id = ? AND user_id = ? AND sender = 'pet'", (pet_id, user_id)).fetchone()
        return (len(rows), {r["source_event_id"] for r in rows}, parse_dt(owner["t"]) if owner["t"] else None, parse_dt(pet["t"]) if pet["t"] else None)

    def recent_history(self, user_id: str, pet_id: str, now: datetime) -> list[tuple[str, str]]:
        return self._history(user_id, pet_id, now)

    def post_pet_note(self, user_id: str, pet_id: str, text: str, *, dedupe_key: str, now: datetime) -> bool:
        """TA 对主人某个动作的回应（例如收到出门建议）：不算主动消息，不占每日上限。写入前同样复核成员关系。"""
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if not self._member_in(conn, user_id, pet_id):
                return False
            return conn.execute(
                "INSERT OR IGNORE INTO web_messages (message_id, user_id, pet_id, sender, source_event_id, text, created_at, available_at, composed_by) "
                "VALUES (?, ?, ?, 'pet', ?, ?, ?, ?, 'template')",
                (f"msg-{uuid.uuid4().hex[:12]}", user_id, pet_id, dedupe_key, text, iso(now), iso(now)),
            ).rowcount == 1

    def owner_asked_stay_home(self, user_id: str, pet_id: str, since: datetime) -> bool:
        """最近有没有哪位家人说过“今天别出门”一类的话（只影响 TA 出不出门的倾向，不执行任何操作；不转述原话）。"""
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT text FROM web_messages WHERE pet_id = ? AND sender = 'owner' AND channel = 'private' AND created_at >= ?",
                                (pet_id, iso(since))).fetchall()
        return any(STAY_HOME.search(r["text"]) for r in rows)

    # ---- 世界事件 ----
    def on_world_event(self, event) -> None:  # WorldEventSink
        kind = event.kind
        journey = event.journey
        if kind == "photo_taken" and event.data.get("photo_task_id"):
            self._insert_event(event, f"在{event.visit.place['name']}给你拍了一张照片。", None, photo_status=PhotoStatus.processing.value,
                               photo_task_id=event.data["photo_task_id"])
            return
        if kind == "photo_taken":
            text, photo = f"在{event.visit.place['name']}给你写了一张纸质卡片（没有照片）。", event.data.get("photo_url")
        elif kind == "leg_arrived" and event.data.get("terminal"):
            return
        elif kind == "adventure":
            text, photo = f"【{event.data['title']}】{event.data['story']}", None
            task_id = self.illustration_request(event)
            if task_id:
                self._insert_event(event, text, None, photo_status=PhotoStatus.processing.value, photo_task_id=task_id)
                return
        elif self._daily_text(kind, journey.destination_key) is not None:
            text = self._daily_text(kind, journey.destination_key).format(title=journey.title, pay=event.data.get("pay", 0))
            photo = None
        elif kind in EVENT_TEXT:
            text = EVENT_TEXT[kind].format(title=journey.title, place=event.data.get("place", ""), venue=event.visit.place["name"] if event.visit else "店里")
            photo = None
        else:
            return
        self._insert_event(event, text, photo)

    @staticmethod
    def _daily_text(kind: str, destination_key: str) -> str | None:
        if not (destination_key.startswith("local:") or destination_key.startswith("work:")):
            return None
        family = "work" if destination_key.startswith("work:") else "local"
        return DAILY_TEXT.get((kind, destination_key)) or DAILY_TEXT.get((kind, family))

    def _insert_event(self, event, text: str, photo: str | None, photo_status: str | None = None, photo_task_id: str | None = None) -> None:
        """世界事件来信进家庭频道（全家可见）；待领养居民没有家庭，不写。"""
        journey, now = event.journey, event.occurred_at
        household_id = self.household_of(journey.pet_id)
        if household_id is None:
            return
        # **读当前状态与插消息必须在同一个写事务里**（BEGIN IMMEDIATE）。两种到达顺序都要对：
        #   写锁先给 worker：它的回调命中 0 行（消息还没插），我们随后在同一事务里读到终态，插正确的值；
        #   写锁先给我们：先插"正在画"并提交，worker 的回调随后命中这一行、照常改成 ready/failed。
        # 都不产生额外派发。分成"先读一次、再另开连接插"就还留着那条缝（CR-C12 第一版的问题）。
        with unit_of_work(self.storage) as conn:
            if photo_task_id and photo_status == PhotoStatus.processing.value:
                photo_status, photo = self._photo_at_insert(conn, photo_task_id)
            conn.execute(
                "INSERT OR IGNORE INTO web_messages (message_id, user_id, pet_id, sender, client_message_id, source_event_id, reply_to, text, photo_url, "
                "created_at, available_at, composed_by, photo_status, photo_task_id, channel, household_id) "
                "VALUES (?, '*', ?, 'pet', NULL, ?, NULL, ?, ?, ?, ?, 'event', ?, ?, 'family', ?)",
                (f"msg-{uuid.uuid4().hex[:12]}", journey.pet_id, event.source_event_id, text, photo, iso(now), iso(now), photo_status, photo_task_id, household_id),
            )

    def _photo_at_insert(self, conn, task_id: str) -> tuple[str, str | None]:
        """在**插消息的那个写事务里**读这张图现在的状态：(展示状态, 图地址)。三个消费者共用同一套判断。"""
        from ..web_journey.photo_display import settled_photo

        return settled_photo(conn, task_id, self.illustration_outcome_in) or (PhotoStatus.processing.value, None)

    # ---- 冒险插画（由插画服务回调）----
    def illustration_ready(self, task_id: str, photo_url: str, conn=None) -> None:
        """conn：插画任务的领取围栏事务（结果与任务完成一起提交；领取失效则一起作废）。"""
        execute_in(self.storage, conn, "UPDATE web_messages SET photo_url = ?, photo_status = 'ready' WHERE photo_task_id = ?", (photo_url, task_id))

    def illustration_failed(self, task_id: str, conn=None, outcome: str = "failed") -> None:
        """outcome：`failed`＝确定没画成；`unknown`＝可能已经受理、结果没确认。两者都要如实显示，不能都写成“没画成”。"""
        status = outcome if outcome in UNRESOLVED_PHOTO else PhotoStatus.failed.value
        execute_in(self.storage, conn, "UPDATE web_messages SET photo_status = ? WHERE photo_task_id = ? AND photo_status = 'processing'", (status, task_id))

    def illustration_retrying(self, user_id: str, pet_id: str, message_id: str) -> str | None:
        """只允许重试这位家人看得到的、已经结束又没出图的插画消息（没画成 或 结果不明）；
        返回**重画凭据** `<任务号>#<当时看到的失败尝试次数>`，交给 `illustrations.retry`。

        这里**只做可见性与状态判断，不写展示状态**：状态改回“处理中”由 `illustrations.retry` 在重排的同一个事务里做
        （见 `illustration_retry_started`），免得出现“页面转圈、队列里其实没有任务”。
        这道查询挡的是顺序连点；并发与迟到的重复请求由凭据里的失败版本 ＋ 重排事务里的条件更新挡。
        """
        marks = ",".join("?" for _ in UNRESOLVED_PHOTO)
        with self.storage.connect() as conn:
            row = conn.execute(
                # web_tasks 没有 channel / user_id 两列，所以 VISIBLE 在这个 JOIN 里不会有歧义
                f"SELECT m.photo_task_id, t.attempts FROM web_messages m LEFT JOIN web_tasks t ON t.task_id = m.photo_task_id "
                f"WHERE m.message_id = ? AND m.pet_id = ? AND {VISIBLE} AND m.photo_status IN ({marks})",
                (message_id, pet_id, user_id, *UNRESOLVED_PHOTO)).fetchone()
        return redraw_ticket(row, "photo_task_id")

    def photo_state_for(self, user_id: str, pet_id: str, message_id: str) -> str | None:
        """这位家人看得到的那条消息，附图现在是什么状态；看不到、不存在、或那条消息没有附图时返回 None。

        给路由分辨用：`None` 才是"找不到可重画的插画"（404）；拿到 `processing` / `ready` 说明消息在、只是这一刻不能重画，
        应当回当前状态而不是 404。**可见性条件与 `illustration_retrying` 完全一致，权限不会因为走这条路被绕过。**
        """
        with self.storage.connect() as conn:
            row = conn.execute(f"SELECT photo_status FROM web_messages WHERE message_id = ? AND pet_id = ? AND {VISIBLE} AND photo_task_id IS NOT NULL",
                               (message_id, pet_id, user_id)).fetchone()
        return row["photo_status"] if row is not None else None

    def illustration_retry_started(self, task_id: str, conn=None) -> None:
        """重画真的排上队了（由插画服务在重排事务里回调）：展示状态回到“处理中”，与重排一起提交或一起作废。"""
        marks = ",".join("?" for _ in UNRESOLVED_PHOTO)
        execute_in(self.storage, conn, f"UPDATE web_messages SET photo_status = 'processing' WHERE photo_task_id = ? AND photo_status IN ({marks})",
                   (task_id, *UNRESOLVED_PHOTO))

    # ---- 读取 ----
    def _summary(self, row, now: datetime) -> MessageSummary:
        note = expected = None
        if row["sender"] == "owner":
            with self.storage.connect() as conn:
                reply = conn.execute("SELECT available_at FROM web_messages WHERE reply_to = ?", (row["message_id"],)).fetchone()
                pending = conn.execute("SELECT 1 FROM web_pending_replies WHERE owner_message_id = ? AND (delivered_message_id IS NULL OR delivered_message_id LIKE 'claim-%')",
                                       (row["message_id"],)).fetchone()
            waiting = pending is not None or (reply is not None and parse_dt(reply["available_at"]) > now)
            state = MessageDeliveryState.awaiting_reply if waiting else MessageDeliveryState.delivered
            if waiting:
                note = row["status_note"]
                expected = parse_dt(row["expected_at"]) if row["expected_at"] else None
        else:
            # **消息状态与图片状态分开**（已定口径）：信确实送到了，所以记 delivered；图的情况由 photo_status 如实说。
            # 不能记 failed——那等于告诉主人"什么都没发生"，而那次很可能已经被受理（见 FRONTEND-HANDOFF §H）。
            # MessageDeliveryState 不再扩 unknown；前端一律按 photo_status / image_status 判断。
            state = {"processing": MessageDeliveryState.processing, "failed": MessageDeliveryState.failed,
                     "unknown": MessageDeliveryState.delivered}.get(row["photo_status"] or "", MessageDeliveryState.delivered)
        composed = row["composed_by"] or ("event" if row["source_event_id"] else ("template" if row["sender"] == "pet" else None))
        return MessageSummary(message_id=row["message_id"], client_message_id=row["client_message_id"], sender=MessageSender(row["sender"]),
                              text=row["text"], state=state, created_at=parse_dt(row["created_at"]),
                              photo_url=row["photo_url"] if row["photo_status"] in (None, "ready") else None,
                              composed_by=MessageComposer(composed) if composed else None,
                              photo_status=PhotoStatus(row["photo_status"]) if row["photo_status"] else None,
                              topic=MessageTopic(row["topic"]) if row["topic"] else None, status_note=note, expected_reply_at=expected,
                              channel=MessageChannel(row["channel"] or "private"),
                              # 只下发世界事件来源（<journey>:<事件键>）；其他去重键可能含家人编号，不外露
                              source_event_id=row["source_event_id"] if WORLD_SOURCE.match(row["source_event_id"] or "") else None,
                              reply_to=row["reply_to"])

    def thread(self, user_id: str, pet_id: str, now: datetime | None = None, limit: int = 60) -> MessageThread:
        now = now or utcnow()  # 只读：到点的排队回复由任务进程兑现（读取不再顺手补上）；这里只记已读位置
        with self.storage.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM (SELECT rowid AS seq, * FROM web_messages WHERE pet_id = ? AND {VISIBLE} AND available_at <= ? "
                "ORDER BY available_at DESC, seq DESC LIMIT ?) ORDER BY available_at, seq", (pet_id, user_id, iso(now), limit)).fetchall()
            conn.execute("INSERT INTO web_message_reads (user_id, pet_id, last_read_at) VALUES (?, ?, ?) ON CONFLICT(user_id, pet_id) DO UPDATE SET last_read_at = excluded.last_read_at",
                         (user_id, pet_id, iso(now)))
        return MessageThread(pet_id=pet_id, items=[self._summary(r, now) for r in rows], next_cursor=None, data_origin=DataOrigin.live)

    def unread(self, user_id: str, pet_id: str, now: datetime | None = None) -> int:
        now = now or utcnow()
        with self.storage.connect() as conn:
            last = conn.execute("SELECT last_read_at FROM web_message_reads WHERE user_id = ? AND pet_id = ?", (user_id, pet_id)).fetchone()
            row = conn.execute(f"SELECT COUNT(*) AS n FROM web_messages WHERE pet_id = ? AND {VISIBLE} AND sender = 'pet' AND available_at <= ? AND available_at > ?",
                               (pet_id, user_id, iso(now), last["last_read_at"] if last else "")).fetchone()
        return int(row["n"])
