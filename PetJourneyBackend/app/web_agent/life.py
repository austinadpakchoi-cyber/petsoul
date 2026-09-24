"""TA 自己决定今天做什么：在家待着、附近走走、去喝一杯、进城逛逛、打工，或者出远门。主人只给建议。

规则由服务端裁定（用户 2026-09-22 的方向）：
- 只在 TA 所在地的白天考虑出门：从 TA 起床一小时后开始的 9 个小时（按 DNA 作息：早起的早出门，夜猫子晚一点，
  默认 08:30–17:30），并且离入睡至少 3 小时；每半小时最多考虑一次，决定会记下来，不重复掷骰；
- 出门节奏、路线兴趣和工作倾向都看 DNA 行为画像（web_agent.profile）：爱热闹、好奇的常出门、更想去远处，
  恋家、爱睡的少出门、多在附近；喜欢书的更愿意去书店打工，喜欢海的更愿意去渔港……；
- 钱从 TA 的银行卡出：不够时只会散步或去打工；钱少时更愿意去打工；一天最多打一份工；
- 家人的建议（出发站选的地方，或者说“今天别出门”）会被认真考虑：建议的地方更可能去，“别出门”时多半就在家；
  但最后由 TA 自己决定，不会因为一句话就瞬间改行程；家里有几位家人时，每位的建议都算；
- 模型不参与决定（不决定钱和时间），只负责之后用 TA 的口吻说话。
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, time, timedelta
from typing import Callable

from ..schemas.web.pets import PetPresence
from ..storage import JourneyStorage
from ..utils import iso, parse_dt
from ..web_platform.lease import LeaseLost
from ..web_platform.uow import unit_of_work
from .profile import BehaviorProfile, derive_profile, profile_sources

logger = logging.getLogger(__name__)

DECIDE_START, DECIDE_END = time(8, 30), time(17, 30)  # 默认作息（07:30 起、23:30 睡）下的出门时段
SLOT_MINUTES = 30
LONG_TRIPS = {"macau_ferry": 3, "tokyo_flight": 6}  # 出远门后至少隔几天再去


def _roll(*parts: object) -> float:
    return int(hashlib.sha1(":".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:8], 16) / 0x100000000


def behavior_of(persona) -> BehaviorProfile:
    """没有装配统一画像（profile_of）时的后备：直接按扮演人设里的资料推导。"""
    return derive_profile(profile_sources(personality=getattr(persona, "personality", None), dna=getattr(persona, "dna", None),
                                          notes=list(getattr(persona, "notes", []) or [])))


def decide_window(profile: BehaviorProfile | None) -> tuple[time, time]:
    """TA 自己考虑出门的时段（当地时间）：起床一小时后开始，持续 9 小时，并且离入睡至少 3 小时。"""
    if profile is None:
        return DECIDE_START, DECIDE_END
    start = profile.wake.hour * 60 + profile.wake.minute + 60
    sleep = profile.sleep_start.hour * 60 + profile.sleep_start.minute
    if sleep <= start:
        sleep += 24 * 60
    end = min(start + 9 * 60, sleep - 180)
    if end <= start:
        return DECIDE_START, DECIDE_END
    return time((start // 60) % 24, start % 60), time((end // 60) % 24, end % 60)


def temperament_of(profile: BehaviorProfile) -> str:
    if profile.curious or profile.sociability == "social":
        return "adventurous"
    return "homebody" if profile.sociability == "homebody" else "steady"


def temperament(persona) -> str:
    return temperament_of(behavior_of(persona))


def choose(options: list, balance: int, persona_kind: str, *, suggested: set[str], worked_today: bool, long_trip_ok: set[str], roll: float,
           interest: dict[str, float] | None = None, job_affinity: dict[str, float] | None = None) -> str | None:
    """在可去的地方里按权重挑一个。options：出发站的 DestinationOption 列表。"""
    weights: dict[str, float] = {}
    for option in options:
        key, fee = option.destination_key, option.fee
        if balance < fee or not getattr(option, "available", True):
            continue  # 钱不够，或者现实资料拿不到（地图不可用、船期待复核）
        if key == "local:stroll":
            weight = 3.0
        elif key.startswith("work:"):
            if worked_today:
                continue
            weight = 4.0 if balance < 40 else 0.4
        elif balance < 8:
            continue  # 钱很少：只散步或打工
        elif key == "local:cafe" or key == "harbour_cafe":
            weight = 2.0
        elif key == "local:city_trip":
            weight = 1.0 if balance >= fee + 10 else 0.0
        elif key in LONG_TRIPS:
            if key not in long_trip_ok or persona_kind == "homebody":
                continue
            weight = 1.2 if persona_kind == "adventurous" else 0.4
        else:
            weight = 0.5
        # DNA：喜欢的地方和活计更可能被选中（倍数），主人的建议被认真考虑
        weight *= (interest or {}).get("long" if key in LONG_TRIPS else key, 1.0)
        if key.startswith("work:"):
            weight *= (job_affinity or {}).get(key.split(":", 1)[1], 1.0)
        if key in suggested:
            weight *= 6
        if weight > 0:
            weights[key] = weight
    if not weights:
        return None
    work = [k for k in weights if k.startswith("work:")]
    for k in work:  # 几份活合起来只算一个“去打工”的选择
        weights[k] /= len(work)
    total = sum(weights.values())
    cursor = roll * total
    for key, weight in sorted(weights.items()):
        cursor -= weight
        if cursor < 0:
            return key
    return sorted(weights)[-1]


SUGGESTION_WINDOW = timedelta(hours=24)  # 建议还在考虑中的时长（与 suggestions/suggesters 的查询口径一致）


def settle_suggestions(storage, pet_id: str, chosen_key: str | None, now: datetime) -> None:
    """TA 出门之后，家人那些建议怎么记（验收 CR-C4）。

    - 选中的那条：accepted（TA 听了你的）；
    - 其余还在考虑中的：**留在 pending**，只记一次 considered_at——这次没选它，不等于不去了，24 小时窗口内还算数；
    - 窗口过了的：由世界线的 `expire_suggestions` 统一置成 passed，不会一直挂着"还在考虑中"。
    """
    with unit_of_work(storage) as conn:
        if chosen_key:
            conn.execute("UPDATE web_owner_suggestions SET status = 'accepted', decided_at = ? WHERE pet_id = ? AND status = 'pending' "
                         "AND destination_key = ?", (iso(now), pet_id, chosen_key))
        conn.execute("UPDATE web_owner_suggestions SET considered_at = ? WHERE pet_id = ? AND status = 'pending' AND created_at >= ?",
                     (iso(now), pet_id, iso(now - SUGGESTION_WINDOW)))


def expire_suggestions(storage, now: datetime) -> int:
    """考虑窗口过了还没被采纳的建议：置成 passed（TA 这回去了别处 / 没赶上）。返回条数。"""
    with unit_of_work(storage) as conn:
        return conn.execute("UPDATE web_owner_suggestions SET status = 'passed', decided_at = ? WHERE status = 'pending' AND created_at < ?",
                            (iso(now), iso(now - SUGGESTION_WINDOW))).rowcount


class LifeEngine:
    def __init__(self, storage: JourneyStorage, journeys, economy, moments, *, persona_of: Callable, home_of: Callable[[str], object | None],
                 activated_pets: Callable[[], list[tuple[str, str]]], owner_said_stay_home: Callable[[str, str, datetime], bool] = lambda u, p, now: False) -> None:
        self.storage = storage
        self.journeys = journeys
        self.economy = economy
        self.moments = moments
        self.persona_of = persona_of
        self.home_of = home_of
        self.activated_pets = activated_pets
        self.owner_said_stay_home = owner_said_stay_home
        # 出门之后：(记账的家人, pet_id, 去哪, 提过这个建议的家人们, 时间)
        self.on_departed: Callable[[str, str, str, list[str], datetime], None] = lambda user_id, pet_id, key, suggested_by, now: None
        # 统一的 DNA 行为画像（装配时注入，与作息、主动消息、DNA 页面展示同一份）
        self.profile_of: Callable[[str], BehaviorProfile] | None = None
        # 两条线共用的“刚刚做过生活决定”判断与记录（装配时接到每宠运行记录）。
        # 世界线的规则生活与认知线的模型生活都会替同一只宠物安排出门；没有这一对钩子，
        # 同一个时段里两条线会各决定一次——模型刚说“今天在家”，规则生活转头就把 TA 送出门。
        self.recently_decided: Callable[[str, datetime], bool] = lambda pet_id, now: False
        # 这只宠物此刻有没有一份**就绪的**旅行计划（装配时接 `wish_wiring.bind_ready_plan`）。
        # **不接就是"没有"**——那时规则生活照原样掷骰选目的地，一行行为都不变。
        self.ready_plan_of: Callable[[str], object | None] = lambda pet_id: None
        # 运营把这只宠物暂停了吗（`web_entity_runtime.maintenance`）。装配时接到**心跳读的同一份运行记录**，
        # 不在这里自己开连接读 SQL——三处各读一份就会变成三份可能漂移的实现。
        # 没接时恒为 False，行为与接线前完全一致。
        self.paused: Callable[[str], bool] = lambda pet_id: False
        self.record_decision: Callable[[str, datetime, str], None] = lambda pet_id, now, by: None

    def run(self, now: datetime) -> int:
        gone = 0
        for user_id, pet_id in self.activated_pets():
            try:
                if self.consider(user_id, pet_id, now):
                    gone += 1
            except LeaseLost:  # 租约被接手：世界已归新任期推进，本轮剩下的宠物不再处理
                raise
            except Exception:  # noqa: BLE001 - 单只宠物出错不影响其他宠物
                logger.exception("life engine failed pet=%s", pet_id)
        return gone

    # ---- 记录 ----
    def _decided(self, pet_id: str, slot_key: str) -> bool:
        with self.storage.connect() as conn:
            return conn.execute("SELECT 1 FROM web_pet_decisions WHERE pet_id = ? AND slot_key = ?", (pet_id, slot_key)).fetchone() is not None

    def _record(self, pet_id: str, slot_key: str, decision: str, now: datetime) -> bool:
        with unit_of_work(self.storage) as conn:
            return conn.execute("INSERT OR IGNORE INTO web_pet_decisions (pet_id, slot_key, decision, created_at) VALUES (?, ?, ?, ?)",
                                (pet_id, slot_key, decision, iso(now))).rowcount == 1

    def _wish_pick(self, pet_id: str, options: list, balance: int, long_ok: set[str]):
        """就绪心愿指向的那个目的地——**而且此刻真的去得了**；否则返回 None，照常掷骰选。

        「有一份就绪计划」和「现在能去那儿」是两件事：
        - 目的地**不在出发选项里**（比如计划指向一个引擎还没接的地方）→ 不强推。
          方案 §8 明写"未接入的目的地最多保存为心愿"，所以这不是缺陷，是那条规则生效的样子；
        - 钱不够、选项不可用、长途冷却没过 → 同样不强推。
          **这三条与 `choose` 用的是同一组判据**，不能因为"有计划"就绕过去。
        """
        picked = self.ready_plan_of(pet_id)
        if picked is None:
            return None
        option = next((o for o in options if o.destination_key == picked.destination_key), None)
        if option is None or not getattr(option, "available", True) or balance < option.fee:
            return None
        if picked.destination_key in LONG_TRIPS and picked.destination_key not in long_ok:
            return None
        return picked

    def _history(self, pet_id: str, since: datetime) -> list[tuple[str, datetime]]:
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT destination_key, departed_at FROM web_journeys WHERE pet_id = ? AND departed_at >= ? ORDER BY departed_at",
                                (pet_id, iso(since))).fetchall()
        return [(r["destination_key"], parse_dt(r["departed_at"])) for r in rows]

    # ---- 主人的建议 ----
    def suggest(self, user_id: str, pet_id: str, home_id: str, destination_key: str, now: datetime) -> dict | None:
        """记下主人的建议（同时只保留一条在考虑中的）；不在可去列表里的返回 None。"""
        option = next((o for o in self.journeys.destinations(user_id, pet_id, home_id) if o.destination_key == destination_key), None)
        if option is None:
            return None
        suggestion_id = f"sg-{uuid.uuid4().hex[:12]}"
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE web_owner_suggestions SET status = 'replaced', decided_at = ? WHERE user_id = ? AND pet_id = ? AND status = 'pending'",
                         (iso(now), user_id, pet_id))
            conn.execute("INSERT INTO web_owner_suggestions (suggestion_id, user_id, pet_id, destination_key, title, status, created_at) VALUES (?, ?, ?, ?, ?, 'pending', ?)",
                         (suggestion_id, user_id, pet_id, destination_key, option.title, iso(now)))
        return {"suggestion_id": suggestion_id, "destination_key": destination_key, "title": option.title, "status": "pending", "created_at": now,
                "decided_at": None, "affordable": option.affordable}

    def recent_suggestions(self, user_id: str, pet_id: str, limit: int = 10) -> list[dict]:
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT * FROM web_owner_suggestions WHERE user_id = ? AND pet_id = ? ORDER BY created_at DESC LIMIT ?",
                                (user_id, pet_id, limit)).fetchall()
        return [{"suggestion_id": r["suggestion_id"], "destination_key": r["destination_key"], "title": r["title"], "status": r["status"],
                 "created_at": parse_dt(r["created_at"]), "decided_at": parse_dt(r["decided_at"]) if r["decided_at"] else None,
                 "considered_at": parse_dt(r["considered_at"]) if r["considered_at"] else None} for r in rows]

    def suggestions(self, user_id: str, pet_id: str, now: datetime) -> set[str]:
        """24 小时内还在考虑中的建议（全家每位家人的都算）。"""
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT destination_key FROM web_owner_suggestions WHERE pet_id = ? AND status = 'pending' AND created_at >= ?",
                                (pet_id, iso(now - timedelta(hours=24)))).fetchall()
        return {r["destination_key"] for r in rows}

    def suggesters(self, pet_id: str, destination_key: str, now: datetime) -> list[str]:
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT DISTINCT user_id FROM web_owner_suggestions WHERE pet_id = ? AND destination_key = ? AND status = 'pending' "
                                "AND created_at >= ? ORDER BY user_id", (pet_id, destination_key, iso(now - timedelta(hours=24)))).fetchall()
        return [r["user_id"] for r in rows]

    # ---- 决定 ----
    def consider(self, user_id: str, pet_id: str, now: datetime) -> str | None:
        if self.paused(pet_id):
            # 运营暂停了这只宠物：**规则生活也不能替 TA 做决定**。
            # 放在最前面是有意的——再往下就会占掉这个时段的决定名额（`_record`），
            # 那会让恢复之后的这半小时白白不出门。在途旅程不受影响，按设计照常走完。
            return None
        moment = self.moments.build(pet_id, now)
        if moment.presence is not PetPresence.at_home or moment.asleep:
            return None
        local = moment.local_time
        start, end_at = decide_window(self.profile_of(pet_id) if self.profile_of else None)
        if not (start <= local.time() < end_at):
            return None
        slot = (local.hour * 60 + local.minute) // SLOT_MINUTES
        slot_key = f"{local.date().isoformat()}:{slot}"
        if self._decided(pet_id, slot_key):
            return None
        if self.journeys.repo.active_for_pet(pet_id) is not None:
            return None  # 已经定好行程（例如在等开船时间出门）：一个时刻只有一个安排
        if self.recently_decided(pet_id, now):
            return None  # 刚刚已经决定过（可能是模型决定的）：这个时段不再替 TA 决定第二次
        persona = self.persona_of(user_id, pet_id)
        home = self.home_of(pet_id)
        if persona is None or home is None:
            return None
        profile = self.profile_of(pet_id) if self.profile_of else behavior_of(persona)
        kind = temperament_of(profile)
        day_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        today = self._history(pet_id, day_start.astimezone(now.tzinfo))
        if len(today) >= profile.outings_per_day:
            self._record(pet_id, slot_key, "rest:enough_today", now)
            return None
        end = datetime.combine(local.date(), end_at, tzinfo=local.tzinfo)
        remaining = max(1, int((end - local).total_seconds() // (SLOT_MINUTES * 60)))
        chance = min(0.9, (profile.outings_per_day - len(today)) / remaining * 1.5)
        if self.owner_said_stay_home(user_id, pet_id, now):
            chance *= 0.15  # 主人说今天别出门：多半就在家
        if _roll(pet_id, slot_key, "go") >= chance:
            self._record(pet_id, slot_key, "rest", now)
            return None
        recent = self._history(pet_id, now - timedelta(days=max(LONG_TRIPS.values())))
        long_ok = {key for key, days in LONG_TRIPS.items() if not any(k in LONG_TRIPS and d >= now - timedelta(days=days) for k, d in recent)}
        suggested = self.suggestions(user_id, pet_id, now)
        options = self.journeys.destinations(user_id, pet_id, home.home_id)
        balance = self.economy.wallet(pet_id).balance
        key = choose(options, balance, kind, suggested=suggested, worked_today=any(k.startswith("work:") for k, _ in today),
                     long_trip_ok=long_ok, roll=_roll(pet_id, slot_key, "where"), interest=profile.route_interest, job_affinity=profile.job_affinity)
        # **名额在出发之前就记掉，出发被拒也不退——这是有意的，不是漏了回滚。**
        # 被拒的原因（主人说了别出门、钱不够、已经在外面）在**同一个时段内**都不会自己变好，
        # 反复再试只是空转。下一个时段照常重新决定。
        #
        # 这条记录**不参与任何冷却**：`_history`（:190）读的是 `web_journeys`——真实走过的行程，
        # 所以长途冷却（:274）、今天出门几次与打没打过工（:262）都只认真的出过门。
        # `web_pet_decisions` 在本文件里只被 :183 读一次，只回答「这个时段决定过了吗」。
        # 写在这里是因为**这一点会被反复重新发现**：看到「没走成却留下一条 go:<key>」，
        # 很容易顺手推出「它会把长途算成刚去过」——**那是错的**（我自己就这么推过一次，C 核出来）。
        # 攒够了、资料也齐了的那份计划：这一轮**优先去那儿**。TA 自己惦记了很久的地方，
        # 不该再跟随机权重抢。「出不出门」那一掷仍在上面，这里只换「去哪儿」。
        picked = self._wish_pick(pet_id, options, balance, long_ok)
        if picked is not None:
            key = picked.destination_key
        if key is None or not self._record(pet_id, slot_key, f"go:{key}", now):
            return None
        by = self.suggesters(pet_id, key, now) if key in suggested else []
        try:
            # honor_commitments=True：规则生活也是 TA 自己决定出门（合同 15 节：自主出发认闸，主人点击不认）。
            # 注意这**不是重复**上面那条 `owner_said_stay_home`——那一条只把出门概率乘 0.15（"多半就在家"），
            # 仍有约一成会出门；这道闸是硬的。**软偏好管的是 TA 想不想去，硬闸管的是允不允许。**
            self.journeys.depart(user_id, pet_id, home.home_id, key, now,
                                 # 按计划出发时**编号与版本一起给**（`PlanChoice` 让漏传写不出来）。
                                 # 这两个值来自事务外那一次读，**只够用来选**；能不能用由 depart 在写事务里重核。
                                 plan=picked.choice if picked is not None else None,
                                 honor_commitments=True)
        except LeaseLost:  # 出发事务已整体回滚；这不是“TA 决定不出门”，不能记成结果
            raise
        except Exception as exc:  # noqa: BLE001 - 钱不够/已经在外面等：这次就在家
            logger.info("pet %s decided %s but could not depart: %s", pet_id, key, exc)
            return None
        settle_suggestions(self.storage, pet_id, key, now)
        self.record_decision(pet_id, now, "rule")  # 记下这一轮是规则决定的：心跳据此退避，不会紧接着再让模型想一次
        self.on_departed(user_id, pet_id, key, by, now)
        return key
