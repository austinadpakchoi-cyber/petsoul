import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { api, playerAnnouncements } from "../api/client";
import type { ContentDetailView, ContentTypeInfo, PreviewView, SessionView } from "../api/types";
import ContentBodyForm, { type Body } from "../components/ContentBodyForm";
import { ErrorNote, Pill, ReasonDialog, useAsync, when, type ConfirmSpec } from "../components/ui";
import { Code, FieldName, PermissionName, Staff, Tech, Term } from "../labels";

export default function ContentDetailPage({ session }: { session: SessionView }) {
  const { itemId = "" } = useParams();
  const { data, error, loading, reload } = useAsync(() => api.get<ContentDetailView>(`/content/${itemId}`), [itemId]);
  const [draft, setDraft] = useState<Body | null>(null);
  const [preview, setPreview] = useState<PreviewView | null>(null);
  const [dialog, setDialog] = useState<ConfirmSpec | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [playerView, setPlayerView] = useState<string>("");
  const [applyNote, setApplyNote] = useState<string | null>(null);
  const [typeInfo, setTypeInfo] = useState<ContentTypeInfo | undefined>(undefined);

  const canEdit = session.staff.permissions.includes("content.edit");
  const canPublish = session.staff.permissions.includes("content.publish");

  useEffect(() => { if (data && draft === null) setDraft({ ...(data.revisions[0]?.body ?? {}) }); }, [data, draft]);
  useEffect(() => {
    api.get<{ types: ContentTypeInfo[] }>("/content")
      .then((payload) => setTypeInfo(payload.types.find((t) => t.content_type === data?.item.content_type)))
      .catch(() => setTypeInfo(undefined));
  }, [data?.item.content_type]);

  const refreshPlayer = async () => {
    if (data?.item.content_type === "announcement") {
      const payload = await playerAnnouncements();
      const hit = payload.announcements.find((a) => a.item_id === itemId);
      setPlayerView(hit ? `玩家端正在读 v${hit.revision}：${hit.title}` : "玩家端此刻读不到这条内容。");
      return;
    }
    // 其余类型没有一个"列出全部"的玩家接口可以直接对照，只如实说明当前发布状态与消费方。
    if (!data) return;
    setPlayerView(data.item.live_revision
      ? `已发布 v${data.item.live_revision}；此后新发生的事件会用这一版。已经发生过的不变。`
      : "当前没有已发布版本，玩家侧用的是内置值。");
  };
  useEffect(() => { void refreshPlayer(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [data]);

  if (loading) return <div className="empty">读取中…</div>;
  if (error) return <ErrorNote error={error} />;
  if (!data || draft === null) return null;
  const item = data.item;
  const set = (key: string, value: unknown) => setDraft((current) => ({ ...(current ?? {}), [key]: value }));

  const save = async () => {
    setBusy(true); setActionError(null);
    try {
      await api.put(`/content/${itemId}`, { body: draft, expected_version: item.version });
      setPreview(null);
      reload();
    } catch (exc) { setActionError(exc); } finally { setBusy(false); }
  };

  const doPreview = async (revision?: number) => {
    setBusy(true); setActionError(null);
    try {
      setPreview(await api.get<PreviewView>(`/content/${itemId}/preview${revision ? `?revision=${revision}` : ""}`));
    } catch (exc) { setActionError(exc); } finally { setBusy(false); }
  };

  // 居民文案发布之后，名单上真实发生了什么（后端给一句人话；被跳过也要当场说出来）
  const after = (result?: unknown) => {
    const note = (result as { resident_apply_note?: string } | null | undefined)?.resident_apply_note;
    setApplyNote(note ?? null);
    setPreview(null); reload(); void refreshPlayer();
  };

  return (
    <>
      <div className="page-head">
        <h1>{item.title}</h1>
        <Code value={`${item.content_type} · ${item.slug}`} />
        {item.status === "published" ? <Pill tone="ok">已发布 v{item.live_revision}</Pill>
          : item.status === "withdrawn" ? <Pill tone="warn">已撤下</Pill> : <Pill tone="muted">草稿</Pill>}
        <Link to="/content">返回列表</Link>
      </div>

      <ErrorNote error={actionError} />
      {playerView && <div className="note info">{playerView}</div>}
      {applyNote && <div className={`note ${applyNote.includes("没有改") ? "warn" : "ok"}`}>{applyNote}</div>}

      <div className="grid cols-2">
        <div className="card">
          <h2>草稿 v{item.draft_revision ?? "—"}<small>保存会生成新的版本号</small></h2>
          <div className="card-body">
            <ContentBodyForm contentType={item.content_type} body={draft} disabled={!canEdit}
                             info={typeInfo} onChange={set} />
            <div className="actions">
              <button onClick={save} disabled={!canEdit || busy}>保存为新草稿</button>
              <button onClick={() => doPreview()} disabled={busy}>预览</button>
              {!canEdit && <span className="pill muted">需要「<PermissionName code="content.edit" />」权限</span>}
            </div>
          </div>
        </div>

        <div className="card">
          <h2>预览与校验<small>按玩家侧真正会读到的形态</small></h2>
          <div className="card-body">
            {!preview ? <div className="empty">点「预览」看这一版发出去会是什么样。</div> : (
              <>
                {preview.issues.length > 0 ? (
                  <div className="note warn"><strong>这一版不能发布：</strong>
                    <ul className="effects">{preview.issues.map((i) => <li key={i.field + i.message}><FieldName field={i.field} />：{i.message}</li>)}</ul>
                  </div>
                ) : <div className="note ok">校验通过，可以发布。</div>}
                <dl className="kv">
                  {Object.entries(preview.rendered).map(([key, value]) => (
                    <div key={key} style={{ display: "contents" }}>
                      <dt><FieldName field={key} /></dt><dd><PreviewValue field={key} value={value} /></dd>
                    </div>
                  ))}
                </dl>
                <div className="actions" style={{ marginTop: 12 }}>
                  <button className="primary" disabled={!canPublish || !preview.publishable || busy}
                          onClick={() => setDialog({
                            title: `发布 v${preview.revision}`,
                            confirmLabel: "发布",
                            effects: ["玩家侧从生效那一刻起读到这一版。",
                                      "已经发生过的事实（已发奖励、已登记的事件）不会被改写。",
                                      "发布会留下不可变版本、操作者、原因与差异摘要。"],
                            run: (reason, op) => api.post(`/content/${itemId}/publish`,
                              { revision: preview.revision, expected_version: item.version, reason }, op),
                          })}>发布这一版</button>
                  {item.status === "published" && canPublish && (
                    <button className="danger" onClick={() => setDialog({
                      title: "撤下当前版本", danger: true, confirmLabel: "撤下",
                      effects: ["玩家侧立刻读不到这条内容。", "发布历史与历史版本都保留，不是删除。"],
                      run: (reason, op) => api.post(`/content/${itemId}/withdraw`, { expected_version: item.version, reason }, op),
                    })}>撤下</button>
                  )}
                  {!canPublish && <span className="pill muted">需要「<PermissionName code="content.publish" />」权限</span>}
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      <div className="card">
        <h2>版本历史<small>不可变</small></h2>
        <table>
          <thead><tr><th>版本</th><th>说明</th><th>作者</th><th>时间</th><th /> <th>操作</th></tr></thead>
          <tbody>
            {data.revisions.map((rev) => (
              <tr key={rev.revision}>
                <td>v{rev.revision}{item.live_revision === rev.revision && <> <Pill tone="ok">线上</Pill></>}</td>
                <td>{rev.note ?? "—"}{rev.source_revision && <div style={{ color: "var(--ink-faint)", fontSize: 12 }}>复制自 v{rev.source_revision}</div>}</td>
                <td><Staff id={rev.created_by} /></td>
                <td>{when(rev.created_at)}</td>
                <td><Tech>{rev.body_hash.slice(0, 12)}</Tech></td>
                <td>
                  <div className="actions">
                    <button className="ghost" onClick={() => doPreview(rev.revision)}>预览</button>
                    {canPublish && item.live_revision !== rev.revision && (
                      <button onClick={() => setDialog({
                        title: `回退到 v${rev.revision}`,
                        confirmLabel: "回退",
                        effects: ["回退＝把旧正文复制成一个新版本号再发布。",
                                  "历史版本与发布流水一条不少，世界时钟与既有事实不动。",
                                  "已经发生过的事件不会被改写。"],
                        run: (reason, op) => api.post(`/content/${itemId}/rollback`,
                          { to_revision: rev.revision, expected_version: item.version, reason }, op),
                      })}>回退到这一版</button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>发布历史<small>仅追加</small></h2>
        {data.publications.length === 0 ? <div className="empty">还没有发布过。</div> : (
          <table>
            <thead><tr><th>动作</th><th>版本</th><th>生效</th><th>操作者</th><th>原因</th><th>差异</th><th>时间</th></tr></thead>
            <tbody>
              {data.publications.map((pub) => (
                <tr key={pub.publication_id}>
                  <td>{pub.action === "publish" ? <Pill tone="ok">发布</Pill> : <Pill tone="warn">撤下</Pill>}</td>
                  <td>v{pub.revision}</td>
                  <td>{when(pub.effective_at)}</td>
                  <td><Staff id={pub.staff_id} /></td>
                  <td>{pub.reason}</td>
                  <td><DiffSummary text={pub.diff_summary} /></td>
                  <td>{when(pub.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {dialog && <ReasonDialog spec={dialog} onClose={() => setDialog(null)} onDone={after} />}
    </>
  );
}

/** 预览里的一格：公告的级别与可见范围说人话；其余照原样（它们就是玩家会读到的文字）。 */
function PreviewValue({ field, value }: { field: string; value: unknown }) {
  if (value === null || value === undefined || value === "") return <>—</>;
  if (field === "severity") return <Term family="announcement_severity" code={String(value)} />;
  if (field === "audience") return <Term family="announcement_audience" code={String(value)} />;
  if (field === "consumer") return <>{String(value)}</>;
  return <>{typeof value === "object" ? JSON.stringify(value) : String(value)}</>;
}

/** 发布流水里的差异摘要。第九批起后端直接写说法；更早的记录里是字段代码（「改动字段：title、body」），这里按词表显示成说法，原文不改。 */
function DiffSummary({ text }: { text: string | null }) {
  if (!text) return <>—</>;
  const match = /^(首次发布|改动字段)：(.+)$/.exec(text);
  if (!match) return <>{text}</>;
  return <>{match[1]}：{match[2].split("、").map((field, i) => <span key={field}>{i > 0 && "、"}<FieldName field={field} /></span>)}</>;
}
