/**
 * 用户详情页的「两本账汇总」：这位用户名下每只宠物一行。两段各要各的权限（economy.read / provider.read），
 * 后端只给有权限的那几段——前端不猜，也不把没有的段显示成 0。
 */
import { Link } from "react-router";
import { api } from "../api/client";
import type { UserLedgerSummary as Summary } from "../api/types";
import { CostCell } from "../components/costs";
import { ErrorNote, Pill, useAsync, when } from "../components/ui";
import { Code, Term } from "../labels";

export function UserLedgerSummary({ userId }: { userId: string }) {
  const { data, error, loading } = useAsync(
    () => api.get<Summary>(`/users/${encodeURIComponent(userId)}/ledger-summary`), [userId]);
  return (
    <div className="card">
      <h2>两本账汇总<small>星币与平台调用各记各的，没有兑换关系</small></h2>
      {loading ? <div className="empty">读取中…</div> : error ? <div className="card-body"><ErrorNote error={error} /></div>
        : !data || data.pets.length === 0 ? <div className="empty">这位用户名下没有宠物。</div> : (
          <>
            <table>
              <thead>
                <tr>
                  <th>宠物</th>
                  {data.sections.economy && <><th className="num">星币余额</th><th className="num">流水</th><th>后台补偿</th></>}
                  {data.sections.calls && <><th>调用（按状态）</th><th className="num">计入用量</th><th>估算费用</th></>}
                </tr>
              </thead>
              <tbody>
                {data.pets.map((pet) => (
                  <tr key={pet.pet_id}>
                    <td><Link to={`/pets/${pet.pet_id}`}>{pet.name}</Link>
                      <Code value={pet.pet_id} /></td>
                    {data.sections.economy && pet.economy && (
                      <>
                        <td className="num">{pet.economy.balance ?? <span style={{ color: "var(--ink-faint)" }}>没有钱包</span>}</td>
                        <td className="num">{pet.economy.entries}
                          {pet.economy.last_entry_at && <div style={{ color: "var(--ink-faint)", fontSize: 11 }}>{when(pet.economy.last_entry_at)}</div>}</td>
                        <td>{pet.economy.admin_compensations === 0 ? "—"
                          : `${pet.economy.admin_compensations} 笔 · +${pet.economy.admin_compensated_coins}`}</td>
                      </>
                    )}
                    {data.sections.calls && pet.calls && (
                      <>
                        <td>
                          {Object.keys(pet.calls.reservations_by_status).length === 0 ? "—"
                            : Object.entries(pet.calls.reservations_by_status).map(([status, n]) => (
                              <Pill key={status} tone={status === "settled" ? "ok" : status === "released" ? "muted" : status === "reserved" ? "warn" : "unknown"}>
                                <Term family="reservation_status" code={status} /> {n}</Pill>))}
                        </td>
                        <td className="num">{pet.calls.counted_units}</td>
                        <td><CostCell state={pet.calls.cost_state} costs={pet.calls.estimated_cost} /></td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="card-body">
              <ul className="effects">{Object.entries(data.notes).map(([key, text]) => <li key={key}>{text}</li>)}</ul>
            </div>
          </>
        )}
    </div>
  );
}
