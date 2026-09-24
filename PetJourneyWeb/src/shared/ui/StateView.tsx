import type { ReactNode } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import { Link } from "react-router";
import { isApiError, toApiError } from "@/shared/api/errors";
import { Icon, type IconName } from "./Icon";
import { Button } from "./primitives";

/** 统一的 loading / empty / error / disabled / pending 呈现。模块不自造各自的错误页。 */
export function LoadingState({ label = "正在接收信号…", lines = 3 }: { label?: string; lines?: number }) {
  return (
    <div className="ps-stack" aria-busy="true" aria-live="polite">
      <span className="visually-hidden">{label}</span>
      {Array.from({ length: lines }, (_, index) => (
        <div key={index} className="ps-skeleton" style={{ height: index === 0 ? 120 : 64 }} />
      ))}
    </div>
  );
}

export function EmptyState({ icon = "sparkle", title, children, action }: { icon?: IconName; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="ps-state">
      <div className="ps-state__icon">
        <Icon name={icon} />
      </div>
      <div className="ps-state__title">{title}</div>
      {children ? <div>{children}</div> : null}
      {action}
    </div>
  );
}

export function DisabledState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="ps-state ps-state--disabled">
      <div className="ps-state__icon">
        <Icon name="lock" />
      </div>
      <div className="ps-state__title">{title}</div>
      {children ? <div>{children}</div> : null}
    </div>
  );
}

/**
 * 错误码、request_id、能力名是给开发和客服看的，玩家页面默认收起（用户 2026-09-24 同意）：
 * 平时只见一句人话，需要反馈问题时展开“技术信息”再看。
 */
function TechDetails({ items }: { items: Array<string | null | undefined> }) {
  const text = items.filter(Boolean).join(" · ");
  if (!text) return null;
  return (
    <details className="ps-state__tech">
      <summary>技术信息</summary>
      <div className="ps-state__meta">{text}</div>
    </details>
  );
}

/**
 * 有的拒绝原因，后端原话里写着参数名（pet_required：“……请指明是哪一只（pet_id）。”）。按原因码换成人话，
 * 原话与原因码收进“技术信息”；后端把原话改好以后这里照样按原因码，不妨碍。
 */
const REASON_TEXT: Record<string, string> = {
  pet_required: "家里有不止一只伙伴，先选一只再看。",
  household_required: "你在不止一个家里，先选好是哪一个家再看。",
};

function plainReason(err: ReturnType<typeof toApiError>): { reason: string; text: string } | null {
  const reason = typeof err.details?.reason === "string" ? err.details.reason : null;
  if (!reason || !Object.prototype.hasOwnProperty.call(REASON_TEXT, reason)) return null;
  return { reason, text: REASON_TEXT[reason] };
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const err = toApiError(error);
  if (err.isCapabilityUnavailable) {
    const capability = typeof err.details?.capability === "string" ? err.details.capability : undefined;
    return (
      <DisabledState title="这里暂时还没开放">
        <p style={{ margin: 0 }}>准备好了会出现在这里。</p>
        <TechDetails items={[capability]} />
      </DisabledState>
    );
  }
  if (err.isAuth) {
    return (
      <div className="ps-state ps-state--error" role="alert">
        <div className="ps-state__icon">
          <Icon name="user" />
        </div>
        <div className="ps-state__title">{err.code === "SESSION_EXPIRED" ? "登录状态已过期" : "需要先登录"}</div>
        <div>{err.message}</div>
        <Link className="ps-btn ps-btn--primary" to="/login">
          去登录
        </Link>
        <TechDetails items={[err.requestId ? `request_id ${err.requestId}` : null]} />
      </div>
    );
  }
  const plain = plainReason(err);
  return (
    <div className="ps-state ps-state--error" role="alert">
      <div className="ps-state__icon">
        <Icon name="alert" />
      </div>
      <div className="ps-state__title">{(err.kind === "network" && !err.fromException) || err.kind === "timeout" || err.code === "UPSTREAM_UNAVAILABLE" ? "信号暂时中断" : err.isNotFound ? "没有找到" : "没能完成这一步"}</div>
      <div>{plain ? plain.text : err.playerMessage}</div>
      {onRetry ? (
        <Button variant="primary" icon="refresh" onClick={onRetry}>
          重试
        </Button>
      ) : null}
      <TechDetails items={[err.code, plain?.reason, plain || err.playerMessage !== err.message ? err.message : null, err.requestId ? `request_id ${err.requestId}` : null]} />
    </div>
  );
}

/** 查询结果的统一包装：loading → error → empty → data。 */
export function QueryView<T>({
  query,
  children,
  isEmpty,
  empty,
  loading,
}: {
  query: UseQueryResult<T>;
  children: (data: T) => ReactNode;
  isEmpty?: (data: T) => boolean;
  empty?: ReactNode;
  loading?: ReactNode;
}) {
  if (query.isPending) return <>{loading ?? <LoadingState />}</>;
  if (query.isError) return <ErrorState error={query.error} onRetry={isApiError(query.error) && !query.error.retryable ? undefined : () => void query.refetch()} />;
  if (isEmpty?.(query.data)) return <>{empty ?? <EmptyState title="这里还空着" />}</>;
  return <>{children(query.data)}</>;
}

export function PendingBadge({ label = "处理中" }: { label?: string }) {
  return (
    <span className="ps-chip ps-chip--sky" role="status">
      <Icon name="refresh" size={13} />
      {label}
    </span>
  );
}
