/**
 * claude-6c2b（分身）· 我的 · TA 的形象（/me/look）。
 * - 入口：“我的”页第二组第一个是“TA 的形象”，指向 /me/look；经真实路由表点进去就是这页，左上角回 /me。
 * - 能力开关关着（能力表说形象没开）：不请求形象，页面上没有任何按钮（没有“调整形象”，也没有证件照一节），只说暂时看不了。
 * - 形象开着、调整与证件照没开：说明与原因照常，但没有按钮，也没有证件照一节；说明句不提“生成证件照”。
 * - live 有形象：头像是 PetPortrait（用照片）；站姿图按中性站姿的身体高度落位；“调整形象”与证件照两节都在，
 *   说明句提到“生成证件照”；点“生成证件照”按这只宠物发出（服务是假的，不触发真实生图）。
 * - 读形象失败：统一错误态可重试（不当成“没有形象”，也不放按钮）；重试成功后两节出现。
 * - 演示模式：温和说明，不编数据、不放按钮，不请求形象与能力表。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import type { CharacterAsset, CharacterState, HouseholdBrief, SessionState, WebMeta } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { createApiClient } from "@/shared/api/client";
import { loadFeatureModules } from "@/app/modules";
import { buildRoutes } from "@/app/router";
import { buildServices, ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { LOOK_INTRO, LOOK_INTRO_NO_PHOTO, LOOK_INTRO_WITH_ID_PHOTO, LookPage } from "@/features/me/LookPage";

const mode = vi.hoisted(() => ({ dataMode: "live" as "fixture" | "live" }));
vi.mock("@/shared/config/env", () => ({
  env: {
    get dataMode() {
      return mode.dataMode;
    },
    isDev: false,
    apiBase: "/api/v1/web",
  },
}));

beforeEach(() => {
  mode.dataMode = "live";
  sessionStorage.clear();
  vi.stubGlobal("scrollTo", vi.fn());
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/* ---------------- 测试数据 ---------------- */

const SIGNED_IN: SessionState = {
  authenticated: true,
  user: { user_id: "owner-1", display_name: "小林", username: "lin", auth_method: "web_password" },
  csrf_required: false,
  expires_at: null,
  onboarding: { step: "active", pet_id: "pet-a", home_id: "home-1", reception_session_id: null, reception_skipped: false, home_activated_at: null, pet_origin: "own_pet" },
};

const PHOTO = "/api/v1/web/media/pets/pet-a/photo";
const HOUSEHOLD: HouseholdBrief = {
  household_id: "house-1",
  name: "海边的家",
  home_id: "home-1",
  role: "admin",
  home_activated: true,
  member_count: 1,
  pets: [{ pet_id: "pet-a", name: "奶茶", species: "cat", photo_url: PHOTO, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-20T00:00:00Z", added_by_you: true }],
};

type CapStatus = "available" | "not_implemented";
const meta = (caps: { state: CapStatus; regenerate: CapStatus; idPhoto: CapStatus }): WebMeta => ({
  api_prefix: "/api/v1/web",
  contract_version: "0.4.5",
  server_time: "2026-09-24T00:00:00Z",
  backend_version: "test",
  data_origin: "live",
  auth_methods_available: [],
  applied_migrations: [],
  capabilities: [
    { key: "character.state", module: "character", status: caps.state, note: null },
    { key: "character.regenerate", module: "character", status: caps.regenerate, note: null },
    { key: "character.id_photo", module: "character", status: caps.idPhoto, note: null },
  ],
});
const ALL_ON = meta({ state: "available", regenerate: "available", idPhoto: "available" });
const ALL_OFF = meta({ state: "not_implemented", regenerate: "not_implemented", idPhoto: "not_implemented" });

const asset = (): CharacterAsset => ({
  asset_id: "ca-1",
  pose: "neutral_full",
  url: "/api/v1/web/media/characters/ca-1",
  content_sha256: "a".repeat(64),
  content_type: "image/png",
  width: 800,
  height: 1000,
  content_box: { left: 200, top: 200, right: 600, bottom: 960 },
  anchor: { x: 0.5, y: 0.96, measured: true },
  opaque_ratio: 0.31,
  has_alpha: true,
});

/** 有生效形象、可以调整、还没有证件照（老伙伴的样子）。 */
const WITH_CHARACTER: CharacterState = {
  pet_id: "pet-a",
  status: "ready",
  active: { character_set_id: "cs-1", pet_id: "pet-a", revision: 3, reference_version: 1, style_version: "v1", assets: [asset()], published_at: "2026-09-23T12:00:00Z" },
  candidate: null,
  can_regenerate: true,
  blocked_reason: null,
  id_photo: null,
};

/* ---------------- 渲染 ---------------- */

/** 只放页面该用的服务；读到没给的服务就算失败（证明页面没偷偷请求别的）。 */
function strictServices(services: Record<string, unknown>): ServiceMap {
  return new Proxy(services as unknown as ServiceMap, {
    get(target, prop: string) {
      if (prop in target) return target[prop as keyof ServiceMap];
      throw new Error(`unexpected service ${prop}`);
    },
  });
}

function renderLook(services: ServiceMap) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [
      { path: "/me/look", element: <LookPage /> },
      { path: "/me", element: <p>这里是我的页</p> },
    ],
    { initialEntries: ["/me/look"] },
  );
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={services}>
        <RouterProvider router={router} />
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return router;
}

/** live：会话与家庭照常；能力表与形象按用例给；两个写命令只记下调用。 */
function liveWith(metaView: WebMeta, character: (petId: string, signal?: AbortSignal) => Promise<CharacterState>) {
  const spies = {
    meta: vi.fn(async () => metaView),
    character: vi.fn(character),
    regenerateCharacter: vi.fn(async () => ({ accepted: true, status: "queued" as const, task_id: "t-1", reason: null })),
    regenerateIdPhoto: vi.fn(async () => ({ accepted: true, status: "queued" as const, task_id: "t-2", reason: null })),
  };
  const services = strictServices({
    session: { current: async () => SIGNED_IN },
    households: { list: async () => [HOUSEHOLD] },
    platform: { meta: spies.meta },
    pets: { character: spies.character, regenerateCharacter: spies.regenerateCharacter, regenerateIdPhoto: spies.regenerateIdPhoto },
  });
  return { spies, services };
}

function renderApp(path: string) {
  mode.dataMode = "fixture";
  const modules = loadFeatureModules();
  const services = buildServices(modules, { mode: "fixture", api: createApiClient("/api/v1/web") });
  const router = createMemoryRouter(buildRoutes(modules), { initialEntries: [path] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={services}>
        <RouterProvider router={router} />
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return router;
}

const heading = () => screen.findByRole("heading", { level: 1, name: "TA 的形象" });
const portraitImage = () => document.querySelector(".ps-look-hero .ps-pet-portrait img")?.getAttribute("src") ?? null;
/** 那一句说明（按钮名包在不换行的小段里，按整段文字比）。 */
const intro = () => document.querySelector(".ps-look-intro")?.textContent ?? null;

/* ---------------- 入口 ---------------- */

describe("TA 的形象：入口", () => {
  it("“我的”页第二组第一个是“TA 的形象”，指向 /me/look；点进去就是这页，左上角回 /me（演示模式经真实路由表）", async () => {
    const router = renderApp("/me");
    const entry = await screen.findByRole("link", { name: /^TA 的形象/ });
    expect(entry.getAttribute("href")).toBe("/me/look");
    expect(entry.textContent).toContain("星球上的样子和证件照");
    // 第二组的读屏名名副其实：“形象与账号”（里面不只有账号）。
    const group = screen.getByRole("list", { name: "形象与账号" });
    expect(entry.closest("ul")).toBe(group);
    expect(within(group).getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual(["/me/look", "/me/reports", "/settings"]);
    expect(screen.queryByRole("list", { name: "账号" })).toBeNull();

    fireEvent.click(entry);
    expect(await heading()).toBeTruthy();
    expect(router.state.location.pathname).toBe("/me/look");
    expect(screen.getByRole("link", { name: "返回我的" }).getAttribute("href")).toBe("/me");
    // 演示模式：温和说明，不编数据、不放按钮。
    expect(await screen.findByText("演示模式没有 TA 的星球形象")).toBeTruthy();
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.queryByTestId("character-adjust")).toBeNull();
    expect(document.body.textContent).not.toMatch(/接口|模型|fixture|character\.|not_implemented/);
  });
});

/* ---------------- 能力开关 ---------------- */

describe("TA 的形象：能力开关", () => {
  it("能力表说形象没开：不请求形象，没有任何按钮、没有证件照一节，只说暂时看不了", async () => {
    const { spies, services } = liveWith(ALL_OFF, async () => WITH_CHARACTER);
    renderLook(services);
    expect(await heading()).toBeTruthy();
    expect(await screen.findByText("TA 的星球形象暂时看不了")).toBeTruthy();
    expect(spies.meta).toHaveBeenCalled();
    expect(spies.character).not.toHaveBeenCalled();
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.queryByTestId("character-adjust")).toBeNull();
    expect(screen.queryByTestId("id-photo-adjust")).toBeNull();
    // 头像照常是 TA 自己的照片；不露能力名与原始状态。
    expect(portraitImage()).toBe(PHOTO);
    expect(document.body.textContent).not.toMatch(/character\.|not_implemented|接口|模型/);
  });

  it("形象开着、调整与证件照没开：说明照常，但没有“调整形象”“生成证件照”，也没有证件照一节；说明句不提生成证件照", async () => {
    const { spies, services } = liveWith(meta({ state: "available", regenerate: "not_implemented", idPhoto: "not_implemented" }), async () => WITH_CHARACTER);
    renderLook(services);
    expect(await screen.findByTestId("character-adjust")).toBeTruthy();
    expect(spies.character).toHaveBeenCalledWith("pet-a", expect.anything());
    expect(intro()).toBe(LOOK_INTRO);
    expect(intro()).not.toContain("生成证件照");
    expect(screen.queryByRole("button", { name: "调整形象" })).toBeNull();
    expect(screen.queryByRole("button", { name: /证件照/ })).toBeNull();
    expect(screen.queryByTestId("id-photo-adjust")).toBeNull();
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });
});

/* ---------------- 有形象 ---------------- */

describe("TA 的形象：live 有形象", () => {
  it("头像用照片；站姿图按身体高度落位；“调整形象”与证件照两节都在，说明句提到“生成证件照”；点“生成证件照”按这只宠物发出", async () => {
    const { spies, services } = liveWith(ALL_ON, async () => WITH_CHARACTER);
    renderLook(services);
    const adjust = await screen.findByTestId("character-adjust");
    const idPhoto = within(adjust).getByTestId("id-photo-adjust");
    expect(screen.getByRole("heading", { level: 2, name: "奶茶" })).toBeTruthy();
    expect(portraitImage()).toBe(PHOTO);
    expect(screen.getByText("星球上的 TA 就是下面这个样子")).toBeTruthy();

    const figure = screen.getByRole("img", { name: "奶茶的星球形象" }) as HTMLImageElement;
    expect(figure.getAttribute("src")).toBe("/api/v1/web/media/characters/ca-1");
    // 主体高 760 / 画布 1000 → 图片高度是舞台的 1000/760；落地点（0.5, 0.96）对准底边中点。
    expect(figure.style.height).toBe("131.58%");
    expect(figure.style.transform).toBe("translate(-50%, 4%)");

    expect(intro()).toBe(LOOK_INTRO_WITH_ID_PHOTO);
    expect(document.querySelector(".ps-look-intro .ps-look-keep")?.textContent).toBe("“生成证件照”");
    expect(within(adjust).getByRole("button", { name: "调整形象" })).toBeTruthy();
    const generate = within(idPhoto).getByRole("button", { name: "生成证件照" });
    expect(within(idPhoto).getByText("还没有证件照：护照、居民证、驾照都会用它。")).toBeTruthy();

    fireEvent.click(generate);
    expect(await screen.findByText("证件照已经在准备了。")).toBeTruthy();
    expect(spies.regenerateIdPhoto).toHaveBeenCalledWith("pet-a", expect.any(String));
    expect(spies.regenerateCharacter).not.toHaveBeenCalled();
  });

  it("还没有形象（没挡住）：不放站姿图，头像旁写“星球上暂时用 TA 的照片”，入口按用途写“为 TA 准备形象”", async () => {
    const { services } = liveWith(ALL_ON, async () => ({ ...WITH_CHARACTER, status: "absent", active: null }));
    renderLook(services);
    const adjust = await screen.findByTestId("character-adjust");
    expect(screen.queryByRole("img", { name: "奶茶的星球形象" })).toBeNull();
    expect(screen.getByText("星球上暂时用 TA 的照片")).toBeTruthy();
    expect(within(adjust).getByRole("button", { name: "为 TA 准备形象" })).toBeTruthy();
    expect(within(adjust).getByRole("button", { name: "生成证件照" })).toBeTruthy();
  });
});

/* ---------------- 读的状态 ---------------- */

describe("TA 的形象：还在读、读失败", () => {
  it("还在读：只有等待，没有按钮；读失败：统一错误态可重试，不当成“没有形象”；重试成功后两节出现", async () => {
    let fail!: (error: unknown) => void;
    let calls = 0;
    const { spies, services } = liveWith(ALL_ON, () => {
      calls += 1;
      if (calls === 1) return new Promise<CharacterState>((_, reject) => (fail = reject));
      return Promise.resolve(WITH_CHARACTER);
    });
    renderLook(services);
    expect(await heading()).toBeTruthy();
    await waitFor(() => expect(spies.character).toHaveBeenCalledTimes(1));
    expect(document.querySelector("[aria-busy='true']")).toBeTruthy();
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.queryByTestId("character-adjust")).toBeNull();

    fail(new ApiError({ kind: "http", status: 500, code: "INTERNAL_ERROR", message: "服务暂时有点忙，请稍后再试。", retryable: true }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("服务暂时有点忙");
    expect(screen.queryByText("还没有星球形象")).toBeNull();
    expect(screen.queryByTestId("character-adjust")).toBeNull();

    fireEvent.click(within(alert).getByRole("button", { name: "重试" }));
    expect(await screen.findByTestId("character-adjust")).toBeTruthy();
    expect(screen.getByTestId("id-photo-adjust")).toBeTruthy();
    expect(spies.character).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

/* ---------------- 没有照片（2026-09-24 巡检 P1：页面上没有的按钮不许诺） ---------------- */

describe("TA 的形象：没有照片的伙伴", () => {
  /** 服务端对没有照片的宠物：不能发起（can_regenerate false），原因 no_reference_photo；证件照也没有。 */
  const NO_PHOTO: CharacterState = { pet_id: "pet-a", status: "absent", active: null, candidate: null, can_regenerate: false, blocked_reason: "no_reference_photo", id_photo: null };

  it("说明句讲照片是形象和证件照的来源；“画不了”由形象、证件照两节各说一次（不说第三遍）；不提“生成证件照”，页面上也确实没有任何按钮", async () => {
    // 这只宠物本来就没有照片（家庭简介里 photo_url 为空），服务端才会说 no_reference_photo
    const noPhotoHousehold: HouseholdBrief = { ...HOUSEHOLD, pets: HOUSEHOLD.pets.map((p) => ({ ...p, photo_url: null })) };
    const services = strictServices({
      session: { current: async () => SIGNED_IN },
      households: { list: async () => [noPhotoHousehold] },
      platform: { meta: async () => ALL_ON },
      pets: { character: async () => NO_PHOTO, regenerateCharacter: vi.fn(), regenerateIdPhoto: vi.fn() },
    });
    renderLook(services);
    const adjust = await screen.findByTestId("character-adjust");
    expect(intro()).toBe(LOOK_INTRO_NO_PHOTO);
    expect(intro()).toContain("照着 TA 的照片");
    expect(intro()).not.toMatch(/生成证件照|点|上传|补一张/);
    expect(document.body.textContent).not.toContain("“生成证件照”");
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    // 画不了：形象一节、证件照一节各说一次
    expect(within(adjust).getByText("还没有 TA 的照片，暂时没法准备形象。")).toBeTruthy();
    expect(screen.getByTestId("id-photo-blocked").textContent).toBe("还没有 TA 的照片，暂时没法准备证件照。");
    expect(document.body.textContent!.split("还没有 TA 的照片").length - 1).toBe(2);
  });

  it("能力开着但服务端这会儿不让发起（不是没照片）：说明句不提“生成证件照”，因为页面上没有这个按钮", async () => {
    const busy: CharacterState = { ...WITH_CHARACTER, can_regenerate: false, blocked_reason: "provider_unavailable" };
    const { services } = liveWith(ALL_ON, async () => busy);
    renderLook(services);
    await screen.findByTestId("character-adjust");
    expect(intro()).toBe(LOOK_INTRO);
    expect(screen.queryByRole("button", { name: /证件照/ })).toBeNull();
  });
});
