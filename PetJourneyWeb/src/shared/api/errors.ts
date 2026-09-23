import type { WebErrorCode, WebErrorEnvelope } from "@/shared/contracts";

/** 客户端统一错误。页面只按 kind/code 分支，不解析 message 文本。 */
export type ApiErrorKind = "http" | "network" | "timeout" | "capability" | "aborted";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly code: WebErrorCode | "NETWORK_ERROR" | "TIMEOUT" | "ABORTED";
  readonly requestId: string | null;
  readonly retryable: boolean;
  readonly details: Record<string, unknown> | null;

  constructor(init: {
    kind: ApiErrorKind;
    status?: number | null;
    code: ApiError["code"];
    message: string;
    requestId?: string | null;
    retryable?: boolean;
    details?: Record<string, unknown> | null;
  }) {
    super(init.message);
    this.name = "ApiError";
    this.kind = init.kind;
    this.status = init.status ?? null;
    this.code = init.code;
    this.requestId = init.requestId ?? null;
    this.retryable = init.retryable ?? false;
    this.details = init.details ?? null;
  }

  get isAuth(): boolean {
    return this.code === "AUTH_REQUIRED" || this.code === "SESSION_EXPIRED";
  }

  get isCapabilityUnavailable(): boolean {
    return this.code === "CAPABILITY_UNAVAILABLE" || this.code === "NOT_CONFIGURED";
  }

  static capability(capability: string, message = "这项能力尚未接入。"): ApiError {
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
    });
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}

export function toApiError(value: unknown): ApiError {
  if (value instanceof ApiError) return value;
  return new ApiError({
    kind: "network",
    code: "NETWORK_ERROR",
    message: value instanceof Error ? value.message : "网络连接失败",
    retryable: true,
  });
}
