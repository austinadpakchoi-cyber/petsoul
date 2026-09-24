/**
 * 系统运行：事件投递、后台执行者、任务线、迁移版本、供应商健康、AI 开关、备份。只读，不重试、不改任何东西。
 * 「网站能打开」不代表后台执行者在干活：执行者单列，心跳过期就标出来。备份没有可读来源就写「未接入」，不写「正常」。
 */
import { api } from "../api/client";
import type { SystemView } from "../api/types";
import { ErrorNote, LaneStatePill, Pill, useAsync, when } from "../components/ui";
import { Code, Tech, Term } from "../labels";

export default function SystemPage() {
  const { data, error, loading, reload } = useAsync(() => api.get<SystemView>("/system"), []);
  if (loading) return <div className="empty">读取中…</div>;
  if (error) return <ErrorNote error={error} />;
  if (!data) return null;
  const env = data.environment;

  return (
    <>
      <div className="page-head">
        <h1>系统运行</h1>
        <p>只读：{when(data.as_of)} 的状态。这一页不重试、不改任何东西。</p>
        <button className="ghost" onClick={reload}>刷新</button>
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h2>环境与版本</h2>
          <div className="card-body">
            <dl className="kv">
              <dt>环境</dt><dd>{env.environment === "production" ? "正式环境" : env.environment === "staging" ? "预发环境" : "开发 / 演示环境"}<Code value={env.environment} /></dd>
              <dt>后端版本</dt><dd>{env.backend_version}</dd>
              <dt>真实供应商</dt><dd>{env.providers_enabled ? <Pill tone="warn">已开启（会产生真实费用）</Pill> : <Pill tone="ok">已关闭（不会产生真实费用）</Pill>}</dd>
              <dt>世界推进</dt><dd><Term family="world_runner" code={env.world_runner} />{env.world_tick_seconds ? `，每 ${env.world_tick_seconds} 秒一轮` : ""}</dd>
              <dt>AI 思考</dt><dd>{env.brain_mode === "off" ? "没有开启（按日常规则生活）" : <>已开启<Code value={env.brain_mode} /></>}</dd>
            </dl>
            <Tech>数据库：{env.database}</Tech>
          </div>
        </div>

        <div className="card">
          <h2>开关与备份</h2>
          <div className="card-body">
            <dl className="kv">
              {data.switches.map((sw) => (
                <div key={sw.key} style={{ display: "contents" }}>
                  <dt>{sw.key === "ai_calls" ? "新增 AI 调用" : sw.key}</dt>
                  <dd>{sw.state === "paused" ? <Pill tone="danger">已暂停</Pill> : <Pill tone="ok">正常</Pill>}
                    {sw.reason && <div className="hint">原因：{sw.reason}</div>}</dd>
                </div>
              ))}
              <dt>备份</dt><dd><Pill tone={data.backups.available ? "ok" : "muted"}>{data.backups.available ? "已接入" : "未接入"}</Pill>
                <div className="hint">{data.backups.note}</div></dd>
            </dl>
            <p className="section-note">暂停 / 恢复在「运营首页」操作（要「暂停 / 恢复新增 AI 调用」权限，会写审计）。</p>
          </div>
        </div>
      </div>

      <div className="card">
        <h2>后台执行者<small>网站能打开不代表它们在干活</small></h2>
        {data.workers === null ? <div className="empty">这个库里还没有执行者记录，查不了。</div>
          : data.workers.length === 0 ? <div className="empty">现在没有执行者登记在岗（演示环境默认不开世界推进）。</div> : (
          <table>
            <thead><tr><th>哪条线</th><th>状态</th><th>最后一次心跳</th><th>最后一次成功</th><th className="num">跑了几轮</th></tr></thead>
            <tbody>
              {data.workers.map((w) => (
                <tr key={w.name}>
                  <td><Term family="lane" code={w.name} /> <span className="hint">（<Term family="worker_role" code={w.role} />）</span>
                    <Tech>{w.holder} · {w.host} · pid {w.pid}</Tech></td>
                  <td><LaneStatePill state={w.state ?? (w.alive ? "healthy" : "lost")} />
                    {w.state === "configured_off" && w.heartbeat_at && <div className="hint">最后一次心跳保留着，供查询</div>}
                    {w.state === "lost" && !w.registered && <div className="hint">应该在跑，但从没登记过</div>}
                    {w.last_error && <div className="pill danger" style={{ marginTop: 4, whiteSpace: "normal" }}>{w.last_error}</div>}</td>
                  <td>{when(w.heartbeat_at)}</td>
                  <td>{when(w.last_ok_at)}</td>
                  <td className="num">{w.ticks}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h2>事件投递<small>{data.outbox ? `待投递 ${data.outbox.pending_total} 条` : ""}</small></h2>
          {data.outbox === null ? <div className="empty">这个库里还没有投递记录，查不了。</div> : (
            <>
              <table>
                <thead><tr><th>投给谁</th><th className="num">待投递</th><th className="num">已投递</th><th className="num">已放弃</th><th>等得最久的</th></tr></thead>
                <tbody>
                  {data.outbox.consumers.map((c) => (
                    <tr key={c.consumer}>
                      <td><Term family="outbox_consumer" code={c.consumer} /></td>
                      <td className="num">{c.pending > 0 ? <Pill tone="warn">{c.pending}</Pill> : 0}</td>
                      <td className="num">{c.delivered}</td>
                      <td className="num">{(c.dead_letter ?? 0) > 0 ? <Pill tone="danger">{c.dead_letter}</Pill> : 0}</td>
                      <td>{c.oldest_pending_at ? when(c.oldest_pending_at) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {(data.outbox.dead ?? []).length > 0 && (
                <div className="card-body">
                  <div className="note danger">有 {data.outbox.dead_total} 条投递失败次数太多、已经放弃（死信）：不会再自动投递，要技术同学查原因后处理。最近的：</div>
                  {data.outbox.dead!.map((d, i) => (
                    <div key={i} style={{ fontSize: 12.5, marginTop: 4 }}>
                      <Term family="outbox_consumer" code={d.consumer} /> · 试了 {d.attempts} 次 · 登记于 {when(d.created_at)}
                      <Tech>{d.kind} · {d.last_error}</Tech>
                    </div>
                  ))}
                </div>
              )}
              {data.outbox.failing.length > 0 && (
                <div className="card-body">
                  <div className="note warn">有 {data.outbox.failing.length} 条在反复投递失败：</div>
                  {data.outbox.failing.map((f, i) => (
                    <div key={i} style={{ fontSize: 12.5, marginTop: 4 }}>
                      <Term family="outbox_consumer" code={f.consumer} /> · 已试 {f.attempts} 次 · 下次 {when(f.next_attempt_at)}
                      <Tech>{f.kind} · {f.last_error}</Tech>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        <div className="card">
          <h2>任务线</h2>
          {data.tasks === null ? <div className="empty">这个库里还没有任务记录，查不了。</div> : (
            <div className="card-body">
              <table>
                <thead><tr><th>什么任务</th><th>状态</th><th className="num">数量</th></tr></thead>
                <tbody>
                  {data.tasks.counts.map((row) => (
                    <tr key={`${row.kind}:${row.status}`}>
                      <td><Term family="task_kind" code={row.kind} /></td>
                      <td><Term family="task_status" code={row.status} /></td>
                      <td className="num">{row.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {data.tasks.overdue.length > 0 ? (
                <div className="note warn" style={{ marginTop: 10 }}>
                  到点了还没执行：{data.tasks.overdue.map((o) => `${o.count} 个（最早 ${when(o.oldest_run_after)}）`).join("，")}。
                  执行者不在岗时就会这样。
                </div>
              ) : <p className="section-note">没有到点还没执行的任务。</p>}
              {data.tasks.recent_failures.length > 0 && (
                <p className="section-note">最近失败 {data.tasks.recent_failures.length} 个，具体原因在「照片与任务」页或对应宠物页。</p>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h2>外部服务的健康</h2>
          {data.providers === null ? <div className="empty">查不了。</div> : data.providers.length === 0 ? (
            <div className="empty">还没有任何外部服务的调用记录（演示环境默认全关）。</div>
          ) : (
            <table>
              <thead><tr><th>服务</th><th>最近成功</th><th>最近失败</th></tr></thead>
              <tbody>
                {data.providers.map((p) => (
                  <tr key={p.provider}>
                    <td><Term family="provider" code={p.provider} /></td>
                    <td>{when(p.last_success_at)}</td>
                    <td>{when(p.last_failure_at)}<Tech>{p.last_error}</Tech></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="card">
          <h2>数据库版本</h2>
          {data.migrations === null ? <div className="empty">查不了。</div> : (
            <div className="card-body">
              <p style={{ margin: 0 }}>一共做过 {data.migrations.count} 次数据库结构升级，最近一次在 {when(data.migrations.latest[0]?.applied_at)}。</p>
              <Tech>{data.migrations.latest.map((m) => <div key={m.migration_id}>{m.migration_id}：{m.description ?? ""}</div>)}</Tech>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
