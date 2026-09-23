import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router";
import type { ActorKind, ActorRef, Comment, Post } from "@/shared/contracts";
import { newIdempotencyKey } from "@/shared/api/idempotency";
import { toApiError } from "@/shared/api/errors";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useSessionState } from "@/shared/session/onboarding";
import { useActiveHome } from "@/shared/session/householdContext";
import { Slot } from "@/shared/slots/Slot";
import { Button, Card, Chip, DataOriginBadge, EmptyState, ErrorState, Icon, Page, PetAvatar, QueryView, ToggleChip, TopBar } from "@/shared/ui";
import "./social.css";

/** 当前查看者的身份：自己的宠物与账号（用于判断“这是我发的吗”）。 */
function useViewer() {
  const home = useActiveHome({ staleTime: 60_000 });
  const session = useSessionState();
  return { petId: home.data?.pet.pet_id ?? null, petName: home.data?.pet.name ?? "TA", userId: session.data?.user?.user_id ?? null };
}

function isMine(actor: ActorRef, viewer: ReturnType<typeof useViewer>): boolean {
  return (actor.actor_kind === "pet" && actor.actor_id === viewer.petId) || (actor.actor_kind === "owner" && actor.actor_id === viewer.userId);
}

function ActorLabel({ actor }: { actor: ActorRef }) {
  const tag = actor.actor_kind === "npc" ? <Chip tone="sky">星球居民</Chip> : actor.actor_kind === "owner" ? <Chip tone="sun">主人</Chip> : null;
  const name = actor.actor_kind === "pet" ? <Link to={`/pets/${actor.actor_id}`}>{actor.display_name}</Link> : <span>{actor.display_name}</span>;
  return (
    <span className="ps-actor">
      <strong>{name}</strong>
      {tag}
    </span>
  );
}

/** 举报 / 屏蔽 / 撤下：都需要主人明确点选；屏蔽后双方互相看不到。 */
function ModerationMenu({ kind, id, mine, onRemoved }: { kind: "post" | "comment"; id: string; mine: boolean; onRemoved?: () => void }) {
  const { social } = useServices();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["social"] });
  const remove = useMutation({
    mutationFn: () => (kind === "post" ? social.removePost(id) : social.removeComment(id)),
    onSuccess: () => {
      setDone(kind === "post" ? "已撤下" : "已删除");
      refresh();
      onRemoved?.();
    },
  });
  const report = useMutation({ mutationFn: () => social.report(kind, id, "owner_reported"), onSuccess: () => setDone("已举报，我们会查看") });
  const block = useMutation({
    mutationFn: () => social.block(kind === "post" ? { post_id: id } : { comment_id: id }),
    onSuccess: () => {
      setDone("已屏蔽这位作者");
      refresh();
    },
  });
  const error = remove.error ?? report.error ?? block.error;
  if (done) return <span className="ps-muted" role="status">{done}</span>;
  return (
    <span className="ps-mod">
      <Button size="sm" variant="ghost" aria-expanded={open} aria-label="更多操作" onClick={() => setOpen((v) => !v)}>
        ···
      </Button>
      {open ? (
        <span className="ps-mod__menu" role="group" aria-label="更多操作">
          {mine ? (
            <Button size="sm" variant="danger" loading={remove.isPending} onClick={() => remove.mutate()}>
              {kind === "post" ? "撤下这条动态" : "删除留言"}
            </Button>
          ) : (
            <>
              <Button size="sm" variant="secondary" loading={report.isPending} onClick={() => report.mutate()}>
                举报
              </Button>
              <Button size="sm" variant="secondary" loading={block.isPending} onClick={() => block.mutate()}>
                屏蔽作者
              </Button>
            </>
          )}
        </span>
      ) : null}
      {error ? (
        <span role="alert" className="ps-muted" style={{ color: "var(--c-danger)" }}>
          {toApiError(error).message}
        </span>
      ) : null}
    </span>
  );
}

function PostMediaView({ post }: { post: Post }) {
  return (
    <>
      {post.media.map((m) =>
        m.url && env.dataMode === "live" ? (
          <figure key={m.media_id} className="ps-post__figure">
            <img src={m.url} alt={m.alt ?? "图片"} loading="lazy" />
            {m.generated ? <figcaption>原创插画明信片，不是真实到店照片</figcaption> : null}
          </figure>
        ) : (
          <div key={m.media_id} className="ps-post__media" role="img" aria-label={m.alt ?? "图片"}>
            <Icon name="camera" /> {m.alt}
            {m.generated ? <Chip>AI 生成图，不是真实到店照片</Chip> : null}
          </div>
        ),
      )}
    </>
  );
}

function PostCard({ post, linkToThread = true }: { post: Post; linkToThread?: boolean }) {
  const { social } = useServices();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const viewer = useViewer();
  const keyRef = useRef(newIdempotencyKey("react"));
  const react = useMutation({
    mutationFn: () => social.react(post.post_id, { as_actor: "pet" }, keyRef.current),
    onSuccess: (next) => {
      keyRef.current = newIdempotencyKey("react");
      queryClient.setQueryData(queryKeys.post(post.post_id), next);
      void queryClient.invalidateQueries({ queryKey: queryKeys.circleFeed });
    },
  });
  const mine = isMine(post.author, viewer);
  return (
    <Card className="ps-post">
      <div className="ps-row" style={{ justifyContent: "space-between" }}>
        <div className="ps-row" style={{ minWidth: 0 }}>
          <PetAvatar petId={post.author.actor_id} name={post.author.display_name} species="cat" photoUrl={post.author.avatar_url} size={36} />
          <ActorLabel actor={post.author} />
        </div>
        <ModerationMenu kind="post" id={post.post_id} mine={mine} onRemoved={() => (!linkToThread ? navigate("/circle") : undefined)} />
      </div>
      <p className="ps-post__text">{post.text}</p>
      <PostMediaView post={post} />
      <div className="ps-row" style={{ justifyContent: "space-between" }}>
        <div className="ps-row">
          <Button
            size="sm"
            variant={post.viewer_reacted ? "secondary" : "ghost"}
            icon="heart"
            loading={react.isPending}
            disabled={post.viewer_reacted || mine}
            onClick={() => react.mutate()}
            aria-label={post.viewer_reacted ? `${viewer.petName} 已点赞，共 ${post.reaction_count}` : `以 ${viewer.petName} 的身份点赞，当前 ${post.reaction_count}`}
          >
            {post.reaction_count}
          </Button>
          {linkToThread ? (
            <Link className="ps-btn ps-btn--ghost ps-btn--sm" to={`/posts/${post.post_id}`} aria-label={`查看评论，共 ${post.comment_count} 条`}>
              <Icon name="comment" size={16} /> {post.comment_count}
            </Link>
          ) : null}
        </div>
        <DataOriginBadge origin={post.data_origin} />
      </div>
      {react.isError ? (
        <span role="alert" className="ps-muted" style={{ color: "var(--c-danger)" }}>
          {toApiError(react.error).message}
        </span>
      ) : null}
    </Card>
  );
}

export function CirclePage() {
  const { social } = useServices();
  const query = useQuery({ queryKey: queryKeys.circleFeed, queryFn: () => social.feed() });
  return (
    <Page>
      <TopBar title="星球圈" subtitle="宠物们自己的公开动态" />
      <Slot name="circle.places" props={{}} />
      <QueryView query={query} isEmpty={(p) => p.items.length === 0} empty={<EmptyState icon="planet" title="还没有动态">宠物们出门到访后的真实事件会出现在这里。</EmptyState>}>
        {(page) => (
          <div className="ps-stack">
            {page.items.map((post) => (
              <PostCard key={post.post_id} post={post} />
            ))}
          </div>
        )}
      </QueryView>
    </Page>
  );
}

/** 评论：主人明确选择以“宠物”还是“主人自己”的身份说话；不会替主人自动发言。 */
function Composer({ postId, replyTo, onDone }: { postId: string; replyTo: Comment | null; onDone: () => void }) {
  const { social } = useServices();
  const queryClient = useQueryClient();
  const viewer = useViewer();
  const [text, setText] = useState("");
  const [asActor, setAsActor] = useState<ActorKind>("pet");
  const keyRef = useRef(newIdempotencyKey("comment"));
  const send = useMutation({
    mutationFn: () => social.comment(postId, { as_actor: asActor, text: text.trim(), reply_to_comment_id: replyTo?.comment_id ?? null }, keyRef.current),
    onSuccess: () => {
      keyRef.current = newIdempotencyKey("comment");
      setText("");
      onDone();
      void queryClient.invalidateQueries({ queryKey: queryKeys.post(postId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.circleFeed });
    },
  });
  return (
    <form
      className="ps-stack ps-composer-card"
      onSubmit={(e) => {
        e.preventDefault();
        if (text.trim()) send.mutate();
      }}
    >
      <div className="ps-segmented" role="group" aria-label="以谁的身份留言">
        <ToggleChip pressed={asActor === "pet"} onToggle={() => setAsActor("pet")}>
          以 {viewer.petName} 的身份
        </ToggleChip>
        <ToggleChip pressed={asActor === "owner"} onToggle={() => setAsActor("owner")}>
          以主人身份
        </ToggleChip>
      </div>
      {replyTo ? <span className="ps-muted">回复 {replyTo.actor.display_name}</span> : null}
      <label className="visually-hidden" htmlFor={`comment-${postId}`}>
        留言
      </label>
      <textarea id={`comment-${postId}`} className="ps-textarea" maxLength={300} value={text} onChange={(e) => setText(e.target.value)} placeholder="说点什么……" />
      <div className="ps-row">
        <Button type="submit" variant="primary" size="sm" loading={send.isPending} disabled={!text.trim()}>
          发表
        </Button>
        {replyTo ? (
          <Button size="sm" variant="ghost" onClick={onDone}>
            取消回复
          </Button>
        ) : null}
        {send.isError ? (
          <span role="alert" className="ps-muted" style={{ color: "var(--c-danger)" }}>
            {toApiError(send.error).message}（内容还在）
          </span>
        ) : null}
      </div>
    </form>
  );
}

export function PostThreadPage() {
  const { postId = "" } = useParams();
  const { social } = useServices();
  const viewer = useViewer();
  const [replyTo, setReplyTo] = useState<Comment | null>(null);
  const post = useQuery({ queryKey: queryKeys.post(postId), queryFn: () => social.post(postId) });
  const comments = useQuery({ queryKey: [...queryKeys.post(postId), "comments"], queryFn: () => social.comments(postId) });
  return (
    <Page>
      <TopBar title="动态" back="/circle" />
      <QueryView query={post}>{(p) => <PostCard post={p} linkToThread={false} />}</QueryView>
      <div className="ps-section-title">评论</div>
      <QueryView query={comments} isEmpty={(c) => c.items.length === 0} empty={<EmptyState icon="comment" title="还没有评论" />}>
        {(page) => (
          <ul className="ps-comments">
            {page.items.map((c) => (
              <li key={c.comment_id} className={c.reply_to_comment_id ? "is-reply" : undefined}>
                <div className="ps-row" style={{ justifyContent: "space-between" }}>
                  <ActorLabel actor={c.actor} />
                  {!c.removed && c.actor.actor_kind !== "npc" ? <ModerationMenu kind="comment" id={c.comment_id} mine={isMine(c.actor, viewer)} /> : null}
                </div>
                <div>{c.removed ? <em className="ps-muted">这条留言已删除</em> : c.text}</div>
                {!c.removed && env.dataMode === "live" ? (
                  <button type="button" className="ps-link-btn" onClick={() => setReplyTo(c)}>
                    回复
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </QueryView>
      {env.dataMode === "live" && post.data ? <Composer postId={postId} replyTo={replyTo} onDone={() => setReplyTo(null)} /> : null}
    </Page>
  );
}

function FollowButton({ petId, following }: { petId: string; following: boolean }) {
  const { social } = useServices();
  const queryClient = useQueryClient();
  const toggle = useMutation({
    mutationFn: () => social.follow(petId, !following),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: queryKeys.petProfile(petId) }),
  });
  return (
    <>
      <Button size="sm" variant={following ? "secondary" : "primary"} loading={toggle.isPending} onClick={() => toggle.mutate()}>
        {following ? "已关注" : "关注"}
      </Button>
      {toggle.isError ? <ErrorState error={toggle.error} /> : null}
    </>
  );
}

export function PetProfilePage() {
  const { petId = "" } = useParams();
  const { pets, social } = useServices();
  const profile = useQuery({ queryKey: queryKeys.petProfile(petId), queryFn: () => pets.publicProfile(petId) });
  const posts = useQuery({ queryKey: queryKeys.petPosts(petId), queryFn: () => social.petPosts(petId) });
  return (
    <Page>
      <TopBar title="宠物主页" back />
      <QueryView query={profile}>
        {(p) => (
          <Card className="ps-row" style={{ alignItems: "flex-start" }}>
            <PetAvatar petId={p.pet_id} name={p.display_name} species={p.species} photoUrl={p.avatar_url} size={64} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <h2 className="ps-h2">{p.display_name}</h2>
              <div className="ps-muted">{p.bio ?? "还没有简介"}</div>
              <div className="ps-row" style={{ flexWrap: "wrap" }}>
                <Chip>{p.follower_count} 只宠物关注</Chip>
                <Chip>{p.post_count} 动态</Chip>
                {p.origin_label ? <Chip>{p.origin_label}</Chip> : null}
                <DataOriginBadge origin={p.data_origin} />
              </div>
            </div>
            {!p.is_own ? <FollowButton petId={p.pet_id} following={p.viewer_follows} /> : <Chip>我的伙伴</Chip>}
          </Card>
        )}
      </QueryView>
      <div className="ps-section-title">TA 的动态</div>
      <QueryView query={posts} isEmpty={(p) => p.items.length === 0} empty={<EmptyState title="还没有公开动态" />}>
        {(page) => (
          <div className="ps-stack">
            {page.items.map((post) => (
              <PostCard key={post.post_id} post={post} />
            ))}
          </div>
        )}
      </QueryView>
    </Page>
  );
}
