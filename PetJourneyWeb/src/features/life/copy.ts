/**
 * 证件卡包的文案与格式化：只把服务端给的事实换成人话，不补服务端没有的内容。
 * 界面上不出现原始代码（kind / status / ref_kind 等），也不出现内部机制的说法。
 */
import type { CredentialField, CredentialKind, CredentialLink, CredentialSummary, DrivingSchoolStatus, JobRecord, SubjectStatus } from "@/shared/contracts";

export const TICKET_KINDS: ReadonlySet<CredentialKind> = new Set<CredentialKind>(["boarding_pass", "transport_ticket"]);

/** 卡面形状：ID-1 卡片、票、护照小本、档案夹。素材单 UI-ASSET-005 的尺寸与安全区按这个分。 */
export type CredentialForm = "card" | "ticket" | "passport" | "folder";

export function formOf(kind: CredentialKind): CredentialForm {
  if (TICKET_KINDS.has(kind)) return "ticket";
  if (kind === "passport") return "passport";
  if (kind === "care_profile") return "folder";
  return "card";
}

/** 列表与详情顶上的小状态；“有效”是常态，不单独标出来。票据沿用后端的“待出发 → 在途 → 已使用”。 */
export function statusText(summary: Pick<CredentialSummary, "kind" | "status">): string | null {
  const ticket = TICKET_KINDS.has(summary.kind);
  switch (summary.status) {
    case "active":
      return ticket ? "待出发" : null;
    case "in_progress":
      return ticket ? "在途" : "办理中";
    case "used":
      return "已使用";
    case "expired":
      return "已过期";
    case "not_obtained":
      return "还没有";
    default:
      return null;
  }
}

/** 已获得＝服务端给了证件号（credential_id）；没有的一律当空卡位，不画卡面、不写号码。 */
export function isObtained(summary: CredentialSummary): summary is CredentialSummary & { credential_id: string } {
  return typeof summary.credential_id === "string" && summary.credential_id.length > 0;
}

/** 已获得的保持服务端顺序在前，未获得的放最后。 */
export function splitWallet(list: CredentialSummary[]) {
  const obtained = list.filter(isObtained);
  const missing = list.filter((item) => !isObtained(item));
  return { obtained, missing };
}

/** 驾照空卡位里的驾校入口：还没有 → 陪 TA 去驾校（方案 8.1）；驾校那边已经在办 → 去驾校看看。 */
export function schoolEntry(summary: CredentialSummary): { text: string; to: string } | null {
  if (summary.kind !== "driver_license" || isObtained(summary)) return null;
  if (summary.status === "not_obtained") return { text: "陪 TA 去驾校", to: "/school" };
  if (summary.status === "in_progress") return { text: "去驾校看看", to: "/school" };
  return null;
}

/** 驾照学车进度里一科的小标签：科目名与说法都只取服务端字段。 */
export interface SubjectTag {
  subject: string;
  name: string;
  text: string;
  tone: "passed" | "available" | "in_exam" | "cooldown" | "locked";
}

/** 驾照空卡位里要写的学车进度（方案 8.2）；null 表示不写进度，空卡位照原来的样子。 */
export type SchoolProgress = { kind: "wish"; wishText: string | null } | { kind: "pending" } | { kind: "subjects"; subjects: SubjectTag[] };

/** 冷却截止时间（看的人所在时区），例如“9月30日 14:00”——和地图面板驾校提醒同一种写法。 */
const COOLDOWN_UNTIL = new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });

/** 服务端科目标题形如“科目二：把小车开稳”，取全角冒号前的科目名（与驾校模块、地图面板、后端同一取法）。 */
export function subjectName(title: string): string {
  return title.split("：")[0] || title;
}

/** 一科的标签；服务端字段不够说清楚（冷却没给截止时间、锁定没给解锁提示）时为 null。 */
export function subjectTag(subject: SubjectStatus): SubjectTag | null {
  const base = { subject: subject.subject, name: subjectName(subject.title) };
  switch (subject.state) {
    case "passed":
      return { ...base, text: "已通过", tone: "passed" };
    case "available":
      return { ...base, text: subject.next_attempt === "retake" ? "可以约补考" : "可以约考", tone: "available" };
    case "in_exam":
      return { ...base, text: "在考", tone: "in_exam" };
    case "cooldown": {
      const until = subject.cooldown_until ? Date.parse(subject.cooldown_until) : Number.NaN;
      return Number.isFinite(until) ? { ...base, text: `冷却到 ${COOLDOWN_UNTIL.format(until)}`, tone: "cooldown" } : null;
    }
    case "locked":
      return subject.unlock_hint ? { ...base, text: subject.unlock_hint, tone: "locked" } : null;
    default:
      return null;
  }
}

/**
 * 驾照“办理中”时空卡位里的学车进度，只按驾校服务的事实说：
 * - enrolled：四科各一个标签；任何一科字段不够说清楚，整块不写进度（不编）；
 * - license_pending：四科都过了，驾照正在签发；
 * - wish（TA 想学、还没报名）：后端这时四科状态照常算，科目一会是 available，但没报名约不了考试（建考局报 not_enrolled）——
 *   写“可以约考”会误导，所以只写 TA 想学的那句话（wish_text 原文），入口是“陪 TA 去驾校”；
 * - 其他阶段（none / licensed）和卡包列表对不上（例如刚领证、列表还没刷新），不写进度。
 */
export function schoolProgress(status: DrivingSchoolStatus): SchoolProgress | null {
  switch (status.stage) {
    case "wish":
      return { kind: "wish", wishText: status.wish_text };
    case "license_pending":
      return { kind: "pending" };
    case "enrolled": {
      if (!status.subjects.length) return null;
      const tags = status.subjects.map(subjectTag);
      return tags.every((tag): tag is SubjectTag => tag !== null) ? { kind: "subjects", subjects: tags } : null;
    }
    default:
      return null;
  }
}

/** 打工状态：going 只是在去的路上，绝不说成在打工。 */
export function jobStatus(status: string): { text: string; tone: "going" | "working" | "done" | "other" } {
  if (status === "going") return { text: "去上班的路上", tone: "going" };
  if (status === "working") return { text: "正在干活", tone: "working" };
  if (status === "done") return { text: "干完了", tone: "done" };
  return { text: "打工记录", tone: "other" };
}

export function payText(job: Pick<JobRecord, "paid">): string {
  return job.paid ? "已进银行卡" : "收工后到账";
}

/** 相关经历：只有能确定对应页面的才给链接。 */
export function linkRoute(link: CredentialLink): string | null {
  if (link.kind === "visit" && link.ref_id) return `/visits/${encodeURIComponent(link.ref_id)}`;
  if (link.kind === "exam") return "/school";
  return null;
}

const LINK_KIND_TEXT: Record<string, string> = { journey: "旅程", leg: "路段", visit: "到访", exam: "驾校", home: "入住" };

export function linkKindText(kind: string): string | null {
  return LINK_KIND_TEXT[kind] ?? null;
}

function validDate(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : date;
}

const DAY = new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "long", day: "numeric" });
const MONTH_DAY = new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric" });

/** 2026年9月3日（按浏览器所在时区）。 */
export function dayText(iso: string | null | undefined): string | null {
  const date = validDate(iso);
  return date ? DAY.format(date) : null;
}

const pad = (value: number) => String(value).padStart(2, "0");

/** 印章上的日期：2026.09.03。 */
export function stampDate(iso: string): string {
  const date = validDate(iso);
  return date ? `${date.getFullYear()}.${pad(date.getMonth() + 1)}.${pad(date.getDate())}` : "";
}

function clock(date: Date): string {
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** 打工时间：同一天写“9月24日 14:00–18:00”，跨天把两头的日期都写上。 */
export function jobWhen(job: Pick<JobRecord, "starts_at" | "ends_at">): string {
  const start = validDate(job.starts_at);
  const end = validDate(job.ends_at);
  if (!start) return "";
  if (!end) return `${MONTH_DAY.format(start)} ${clock(start)}`;
  const sameDay = start.toDateString() === end.toDateString();
  return sameDay
    ? `${MONTH_DAY.format(start)} ${clock(start)}–${clock(end)}`
    : `${MONTH_DAY.format(start)} ${clock(start)} – ${MONTH_DAY.format(end)} ${clock(end)}`;
}

export function deltaText(delta: number): string {
  if (delta > 0) return `+${delta}`;
  if (delta < 0) return `−${Math.abs(delta)}`;
  return "0";
}

/** 粗略显示宽度：中日韩字符算 2，其余算 1。用来决定字段占一栏还是两栏。 */
export function textWidth(value: string): number {
  let width = 0;
  for (const ch of value) width += /[⺀-￿]/.test(ch) ? 2 : 1;
  return width;
}

export function isWideField(field: CredentialField, limit = 13): boolean {
  return textWidth(field.value) > limit || textWidth(field.label) > limit;
}

/** YYYY-MM-DD（浏览器所在时区）。 */
function localDay(iso: string): string | null {
  const date = validDate(iso);
  return date ? `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` : null;
}

/**
 * 星球居民证、驾驶证：卡面底图（UI-ASSET-005）的照片框和字段区是固定比例的，字段太多会把卡撑高、和底图对不齐。
 * 字段不超过 5 个时全放正面；超过时正面放前 4 个，其余按原顺序排到背面（驾照背面底图正好是四行横线）。字段本身一个不少、原样显示。
 */
export const FAMILY_FRONT_MAX = 5;

export function splitFamilyFields(fields: CredentialField[]): { front: CredentialField[]; back: CredentialField[] } {
  if (fields.length <= FAMILY_FRONT_MAX) return { front: fields, back: [] };
  return { front: fields.slice(0, FAMILY_FRONT_MAX - 1), back: fields.slice(FAMILY_FRONT_MAX - 1) };
}

/**
 * 编号 / 签发日期在服务端字段里已经出现过就不再重复写。
 * 服务端字段里的日期可能按 UTC 取，也可能按本地取：两种写法都算“已经写了”。
 */
export function faceExtras(summary: CredentialSummary, fields: CredentialField[]) {
  const values = fields.map((field) => field.value.trim());
  const number = summary.number && !values.includes(summary.number) ? summary.number : null;
  const days = summary.issued_at ? [summary.issued_at.slice(0, 10), localDay(summary.issued_at)].filter((day): day is string => Boolean(day)) : [];
  const shown = values.some((value) => days.some((day) => value.includes(day)));
  const issued = summary.issued_at && !shown ? dayText(summary.issued_at) : null;
  return { number, issued };
}

/** 照护档案一条叮嘱形如“习惯：……”；把前缀单独加粗，文字本身原样不动。 */
export function splitNote(note: string): { head: string | null; body: string } {
  const match = /^([^：:]{1,6}[：:])(.+)$/s.exec(note);
  return match ? { head: match[1], body: match[2] } : { head: null, body: note };
}

/**
 * 双语字段的英文小标签：只翻译服务端真的会给的中文标签（以及用户参考样式里的典型字段名，服务端给了才会显示）。
 * 认不出的标签只显示中文，不猜英文。
 */
const FIELD_EN: Record<string, string> = {
  名字: "Name",
  姓名: "Name",
  物种: "Species",
  种类: "Species",
  品种: "Breed",
  性别: "Sex",
  出生日期: "Date of birth",
  出生地: "Place of birth",
  国籍: "Nationality",
  有效期至: "Date of expiry",
  星球编号: "Planet ID No.",
  住在: "Residence",
  入住日期: "Moved in",
  护照号: "Passport No.",
  签发日期: "Date of issue",
  签发地: "Place of issue",
  准驾车型: "Class",
  证号: "Licence No.",
  初次领取: "First issued",
  成绩: "Scores",
  签发机构: "Issued by",
  说明: "Note",
};

export function fieldLabelEn(label: string): string | null {
  return FIELD_EN[label.trim()] ?? null;
}

/**
 * 同一家族证件（护照、星球居民证、驾驶证）抬头条上的英文名。按证件种类（kind）取，不按中文名取，
 * 所以后端给证件改中文名（kind 仍是 identity_card）时，这里不需要按旧名留兼容项。
 */
const KIND_EN: Partial<Record<CredentialKind, string>> = {
  identity_card: "PLANET RESIDENT CARD",
  driver_license: "PAW DRIVING LICENCE",
  passport: "PETSOUL PASSPORT",
};

export function kindEn(kind: CredentialKind): string | null {
  return KIND_EN[kind] ?? null;
}

/** 本地日期的 YYMMDD。 */
function yymmdd(iso: string | null | undefined): string {
  const date = validDate(iso);
  return date ? `${String(date.getFullYear()).slice(2)}${pad(date.getMonth() + 1)}${pad(date.getDate())}` : "";
}

const MRZ_WIDTH = 30;

/**
 * 护照底部两行机读码风格的等宽字：只用真实数据（护照号、签发日期、物种）拼出 PetSoul 自己的代号，
 * PSR 是虚构的“PETSOUL REPUBLIC”，行宽 30 也不是任何真实护照的格式；没有护照号就不画。
 */
export function passportMrz(summary: Pick<CredentialSummary, "number" | "issued_at">, species: string | null): [string, string] | null {
  if (!summary.number) return null;
  const clean = (value: string) => value.toUpperCase().replace(/[^A-Z0-9]/g, "");
  const fill = (value: string) => (value + "<".repeat(MRZ_WIDTH)).slice(0, MRZ_WIDTH);
  const speciesCode = species ? clean(species) : "";
  const line1 = fill(`P<PSR<${speciesCode ? `${speciesCode}<<` : "<"}PETSOUL`);
  const line2 = fill(`${clean(summary.number)}<${yymmdd(summary.issued_at)}`);
  return [line1, line2];
}

/** 稳定的小整数（按字符串），用于印章旋转、墨色、位置微调；同一个章每次画得一样。 */
export function hashOf(value: string): number {
  let hash = 2166136261;
  for (let i = 0; i < value.length; i += 1) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

export function chunk<T>(items: T[], size: number): T[][] {
  const pages: T[][] = [];
  for (let i = 0; i < items.length; i += size) pages.push(items.slice(i, i + size));
  return pages;
}
