import { useState } from "react";
import { api } from "../api/client";
import type { ReportRow, SessionView } from "../api/types";
import { Player } from "../components/player";
import { ErrorNote, Pill, ReasonDialog, useAsync, when, type ConfirmSpec } from "../components/ui";
import { Code, PermissionName, Term } from "../labels";

export default function ReportsPage({ session }: { session: SessionView }) {
  const [onlyOpen, setOnlyOpen] = useState(true);
  const { data, error, loading, reload } = useAsync(
    () => api.get<{ reports: ReportRow[]; note: string }>(`/reports?only_open=${onlyOpen}`), [onlyOpen]);
  const [dialog, setDialog] = useState<ConfirmSpec | null>(null);
  const canAct = session.staff.permissions.includes("report.action");
  const [claimError, setClaimError] = useState<unknown>(null);
  const claim = async (row: ReportRow, release = false) => {
    setClaimError(null);
    try { await api.post(release ? "/reports/release" : "/reports/claim", { target_kind: row.target_kind, target_id: row.target_id }); reload(); }
    catch (exc) { setClaimError(exc); reload(); }
  };

  if (loading) return <div className="empty">读取中…</div>;
  if (error) return <ErrorNote error={error} />;
  const reports = data?.reports ?? [];

  const act = (row: ReportRow, decision: "takedown" | "restore" | "dismiss") => setDialog({
    title: { takedown: "下架这条公开内容", restore: "恢复这条公开内容", dismiss: "记为不处理" }[decision],
    danger: decision === "takedown",
    confirmLabel: { takedown: "下架", restore: "恢复", dismiss: "不处理" }[decision],
    placeholder: { takedown: "例如：内容含人身攻击，违反社区规范", restore: "例如：复核后没有违规，恢复公开",
                   dismiss: "例如：只是观点不同，不构成违规" }[decision],
    effects: decision === "dismiss"
      ? ["只记一条处理结果，内容可见性不变。"]
      : ["只改公开可见性，不做硬删除。", "举报记录与原文都保留，作为审计依据。", "处理结果会写进审计。"],
    run: (reason, op) => api.post("/moderation", {
      report_id: row.report_id, target_kind: row.target_kind, target_id: row.target_id, decision, reason,
    }, op),
  });

  return (
    <>
      <div className="page-head">
        <h1>举报审核</h1>
        <p>{data?.note}</p>
      </div>

      <div className="card">
        <div className="card-body">
          <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
            <input type="checkbox" checked={onlyOpen} onChange={(e) => setOnlyOpen(e.target.checked)} style={{ width: "auto" }} />
            只看还没处理的
          </label>
        </div>
      </div>

      <ErrorNote error={claimError} />

      <div className="card">
        <h2>队列<small>{reports.length} 条 · 认领 30 分钟，处理完自动结束</small></h2>
        {reports.length === 0 ? <div className="empty">{onlyOpen ? "没有待处理的举报。" : "还没有举报记录。"}</div> : (
          <table>
            <thead><tr><th>举报</th><th>内容</th><th>谁举报了谁</th><th>时间</th><th>处理</th></tr></thead>
            <tbody>
              {reports.map((row) => (
                <tr key={row.report_id}>
                  <td>
                    <Pill tone={row.handled ? "muted" : "warn"}>{row.handled ? "已处理" : "待处理"}</Pill>
                    <div style={{ marginTop: 4 }}>{row.reason}</div>
                    <div className="hint"><Term family="target_kind" code={row.target_kind} /><Code value={row.target_id} /></div>
                  </td>
                  <td style={{ maxWidth: 360 }}>
                    {row.target?.text ?? <span style={{ color: "var(--ink-faint)" }}>{row.target?.note ?? "内容已不存在"}</span>}
                    {row.target?.visibility && (
                      <div style={{ marginTop: 4 }}>
                        <Pill tone={row.target.visibility === "removed" ? "danger" : "ok"}>
                          {row.target.visibility === "removed" ? "已下架" : "公开中"}
                        </Pill>
                      </div>
                    )}
                    {row.actions.length > 0 && (
                      <div style={{ marginTop: 6, fontSize: 12, color: "var(--ink-soft)" }}>
                        最近处理：<Term family="report_decision" code={row.actions[0].decision} /> · {row.actions[0].reason}（{when(row.actions[0].created_at)}）
                      </div>
                    )}
                  </td>
                  <td style={{ maxWidth: 300 }}><Relation row={row} /></td>
                  <td>{when(row.created_at)}</td>
                  <td>
                    {row.claim && (
                      <div style={{ marginBottom: 6 }}>
                        <Pill tone={row.claim.mine ? "ok" : "warn"}>{row.claim.mine ? "我认领的" : `${row.claim.username ?? "别人"} 处理中`}</Pill>
                        <div style={{ fontSize: 11.5, color: "var(--ink-faint)" }}>到 {when(row.claim.expires_at)}</div>
                      </div>
                    )}
                    {canAct && row.claim && !row.claim.mine ? (
                      <span className="pill muted">别人认领着，过期后可以接手</span>
                    ) : canAct ? (
                      <div className="actions">
                        {!row.handled && (row.claim?.mine
                          ? <button className="ghost" onClick={() => void claim(row, true)}>放弃认领</button>
                          : <button onClick={() => void claim(row)}>认领</button>)}
                        {row.target?.visibility === "removed"
                          ? <button onClick={() => act(row, "restore")}>恢复</button>
                          : <button className="danger" onClick={() => act(row, "takedown")}>下架</button>}
                        <button className="ghost" onClick={() => act(row, "dismiss")}>不处理</button>
                      </div>
                    ) : <span className="pill muted">需要「<PermissionName code="report.action" />」权限</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {dialog && <ReasonDialog spec={dialog} onClose={() => setDialog(null)} onDone={reload} />}
    </>
  );
}

/** 举报人与被举报的人：名字、两人之间有没有拉黑、各自的举报记录（只给次数，不给任何一方的私人内容）。 */
function Relation({ row }: { row: ReportRow }) {
  const c = row.context;
  return (
    <>
      <div>举报人：<Player id={row.reporter_user_id} name={row.reporter_name} /></div>
      {c ? (
        <>
          <div>被举报：<Player id={c.author_user_id} name={c.author_name} /></div>
          {(c.same_person || c.reporter_blocked_author || c.author_blocked_reporter) && (
            <div style={{ marginTop: 4 }}>
              {c.same_person && <Pill tone="muted">举报的是自己的内容</Pill>}{" "}
              {c.reporter_blocked_author && <Pill tone="warn">举报人已经拉黑了对方</Pill>}{" "}
              {c.author_blocked_reporter && <Pill tone="warn">对方拉黑了举报人</Pill>}
            </div>
          )}
          <div className="hint" style={{ marginTop: 4 }}>
            被举报的人：内容一共被举报过 {c.reports_against_author} 次，被下架过 {c.author_removed} 条。
            举报人：一共举报过 {c.reporter_filed} 次。
          </div>
        </>
      ) : <div className="hint">查不到被举报的人（内容可能已不存在）。</div>}
    </>
  );
}
