import { render, screen, fireEvent, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import type { ApiClient } from "@/shared/api/client";
import { ApiError } from "@/shared/api/errors";
import type { HouseholdSettings, PhotoRequestResult, PhotoRequestView } from "@/shared/contracts";
import { buildServices } from "@/shared/services/registry";
import petsModule from "@/features/pets/module";
import householdModule from "@/features/household/module";
import { PhotoConsentSetting } from "@/features/household/HouseholdPage";
import { PhotoConsentNotice, PhotoFeedback, PhotoRequestCard, canRequestPhoto, currentPhotoRequestNotice, currentPhotoRetryNote } from "@/features/pets/PhotoRequestsPage";
import { beginPhotoIntent, clearPhotoIntent, readPhotoIntent, sendPhotoIntent } from "@/features/pets/photoIntent";
import type { PetsService } from "@/shared/services/types";

const row: PhotoRequestView = {
  request_id: "pr-1", task_id: "task-1", scene: "flight_adventure", narrative: "fictional_adventure", fictional: true,
  captured_at: "2026-09-23T00:00:00Z", place: "想象中的云端", city: "想象中的城市",
  photo_status: "unknown", image_url: null, can_retry: true,
};

describe("0.4.5 owner photo UI", () => {
  it("uses the unified pet service for explicit request, read-only list and retry", async () => {
    const request = vi.fn(async (path: string) => path.includes("retry-image") ? [row] : path.endsWith("photo-requests") ? [] : { request_id: "pr-1", task_id: null });
    const services = buildServices([petsModule], { mode: "live", api: { request } as unknown as ApiClient });
    const signal = new AbortController().signal;
    await services.pets.requestPhoto("pet-1", { scene: "flight_adventure", narrative: "fictional_adventure" }, "click-1");
    await services.pets.photoRequests("pet-1", signal);
    await services.pets.retryPhoto("pet-1", "pr-1");
    expect(request).toHaveBeenNthCalledWith(1, "/pets/pet-1/photo-request", { method: "POST", body: { scene: "flight_adventure", narrative: "fictional_adventure" }, idempotencyKey: "click-1" });
    expect(request).toHaveBeenNthCalledWith(2, "/pets/pet-1/photo-requests", { signal });
    expect(request).toHaveBeenNthCalledWith(3, "/pets/pet-1/photo-requests/pr-1/retry-image", { method: "POST" });
  });

  it("separates unknown from failed and only offers explicit redraw when allowed", () => {
    const onRetry = vi.fn();
    const view = render(<PhotoRequestCard item={row} onRetry={onRetry} retrying={false} />);
    expect(screen.getByText("结果还没确认")).toBeTruthy();
    expect(screen.getByText(/可能已经开始制作/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "我决定重画这张" }));
    expect(onRetry).toHaveBeenCalledWith("pr-1");
    view.rerender(<PhotoRequestCard item={{ ...row, photo_status: "processing", can_retry: false }} onRetry={onRetry} retrying={false} />);
    expect(screen.queryByRole("button", { name: "我决定重画这张" })).toBeNull();
    view.rerender(<PhotoRequestCard item={{ ...row, photo_status: "failed", can_retry: true }} onRetry={onRetry} retrying={false} />);
    expect(screen.getByText("没画成")).toBeTruthy();
  });

  it("explains a scene 409 in player language", () => {
    render(<PhotoFeedback scene="train" error={new ApiError({ kind: "http", status: 409, code: "CONFLICT", message: "not on train" })} />);
    expect(screen.getByRole("alert").textContent).toContain("TA 现在不在列车上");
  });

  it("explains care-permission refusal without claiming a queued photo", () => {
    const view = render(<PhotoFeedback scene="home" error={new ApiError({ kind: "http", status: 403, code: "FORBIDDEN", message: "no care" })} />);
    expect(view.container.textContent).toContain("没有照顾 TA 的权限");
    expect(view.container.textContent).toContain("不能申请这张照片");
  });

  it("keeps the same key and payload after the server accepted a request but the response was lost, then gives a new confirmed application a new key", async () => {
    sessionStorage.clear();
    const actualTasks = new Map<string, string>();
    let dropFirstResponse = true;
    const requestPhoto = vi.fn(async (_petId: string, body: { scene: string }, key: string) => {
      if (!actualTasks.has(key)) actualTasks.set(key, `task-${actualTasks.size + 1}`);
      if (dropFirstResponse) {
        dropFirstResponse = false;
        throw new ApiError({ kind: "network", code: "NETWORK_ERROR", message: "browser lost response", retryable: true });
      }
      return { request_id: `request-${key}`, task_id: actualTasks.get(key)!, scene: body.scene, fictional: body.scene === "flight_adventure" };
    });
    const pets = { requestPhoto } as unknown as PetsService;
    const first = beginPhotoIntent("user-a", "pet-a", "home");
    await expect(sendPhotoIntent(pets, first)).rejects.toThrow("browser lost response");
    expect(actualTasks.size).toBe(1); // 单元替身模拟服务端已受理、浏览器只丢了回执；不是 HTTP 证据。
    const restored = readPhotoIntent("user-a", "pet-a");
    expect(restored).toEqual(first);
    const retry = beginPhotoIntent("user-a", "pet-a", "flight_adventure", restored);
    expect(retry).toEqual(first); // 即使用户试图换场景，未确认的申请仍是原 payload。
    await sendPhotoIntent(pets, retry);
    expect(requestPhoto).toHaveBeenNthCalledWith(2, "pet-a", first.body, first.key);
    expect(actualTasks.size).toBe(1);
    expect(readPhotoIntent("user-a", "pet-a")).toBeNull();
    const newApplication = beginPhotoIntent("user-a", "pet-a", "flight_adventure");
    expect(newApplication.key).not.toBe(first.key);
    await sendPhotoIntent(pets, newApplication);
    expect(actualTasks.size).toBe(2); // 只有明确拿回首次回执后，用户新拍照才建第二个任务。
    clearPhotoIntent(newApplication);
  });

  it("keeps pending application isolated by both account and pet", () => {
    sessionStorage.clear();
    const pending = beginPhotoIntent("user-a", "pet-a", "train");
    expect(readPhotoIntent("user-a", "pet-a")).toEqual(pending);
    expect(readPhotoIntent("user-a", "pet-b")).toBeNull();
    expect(readPhotoIntent("user-b", "pet-a")).toBeNull();
    clearPhotoIntent(pending);
  });

  it("drops an old processing note when the refreshed result becomes ready", () => {
    const note = { scope: "user-a:pet-a", requestId: "pr-1", status: "processing" as const, text: "正在生成" };
    expect(currentPhotoRetryNote(note, [{ ...row, photo_status: "processing", can_retry: false }], "user-a:pet-a")).toBe("正在生成");
    expect(currentPhotoRetryNote(note, [{ ...row, photo_status: "ready", image_url: "/photo.png", can_retry: false }], "user-a:pet-a")).toBeNull();
    expect(currentPhotoRetryNote(note, [{ ...row, photo_status: "processing", can_retry: false }], "user-b:pet-b")).toBeNull();
  });

  it("hides an accepted request receipt once its exact result appears, while a null task stays unqueued", () => {
    const accepted: PhotoRequestResult = {
      request_id: "pr-1", task_id: "task-1", scene: "flight_adventure", narrative: "fictional_adventure", fictional: true,
      captured_at: "2026-09-23T00:00:00Z", place: "想象中的云端", city: "想象中的城市",
    };
    expect(currentPhotoRequestNotice(accepted, [])).toContain("申请已经送达");
    expect(currentPhotoRequestNotice(accepted, [{ ...row, photo_status: "failed" }])).toBeNull();
    expect(currentPhotoRequestNotice(accepted, [{ ...row, request_id: "pr-other" }])).toContain("申请已经送达");
    expect(currentPhotoRequestNotice({ ...accepted, task_id: null }, [])).toContain("没有照片在等待");
  });

  it("sends the existing household settings PATCH with the explicit photo consent value", async () => {
    const request = vi.fn(async () => ({ settings: { generated_photos: true } }));
    const services = buildServices([householdModule], { mode: "live", api: { request } as unknown as ApiClient });
    await services.households.updateSettings("house-1", { generated_photos: true });
    await services.households.updateSettings("house-1", { generated_photos: false });
    expect(request).toHaveBeenNthCalledWith(1, "/households/house-1/settings", { method: "PATCH", body: { generated_photos: true } });
    expect(request).toHaveBeenNthCalledWith(2, "/households/house-1/settings", { method: "PATCH", body: { generated_photos: false } });
  });

  it("requires an administrator's explicit choice and leaves caregivers read-only", () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const onChange = vi.fn();
    const view = render(<PhotoConsentSetting enabled={false} canManage pending={false} error={null} onChange={onChange} />);
    fireEvent.click(within(view.container).getByRole("button", { name: "明确开启照片制作" }));
    expect(onChange).toHaveBeenCalledWith(true);
    view.rerender(<PhotoConsentSetting enabled canManage pending={false} error={null} onChange={onChange} />);
    fireEvent.click(within(view.container).getByRole("button", { name: "关闭照片制作" }));
    expect(onChange).toHaveBeenCalledWith(false);
    view.rerender(<PhotoConsentSetting enabled={false} canManage={false} pending={false} error={null} onChange={onChange} />);
    expect(within(view.container).queryByRole("button")).toBeNull();
    expect(view.container.textContent).toContain("只有家庭管理员");
    confirm.mockRestore();
  });

  it("gates new photo commands on the current household permission and explains a known refusal", () => {
    const settings: HouseholdSettings = { name: null, caregivers_can_spend: false, generated_photos: false, pet_messages: false, public_posts: false };
    expect(canRequestPhoto("home", false, true, false, false)).toBe(false);
    expect(canRequestPhoto("flight_adventure", false, false, false, false)).toBe(false);
    expect(canRequestPhoto("home", true, true, false, false)).toBe(true);
    expect(canRequestPhoto("home", false, false, false, true)).toBe(true); // 仅恢复先前未确认的同一请求。
    const view = render(<MemoryRouter><PhotoConsentNotice detail={{ settings, your_permissions: ["manage"] }} /></MemoryRouter>);
    expect(within(view.container).getByRole("link", { name: /去家庭设置开启/ }).getAttribute("href")).toBe("/households/manage");
    view.rerender(<MemoryRouter><PhotoConsentNotice detail={{ settings, your_permissions: ["view"] }} /></MemoryRouter>);
    expect(within(view.container).queryByRole("link")).toBeNull();
    expect(view.container.textContent).toContain("请家庭管理员");
    view.rerender(<MemoryRouter><PhotoConsentNotice detail={{ settings: { ...settings, generated_photos: true }, your_permissions: ["manage"] }} /></MemoryRouter>);
    expect(view.container.textContent).toBe("");
  });

  it("does not call an accepted settings write unchanged when its response is lost", async () => {
    let savedOnServer = false;
    const lostReceipt = new ApiError({ kind: "network", code: "NETWORK_ERROR", message: "response lost", retryable: true });
    const serverPatch = vi.fn(async () => { savedOnServer = true; throw lostReceipt; });
    const serverRead = vi.fn(async () => savedOnServer);
    await expect(serverPatch()).rejects.toBe(lostReceipt);
    expect(await serverRead()).toBe(true);
    const view = render(<PhotoConsentSetting enabled={false} canManage pending={false} error={lostReceipt} onChange={vi.fn()} />);
    expect(view.container.textContent).toContain("保存结果未确认");
    expect(view.container.textContent).not.toContain("设置没有改变");
  });
});
