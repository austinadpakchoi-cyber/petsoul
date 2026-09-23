import { describe, expect, it, vi } from "vitest";
import type { ApiClient } from "@/shared/api/client";
import { createLiveTransportService } from "@/features/transport/service";

describe("0.4.1 journey: pet-scoped departure and advice", () => {
  it("sends the selected pet to destination, plan, suggestion and departure endpoints", async () => {
    const request = vi.fn(async (path: string) => path === "/journey/depart"
      ? { server_time: "2026-09-23T01:00:00Z" }
      : []);
    const transport = createLiveTransportService({
      mode: "live",
      api: { request, base: "/api/v1/web" } as unknown as ApiClient,
    });
    const signal = new AbortController().signal;

    await transport.destinations("pet-b", signal);
    await transport.plan("harbour_cafe", "pet-b", signal);
    await transport.suggestions("pet-b", signal);
    await transport.guides("pet-b", signal);
    await transport.suggest("harbour_cafe", "pet-b");
    await transport.guide("guide-1", signal);
    await transport.depart("harbour_cafe", "depart-key", "pet-b");

    expect(request).toHaveBeenNthCalledWith(1, "/journey/destinations", { query: { pet_id: "pet-b" }, signal });
    expect(request).toHaveBeenNthCalledWith(2, "/journey/plan", { query: { destination_key: "harbour_cafe", pet_id: "pet-b" }, signal });
    expect(request).toHaveBeenNthCalledWith(3, "/journey/suggestions", { query: { pet_id: "pet-b" }, signal });
    expect(request).toHaveBeenNthCalledWith(4, "/guides", { query: { pet_id: "pet-b" }, signal });
    expect(request).toHaveBeenNthCalledWith(5, "/journey/suggest", {
      method: "POST", query: { pet_id: "pet-b" }, body: { destination_key: "harbour_cafe" },
    });
    expect(request).toHaveBeenNthCalledWith(6, "/guides/guide-1", { signal });
    expect(request).toHaveBeenNthCalledWith(7, "/journey/depart", {
      method: "POST", query: { pet_id: "pet-b" }, body: { destination_key: "harbour_cafe" }, idempotencyKey: "depart-key",
    });
  });
});
