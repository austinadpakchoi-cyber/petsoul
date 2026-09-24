/**
 * 地图还在读、或读不出来时的外壳（第 0b 步）：不能是死胡同——底部三栏（地图 · 通讯器 · 回忆）和右上“我的”一直在。
 * - 跨多个家又没指明宠物（后端 409，details.reason = pet_required；W1 加了可选 petId 以后唯一还会报的这种错）：
 *   说人话，给去选的入口（“我的”，那里有切换宠物的栏）；原话和错误码收进“技术信息”；不给“重试”（重试还是一样）。
 * - 其他错误：照旧用统一错误态，能重试。
 * 这里不自己拼 pet_id 绕过去：跨家时前端该不该带、带哪只，由当前宠物决定（见 MapHomePage 的 LiveMapHome）。
 */
import type { ReactNode } from "react";
import { Link } from "react-router";
import { toApiError } from "@/shared/api/errors";
import { ErrorState, Icon, Page } from "@/shared/ui";
import { PreviewTabBar } from "./PreviewTabBar";

export const PET_REQUIRED_TEXT = "你在不止一个家里照顾伙伴，先选一只再看地图。";

export function isPetRequired(error: unknown): boolean {
  const err = toApiError(error);
  return err.status === 409 && err.details?.reason === "pet_required";
}

export function MapStatusShell({ children }: { children: ReactNode }) {
  return (
    <>
      <Page className="ps-wmap-shell">
        <header className="ps-wmap-shell__top">
          <Link className="ps-wmap-me" to="/me" aria-label="我的">
            <Icon name="user" size={20} />
          </Link>
        </header>
        {children}
      </Page>
      <div className="ps-wmap-shell__dock">
        <PreviewTabBar />
      </div>
    </>
  );
}

export function MapLoadError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  if (!isPetRequired(error)) return <ErrorState error={error} onRetry={onRetry} />;
  const err = toApiError(error);
  const tech = [err.code, err.message, err.requestId ? `request_id ${err.requestId}` : null].filter(Boolean).join(" · ");
  return (
    <div className="ps-state ps-state--error" role="alert">
      <div className="ps-state__icon">
        <Icon name="user" />
      </div>
      <div className="ps-state__title">{PET_REQUIRED_TEXT}</div>
      <Link className="ps-btn ps-btn--primary" to="/me">
        去“我的”选一只
      </Link>
      <details className="ps-state__tech">
        <summary>技术信息</summary>
        <div className="ps-state__meta">{tech}</div>
      </details>
    </div>
  );
}
