import { useState } from "react";
import { Link, useParams } from "react-router";
import { api } from "../api/client";
import type { DiagnosisView, JourneyLegView, JourneyVisitView, PhotoAttemptView, SessionView } from "../api/types";
import { CallStatePill, ErrorNote, Pill, ReasonDialog, useAsync, when, type ConfirmSpec } from "../components/ui";
import { Code, Tech, Term, useSilenceHint } from "../labels";
import { PetBelongings } from "./PetBelongings";
import { PetLedgers } from "./PetLedgers";
import { PetRuntimeRecord } from "./PetRuntimeRecord";

// silence_kind 由后端直接给说法（diagnosis.py 的 KIND_LABEL），这里按说法配颜色，不再查词表
const KIND_TONE: Record<string, "ok" | "warn" | "danger"> = { 正常: "ok", 已推迟: "warn", 故障: "danger" };

/**
 * 宠物诊断：TA 为什么没动静、照片走到哪一步、TA 有什么东西。整页只读。
 * 说的都是人话；原始代码、编号在右上角「显示技术代码」里。
 */
export default function PetPage({ session }: { session: SessionView }) {
  const { petId = "" } = useParams();
  const { data, error, loading, reload } = useAsync(() => api.get<DiagnosisView>(`/pets/${petId}/diagnosis`), [petId]);
  const [dialog, setDialog] = useState<ConfirmSpec | null>(null);
  const hint = useSilenceHint();
  const can = (permission: string) => session.staff.permissions.includes(permission);

  if (loading) return <div className="empty">读取中…</div>;
  if (error) return <ErrorNote error={error} />;
  if (!data) return null;

  const sleep = data.place?.sleep_window?.length === 2 ? `${data.place.sleep_window[0]} 睡 – ${data.place.sleep_window[1]} 起` : null;
  const reasons = data.reasons ?? data.heartbeat?.reason_codes?.map((code) => ({ code, label: null })) ?? [];

  return (
    <>
      <div className="page-head">
        <h1>{data.pet?.name ?? petId}</h1>
        <Code value={petId} />
        {data.owner_user_id && <Link to={`/users/${data.owner_user_id}`}>看照顾人</Link>}
      </div>

      <div className="card">
        <h2>TA 现在怎么样<small>按此刻的事实判断一次：不执行、不记录、不调用模型</small></h2>
        <div className="card-body">
          {!data.available ? (
            <div className="note warn"><strong>{data.headline}</strong><br />{data.unavailable_reason}</div>
          ) : (
            <>
              <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 6 }}>
                <span style={{ fontSize: 18, fontWeight: 650 }}>{data.headline}</span>
                {data.silence_kind && <Pill tone={KIND_TONE[data.silence_kind] ?? "muted"}>{data.silence_kind}</Pill>}
                <Code value={data.silence_reason} />
              </div>
              <p style={{ margin: "0 0 12px", color: "var(--ink-soft)" }}>{hint(data.silence_reason) ?? data.detail}</p>
              <dl className="kv">
                <dt>在哪儿</dt>
                <dd>{data.place_label ?? data.place.region_id ?? "不知道"}
                  {data.place.timezone ? "" : <span className="unlabeled">时区未知</span>}
                  <Code value={[data.place.region_id, data.place.timezone].filter(Boolean).join(" · ")} /></dd>
                <dt>当地作息</dt><dd>{sleep ?? "—"}</dd>
                <dt>此刻在做</dt>
                <dd><Term family="activity" code={data.activity.kind} />{data.activity.ends_at ? `，预计到 ${when(data.activity.ends_at)}` : ""}
                  {!data.activity.interruptible && <span className="hint">（现在不能打断）</span>}
                  <Tech>{data.activity.ref}</Tech></dd>
                <dt>上次做决定</dt>
                <dd>{data.heartbeat.last_decision_at ? when(data.heartbeat.last_decision_at) : "还没有做过决定"}
                  {data.heartbeat.last_decision_by && <>（<Term family="decided_by" code={data.heartbeat.last_decision_by} />）</>}</dd>
                <dt>下次复查</dt><dd>{when(data.heartbeat.next_review_at ?? data.heartbeat.next_check_at)}</dd>
                <dt>这一次的判断</dt>
                <dd><Term family="heartbeat_action" code={data.heartbeat.action} />
                  {reasons.length > 0 && (
                    <div className="hint">依据：{reasons.map((r, i) => (
                      <span key={r.code}>{i > 0 && "；"}<Term code={r.code} label={r.label} /></span>))}</div>
                  )}</dd>
                <dt>暂停</dt><dd>{data.heartbeat.maintenance ? <Pill tone="warn">已暂停：不做新的生活决定</Pill> : "没有"}</dd>
              </dl>
            </>
          )}
          <div className="note plain" style={{ marginTop: 12 }}>{data.read_only_note}</div>
        </div>
      </div>

      <PetRuntimeRecord petId={petId} session={session} />

      <div className="grid cols-2">
        <div className="card">
          <h2>等着要办的事<small>{data.due_items.length} 件</small></h2>
          {data.due_items.length === 0 ? <div className="empty">没有到期还没办的事。</div> : (
            <table>
              <thead><tr><th>事情</th><th>什么时候到期</th><th>答应过家人</th></tr></thead>
              <tbody>
                {data.due_items.map((item) => (
                  <tr key={item.ref}>
                    <td><Term family="due_kind" code={item.kind} /><Tech>{item.ref}</Tech></td>
                    <td>{when(item.due_at)}</td>
                    <td>{item.commitment ? <Pill tone="warn">是，答应过家人</Pill> : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="card">
          <h2>照顾人的设置<small>只看开关，不看任何内容</small></h2>
          <div className="card-body">
            <dl className="kv">
              {(data.consent_rows ?? Object.entries(data.consent).map(([key, value]) => ({ key, label: null, value }))).map((row) => (
                <div key={row.key} style={{ display: "contents" }}>
                  <dt><Term code={row.key} label={row.label} /></dt>
                  <dd>{row.key === "owner_user_id" && typeof row.value === "string" ? <Link to={`/users/${row.value}`}>打开照顾人</Link>
                    : row.key === "household_id" ? (row.value ? <>已加入家庭<Code value={String(row.value)} /></> : "没有家庭（待领养的居民）")
                    : row.value === null ? <Pill tone="muted">没设置过</Pill>
                    : typeof row.value === "boolean" ? <Pill tone={row.value ? "ok" : "muted"}>{row.value ? "开" : "关"}</Pill>
                    : String(row.value)}</dd>
                </div>
              ))}
            </dl>
            <p className="section-note">后台不能替用户打开照片或 AI 的授权。</p>
          </div>
        </div>
      </div>

      {data.journey && (
        <div className="card">
          <h2>最近一段旅程<small>{data.journey.title} · {data.journey.city} · <Term family="journey_lifecycle" code={data.journey.lifecycle} label={data.journey.lifecycle_label} /></small></h2>
          <table>
            <thead><tr><th>发生了什么</th><th>什么时候</th></tr></thead>
            <tbody>
              {data.journey.recent_events.map((event) => (
                <tr key={event.event_key}>
                  <td><Term family="world_event" code={event.kind} label={event.label} /><Tech>{event.event_key}</Tech></td>
                  <td>{when(event.occurred_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.journey.legs && data.journey.legs.length > 0 && <JourneyLegs legs={data.journey.legs} />}
          {data.journey.visits && data.journey.visits.length > 0 && <JourneyVisits visits={data.journey.visits} />}
        </div>
      )}

      <div className="card">
        <h2>照片<small>{data.photos.length} 张</small></h2>
        {data.photos.length === 0 ? <div className="empty">这只宠物还没有照片。</div> : (
          <table>
            <thead><tr><th>结果</th><th>用在哪里</th><th>进度</th><th>生图调用</th><th>最近更新</th><th>能做什么</th></tr></thead>
            <tbody>
              {data.photos.map((photo) => (
                <PhotoRow key={photo.illustration_id} photo={photo} canRecover={can("task.recover")} onRecover={() => setDialog({
                  title: "受控恢复这张照片",
                  placeholder: "例如：用户反馈照片一直没出来，供应商已恢复，重排一次",
                  confirmLabel: "恢复一次",
                  effects: ["只排一次新的尝试，已用的次数不清零。",
                            "提交后只表示已受理：任务进了队列，还没开始画。",
                            "如果上一次调用的结果还没确认，系统会拒绝，不会替你重发。"],
                  run: (reason, op) => api.post(`/photos/${photo.illustration_id}/recover`, { reason }, op),
                })} />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {can("pet.read") && <PetBelongings petId={petId} />}
      <PetLedgers petId={petId} permissions={session.staff.permissions} />

      {dialog && <ReasonDialog spec={dialog} onClose={() => setDialog(null)} onDone={reload} />}
    </>
  );
}

/** 一张照片的一行：结果、用在哪里、卡在哪一步、调用算了几次、能做什么。宠物页与「照片与任务」页共用。 */
export function PhotoRow({ photo, canRecover, onRecover, showPet = false }: {
  photo: PhotoAttemptView; canRecover: boolean; onRecover: () => void; showPet?: boolean;
}) {
  return (
    <tr>
      <td><CallStatePill state={photo.call_state} /><Tech>{photo.illustration_id}</Tech></td>
      {showPet && <td><Link to={`/pets/${photo.pet_id}`}>打开宠物</Link><Code value={photo.pet_id} /></td>}
      <td><PhotoSurfaces photo={photo} /></td>
      <td>
        <Term family="task_status" code={photo.task_status} fallback="没有任务记录" />
        {photo.attempts != null && <span className="hint">（第 {photo.attempts} 次，最多 {photo.max_attempts ?? "—"} 次）</span>}
        {photo.last_error && (
          <div className="pill danger" style={{ marginTop: 4, whiteSpace: "normal" }}>{photo.error_label ?? photo.last_error}</div>
        )}
        {photo.error_label && <Tech>{photo.last_error}</Tech>}
        <Tech>{photo.task_id}</Tech>
      </td>
      <td>
        {photo.reservations.length === 0 ? <span className="hint">没有调用记录</span> : photo.reservations.map((r) => (
          <div key={r.operation_id} style={{ fontSize: 12.5 }}>
            <Term family="purpose" code={r.purpose} /> · <Term family="reservation_status" code={r.status} />
            {r.status === "released" ? "" : r.counted_units === null ? "（还在途，暂不计入）" : `，计入 ${r.counted_units} 次`}
            <Tech>{r.operation_id}{r.provider_request_id ? ` · ${r.provider_request_id}` : ""}</Tech>
          </div>
        ))}
      </td>
      <td>{when(photo.updated_at)}</td>
      <td>
        {photo.recoverable && canRecover ? <button onClick={onRecover}>恢复一次</button>
          : photo.call_state === "unknown" ? <span className="pill unknown" title="结果未确认不等于没发出去：先向供应商核对">不自动重发</span>
          : photo.recoverable ? <span className="pill muted">需要「受控恢复失败的任务」权限</span>
          : <span className="pill muted">—</span>}
      </td>
    </tr>
  );
}

function PhotoSurfaces({ photo }: { photo: PhotoAttemptView }) {
  if (photo.surfaces == null) return <span className="hint">查不了（这个库还没有这些记录）</span>;
  if (photo.surfaces.length === 0) return <span className="hint">没找到用在哪里</span>;
  return (
    <>
      {photo.surfaces.map((surface) => (
        <div key={`${surface.kind}:${surface.ref}`}>
          <Term family="photo_surface" code={surface.kind} />
          {surface.kind === "keepsake" && surface.item_kind && <>：<Term family="collection_kind" code={surface.item_kind} /></>}
          {surface.city ? ` · ${surface.city}` : ""}{surface.at ? ` · ${when(surface.at)}` : ""}
          <Code value={surface.ref} />
        </div>
      ))}
    </>
  );
}

/** 逐段交通：去程 / 回程每一段怎么走、从哪到哪、几点出发几点到；此刻在哪一段标出来。时间的依据如实写（演示时间还是核实过的时刻表）。 */
function JourneyLegs({ legs }: { legs: JourneyLegView[] }) {
  const now = Date.now();
  return (
    <>
      <h3 className="subhead">逐段交通</h3>
      <table>
        <thead><tr><th>哪一段</th><th>怎么走</th><th>从哪到哪</th><th>出发</th><th>到达</th><th>时间的依据</th></tr></thead>
        <tbody>
          {legs.map((leg) => {
            const current = leg.starts_at && leg.ends_at && Date.parse(leg.starts_at) <= now && now < Date.parse(leg.ends_at);
            return (
              <tr key={leg.leg_id}>
                <td><Term family="leg_direction" code={leg.direction} /> · <Term family="leg_kind" code={leg.kind} />
                  {current && <Pill tone="warn">此刻在这一段</Pill>}<Code value={leg.leg_id} /></td>
                <td><Term family="transport_mode" code={leg.mode} /><div className="hint"><Term family="traveller_role" code={leg.role} /></div></td>
                <td>{leg.from ?? "—"} → {leg.to ?? "—"}</td>
                <td>{when(leg.starts_at)}</td>
                <td>{when(leg.ends_at)}</td>
                <td><Term family="time_basis" code={leg.time_basis} />
                  <div className="hint"><Term family="data_freshness" code={leg.freshness} /> · <Term family="position_basis" code={leg.position_basis} /></div></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </>
  );
}

/** 到店：店名、几点到几点走、店里的几件事做到哪了（不看活动的结果文字，那是写给玩家的故事）。 */
function JourneyVisits({ visits }: { visits: JourneyVisitView[] }) {
  return (
    <>
      <h3 className="subhead">到店</h3>
      {visits.map((visit) => (
        <div key={visit.visit_id} className="card-body" style={{ paddingTop: 0 }}>
          <strong>{visit.place ?? "（没有店名）"}</strong>
          <span className="hint"> · <Term family="venue_template" code={visit.template} /> · {when(visit.starts_at)} – {when(visit.ends_at)}</span>
          <Code value={visit.visit_id} />
          <div style={{ marginTop: 4 }}>
            {visit.activities.map((a) => (
              <span key={a.kind} style={{ marginRight: 10 }}>
                {a.label ?? <Term family="visit_activity" code={a.kind} />}：<Term family="visit_activity_state" code={a.state} />
              </span>
            ))}
          </div>
        </div>
      ))}
    </>
  );
}
