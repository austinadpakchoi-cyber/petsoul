/**
 * 管理端 API 客户端。
 *
 * - 会话靠 HttpOnly cookie（`credentials: "same-origin"`），前端**永远拿不到**会话值，也不保存任何管理令牌；
 * - 写操作自动带 CSRF 头（从可读的 `petsoul_admin_csrf` cookie 回填）与 `Idempotency-Key`；
 * - 错误一律是后端的稳定信封 `{error:{code,message,request_id,details}}`；界面按 code 决策，按 message 显示，
 *   **不把原始 JSON 或堆栈当日常界面**。
 */

const ADMIN = "/api/v1/admin";
const CSRF_COOKIE = "petsoul_admin_csrf";

export class AdminError extends Error {
  code: string;
  status: number;
  requestId: string;
  details: Record<string, unknown> | null;

  constructor(status: number, body: { code: string; message: string; request_id: string; details?: Record<string, unknown> | null }) {
    super(body.message);
    this.status = status;
    this.code = body.code;
    this.requestId = body.request_id;
    this.details = body.details ?? null;
  }
}

function csrfToken(): string {
  const hit = document.cookie.split("; ").find((row) => row.startsWith(`${CSRF_COOKIE}=`));
  return hit ? decodeURIComponent(hit.slice(CSRF_COOKIE.length + 1)) : "";
}

/**
 * 一次写操作的**操作号**（即 `Idempotency-Key`）。
 *
 * 规则：**一次操作一个号，重试沿用同一个号**。对话框打开时生成，点"重试"不换号——
 * 否则"请求超时 → 再点一次"在后端看来就是两次不同的操作，单笔补偿会入账两次。
 * 只有内容确定没被执行（后端明确拒绝）之后改了内容，才算新的一次操作。
 */
export function newOperationId(prefix: string): string {
  const random = crypto.randomUUID().replaceAll("-", "").slice(0, 16);
  return `${prefix}-${random}`;
}

/**
 * 这次写操作"做没做成"**没有定论**：没连上后台、网关或服务端出错、或者同一个操作号还在处理中。
 * 这时既不能说"失败了"，也不能换一个新操作号重试——只能用**同一个**操作号重试，
 * 已经生效的话后端只回那一次的结果。其余 4xx 是后端明确拒绝，操作没有被执行。
 */
export function outcomeUnknown(error: unknown): boolean {
  if (!(error instanceof AdminError)) return true;  // 连错误信封都没有：按不确定处理，宁可锁住也不重复执行
  return error.status === 0 || error.status >= 500 || error.code === "IDEMPOTENCY_IN_PROGRESS";
}

/** 发请求并统一成 AdminError：网络断开、网关返回的非 JSON 页面也有稳定的 code，不抛 SyntaxError。 */
async function send<T>(url: string, init: RequestInit, fallbackMessage: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, { ...init, credentials: "same-origin" });
  } catch {
    throw new AdminError(0, { code: "NETWORK_ERROR", message: "没有连上后台（网络中断或超时）。", request_id: "-" });
  }
  const text = await response.text();
  let payload: { error?: ConstructorParameters<typeof AdminError>[1] } | null = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = null;  // 网关的 HTML 错误页之类
  }
  if (!response.ok) {
    if (payload && payload.error) throw new AdminError(response.status, payload.error);
    throw new AdminError(response.status, {
      code: response.status >= 500 ? "UPSTREAM_ERROR" : "INTERNAL_ERROR", message: fallbackMessage, request_id: "-",
    });
  }
  return payload as T;
}

async function request<T>(method: string, path: string, body?: unknown, operationId?: string): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") {
    headers["X-Admin-CSRF-Token"] = csrfToken();
    headers["Idempotency-Key"] = operationId ?? newOperationId("op");
  }
  return send<T>(`${ADMIN}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  }, "请求失败，请稍后再试。");
}

/** 素材上传：多部分表单，CSRF 与幂等键同普通写操作。**服务器不会去抓任何 URL**，只收这里传上去的文件。 */
export async function uploadAsset(form: FormData, operationId?: string): Promise<unknown> {
  return send(`${ADMIN}/assets`, {
    method: "POST",
    headers: { "X-Admin-CSRF-Token": csrfToken(), "Idempotency-Key": operationId ?? newOperationId("asset") },
    body: form,
  }, "上传失败，请稍后再试。");
}

// 同一个读请求还在路上时，再发一次就共用这一个（不是缓存：回来之后下一次照样重新取）。
// 为什么要有：开发模式的 StrictMode 会把每个页面的副作用故意执行两遍，于是每次打开页面都发两次 GET；
// 查看个人数据的接口每次都写一条访问审计，操作记录里就变成「每次查看记两次」——审计失真。正式构建本来就只发一次。
const inflight = new Map<string, Promise<unknown>>();
function getOnce<T>(path: string): Promise<T> {
  const running = inflight.get(path);
  if (running) return running as Promise<T>;
  const started = request<T>("GET", path).finally(() => inflight.delete(path));
  inflight.set(path, started);
  return started;
}

export const api = {
  get: <T,>(path: string) => getOnce<T>(path),
  post: <T,>(path: string, body?: unknown, operationId?: string) => request<T>("POST", path, body, operationId),
  put: <T,>(path: string, body?: unknown, operationId?: string) => request<T>("PUT", path, body, operationId),
};

/** 玩家侧接口：只用来当场证明"发布的内容玩家真的读到了"，不代表后台有玩家权限。 */
export async function playerAnnouncements(): Promise<{ announcements: PlayerAnnouncement[]; as_of: string }> {
  const response = await fetch("/api/v1/web/announcements", { credentials: "omit" });
  if (!response.ok) throw new Error(`玩家接口返回 ${response.status}`);
  return response.json();
}

export interface PlayerAnnouncement {
  item_id: string;
  slug: string;
  revision: number;
  title: string;
  body: string;
  severity: string;
  link: string | null;
  effective_at: string;
  expires_at: string | null;
}
