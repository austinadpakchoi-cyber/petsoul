/**
 * 宠物运行：每只宠物（玩家的与驿站居民）的心跳、思考与决定、在做什么、钱袋子、今天的额度、是否暂停。
 * 只读已经记下的事实——这一页不评估心跳、不推进世界、不调模型（要看这一刻的评估，打开宠物页）。
 * 最上面先写清楚现在的运行方式：心跳是对照模式时「心跳按时」不等于「宠物在按心跳行动」。
 */
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { api } from "../api/client";
import type { PetRuntimeRow, PetsRuntimeView, SessionView } from "../api/types";
import { Player } from "../components/player";
import { Brain, Heartbeat, pauseSpec, Usage } from "../components/runtime";
import { ErrorNote, LaneStatePill, Pill, ReasonDialog, useAsync, when, type ConfirmSpec } from "../components/ui";
import { Code, PermissionName, Term } from "../labels";

const FILTERS: Record<string, { label: string; keep: (row: PetRuntimeRow) => boolean }> = {
  all: { label: "全部", keep: () => true },
  attention: { label: "需要留意（过点没看、思考卡住）", keep: (r) => r.heartbeat.state === "late" || r.brain.state === "stuck" },
  paused: { label: "已暂停", keep: (r) => r.paused },
  thinking: { label: "正在思考", keep: (r) => r.brain.state !== "idle" },
  trip: { label: "在路上", keep: (r) => r.trip !== null },
};

export default function PetsRuntimePage({ session }: { session: SessionView }) {
  const { data, error, loading, reload } = useAsync(() => api.get<PetsRuntimeView>("/pets-runtime"), []);
  const [kind, setKind] = useState("");
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [dialog, setDialog] = useState<ConfirmSpec | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const can = (p: string) => session.staff.permissions.includes(p);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data?.pets ?? []).filter((r) => (!kind || r.kind === kind) && FILTERS[filter].keep(r)
      && (!q || [r.name, r.pet_id, r.owner_name?.username, r.residence].some((v) => v?.toLowerCase().includes(q))));
  }, [data, kind, filter, query]);

  if (loading) return <div className="empty">读取中…</div>;
  if (error) return <ErrorNote error={error} />;
  if (!data) return null;
  const m = data.modes;

  const openPause = async (row: PetRuntimeRow) => {
    setActionError(null);
    try { setDialog(await pauseSpec(row.pet_id, row.name)); } catch (exc) { setActionError(exc); }
  };

  return (
    <>
      <div className="page-head">
        <h1>宠物运行</h1>
        <p>{data.notes.source}</p>
      </div>

      <div className="card">
        <h2>现在的运行方式</h2>
        <div className="card-body">
          <dl className="kv">
            <dt>世界推进</dt>
            <dd><Term family="world_runner" code={m.world_runner} />{" "}<LaneStatePill state={m.world_state} />
              {m.world_state !== "healthy" && <div className="hint">现在心跳和规则生活都不会动{m.world_state === "lost" ? "——按配置应该在跑，这是故障" : "（按配置关着，不是故障）"}。</div>}</dd>
            <dt>心跳</dt><dd><Term family="heartbeat_mode" code={m.heartbeat_mode} /></dd>
            <dt>AI 思考</dt>
            <dd><Term family="brain_mode" code={m.brain_mode} />{" "}
              <LaneStatePill state={m.cognition_state} /></dd>
            <dt>每只宠物每天</dt>
            <dd>AI 思考最多 {m.caps.brain_per_pet} 次；生图每个用途最多 {m.caps.image_per_pet} 张
              <div className="hint">今天＝{m.accounting_day}（UTC 记账日，北京时间 08:00 换日）</div></dd>
            <dt>暂停</dt>
            <dd>{m.pause_open ? "已开放：只对还在驿站生活的居民（玩家的宠物还要等回复与来信也认暂停）。"
              : <span className="hint">{m.pause_closed_reason}</span>}</dd>
          </dl>
        </div>
      </div>

      <div className="card">
        <div className="card-body" style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
          <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="按类型筛选" style={{ width: "auto" }}>
            <option value="">玩家的宠物与驿站居民</option>
            <option value="household">只看玩家的宠物</option>
            <option value="resident">只看驿站居民</option>
          </select>
          <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="按状态筛选" style={{ width: "auto" }}>
            {Object.entries(FILTERS).map(([key, f]) => <option key={key} value={key}>{f.label}</option>)}
          </select>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="按名字、玩家、驿站找" aria-label="按名字找" style={{ width: 220 }} />
        </div>
      </div>

      <ErrorNote error={actionError} />

      <div className="card">
        <h2>每只宠物<small>{rows.length} 只</small></h2>
        {rows.length === 0 ? <div className="empty">没有符合条件的宠物。</div> : (
          <table>
            <thead>
              <tr>
                <th>宠物</th><th>心跳（每轮评估）</th><th>思考与决定</th><th>在做什么</th>
                {data.sections.wallets && <th className="num">钱袋子</th>}
                {data.sections.usage && <th>今天的额度</th>}
                <th>暂停</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.pet_id}>
                  <td>
                    {can("pet.read") ? <Link to={`/pets/${row.pet_id}`}>{row.name ?? "（没有名字）"}</Link> : row.name}
                    <div className="hint"><Term family="species" code={row.species} /> · {row.kind === "resident"
                      ? <>驿站居民{row.residence ? `（${row.residence}）` : ""}</>
                      : row.owner_user_id ? <>玩家 <Player id={row.owner_user_id} name={row.owner_name} link={can("user.read")} /> 的</> : "玩家的"}
                      {row.kind === "household" && row.moved_in === false && <Pill tone="muted">还没入住</Pill>}</div>
                    <Code value={row.pet_id} />
                  </td>
                  <td><Heartbeat row={row} /></td>
                  <td><Brain row={row} /></td>
                  <td>{row.trip ? (
                    <>在路上：{row.trip.title ?? "—"}{row.trip.city ? `（${row.trip.city}）` : ""}
                      <div className="hint">{when(row.trip.departed_at)} 出发 · 预计 {when(row.trip.completes_at)} 回来</div></>
                  ) : <span className="hint">没有进行中的旅程</span>}</td>
                  {data.sections.wallets && <td className="num">{row.wallet == null ? <span className="hint">没有钱包</span> : `${row.wallet} 星币`}</td>}
                  {data.sections.usage && <td><Usage row={row} caps={m.caps} /></td>}
                  <td>
                    {row.paused ? <Pill tone="danger">已暂停</Pill> : <Pill tone="muted">在运行</Pill>}
                    {row.pause_record && (
                      <div className="hint" style={{ marginTop: 4 }}>{row.pause_record.paused ? "暂停" : "恢复"}于 {when(row.pause_record.changed_at)}：{row.pause_record.reason}</div>)}
                    {can("pet.maintain") && (row.paused || (m.pause_open && row.kind === "resident")) ? (
                      <div className="actions" style={{ marginTop: 6 }}>
                        <button className={row.paused ? "primary" : "ghost"} onClick={() => void openPause(row)}>{row.paused ? "恢复" : "暂停"}</button>
                      </div>
                    ) : !can("pet.maintain") ? null : (
                      <div className="hint" style={{ marginTop: 4 }}>{m.pause_open ? "玩家的宠物暂不开放暂停" : "暂不开放（见上方说明）"}</div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {!can("pet.maintain") && <div className="card-body"><span className="pill muted">暂停与恢复要「<PermissionName code="pet.maintain" />」权限</span></div>}
      </div>
      <p className="section-note">{data.sections.wallets && data.notes.wallet} {data.sections.usage && data.notes.usage}</p>

      {dialog && <ReasonDialog spec={dialog} onClose={() => setDialog(null)} onDone={reload} />}
    </>
  );
}
