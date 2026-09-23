import { describe, expect, it, vi } from "vitest";
import { createApiClient } from "@/shared/api/client";
import { ApiError } from "@/shared/api/errors";

function respond(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });
}

describe("api client", () => {
  it("maps the error envelope to ApiError with request_id", async () => {
    const fetchImpl = vi.fn(async () =>
      respond(401, { error: { code: "AUTH_REQUIRED", message: "需要登录后才能继续。", request_id: "req_abc12345", retryable: false, details: null } }, { "X-Request-ID": "req_abc12345" }),
    );
    const api = createApiClient("/api/v1/web", fetchImpl as unknown as typeof fetch);
    const err = (await api.request("/home").catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("AUTH_REQUIRED");
    expect(err.isAuth).toBe(true);
    expect(err.requestId).toBe("req_abc12345");
  });

  it("treats 501 capability errors as capability, not as a crash", async () => {
    const fetchImpl = vi.fn(async () =>
      respond(501, { error: { code: "CAPABILITY_UNAVAILABLE", message: "这项能力尚未接入。", request_id: "req_x0000001", retryable: false, details: { capability: "social.feed" } } }),
    );
    const err = (await createApiClient("/api/v1/web", fetchImpl as unknown as typeof fetch).request("/circle/feed").catch((e: unknown) => e)) as ApiError;
    expect(err.kind).toBe("capability");
    expect(err.details?.capability).toBe("social.feed");
  });

  it("normalizes network failures and 502 without an envelope", async () => {
    const down = createApiClient("/api/v1/web", (async () => {
      throw new TypeError("Failed to fetch");
    }) as unknown as typeof fetch);
    await expect(down.request("/meta")).rejects.toMatchObject({ kind: "network", code: "NETWORK_ERROR", retryable: true });
    const proxy = createApiClient("/api/v1/web", (async () => new Response("Bad Gateway", { status: 502 })) as unknown as typeof fetch);
    await expect(proxy.request("/meta")).rejects.toMatchObject({ code: "UPSTREAM_UNAVAILABLE", retryable: true });
  });

  it("sends CSRF from cookie and the idempotency key on writes, with cookies included", async () => {
    document.cookie = "petsoul_csrf=csrf-token-value";
    const fetchImpl = vi.fn(async () => respond(200, { ok: true }));
    await createApiClient("/api/v1/web", fetchImpl as unknown as typeof fetch).request("/farm/actions", { method: "POST", body: { a: 1 }, idempotencyKey: "farm:abc12345" });
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    expect(url).toBe("/api/v1/web/farm/actions");
    expect(init.credentials).toBe("include");
    expect(headers["X-CSRF-Token"]).toBe("csrf-token-value");
    expect(headers["Idempotency-Key"]).toBe("farm:abc12345");
  });
});
