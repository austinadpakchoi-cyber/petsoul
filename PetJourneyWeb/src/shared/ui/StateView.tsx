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

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const err = toApiError(error);
  if (err.isCapabilityUnavailable) {
    const capability = typeof err.details?.capability === "string" ? err.details.capability : undefined;
    return (
      <DisabledState title="这里还在搭建中">
        <p style={{ margin: 0 }}>这项能力尚未接入，接入后会在这里出现。</p>
        {capability ? <div className="ps-state__meta">{capability}</div> : null}
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
        {err.requestId ? <div className="ps-state__meta">request_id {err.requestId}</div> : null}
      </div>
    );
  }
  return (
    <div className="ps-state ps-state--error" role="alert">
      <div className="ps-state__icon">
        <Icon name="alert" />
      </div>
      <div className="ps-state__title">{err.kind === "network" || err.kind === "timeout" || err.code === "UPSTREAM_UNAVAILABLE" ? "信号暂时中断" : "没能完成这一步"}</div>
      <div>{err.message}</div>
      {onRetry ? (
        <Button variant="primary" icon="refresh" onClick={onRetry}>
          重试
        </Button>
      ) : null}
      <div className="ps-state__meta">
        {err.code}
        {err.requestId ? ` · request_id ${err.requestId}` : ""}
      </div>
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
