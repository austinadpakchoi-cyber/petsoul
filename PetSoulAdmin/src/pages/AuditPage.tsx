import { useState } from "react";
import { Link } from "react-router";
import { api } from "../api/client";
import type { AuditEntry } from "../api/types";
import { ErrorNote, Pill, useAsync, when } from "../components/ui";
import { Code, Tech, Term, useFamily, useLabel } from "../labels";

const TONE: Record<string, "ok" | "warn" | "danger" | "muted"> = {
  succeeded: "ok", replayed: "muted", allowed: "muted", denied: "danger", failed: "warn",
};
// 对象能直接打开的几种：点进去看
const TARGET_LINK: Record<string, (id: string) => string> = {
  user: (id) => `/users/${id}`, pet: (id) => `/pets/${id}`, home: (id) => `/homes/${id}`,
};

/** 操作记录：谁、做了什么、对什么、为什么、结果怎样。仅追加。变更细节默认收起。 */
export default function AuditPage() {
  const lookup = useLabel();
  const [filters, setFilters] = useState({ actor: "", action: "", target_id: "", status: "" });
  const [applied, setApplied] = useState(filters);
  const query = Object.entries(applied).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&");
  const { data, error, loading } = useAsync(
    () => api.get<{ entries: AuditEntry[]; total: number; note: string }>(`/audit${query ? `?${query}` : ""}`), [query]);

  return (
    <>
      <div className="page-head">
        <h1>操作记录</h1>
        <p>谁、做了什么、对什么、为什么、结果怎样。只能追加，不能改也不能删。</p>
      </div>

      <div className="card">
        <div className="card-body">
          <form className="row" onSubmit={(e) => { e.preventDefault(); setApplied(filters); }}>
            <div><label>谁做的</label><input value={filters.actor} onChange={(e) => setFilters({ ...filters, actor: e.target.value })} placeholder="员工用户名" /></div>
            <div><label>做了什么</label>
              <ActionSelect value={filters.action} onChange={(action) => setFilters({ ...filters, action })} /></div>
            <div><label>对象编号</label><input value={filters.target_id} onChange={(e) => setFilters({ ...filters, target_id: e.target.value })} placeholder="用户 / 宠物 / 家的编号" /></div>
            <div><label>结果</label>
              <select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}>
                <option value="">全部</option>
                {["succeeded", "denied", "allowed", "failed", "replayed"].map((code) => (
                  <option key={code} value={code}>{lookup("audit_status", code) ?? code}</option>))}
              </select></div>
            <div style={{ flex: 0, minWidth: 90 }}><button className="primary" type="submit">筛选</button></div>
          </form>
        </div>
      </div>

      <ErrorNote error={error} />
      <div className="card">
        <h2>记录<small>{data?.total ?? 0} 条</small></h2>
        {loading ? <div className="empty">读取中…</div>
          : (data?.entries.length ?? 0) === 0 ? <div className="empty">没有符合条件的记录。</div> : (
            <table>
              <thead><tr><th>时间</th><th>谁</th><th>做了什么</th><th>对什么</th><th>为什么</th><th>结果</th><th>细节</th></tr></thead>
              <tbody>
                {data!.entries.map((entry) => (
                  <tr key={entry.audit_id}>
                    <td>{when(entry.occurred_at)}</td>
                    <td>{entry.actor_username ?? "—"}<Code value={entry.actor_staff_id} /></td>
                    <td><AuditAction action={entry.action} />
                      {entry.permission && <div className="hint">凭「<Term family="permission" code={entry.permission.split("|")[0]} />」权限</div>}</td>
                    <td><Target kind={entry.target_kind} id={entry.target_id} /></td>
                    <td style={{ maxWidth: 220 }}>{entry.reason ?? "—"}</td>
                    <td><Pill tone={TONE[entry.status] ?? "muted"}><Term family="audit_status" code={entry.status} /></Pill>
                      {entry.outcome && <Outcome value={entry.outcome} />}</td>
                    <td style={{ maxWidth: 280 }}>
                      {entry.changes ? (
                        <details>
                          <summary>看细节</summary>
                          <dl className="kv" style={{ fontSize: 12 }}>
                            {Object.entries(entry.changes).map(([key, value]) => (
                              <div key={key} style={{ display: "contents" }}>
                                <dt>{key}</dt><dd>{typeof value === "object" ? JSON.stringify(value) : String(value)}</dd>
                              </div>
                            ))}
                          </dl>
                        </details>
                      ) : "—"}
                      <Tech>{entry.audit_id}{entry.operation_id ? ` · 操作号 ${entry.operation_id}` : ""}{entry.request_id ? ` · ${entry.request_id}` : ""}</Tech>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        {data?.note && <div className="card-body"><div className="note plain">{data.note}</div></div>}
      </div>
    </>
  );
}

/** 「做了什么」下拉：按词表列出所有动作（中文），按前缀分组；选中的就是精确的动作代码。 */
function ActionSelect({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const actions = useFamily("audit_action");
  const codes = Object.keys(actions);
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">全部</option>
      {Object.entries(ACTION_GROUPS).map(([prefix, title]) => {
        const inGroup = codes.filter((code) => code.startsWith(prefix));
        return inGroup.length === 0 ? null : (
          <optgroup key={prefix} label={title}>
            {inGroup.map((code) => <option key={code} value={code}>{actions[code]}</option>)}
          </optgroup>
        );
      })}
    </select>
  );
}

// 下拉里的分组（按动作代码的前缀）
const ACTION_GROUPS: Record<string, string> = {
  "user.": "查看用户", "pet.": "查看宠物", "home.": "查看家", "photo.": "照片", "report.": "举报",
  "account.": "账号处置", "provider.": "AI 调用开关", "task.": "任务恢复", "economy.": "游戏经济",
  "content.": "内容", "asset.": "素材", "cost.": "平台成本", "staff.": "员工",
};

function AuditAction({ action }: { action: string }) {
  if (action.startsWith("denied:")) {
    return <span title={action}>没有权限、被挡下的请求<Tech>{action.slice("denied:".length)}</Tech></span>;
  }
  return <Term family="audit_action" code={action} />;
}

function Target({ kind, id }: { kind: string | null; id: string | null }) {
  if (!kind) return <>—</>;
  const link = id && TARGET_LINK[kind] ? TARGET_LINK[kind](id) : null;
  return (
    <span>
      <Term family="target_kind" code={kind} />
      {id && (link ? <> · <Link to={link}>打开</Link></> : kind === "query" ? <> · 「{id}」</> : null)}
      <Code value={id} />
    </span>
  );
}

/** 结果补充：以数字或正负号开头（「+20」）、或本来就是中文的直接显示；「self_reversal」「v3」这种代码收进技术代码。 */
function Outcome({ value }: { value: string }) {
  const readable = /^[+\-]?\d/.test(value) || /[^\x00-\x7f]/.test(value);
  return readable ? <div style={{ fontSize: 12 }}>{value}</div> : <Tech>{value}</Tech>;
}
