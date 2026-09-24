/**
 * 我的 · 我的举报（方案第 9 节，GET /reports/mine）：逐条校验与显示用的说法。全是纯函数，服务与页面共用；
 * 单独测试见 tests/claude-6c2b-my-reports.test.tsx。
 *
 * 类型用契约：`MyReports { reports: ReportOutcomeItem[], note }`（总集成从 `app/web_admin/moderation.py` 的 reporter_outcomes 读出）。
 * 路由 `app/routers/web/report_outcomes.py` 还是 `response_model=None`（关联归 adm1），服务端不替我们校验，
 * 所以取回后照样逐条校验，坏条目丢掉。
 *
 * 后端事实（以代码为准）：
 * - 运营后台没装或表没迁移好 → 503 NOT_CONFIGURED（`social.report_outcomes`），后端不拿“已收到”顶上，这里也不编；
 * - 每条的 message 是与结局对应的固定措辞，产品口径归后端：**原样显示，不按 outcome 自己拼文案**；
 *   outcome、status 只拿来决定样式（处理中 / 已处理的颜色），不生成文字；
 * - reason 是提交举报时带的理由（现在前端提交的是代码 `owner_reported`，不是主人写的话）；
 * - 不含员工身份、内部处理原因，也不含被举报内容本身。
 * 页面只写对玩家有意义的：什么时候举报的、举报的是一条动态还是一条评论、主人自己写的理由（像代码的不显示）、
 * 处理结果（message 原文）与处理时间。编号（report_id、target_id）和原始代码（status、outcome、理由代码）不给玩家看。
 */
import { ReportOutcomeValues, ReportStatusValues, type MyReports, type ReportOutcome, type ReportOutcomeItem, type ReportStatus } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";

/* ---------------- 逐条校验：坏条目丢掉 ---------------- */

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const filled = (value: unknown): value is string => typeof value === "string" && value.trim().length > 0;
const readableTime = (value: unknown): value is string => filled(value) && Number.isFinite(Date.parse(value));
const isStatus = (value: unknown): value is ReportStatus => (ReportStatusValues as readonly unknown[]).includes(value);
const isOutcome = (value: unknown): value is ReportOutcome => (ReportOutcomeValues as readonly unknown[]).includes(value);

/**
 * 解析一条举报，按契约 ReportOutcomeItem 校验：report_id、target_kind、message 是非空文本；target_id、reason 是文本；
 * created_at 读得出时间；status、outcome 是契约里列出的值；resolved_at 缺省或 null 按 null，给了就要读得出时间。
 * 任何一项不符 → null（整条丢掉）。
 */
export function parseMyReport(raw: unknown): ReportOutcomeItem | null {
  if (!isRecord(raw)) return null;
  const { report_id, target_kind, target_id, reason, created_at, status, outcome, message } = raw;
  if (!filled(report_id) || !filled(target_kind) || !filled(message)) return null;
  if (typeof target_id !== "string" || typeof reason !== "string") return null;
  if (!readableTime(created_at) || !isStatus(status) || !isOutcome(outcome)) return null;
  const resolvedAt = raw.resolved_at ?? null;
  if (resolvedAt !== null && !readableTime(resolvedAt)) return null;
  return { report_id, target_kind, target_id, reason, created_at, status, outcome, resolved_at: resolvedAt, message };
}

/**
 * 整个响应：外层不对（不是对象、reports 不是列表）→ 抛可重试的错误；读不出来不等于“没有举报过”。
 * 同一个 report_id 只留第一条。note 按契约是文本：给了别的类型或没给，就当没有说明（空字符串，页面不显示）。
 */
export function parseMyReports(raw: unknown): MyReports {
  if (!isRecord(raw) || !Array.isArray(raw.reports)) {
    throw new ApiError({ kind: "http", code: "INTERNAL_ERROR", message: "举报记录暂时读不出来，请稍后再试。", retryable: true });
  }
  const seen = new Set<string>();
  const reports: ReportOutcomeItem[] = [];
  for (const item of raw.reports) {
    const parsed = parseMyReport(item);
    if (!parsed || seen.has(parsed.report_id)) continue;
    seen.add(parsed.report_id);
    reports.push(parsed);
  }
  return { reports, note: typeof raw.note === "string" ? raw.note.trim() : "" };
}

/* ---------------- 显示用的说法（都不涉及结局文字：结局只用服务端的 message） ---------------- */

/** 举报的是什么：只按服务端的种类说，不写编号。 */
export function targetLabel(kind: string): string {
  if (kind === "post") return "一条动态";
  if (kind === "comment") return "一条评论";
  return "一条内容";
}

/** 像代码的理由（只有字母、数字和 _ . : -，例如 owner_reported）不给玩家看；主人写的话原样给。 */
export function readableReason(reason: string | null): string | null {
  const text = reason?.trim() ?? "";
  if (!text || /^[A-Za-z0-9_.:-]+$/.test(text)) return null;
  return text;
}

/** 已经有结果了吗：只用来决定样式（处理中是暖黄、已处理是绿），不生成文字。 */
export function isSettled(report: ReportOutcomeItem): boolean {
  return report.status === "resolved" || report.resolved_at !== null;
}

const pad = (n: number) => String(n).padStart(2, "0");

/** 按本机时区写成“9月24日 05:13”，不是今年的前面加年份；读不出时间返回 null。 */
export function formatWhen(iso: string | null, now: Date = new Date()): string | null {
  if (!iso) return null;
  const at = new Date(iso);
  if (!Number.isFinite(at.getTime())) return null;
  const day = `${at.getMonth() + 1}月${at.getDate()}日 ${pad(at.getHours())}:${pad(at.getMinutes())}`;
  return at.getFullYear() === now.getFullYear() ? day : `${at.getFullYear()}年${day}`;
}
