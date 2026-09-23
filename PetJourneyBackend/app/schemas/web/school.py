"""爪爪驾校（0.3.0）：驾校总览、四科状态与课程。规格见 docs/contracts/DRIVING-SCHOOL-v1.md。

正式成绩只由操作与规则决定：科一、科四由服务端按固定题库批改；科二、科三由服务端按操作记录复算。
每科首次考试＋一次补考；两次不过，从第二次结算起冷却 7×24 小时；已通过的科目永久保留。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from .common import WebModel
from .credentials import CredentialSummary


class SchoolSubject(str, Enum):
    s1 = "s1"
    s2 = "s2"
    s3 = "s3"
    s4 = "s4"


class SchoolStage(str, Enum):
    """none 还没想学 / wish TA 有了愿望 / enrolled 已报名 / license_pending 已通过、驾驶证签发中 / licensed 有驾照。"""

    none = "none"
    wish = "wish"
    enrolled = "enrolled"
    license_pending = "license_pending"
    licensed = "licensed"


class SubjectState(str, Enum):
    """locked 前一科还没通过 / available 可以约考试 / in_exam 有一场未结束的正式考试 / cooldown 两次没过、等待中 / passed 已通过。"""

    locked = "locked"
    available = "available"
    in_exam = "in_exam"
    cooldown = "cooldown"
    passed = "passed"


class SessionMode(str, Enum):
    practice = "practice"
    formal = "formal"


class AttemptKind(str, Enum):
    first = "first"
    retake = "retake"


class SchoolSessionState(str, Enum):
    """preparing 已建立、资源加载中（不计次）/ running 已开始 / settled 已结算 / void 作废（不计次）。"""

    preparing = "preparing"
    running = "running"
    settled = "settled"
    void = "void"


class SessionBrief(WebModel):
    session_id: str
    subject: SchoolSubject
    mode: SessionMode
    item: str | None = None
    attempt_kind: AttemptKind | None = None
    state: SchoolSessionState
    passed: bool | None = None
    score: int | None = None
    created_at: datetime
    settled_at: datetime | None = None


class SubjectStatus(WebModel):
    subject: SchoolSubject
    title: str
    theme: str
    kind: str = Field(description="quiz（科一、科四）/ drive（科二、科三）")
    state: SubjectState
    passed_at: datetime | None = None
    passed_score: int | None = None
    legacy: bool = Field(default=False, description="旧版驾考已通过（此前自动答题的版本），不再需要考试")
    round_no: int = Field(description="第几轮（冷却结束后开始新一轮）")
    attempts_used: int = Field(description="本轮已经用掉的正式考试次数（0—2）")
    attempts_left: int = Field(description="本轮还剩几次正式考试（首次＋补考共 2 次）")
    next_attempt: AttemptKind | None = Field(default=None, description="下一次正式考试是首次还是补考")
    cooldown_until: datetime | None = Field(default=None, description="冷却中时：可以再约考试的时间（服务器时间）")
    unlock_hint: str | None = Field(default=None, description="锁定时的原因，例如“先通过科目一”")
    open_session_id: str | None = Field(default=None, description="这一科未结束的正式考局，回来可以接着考")
    last_result: SessionBrief | None = None
    practice_count: int = 0


class CoachInfo(WebModel):
    name: str
    line: str
    intro: str


class DrivingSchoolStatus(WebModel):
    stage: SchoolStage
    wish_text: str | None = Field(default=None, description="TA 为什么想学开车")
    enrolled_at: datetime | None = None
    coach: CoachInfo
    subjects: list[SubjectStatus]
    open_session: SessionBrief | None = Field(default=None, description="未结束的正式考局（同一时间最多一场）")
    license: CredentialSummary | None = None
    voucher_available: bool = Field(default=False, description="还有一张驾校借车券（第一次自驾免租车费）")
    ceremony_done: bool = Field(default=False, description="领证仪式已经做过")
    temperament: str = Field(description="lively / steady / quiet：挑选 TA 台词的性格（来自 DNA 行为画像）")
    rules_version: str
    server_time: datetime


class LessonStep(WebModel):
    title: str
    body: str


class DeductionRule(WebModel):
    label: str
    points: int


class ItemInfo(WebModel):
    item: str = Field(description="reverse_park / side_park / curve / route；练习另有 reverse_straight / reverse_turn")
    title: str
    time_limit_s: int


class SubjectCurriculum(WebModel):
    subject: SchoolSubject
    title: str
    theme: str
    format: str
    pass_rule: str
    pass_score: int
    duration: str
    kind: str
    lessons: list[LessonStep]
    deductions: list[DeductionRule]
    red_lines: list[str] = Field(description="红线：触发即自动制动、本次不通过（开考前必须展示）")
    items: list[ItemInfo] = Field(default_factory=list, description="正式考试的项目（科二三项、科三一条路线）")
    practice_items: list[ItemInfo] = Field(default_factory=list)


class SchoolCurriculum(WebModel):
    rules_version: str
    coach: CoachInfo
    subjects: list[SubjectCurriculum]
    controls: list[str]
    retake_rule: list[str]
    cooldown_hours: int
    pet_lines: dict[str, dict[str, str]] = Field(description="按性格（lively / steady / quiet）的台词：pass / fail / park / right / license")
    reasons: dict[str, str] = Field(description="判定事件与扣分的说明文字（line → 压线、red_light → 闯了红灯……），前端实时提示与成绩单共用")


__all__ = [
    "SchoolSubject",
    "SchoolStage",
    "SubjectState",
    "SessionMode",
    "AttemptKind",
    "SchoolSessionState",
    "SessionBrief",
    "SubjectStatus",
    "CoachInfo",
    "DrivingSchoolStatus",
    "LessonStep",
    "DeductionRule",
    "ItemInfo",
    "SubjectCurriculum",
    "SchoolCurriculum",
]
