/**
 * 平台成本页的「中转实测消费」（c84a 审查 ADM-COST-01）：经自建中转站的逐次调用回执，四块分开——
 * 中转实测用量 / 按有来源价格估算 / 供应商账单确认 / 结果未确认·待对账。缺什么就写缺什么：不填均价、不补 0、币种分开，和游戏星币无关。
 * 现在还没有真实来源（PetSoul 复用的是 okeymind 客户端）：导入默认关闭，页面写清楚要中转与 I 提供什么。
 */
import { useState } from "react";
import { api, newOperationId, outcomeUnknown } from "../api/client";
import type { RelayConsumptionView, RelayDayCell } from "../api/types";
import { money } from "../components/costs";
import { ErrorNote, PendingOutcomeNote, Pill, useAsync, when } from "../components/ui";
import { PermissionName, Term } from "../labels";

export function RelayConsumption({ canImport }: { canImport: boolean }) {
  const { data, error, loading, reload } = useAsync(() => api.get<RelayConsumptionView>("/costs/consumption"), []);
  const [importing, setImporting] = useState(false);
  if (loading) return <div className="card"><div className="empty">读取中转回执…</div></div>;
  if (error) return <ErrorNote error={error} />;
  if (!data) return null;
  if (!data.available) return <div className="card"><h2>中转实测消费</h2><div className="empty">{data.note}</div></div>;
  const sync = data.sync!;
  const enabled = data.capability?.enabled ?? false;

  return (
    <div className="card">
      <h2>中转实测消费<small>逐次回执 · 实测用量 / 估算 / 账单确认 / 待对账 四块分开</small></h2>
      <div className="card-body">
        {!enabled && (
          <div className="note warn">
            <strong>未接入。</strong>{data.capability?.note}
            <ul className="effects" style={{ marginTop: 6, marginBottom: 0 }}>
              <li>要中转维护者提供：按环境分开的 PetSoul 专属客户端；每次发送持久化一条回执（带唯一事件号、模型、各类用量）；按项目与游标拉取的只读接口。</li>
              <li>要 I 提供：调用中转时带上业务操作号与用途，把中转返回的事件号存进额度账——后台才能把回执对上是哪一次业务。</li>
              <li>在那之前这里不显示任何金额（不填均价、不补 0）；平台成本的估算仍按上面的价格表与调用次数。</li>
            </ul>
          </div>
        )}
        <dl className="kv">
          <dt>同步</dt>
          <dd>{sync.batches === 0 ? "还没导入过" : <>导入过 {sync.batches} 批，最近一次 {when(sync.last_import_at)}</>}
            {enabled && <span className="hint">（白名单里的专属客户端：{data.capability!.clients.join("、")}）</span>}</dd>
          <dt>回执</dt>
          <dd>{sync.receipts} 条{sync.receipts > 0 && <>：
            {sync.unattributed > 0 && <Pill tone="warn">未归属 {sync.unattributed}</Pill>}{" "}
            {sync.unpriced > 0 && <Pill tone="unknown">未定价 {sync.unpriced}</Pill>}{" "}
            {sync.unknown_outcome > 0 && <Pill tone="unknown">结果未确认 {sync.unknown_outcome}</Pill>}{" "}
            {sync.no_usage > 0 && <Pill tone="muted">没有用量 {sync.no_usage}</Pill>}{" "}
            <Pill tone="muted">有账单 {sync.billed}</Pill></>}</dd>
          <dt>导入时的问题</dt>
          <dd>{sync.conflicts === 0 && sync.rejected === 0 ? "没有" : <>
            {sync.conflicts > 0 && <Pill tone="danger">同号内容冲突 {sync.conflicts}（保留原来的，没覆盖）</Pill>}{" "}
            {sync.rejected > 0 && <Pill tone="warn">拒收 {sync.rejected}</Pill>}</>}</dd>
        </dl>
        {enabled && (canImport
          ? <div className="actions" style={{ marginTop: 10 }}><button onClick={() => setImporting(true)}>导入回执文件</button></div>
          : <div className="hint" style={{ marginTop: 8 }}>导入要「<PermissionName code="cost.manage" />」权限。</div>)}
      </div>
      {(data.days ?? []).length === 0 ? <div className="empty">还没有回执。</div> : (
        <table>
          <thead><tr><th>哪天（UTC）</th><th>用途 / 模型</th><th>中转实测用量</th><th>按有来源价格估算</th><th>供应商账单确认</th><th className="num">待对账</th></tr></thead>
          <tbody>{data.days!.map((cell) => <DayRow key={`${cell.day}:${cell.purpose}:${cell.model}`} cell={cell} />)}</tbody>
        </table>
      )}
      {data.notes && (
        <div className="card-body">
          <ul className="effects" style={{ margin: 0 }}>{Object.entries(data.notes).map(([key, text]) => <li key={key}>{text}</li>)}</ul>
        </div>
      )}
      {importing && <ImportDialog onClose={() => setImporting(false)} onDone={() => { setImporting(false); reload(); }} />}
    </div>
  );
}

function amounts(values: Record<string, string>) {
  const entries = Object.entries(values);
  return entries.length === 0 ? null : entries.map(([currency, amount]) => <div key={currency}>{money(currency, amount)}</div>);
}

function DayRow({ cell }: { cell: RelayDayCell }) {
  const m = cell.measured;
  return (
    <tr>
      <td>{cell.day}</td>
      <td>{cell.purpose ? <Term family="purpose" code={cell.purpose} /> : <span className="hint">没写用途</span>}
        <div className="hint">{cell.model ?? "没写模型"}{cell.model && !cell.model_confirmed && "（请求时写的，供应商没确认）"}</div></td>
      <td>发了 {m.dispatches} 次、成了 {m.succeeded} 次{m.images > 0 && `，返回 ${m.images} 张图`}
        <div className="hint">token：文字入 {m.input_text_tokens}、图片入 {m.input_image_tokens}、缓存 {m.cached_tokens}、出 {m.output_tokens}
          （{m.with_usage} 次带用量）</div>
        {cell.unattributed > 0 && <div className="hint">其中 {cell.unattributed} 次对不上额度账的操作号（未归属）</div>}</td>
      <td>{amounts(cell.estimated) ?? <span className="hint">没有</span>}
        {cell.unpriced > 0 && <div className="hint">未定价 {cell.unpriced} 次（不算钱，也不是 0）</div>}</td>
      <td>{amounts(cell.billed) ?? <Pill tone="unknown">未知</Pill>}
        {cell.unbilled > 0 && Object.keys(cell.billed).length > 0 && <div className="hint">另有 {cell.unbilled} 次没账单</div>}</td>
      <td className="num">{cell.pending > 0 ? <Pill tone="unknown">{cell.pending}</Pill> : 0}</td>
    </tr>
  );
}

/** 离线导入（临时桥接）：选 JSON 数组或一行一条的 JSONL 文件，写来源说明；操作号在打开时生成，结果没确认就只能同号重试。 */
function ImportDialog({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [operationId] = useState(() => newOperationId("relay"));
  const [records, setRecords] = useState<unknown[] | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  const pick = async (file: File | undefined) => {
    setParseError(null); setRecords(null);
    if (!file) return;
    setFileName(file.name);
    const text = await file.text();
    try {
      const trimmed = text.trim();
      const parsed = trimmed.startsWith("[") ? JSON.parse(trimmed)
        : trimmed.split(String.fromCharCode(10)).filter((line) => line.trim()).map((line) => JSON.parse(line));
      if (!Array.isArray(parsed)) throw new Error("文件里要是一组回执");
      setRecords(parsed);
    } catch (exc) {
      setParseError(`读不懂这个文件：${exc instanceof Error ? exc.message : String(exc)}（要 JSON 数组，或一行一条的 JSONL）`);
    }
  };

  const submit = async () => {
    setBusy(true); setError(null);
    try {
      setResult(await api.post<Record<string, unknown>>("/costs/relay-receipts/import",
        { records, source_note: note.trim(), file_name: fileName }, operationId));
    } catch (exc) {
      setError(exc);
      if (outcomeUnknown(exc)) setPending(true);
    } finally { setBusy(false); }
  };

  return (
    <div className="overlay" role="dialog" aria-modal="true">
      <div className="dialog">
        <h2>导入中转回执</h2>
        <div className="dialog-body">
          <ErrorNote error={error} />
          {pending && <PendingOutcomeNote operationId={operationId} />}
          {result ? (
            <div className="note ok">新入库 {String(result.inserted)} 条，重复 {String(result.duplicates)} 条（没多记），
              同号冲突 {String(result.conflicts)} 条（保留原来的），拒收 {String(result.rejected)} 条（原因已记下）。</div>
          ) : (
            <>
              <ul className="effects">
                <li>只收白名单里的 PetSoul 专属客户端；别的项目（比如 okeymind）的回执整条拒收。</li>
                <li>同一条回执（同一个中转实例＋事件号）重复导入不会记两次；内容不一样的记成冲突，不覆盖。</li>
                <li>这是临时桥接；正式做法是后端按游标从中转只读同步。</li>
              </ul>
              <div className="field"><label htmlFor="relay-file">回执文件（JSON 数组或 JSONL）</label>
                <input id="relay-file" type="file" accept=".json,.jsonl,application/json" disabled={pending || busy}
                       onChange={(e) => void pick(e.target.files?.[0])} /></div>
              {parseError && <div className="note warn">{parseError}</div>}
              {records && <div className="note plain">读到 {records.length} 条回执。</div>}
              <div className="field"><label htmlFor="relay-note">来源说明（必填，至少 4 个字，会写进审计）</label>
                <textarea id="relay-note" value={note} readOnly={pending} onChange={(e) => setNote(e.target.value)}
                          placeholder="例如：中转维护者导出的 9 月 24 日本地环境回执，文件由某某提供" /></div>
            </>
          )}
        </div>
        <div className="dialog-foot">
          <button className="ghost" onClick={result || pending ? onDone : onClose} disabled={busy}>{result || pending ? "关闭并刷新" : "取消"}</button>
          {!result && <button className="primary" onClick={submit} disabled={busy || !records || note.trim().length < 4}>
            {busy ? "导入中…" : pending ? "用同一操作号重试" : "导入"}</button>}
        </div>
      </div>
    </div>
  );
}
