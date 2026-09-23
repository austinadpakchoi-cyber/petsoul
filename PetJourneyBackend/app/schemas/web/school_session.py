"""爪爪驾校考局（0.3.0）：练习与正式考局、科一科四的作答、科二科三的操作记录与服务端复算、结果与领证仪式。

- 正式考局建立后是 preparing（不计次）；资源加载完成、点“开始考试”（begin）后才计次。
- 科二、科三：前端每秒上传一段操作 `{item_index, from_tick, upto_tick, events}`，服务端按确定性模拟复算（事件格式见 DRIVING-SCHOOL-v1 §4.4）；
  只接受从已提交位置连续往后的片段，完全相同的重发原样返回（天然幂等）。
- 科一、科四：逐题保存作答；练习模式立即讲解，正式模式交卷前不给任何提示。
- 结算只做一次；客户端上报的分数一律无效。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from .common import WebModel
from .credentials import CredentialSummary
from .school import AttemptKind, SchoolSubject, SessionMode, SchoolSessionState
from .social import CollectionItem


class QuizKind(str, Enum):
    choice = "choice"
    match = "match"
    order = "order"


class QuizOption(WebModel):
    option_id: str
    label: str


class QuizTarget(WebModel):
    target_id: str
    label: str


class QuizQuestionView(WebModel):
    """题目（不含答案）。match：把 options 放到 targets 上；order：把 options 排成正确顺序。"""

    question_id: str
    kind: QuizKind
    scene: str = Field(description="场景插画的键（前端按键绘制）")
    topic_title: str
    prompt: str
    options: list[QuizOption]
    targets: list[QuizTarget] = Field(default_factory=list)
    group: str | None = Field(default=None, description="科四：同一段情境的两个判断共用一个 group")
    group_title: str | None = None
    story: list[str] = Field(default_factory=list)


class QuizAnswer(WebModel):
    choice: str | None = None
    order: list[str] | None = None
    matches: dict[str, str] | None = Field(default=None, description="{target_id: option_id}")


class QuizFeedback(WebModel):
    question_id: str
    correct: bool
    correct_answer: QuizAnswer
    explanation: str
    pet_line: str


class QuizProgress(WebModel):
    questions: list[QuizQuestionView]
    answers: dict[str, QuizAnswer] = Field(default_factory=dict, description="已保存的作答（续考时恢复）")
    feedback: dict[str, QuizFeedback] = Field(default_factory=dict, description="练习模式的即时讲解；正式模式交卷前为空")


class InputEvent(WebModel):
    t: int = Field(ge=0, description="tick（每秒 30 个），每一项从 0 开始")
    c: str = Field(pattern=r"^[stbgkcv]$", description="s 转向目标 / t 油门 / b 刹车 / g 换挡 / k 转向灯 / c 出发前检查 / v 视频邀请")
    v: int = Field(ge=-12, le=12)


class SimEvent(WebModel):
    t: int
    k: str = Field(description="line / cone / out_of_bounds / timeout / done / precheck_skipped / start_no_signal / stop_rolled / crosswalk / red_light / "
                               "turn_no_signal / speeding / invite_shown / invite_opened")
    ref: str | None = None
    p: int = Field(description="扣分")
    f: int = Field(description="1＝红线或失败，本项立即结束")


class DriveItemProgress(WebModel):
    item: str
    title: str
    course: dict[str, Any] = Field(description="场地配置：车身、正切表、速度、线、锥桶、目标区、时限、路线检查点与装饰（渲染用）")
    status: str = Field(description="pending / running / done / failed")
    committed_tick: int
    events: list[InputEvent] = Field(default_factory=list, description="服务端已接受的操作（续考时本地重放恢复状态）")
    sim_events: list[SimEvent] = Field(default_factory=list, description="服务端复算出的判定事件")
    snapshot: dict[str, Any] | None = Field(default=None, description="服务端复算到 committed_tick 时的模拟快照（用于对齐）")


class DriveProgress(WebModel):
    items: list[DriveItemProgress]
    current_item: int


class Deduction(WebModel):
    kind: str
    label: str
    points: int
    item: str | None = None
    t: int | None = None
    ref: str | None = None
    question_id: str | None = None


class QuestionReview(WebModel):
    question_id: str
    prompt: str
    correct: bool
    your_answer: QuizAnswer | None = None
    correct_answer: QuizAnswer
    explanation: str


class ItemResult(WebModel):
    item: str
    title: str
    status: str
    deducted: int
    ticks: int


class NextStep(WebModel):
    kind: str = Field(description="passed / licensed / retake / cooldown / practice")
    message: str
    attempts_left: int | None = None
    cooldown_until: datetime | None = None


class SessionResult(WebModel):
    passed: bool
    score: int
    max_score: int
    pass_score: int
    deductions: list[Deduction] = Field(default_factory=list)
    fatal: Deduction | None = Field(default=None, description="红线或失败原因（科二科三），例如超时、闯红灯、主动放弃")
    review: list[QuestionReview] = Field(default_factory=list, description="科一科四：结算后才给出正确答案与讲解")
    items: list[ItemResult] = Field(default_factory=list)
    pet_says: str
    next: NextStep | None = None


class SchoolSession(WebModel):
    session_id: str
    subject: SchoolSubject
    title: str
    mode: SessionMode
    item: str | None = None
    attempt_kind: AttemptKind | None = None
    round_no: int | None = None
    state: SchoolSessionState
    pass_score: int
    created_at: datetime
    begun_at: datetime | None = None
    paused_at: datetime | None = None
    settled_at: datetime | None = None
    void_reason: str | None = None
    quiz: QuizProgress | None = None
    drive: DriveProgress | None = None
    result: SessionResult | None = None


class SessionCreateRequest(WebModel):
    subject: SchoolSubject
    mode: SessionMode
    item: str | None = Field(default=None, max_length=32, description="练习单项（科二：reverse_straight / reverse_turn / reverse_park / side_park / curve）；不填为整科")


class AnswerRequest(WebModel):
    question_id: str = Field(max_length=64)
    answer: QuizAnswer


class AnswerResult(WebModel):
    question_id: str
    saved: bool
    answered: int
    total: int
    feedback: QuizFeedback | None = Field(default=None, description="只在练习模式返回")


class InputChunk(WebModel):
    item_index: int = Field(ge=0)
    from_tick: int = Field(ge=0)
    upto_tick: int = Field(ge=0)
    events: list[InputEvent] = Field(default_factory=list, max_length=2000)


class InputResult(WebModel):
    session_id: str
    session_state: SchoolSessionState
    item_index: int
    current_item: int
    item_status: str
    committed_tick: int
    new_events: list[SimEvent] = Field(default_factory=list)
    deducted: int = Field(description="这一场到目前为止的扣分合计（服务端复算）")
    snapshot: dict[str, Any] | None = None
    result: SessionResult | None = None


class AbandonRequest(WebModel):
    confirm: bool = Field(description="必须为 true：放弃已经开始的正式考试，计为本次不通过")


class CeremonyResult(WebModel):
    license: CredentialSummary
    memento: CollectionItem | None = Field(default=None, description="领证合影（收藏）")
    voucher: CollectionItem | None = Field(default=None, description="驾校借车券（第一次自驾免租车费；用掉后为空）")
    pet_says: str
    first_time: bool = Field(description="这是第一次看仪式（再次打开只是回看）")


__all__ = [
    "QuizKind",
    "QuizOption",
    "QuizTarget",
    "QuizQuestionView",
    "QuizAnswer",
    "QuizFeedback",
    "QuizProgress",
    "InputEvent",
    "SimEvent",
    "DriveItemProgress",
    "DriveProgress",
    "Deduction",
    "QuestionReview",
    "ItemResult",
    "NextStep",
    "SessionResult",
    "SchoolSession",
    "SessionCreateRequest",
    "AnswerRequest",
    "AnswerResult",
    "InputChunk",
    "InputResult",
    "AbandonRequest",
    "CeremonyResult",
]
