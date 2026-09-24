"""星球圈（公开）与通讯（私密）契约，以及收藏/市场。

- 行动者明确：其他家庭的宠物、公共 NPC、主人本人三类不混淆；NPC 不冒充真实玩家。
- 计数来自已执行动作；不预填随机点赞。
- 通讯为主人与专属宠物的私密通道，复用既有 communicator 服务，不进入公开 Post。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from .common import DataOrigin, WebModel


class ActorKind(str, Enum):
    pet = "pet"
    npc = "npc"
    owner = "owner"


class ActorRef(WebModel):
    actor_kind: ActorKind
    actor_id: str
    display_name: str
    avatar_url: str | None = None
    is_real_household: bool = Field(description="真实账号家庭的宠物/主人为 true；NPC 恒为 false")


class PostVisibility(str, Enum):
    public = "public"
    followers = "followers"
    removed = "removed"


class PostMedia(WebModel):
    media_id: str
    kind: str
    url: str | None = None
    alt: str | None = None
    generated: bool = Field(description="AI 生成图为 true；生成图不代表真实到店照片")


class Post(WebModel):
    post_id: str
    author: ActorRef
    text: str
    media: list[PostMedia] = Field(default_factory=list)
    source_event_id: str = Field(description="来源世界事件；普通动作不逐条发帖")
    visit_id: str | None = None
    visibility: PostVisibility
    created_at: datetime
    reaction_count: int = 0
    comment_count: int = 0
    viewer_reacted: bool = False
    data_origin: DataOrigin


class Comment(WebModel):
    comment_id: str
    post_id: str
    actor: ActorRef
    reply_to_comment_id: str | None = None
    text: str
    created_at: datetime
    removed: bool = False


class PostPage(WebModel):
    items: list[Post] = Field(default_factory=list)
    next_cursor: str | None = None


class CommentPage(WebModel):
    items: list[Comment] = Field(default_factory=list)
    next_cursor: str | None = None


class ReactionRequest(WebModel):
    """需 Idempotency-Key；同一行动者对同一帖只计一次。"""

    as_actor: ActorKind


class CommentRequest(WebModel):
    """需 Idempotency-Key。"""

    as_actor: ActorKind
    text: str = Field(min_length=1, max_length=280)
    reply_to_comment_id: str | None = None


class FollowRequest(WebModel):
    follow: bool = True


class BlockRequest(WebModel):
    """屏蔽某条动态/评论的作者（不暴露对方账号 ID）。"""

    post_id: str | None = None
    comment_id: str | None = None


class ReportRequest(WebModel):
    target_kind: str = Field(pattern="^(post|comment)$")
    target_id: str
    reason: str = Field(min_length=1, max_length=200)


class MessageSender(str, Enum):
    owner = "owner"
    pet = "pet"


class MessageDeliveryState(str, Enum):
    sending = "sending"
    delivered = "delivered"
    awaiting_reply = "awaiting_reply"
    processing = "processing"
    failed = "failed"


class MessageComposer(str, Enum):
    """这条消息是谁写的：世界事件模板 / 固定模板回应 / 对话模型（主人开启“模型回信”后）。"""

    event = "event"
    template = "template"
    model = "model"


class MessageTopic(str, Enum):
    """TA 主动发来的消息的话题（news＝刚发生了值得分享的事）；回复主人与世界事件消息为空。"""

    morning = "morning"
    share = "share"
    goodnight = "goodnight"
    thinking_of_you = "thinking_of_you"
    news = "news"


class PhotoStatus(str, Enum):
    """processing＝还在画；ready＝画好了；failed＝确定没画成（可以重画）；

    unknown＝**结果还没确认**：请求已经发出去、可能已经受理并计费，但响应没拿回来（超时、传输中断，或响应回来后解析失败）。
    页面要显示成"还没确认"并给"重画"入口，**不能写成"没画成"**——那会让主人以为什么都没发生。
    """

    processing = "processing"
    ready = "ready"
    failed = "failed"
    unknown = "unknown"


class MessageChannel(str, Enum):
    """private：你和 TA 的私聊（只有你看得到）；family：家庭频道（世界事件来信、明信片、攻略、新鲜事，全家都看得到）。"""

    private = "private"
    family = "family"


class MessageSummary(WebModel):
    message_id: str
    client_message_id: str | None = None
    sender: MessageSender
    text: str
    state: MessageDeliveryState
    created_at: datetime
    photo_url: str | None = None
    composed_by: MessageComposer | None = Field(default=None, description="宠物消息的来源；主人消息为空", json_schema_extra={"x-additive": True})
    photo_status: PhotoStatus | None = Field(default=None, description="附图（冒险插画）状态；无附图为空", json_schema_extra={"x-additive": True})
    topic: MessageTopic | None = Field(default=None, description="TA 主动发来的消息的话题", json_schema_extra={"x-additive": True})
    status_note: str | None = Field(default=None, description="主人消息等待回复时的说明，例如“TA 睡着啦，醒来会看到”", json_schema_extra={"x-additive": True})
    expected_reply_at: datetime | None = Field(default=None, description="预计回复时间（等待中才有）", json_schema_extra={"x-additive": True})
    channel: MessageChannel = Field(default=MessageChannel.private, description="这条消息在哪个频道（0.4.0 家庭共同照顾）", json_schema_extra={"x-additive": True})
    source_event_id: str | None = Field(default=None, description="由世界事件产生的来信指向那个事件（<journey_id>:<事件键>），同一事件全家只有一条；其他消息为空（0.4.1）",
                                        json_schema_extra={"x-additive": True})
    reply_to: str | None = Field(default=None, description="TA 的这条回复针对的家人消息编号（0.4.1）", json_schema_extra={"x-additive": True})


class MessageThread(WebModel):
    pet_id: str
    items: list[MessageSummary] = Field(default_factory=list)
    next_cursor: str | None = None
    data_origin: DataOrigin


class SendMessageRequest(WebModel):
    """client_message_id 即幂等键（复用旧 communicator 的 (pet_id, client_message_id) 去重）。"""

    client_message_id: str = Field(min_length=8, max_length=64)
    text: str = Field(min_length=1, max_length=500)


class FriendKind(str, Enum):
    pet = "pet"
    resident = "resident"


class FriendSummary(WebModel):
    """TA 在外面遇到的朋友：真实宠物（同一时间同一地点遇到）或星球居民（NPC，明确标注）。"""

    friend_id: str
    kind: FriendKind
    name: str
    species: str | None = None
    meet_count: int
    closeness: str = Field(description="初识 / 熟人 / 好朋友")
    first_met_at: datetime
    last_met_at: datetime
    last_place: str | None = None


class CollectionItem(WebModel):
    item_id: str
    kind: str
    item_key: str | None = Field(default=None, description="可种植种子的作物键（kind=seed 时有值）")
    title: str
    obtained_at: datetime
    tradable: bool
    bound_to_pet: bool
    source_event_id: str | None = None
    data_origin: DataOrigin
    note: str | None = Field(default=None, description="明信片上 TA 写给主人的话", json_schema_extra={"x-additive": True})
    image_url: str | None = Field(default=None, description="明信片上的写实自拍（生成完成后才有；仅主人可读）", json_schema_extra={"x-additive": True})
    image_status: PhotoStatus | None = Field(default=None, description="自拍生成状态；没有开启“生成照片”时为空", json_schema_extra={"x-additive": True})
    place: str | None = Field(default=None, description="寄出明信片的地方", json_schema_extra={"x-additive": True})
    city: str | None = Field(default=None, json_schema_extra={"x-additive": True})


__all__ = [
    "ActorKind",
    "ActorRef",
    "PostVisibility",
    "PostMedia",
    "Post",
    "Comment",
    "PostPage",
    "CommentPage",
    "ReactionRequest",
    "CommentRequest",
    "FollowRequest",
    "BlockRequest",
    "ReportRequest",
    "MessageSender",
    "MessageDeliveryState",
    "MessageComposer",
    "MessageTopic",
    "MessageChannel",
    "PhotoStatus",
    "MessageSummary",
    "MessageThread",
    "SendMessageRequest",
    "CollectionItem",
    "FriendKind",
    "FriendSummary",
]
