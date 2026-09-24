import { Link, isRouteErrorResponse, useRouteError } from "react-router";
import { Button, EmptyState, Page } from "@/shared/ui";

/** 页面崩溃时给玩家一句人话；报错原文（常是英文的 JS 报错）只收进默认收起的“技术信息”，和 StateView 的写法、样式一致。 */
export const ROUTE_ERROR_HINT = "刷新一下试试；还不行的话，先回地图。";

export function RouteErrorPage() {
  const error = useRouteError();
  const detail = isRouteErrorResponse(error) ? `${error.status} ${error.statusText}` : error instanceof Error ? error.message : "未知错误";
  console.error("[petsoul] route error", error);
  return (
    <Page bare>
      <div className="ps-state ps-state--error" role="alert" style={{ marginTop: "20vh" }}>
        <div className="ps-state__title">这一页没能打开</div>
        <div className="ps-muted">{ROUTE_ERROR_HINT}</div>
        <details className="ps-state__tech">
          <summary>技术信息</summary>
          <div className="ps-state__meta">{detail}</div>
        </details>
        <div className="ps-row" style={{ justifyContent: "center" }}>
          <Button variant="primary" icon="refresh" onClick={() => window.location.reload()}>
            刷新
          </Button>
          <Link className="ps-btn ps-btn--secondary" to="/map">
            回到地图
          </Link>
        </div>
      </div>
    </Page>
  );
}

export function NotFoundPage() {
  return (
    <Page>
      <div style={{ marginTop: "18vh" }}>
        <EmptyState icon="compass" title="这里还没有路" action={<Link className="ps-btn ps-btn--primary" to="/map">回到地图</Link>}>
          地址可能写错了，或者这个地方还在建设。
        </EmptyState>
      </div>
    </Page>
  );
}
