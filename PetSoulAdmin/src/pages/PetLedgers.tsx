/**
 * 宠物页下方的"两本账"：游戏账本（星币）与平台调用账（调用次数）。
 *
 * 两个标签、两条权限（economy.read / provider.read）、两套单位，**没有任何换算**。
 * 单笔补偿从这里发起（方案 §7 工作流 #4）：看影响 → 写原因 → 发放 → 在同一个标签里看到那一条入账；
 * 切到另一个标签，调用账一条没多。
 */
import { useEffect, useState } from "react";
import { api, newOperationId, outcomeUnknown } from "../api/client";
import type { GrantPreview, GrantResult, LedgerView, PetCallsView } from "../api/types";
import { RowCost } from "../components/costs";
import { ReversalDialog } from "../components/ReversalDialog";
import { ErrorNote, PendingOutcomeNote, Pill, useAsync, when } from "../components/ui";
import { Code, Staff, Tech, Term, useLabel } from "../labels";

const CALL_STATUS: Record<string, { tone: "ok" | "warn" | "danger" | "unknown" | "muted"; label: string }> = {
  settled: { tone: "ok", label: "已结清" },
  reserved: { tone: "warn", label: "在途" },
  released: { tone: "muted", label: "未发出，已退回" },
  unknown: { tone: "unknown", label: "结果未确认" },
  expired: { tone: "unknown", label: "预占过期（按已用计）" },
};

export function PetLedgers({ petId, permissions }: { petId: string; permissions: string[] }) {
  const canEconomy = permissions.includes("economy.read");
  const canCalls = permissions.includes("provider.read");
  const [tab, setTab] = useState<"economy" | "calls">(canEconomy || !canCalls ? "economy" : "calls");
  return (
    <div className="card">
      <h2>两本账<small>星币与平台调用各记各的，没有兑换关系</small></h2>
      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === "economy"} className={tab === "economy" ? "active" : ""}
                onClick={() => setTab("economy")}>游戏账本（星币）</button>
        <button role="tab" aria-selected={tab === "calls"} className={tab === "calls" ? "active" : ""}
                onClick={() => setTab("calls")}>平台调用账（调用次数）</button>
      </div>
      {tab === "economy"
        ? (canEconomy ? <GameLedger petId={petId} canGrant={permissions.includes("economy.grant")}
                                    canReverse={permissions.includes("economy.reverse")} />
          : <div className="empty">看游戏账本需要「看星币流水与家里的库存」权限。</div>)
        : (canCalls ? <CallLedger petId={petId} />
          : <div className="empty">看平台调用账需要「看调用用量与平台成本」权限。</div>)}
    </div>
  );
}

function GameLedger({ petId, canGrant, canReverse }: { petId: string; canGrant: boolean; canReverse: boolean }) {
  const { data, error, loading, reload } = useAsync(
    () => api.get<LedgerView>(`/economy/ledger?pet_id=${encodeURIComponent(petId)}`), [petId]);
  const [granting, setGranting] = useState(false);
  const [reversing, setReversing] = useState<string | null>(null);
  if (loading) return <div className="empty">读取中…</div>;
  if (error) return <div className="card-body"><ErrorNote error={error} /></div>;
  if (!data) return null;
  const wallet = data.wallets.find((w) => w.pet_id === petId);
  return (
    <>
      <div className="card-body">
        <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
          <span style={{ fontSize: 20, fontWeight: 650 }}>{wallet ? wallet.travel_coin : "—"}</span>
          <span style={{ color: "var(--ink-soft)" }}>{wallet ? "星币余额" : "还没有钱包记录（不是 0，是没有记录）"}</span>
          {wallet?.updated_at && <span style={{ color: "var(--ink-faint)", fontSize: 12 }}>更新于 {when(wallet.updated_at)}</span>}
          <span style={{ marginLeft: "auto" }}>
            {canGrant ? <button className="primary" onClick={() => setGranting(true)}>补偿星币</button>
              : <span className="pill muted">补偿要「单笔补偿星币」权限</span>}
          </span>
        </div>
        <p style={{ color: "var(--ink-faint)", fontSize: 12, margin: "8px 0 0" }}>{data.separation_note}</p>
      </div>
      {data.transactions.length === 0 ? <div className="empty">这只宠物还没有星币流水。</div> : (
        <table>
          <thead><tr><th>时间</th><th className="num">星币</th><th>怎么来的</th><th>谁的操作</th><th>说明（玩家在银行卡上看得到）</th><th /></tr></thead>
          <tbody>
            {data.transactions.map((tx) => (
              <tr key={tx.tx_id}>
                <td>{when(tx.created_at)}</td>
                <td className="num">{tx.travel_coin > 0 ? `+${tx.travel_coin}` : tx.travel_coin}</td>
                <td><Term family="ledger_source" code={tx.source} /><div className="hint"><Term family="ledger_type" code={tx.type} /></div></td>
                <td><Staff id={tx.operator} /></td>
                <td>{tx.reason || "—"}
                  {tx.reversed_by && <div><Pill tone="muted">这一笔已经被冲正</Pill><Code value={tx.reversed_by} /></div>}
                  {tx.reversal_of && <div><Pill tone="warn">这是一笔冲正</Pill><Code value={tx.reversal_of} /></div>}
                  <Tech>{tx.tx_id} · {tx.idempotency_key}</Tech></td>
                <td>{canReverse && tx.admin_compensation && tx.travel_coin > 0 && !tx.reversed_by && (
                  <button className="ghost" onClick={() => setReversing(tx.tx_id)}>冲正</button>)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {granting && <GrantDialog petId={petId} onClose={() => setGranting(false)} onDone={() => { setGranting(false); reload(); }} />}
      {reversing && <ReversalDialog txId={reversing} onClose={() => setReversing(null)}
                                    onDone={() => { setReversing(null); reload(); }} />}
    </>
  );
}

/** 单笔补偿。影响预览必须对应"要提交的这个金额"，改了金额就得重新看；结果没确认时同号重试。 */
function GrantDialog({ petId, onClose, onDone }: { petId: string; onClose: () => void; onDone: () => void }) {
  const [operationId] = useState(() => newOperationId("grant"));
  const [amount, setAmount] = useState(20);
  const [playerNote, setPlayerNote] = useState("");
  const [reason, setReason] = useState("");
  const [preview, setPreview] = useState<GrantPreview | null>(null);
  const [previewError, setPreviewError] = useState<unknown>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<GrantResult | null>(null);

  useEffect(() => {
    let alive = true;
    setPreview(null);
    setPreviewError(null);
    const note = playerNote.trim() ? `&player_note=${encodeURIComponent(playerNote.trim())}` : "";
    api.get<GrantPreview>(`/economy/grant/preview?pet_id=${encodeURIComponent(petId)}&amount=${amount}${note}`)
      .then((value) => { if (alive) setPreview(value); })
      .catch((exc) => { if (alive) setPreviewError(exc); });
    return () => { alive = false; };
  }, [petId, amount, playerNote]);

  const submit = async () => {
    setBusy(true); setError(null);
    try {
      setResult(await api.post<GrantResult>("/economy/grant",
        { pet_id: petId, amount, reason: reason.trim(), player_note: playerNote.trim() || null }, operationId));
      setPending(false);
    } catch (exc) {
      setError(exc);
      if (outcomeUnknown(exc)) setPending(true);
    } finally { setBusy(false); }
  };

  // 预览必须对应要提交的这份内容：金额与玩家说明都对上才能确认
  const previewMatches = preview !== null && preview.amount === amount
    && preview.player_view.reason === (playerNote.trim() ? playerNote.trim().split(/\s+/).join(" ") : "运营补偿");
  return (
    <div className="overlay" role="dialog" aria-modal="true">
      <div className="dialog">
        <h2>补偿星币{preview ? ` · ${preview.pet_name}` : ""}</h2>
        <div className="dialog-body">
          {result ? (
            <>
              <div className={`note ${result.applied && !result.replayed ? "ok" : "info"}`}>
                <strong>{result.replayed ? "这个操作号之前已经入过账" : "已入账"} +{result.amount} 星币</strong>，
                入账后余额 {result.balance}。{result.note}
              </div>
              <Tech>账本幂等键 {result.ledger_key} · 操作号 {operationId}</Tech>
              <p style={{ color: "var(--ink-faint)", fontSize: 12 }}>切到「平台调用账」标签可以核对：调用次数一条没多。</p>
            </>
          ) : (
            <>
              <ErrorNote error={error} />
              {pending && <PendingOutcomeNote operationId={operationId} />}
              <div className="field">
                <label htmlFor="grant-amount">金额（星币，1–{preview?.max_amount ?? 200}）</label>
                <input id="grant-amount" type="number" min={1} max={preview?.max_amount ?? 200} value={amount} readOnly={pending}
                       onChange={(e) => setAmount(Math.trunc(Number(e.target.value)) || 0)} />
              </div>
              <ErrorNote error={previewError} />
              {preview && (
                <>
                  <div className={`note ${preview.caregiver_frozen ? "warn" : "info"}`}>
                    星币余额 {preview.balance_before} → <strong>{preview.balance_after}</strong><Code value={preview.currency} />
                    <div style={{ marginTop: 4 }}>玩家在星球银行卡上会看到：<strong>+{preview.player_view.delta} 星币 · {preview.player_view.reason}</strong></div>
                  </div>
                  <ul className="effects">{preview.effects.map((line) => <li key={line}>{line}</li>)}</ul>
                </>
              )}
              <div className="field">
                <label htmlFor="grant-note">玩家看到的说明（空着就用「运营补偿」，最多 30 字）</label>
                <input id="grant-note" value={playerNote} readOnly={pending} onChange={(e) => setPlayerNote(e.target.value)}
                       placeholder="运营补偿" />
              </div>
              <div className="field">
                <label htmlFor="grant-reason">补偿原因（必填，至少 4 个字，只进审计，玩家看不到）</label>
                <textarea id="grant-reason" value={reason} readOnly={pending} onChange={(e) => setReason(e.target.value)}
                          placeholder="例如：照片一直没出来，补偿 20 星币" />
              </div>
            </>
          )}
        </div>
        <div className="dialog-foot">
          {result ? <button className="primary" onClick={onDone}>完成</button> : (
            <>
              <button className="ghost" onClick={pending ? onDone : onClose} disabled={busy}>{pending ? "关闭并刷新" : "取消"}</button>
              <button className="primary" onClick={submit}
                      disabled={busy || !previewMatches || reason.trim().length < 4}>
                {busy ? "提交中…" : pending ? "用同一操作号重试" : `发放 ${amount} 星币`}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function CallLedger({ petId }: { petId: string }) {
  const { data, error, loading } = useAsync(() => api.get<PetCallsView>(`/pets/${encodeURIComponent(petId)}/calls`), [petId]);
  if (loading) return <div className="empty">读取中…</div>;
  if (error) return <div className="card-body"><ErrorNote error={error} /></div>;
  if (!data) return null;
  const statuses = Object.entries(data.reservations_by_status);
  return (
    <>
      <div className="card-body">
        <div className="actions" style={{ marginBottom: 8 }}>
          {statuses.length === 0 ? <span className="pill muted">这只宠物还没有以它为计费主体的调用</span>
            : statuses.map(([status, count]) => (
              <Pill key={status} tone={CALL_STATUS[status]?.tone ?? "muted"}>{CALL_STATUS[status]?.label ?? status} {count}</Pill>
            ))}
        </div>
        <p style={{ color: "var(--ink-soft)", fontSize: 12.5, margin: "0 0 4px" }}>单位：{data.unit}。{data.cost_note}</p>
        <p style={{ color: "var(--ink-faint)", fontSize: 12, margin: 0 }}>{data.scope_note} {data.counted_note}</p>
      </div>
      {data.counters_today.length > 0 && (
        <table>
          <thead><tr><th>今日额度层（{data.accounting_window}，UTC）</th><th className="num">已用</th><th className="num">在途</th></tr></thead>
          <tbody>
            {data.counters_today.map((c) => (
              <tr key={c.scope_key}><td><ScopeName scope={c.scope_key} /></td><td className="num">{c.used_units}</td><td className="num">{c.inflight_units}</td></tr>
            ))}
          </tbody>
        </table>
      )}
      {data.reservations.length > 0 && (
        <table>
          <thead><tr><th>时间</th><th>做什么用的</th><th>结果</th><th className="num">占用 / 计入次数</th><th>费用</th></tr></thead>
          <tbody>
            {data.reservations.map((r) => (
              <tr key={r.operation_id}>
                <td>{when(r.created_at)}</td>
                <td><Term family="purpose" code={r.purpose} /><div className="hint"><Term family="provider" code={r.provider} /></div></td>
                <td><Pill tone={CALL_STATUS[r.status]?.tone ?? "muted"}>{CALL_STATUS[r.status]?.label ?? r.status}</Pill></td>
                <td className="num">{r.reserved_units} / {r.counted_units ?? "在途"}</td>
                <td><RowCost state={r.cost_state} amount={r.estimated_cost} currency={r.cost_currency} /><Tech>{r.operation_id}</Tech></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

/** 额度层级 → 人话：`pet:<宠物>:<用途>` 是这只宠物自己的额度，`provider:<服务>:<用途>` 是全平台的额度。认不出来照原样显示。 */
function ScopeName({ scope }: { scope: string }) {
  const lookup = useLabel();
  const [head, id, purpose] = scope.split(":");
  const purposeText = purpose ? lookup("purpose", purpose) ?? purpose : null;
  if (head === "pet" && purposeText) return <span title={scope}>这只宠物自己的额度 · {purposeText}<Code value={scope} /></span>;
  if (head === "provider" && purposeText) {
    return <span title={scope}>全平台的额度 · {lookup("provider", id) ?? id} · {purposeText}<Code value={scope} /></span>;
  }
  return <span className="mono">{scope}</span>;
}
