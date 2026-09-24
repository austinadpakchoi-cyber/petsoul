/**
 * 宠物页的「运行记录」：已经记下的心跳、思考与决定、今天的额度、钱袋子、是否暂停。
 * 与「宠物运行」页同一个接口、同一套展示（只看这一只）；上面那张「TA 现在怎么样」是按此刻事实现算的，这张是记下来的。
 */
import { useState } from "react";
import { api } from "../api/client";
import type { PetsRuntimeView, SessionView } from "../api/types";
import { Brain, Heartbeat, pauseSpec, Usage } from "../components/runtime";
import { ErrorNote, Pill, ReasonDialog, useAsync, when, type ConfirmSpec } from "../components/ui";
import { PermissionName, Staff } from "../labels";

export function PetRuntimeRecord({ petId, session }: { petId: string; session: SessionView }) {
  const { data, error, loading, reload } = useAsync(
    () => api.get<PetsRuntimeView>(`/pets-runtime?pet_id=${encodeURIComponent(petId)}`), [petId]);
  const [dialog, setDialog] = useState<ConfirmSpec | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const can = (p: string) => session.staff.permissions.includes(p);
  if (loading) return <div className="card"><div className="empty">读取运行记录…</div></div>;
  if (error) return <ErrorNote error={error} />;
  const row = data?.pets[0];
  if (!data || !row) return null;
  const m = data.modes;
  const canToggle = can("pet.maintain") && (row.paused || (m.pause_open && row.kind === "resident"));

  return (
    <div className="card">
      <h2>运行记录<small>已经记下的，不是现算的</small></h2>
      <div className="card-body">
        <ErrorNote error={actionError} />
        <div className="grid cols-2">
          <dl className="kv">
            <dt>心跳</dt><dd><Heartbeat row={row} /></dd>
            <dt>思考与决定</dt><dd><Brain row={row} /></dd>
          </dl>
          <dl className="kv">
            {data.sections.wallets && (<><dt>钱袋子</dt><dd>{row.wallet == null ? "没有钱包" : `${row.wallet} 星币`}</dd></>)}
            {data.sections.usage && (<><dt>今天的额度</dt><dd><Usage row={row} caps={m.caps} /></dd></>)}
            <dt>暂停</dt>
            <dd>
              {row.paused ? <Pill tone="danger">已暂停</Pill> : <Pill tone="muted">在运行</Pill>}
              {row.pause_record && (
                <div className="hint" style={{ marginTop: 4 }}>{row.pause_record.paused ? "暂停" : "恢复"}：{when(row.pause_record.changed_at)}，
                  <Staff id={row.pause_record.changed_by} />；原因：{row.pause_record.reason}</div>
              )}
              {canToggle ? (
                <div className="actions" style={{ marginTop: 6 }}>
                  <button className={row.paused ? "primary" : "danger"} onClick={async () => {
                    setActionError(null);
                    try { setDialog(await pauseSpec(row.pet_id, row.name)); } catch (exc) { setActionError(exc); }
                  }}>{row.paused ? "恢复自主运行" : "暂停自主运行"}</button>
                </div>
              ) : can("pet.maintain") ? (
                <div className="hint" style={{ marginTop: 4 }}>{!m.pause_open ? m.pause_closed_reason : "玩家自己的宠物暂不开放暂停：到点回复与主动来信还不认暂停。"}</div>
              ) : <div className="hint" style={{ marginTop: 4 }}>暂停与恢复要「<PermissionName code="pet.maintain" />」权限</div>}
            </dd>
          </dl>
        </div>
      </div>
      {dialog && <ReasonDialog spec={dialog} onClose={() => setDialog(null)} onDone={reload} />}
    </div>
  );
}
