/** 爪爪驾校的展示文字与小工具（只做呈现；规则、机会与冷却一律以服务端返回为准）。 */
import type { AttemptKind, SchoolSubject, SubjectState } from "@/shared/contracts";
import type { ChipTone } from "@/shared/ui";

export const SUBJECT_SHORT: Record<SchoolSubject, string> = { s1: "科目一", s2: "科目二", s3: "科目三", s4: "科目四" };

export const STATE_TEXT: Record<SubjectState, string> = { locked: "未解锁", available: "可以约考", in_exam: "考试中", cooldown: "等待中", passed: "已通过" };

export const STATE_TONE: Record<SubjectState, ChipTone> = { locked: "neutral", available: "sky", in_exam: "sun", cooldown: "coral", passed: "leaf" };

export function attemptText(kind: AttemptKind | null | undefined): string {
  return kind === "retake" ? "补考" : "首次考试";
}

export function isSubject(value: string | undefined): value is SchoolSubject {
  return value === "s1" || value === "s2" || value === "s3" || value === "s4";
}

/** 冷却剩余时间：服务端给出截止时间，这里只负责显示。 */
export function formatWait(untilIso: string, nowMs: number): string {
  const ms = Date.parse(untilIso) - nowMs;
  if (!(ms > 0)) return "现在可以再约考试了";
  const minutes = Math.ceil(ms / 60_000);
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const mins = minutes % 60;
  if (days > 0) return `还要等 ${days} 天${hours ? ` ${hours} 小时` : ""}`;
  if (hours > 0) return `还要等 ${hours} 小时${mins ? ` ${mins} 分钟` : ""}`;
  return `还要等 ${mins} 分钟`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
}

/** tick（每秒 30 个）→ 分:秒 */
export function formatTicks(ticks: number, hz = 30): string {
  const s = Math.max(0, Math.floor(ticks / hz));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function reducedMotion(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
