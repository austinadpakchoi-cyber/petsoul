import { Link } from "react-router";
import { useState } from "react";
import { api, newOperationId, outcomeUnknown } from "../api/client";
import type { BatchCapability, BatchDetail, BatchPreview, BatchSummary, SearchView, SessionView } from "../api/types";
import { ErrorNote, PendingOutcomeNote, Pill, ReasonDialog, useAsync, when, type ConfirmSpec } from "../components/ui";
import { Code, PermissionName, Staff, Tech, Term } from "../labels";

const STATUS: Record<string, { tone: "ok" | "warn" | "danger" | "muted"; label: string }> = {
  pending_approval: { tone: "warn", label: "待审批" },
  approved: { tone: "warn", label: "已批准，待执行" },
  rejected: { tone: "muted", label: "已驳回" },
  executed: { tone: "ok", label: "已执行" },
  failed: { tone: "danger", label: "失败" },
};

/** 批量补偿：额度没配就整条关着；提交与审批必须是两个人；执行逐条留痕。 */
export default function BatchesPage({ session }: { session: SessionView }) {
  const { data, error, loading, reload } = useAsync(
    () => api.get<{ batches: BatchSummary[]; capability: BatchCapability }>("/economy/batches"), []);
  const [dialog, setDialog] = useState<ConfirmSpec | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [detail, setDetail] = useState<BatchDetail | null>(null);
  const [composing, setComposing] = useState(false);

  const can = (p: string) => session.staff.permissions.includes(p);
  if (loading) return <div className="empty">读取中…</div>;
  if (error) return <ErrorNote error={error} />;
  const capability = data!.capability;

  const openDetail = async (batchId: string) => {
    setActionError(null);
    try { setDetail(await api.get<BatchDetail>(`/economy/batches/${batchId}`)); }
    catch (exc) { setActionError(exc); }
  };

  return (
    <>
      <div className="page-head">
        <h1>批量补偿</h1>
        <p>提交 → 审批（换一个人）→ 执行。只写游戏账本，不影响平台 API 调用账。</p>
      </div>

      <ErrorNote error={actionError} />

      <div className="card">
        <h2>能力状态</h2>
        <div className="card-body">
          {capability.enabled ? (
            <>
              <div className="note ok">批量补偿已开放。</div>
              <dl className="kv">
                <dt>单批最多人数</dt><dd>{capability.max_recipients}</dd>
                <dt>每只最多星币</dt><dd>{capability.max_coins_per_pet}</dd>
                <dt>单批合计上限</dt><dd>{capability.max_total_coins}</dd>
              </dl>
              <p style={{ color: "var(--ink-soft)", fontSize: 12.5 }}>{capability.note}</p>
            </>
          ) : (
            <div className="note warn">
              <strong>这项能力当前关闭。</strong>
              <div style={{ marginTop: 6 }}>{capability.note}</div>
            </div>
          )}
          {capability.enabled && can("economy.grant_batch") && (
            <div className="actions" style={{ marginTop: 12 }}>
              <button className="primary" onClick={() => setComposing(true)}>新建批次</button>
            </div>
          )}
          {capability.enabled && !can("economy.grant_batch") && (
            <span className="pill muted">提交需要「<PermissionName code="economy.grant_batch" />」权限</span>
          )}
        </div>
      </div>

      <div className="card">
        <h2>批次<small>{data!.batches.length} 个</small></h2>
        {data!.batches.length === 0 ? <div className="empty">还没有批次。</div> : (
          <table>
            <thead>
              <tr><th>批次</th><th>状态</th><th className="num">人数 / 每只</th><th className="num">合计</th>
                <th>提交 / 审批</th><th>结果</th><th>操作</th></tr>
            </thead>
            <tbody>
              {data!.batches.map((batch) => {
                const status = STATUS[batch.status] ?? { tone: "muted" as const, label: batch.status };
                return (
                  <tr key={batch.batch_id}>
                    <td>
                      <a href="#" onClick={(e) => { e.preventDefault(); void openDetail(batch.batch_id); }}>{batch.title}</a>
                      <Code value={batch.batch_id} />
                      <div style={{ fontSize: 12, color: "var(--ink-soft)" }}>{batch.reason}</div>
                      <div style={{ fontSize: 12, color: "var(--ink-faint)" }}>玩家看到：{batch.player_note}</div>
                    </td>
                    <td><Pill tone={status.tone}>{status.label}</Pill></td>
                    <td className="num">{batch.recipient_count} / {batch.amount_per_pet}</td>
                    <td className="num">{batch.total_amount}</td>
                    <td style={{ fontSize: 12 }}>
                      <div><Staff id={batch.submitted_by} /></div>
                      <div style={{ color: "var(--ink-faint)" }}>{when(batch.submitted_at)}</div>
                      {batch.decided_by && <div style={{ marginTop: 4 }}>批：<Staff id={batch.decided_by} /></div>}
                    </td>
                    <td style={{ fontSize: 12 }}>
                      {batch.status === "executed"
                        ? <>入账 {batch.applied_count}、跳过 {batch.skipped_count}<div>实发 {batch.applied_amount} 星币</div></>
                        : "—"}
                    </td>
                    <td>
                      <div className="actions">
                        {batch.status === "pending_approval" && can("economy.approve") && (
                          <>
                            <button className="primary" onClick={() => setDialog({
                              title: `批准「${batch.title}」`, confirmLabel: "批准",
                              effects: [`${batch.recipient_count} 只宠物各 ${batch.amount_per_pet} 星币，合计 ${batch.total_amount}。`,
                                        "批准之后还要执行一步才会真正入账。",
                                        "不能批准自己提交的批次；后台会按提交人拦下。"],
                              run: (note, op) => api.post(`/economy/batches/${batch.batch_id}/decision`,
                                { approve: true, note, expected_version: batch.version }, op),
                            })}>批准</button>
                            <button className="danger" onClick={() => setDialog({
                              title: `驳回「${batch.title}」`, danger: true, confirmLabel: "驳回",
                              effects: ["这个批次不会再执行。", "驳回理由会进审计。"],
                              run: (note, op) => api.post(`/economy/batches/${batch.batch_id}/decision`,
                                { approve: false, note, expected_version: batch.version }, op),
                            })}>驳回</button>
                          </>
                        )}
                        {batch.status === "approved" && can("economy.grant_batch") && (
                          <button className="primary" onClick={() => setDialog({
                            title: `执行「${batch.title}」`, confirmLabel: "执行",
                            effects: [`给 ${batch.recipient_count} 只宠物各发 ${batch.amount_per_pet} 星币。`,
                                      "执行时会再核一次照顾人有没有被冻结，被冻结的当场跳过并记原因。",
                                      "重复执行不会重复发放。"],
                            run: (note, op) => api.post(`/economy/batches/${batch.batch_id}/execute`,
                              { expected_version: batch.version, note }, op),
                          })}>执行</button>
                        )}
                        <button className="ghost" onClick={() => void openDetail(batch.batch_id)}>明细</button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {detail && <DetailDialog detail={detail} onClose={() => setDetail(null)} />}
      {composing && <ComposeDialog capability={capability} onClose={() => setComposing(false)}
                                   onDone={() => { setComposing(false); reload(); }} />}
      {dialog && <ReasonDialog spec={dialog} onClose={() => setDialog(null)} onDone={reload} />}
    </>
  );
}

function DetailDialog({ detail, onClose }: { detail: BatchDetail; onClose: () => void }) {
  return (
    <div className="overlay">
      <div className="dialog" style={{ width: "min(680px, 100%)" }}>
        <h2>{detail.batch.title}</h2>
        <div className="dialog-body">
          <dl className="kv">
            <dt>原因（内部）</dt><dd>{detail.batch.reason}</dd>
            <dt>玩家看到</dt><dd>+{detail.batch.amount_per_pet} 星币 · {detail.batch.player_note}</dd>
            <dt>提交</dt><dd><Staff id={detail.batch.submitted_by} /> · {when(detail.batch.submitted_at)}</dd>
            <dt>审批</dt><dd>{detail.batch.decided_by
              ? <><Staff id={detail.batch.decided_by} /> · {when(detail.batch.decided_at)}<div>{detail.batch.decision_note}</div></> : "—"}</dd>
            <dt>执行</dt><dd>{detail.batch.executed_by ? <><Staff id={detail.batch.executed_by} /> · {when(detail.batch.executed_at)}</> : "—"}</dd>
          </dl>
          <table style={{ marginTop: 12 }}>
            <thead><tr><th>宠物</th><th className="num">金额</th><th>结果</th></tr></thead>
            <tbody>
              {detail.items.map((item) => (
                <tr key={item.pet_id}>
                  <td><Link to={`/pets/${item.pet_id}`}>打开宠物</Link><Code value={item.pet_id} /></td>
                  <td className="num">{item.amount}</td>
                  <td><Pill tone={item.status === "applied" ? "ok" : item.status === "skipped" ? "muted" : item.status === "failed" ? "danger" : "warn"}>
                    <Term family="batch_item_status" code={item.status} /></Pill>{item.outcome && <div className="hint">{item.outcome}</div>}
                    <Tech>{item.ledger_key ?? ""}</Tech></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="dialog-foot"><button className="primary" onClick={onClose}>关闭</button></div>
      </div>
    </div>
  );
}

function ComposeDialog({ capability, onClose, onDone }: { capability: BatchCapability; onClose: () => void; onDone: () => void }) {
  // 这一次提交的固定操作号：结果没确认时用它重试，后端回第一次的批次，不会出现两个一样的批次。
  const [operationId] = useState(() => newOperationId("batch"));
  const [title, setTitle] = useState("");
  const [reason, setReason] = useState("");
  const [playerNote, setPlayerNote] = useState("");
  const [amount, setAmount] = useState(10);
  const [raw, setRaw] = useState("");
  const [preview, setPreview] = useState<BatchPreview | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState(false);  // 提交结果未确认：整张表单锁住，只能同号重试
  const petIds = raw.split(/[\s,，、]+/).map((s) => s.trim()).filter(Boolean);
  // 按名字找宠物，点「加入」把编号放进名单——运营不必自己记编号（检索要「查用户与家庭」权限，会留访问记录）
  const [find, setFind] = useState("");
  const [found, setFound] = useState<SearchView["pets"] | null>(null);
  const lookup = async () => {
    setError(null);
    try { setFound((await api.get<SearchView>(`/search?q=${encodeURIComponent(find.trim())}`)).pets); }
    catch (exc) { setError(exc); }
  };
  const add = (petId: string) => {
    if (petIds.includes(petId)) return;
    setRaw((current) => (current.trim() ? [current.trim(), petId].join(String.fromCharCode(10)) : petId));
    setPreview(null);
  };

  const doPreview = async () => {
    setBusy(true); setError(null);
    try { setPreview(await api.post<BatchPreview>("/economy/batches/preview",
      { pet_ids: petIds, amount_per_pet: amount, player_note: playerNote.trim() || null })); }
    catch (exc) { setError(exc); setPreview(null); } finally { setBusy(false); }
  };

  const submit = async () => {
    setBusy(true); setError(null);
    try {
      await api.post("/economy/batches",
        { title: title.trim(), reason: reason.trim(), pet_ids: petIds, amount_per_pet: amount,
          player_note: playerNote.trim() || null }, operationId);
      onDone();
    } catch (exc) {
      setError(exc);
      if (outcomeUnknown(exc)) setPending(true);
    } finally { setBusy(false); }
  };

  return (
    <div className="overlay">
      <div className="dialog" style={{ width: "min(680px, 100%)" }}>
        <h2>新建批量补偿</h2>
        <div className="dialog-body">
          <ErrorNote error={error} />
          {pending && <PendingOutcomeNote operationId={operationId} />}
          <div className="field"><label>批次名（审批的人要看）</label>
            <input value={title} readOnly={pending} onChange={(e) => setTitle(e.target.value)} placeholder="上周照片积压补偿" /></div>
          <div className="field"><label>原因（必填，只给审批人和审计看，玩家看不到）</label>
            <textarea value={reason} readOnly={pending} onChange={(e) => setReason(e.target.value)} style={{ minHeight: 60 }} /></div>
          <div className="field"><label>玩家在星球银行卡上看到的说明（空着就用「运营补偿」，最多 30 字）</label>
            {/* 改了说明，之前的影响预览就不再代表要提交的内容：清掉，逼着重新预览 */}
            <input value={playerNote} readOnly={pending} placeholder="运营补偿"
                   onChange={(e) => { setPlayerNote(e.target.value); setPreview(null); }} /></div>
          <div className="row">
            <div><label>每只宠物（星币，上限 {capability.max_coins_per_pet}）</label>
              {/* 金额一改，之前的影响预览就不再代表要提交的东西：清掉，逼着重新预览 */}
              <input type="number" min={1} max={capability.max_coins_per_pet ?? 1} value={amount} readOnly={pending}
                     onChange={(e) => { setAmount(Number(e.target.value)); setPreview(null); }} /></div>
            <div><label>名单人数</label>
              <input value={`${petIds.length} / ${capability.max_recipients}`} readOnly /></div>
          </div>
          <div className="field">
            <label>按名字找宠物，点「加入」放进名单</label>
            <div className="row" style={{ alignItems: "center" }}>
              <input value={find} readOnly={pending} onChange={(e) => setFind(e.target.value)} placeholder="宠物名或宠物编号" />
              <button onClick={() => void lookup()} disabled={pending || !find.trim()} style={{ flex: "0 0 auto" }}>查找</button>
            </div>
            {found && (found.length === 0 ? <div className="hint">没找到这样的宠物。</div> : (
              <div style={{ marginTop: 6 }}>
                {found.map((pet) => (
                  <div key={pet.pet_id} style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13, marginTop: 4 }}>
                    <span>{pet.name}（<Term family="species" code={pet.species} />）</span><Code value={pet.pet_id} />
                    <button className="ghost" disabled={pending || petIds.includes(pet.pet_id)} onClick={() => add(pet.pet_id)}>
                      {petIds.includes(pet.pet_id) ? "已在名单里" : "加入"}</button>
                  </div>
                ))}
              </div>
            ))}
          </div>
          <div className="field">
            <label>名单（宠物编号，一行一个；用上面的查找来加，也可以直接粘贴）</label>
            <textarea value={raw} readOnly={pending} onChange={(e) => { setRaw(e.target.value); setPreview(null); }} placeholder="PJ-XXXXXXXX" />
          </div>

          {preview && (
            <>
              <div className="note info">
                可发放 {preview.eligible_count} 只，跳过 {preview.skipped_count} 只，合计 {preview.total_amount} 星币。
              </div>
              <ul className="effects">{preview.effects.map((line) => <li key={line}>{line}</li>)}</ul>
              <table>
                <thead><tr><th>宠物</th><th>可发放</th><th className="num">当前</th><th className="num">发完</th></tr></thead>
                <tbody>
                  {preview.recipients.map((row) => (
                    <tr key={row.pet_id}>
                      <td>{row.name ?? "—"}<Code value={row.pet_id} /></td>
                      <td>{row.eligible ? <Pill tone="ok">可以</Pill> : <><Pill tone="muted">跳过</Pill><div style={{ fontSize: 12 }}>{row.reason}</div></>}</td>
                      <td className="num">{row.balance_before ?? "—"}</td>
                      <td className="num">{row.balance_after ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
        <div className="dialog-foot">
          <button className="ghost" onClick={pending ? onDone : onClose} disabled={busy}>{pending ? "关闭并刷新" : "取消"}</button>
          <button onClick={doPreview} disabled={busy || pending || petIds.length === 0}>影响预览</button>
          <button className="primary" onClick={submit}
                  disabled={busy || !preview || preview.eligible_count === 0 || title.trim().length === 0 || reason.trim().length < 4}>
            {pending ? "用同一操作号重试" : "提交待审批"}
          </button>
        </div>
      </div>
    </div>
  );
}
