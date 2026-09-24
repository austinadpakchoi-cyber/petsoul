/**
 * 宠物运行的共用展示：心跳、思考与决定、今天的额度、暂停对话框。「宠物运行」页与宠物页用同一套，口径一致。
 */
import { api } from "../api/client";
import type { PausePreview, PetRuntimeRow } from "../api/types";
import { Term } from "../labels";
import { Pill, when, type ConfirmSpec } from "./ui";

const HEARTBEAT_TONE: Record<string, "ok" | "warn" | "danger" | "muted"> = { ok: "ok", late: "warn", never: "muted", paused: "danger" };
const BRAIN_TONE: Record<string, "ok" | "warn" | "muted"> = { thinking: "ok", stuck: "warn", idle: "muted" };

/** 暂停 / 恢复的确认对话框：影响说明由后端按这只宠物与世界推进的实际情况给，这里不自己编。 */
export async function pauseSpec(petId: string, name: string | null): Promise<ConfirmSpec> {
  const preview = await api.get<PausePreview>(`/pets/${petId}/pause/preview`);
  const pausing = !preview.paused;
  return {
    title: `${pausing ? "暂停" : "恢复"}「${preview.name ?? name ?? petId}」的自主运行`,
    danger: pausing,
    confirmLabel: pausing ? "暂停" : "恢复",
    placeholder: pausing ? "例如：这位居民最近反复出门又马上回来，先暂停观察，排查完再恢复" : "例如：排查完了，行为正常，恢复运行",
    effects: pausing ? preview.pause_effects : preview.resume_effects,
    run: (reason, op) => api.post(`/pets/${petId}/pause`, { paused: pausing, reason, expected_version: preview.version }, op),
  };
}

export function Heartbeat({ row }: { row: PetRuntimeRow }) {
  const h = row.heartbeat;
  return (
    <>
      <Pill tone={HEARTBEAT_TONE[h.state] ?? "muted"}><Term family="heartbeat_state" code={h.state} /></Pill>
      <div className="hint" style={{ marginTop: 4 }}>
        {h.last_evaluated_at ? <>上次 {when(h.last_evaluated_at)}</> : "从来没评估过"}
        {h.next_check_at && <>，下次 {when(h.next_check_at)}</>}
      </div>
      {h.silence_reason && <div className="hint">安静原因：<Term family="silence" code={h.silence_reason} label={h.silence_label} /></div>}
    </>
  );
}

export function Brain({ row }: { row: PetRuntimeRow }) {
  const b = row.brain;
  return (
    <>
      <Pill tone={BRAIN_TONE[b.state] ?? "muted"}><Term family="brain_state" code={b.state} /></Pill>
      {b.started_at && <div className="hint" style={{ marginTop: 4 }}>从 {when(b.started_at)} 开始</div>}
      <div className="hint" style={{ marginTop: 4 }}>
        上次做决定：{b.last_decision_at ? <>{when(b.last_decision_at)}（<Term family="decided_by" code={b.last_decision_by} />）</> : "还没有"}
      </div>
      {row.rule_life && (
        <div className="hint">规则生活这个时段的决定：<Term code={row.rule_life.decision?.code} label={row.rule_life.decision?.label} />（{when(row.rule_life.at)}）
          {/* 「决定出门」在出发之前就记下，出发被拒也不撤回：没有进行中的旅程时两种可能都如实写，不猜是哪一种 */}
          {row.rule_life.decision?.code?.startsWith("go:") && !row.trip && <>；现在没有进行中的旅程：可能没走成，也可能已经回来了</>}
        </div>
      )}
    </>
  );
}

export function Usage({ row, caps }: { row: PetRuntimeRow; caps: { brain_per_pet: number; image_per_pet: number } }) {
  const u = row.usage_today ?? {};
  const line = (purpose: string, cap: number) => {
    const cell = u[purpose];
    const used = cell ? cell.used + cell.inflight : 0;
    return (
      <div key={purpose} style={{ fontSize: 12.5 }}>
        <Term family="purpose" code={purpose} />：{used} / {cap}
        {cell && cell.inflight > 0 && <span className="hint">（其中在途 {cell.inflight}）</span>}
        {used >= cap && <> <Pill tone="warn">到上限了</Pill></>}
      </div>
    );
  };
  // 插画、角色、证件照是三条独立的每宠车道，上限是同一个数、各算各的（config.web_image_per_pet_daily_cap）
  const fixed = ["life_plan", "illustration", "character", "id_photo"];
  // 其它用途（比如旅行心愿查资料）今天有计数也列出来：只写已用，上限按那一项自己的配置，这里不编
  const others = Object.keys(u).filter((purpose) => !fixed.includes(purpose)).sort();
  return <>{line("life_plan", caps.brain_per_pet)}{line("illustration", caps.image_per_pet)}{line("character", caps.image_per_pet)}{line("id_photo", caps.image_per_pet)}
    {others.map((purpose) => (
      <div key={purpose} style={{ fontSize: 12.5 }}>
        <Term family="purpose" code={purpose} />：已用 {u[purpose].used + u[purpose].inflight}
        {u[purpose].inflight > 0 && <span className="hint">（其中在途 {u[purpose].inflight}）</span>}
        <span className="hint">（上限按这一项自己的配置，这里不显示）</span>
      </div>
    ))}</>;
}
