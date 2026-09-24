/** 爪爪驾校的展示文字与小工具（只做呈现；规则、机会与冷却一律以服务端返回为准）。 */
import type { AttemptKind, DrivingSchoolStatus, SchoolSubject, SubjectState } from "@/shared/contracts";
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

/** 看的人所在时区的“几月几日 几点”，例如“9月30日 14:05”（与地图面板的驾校提醒同一种写法）。取不到时间时为空串。 */
export function formatClock(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
}

/** tick（每秒 30 个）→ 分:秒 */
export function formatTicks(ticks: number, hz = 30): string {
  const s = Math.max(0, Math.floor(ticks / hz));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** 一段时长：12 秒 / 1 分 05 秒（成绩单用，不写成 0:12 这种计时器格式）。 */
export function formatSpan(ticks: number, hz = 30): string {
  const s = Math.max(0, Math.floor(ticks / hz));
  const m = Math.floor(s / 60);
  return m ? `${m} 分 ${String(s % 60).padStart(2, "0")} 秒` : `${s} 秒`;
}

/** 成绩单里“发生在第几秒”：第 12 秒 / 第 1 分 05 秒。 */
export function formatMoment(ticks: number, hz = 30): string {
  return `第 ${formatSpan(ticks, hz)}`;
}

/** 驾校总览顶上那张“现在 / 下一步”卡：只有一个主要动作（报名、接着考、去某一科、去领证），没有就为空。 */
export type SchoolNowAction = { kind: "enroll"; label: string } | { kind: "link"; label: string; to: string };

export interface SchoolNow {
  /** 走到哪一步了（第 1 步报名 / 第 2 步学四科 / 第 3 步领证 / 已拿证） */
  step: string;
  title: string;
  detail: string | null;
  action: SchoolNowAction | null;
  tone: "leaf" | "sun" | "coral" | "sky" | "neutral";
}

/**
 * 按服务端的阶段、四科状态、未结束的考试、驾照与仪式，说清“现在在哪一步、下一步做什么”。
 * 只挑一件事：有没考完的考试先接着考；否则看第一门还没通过的科目（正式考试按科目一到四依次解锁）。
 * 冷却写看的人本地的几月几日几点；字段缺了就少说一句，不编。
 */
export function schoolNow(status: DrivingSchoolStatus, name: string, nowMs: number, cooldownHours: number | null = null): SchoolNow {
  const passed = status.subjects.filter((s) => s.state === "passed").length;
  if (status.license) {
    if (!status.ceremony_done) {
      return {
        step: "第 3 步 · 领证",
        title: "四科都过了，驾照已经签好",
        detail: `龟教练在等你们去领证：盖爪印章，${name}接过驾照，再拍一张合影。`,
        action: { kind: "link", label: "去领证：盖章、合影", to: "/school/ceremony" },
        tone: "sun",
      };
    }
    return { step: "已拿证", title: `${name}拿到爪爪驾照了`, detail: "驾照在证件卡包里；以后 TA 自己开车出门就靠它。", action: null, tone: "leaf" };
  }
  if (status.stage === "none" || status.stage === "wish") {
    return {
      step: "第 1 步 · 报名",
      title: status.wish_text ? `${name}想学开车` : `陪${name}学开车`,
      detail: "报名后可以上课、不限次数练习；正式考试按科目一到科目四依次解锁。",
      action: { kind: "enroll", label: `陪 ${name} 报名爪爪驾校` },
      tone: "sun",
    };
  }
  const pending: SchoolNow = { step: "第 3 步 · 领证", title: "四科都过了，驾照正在签发", detail: "签好以后，这里会出现领证入口。", action: null, tone: "leaf" };
  if (status.stage === "license_pending") return pending;
  const step = `第 2 步 · 学四科 · 已通过 ${passed}/4`;
  const open = status.open_session;
  if (open) {
    const short = SUBJECT_SHORT[open.subject];
    return {
      step,
      title: `${short}有一场正式考试还没考完`,
      detail: open.state === "preparing" ? "考场备好了，还没点“开始考试”，还不算次数。" : "回去会从保存的位置接着考，不会重新抽题。",
      action: { kind: "link", label: `接着考${short}`, to: `/school/session/${open.session_id}` },
      tone: "sun",
    };
  }
  const current = status.subjects.find((s) => s.state !== "passed");
  if (!current) return pending;
  const short = SUBJECT_SHORT[current.subject];
  const to = `/school/subject/${current.subject}`;
  switch (current.state) {
    case "in_exam":
      return {
        step,
        title: `${short}有一场正式考试还没考完`,
        detail: "回去会从保存的位置接着考，不会重新抽题。",
        action: current.open_session_id ? { kind: "link", label: `接着考${short}`, to: `/school/session/${current.open_session_id}` } : { kind: "link", label: `去${short}`, to },
        tone: "sun",
      };
    case "cooldown": {
      const until = formatClock(current.cooldown_until);
      return {
        step,
        title: until ? `${short} ${until} 后可以再约考试` : `${short}这一轮的两次机会用完了`,
        detail: `${current.cooldown_until ? `${formatWait(current.cooldown_until, nowMs)}。` : ""}这段时间可以不限次数地练习，TA 的生活和旅行照常。`,
        action: { kind: "link", label: `去${short}练习`, to },
        tone: "coral",
      };
    }
    case "locked":
      return { step, title: `${short}：${current.unlock_hint ?? "还没解锁"}`, detail: "上课和练习随时可以。", action: { kind: "link", label: `去${short}上课`, to }, tone: "neutral" };
    default:
      return {
        step,
        title: `${short}可以约${attemptText(current.next_attempt)}了`,
        detail: `本轮还剩 ${current.attempts_left} 次机会${
          current.next_attempt === "retake" ? `（这是最后一次${cooldownHours ? `，没通过要等 ${Math.round(cooldownHours / 24)} 天` : ""}）` : "（首次考试＋一次补考）"
        }。没把握就先上课、练习，练多少次都不算。`,
        action: { kind: "link", label: `去${short}：上课、练习、约考`, to },
        tone: "sky",
      };
  }
}

export function reducedMotion(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
