import { Link } from "react-router";
import { api } from "../api/client";
import type { LedgerView, UsageView } from "../api/types";
import { CostCell } from "../components/costs";
import { ErrorNote, Pill, useAsync, when } from "../components/ui";
import { Code, Staff, Tech, Term } from "../labels";

const TONE: Record<string, "ok" | "warn" | "danger" | "unknown" | "muted"> = {
  settled: "ok", released: "muted", reserved: "warn", unknown: "unknown", expired: "unknown",
};

/** 两本账并排放，但**没有任何换算**：上面是平台 API 调用（按次数记），下面是游戏星币。 */
export default function LedgersPage() {
  const usage = useAsync(() => api.get<UsageView>("/providers/usage"), []);
  const ledger = useAsync(() => api.get<LedgerView>("/economy/ledger"), []);

  return (
    <>
      <div className="page-head">
        <h1>两本账</h1>
        <p>平台 API 调用与游戏星币完全分开记，两者之间没有兑换关系。</p>
      </div>

      <div className="card">
        <h2>平台 API 调用账<small>{usage.data?.accounting_window}（UTC 当天）· 按调用次数记<Code value={usage.data?.unit} /></small></h2>
        {usage.error ? <ErrorNote error={usage.error} /> : usage.loading ? <div className="empty">读取中…</div> : (
          <>
            <div className="card-body"><div className="note plain">{usage.data!.cost_note} <Link to="/costs">看价格表与区间估算</Link>；按天看生了多少张图：<Link to="/photos">照片与任务</Link></div></div>
            {usage.data!.lines.length === 0 ? <div className="empty">今天还没有调用。</div> : (
              <table>
                <thead><tr><th>做什么用的</th><th className="num">已用次数</th><th className="num">还在途</th><th>估算费用</th><th>账单确认费用</th></tr></thead>
                <tbody>
                  {usage.data!.lines.map((line) => (
                    <tr key={`${line.provider}:${line.purpose}`}>
                      <td><Term family="purpose" code={line.purpose} /><div className="hint"><Term family="provider" code={line.provider} /></div></td>
                      <td className="num">{line.used_units}</td>
                      <td className="num">{line.inflight_units}</td>
                      <td><CostCell state={line.cost_state} costs={line.estimated_cost} /></td>
                      <td>{line.billed_cost === null ? <Pill tone="unknown">未确认</Pill> : line.billed_cost}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <div className="card-body">
              <div className="note plain">{usage.data!.window_note}</div>
              <StatusChips title="今天的调用，按结果分" counts={usage.data!.reservations_by_status} empty="今天还没有调用记录。" />
              <StatusChips title="不分日期，全部调用按结果分" counts={usage.data!.reservations_all_time_by_status} empty="还没有任何调用记录。" />
            </div>
          </>
        )}
      </div>

      <div className="card">
        <h2>还没结清的调用<small>还没结果、结果未确认、占着的额度过期了 · 不分日期</small></h2>
        {usage.error ? null : usage.loading ? <div className="empty">读取中…</div>
          : (usage.data!.unsettled.length === 0 ? <div className="empty">没有还没结清的调用。</div> : (
            <>
              <div className="card-body">
                <div className="note warn">
                  这些调用<strong>很可能已经发出去了</strong>，只是结果没确认。不是失败，也不是没发送：后台不会自动重发，
                  也不会抹掉计量。要处理请先向供应商核对。
                </div>
              </div>
              <table>
                <thead><tr><th>做什么用的</th><th>结果</th><th className="num">计入次数</th><th>记在哪天</th><th>发起时间</th></tr></thead>
                <tbody>
                  {usage.data!.unsettled.map((row) => (
                    <tr key={row.operation_id}>
                      <td><Term family="purpose" code={row.purpose} /><div className="hint"><Term family="provider" code={row.provider} /></div>
                        <Tech>操作号 {row.operation_id}</Tech></td>
                      <td><Pill tone={TONE[row.status] ?? "unknown"}><Term family="reservation_status" code={row.status} /></Pill></td>
                      <td className="num">{row.counted_units ?? "还在途"}</td>
                      <td>{row.accounting_window}</td>
                      <td>{when(row.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ))}
      </div>

      <div className="card">
        <h2>游戏星币账<small>{ledger.data?.currency}</small></h2>
        {ledger.error ? <ErrorNote error={ledger.error} /> : ledger.loading ? <div className="empty">读取中…</div> : (
          <>
            <div className="card-body"><div className="note plain">{ledger.data!.separation_note}</div></div>
            {ledger.data!.transactions.length === 0 ? <div className="empty">还没有星币流水。</div> : (
              <table>
                <thead><tr><th>时间</th><th>宠物</th><th className="num">星币</th><th>怎么来的</th><th>说明（玩家在银行卡上看得到）</th><th>谁的操作</th></tr></thead>
                <tbody>
                  {ledger.data!.transactions.map((tx) => (
                    <tr key={tx.tx_id}>
                      <td>{when(tx.created_at)}<Code value={tx.tx_id} /></td>
                      <td><Link to={`/pets/${tx.pet_id}`}>打开宠物</Link><Code value={tx.pet_id} /></td>
                      <td className="num">{tx.travel_coin > 0 ? `+${tx.travel_coin}` : tx.travel_coin}</td>
                      <td><Term family="ledger_source" code={tx.source} /><div className="hint"><Term family="ledger_type" code={tx.type} /></div></td>
                      <td>{tx.reason || "—"}</td>
                      <td><Staff id={tx.operator} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </div>
    </>
  );
}

function StatusChips({ title, counts, empty }: { title: string; counts: Record<string, number>; empty: string }) {
  const entries = Object.entries(counts);
  return (
    <>
      <h3 style={{ fontSize: 13, margin: "12px 0 6px" }}>{title}</h3>
      <div className="actions">
        {entries.length === 0 ? <span className="hint">{empty}</span> : entries.map(([status, count]) => (
          <Pill key={status} tone={TONE[status] ?? "unknown"}><Term family="reservation_status" code={status} /> {count}</Pill>
        ))}
      </div>
    </>
  );
}
