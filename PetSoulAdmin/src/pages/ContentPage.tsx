import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { api, playerAnnouncements, type PlayerAnnouncement } from "../api/client";
import type { ContentItem, ContentSource, ContentType, ContentTypeInfo, SessionView, ValidationIssue } from "../api/types";
import ContentBodyForm, { EMPTY_BODY, type Body } from "../components/ContentBodyForm";
import { ErrorNote, Pill, useAsync, when } from "../components/ui";
import { Code, FieldName, PermissionName, Tech, useTech } from "../labels";

/** 公告的内部标识：自动生成（notice-年月日-四位随机），运营不必自己想英文名。 */
function autoSlug(): string {
  const day = new Date().toISOString().slice(0, 10).split("-").join("");
  return `notice-${day}-${Math.random().toString(16).slice(2, 6)}`;
}

const KIND_LABEL: Record<string, string> = {
  standalone: "独立内容",
  overlay: "给内置目录发新版本",
  table: "改业务表里的文案",
};

export default function ContentPage({ session }: { session: SessionView }) {
  const { data, error, loading, reload } = useAsync(
    () => api.get<{ items: ContentItem[]; types: ContentTypeInfo[] }>("/content"), []);
  const player = useAsync(() => playerAnnouncements(), []);
  const canEdit = session.staff.permissions.includes("content.edit");
  const [params, setParams] = useSearchParams();
  const preset = params.get("new") === "resident" && params.get("slug") ? params.get("slug") : null;
  const [creating, setCreating] = useState(Boolean(preset && canEdit));

  if (loading) return <div className="empty">读取中…</div>;
  if (error) return <ErrorNote error={error} />;

  return (
    <>
      <div className="page-head">
        <h1>内容发布</h1>
        <p>草稿 → 校验 → 预览 → 发布 → 撤下 / 回退。每次发布是一个不可变版本。</p>
      </div>

      <div className="card">
        <h2>内容类型<small>每一种都有明确的玩家侧消费方，没有空菜单</small></h2>
        <table>
          <thead><tr><th>类型</th><th>形态</th><th>玩家侧谁在读</th><th>可发布</th><th>不可发布</th></tr></thead>
          <tbody>
            {(data?.types ?? []).map((type) => (
              <tr key={type.content_type}>
                <td>{type.label}<Code value={type.content_type} /></td>
                <td><Pill tone="muted">{KIND_LABEL[type.kind] ?? type.kind}</Pill></td>
                <td style={{ maxWidth: 320 }}>{type.consumer}{type.consumer_api && <Tech>{type.consumer_api}</Tech>}</td>
                <td>{type.publishable.map((f) => <Pill key={f} tone="ok"><FieldName field={f} /></Pill>)}</td>
                <td>{type.blocked.length === 0 ? "—" : type.blocked.map((f) => <Pill key={f} tone="danger"><FieldName field={f} /></Pill>)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>玩家端此刻读到的公告<small>直接读玩家网页那一侧的公告，不是后台自己算的<Tech>GET /api/v1/web/announcements</Tech></small></h2>
        {player.loading ? <div className="empty">读取中…</div>
          : player.error ? <ErrorNote error={player.error} />
          : (player.data?.announcements.length ?? 0) === 0 ? <div className="empty">玩家端此刻没有公告。</div> : (
            <table>
              <thead><tr><th>标题</th><th>正文</th><th>版本</th><th>生效</th></tr></thead>
              <tbody>
                {player.data!.announcements.map((item: PlayerAnnouncement) => (
                  <tr key={item.item_id}>
                    <td>{item.title}</td>
                    <td style={{ maxWidth: 420 }}>{item.body}</td>
                    <td><Pill tone="ok">v{item.revision}</Pill></td>
                    <td>{when(item.effective_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </div>

      <div className="card">
        <h2>全部内容<small>{data?.items.length ?? 0} 条</small></h2>
        <div className="card-body">
          {canEdit ? <button className="primary" onClick={() => setCreating(true)}>新建草稿</button>
            : <span className="pill muted">需要「<PermissionName code="content.edit" />」权限</span>}
        </div>
        {(data?.items.length ?? 0) === 0 ? <div className="empty">还没有任何内容。</div> : (
          <table>
            <thead><tr><th>标题</th><th>类型</th><th>状态</th><th>已发布</th><th>草稿</th><th>最近更新</th></tr></thead>
            <tbody>
              {data!.items.map((item) => (
                <tr key={item.item_id}>
                  <td><Link to={`/content/${item.item_id}`}>{item.title}</Link>
                    <Code value={item.slug} /></td>
                  <td>{data!.types.find((t) => t.content_type === item.content_type)?.label ?? item.content_type}</td>
                  <td>{item.status === "published" ? <Pill tone="ok">已发布</Pill>
                    : item.status === "withdrawn" ? <Pill tone="warn">已撤下</Pill> : <Pill tone="muted">草稿</Pill>}</td>
                  <td>{item.live_revision ? `v${item.live_revision}` : "—"}</td>
                  <td>{item.draft_revision ? `v${item.draft_revision}` : "—"}</td>
                  <td>{when(item.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {creating && (
        <CreateDialog types={data?.types ?? []} presetResident={preset}
                      onClose={() => { setCreating(false); setParams({}); }}
                      onDone={() => { setCreating(false); setParams({}); reload(); }} />
      )}
    </>
  );
}

function CreateDialog({ types, presetResident, onClose, onDone }: {
  types: ContentTypeInfo[]; presetResident?: string | null; onClose: () => void; onDone: () => void;
}) {
  const [type, setType] = useState<ContentType>(presetResident ? "resident" : "announcement");
  const [slug, setSlug] = useState(() => (presetResident ? "" : autoSlug()));
  const [presetUsed, setPresetUsed] = useState(false);
  const { on: tech } = useTech();
  const [body, setBody] = useState<Body>({ ...EMPTY_BODY.announcement });
  const [sources, setSources] = useState<ContentSource[] | null>(null);
  const [issues, setIssues] = useState<ValidationIssue[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const info = types.find((t) => t.content_type === type);
  const needsSource = info?.kind === "overlay" || info?.kind === "table";

  useEffect(() => {
    setSources(null);
    if (!needsSource) return;
    let alive = true;
    api.get<{ sources: ContentSource[] }>(`/content-sources/${type}`)
      .then((payload) => { if (alive) setSources(payload.sources); })
      .catch((exc) => { if (alive) setError(exc); });
    return () => { alive = false; };
  }, [type, needsSource]);

  const switchType = (next: ContentType) => {
    setType(next);
    setSlug(next === "announcement" ? autoSlug() : "");
    setBody({ ...EMPTY_BODY[next] });
    setIssues(null);
  };

  /** 选中一个内置条目：把它**当前的值**填进草稿，运营在这个基础上改，差异一眼可见。 */
  const pickSource = (picked: string) => {
    setSlug(picked);
    const source = sources?.find((s) => s.slug === picked);
    setBody(source ? { ...(source.builtin as Body) } : { ...EMPTY_BODY[type] });
    setIssues(null);
  };

  // 从居民页带过来的居民：条目一读到就选中它，正文填它现在的文案
  useEffect(() => {
    if (!presetResident || presetUsed || sources === null || type !== "resident") return;
    setPresetUsed(true);
    if (sources.some((s) => s.slug === presetResident)) pickSource(presetResident);
  }, [presetResident, presetUsed, sources, type]); // eslint-disable-line react-hooks/exhaustive-deps

  const set = (key: string, value: unknown) => setBody((current) => ({ ...current, [key]: value }));

  const validate = async () => {
    setBusy(true); setError(null);
    try {
      const result = await api.post<{ ok: boolean; issues: ValidationIssue[] }>("/content/validate",
        { content_type: type, slug: slug || "draft", title: String(body.title || slug || "草稿"), body });
      setIssues(result.issues);
    } catch (exc) { setError(exc); } finally { setBusy(false); }
  };

  const create = async () => {
    setBusy(true); setError(null);
    try {
      const title = String(body.title || body.label || slug);
      await api.post("/content", { content_type: type, slug: slug.trim(), title, body });
      onDone();
    } catch (exc) { setError(exc); } finally { setBusy(false); }
  };

  return (
    <div className="overlay">
      <div className="dialog">
        <h2>新建草稿</h2>
        <div className="dialog-body">
          <ErrorNote error={error} />
          {issues && (issues.length === 0
            ? <div className="note ok">校验通过，可以保存草稿。</div>
            : <div className="note warn"><strong>这一版还不能发布：</strong>
                <ul className="effects">{issues.map((i) => <li key={i.field + i.message}><FieldName field={i.field} />：{i.message}</li>)}</ul></div>)}
          <div className="field">
            <label>类型</label>
            <select value={type} onChange={(e) => switchType(e.target.value as ContentType)}>
              {types.map((t) => <option key={t.content_type} value={t.content_type}>{t.label}</option>)}
            </select>
            {info && <div style={{ color: "var(--ink-faint)", fontSize: 12, marginTop: 4 }}>玩家侧：{info.consumer}{info.consumer_api && <Tech>{info.consumer_api}</Tech>}</div>}
          </div>

          {needsSource ? (
            <div className="field">
              <label>{info?.kind === "table" ? "选一位还没被领养的居民" : "选一个已有条目（只能给它发新版本）"}</label>
              {sources === null ? <div className="empty">读取中…</div> : (
                <select value={slug} onChange={(e) => pickSource(e.target.value)}>
                  <option value="">请选择…</option>
                  {sources.map((source) => (
                    <option key={source.slug} value={source.slug}>
                      {(source.name ?? source.identity?.name ?? source.slug) + (tech ? `（${source.slug}）` : "")}
                    </option>
                  ))}
                </select>
              )}
            </div>
          ) : (
            <div className="field">
              <label>内部标识（玩家看不到，只用来区分每条公告；已自动生成，想改可以改）</label>
              <input value={slug} onChange={(e) => setSlug(e.target.value)} />
            </div>
          )}

          {(!needsSource || slug) && (
            <ContentBodyForm contentType={type} body={body} info={info} onChange={set} />
          )}
        </div>
        <div className="dialog-foot">
          <button className="ghost" onClick={onClose} disabled={busy}>取消</button>
          <button onClick={validate} disabled={busy || !slug.trim()}>校验</button>
          <button className="primary" onClick={create} disabled={busy || !slug.trim()}>保存草稿</button>
        </div>
      </div>
    </div>
  );
}
