/**
 * 用户详情页的「社交」：发过的动态与评论、拉黑与被拉黑、关注、点赞与举报的次数。
 * 动态与评论只给公开范围里的前 40 个字；仅关注者可见的动态不给内容；私聊不在这里——后端就不给。
 * 处理骚扰类举报时要看的就是这些：谁拉黑了谁、被举报过几次。
 */
import { Link } from "react-router";
import { api } from "../api/client";
import type { UserSocialView } from "../api/types";
import { Player } from "../components/player";
import { ErrorNote, Pill, useAsync, when } from "../components/ui";
import { Code, Term } from "../labels";

export function UserSocial({ userId }: { userId: string }) {
  const { data, error, loading } = useAsync(
    () => api.get<UserSocialView>(`/users/${encodeURIComponent(userId)}/social`), [userId]);
  return (
    <div className="card">
      <h2>社交<small>动态、评论、拉黑、关注与举报</small></h2>
      {loading ? <div className="empty">读取中…</div> : error ? <div className="card-body"><ErrorNote error={error} /></div> : !data ? null : (
        <div className="card-body">
          <Counts data={data} />
          <div className="grid cols-2" style={{ marginTop: 12 }}>
            <Posts data={data} />
            <Relations data={data} />
          </div>
          <Comments data={data} />
          <p className="section-note">{data.privacy_note}</p>
        </div>
      )}
    </div>
  );
}

function Missing() {
  return <div className="hint">这个库里还没有这类记录，查不了（不等于没有）。</div>;
}

function n(value: number | null): string {
  return value == null ? "查不了" : `${value} 次`;
}

function Counts({ data }: { data: UserSocialView }) {
  return (
    <dl className="kv">
      <dt>点赞</dt><dd>点过别人 {n(data.reactions.given)}，收到 {n(data.reactions.received)}</dd>
      <dt>举报</dt>
      <dd>举报过别人 {n(data.reports.filed)}，
        自己的内容被举报 {data.reports.against == null ? "查不了" : data.reports.against === 0 ? "0 次" : <Pill tone="warn">{data.reports.against} 次</Pill>}</dd>
    </dl>
  );
}

function Posts({ data }: { data: UserSocialView }) {
  const posts = data.posts;
  return (
    <div>
      <h3 style={{ fontSize: 13, margin: "0 0 6px" }}>发过的动态</h3>
      {posts === null ? <Missing /> : posts.recent.length === 0 ? <div className="hint">还没有发过。</div> : (
        <>
          <div className="hint" style={{ marginBottom: 6 }}>
            {Object.entries(posts.by_visibility).map(([visibility, count], i) => (
              <span key={visibility}>{i > 0 && "，"}<Term family="post_visibility" code={visibility} /> {count} 条</span>))}
          </div>
          <table>
            <thead><tr><th>什么时候</th><th>写了什么（前 40 个字）</th></tr></thead>
            <tbody>
              {posts.recent.map((post) => (
                <tr key={post.post_id}>
                  <td>{when(post.created_at)}<Code value={post.post_id} /></td>
                  <td>
                    {post.excerpt ?? <span className="hint">（不是公开动态，不显示内容）</span>}
                    <div style={{ marginTop: 4 }}>
                      <Pill tone={post.visibility === "removed" ? "danger" : post.visibility === "public" ? "ok" : "muted"}>
                        <Term family="post_visibility" code={post.visibility} /></Pill>{" "}
                      {post.reported && <Pill tone="warn">被举报过</Pill>}
                      {post.removed_at && <span className="hint"> {when(post.removed_at)} 下架</span>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

function Comments({ data }: { data: UserSocialView }) {
  const comments = data.comments;
  return (
    <div style={{ marginTop: 12 }}>
      <h3 style={{ fontSize: 13, margin: "0 0 6px" }}>
        发过的评论{comments && comments.total > 0 && <small className="hint">（一共 {comments.total} 条{comments.removed ? `，被下架 ${comments.removed} 条` : ""}）</small>}
      </h3>
      {comments === null ? <Missing /> : comments.recent.length === 0 ? <div className="hint">还没有评论过。</div> : (
        <table>
          <thead><tr><th>什么时候</th><th>以谁的名义</th><th>写了什么（前 40 个字）</th></tr></thead>
          <tbody>
            {comments.recent.map((comment) => (
              <tr key={comment.comment_id}>
                <td>{when(comment.created_at)}<Code value={comment.comment_id} /></td>
                <td><Term family="actor_kind" code={comment.actor_kind} /></td>
                <td>
                  {comment.excerpt ?? <span className="hint">（没有内容）</span>}
                  {(comment.removed_at || comment.reported) && (
                    <div style={{ marginTop: 4 }}>
                      {comment.removed_at && <Pill tone="danger">已下架</Pill>}{" "}
                      {comment.reported && <Pill tone="warn">被举报过</Pill>}
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function Relations({ data }: { data: UserSocialView }) {
  const blocks = data.blocks;
  const follows = data.follows;
  return (
    <div>
      <h3 style={{ fontSize: 13, margin: "0 0 6px" }}>拉黑</h3>
      {blocks === null ? <Missing /> : (
        <dl className="kv">
          <dt>TA 拉黑了</dt>
          <dd>{blocks.blocked.length === 0 ? "没有人" : blocks.blocked.map((b) => (
            <div key={b.user_id}><Player id={b.user_id} name={b.name} /> <span className="hint">{when(b.created_at)}</span></div>))}</dd>
          <dt>拉黑了 TA 的</dt>
          <dd>{blocks.blocked_by.length === 0 ? "没有人" : blocks.blocked_by.map((b) => (
            <div key={b.user_id}><Player id={b.user_id} name={b.name} /> <span className="hint">{when(b.created_at)}</span></div>))}</dd>
        </dl>
      )}
      <h3 style={{ fontSize: 13, margin: "12px 0 6px" }}>关注（宠物之间）</h3>
      {follows === null ? <Missing /> : (
        <dl className="kv">
          <dt>TA 家宠物关注了</dt>
          <dd>{follows.following.length === 0 ? "没有" : follows.following.map((f, i) => (
            <div key={`${f.pet_id}-${i}`}><Link to={`/pets/${f.pet_id}`}>{f.pet_name ?? "（没有名字）"}</Link> <span className="hint">{when(f.created_at)}</span><Code value={f.pet_id} /></div>))}</dd>
          <dt>关注 TA 家宠物的</dt>
          <dd>{follows.followers.length === 0 ? "没有" : follows.followers.map((f, i) => (
            <div key={`${f.pet_id}-${i}`}><Link to={`/pets/${f.pet_id}`}>{f.pet_name ?? "（没有名字）"}</Link> <span className="hint">{when(f.created_at)}</span><Code value={f.pet_id} /></div>))}</dd>
        </dl>
      )}
    </div>
  );
}
