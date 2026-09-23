import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";
import { Link, useNavigate } from "react-router";
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

export function TopBar({ title, subtitle, back, right }: { title: ReactNode; subtitle?: ReactNode; back?: string | boolean; right?: ReactNode }) {
  const navigate = useNavigate();
  return (
    <header className="ps-topbar">
      {back ? (
        typeof back === "string" ? (
          <Link to={back} className="ps-btn ps-btn--ghost ps-btn--icon" aria-label="返回">
            <Icon name="back" />
          </Link>
        ) : (
          <button type="button" className="ps-btn ps-btn--ghost ps-btn--icon" aria-label="返回" onClick={() => navigate(-1)}>
            <Icon name="back" />
          </button>
        )
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
