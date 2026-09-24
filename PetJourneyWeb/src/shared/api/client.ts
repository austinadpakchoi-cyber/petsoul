/**
 * 唯一 HTTP 客户端：所有模块经由它访问 /api/v1/web，不各写 fetch。
 * - 同源 cookie（credentials: "include"），写操作自动回填 X-CSRF-Token；
 * - 需要幂等的写操作传入 idempotencyKey（同一次用户动作重试复用同一个键）；
 * - 统一把错误信封/网络失败/超时归一为 ApiError，并保留 request_id。
 */

import type { WebErrorEnvelope } from "@/shared/contracts";
import { env } from "@/shared/config/env";
import { ApiError } from "./errors";

const CSRF_COOKIE = "petsoul_csrf";
const DEFAULT_TIMEOUT_MS = 15_000;

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  query?: Record<string, string | number | boolean | undefined | null>;
  body?: unknown;
  idempotencyKey?: string;
  signal?: AbortSignal;
  timeoutMs?: number;
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.split("; ").find((part) => part.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

function buildUrl(base: string, path: string, query?: RequestOptions["query"]): string {
  const url = `${base}${path.startsWith("/") ? path : `/${path}`}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null) params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

function isEnvelope(value: unknown): value is WebErrorEnvelope {
  return typeof value === "object" && value !== null && "error" in value && typeof (value as WebErrorEnvelope).error?.code === "string";
}

export interface ApiClient {
  request<T>(path: string, options?: RequestOptions): Promise<T>;
  readonly base: string;
}

export function createApiClient(base: string = env.apiBase, fetchImpl: typeof fetch = (...args) => fetch(...args)): ApiClient {
  async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const method = options.method ?? "GET";
    const headers: Record<string, string> = { Accept: "application/json" };
    const isForm = typeof FormData !== "undefined" && options.body instanceof FormData;
    // FormData（照片上传）由浏览器生成 multipart 边界，不手动设置 Content-Type。
    if (options.body !== undefined && !isForm) headers["Content-Type"] = "application/json";
    if (method !== "GET") {
      const csrf = readCookie(CSRF_COOKIE);
      if (csrf) headers["X-CSRF-Token"] = csrf;
    }
    if (options.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort("timeout"), options.timeoutMs ?? DEFAULT_TIMEOUT_MS);
    options.signal?.addEventListener("abort", () => controller.abort("aborted"), { once: true });

    let response: Response;
    try {
      response = await fetchImpl(buildUrl(base, path, options.query), {
        method,
        headers,
        body: options.body === undefined ? undefined : isForm ? (options.body as FormData) : JSON.stringify(options.body),
        credentials: "include",
        signal: controller.signal,
      });
    } catch (cause) {
      const reason = controller.signal.reason;
      if (reason === "timeout") {
        throw new ApiError({ kind: "timeout", code: "TIMEOUT", message: "请求超时，请稍后重试。", retryable: true });
      }
      if (reason === "aborted") {
        throw new ApiError({ kind: "aborted", code: "ABORTED", message: "请求已取消。" });
      }
      throw new ApiError({
        kind: "network",
        code: "NETWORK_ERROR",
        message: "连不上服务，请检查网络后重试。",
        retryable: true,
        details: { cause: cause instanceof Error ? cause.message : String(cause) },
      });
    } finally {
      clearTimeout(timeout);
    }

    const requestId = response.headers.get("X-Request-ID");
    if (response.status === 204) return undefined as T;
    const text = await response.text();
    let payload: unknown = null;
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        payload = null;
      }
    }
    if (!response.ok) {
      if (isEnvelope(payload)) throw ApiError.fromEnvelope(response.status, payload, requestId);
      throw new ApiError({
        kind: "http",
        status: response.status,
        code: response.status >= 500 ? "UPSTREAM_UNAVAILABLE" : "INTERNAL_ERROR",
        message: response.status === 502 || response.status === 504 ? "服务暂时连不上。" : "请求未能完成。",
        requestId,
        retryable: response.status >= 500,
      });
    }
    return payload as T;
  }

  return { request, base };
}

export const apiClient = createApiClient();
