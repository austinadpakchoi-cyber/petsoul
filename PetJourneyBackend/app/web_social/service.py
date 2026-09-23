"""星球圈：宠物自己的公开动态（只来自真实世界事件）、点赞/评论/回复/关注、屏蔽/举报/撤下。

- 行动者明确：pet（真实账号家庭的宠物）/ owner（主人本人）/ npc（公共居民，不冒充玩家）；
- 计数来自已执行动作；同一行动者对同一帖只计一次点赞；
- 只有家庭允许公开动态的宠物（与生活本来就公开的待领养居民），到访结束才发帖；私密通讯内容不进入动态；
- 帖子属于宠物（author_pet_id）：这只宠物所在家庭的成员都能看到它的非公开帖、都能撤下它的帖子；评论与点赞属于个人；
- 每条动态最多一条 NPC 自动评论（频率与链条上限）。
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from ..schemas.web.common import DataOrigin
from ..schemas.web.social import ActorKind, ActorRef, Comment, CommentPage, Post, PostMedia, PostPage, PostVisibility
from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow

NPC = ActorRef(actor_kind=ActorKind.npc, actor_id="npc-pigeon", display_name="邮差鸽阿咕（星球居民）", avatar_url=None, is_real_household=False)
NPC_LINES = ["咕，这封信我记下了，明天送到。", "咕咕，看起来是个好地方。", "咕，下次路过也帮你捎一张明信片。"]


class SocialError(Exception):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


@dataclass(frozen=True)
class Viewer:
    user_id: str
    pet_id: str | None  # 以宠物身份行动时的那只宠物（显式指明；没有就只能以主人身份）
    pet_name: str | None
    owner_name: str
    pet_ids: tuple[str, ...] = ()  # 这位成员所在家庭的全部宠物（能看到它们的非公开帖、能撤下它们的帖）

    def is_member_of(self, pet_id: str) -> bool:
        return pet_id in self.pet_ids


class WebSocialService:
    def __init__(self, storage: JourneyStorage) -> None:
        self.storage = storage
        self.public_posts_of: Callable[[str], bool] = lambda pet_id: False  # 这只宠物的新动态是否公开（按家庭设置）
        self.members_of_pet: Callable[[str], list[str]] = lambda pet_id: []
        self.pet_ref_of: Callable[[str], ActorRef | None] = lambda pet_id: None
        self.owner_ref_of: Callable[[str], ActorRef | None] = lambda user_id: None
        self.on_post_media_public: Callable[[str], None] = lambda url: None

    # ---- 世界事件 → 动态 ----
    def on_world_event(self, event) -> None:  # WorldEventSink
        if event.kind != "visit_ended" or event.visit is None:
            return
        journey = event.journey
        if not self.public_posts_of(journey.pet_id):
            return
        photo = next((a.get("photo_url") for a in event.visit.activities if a.get("kind") == "take_photo" and a.get("photo_url")), None)
        done = [a["label"] for a in event.visit.activities if a.get("state") == "done" and a.get("kind") != "take_photo"]
        extra = f"，{'、'.join(done)}" if done else ""
        if journey.destination_key.startswith("work:"):
            text = f"今天{journey.title}，在{event.visit.place['name']}忙了一阵{extra}。"
        else:
            text = f"在{event.visit.place['name']}待了一会儿{extra}。{journey.city}的风很舒服。"
        media = [{"media_id": photo.rsplit("/", 1)[-1], "kind": "image", "url": photo, "alt": "纸质卡片（没有照片）", "generated": True}] if photo else []
        post_id = f"post-{uuid.uuid4().hex[:12]}"
        with self.storage.connect() as conn:
            inserted = conn.execute(
                "INSERT OR IGNORE INTO web_posts (post_id, author_pet_id, user_id, text, media_json, source_event_id, visit_id, visibility, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'public', ?)",
                (post_id, journey.pet_id, journey.user_id, text, json.dumps(media, ensure_ascii=False), event.source_event_id, event.visit.visit_id, iso(event.occurred_at)),
            ).rowcount
            if inserted:
                line = NPC_LINES[int(post_id[-2:], 16) % len(NPC_LINES)]
                conn.execute(
                    "INSERT INTO web_comments (comment_id, post_id, actor_kind, actor_id, user_id, reply_to_comment_id, text, created_at) VALUES (?, ?, 'npc', ?, NULL, NULL, ?, ?)",
                    (f"cm-{uuid.uuid4().hex[:12]}", post_id, NPC.actor_id, line, iso(event.occurred_at)),
                )
        if photo:
            self.on_post_media_public(photo)

    # ---- 读取 ----
    def _blocked(self, conn: sqlite3.Connection, viewer_user_id: str) -> set[str]:
        return {r["blocked_user_id"] for r in conn.execute("SELECT blocked_user_id FROM web_blocks WHERE user_id = ?", (viewer_user_id,))} | {
            r["user_id"] for r in conn.execute("SELECT user_id FROM web_blocks WHERE blocked_user_id = ?", (viewer_user_id,))
        }

    def _post(self, conn: sqlite3.Connection, row: sqlite3.Row, viewer: Viewer) -> Post:
        author = self.pet_ref_of(row["author_pet_id"]) or ActorRef(actor_kind=ActorKind.pet, actor_id=row["author_pet_id"], display_name="星球宠物", is_real_household=True)
        reactions = conn.execute("SELECT COUNT(*) AS n FROM web_reactions WHERE post_id = ?", (row["post_id"],)).fetchone()["n"]
        comments = conn.execute("SELECT COUNT(*) AS n FROM web_comments WHERE post_id = ? AND removed_at IS NULL", (row["post_id"],)).fetchone()["n"]
        mine = conn.execute("SELECT 1 FROM web_reactions WHERE post_id = ? AND user_id = ?", (row["post_id"], viewer.user_id)).fetchone()
        return Post(post_id=row["post_id"], author=author, text=row["text"], media=[PostMedia(**m) for m in json.loads(row["media_json"])],
                    source_event_id=row["source_event_id"], visit_id=row["visit_id"], visibility=PostVisibility(row["visibility"]),
                    created_at=parse_dt(row["created_at"]), reaction_count=reactions, comment_count=comments, viewer_reacted=mine is not None, data_origin=DataOrigin.live)

    def feed(self, viewer: Viewer, cursor: str | None = None, limit: int = 20) -> PostPage:
        with self.storage.connect() as conn:
            blocked = self._blocked(conn, viewer.user_id)
            params: list = []
            where = "visibility = 'public'"
            if cursor:
                where += " AND created_at < ?"
                params.append(cursor)
            rows = conn.execute(f"SELECT * FROM web_posts WHERE {where} ORDER BY created_at DESC LIMIT ?", (*params, limit + 1)).fetchall()
            rows = [r for r in rows if r["user_id"] not in blocked]
            items = [self._post(conn, r, viewer) for r in rows[:limit]]
        return PostPage(items=items, next_cursor=rows[limit - 1]["created_at"] if len(rows) > limit else None)

    def pet_posts(self, viewer: Viewer, pet_id: str) -> PostPage:
        with self.storage.connect() as conn:
            blocked = self._blocked(conn, viewer.user_id)
            member = viewer.is_member_of(pet_id)
            rows = conn.execute("SELECT * FROM web_posts WHERE author_pet_id = ? AND (visibility = 'public' OR ?) AND visibility != 'removed' "
                                "ORDER BY created_at DESC LIMIT 50", (pet_id, 1 if member else 0)).fetchall()
            return PostPage(items=[self._post(conn, r, viewer) for r in rows if r["user_id"] not in blocked], next_cursor=None)

    def post(self, viewer: Viewer, post_id: str) -> Post:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM web_posts WHERE post_id = ?", (post_id,)).fetchone()
            if row is None or row["visibility"] == "removed" or (row["visibility"] != "public" and not viewer.is_member_of(row["author_pet_id"])) \
                    or row["user_id"] in self._blocked(conn, viewer.user_id):
                raise SocialError("not_found", "这条动态不存在或已撤下。")
            return self._post(conn, row, viewer)

    def comments(self, viewer: Viewer, post_id: str) -> CommentPage:
        self.post(viewer, post_id)
        with self.storage.connect() as conn:
            blocked = self._blocked(conn, viewer.user_id)
            rows = conn.execute("SELECT * FROM web_comments WHERE post_id = ? ORDER BY created_at", (post_id,)).fetchall()
        items = []
        for r in rows:
            if r["user_id"] and r["user_id"] in blocked:
                continue
            actor = NPC if r["actor_kind"] == "npc" else (self.pet_ref_of(r["actor_id"]) if r["actor_kind"] == "pet" else self.owner_ref_of(r["actor_id"]))
            if actor is None:
                continue
            items.append(Comment(comment_id=r["comment_id"], post_id=r["post_id"], actor=actor, reply_to_comment_id=r["reply_to_comment_id"],
                                 text="" if r["removed_at"] else r["text"], created_at=parse_dt(r["created_at"]), removed=r["removed_at"] is not None))
        return CommentPage(items=items, next_cursor=None)

    # ---- 行动 ----
    def _actor(self, viewer: Viewer, as_actor: ActorKind) -> tuple[str, str]:
        if as_actor is ActorKind.pet:
            if not viewer.pet_id:
                raise SocialError("no_pet", "以宠物身份互动时要指明是哪一只宠物（pet_id）。")
            return "pet", viewer.pet_id
        if as_actor is ActorKind.owner:
            return "owner", viewer.user_id
        raise SocialError("not_allowed", "不能以星球居民身份发言。")

    def react(self, viewer: Viewer, post_id: str, as_actor: ActorKind, now: datetime | None = None) -> Post:
        self.post(viewer, post_id)
        kind, actor_id = self._actor(viewer, as_actor)
        with self.storage.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO web_reactions (post_id, actor_kind, actor_id, user_id, created_at) VALUES (?, ?, ?, ?, ?)",
                         (post_id, kind, actor_id, viewer.user_id, iso(now or utcnow())))
        return self.post(viewer, post_id)

    def comment(self, viewer: Viewer, post_id: str, as_actor: ActorKind, text: str, reply_to: str | None, now: datetime | None = None) -> Comment:
        self.post(viewer, post_id)
        kind, actor_id = self._actor(viewer, as_actor)
        comment_id = f"cm-{uuid.uuid4().hex[:12]}"
        with self.storage.connect() as conn:
            if reply_to and not conn.execute("SELECT 1 FROM web_comments WHERE comment_id = ? AND post_id = ?", (reply_to, post_id)).fetchone():
                raise SocialError("not_found", "要回复的评论不存在。")
            conn.execute("INSERT INTO web_comments (comment_id, post_id, actor_kind, actor_id, user_id, reply_to_comment_id, text, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (comment_id, post_id, kind, actor_id, viewer.user_id, reply_to, text.strip(), iso(now or utcnow())))
        return next(c for c in self.comments(viewer, post_id).items if c.comment_id == comment_id)

    def remove_post(self, viewer: Viewer, post_id: str) -> None:
        """撤下自家宠物的动态：这只宠物所在家庭的成员都可以（被移出家庭后立即不行）。"""
        with self.storage.connect() as conn:
            row = conn.execute("SELECT author_pet_id FROM web_posts WHERE post_id = ? AND visibility != 'removed'", (post_id,)).fetchone()
            if row is None or not viewer.is_member_of(row["author_pet_id"]) \
                    or conn.execute("UPDATE web_posts SET visibility = 'removed', removed_at = ? WHERE post_id = ? AND visibility != 'removed'",
                                    (iso(utcnow()), post_id)).rowcount != 1:
                raise SocialError("not_found", "只能撤下自家宠物的动态。")

    def remove_comment(self, viewer: Viewer, comment_id: str) -> None:
        with self.storage.connect() as conn:
            if conn.execute("UPDATE web_comments SET removed_at = ? WHERE comment_id = ? AND user_id = ?", (iso(utcnow()), comment_id, viewer.user_id)).rowcount != 1:
                raise SocialError("not_found", "只能删除自己的留言。")

    def follow(self, viewer: Viewer, pet_id: str, follow: bool) -> None:
        if not viewer.pet_id or viewer.pet_id == pet_id:
            raise SocialError("not_allowed", "不能关注自己。")
        with self.storage.connect() as conn:
            if follow:
                conn.execute("INSERT OR IGNORE INTO web_follows (follower_pet_id, followee_pet_id, created_at) VALUES (?, ?, ?)", (viewer.pet_id, pet_id, iso(utcnow())))
            else:
                conn.execute("DELETE FROM web_follows WHERE follower_pet_id = ? AND followee_pet_id = ?", (viewer.pet_id, pet_id))

    def is_follower(self, viewer_pet_id: str | None, pet_id: str) -> bool:
        if not viewer_pet_id:
            return False
        with self.storage.connect() as conn:
            return conn.execute("SELECT 1 FROM web_follows WHERE follower_pet_id = ? AND followee_pet_id = ?", (viewer_pet_id, pet_id)).fetchone() is not None

    def counts(self, pet_id: str) -> tuple[int, int]:
        with self.storage.connect() as conn:
            followers = conn.execute("SELECT COUNT(*) AS n FROM web_follows WHERE followee_pet_id = ?", (pet_id,)).fetchone()["n"]
            posts = conn.execute("SELECT COUNT(*) AS n FROM web_posts WHERE author_pet_id = ? AND visibility = 'public'", (pet_id,)).fetchone()["n"]
        return int(followers), int(posts)

    def block(self, viewer: Viewer, blocked_user_id: str) -> None:
        if blocked_user_id == viewer.user_id:
            raise SocialError("not_allowed", "不能屏蔽自己。")
        with self.storage.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO web_blocks (user_id, blocked_user_id, created_at) VALUES (?, ?, ?)", (viewer.user_id, blocked_user_id, iso(utcnow())))

    def report(self, viewer: Viewer, target_kind: str, target_id: str, reason: str) -> None:
        with self.storage.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO web_reports (report_id, reporter_user_id, target_kind, target_id, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                         (f"rp-{uuid.uuid4().hex[:12]}", viewer.user_id, target_kind, target_id, reason[:200], iso(utcnow())))

    def author_user_of_post(self, post_id: str) -> str | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT user_id FROM web_posts WHERE post_id = ?", (post_id,)).fetchone()
        return row["user_id"] if row else None

    def author_user_of_comment(self, comment_id: str) -> str | None:
        """NPC 评论没有真实账号（user_id 为空），不能被“屏蔽作者”。"""
        with self.storage.connect() as conn:
            row = conn.execute("SELECT user_id FROM web_comments WHERE comment_id = ?", (comment_id,)).fetchone()
        return row["user_id"] if row else None

    def unread_circle(self, user_id: str, pet_ids: list[str] | tuple[str, ...], since: datetime | None) -> int:
        """自家宠物的动态下，别人（不是自己）留下的新评论数。"""
        if not pet_ids:
            return 0
        marks = ",".join("?" for _ in pet_ids)
        with self.storage.connect() as conn:
            row = conn.execute(f"SELECT COUNT(*) AS n FROM web_comments c JOIN web_posts p ON p.post_id = c.post_id WHERE p.author_pet_id IN ({marks}) "
                               "AND c.user_id IS NOT ? AND c.created_at > ?", (*pet_ids, user_id, iso(since) if since else "")).fetchone()
        return int(row["n"])
