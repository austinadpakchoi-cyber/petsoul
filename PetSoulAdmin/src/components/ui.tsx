/** 后台通用小部件：状态标、指标卡、错误条、带原因的确认框、异步数据钩子。 */
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { AdminError, newOperationId, outcomeUnknown } from "../api/client";
import type { MetricView, ValidationIssue } from "../api/types";
import { Tech, Term } from "../labels";

export function Pill({ tone, children }: { tone: "ok" | "warn" | "danger" | "unknown" | "muted"; children: ReactNode }) {
  return <span className={`pill ${tone}`}>{children}</span>;
}

/** 照片/调用的状态标。unknown 单独一色：它既不是成功也不是失败。 */
export function CallStatePill({ state }: { state: string }) {
  const map: Record<string, { tone: "ok" | "warn" | "danger" | "unknown" | "muted"; label: string }> = {
    ready: { tone: "ok", label: "已出图" },
    processing: { tone: "warn", label: "处理中" },
    failed: { tone: "danger", label: "没画成" },
    unknown: { tone: "unknown", label: "结果未确认" },
  };
  const hit = map[state] ?? { tone: "muted" as const, label: state };
  return <Pill tone={hit.tone}>{hit.label}</Pill>;
}

export function Metric({ metric }: { metric: MetricView }) {
  const alert = metric.available && (metric.value ?? 0) > 0 &&
    ["tasks.overdue", "tasks.failed", "photos.failed", "reports.open", "calls.unknown", "accounts.frozen",
     "pets.paused", "pets.thinking_stuck", "pets.heartbeat_late"].includes(metric.key);
  // 没有值：后端给了说明的是「此刻不适用」（比如世界推进没在跑时的「心跳过点」），没给的才是「未接入」
  const empty = metric.note ? "不适用" : "未接入";
  return (
    <div className={`metric${alert ? " alert" : ""}`}>
      <div className={metric.available ? "value" : "value na"}>{metric.available ? metric.value : empty}</div>
      <div className="label">{metric.label}</div>
      {!metric.available && metric.note && <div className="source">{metric.note}</div>}
      {metric.window && <div className="source">{metric.window}</div>}
      <Tech>数据来源：{metric.source}</Tech>
    </div>
  );
}

/** 执行者状态（按配置判）：按配置关着是灰色、不是故障；应该在跑却失联才标红。 */
export function LaneStatePill({ state }: { state: string | undefined }) {
  const tone = state === "healthy" ? "ok" : state === "lost" ? "danger" : "muted";
  return <Pill tone={tone}><Term family="lane_state" code={state} /></Pill>;
}

/** 错误条：说清原因、影响与下一步，带 request_id 方便对日志；不显示堆栈或原始 JSON。 */
export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  if (error instanceof AdminError) {
    const issues = (error.details?.issues as ValidationIssue[] | undefined) ?? [];
    return (
      // 结果没有定论（没连上、服务端出错、同号仍在处理）用 unknown 色：它不是失败，别画成红色的失败
      <div className={`note ${error.code === "NOT_RECOVERABLE" ? "warn" : outcomeUnknown(error) ? "unknown" : "danger"}`}>
        <strong>{error.message}</strong>
        <span className="rid">{error.code} · {error.requestId}</span>
        {issues.length > 0 && (
          <ul className="effects">{issues.map((issue) => <li key={issue.field}>{issue.field}：{issue.message}</li>)}</ul>
        )}
        {error.code === "NOT_RECOVERABLE" && error.details?.call_state === "unknown" && (
          <div style={{ marginTop: 6 }}>结果未确认不等于没发出去。请先向供应商核对这一次调用，再由人决定怎么处理。</div>
        )}
        {error.code === "IDEMPOTENCY_KEY_REUSED" && (
          <div style={{ marginTop: 6 }}>这个操作号之前已经以不同的内容执行过了；为防止重复执行，后台拒绝了这一次。请刷新页面查看实际结果。</div>
        )}
      </div>
    );
  }
  return <div className="note danger">{String((error as Error).message ?? error)}</div>;
}

export function useAsync<T>(loader: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);
  const reload = useCallback(() => setNonce((n) => n + 1), []);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    loader()
      .then((value) => { if (alive) { setData(value); setError(null); } })
      .catch((exc) => { if (alive) setError(exc); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);
  return { data, error, loading, reload };
}

export interface ConfirmSpec {
  title: string;
  effects: string[];
  confirmLabel: string;
  danger?: boolean;
  /** 原因框里的示例（按场景写；不给就用一句通用提示）。 */
  placeholder?: string;
  /** `operationId` 是这一次操作的固定操作号：对话框打开时生成一次，重试沿用。调用方必须把它原样传给接口。 */
  run: (reason: string, operationId: string) => Promise<unknown>;
}

/** 结果没有定论时的提示：可能已经生效；内容锁定，只能用同一个操作号重试。 */
export function PendingOutcomeNote({ operationId }: { operationId: string }) {
  return (
    <div className="note unknown">
      <strong>上一次提交的结果没有确认</strong>——它可能已经生效了。内容已锁定，
      重试会带同一个操作号 <span className="mono">{operationId}</span>：已经生效的话只会拿回那一次的结果，不会再执行一次。
      也可以关掉对话框，刷新后看实际状态再决定。
    </div>
  );
}

/** 写操作统一走这里：先看影响预览，再写原因，才能提交。原因会进审计。 */
export function ReasonDialog({ spec, onClose, onDone }: { spec: ConfirmSpec; onClose: () => void; onDone: (result: unknown) => void }) {
  const [operationId] = useState(() => newOperationId("op"));
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  // 结果未确认：锁住原因（它是请求内容的一部分，改了就成了另一次操作），只允许同号重试。
  const [pending, setPending] = useState(false);
  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      onDone(await spec.run(reason.trim(), operationId));
      onClose();
    } catch (exc) {
      setError(exc);
      if (outcomeUnknown(exc)) setPending(true);
    } finally {
      setBusy(false);
    }
  };
  const close = () => {
    if (pending) onDone(null);  // 可能已经生效：关掉时让页面按服务器的实际状态刷新
    onClose();
  };
  return (
    <div className="overlay" role="dialog" aria-modal="true">
      <div className="dialog">
        <h2>{spec.title}</h2>
        <div className="dialog-body">
          <ErrorNote error={error} />
          {pending && <PendingOutcomeNote operationId={operationId} />}
          <ul className="effects">{spec.effects.map((line) => <li key={line}>{line}</li>)}</ul>
          <div className="field">
            <label htmlFor="reason">处理原因（必填，至少 4 个字，会写进审计）</label>
            <textarea id="reason" value={reason} readOnly={pending} onChange={(e) => setReason(e.target.value)}
                      placeholder={spec.placeholder ?? "写清楚为什么要这样做、依据是什么（会写进审计）"} />
          </div>
        </div>
        <div className="dialog-foot">
          <button className="ghost" onClick={close} disabled={busy}>{pending ? "关闭并刷新" : "取消"}</button>
          <button className={spec.danger ? "danger" : "primary"} onClick={submit} disabled={busy || reason.trim().length < 4}>
            {busy ? "提交中…" : pending ? "用同一操作号重试" : spec.confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export function when(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}
