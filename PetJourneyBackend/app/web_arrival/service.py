"""到站自拍（用户 2026-09-24：「每一个用户注册完成之后都会收到宠物在聊天框和明信片给他发的一个到站的自拍图」）。

注册那一刻还没有宠物，所以「注册完成」落在 **TA 第一次住进家**（入住＝到站）。这时 TA 给家里发两样东西，**用同一张自拍**：

  · 家庭频道里一条消息「我到站啦」，带自拍（先显示冲洗中，画好自动换上）；
  · 收藏里一张「到站明信片」：TA 写的话、地点（**家的真实片区**，不编驿站和门牌）、同一张自拍。

图只画一次：一个生图任务，画好之后消息和明信片按任务号一起回填（现有的插画回调，三处同一个口径）。

怎么走：入住接口只 `register`（快、幂等、每只宠物一行）；认知线的后台轮次 `run` 再写话、排自拍、发消息和明信片——
写话可能要调模型，不能拖慢入住。**排自拍、插明信片、插消息、标记已发在同一个写事务里**，要么全有要么全无；
模型写话在事务之外先做（慢调用不占写锁），出错就用模板。

不做的事：
  · 生图不可用（没配供应商）时不排任务，只寄一张手写明信片，**消息文字也不提自拍**——不说没发生的事；
  · 额度、每宠上限、幂等、「结果未确认不自动重画」全部沿用插画服务，这里不另开付费通道；
  · 功能上线前已入住的宠物不补发；同一只宠物只发一次；多宠家庭每只各一次。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Callable

from ..utils import iso, utcnow
from ..web_platform.uow import unit_of_work

logger = logging.getLogger(__name__)

RETRY_SECONDS = (30, 120, 600, 1800)
MAX_ATTEMPTS = 5


def source_key(pet_id: str) -> str:
    """消息、明信片、自拍任务共用的自然键：同一只宠物永远只有这一份。"""
    return f"arrival:{pet_id}"


def postcard_title(place) -> str:
    return f"来自{place.area_label}的到站明信片"


def template_note(place) -> str:
    """明信片上 TA 写的话（没有模型或不许用模型时）。只写真实的片区。"""
    return f"我到站啦！这里是{place.city}·{place.area_label}，以后我就住在这儿了。给家里寄一张到站明信片，这是我在新家写下的第一句话～"


def chat_text(place, with_selfie: bool) -> str:
    """家庭频道那条消息。**有自拍任务才提自拍**；没有时只说寄了明信片。"""
    if with_selfie:
        return f"我到站啦！这是我在{place.area_label}拍的第一张自拍～到站明信片也寄出了，在收藏里能看到。"
    return f"我到站啦！这里是{place.city}·{place.area_label}。给家里寄了一张到站明信片，在收藏里能看到。"


# 片区的画面特征。**提示词里只放画面、不放地名**（P 2026-09-24，真图上吃过亏）：地名和名字写进提示词，
# 街边招牌最容易被画出那几个字；片区名交给界面排版（明信片的 place / city 字段）。没登记的片区用环境类型（海边／城市……）。
AREA_LOOKS = {
    "hk_central": "高楼林立、街道干净的城市街区", "hk_saikung": "有小码头和渔船的海湾边",
    # 其余 25 个片区由 P 补齐（2026-09-24）：只写看得见的样子，不写地名、数字，也避开店、招牌这类会招来伪文字的词；
    # P 对照 60 个专名自查 0 命中。是常识性外观，没有核验来源，也都**未经出图验证**。这些片区眼下还没开放（家分不到那里）。
    "xm_huandao": "有长长木栈道和椰子树的海边", "qd_badaguan": "红瓦老房子和林荫道挨着的海边",
    "sy_haitang": "白沙滩、椰林和清澈海水的热带海边", "dl_xinghai": "宽阔海滨广场和长长海堤的海边",
    "hulunbuir": "一望无际、缓缓起伏的绿色草原", "xilinhot": "天空辽阔、零星散落着白色毡房的草原",
    "ruoergai": "有弯弯曲曲的小河和湿地的高原草原", "dunhuang": "金色沙丘连绵起伏的沙漠边",
    "zhongwei": "沙丘紧挨着河流和绿洲的沙漠边", "xishuangbanna": "高大热带树木和竹楼掩映的雨林边",
    "shennongjia": "山高林密、雾气缭绕的原始森林", "changbaishan": "白桦和松树高高林立的林边",
    "hz_xihu": "垂柳成排、有石桥和亭子的湖边", "dali_erhai": "湖水湛蓝、远处是连绵青山的高原湖边",
    "sz_jinjihu": "湖面开阔、对岸有现代高楼的湖边", "huangshan": "奇松怪石、云雾缭绕的山脚下",
    "yangshuo": "尖尖的山峰和清澈小河环绕的山间", "moganshan": "竹林茂密、老石头房子藏在山坡上的山里",
    "sh_xuhui": "梧桐树荫下、老洋房连成一片的街区", "cd_yulin": "树荫下低矮老楼挨在一起的街巷",
    "gz_dongshan": "红砖小洋楼和绿树掩映的老街区", "bj_hutong": "灰砖墙和四合院门楼连成一片的胡同",
    "wuyuan": "白墙黑瓦的村落和层层梯田的田野边", "anji": "漫山竹林和小溪环绕的村子",
    "wuzhen": "小河穿过、白墙黑瓦民居临水而建的水乡",
}


def selfie_setting(place) -> str:
    return AREA_LOOKS.get(place.area_key, place.habitat_label)


def selfie_scene(place) -> str:
    """交给写实自拍模板的整句画面（模板的回落路径只读 scene，见 A 的 `build_selfie_prompt`）。
    不写"星球""车站"：生图会照字面画成科幻星球或火车站。"""
    # 不写「站在街边」：8 类住处里只有城市配得上，沙漠、草原会被硬画出一条街（P 2026-09-24）。构图交给模板那句「镜头离它很近……」
    return f"在{selfie_setting(place)}的新家附近，开心地拍下搬来后的第一张自拍"


class ArrivalService:
    def __init__(self, storage) -> None:
        self.storage = storage
        # 以下由组合根注入；默认值都是"少做"而不是"多造"：
        # 这只宠物的家在哪（HomePlace：area_label / city）；没有家返回 None → 不发
        self.place_of: Callable[[str], object | None] = lambda pet_id: None
        # 明信片上 TA 写的话（模型）；返回 None 就用模板。只在事务之外调用
        self.note_writer: Callable[[str, object], str | None] = lambda pet_id, place: None
        # 在调用方的写事务里排一张写实自拍（插画服务的 request_photo_in）；生图不可用时返回 None
        self.selfie_request_in: Callable[..., str | None] = lambda conn, user_id, pet_id, key, **kwargs: None
        # 在调用方的写事务里寄明信片、写 TA 的消息（收藏的 postcard_in、通讯器的 pet_note_in：给 user_id 写私聊，不给写家庭频道）
        self.postcard_in: Callable[..., bool] | None = None
        self.pet_note_in: Callable[..., bool] | None = None

    # ---- 入住时登记 ----
    def register(self, pet_id: str, household_id: str, user_id: str, now: datetime | None = None) -> bool:
        """TA 第一次住进这个家：登记一行等后台发。重复调用不重复登记（入住接口本身也幂等）。"""
        now = now or utcnow()
        # 只对「这只已经登记过」不报错。不用 INSERT OR IGNORE：它连 NOT NULL / CHECK 违例一起吞（A 2026-09-24 实测），
        # 一次写坏的登记会无声消失，到站自拍就永远不发，而且没有任何地方报错。
        with self.storage.connect() as conn:
            return conn.execute(
                "INSERT INTO web_pet_arrivals (pet_id, household_id, user_id, registered_at, next_attempt_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(pet_id) DO NOTHING",
                (pet_id, household_id, user_id, iso(now), iso(now)),
            ).rowcount == 1

    def state_of(self, pet_id: str) -> dict | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM web_pet_arrivals WHERE pet_id = ?", (pet_id,)).fetchone()
        return dict(row) if row is not None else None

    # ---- 后台轮次（认知线）----
    def run(self, now: datetime | None = None, limit: int = 10) -> int:
        """发出到点的到站欢迎；返回这一轮真正发出的只数。一只出错不挡别的，按退避重试，用尽次数就放弃并留下原因。"""
        now = now or utcnow()
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT * FROM web_pet_arrivals WHERE state = 'pending' AND next_attempt_at <= ? ORDER BY registered_at, pet_id LIMIT ?",
                                (iso(now), limit)).fetchall()
        sent = 0
        for row in rows:
            try:
                sent += 1 if self._deliver(dict(row), now) == "delivered" else 0
            except Exception as exc:  # noqa: BLE001 - 一只出错不挡别的；事务已整体回滚，什么都没写出去
                logger.warning("arrival welcome failed pet=%s: %s", row["pet_id"], exc)
                self._failed(row["pet_id"], f"{type(exc).__name__}: {exc}"[:200], now)
        return sent

    def _deliver(self, row: dict, now: datetime) -> str:
        pet_id = row["pet_id"]
        place = self.place_of(pet_id)
        if place is None:
            return self._finish(pet_id, "skipped", last_error="no_home")
        try:
            note, composed_by = self.note_writer(pet_id, place), "model"
        except Exception:  # noqa: BLE001 - 模型不可用时用模板
            note = None
        if not note:
            note, composed_by = template_note(place), "template"
        key = source_key(pet_id)
        with unit_of_work(self.storage) as conn:
            current = conn.execute("SELECT state FROM web_pet_arrivals WHERE pet_id = ?", (pet_id,)).fetchone()
            if current is None or current["state"] != "pending":
                return "already"  # 另一个轮次已经发过（或已放弃）
            household = conn.execute("SELECT household_id FROM web_household_pets WHERE pet_id = ?", (pet_id,)).fetchone()
            if household is None or household["household_id"] != row["household_id"]:
                # 登记之后、发出之前 TA 已不在这个家：不往原来的家发，也不替新家补发
                conn.execute("UPDATE web_pet_arrivals SET state = 'skipped', last_error = 'left_household', attempts = attempts + 1 WHERE pet_id = ?", (pet_id,))
                return "skipped"
            # 画面整句放进 scene；place / city 留空（A 2026-09-24：回落模板只读 scene，place/city 另有导演与界面读真名——
            # 到站这条路两者都用不到，留空最稳：现行模板遇空不写，改成只读 scene 之后结果也一样）
            task_id = self.selfie_request_in(conn, row["user_id"], pet_id, key, place="", city="", scene=selfie_scene(place))
            self.postcard_in(conn, user_id=row["user_id"], pet_id=pet_id, source_event_id=key, title=postcard_title(place), note=note,
                             place=place.area_label, city=place.city, task_id=task_id, now=now)
            # 聊天框＝「我和 TA」私聊：前端通讯器默认打开的就是它（家庭频道在另一个分区，默认看不到）。
            # 写给接 TA 入住的那位家人；那位已不是有效成员时（pet_note_in 返回 False）退回家庭频道，家里仍然收得到。
            # 重复写入同样返回 False，这时退回那一次也撞同一个去重键，不会多出一条。
            message = dict(pet_id=pet_id, household_id=row["household_id"], text=chat_text(place, task_id is not None),
                           dedupe_key=key, now=now, photo_task_id=task_id)
            if not self.pet_note_in(conn, user_id=row["user_id"], **message):
                self.pet_note_in(conn, **message)
            conn.execute("UPDATE web_pet_arrivals SET state = 'delivered', delivered_at = ?, photo_task_id = ?, note_composed_by = ?, "
                         "attempts = attempts + 1, last_error = NULL WHERE pet_id = ?", (iso(now), task_id, composed_by, pet_id))
        return "delivered"

    def _finish(self, pet_id: str, state: str, *, last_error: str | None = None) -> str:
        with self.storage.connect() as conn:
            conn.execute("UPDATE web_pet_arrivals SET state = ?, last_error = ?, attempts = attempts + 1 WHERE pet_id = ? AND state = 'pending'",
                         (state, last_error, pet_id))
        return state

    def _failed(self, pet_id: str, error: str, now: datetime) -> None:
        """记一次失败：**在写事务里读当前次数再加一**。原先用批量读取那一刻的旧值按绝对值写回，
        两路同时失败会算出同一个新值、互相覆盖，次数少算、放弃被推迟（Q 2026-09-24 读代码发现）。"""
        with unit_of_work(self.storage) as conn:
            row = conn.execute("SELECT attempts FROM web_pet_arrivals WHERE pet_id = ? AND state = 'pending'", (pet_id,)).fetchone()
            if row is None:
                return  # 已经发出、跳过或放弃了：没有可记的
            attempts = int(row["attempts"]) + 1
            state = "abandoned" if attempts >= MAX_ATTEMPTS else "pending"
            delay = RETRY_SECONDS[min(attempts - 1, len(RETRY_SECONDS) - 1)]
            conn.execute("UPDATE web_pet_arrivals SET state = ?, attempts = ?, next_attempt_at = ?, last_error = ? WHERE pet_id = ?",
                         (state, attempts, iso(now + timedelta(seconds=delay)), error, pet_id))
