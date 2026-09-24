import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import type { DataOrigin } from "@/shared/contracts";
import { Icon, type IconName } from "./Icon";

type ButtonVariant = "primary" | "leaf" | "secondary" | "ghost" | "danger";

export function Button({
  variant = "secondary",
  size,
  block,
  icon,
  loading,
  children,
  className,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: "sm";
  block?: boolean;
  icon?: IconName;
  loading?: boolean;
}) {
  const cls = [
    "ps-btn",
    `ps-btn--${variant}`,
    size === "sm" ? "ps-btn--sm" : "",
    block ? "ps-btn--block" : "",
    !children && icon ? "ps-btn--icon" : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <button type="button" className={cls} aria-busy={loading || undefined} {...rest} disabled={loading || rest.disabled}>
      {icon ? <Icon name={loading ? "refresh" : icon} size={size === "sm" ? 16 : 18} /> : null}
      {children}
    </button>
  );
}

export function Card({ paper, flat, className, ...rest }: HTMLAttributes<HTMLDivElement> & { paper?: boolean; flat?: boolean }) {
  return <div className={["ps-card", paper ? "ps-card--paper" : "", flat ? "ps-card--flat" : "", className ?? ""].join(" ")} {...rest} />;
}

export type ChipTone = "neutral" | "leaf" | "sun" | "coral" | "sky" | "danger";

export function Chip({ tone = "neutral", icon, children, ...rest }: HTMLAttributes<HTMLSpanElement> & { tone?: ChipTone; icon?: IconName }) {
  return (
    <span className={`ps-chip ${tone === "neutral" ? "" : `ps-chip--${tone}`}`} {...rest}>
      {icon ? <Icon name={icon} size={13} /> : null}
      {children}
    </span>
  );
}

export function ToggleChip({ pressed, onToggle, children }: { pressed: boolean; onToggle: () => void; children: ReactNode }) {
  return (
    <button type="button" className="ps-chip" aria-pressed={pressed} onClick={onToggle}>
      {children}
    </button>
  );
}

/** 演示数据标识：fixture 数据在用户可见处明确标出，不冒充真实数据。 */
export function DataOriginBadge({ origin, label }: { origin: DataOrigin | "fixture" | "live"; label?: string }) {
  if (origin !== "fixture") return null;
  return (
    <span className="ps-origin" title="这部分是明确的演示数据，不代表真实商家、班次或账号">
      <Icon name="info" size={13} />
      {label ?? "演示数据"}
    </span>
  );
}

/**
 * 顶栏返回（用户 2026-09-24 同意）：从哪来回哪去。
 * - 有站内上一页（不是直接打开链接进来的）：普通点击退回上一页，例如从小窝的菜园门进菜园，返回回到小窝；
 * - 直接打开链接进来、没有站内历史：回上级页。back 为字符串时回它，为 true 时回地图首页。
 * 链接的 href 始终是上级页：新标签页打开、读屏、“没有死胡同”的检查都以它为准。
 */
export function TopBar({ title, subtitle, back, right }: { title: ReactNode; subtitle?: ReactNode; back?: string | boolean; right?: ReactNode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const parent = typeof back === "string" ? back : "/map";
  const hasInAppHistory = location.key !== "default";
  return (
    <header className="ps-topbar">
      {back ? (
        <Link
          to={parent}
          className="ps-btn ps-btn--ghost ps-btn--icon"
          aria-label="返回"
          onClick={(event) => {
            // 修饰键 / 中键交给浏览器（新标签页打开上级页）；只有普通左键、并且确有站内上一页时才退回上一页。
            if (!hasInAppHistory || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
            event.preventDefault();
            navigate(-1);
          }}
        >
          <Icon name="back" />
        </Link>
      ) : null}
      <div className="ps-topbar__title">
        {title}
        {subtitle ? <span className="ps-topbar__sub">{subtitle}</span> : null}
      </div>
      {right}
    </header>
  );
}

export function Page({ bare, children, className }: { bare?: boolean; children: ReactNode; className?: string }) {
  return <main className={["ps-page", bare ? "ps-page--bare" : "", className ?? ""].join(" ")}>{children}</main>;
}

export function Progress({ value, label }: { value: number; label: string }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div className="ps-progress" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
      <span style={{ width: `${pct}%` }} />
    </div>
  );
}
