import type { WebErrorCode, WebErrorEnvelope } from "@/shared/contracts";

/** 客户端统一错误。页面只按 kind/code 分支，不解析 message 文本。 */
export type ApiErrorKind = "http" | "network" | "timeout" | "capability" | "aborted";

/** 给玩家看的三句（ApiError.playerMessage 与 StateView 共用）：不说“接口”“能力”“接入”这类开发说法。 */
export const PLAYER_ERROR_TEXT = {
  unavailable: "这里暂时还没开放，准备好了会出现在这里。",
  notFound: "没有找到要看的内容：它可能已经不在了，或者这里暂时还没开放。",
  /** 程序自己出的错（TypeError 之类，经 toApiError 包进来）：原文是给开发看的、可能是英文，玩家只看这一句。 */
  failed: "操作暂时没有完成，请重试。",
} as const;

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly code: WebErrorCode | "NETWORK_ERROR" | "TIMEOUT" | "ABORTED";
  readonly requestId: string | null;
  readonly retryable: boolean;
  readonly details: Record<string, unknown> | null;
  /**
   * 后端没有这条路（路由级 404/405，由 fromEnvelope 判定）：原话是“没有找到这个接口。”，给玩家要换成人话。
   * 业务上的“找不到”后端都会带上 details（resource 或 reason），原话本来就是写给玩家的（“没有找到这张证件。”），照用。
   */
  readonly unknownRoute: boolean;
  /**
   * 不是 ApiError 的异常（代码 bug、TypeError 之类），由 toApiError 包进来的：原文只进“技术信息”，给玩家看 PLAYER_ERROR_TEXT.failed。
   * kind / code 照旧是 network / NETWORK_ERROR（别处按它决定要不要重试，不动）；真正的网络失败由 client.ts 自己造，不带这个标记。
   */
  readonly fromException: boolean;

  constructor(init: {
    kind: ApiErrorKind;
    status?: number | null;
    code: ApiError["code"];
    message: string;
    requestId?: string | null;
    retryable?: boolean;
    details?: Record<string, unknown> | null;
    unknownRoute?: boolean;
    fromException?: boolean;
  }) {
    super(init.message);
    this.name = "ApiError";
    this.kind = init.kind;
    this.status = init.status ?? null;
    this.code = init.code;
    this.requestId = init.requestId ?? null;
    this.retryable = init.retryable ?? false;
    this.details = init.details ?? null;
    this.unknownRoute = init.unknownRoute ?? false;
    this.fromException = init.fromException ?? false;
  }

  get isAuth(): boolean {
    return this.code === "AUTH_REQUIRED" || this.code === "SESSION_EXPIRED";
  }

  get isCapabilityUnavailable(): boolean {
    return this.code === "CAPABILITY_UNAVAILABLE" || this.code === "NOT_CONFIGURED";
  }

  /** 找不到：HTTP 404 或错误码 NOT_FOUND（出错页的标题据此写“没有找到”）。 */
  get isNotFound(): boolean {
    return this.status === 404 || this.code === "NOT_FOUND";
  }

  /**
   * 给玩家看的一句（2026-09-24 巡检 P1）：还没开放、后端没有这条路（原话带“能力”“接口”这类技术词）的换成人话，
   * 原话与错误码只放进“技术信息”（StateView 的 ErrorState）；其余照用原话——后端业务上的出错原话（含“没有找到这张证件。”
   * 这类找不到）本来就是写给玩家看的中文，比一句笼统的“没有找到”说得清楚。页面上凡是直接显示出错原因的地方都用它，不用 message。
   */
  get playerMessage(): string {
    if (this.isCapabilityUnavailable) return PLAYER_ERROR_TEXT.unavailable;
    if (this.unknownRoute) return PLAYER_ERROR_TEXT.notFound;
    if (this.fromException) return PLAYER_ERROR_TEXT.failed;
    return this.message;
  }

  static capability(capability: string, message = "这里暂时还没开放。"): ApiError {
    return new ApiError({
      kind: "capability",
      code: "CAPABILITY_UNAVAILABLE",
      message,
      details: { capability },
    });
  }

  static fromEnvelope(status: number, envelope: WebErrorEnvelope, headerRequestId: string | null): ApiError {
    const err = envelope.error;
    return new ApiError({
      kind: err.code === "CAPABILITY_UNAVAILABLE" || err.code === "NOT_CONFIGURED" ? "capability" : "http",
      status,
      code: err.code,
      message: err.message,
      requestId: err.request_id ?? headerRequestId,
      retryable: err.retryable,
      details: err.details ?? null,
      // 后端对“找不到某样东西”都带 details（WebAPIError.not_found 带 resource，其余带 reason）；
      // 什么都不带的 404/405 只来自路由级兜底（web_platform/errors.py 的 _http_error：“没有找到这个接口。”）。
      unknownRoute: err.code === "NOT_FOUND" && (status === 404 || status === 405) && (!err.details || Object.keys(err.details).length === 0),
    });
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}

/**
 * 把任意异常收成 ApiError。不是 ApiError 的（代码 bug、TypeError、第三方库抛的）照旧按网络类处理（可重试），
 * 但标上 fromException：原文（可能是英文）只进“技术信息”，玩家只看“操作暂时没有完成，请重试。”（2026-09-24，驾驶分身转）。
 */
export function toApiError(value: unknown): ApiError {
  if (value instanceof ApiError) return value;
  return new ApiError({
    kind: "network",
    code: "NETWORK_ERROR",
    message: value instanceof Error ? value.message : "网络连接失败",
    retryable: true,
    fromException: true,
  });
}
