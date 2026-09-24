/**
 * 平台成本：区间估算 + 价格表（只追加）。
 *
 * 估算＝计入用量 × 调用时有效的单价。没有适用价格的计入用量单列，不算作免费；
 * 人民币与美元分开，不相加、不换算；账单确认费用要等账单导入，现在一律未知。与游戏星币没有任何关系。
 */
import { useState } from "react";
import { api, newOperationId, outcomeUnknown } from "../api/client";
import type { CostEstimateLine, CostEstimateView, CostState, PriceRow, PricesView, SessionView } from "../api/types";
import { CostCell, money } from "../components/costs";
import { RelayConsumption } from "./RelayConsumption";
import { ErrorNote, PendingOutcomeNote, Pill, ReasonDialog, useAsync, when, type ConfirmSpec } from "../components/ui";
import { PermissionName, Staff, Term, useFamily, useLabel } from "../labels";

const CURRENCY: Record<string, string> = { CNY: "人民币", USD: "美元" };
const OTHER = "__other__";

const WINDOWS = [
  { key: "today", label: "今天", days: 1 },
  { key: "7d", label: "最近 7 天", days: 7 },
  { key: "30d", label: "最近 30 天", days: 30 },
] as const;

function utcDay(offsetDays: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - offsetDays);
  return d.toISOString().slice(0, 10);
}

export default function CostsPage({ session }: { session: SessionView }) {
  const [windowKey, setWindowKey] = useState<(typeof WINDOWS)[number]["key"]>("7d");
  const days = WINDOWS.find((w) => w.key === windowKey)!.days;
  const estimate = useAsync(
    () => api.get<CostEstimateView>(`/costs/estimate?start=${utcDay(days - 1)}&end=${utcDay(0)}`), [days]);
  const prices = useAsync(() => api.get<PricesView>("/costs/prices"), []);
  const [dialog, setDialog] = useState<ConfirmSpec | null>(null);
  const [adding, setAdding] = useState(false);
  const canManage = session.staff.permissions.includes("cost.manage");
  const label = useLabel();
  const reloadAll = () => { prices.reload(); estimate.reload(); };

  return (
    <>
      <div className="page-head">
        <h1>平台成本</h1>
        <p>估算＝计入用量 × 调用时有效的单价。人民币与美元分开记，和游戏星币没有兑换关系。</p>
      </div>

      <div className="card">
        <h2>费用估算<small>{estimate.data ? `${estimate.data.window.from} – ${estimate.data.window.to} · ${estimate.data.window.basis}` : ""}</small></h2>
        <div className="tabs" role="tablist">
          {WINDOWS.map((w) => (
            <button key={w.key} role="tab" aria-selected={windowKey === w.key} className={windowKey === w.key ? "active" : ""}
                    onClick={() => setWindowKey(w.key)}>{w.label}</button>
          ))}
        </div>
        {estimate.error ? <div className="card-body"><ErrorNote error={estimate.error} /></div>
          : estimate.loading || !estimate.data ? <div className="empty">读取中…</div> : (
            <EstimateBody data={estimate.data} />
          )}
      </div>

      <div className="card">
        <h2>价格表<small>只追加：改价录新价，录错了作废那一条；历史不删不改</small></h2>
        {prices.error ? <div className="card-body"><ErrorNote error={prices.error} /></div>
          : prices.loading || !prices.data ? <div className="empty">读取中…</div> : (
            <>
              <div className="card-body">
                <div className="note plain">{prices.data.unit_note}</div>
                <div className="actions">
                  {canManage ? <button className="primary" onClick={() => setAdding(true)}>录一条价格</button>
                    : <span className="pill muted">录价需要「<PermissionName code="cost.manage" />」权限</span>}
                </div>
              </div>
              {prices.data.prices.length === 0 ? <div className="empty">还没有录入任何价格。没有价格时费用一律是「未知」，不显示 0。</div> : (
                <table>
                  <thead><tr><th>供应商 / 用途</th><th>单价（每个计量单位）</th><th>生效时间</th><th>来源</th><th>状态</th><th>录入</th><th /></tr></thead>
                  <tbody>
                    {prices.data.prices.map((row) => (
                      <PriceLine key={row.price_id} row={row} canManage={canManage}
                                 onRetire={() => setDialog({
                                   title: `作废这条价格（${label("provider", row.provider) ?? row.provider} / ${row.purpose === "*" ? "所有用途" : label("purpose", row.purpose) ?? row.purpose} ·${money(row.currency, row.unit_price)}）`,
                                   danger: true, confirmLabel: "作废",
                                   effects: ["作废之后它不再参与估算；这条记录本身保留，历史可查。",
                                             "已经看到过的估算会按新的价格历史现算——没有「冻结在当时」的旧估算。",
                                             "要改价请录一条生效时间更晚的新价，而不是作废旧价。"],
                                   run: (reason, op) => api.post(`/costs/prices/${row.price_id}/retire`, { reason }, op),
                                 })} />
                    ))}
                  </tbody>
                </table>
              )}
              <div className="card-body">
                <div className="note plain">{prices.data.billed_note} {prices.data.history_note}</div>
              </div>
            </>
          )}
      </div>

      <RelayConsumption canImport={canManage} />

      {adding && prices.data && <AddPriceDialog view={prices.data} onClose={() => setAdding(false)}
                                                 onDone={() => { setAdding(false); reloadAll(); }} />}
      {dialog && <ReasonDialog spec={dialog} onClose={() => setDialog(null)} onDone={reloadAll} />}
    </>
  );
}

function lineState(line: CostEstimateLine, configured: boolean): CostState {
  if (!configured) return "unknown_no_price_table";
  if (line.counted_units === 0) return "not_counted";
  if (line.priced_units === 0) return "unknown_no_price";
  return line.complete ? "estimated" : "partial";
}

function EstimateBody({ data }: { data: CostEstimateView }) {
  const currencies = Object.entries(data.currencies);
  return (
    <>
      <div className="card-body">
        {!data.price_table_configured && <div className="note warn">价格表里没有有效的价格（没录过，或录过的都已作废）：下面所有计入用量都没有价格，费用是「未知」，不是 0。</div>}
        <div className="grid cols-4">
          {currencies.length === 0 ? (
            <div className="metric"><div className="value na">未知</div><div className="label">估算费用</div>
              <div className="source">这个区间里没有任何一次调用有适用价格</div></div>
          ) : currencies.map(([currency, value]) => (
            <div className="metric" key={currency}>
              <div className="value">{money(currency, value.estimated)}</div>
              <div className="label">估算费用（已结清）· {CURRENCY[currency] ?? currency}</div>
              <div className="source">另有未确认 {money(currency, value.unconfirmed)}</div>
            </div>
          ))}
          <div className="metric">
            <div className={data.unpriced_units > 0 ? "value" : "value na"}>{data.unpriced_units}</div>
            <div className="label">没有适用价格的计入用量</div>
            <div className="source">不计价、单列，不是免费</div>
          </div>
          <div className="metric">
            <div className="value na">未知</div>
            <div className="label">账单确认费用</div>
            <div className="source">要等供应商账单导入</div>
          </div>
        </div>
      </div>
      {data.lines.length === 0 ? <div className="empty">这个区间里没有调用。</div> : (
        <table>
          <thead><tr><th>供应商 / 用途</th><th className="num">调用</th><th className="num">计入用量</th><th className="num">未定价</th>
            <th className="num">在途 / 未计入</th><th>估算（按币种）</th></tr></thead>
          <tbody>
            {data.lines.map((line) => (
              <tr key={`${line.provider}:${line.purpose}`}>
                <td><Term family="purpose" code={line.purpose} /><div className="hint"><Term family="provider" code={line.provider} /></div></td>
                <td className="num">{line.calls}</td>
                <td className="num">{line.counted_units}</td>
                <td className="num">{line.unpriced_units > 0 ? <Pill tone="warn">{line.unpriced_units}</Pill> : 0}</td>
                <td className="num">{line.in_flight_calls} / {line.not_counted_calls}</td>
                <td><CostCell state={lineState(line, data.price_table_configured)} costs={line.by_currency} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="card-body">
        <ul className="effects">{Object.entries(data.notes).map(([key, text]) => <li key={key}>{text}</li>)}</ul>
      </div>
    </>
  );
}

/** 生效时间按 UTC 显示（录入时也是按 UTC 填的），不转成浏览器本地时间，免得同一条价两处看起来差 8 小时。 */
function utcMinute(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : `${d.toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

function PriceLine({ row, canManage, onRetire }: { row: PriceRow; canManage: boolean; onRetire: () => void }) {
  const retired = row.status === "retired";
  return (
    <tr style={retired ? { opacity: 0.6 } : undefined}>
      <td>{row.purpose === "*" ? "所有用途" : <Term family="purpose" code={row.purpose} />}<div className="hint"><Term family="provider" code={row.provider} />{row.model_note ? ` · ${row.model_note}` : ""}</div></td>
      <td>{money(row.currency, row.unit_price)}<div className="hint">每次调用 · {CURRENCY[row.currency] ?? row.currency}</div></td>
      <td className="mono">{utcMinute(row.effective_from)}</td>
      <td>{row.source_note}</td>
      <td>{retired ? <><Pill tone="muted">已作废</Pill><div style={{ fontSize: 12 }}>{row.retired_reason}</div></> : <Pill tone="ok">有效</Pill>}</td>
      <td style={{ fontSize: 12 }}><Staff id={row.created_by} /><div>{when(row.created_at)}</div></td>
      <td>{!retired && canManage && <button className="danger" onClick={onRetire}>作废</button>}</td>
    </tr>
  );
}

/** 录价：操作号在打开时生成；结果没确认就锁住内容、只能同号重试（与其他写操作同一套规则）。 */
function AddPriceDialog({ view, onClose, onDone }: { view: PricesView; onClose: () => void; onDone: () => void }) {
  const [operationId] = useState(() => newOperationId("price"));
  const first = view.observed_scopes[0];
  const [provider, setProvider] = useState(first?.provider ?? "");
  const [purpose, setPurpose] = useState(first?.purpose ?? "");
  const [currency, setCurrency] = useState(view.currencies[0] ?? "CNY");
  const [unitPrice, setUnitPrice] = useState("");
  const [effective, setEffective] = useState(() => new Date().toISOString().slice(0, 16));
  const [source, setSource] = useState("");
  const [model, setModel] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);
  const observed = view.observed_scopes.some((s) => s.provider === provider && (purpose === "*" || s.purpose === purpose));

  const submit = async () => {
    setBusy(true); setError(null);
    try {
      // 输入框里是 UTC 时间（下面写明了），补上 Z 再发，服务端要求带时区
      await api.post("/costs/prices", { provider: provider.trim(), purpose: purpose.trim(), currency, unit_price: unitPrice.trim(),
                                        effective_from: `${effective}:00Z`, source_note: source.trim(), model_note: model.trim() || null },
                     operationId);
      onDone();
    } catch (exc) {
      setError(exc);
      if (outcomeUnknown(exc)) setPending(true);
    } finally { setBusy(false); }
  };

  return (
    <div className="overlay" role="dialog" aria-modal="true">
      <div className="dialog" style={{ width: "min(620px, 100%)" }}>
        <h2>录一条价格</h2>
        <div className="dialog-body">
          <ErrorNote error={error} />
          {pending && <PendingOutcomeNote operationId={operationId} />}
          {view.observed_scopes.length > 0 && (
            <div className="field">
              <label>额度账里出现过的（供应商 / 用途）</label>
              <div className="actions">
                {view.observed_scopes.map((s) => (
                  <button key={`${s.provider}:${s.purpose}`} className="ghost" disabled={pending}
                          onClick={() => { setProvider(s.provider); setPurpose(s.purpose); }}>
                    <Term family="provider" code={s.provider} /> / <Term family="purpose" code={s.purpose} />（{s.calls} 次）
                  </button>
                ))}
              </div>
            </div>
          )}
          <div className="row">
            <div><label htmlFor="price-provider">供应商</label>
              <CodePicker id="price-provider" family="provider" value={provider} onChange={setProvider} disabled={pending}
                          codes={view.observed_scopes.map((s) => s.provider)} /></div>
            <div><label htmlFor="price-purpose">用途</label>
              <CodePicker id="price-purpose" family="purpose" value={purpose} onChange={setPurpose} disabled={pending} star
                          codes={view.observed_scopes.map((s) => s.purpose)} /></div>
          </div>
          {!observed && provider && purpose && (
            <div className="note warn">额度账里还没出现过「<Term family="provider" code={provider} /> / {purpose === "*" ? "全部用途" : <Term family="purpose" code={purpose} />}」。要与账上记的一致，否则这条价格永远用不上。</div>)}
          <div className="row">
            <div><label htmlFor="price-currency">币种（各算各的，不换算）</label>
              <select id="price-currency" value={currency} disabled={pending} onChange={(e) => setCurrency(e.target.value)}>
                {view.currencies.map((c) => <option key={c} value={c}>{CURRENCY[c] ? `${CURRENCY[c]}（${c}）` : c}</option>)}
              </select></div>
            <div><label htmlFor="price-unit">单价（每个计量单位，最多 6 位小数）</label>
              <input id="price-unit" value={unitPrice} readOnly={pending} onChange={(e) => setUnitPrice(e.target.value)} placeholder="例如 0.28" /></div>
          </div>
          <div className="field"><label htmlFor="price-effective">生效时间（UTC）：预占创建时刻不早于它的调用才用这条价</label>
            <input id="price-effective" type="datetime-local" value={effective} readOnly={pending} onChange={(e) => setEffective(e.target.value)} /></div>
          <div className="field"><label htmlFor="price-source">来源（必填：价目页、合同或账单，会进审计）</label>
            <input id="price-source" value={source} readOnly={pending} onChange={(e) => setSource(e.target.value)} /></div>
          <div className="field"><label htmlFor="price-model">对应的模型或套餐（选填，说明用；额度账里没有记模型）</label>
            <input id="price-model" value={model} readOnly={pending} onChange={(e) => setModel(e.target.value)} /></div>
          <div className="note plain">{view.unit_note}</div>
        </div>
        <div className="dialog-foot">
          <button className="ghost" onClick={pending ? onDone : onClose} disabled={busy}>{pending ? "关闭并刷新" : "取消"}</button>
          <button className="primary" onClick={submit}
                  disabled={busy || !provider.trim() || !purpose.trim() || !unitPrice.trim() || source.trim().length < 4}>
            {busy ? "提交中…" : pending ? "用同一操作号重试" : "录入"}
          </button>
        </div>
      </div>
    </div>
  );
}

/** 供应商 / 用途：从词表与额度账里出现过的里选（显示说法）；都不是时选「其他」手动填代码。 */
function CodePicker({ id, family, value, onChange, codes, star = false, disabled }: {
  id: string; family: string; value: string; onChange: (code: string) => void; codes: string[]; star?: boolean; disabled: boolean;
}) {
  const known = useFamily(family);
  const options = [...new Set([...(star ? ["*"] : []), ...Object.keys(known), ...codes])];
  const [manual, setManual] = useState(value !== "" && !options.includes(value));
  const text = (code: string) => (code === "*" ? "这个供应商的全部用途（只在没有专门价格时用）" : known[code] ?? `${code}（词表里没有）`);
  return (
    <>
      <select id={id} value={manual ? OTHER : value} disabled={disabled}
              onChange={(e) => { const next = e.target.value; setManual(next === OTHER); onChange(next === OTHER ? "" : next); }}>
        <option value="" disabled>请选择…</option>
        {options.map((code) => <option key={code} value={code}>{text(code)}</option>)}
        <option value={OTHER}>其他（手动填写代码）</option>
      </select>
      {manual && <input aria-label="手动填写的代码" value={value} readOnly={disabled} onChange={(e) => onChange(e.target.value)}
                        placeholder="填额度账里记的那个代码" style={{ marginTop: 6 }} />}
    </>
  );
}
