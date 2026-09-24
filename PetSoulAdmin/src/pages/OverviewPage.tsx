import { useState } from "react";
import { Link } from "react-router";
import { api } from "../api/client";
import type { OverviewView, SessionView } from "../api/types";
import { ErrorNote, LaneStatePill, Metric, ReasonDialog, useAsync, when, type ConfirmSpec } from "../components/ui";
import { Code, PermissionName, Staff, Tech, Term } from "../labels";

/** 问题指标对应的处理页面与它需要的权限。没权限就不给链接——不放会 403 的入口。 */
const DESTINATION: Record<string, { to: string; label: string; permission: string }> = {
  "photos.failed": { to: "/photos", label: "照片与任务", permission: "task.read" },
  "tasks.overdue": { to: "/photos", label: "照片与任务", permission: "task.read" },
  "tasks.failed": { to: "/photos", label: "照片与任务", permission: "task.read" },
  "reports.open": { to: "/reports", label: "举报审核", permission: "report.read" },
  "calls.unknown": { to: "/ledgers", label: "调用账", permission: "provider.read" },
  "accounts.frozen": { to: "/audit", label: "操作记录", permission: "audit.read" },
  "economy.mismatch": { to: "/economy/checks", label: "经济对账", permission: "economy.read" },
  "pets.paused": { to: "/pets-runtime", label: "宠物运行", permission: "pet.read" },
  "pets.thinking_stuck": { to: "/pets-runtime", label: "宠物运行", permission: "pet.read" },
  "pets.heartbeat_late": { to: "/pets-runtime", label: "宠物运行", permission: "pet.read" },
};

function destination(key: string, session: SessionView) {
  const hit = DESTINATION[key];
  if (!hit) return <span className="pill muted">—</span>;
  if (!session.staff.permissions.includes(hit.permission)) {
    return <span className="pill muted">需要「<PermissionName code={hit.permission} />」权限</span>;
  }
  return <Link to={hit.to}>{hit.label}</Link>;
}

/** 运营首页：先给"需要处理的问题"，再给全量指标与运行健康。每个数字都带来源，没有来源就写未接入。 */
export default function OverviewPage({ session }: { session: SessionView }) {
  const { data, error, loading, reload } = useAsync(() => api.get<OverviewView>("/overview"), []);
  const [dialog, setDialog] = useState<ConfirmSpec | null>(null);
  const canPause = session.staff.permissions.includes("provider.pause");

  if (loading) return <div className="empty">读取中…</div>;
  if (error) return <ErrorNote error={error} />;
  if (!data) return null;

  const aiSwitch = data.switches.find((item) => item.key === "ai_calls");
  const paused = aiSwitch?.state === "paused";

  return (
    <>
      <div className="page-head">
        <h1>运营首页</h1>
        <p>{data.read_only_note}</p>
      </div>

      <div className="card">
        <h2>需要处理<small>{data.attention.length === 0 ? "此刻没有待处理项" : `${data.attention.length} 项`}</small></h2>
        {data.attention.length === 0 ? (
          <div className="empty">没有积压、没有失败任务、没有待处理举报。</div>
        ) : (
          <table>
            <thead><tr><th>问题</th><th className="num">数量</th><th>去处理</th></tr></thead>
            <tbody>
              {data.attention.map((item) => (
                <tr key={item.key}>
                  <td>{item.label}{item.note && <div style={{ color: "var(--ink-faint)", fontSize: 12 }}>{item.note}</div>}
                    <Tech>数据来源：{item.source}</Tech></td>
                  <td className="num">{item.value}</td>
                  <td>{destination(item.key, session)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h2>环境与版本</h2>
        <div className="card-body">
          <dl className="kv">
            <dt>环境</dt><dd>{data.environment.environment === "production" ? "正式环境" : data.environment.environment === "staging" ? "预发环境" : "开发 / 演示环境"}<Code value={data.environment.environment} /></dd>
            <dt>后端版本</dt><dd>{data.environment.backend_version}</dd>
            <dt>服务器时间</dt><dd>{when(data.environment.server_time)}</dd>
            <dt>真实供应商</dt><dd>{data.environment.providers_enabled ? "已开启（会产生真实费用）" : "已关闭（不会产生真实费用）"}</dd>
            <dt>世界推进</dt><dd><Term family="world_runner" code={data.environment.world_runner} />{data.environment.world_tick_seconds ? `，每 ${data.environment.world_tick_seconds} 秒一轮` : ""}</dd>
            <dt>AI 思考</dt><dd>{data.environment.brain_mode === "off" ? "没有开启（按日常规则生活）" : <>已开启<Code value={data.environment.brain_mode} /></>}</dd>
          </dl>
          <Tech>数据库：{data.environment.database}</Tech>
        </div>
      </div>

      <div className="card">
        <h2>全部指标</h2>
        <div className="card-body">
          <div className="grid cols-4">
            {data.metrics.map((metric) => <Metric key={metric.key} metric={metric} />)}
          </div>
        </div>
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h2>运行健康</h2>
          <div className="card-body">
            <table>
              <thead><tr><th>哪条线</th><th>状态</th><th>这台机器上在跑</th><th>最近一轮</th><th className="num">跑了几轮</th></tr></thead>
              <tbody>
                {Object.entries(data.runtime.lanes).map(([name, lane]) => (
                  <tr key={name}>
                    <td><Term family="lane" code={name} /></td>
                    <td><LaneStatePill state={lane.state ?? (lane.lease_alive ? "healthy" : "lost")} /></td>
                    <td>{lane.running_here ? "是" : "否"}</td>
                    <td>{when(lane.last_tick_at)}{lane.last_error && <div className="pill danger">{lane.last_error}</div>}</td>
                    <td className="num">{lane.ticks}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p style={{ color: "var(--ink-faint)", fontSize: 12, margin: "10px 0 0" }}>
              网站能打开不代表后台在干活：这里看的是执行者的登记与实际跑了几轮。到期的事平均晚了 {data.runtime.due_lag_seconds ?? "—"} 秒。更多在「系统运行」页。
            </p>
          </div>
        </div>

        <div className="card">
          <h2>受控开关</h2>
          <div className="card-body">
            <dl className="kv">
              <dt>新增 AI 调用</dt>
              <dd>{paused ? <span className="pill danger">已暂停</span> : <span className="pill ok">正常</span>}
                {aiSwitch?.reason && <div style={{ color: "var(--ink-soft)", fontSize: 12 }}>原因：{aiSwitch.reason}</div>}</dd>
              <dt>最近改动</dt><dd>{when(aiSwitch?.changed_at)}{aiSwitch?.changed_by && <> · <Staff id={aiSwitch.changed_by} /></>}</dd>
            </dl>
            <div className="actions" style={{ marginTop: 12 }}>
              <button
                className={paused ? "primary" : "danger"}
                disabled={!canPause}
                onClick={() => setDialog({
                  title: paused ? "恢复新增 AI 调用" : "暂停新增 AI 调用",
                  danger: !paused,
                  confirmLabel: paused ? "恢复" : "暂停",
                  effects: paused
                    ? ["之后的付费调用会照常发出。", "被暂停期间挡下的调用不会自动补发。"]
                    : ["还没发出的付费调用会被直接挡住（等同到了每日上限）。",
                       "在途的调用不受影响，已经记下的用量和 unknown 一条都不动。",
                       "这不影响游戏经济，也不会退款。"],
                  run: (reason, op) => api.post("/switches/ai_calls",
                    { state: paused ? "active" : "paused", reason, expected_version: aiSwitch?.version ?? 0 }, op),
                })}
              >
                {paused ? "恢复新增调用" : "暂停新增调用"}
              </button>
              {!canPause && <span className="pill muted">需要「<PermissionName code="provider.pause" />」权限</span>}
            </div>
          </div>
        </div>
      </div>

      {dialog && <ReasonDialog spec={dialog} onClose={() => setDialog(null)} onDone={reload} />}
    </>
  );
}
