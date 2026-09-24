/**
 * 宠物页的「TA 的东西」：收藏、证件、护照、驾校、消息往来、角色形象。
 * 只有状态、数量与时间——消息正文、明信片上的字、驾校的愿望原文、考试答案、照护档案的内容都不在后台显示（后端就不给）。
 */
import { api } from "../api/client";
import type { PetBelongingsView } from "../api/types";
import { CallStatePill, ErrorNote, Pill, useAsync, when } from "../components/ui";
import { Code, Tech, Term } from "../labels";

export function PetBelongings({ petId }: { petId: string }) {
  const { data, error, loading } = useAsync(() => api.get<PetBelongingsView>(`/pets/${petId}/belongings`), [petId]);
  if (loading) return <div className="card"><div className="empty">读取 TA 的东西…</div></div>;
  if (error) return <ErrorNote error={error} />;
  if (!data) return null;

  return (
    <>
      <div className="grid cols-2">
        <Messages data={data} />
        <Character data={data} />
      </div>
      <div className="grid cols-2">
        <Collection data={data} />
        <div className="card">
          <h2>证件、护照与驾校</h2>
          <div className="card-body">
            <Credentials data={data} />
            <Driving data={data} />
          </div>
        </div>
      </div>
      <div className="grid cols-2">
        <Friends data={data} />
        <SchoolMediaFood data={data} />
      </div>
      <p className="section-note" style={{ margin: "-4px 0 16px" }}>{data.privacy_note}</p>
    </>
  );
}

function Missing() {
  return <div className="empty">这个库里还没有这类记录，查不了（不等于没有）。</div>;
}

function Messages({ data }: { data: PetBelongingsView }) {
  const m = data.messages;
  return (
    <div className="card">
      <h2>消息往来<small>只有条数与时间，不看内容</small></h2>
      {m === null ? <Missing /> : (
        <div className="card-body">
          <dl className="kv">
            <dt>主人发的</dt><dd>{m.by_sender.owner ? `${m.by_sender.owner.count} 条，最近一条 ${when(m.by_sender.owner.last_at)}` : "还没有"}</dd>
            <dt>TA 发的</dt><dd>{m.by_sender.pet ? `${m.by_sender.pet.count} 条，最近一条 ${when(m.by_sender.pet.last_at)}` : "还没有"}</dd>
            <dt>消息里的照片</dt>
            <dd>{Object.keys(m.photos).length === 0 ? "没有" : Object.entries(m.photos).map(([state, n]) => (
              <span key={state} style={{ marginRight: 8 }}><CallStatePill state={state} /> {n}</span>))}</dd>
          </dl>
          {m.replies.length > 0 && (
            <table style={{ marginTop: 10 }}>
              <thead><tr><th>主人来消息后</th><th>该回的时间</th><th>结果</th></tr></thead>
              <tbody>
                {m.replies.map((reply, index) => (
                  <tr key={index}>
                    <td><Term family="reply_reason" code={reply.reason} /></td>
                    <td>{when(reply.due_at)}{reply.overdue && <Pill tone="warn">已过点还没回</Pill>}</td>
                    <td>{reply.outcome ? <Term family="reply_outcome" code={reply.outcome} /> : "还没回"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

function Character({ data }: { data: PetBelongingsView }) {
  const c = data.character;
  return (
    <div className="card">
      <h2>角色形象</h2>
      {c === null ? <Missing /> : (
        <div className="card-body">
          <p style={{ margin: "0 0 8px" }}>
            {c.active ? <>正在用第 {c.active.revision} 版，{when(c.active.published_at)} 换上的<Code value={c.active.set_id} /></>
              : "还没有正式用上的形象。"}
          </p>
          {c.takes.length === 0 ? <div className="hint">没有生成记录。</div> : (
            <table>
              <thead><tr><th>姿势</th><th>状态</th><th>更新</th></tr></thead>
              <tbody>
                {c.takes.map((take, index) => (
                  <tr key={index}>
                    <td><Term family="character_pose" code={take.pose} /></td>
                    <td><Term family="character_state" code={take.state} />
                      {take.reason && <div className="hint"><Term family="character_reason" code={take.reason} /></div>}<Tech>{take.task_id}</Tech></td>
                    <td>{when(take.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <IdPhoto photo={c.id_photo} />
        </div>
      )}
    </div>
  );
}

/** 证件照：和角色形象同一套原因码，但额度车道是它自己的（每宠上限与角色同一个数、单独计数）。只看状态，不看图。 */
function IdPhoto({ photo }: { photo: NonNullable<PetBelongingsView["character"]>["id_photo"] }) {
  return (
    <>
      <h3 style={{ fontSize: 13, margin: "14px 0 6px" }}>证件照</h3>
      {!photo ? <div className="hint">这个库里还没有证件照记录，查不了（不等于没有）。</div> : (
        <>
          <p style={{ margin: "0 0 8px" }}>
            {photo.active ? <>正在用第 {photo.active.revision} 版，{when(photo.active.published_at)} 换上的</> : "还没有生效的证件照。"}
          </p>
          {photo.takes.length === 0 ? <div className="hint">没有生成记录。</div> : (
            <table>
              <thead><tr><th>第几版</th><th>状态</th><th>更新</th></tr></thead>
              <tbody>
                {photo.takes.map((take) => (
                  <tr key={take.revision}>
                    <td>第 {take.revision} 版</td>
                    <td><Term family="character_state" code={take.state} />
                      {take.reason && <div className="hint"><Term family="character_reason" code={take.reason} /></div>}<Tech>{take.task_id}</Tech></td>
                    <td>{when(take.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </>
  );
}

function Collection({ data }: { data: PetBelongingsView }) {
  const c = data.collection;
  return (
    <div className="card">
      <h2>收藏<small>{c ? `一共 ${Object.values(c.counts).reduce((sum, n) => sum + n, 0)} 个` : ""}</small></h2>
      {c === null ? <Missing /> : (
        <div className="card-body">
          <p style={{ margin: "0 0 8px" }}>
            {Object.keys(c.counts).length === 0 ? "还没有收藏。" : Object.entries(c.counts).map(([kind, n], i) => (
              <span key={kind}>{i > 0 && "，"}<Term family="collection_kind" code={kind} /> {n} 个</span>))}
          </p>
          {c.items.length > 0 && (
            <table>
              <thead><tr><th>是什么</th><th>在哪儿得到</th><th>配图</th><th>时间</th></tr></thead>
              <tbody>
                {c.items.map((item) => (
                  <tr key={item.item_id}>
                    <td><Term family="collection_kind" code={item.kind} />{item.consumed_at && <span className="hint">（已用掉）</span>}<Code value={item.item_id} /></td>
                    <td>{item.city ?? "—"}</td>
                    <td>{item.image_status ? <CallStatePill state={item.image_status} /> : "—"}</td>
                    <td>{when(item.obtained_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

function Credentials({ data }: { data: PetBelongingsView }) {
  const creds = data.credentials;
  const passport = data.passport;
  return (
    <dl className="kv" style={{ marginBottom: 12 }}>
      <dt>证件</dt>
      <dd>{creds === null ? "查不了" : creds.length === 0 ? "还没有" : creds.map((c, i) => (
        <div key={i}><Term family="credential_kind" code={c.kind} />{c.number_tail ? `（尾号 ${c.number_tail}）` : ""} · {when(c.issued_at)}</div>
      ))}</dd>
      <dt>护照印章</dt>
      <dd>{passport === null ? "查不了" : passport.count === 0 ? "还没有" : (
        <>{passport.count} 个{passport.recent.length > 0 && <div className="hint">最近：{passport.recent.slice(0, 3).map((s) => s.city ?? s.title).join("、")}</div>}</>
      )}</dd>
    </dl>
  );
}

function Driving({ data }: { data: PetBelongingsView }) {
  const d = data.driving;
  if (d === null) return <div className="hint">驾校：查不了</div>;
  if (!d.stage) return <div className="hint">驾校：{d.note ?? "没有学车记录。"}</div>;
  return (
    <dl className="kv">
      <dt>驾校</dt>
      <dd><Term family="driving_stage" code={d.stage} />{d.needs_practice && <Pill tone="warn">需要多练</Pill>}
        <div className="hint">
          {d.enrolled_at && `入学 ${when(d.enrolled_at)}`}{d.theory_passed_at && `，理论通过 ${when(d.theory_passed_at)}`}
          {d.licensed_at && `，拿证 ${when(d.licensed_at)}`}
        </div></dd>
      {d.exams && d.exams.length > 0 && (<>
        <dt>考试</dt>
        <dd>{d.exams.map((exam, i) => (
          <div key={i}>第 {exam.attempt_no} 次 · {exam.score ?? "—"}/{exam.max_score ?? "—"} 分 · {exam.passed ? "通过" : "没过"} · {when(exam.taken_at)}
            <Code value={exam.part} /></div>
        ))}</dd>
      </>)}
    </dl>
  );
}

function Friends({ data }: { data: PetBelongingsView }) {
  const friends = data.friends;
  return (
    <div className="card">
      <h2>朋友<small>{friends ? `${friends.length} 个` : ""}</small></h2>
      {friends == null ? <Missing /> : friends.length === 0 ? <div className="empty">还没有交到朋友。</div> : (
        <table>
          <thead><tr><th>谁</th><th className="num">见过几次</th><th>最近一次</th></tr></thead>
          <tbody>
            {friends.map((f) => (
              <tr key={f.friend_id}>
                <td>{f.friend_name ?? "（没有名字）"}<div className="hint"><Term family="friend_kind" code={f.friend_kind} /></div><Code value={f.friend_id} /></td>
                <td className="num">{f.meet_count}</td>
                <td>{when(f.last_met_at)}{f.last_place && <div className="hint">在 {f.last_place}</div>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function SchoolMediaFood({ data }: { data: PetBelongingsView }) {
  const school = data.school;
  const media = data.media;
  const food = data.food;
  return (
    <div className="card">
      <h2>驾校课堂、同行影音、口味</h2>
      <div className="card-body">
        <h3 style={{ fontSize: 13, margin: "0 0 6px" }}>驾校课堂</h3>
        {school == null ? <div className="hint">查不了。</div> : school.subjects.length === 0 && school.sessions.length === 0 ? (
          <div className="hint">还没有上过课、考过试。</div>
        ) : (
          <>
            {school.subjects.map((s) => (
              <div key={s.subject} style={{ fontSize: 12.5 }}>
                {s.title ?? s.subject}：{s.passed_at ? <Pill tone="ok">通过了（{s.passed_score ?? "—"} 分）</Pill> : "还没通过"}
                <span className="hint">，练了 {s.practice_count} 次{s.fails_in_round ? `，这一轮没过 ${s.fails_in_round} 次` : ""}
                  {s.cooldown_until ? `，要等到 ${when(s.cooldown_until)} 才能再约考试` : ""}</span>
                <Code value={s.subject} />
              </div>
            ))}
            {school.sessions.length > 0 && (
              <div className="hint" style={{ marginTop: 4 }}>最近几次：{school.sessions.slice(0, 5).map((s, i) => (
                <span key={i}>{i > 0 && "；"}{s.title ?? s.subject} · <Term family="school_mode" code={s.mode} /> · <Term family="school_state" code={s.state} />
                  {s.score != null ? ` · ${s.score} 分` : ""}</span>))}</div>
            )}
          </>
        )}
        {school?.notes && school.notes.count > 0 && (
          <div className="hint" style={{ marginTop: 4 }}>主人给驾校留过 {school.notes.count} 句话，送到 {school.notes.delivered} 句（不看内容）。</div>
        )}

        <h3 style={{ fontSize: 13, margin: "12px 0 6px" }}>同行影音</h3>
        {media == null ? <div className="hint">查不了。</div> : media.count === 0 ? <div className="hint">没有一起听过、看过。</div> : (
          media.recent.map((m) => (
            <div key={m.session_id} style={{ fontSize: 12.5 }}>
              <Term family="media_state" code={m.state} /> · {m.devices} 台设备 · 听了 {m.minutes} 分钟 · {when(m.updated_at)}
              <span className="hint"> {m.modes.map((mode) => <Term key={mode} family="participation_mode" code={mode} />)}</span>
              <Code value={m.session_id} />
            </div>
          ))
        )}

        <h3 style={{ fontSize: 13, margin: "12px 0 6px" }}>口味（只看数量，不看内容）</h3>
        {food == null ? <div className="hint">查不了。</div> : (
          <div style={{ fontSize: 12.5 }}>
            偏好：{Object.keys(food.preferences).length === 0 ? "还没填" : Object.entries(food.preferences).map(([subject, n], i) => (
              <span key={subject}>{i > 0 && "，"}<Term family="food_subject" code={subject} /> {n} 条</span>))}
            <br />推荐：{Object.keys(food.recommendations).length === 0 ? "还没有" : Object.entries(food.recommendations).map(([mode, n], i) => (
              <span key={mode}>{i > 0 && "，"}<Term family="food_mode" code={mode} /> {n} 次</span>))}
            {food.feedback != null && <>；吃后反馈 {food.feedback} 条</>}
          </div>
        )}
      </div>
    </div>
  );
}
