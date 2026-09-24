/**
 * 家园统一宠物形象入口（CR-PLAYER-CHARACTER-01 前端部分），按已生成的正式契约 `CharacterState` 写。
 * 后端三条角色路由当前 not_implemented：这里是隔离状态用例，只证明页面对各状态的呈现与请求边界，
 * 不证明自动生成、权限、真实成图或 alpha 质量。
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CharacterReasonValues, type CharacterAsset, type CharacterIdPhoto, type CharacterState, type HomeSnapshot, type WebMeta } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { HomeScene } from "@/features/home/HomeScene";
import { AdjustCharacter, characterNote, IdPhotoAdjust, idPhotoReasonText, reasonText, referenceBodyHeight, sceneAsset, usePetCharacter } from "@/features/home/PetFigure";
import { fixtureHomeSnapshot } from "@/fixtures/home";

vi.mock("@/shared/config/env", () => ({ env: { dataMode: "live", isDev: false, apiBase: "/api/v1/web" } }));

afterEach(cleanup);

function asset(overrides: Partial<CharacterAsset> = {}): CharacterAsset {
  return {
    asset_id: "ca-1", pose: "neutral_full", url: "/api/v1/web/media/characters/ca-1", content_sha256: "a".repeat(64), content_type: "image/png",
    width: 800, height: 1000, content_box: { left: 200, top: 200, right: 600, bottom: 960 }, anchor: { x: 0.5, y: 0.96, measured: true }, opaque_ratio: 0.31, has_alpha: true,
    ...overrides,
  };
}

function state(overrides: Partial<CharacterState> = {}): CharacterState {
  return { pet_id: "pet-1", status: "absent", active: null, candidate: null, can_regenerate: false, blocked_reason: null, ...overrides };
}

function active(assets: CharacterAsset[], revision = 3): NonNullable<CharacterState["active"]> {
  return { character_set_id: "cs-1", pet_id: "pet-1", revision, reference_version: 1, style_version: "v1", assets, published_at: "2026-09-23T12:00:00Z" };
}

function snapshot(presence: HomeSnapshot["presence"] = "at_home"): HomeSnapshot {
  const base = fixtureHomeSnapshot();
  return { ...base, data_origin: "live", presence, journey: null, pet: { ...base.pet, pet_id: "pet-1", name: "栗子", photo_url: "/photo/pet-1.jpg", photo_generated: false } } as HomeSnapshot;
}

function renderScene(character: CharacterState | null, presence: HomeSnapshot["presence"] = "at_home", room = "/") {
  return render(<MemoryRouter initialEntries={[room]}><HomeScene snapshot={snapshot(presence)} worldCharacter={character} /></MemoryRouter>);
}

describe("character state → words (real contract enums)", () => {
  it("absent is 'no task yet' — no progress; a blocked pet gets a short honest tag", () => {
    expect(characterNote(state({ status: "absent" }))).toBeNull();
    expect(characterNote(state({ status: "absent", blocked_reason: "no_reference_photo" }))).toBe("还没有星球形象");
  });
  it("every contract reason code has its own player wording (none falls to the generic line or echoes the code)", () => {
    for (const code of CharacterReasonValues) {
      const text = reasonText(code);
      expect(text, code).not.toBe("这一次没有准备好。");
      expect(text, code).not.toContain(code);
    }
  });
  it("server reason codes become player words and a raw code is never shown", () => {
    expect(reasonText("no_reference_photo")).toBe("还没有 TA 的照片，暂时没法准备形象。");
    expect(reasonText("pet_has_no_household")).toBe("TA 还没有加入家庭，暂时没法准备形象。");
    // 用户决定不再询问授权后，许可类原因码已从契约删除；旧数据里若还出现，只给泛化说法、不提许可
    expect(reasonText("consent_missing")).toBe("这一次没有准备好。");
    expect(reasonText("constructor")).toBe("这一次没有准备好。");
    expect(reasonText("already_queued")).toBe("新的形象已经在准备了。");
    expect(reasonText("some_future_code")).toBe("这一次没有准备好。");
    expect(reasonText(null)).toBeNull();
  });
  it("queued/running prepare, failed did not draw, unknown is unconfirmed (never 'not generated')", () => {
    expect(characterNote(state({ status: "queued" }))).toBe("正在准备 TA 的形象");
    expect(characterNote(state({ status: "running" }))).toBe("正在准备 TA 的形象");
    expect(characterNote(state({ status: "failed" }))).toBe("形象这次没画成");
    expect(characterNote(state({ status: "unknown" }))).toBe("形象结果还没确认");
  });
  it("各姿态按中性站姿的身体高度定比例：趴着睡的不被放大成站着那么高", () => {
    const neutral = asset(); // 主体 200→960，高 760
    const sleeping = asset({ asset_id: "ca-2", pose: "sleeping", content_box: { left: 100, top: 600, right: 700, bottom: 960 } }); // 主体高 360
    expect(referenceBodyHeight(state({ status: "ready", active: active([neutral, sleeping]) }), sleeping)).toBe(760);
    // 这一套里没有可用的中性站姿，才按自己的主体高度撑满。
    expect(referenceBodyHeight(state({ status: "ready", active: active([sleeping]) }), sleeping)).toBe(360);
    expect(referenceBodyHeight(state({ status: "ready", active: active([asset({ has_alpha: false }), sleeping]) }), sleeping)).toBe(360);
  });

  it("only alpha-verified assets go into the scene; sleeping falls back to neutral_full", () => {
    expect(sceneAsset(state({ status: "ready", active: active([asset({ has_alpha: false })]) }))).toBeNull();
    // 有 alpha 但几乎全不透明（背景没抠掉）或几乎全透明（主体被裁没）也不放进场景。
    expect(sceneAsset(state({ status: "ready", active: active([asset({ opaque_ratio: 0.98 })]) }))).toBeNull();
    expect(sceneAsset(state({ status: "ready", active: active([asset({ opaque_ratio: 0.01 })]) }))).toBeNull();
    expect(sceneAsset(state({ status: "ready", active: active([asset()]) }), "sleeping")?.pose).toBe("neutral_full");
    expect(sceneAsset(state({ status: "ready", active: active([asset(), asset({ asset_id: "ca-2", pose: "sleeping" })]) }), "sleeping")?.asset_id).toBe("ca-2");
  });
});

describe("home figure", () => {
  it("places the active character by content box and ground anchor, not by canvas size", () => {
    renderScene(state({ status: "ready", active: active([asset()]) }));
    const figure = screen.getByTestId("pet-character");
    expect(figure.getAttribute("data-revision")).toBe("3");
    const img = within(figure).getByRole("img", { name: "栗子的星球形象" }) as HTMLImageElement;
    expect(img.getAttribute("src")).toBe("/api/v1/web/media/characters/ca-1");
    // 主体高 760px / 画布 1000px → 图片高度 = 容器的 1000/760。
    expect(img.style.height).toBe("131.58%");
    expect(img.style.transform).toBe("translate(-50%, 4%)");
    expect(document.querySelector(".ps-living-pet__identity")).toBeNull();
  });

  it("屋内用睡姿；睡姿按站姿的身体高度定比例，不被放大", () => {
    const sleeping = asset({ asset_id: "ca-2", pose: "sleeping", url: "/api/v1/web/media/characters/ca-2", content_box: { left: 100, top: 600, right: 700, bottom: 960 } });
    renderScene(state({ status: "ready", active: active([asset(), sleeping]) }), "at_home", "/?room=inside");
    const img = within(screen.getByTestId("pet-character")).getByRole("img", { name: "栗子的星球形象" }) as HTMLImageElement;
    expect(img.getAttribute("src")).toBe("/api/v1/web/media/characters/ca-2");
    // 画布 1000 / 站姿主体 760 = 131.58%（若按睡姿自己的 360 会是 277.78%，TA 会被放大一倍多）。
    expect(img.style.height).toBe("131.58%");
  });

  it("keeps the active character while a new candidate fails", () => {
    renderScene(state({ status: "failed", active: active([asset()], 2), candidate: { status: "failed", pose: "neutral_full", reference_version: 2, style_version: "v1", queued_at: "2026-09-23T12:10:00Z", reason: "供应商这次没有返回图片", task_id: "t-9" } }));
    expect(screen.getByTestId("pet-character").getAttribute("data-revision")).toBe("2");
    expect(screen.queryByTestId("pet-character-note")).toBeNull();
  });

  // 2026-09-24：场景里 TA 身下不再挂状态小牌（巡检：小窝里一直挂着“还没有星球形象”）。
  // 状态仍说得出：TA 的无障碍名称带着它，点 TA 冒出的气泡里写“在家 · …”（“陪 TA 待一会儿”面板同一句）。
  it.each([
    ["queued", "正在准备 TA 的形象", null],
    ["running", "正在准备 TA 的形象", null],
    ["failed", "形象这次没画成", null],
    ["unknown", "形象结果还没确认", null],
    ["absent", "还没有星球形象", "no_reference_photo"],
  ] as const)("without an active character (%s) keeps the photo as a temporary portrait; no tag in the scene, TA says it when tapped", (status, note, blocked) => {
    renderScene(state({ status, blocked_reason: blocked }));
    expect(screen.queryByTestId("pet-character-note")).toBeNull();
    expect(document.querySelector(".ps-pet-figure__note")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: `看看 栗子，${note}` }));
    expect(screen.getByRole("group", { name: "栗子" }).querySelector(".ps-home-bubble__detail")?.textContent).toBe(`在家 · ${note}`);
    expect(screen.queryByRole("button", { name: /^(开始)?(生成|确认|重画|调整)/ })).toBeNull();
  });

  it("absent shows no spinner and no generate button", () => {
    renderScene(state({ status: "absent" }));
    expect(screen.queryByTestId("pet-character-note")).toBeNull();
    expect(screen.queryByTestId("pet-character-preparing")).toBeNull();
    expect(screen.queryByRole("button", { name: /^(开始)?(生成|确认)/ })).toBeNull();
  });

  it("the preparing animation only runs while a real task is queued or running", () => {
    for (const status of ["queued", "running"] as const) {
      renderScene(state({ status }));
      expect(screen.getByTestId("pet-character-preparing")).toBeTruthy();
      cleanup();
    }
    for (const status of ["absent", "failed", "unknown"] as const) {
      renderScene(state({ status, blocked_reason: status === "absent" ? "no_reference_photo" : null }));
      expect(screen.queryByTestId("pet-character-preparing")).toBeNull();
      cleanup();
    }
  });

  it("does not seat the character at home while TA is out", () => {
    renderScene(state({ status: "ready", active: active([asset()]) }), "in_transit");
    expect(screen.queryByTestId("pet-character")).toBeNull();
  });
});

const metaWith = (status: "available" | "not_implemented"): WebMeta => ({
  api_prefix: "/api/v1/web", contract_version: "0.4.5", server_time: "2026-09-23T12:00:00Z", backend_version: "test", data_origin: "live", auth_methods_available: [], applied_migrations: [],
  capabilities: [
    { key: "character.state", module: "character", status, note: null },
    { key: "character.regenerate", module: "character", status, note: null },
  ],
});

function wrapper(services: Record<string, unknown>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}><ServicesProvider services={services as unknown as ServiceMap}><MemoryRouter>{children}</MemoryRouter></ServicesProvider></QueryClientProvider>;
}

describe("reading the character respects the capability switch", () => {
  it("does not call the endpoint while meta reports not_implemented", async () => {
    const character = vi.fn();
    const meta = vi.fn(async () => metaWith("not_implemented"));
    const { result } = renderHook(() => usePetCharacter("pet-1"), { wrapper: wrapper({ platform: { meta }, pets: { character } }) });
    await waitFor(() => expect(meta).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(character).not.toHaveBeenCalled();
    expect(result.current).toBeNull();
  });

  it("reads once when available (pure read; nothing else is sent)", async () => {
    const character = vi.fn(async () => state({ status: "queued" }));
    const regenerateCharacter = vi.fn();
    const { result } = renderHook(() => usePetCharacter("pet-1"), { wrapper: wrapper({ platform: { meta: async () => metaWith("available") }, pets: { character, regenerateCharacter } }) });
    await waitFor(() => expect(result.current?.status).toBe("queued"));
    expect(character).toHaveBeenCalledWith("pet-1", expect.any(AbortSignal));
    expect(regenerateCharacter).not.toHaveBeenCalled();
  });
});

describe("pet sheet: reason and optional entry", () => {
  it("is hidden until the regenerate capability is available", async () => {
    const meta = vi.fn(async () => metaWith("not_implemented"));
    render(<AdjustCharacter petId="pet-1" state={state({ status: "unknown", can_regenerate: true })} />, { wrapper: wrapper({ platform: { meta }, pets: { regenerateCharacter: vi.fn() } }) });
    await waitFor(() => expect(meta).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: /形象/ })).toBeNull();
  });

  it("explains a blocked pet in words with no consent detour, no button, and never the raw code", async () => {
    const view = render(<AdjustCharacter petId="pet-1" state={state({ status: "absent", can_regenerate: false, blocked_reason: "pet_has_no_household" })} />, { wrapper: wrapper({ platform: { meta: async () => metaWith("available") }, pets: { regenerateCharacter: vi.fn() } }) });
    expect(await screen.findByText("TA 还没有加入家庭，暂时没法准备形象。")).toBeTruthy();
    // 不再询问授权：不指向任何“去开许可”的入口
    expect(screen.queryByRole("link")).toBeNull();
    expect(view.container.textContent).not.toMatch(/许可|授权/);
    expect(screen.queryByRole("button", { name: /形象/ })).toBeNull();
    expect(view.container.textContent).not.toContain("pet_has_no_household");
  });

  it("sends the key in the Idempotency-Key argument: same key after a lost response, a new one after a definite answer", async () => {
    const keys: string[] = [];
    const bodies: unknown[] = [];
    const regenerateCharacter = vi
      .fn<(petId: string, body: unknown, key: string) => Promise<unknown>>()
      .mockImplementationOnce(async (_p, body, key) => { keys.push(key); bodies.push(body); throw new ApiError({ kind: "network", code: "NETWORK_ERROR", message: "网络连接失败", retryable: true }); })
      .mockImplementationOnce(async (_p, body, key) => { keys.push(key); bodies.push(body); return { accepted: true, status: "queued", task_id: "t-1", reason: null }; })
      .mockImplementationOnce(async (_p, body, key) => { keys.push(key); bodies.push(body); return { accepted: false, status: "queued", task_id: null, reason: "already_queued" }; });
    const view = render(<AdjustCharacter petId="pet-1" state={state({ status: "unknown", can_regenerate: true })} />, { wrapper: wrapper({ platform: { meta: async () => metaWith("available") }, pets: { regenerateCharacter } }) });
    const button = await screen.findByRole("button", { name: "重新准备 TA 的形象" });
    fireEvent.click(button);
    expect(await screen.findByRole("alert")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "重新准备 TA 的形象" }));
    await waitFor(() => expect(regenerateCharacter).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByRole("button", { name: "重新准备 TA 的形象" }));
    await waitFor(() => expect(regenerateCharacter).toHaveBeenCalledTimes(3));
    expect(keys[0]).toBe(keys[1]);
    expect(keys[2]).not.toBe(keys[1]);
    expect(bodies[0]).toEqual({ pose: "neutral_full", note: null });
    expect(await screen.findByText("新的形象已经在准备了。")).toBeTruthy();
    expect(view.container.textContent).not.toContain("already_queued");
  });

  it("names the entry by what it does: adjust an existing figure vs prepare the first one", async () => {
    const services = { platform: { meta: async () => metaWith("available") }, pets: { regenerateCharacter: vi.fn() } };
    render(<AdjustCharacter petId="pet-1" state={state({ status: "ready", active: active([asset()]), can_regenerate: true })} />, { wrapper: wrapper(services) });
    expect(await screen.findByRole("button", { name: "调整形象" })).toBeTruthy();
    cleanup();
    render(<AdjustCharacter petId="pet-1" state={state({ status: "absent", can_regenerate: true })} />, { wrapper: wrapper(services) });
    expect(await screen.findByRole("button", { name: "为 TA 准备形象" })).toBeTruthy();
  });
});

/* ---------- 证件照（CR-6C2B-IDPHOTO）：存量宠物只能在这里拿到第一张 ---------- */

const metaWithIdPhoto = (): WebMeta => {
  const base = metaWith("available");
  return { ...base, capabilities: [...base.capabilities, { key: "character.id_photo", module: "character", status: "available", note: null }] };
};

function idPhoto(overrides: Partial<CharacterIdPhoto> = {}): CharacterIdPhoto {
  return { status: "absent", source: null, url: null, avatar_url: null, width: null, height: null, content_sha256: null, reference_version: null, revision: null, reason: null, task_id: null, ...overrides };
}

const READY_GENERATED = idPhoto({ status: "ready", source: "generated", url: "/api/v1/web/media/id-photos/ip-1", avatar_url: "/api/v1/web/media/id-photos/ip-1/avatar", width: 900, height: 1200, revision: 1 });

describe("ID photo: first one for existing pets, redo only when there is one", () => {
  it("every reason reads as an ID-photo sentence: never says 形象, never echoes the code, never the generic line", () => {
    for (const code of CharacterReasonValues) {
      const text = idPhotoReasonText(code);
      expect(text, code).toBeTruthy();
      expect(text, code).not.toContain("形象");
      expect(text, code).not.toContain(code);
      expect(text, code).not.toBe("这一次没有准备好。");
    }
    expect(idPhotoReasonText("already_queued")).toBe("新的证件照已经在准备了。");
  });

  it("stays hidden until meta reports character.id_photo", async () => {
    const meta = vi.fn(async () => metaWith("available"));
    render(<IdPhotoAdjust petId="pet-1" idPhoto={null} canRequest />, { wrapper: wrapper({ platform: { meta }, pets: { regenerateIdPhoto: vi.fn() } }) });
    await waitFor(() => expect(meta).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.queryByTestId("id-photo-adjust")).toBeNull();
  });

  // 2026-09-24 修：这一条原来用的是 can_regenerate: false（state() 的默认值），按钮照样出现——那正是“点了必然被拒”的死路按钮。
  // 服务端允许（can_regenerate: true）时才该有按钮；不允许的情形见下面“服务端不允许”那组。
  it("an existing pet without one gets “生成证件照” (not 重画); a definite yes says it is being prepared", async () => {
    const regenerateIdPhoto = vi.fn(async () => ({ accepted: true, status: "queued" as const, task_id: "t-9", reason: null }));
    render(<AdjustCharacter petId="pet-1" state={state({ status: "ready", active: active([asset()]), id_photo: undefined, can_regenerate: true })} />, { wrapper: wrapper({ platform: { meta: async () => metaWithIdPhoto() }, pets: { regenerateIdPhoto, regenerateCharacter: vi.fn() } }) });
    const button = await screen.findByRole("button", { name: "生成证件照" });
    expect(screen.queryByRole("button", { name: "重画证件照" })).toBeNull();
    expect(screen.getByText("还没有证件照：护照、居民证、驾照都会用它。")).toBeTruthy();
    fireEvent.click(button);
    expect(await screen.findByText("证件照已经在准备了。")).toBeTruthy();
    expect(regenerateIdPhoto).toHaveBeenCalledWith("pet-1", expect.any(String));
  });

  it("with a generated one: shows it and offers “重画证件照”", async () => {
    render(<IdPhotoAdjust petId="pet-1" idPhoto={READY_GENERATED} canRequest />, { wrapper: wrapper({ platform: { meta: async () => metaWithIdPhoto() }, pets: { regenerateIdPhoto: vi.fn() } }) });
    expect(await screen.findByRole("button", { name: "重画证件照" })).toBeTruthy();
    expect(screen.getByRole("img", { name: "TA 的证件照" }).getAttribute("src")).toBe("/api/v1/web/media/id-photos/ip-1");
  });

  it("using TA's own photo (companion_portrait): shows it, says so, and offers no button (the server would refuse)", async () => {
    render(<IdPhotoAdjust petId="pet-1" idPhoto={idPhoto({ status: "ready", source: "companion_portrait", url: "/api/v1/web/media/pets/pet-1/photo" })} canRequest />, { wrapper: wrapper({ platform: { meta: async () => metaWithIdPhoto() }, pets: { regenerateIdPhoto: vi.fn() } }) });
    expect(await screen.findByText("证件照先用 TA 现在的照片。")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /证件照/ })).toBeNull();
  });

  it("queued / running: “正在准备”, no button; unknown: not confirmed yet, no button (a retry could pay twice)", async () => {
    const services = { platform: { meta: async () => metaWithIdPhoto() }, pets: { regenerateIdPhoto: vi.fn() } };
    for (const status of ["queued", "running"] as const) {
      render(<IdPhotoAdjust petId="pet-1" idPhoto={idPhoto({ status })} canRequest />, { wrapper: wrapper(services) });
      expect(await screen.findByText("证件照正在准备。")).toBeTruthy();
      expect(screen.queryByRole("button", { name: /证件照/ })).toBeNull();
      cleanup();
    }
    render(<IdPhotoAdjust petId="pet-1" idPhoto={idPhoto({ status: "unknown" })} canRequest />, { wrapper: wrapper(services) });
    expect(await screen.findByText("上一次证件照的结果还没确认，先别重复点。")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /证件照/ })).toBeNull();
  });

  it("failed without one: the reason in words (never the code) and “生成证件照” again", async () => {
    const view = render(<IdPhotoAdjust petId="pet-1" idPhoto={idPhoto({ status: "failed", source: "generated", reason: "photo_head_cut_off" })} canRequest />, { wrapper: wrapper({ platform: { meta: async () => metaWithIdPhoto() }, pets: { regenerateIdPhoto: vi.fn() } }) });
    expect(await screen.findByText("这一版证件照 TA 的头太靠边，做头像会被裁掉，没有用上。")).toBeTruthy();
    expect(screen.getByRole("button", { name: "生成证件照" })).toBeTruthy();
    expect(view.container.textContent).not.toContain("photo_head_cut_off");
  });

  it("keeps the same key after a lost response, a new one after a definite answer; already_queued reads as words", async () => {
    const keys: string[] = [];
    const regenerateIdPhoto = vi
      .fn<(petId: string, key: string) => Promise<unknown>>()
      .mockImplementationOnce(async (_p, key) => { keys.push(key); throw new ApiError({ kind: "network", code: "NETWORK_ERROR", message: "网络连接失败", retryable: true }); })
      .mockImplementationOnce(async (_p, key) => { keys.push(key); return { accepted: true, status: "queued", task_id: "t-1", reason: null }; })
      .mockImplementationOnce(async (_p, key) => { keys.push(key); return { accepted: false, status: "queued", task_id: null, reason: "already_queued" }; });
    const view = render(<IdPhotoAdjust petId="pet-1" idPhoto={READY_GENERATED} canRequest />, { wrapper: wrapper({ platform: { meta: async () => metaWithIdPhoto() }, pets: { regenerateIdPhoto } }) });
    fireEvent.click(await screen.findByRole("button", { name: "重画证件照" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "重画证件照" }));
    await waitFor(() => expect(regenerateIdPhoto).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByRole("button", { name: "重画证件照" }));
    await waitFor(() => expect(regenerateIdPhoto).toHaveBeenCalledTimes(3));
    expect(keys[0]).toBe(keys[1]);
    expect(keys[2]).not.toBe(keys[1]);
    expect(await screen.findByText("新的证件照已经在准备了。")).toBeTruthy();
    expect(view.container.textContent).not.toContain("already_queued");
  });
});
