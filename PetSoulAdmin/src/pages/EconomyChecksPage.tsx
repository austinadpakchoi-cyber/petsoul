/**
 * 经济对账：只读。判据与领域自己重建钱包的方式同口径（余额＝从 0 起全部 committed 流水之和），
 * 另查流水首尾相接、单条自洽、负余额，以及短时间内的重复人工补偿（需要人判断，不算错）。
 *
 * 这一页**没有「修复」按钮**：纠错要走冲正或补偿（新的一条流水），不在后台里重建或覆盖余额——
 * 那会把差额连同证据一起抹掉。重复补偿旁边的「冲正这一笔」就是这样一条新流水（整笔、一次、不能冲自己发的），
 * 原补偿保留；它只对后台发出的补偿开放，对「余额与流水对不上」这类差额没有入口。
 */
import { useState } from "react";
import { Link } from "react-router";
import { api } from "../api/client";
import type { EconomyChecksView, EconomyFinding, SessionView } from "../api/types";
import { ReversalDialog } from "../components/ReversalDialog";
import { ErrorNote, Pill, useAsync, when } from "../components/ui";
import { Code, Staff, Term } from "../labels";

const SEVERITY: Record<EconomyFinding["severity"], { tone: "danger" | "warn" | "unknown"; label: string; heading: string }> = {
  error: { tone: "danger", label: "错误", heading: "账目对不上" },
  warn: { tone: "warn", label: "需留意", heading: "流水之间接不上" },
  review: { tone: "unknown", label: "需要人判断", heading: "短时间内的重复人工补偿" },
};

export default function EconomyChecksPage({ session }: { session: SessionView }) {
  const { data, error, loading, reload } = useAsync(() => api.get<EconomyChecksView>("/economy/checks"), []);
  const [reversing, setReversing] = useState<string | null>(null);
  const canReverse = session.staff.permissions.includes("economy.reverse");
  if (loading) return <div className="empty">对账中…</div>;
  if (error) return <ErrorNote error={error} />;
  if (!data) return null;
  const groups = (["error", "warn", "review"] as const).map((severity) => ({
    severity, items: data.findings.filter((f) => f.severity === severity),
  }));

  return (
    <>
      <div className="page-head">
        <h1>经济对账</h1>
        <p>只读：{when(data.as_of)} 对了 {data.checked_pets} 只宠物、{data.checked_entries} 条流水。</p>
        <button className="ghost" onClick={reload}>重新对一次</button>
      </div>

      <div className="card">
        <div className="card-body">
          <div className={`note ${data.pets_with_errors > 0 ? "danger" : "ok"}`}>
            {data.pets_with_errors > 0 ? `${data.pets_with_errors} 只宠物的账对不上。` : "没有账目对不上的宠物。"}
            {" "}{data.note}
          </div>
          <ul className="effects">
            {Object.entries(data.rules).map(([kind, rule]) => <li key={kind}>{rule}<Code value={kind} /></li>)}
          </ul>
          <div className="note plain">
            {data.scale_note}
            {data.unchained_entries > 0 && ` 另有 ${data.unchained_entries} 条流水没有记 before/after，链条在那里断开、不硬比。`}
            {Object.keys(data.non_committed_entries).length > 0 &&
              ` 非 committed 的流水（不计入余额）：${Object.entries(data.non_committed_entries).map(([s, n]) => `${s} ${n}`).join("，")}。`}
          </div>
        </div>
      </div>

      {groups.map(({ severity, items }) => (
        <div className="card" key={severity}>
          <h2>{SEVERITY[severity].heading}<small>{items.length} 条 · {SEVERITY[severity].label}</small></h2>
          {items.length === 0 ? <div className="empty">没有。</div> : (
            <table>
              <thead><tr><th>宠物</th><th>发现</th><th>依据</th></tr></thead>
              <tbody>
                {items.map((finding, index) => (
                  <tr key={`${finding.pet_id}:${finding.kind}:${index}`}>
                    <td><Link to={`/pets/${finding.pet_id}`}>{finding.pet_name ?? finding.pet_id}</Link>
                      <Code value={finding.pet_id} /></td>
                    <td><Pill tone={SEVERITY[finding.severity].tone}><Term family="finding_kind" code={finding.kind} /></Pill>
                      <div style={{ marginTop: 4 }}>{finding.title}</div>
                      <FindingDetails finding={finding} canReverse={canReverse} onReverse={setReversing} /></td>
                    <td style={{ color: "var(--ink-soft)", fontSize: 12.5, maxWidth: 320 }}>{finding.rule}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ))}

      {reversing && <ReversalDialog txId={reversing} onClose={() => setReversing(null)}
                                    onDone={() => { setReversing(null); reload(); }} />}
    </>
  );
}

/** 把最有用的几个事实摆出来：差额出在哪两条流水之间、最后一条之后又变了多少、重复补偿各是谁发的。 */
function FindingDetails({ finding, canReverse, onReverse }: { finding: EconomyFinding; canReverse: boolean;
                                                          onReverse: (txId: string) => void }) {
  const d = finding.details as Record<string, any>;
  if (finding.kind === "balance_mismatch" && d.first_gap) {
    return <div className="mono" style={{ fontSize: 11.5, marginTop: 4 }}>
      首次接不上：{d.first_gap.after_tx} 之后是 {d.first_gap.expected_before}，{d.first_gap.before_tx} 读到 {d.first_gap.found_before}
      （{d.first_gap.delta > 0 ? "+" : ""}{d.first_gap.delta}）</div>;
  }
  if (finding.kind === "balance_mismatch" && d.after_last_entry) {
    return <div className="mono" style={{ fontSize: 11.5, marginTop: 4 }}>
      最后一条 {d.after_last_entry.tx_id} 之后是 {d.after_last_entry.after}，现在余额 {d.after_last_entry.wallet_now}</div>;
  }
  if (finding.kind === "repeated_admin_compensation" && Array.isArray(d.entries)) {
    return (
      <ul className="effects" style={{ marginTop: 4 }}>
        {d.entries.map((e: Record<string, any>) => (
          <li key={e.tx_id}>{when(e.created_at)} · +{e.amount} · <Staff id={e.operator} /> · {e.internal_reason ?? "（内部原因找不到）"}
            <span style={{ color: "var(--ink-faint)" }}>（玩家看到：{e.reason}）</span>
            {canReverse && <button className="ghost" style={{ marginLeft: 8 }} onClick={() => onReverse(e.tx_id)}>冲正这一笔</button>}</li>
        ))}
      </ul>
    );
  }
  return null;
}
