/**
 * 冲正一笔后台补偿：先看影响（原补偿是谁发的、为什么、余额够不够、玩家会看到什么），再写原因与玩家说明，最后确认。
 *
 * 规则由后端守（整笔、一次、经手人不能冲、余额不够就拒绝）；这里只负责把规则在点确认**之前**讲清楚，
 * 并沿用所有写操作的同一套操作号规则：结果没确认就锁住内容、只能同号重试。
 */
import { useEffect, useState } from "react";
import { api, newOperationId, outcomeUnknown } from "../api/client";
import type { ReversalPreview, ReversalResult } from "../api/types";
import { ErrorNote, PendingOutcomeNote, when } from "./ui";
import { Staff, Tech } from "../labels";

export function ReversalDialog({ txId, onClose, onDone }: { txId: string; onClose: () => void; onDone: () => void }) {
  const [operationId] = useState(() => newOperationId("reverse"));
  const [playerNote, setPlayerNote] = useState("");
  const [reason, setReason] = useState("");
  const [preview, setPreview] = useState<ReversalPreview | null>(null);
  const [previewError, setPreviewError] = useState<unknown>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<ReversalResult | null>(null);

  useEffect(() => {
    let alive = true;
    const note = playerNote.trim() ? `&player_note=${encodeURIComponent(playerNote.trim())}` : "";
    api.get<ReversalPreview>(`/economy/reversals/preview?tx_id=${encodeURIComponent(txId)}${note}`)
      .then((value) => { if (alive) { setPreview(value); setPreviewError(null); } })
      .catch((exc) => { if (alive) setPreviewError(exc); });
    return () => { alive = false; };
  }, [txId, playerNote]);

  const submit = async () => {
    setBusy(true); setError(null);
    try {
      setResult(await api.post<ReversalResult>("/economy/reversals",
        { tx_id: txId, reason: reason.trim(), player_note: playerNote.trim() || null }, operationId));
      setPending(false);
    } catch (exc) {
      setError(exc);
      if (outcomeUnknown(exc)) setPending(true);
    } finally { setBusy(false); }
  };

  const original = preview?.original;
  // 预览必须对应要提交的这份说明（与补偿对话框同一条规则）：说明改了、新的预览还没回来（或说明不合规）时不能确认
  const expectedNote = playerNote.trim() ? playerNote.trim().split(/\s+/).join(" ") : "撤回一笔多发的补偿";
  const previewMatches = preview !== null && preview.player_view.reason === expectedNote;
  return (
    <div className="overlay" role="dialog" aria-modal="true">
      <div className="dialog" style={{ width: "min(600px, 100%)" }}>
        <h2>冲正一笔后台补偿{preview?.pet_name ? ` · ${preview.pet_name}` : ""}</h2>
        <div className="dialog-body">
          {result ? (
            <>
              <div className="note ok">
                <strong>{result.replayed ? "这个操作号之前已经冲正过" : "已冲正"} {result.reversal.amount} 星币</strong>，冲正后余额 {result.balance}。{result.note}
              </div>
              <dl className="kv">
                <dt>玩家看到</dt><dd>{result.player_view.delta} 星币 · {result.player_view.reason}</dd>
              </dl>
              <Tech>冲正流水 {result.reversal.tx_id} · 原补偿 {result.reversal.original_tx_id}</Tech>
            </>
          ) : (
            <>
              <ErrorNote error={error} />
              {pending && <PendingOutcomeNote operationId={operationId} />}
              <ErrorNote error={previewError} />
              {original && (
                <dl className="kv" style={{ marginBottom: 12 }}>
                  <dt>原补偿</dt><dd>+{original.amount} 星币 · {when(original.created_at)} · <Staff id={original.operator} /></dd>
                  <dt>当时的内部原因</dt><dd>{original.internal_reason ?? <span style={{ color: "var(--ink-faint)" }}>找不到（不猜）</span>}</dd>
                  <dt>玩家当时看到</dt><dd>{original.reason}</dd>
                  <dt>余额</dt><dd>{preview!.balance_before} → {preview!.balance_after ?? "不够整笔冲正"}</dd>
                </dl>
              )}
              {preview?.refusal && <div className="note warn"><strong>不能冲正：</strong>{preview.refusal.message}</div>}
              {preview && <ul className="effects">{preview.effects.map((line) => <li key={line}>{line}</li>)}</ul>}
              <div className="field">
                <label htmlFor="reversal-note">玩家在星球银行卡上看到的说明（空着就用「撤回一笔多发的补偿」，最多 30 字）</label>
                <input id="reversal-note" value={playerNote} readOnly={pending} onChange={(e) => setPlayerNote(e.target.value)}
                       placeholder="撤回一笔多发的补偿" />
              </div>
              <div className="field">
                <label htmlFor="reversal-reason">冲正原因（必填，至少 4 个字，只进审计，玩家看不到）</label>
                <textarea id="reversal-reason" value={reason} readOnly={pending} onChange={(e) => setReason(e.target.value)}
                          placeholder="例如：同一张工单被两位同事各补了一次，撤回后补的那一笔" />
              </div>
            </>
          )}
        </div>
        <div className="dialog-foot">
          {result ? <button className="primary" onClick={onDone}>完成</button> : (
            <>
              <button className="ghost" onClick={pending ? onDone : onClose} disabled={busy}>{pending ? "关闭并刷新" : "取消"}</button>
              <button className="danger" onClick={submit}
                      // 结果未确认时不按预览禁用：第一次若其实已成功，预览会说「已冲正过」，而同号重试正是拿回那次结果的办法
                      disabled={busy || (!pending && (!preview?.reversible || !previewMatches)) || reason.trim().length < 4}>
                {busy ? "提交中…" : pending ? "用同一操作号重试" : `冲正 ${original ? original.amount : ""} 星币`}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
