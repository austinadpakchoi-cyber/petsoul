/**
 * claude-6c2b（星球分身）· 我的 · TA 的形象（/me/look）· 补一张照片（PUT /pets/{id}/photo，契约 add_pet_photo）。
 * - 入口只在这只宠物一张照片都没有、而且是自己的宠物时出现；已有照片（上传的，或没照片时生成的形象照——它也占着照片位，photo_url 不为空）、
 *   领养来的伙伴、演示模式都不出现。
 * - 选图 → 预览 → 确认才上传；上传中不能再点；成功后刷新，头像换成照片、入口消失、说一句“放好了”；上传后不生成证件照。
 * - 失败说人话：photo_exists / not_own_pet / MEDIA_REJECTED 各一句，其余用统一的玩家说法；换一张图换一把幂等键，同一张重试沿用。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import type { CharacterState, HouseholdBrief, HouseholdPetBrief, PetPrivateSummary, SessionState, WebMeta } from "@/shared/contracts";
import { ApiError, toApiError } from "@/shared/api/errors";
import { buildServices, ServicesProvider } from "@/shared/services/registry";
import { createApiClient } from "@/shared/api/client";
import { loadFeatureModules } from "@/app/modules";
import type { ServiceMap } from "@/shared/services/types";
import { ADD_PHOTO_DONE, ADD_PHOTO_PRIVACY, addPhotoFailureText, canAddPhoto, LookPage } from "@/features/me/LookPage";

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

// jsdom 没有 createObjectURL：预览地址换成固定的假地址（只换这两个静态方法，不动 URL 构造器）
const realCreate = URL.createObjectURL;
const realRevoke = URL.revokeObjectURL;

beforeEach(() => {
  mode.dataMode = "live";
  sessionStorage.clear();
  vi.stubGlobal("scrollTo", vi.fn());
  URL.createObjectURL = vi.fn(() => "blob:preview-1");
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  URL.createObjectURL = realCreate;
  URL.revokeObjectURL = realRevoke;
});

const SIGNED_IN: SessionState = {
  authenticated: true,
  user: { user_id: "owner-1", display_name: "小林", username: "lin", auth_method: "web_password" },
  csrf_required: false,
  expires_at: null,
  onboarding: { step: "active", pet_id: "pet-a", home_id: "home-1", reception_session_id: null, reception_skipped: false, home_activated_at: null, pet_origin: "own_pet" },
};

const PHOTO = "/api/v1/web/media/pets/pet-a/photo";
const petBrief = (over: Partial<HouseholdPetBrief> = {}): HouseholdPetBrief => ({
  pet_id: "pet-a", name: "奶茶", species: "cat", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-20T00:00:00Z", added_by_you: true, ...over,
});
const household = (pet: HouseholdPetBrief): HouseholdBrief => ({ household_id: "house-1", name: "海边的家", home_id: "home-1", role: "admin", home_activated: true, member_count: 1, pets: [pet] });

const META: WebMeta = {
  api_prefix: "/api/v1/web", contract_version: "0.4.5", server_time: "2026-09-24T00:00:00Z", backend_version: "test", data_origin: "live", auth_methods_available: [], applied_migrations: [],
  capabilities: [
    { key: "character.state", module: "character", status: "available", note: null },
    { key: "character.regenerate", module: "character", status: "available", note: null },
    { key: "character.id_photo", module: "character", status: "available", note: null },
  ],
};
/** 没照片：服务端说画不了（no_reference_photo）。 */
const NO_PHOTO: CharacterState = { pet_id: "pet-a", status: "absent", active: null, candidate: null, can_regenerate: false, blocked_reason: "no_reference_photo", id_photo: null };
/** 补上照片以后：可以发起了，还没有证件照。 */
const HAS_PHOTO: CharacterState = { ...NO_PHOTO, can_regenerate: true, blocked_reason: null };

const summary = (over: Partial<PetPrivateSummary> = {}): PetPrivateSummary => ({ pet_id: "pet-a", home_id: "home-1", name: "奶茶", species: "cat", photo_url: PHOTO, origin: "own_pet", owner_title: null, presence: "at_home", photo_generated: false, ...over });

function strictServices(services: Record<string, unknown>): ServiceMap {
  return new Proxy(services as unknown as ServiceMap, {
    get(target, prop: string) {
      if (prop in target) return target[prop as keyof ServiceMap];
      throw new Error(`unexpected service ${prop}`);
    },
  });
}

/** 家庭里的这只宠物按 state.pet 走（上传成功后测试把它换成有照片的）；形象按 state.character 走。 */
function setup(pet: HouseholdPetBrief, addPhoto: (petId: string, photo: File, key: string) => Promise<PetPrivateSummary> = async () => summary()) {
  const state = { pet, character: pet.photo_url ? HAS_PHOTO : NO_PHOTO };
  const spies = {
    list: vi.fn(async () => [household(state.pet)]),
    character: vi.fn(async () => state.character),
    addPhoto: vi.fn(addPhoto),
    regenerateIdPhoto: vi.fn(async () => ({ accepted: true, status: "queued" as const, task_id: "t-2", reason: null })),
    regenerateCharacter: vi.fn(async () => ({ accepted: true, status: "queued" as const, task_id: "t-1", reason: null })),
  };
  const services = strictServices({
    session: { current: async () => SIGNED_IN },
    households: { list: spies.list },
    platform: { meta: async () => META },
    pets: { character: spies.character, addPhoto: spies.addPhoto, regenerateIdPhoto: spies.regenerateIdPhoto, regenerateCharacter: spies.regenerateCharacter },
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter([{ path: "/me/look", element: <LookPage /> }, { path: "/me", element: <p>我的</p> }], { initialEntries: ["/me/look"] });
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={services}>
        <RouterProvider router={router} />
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return { state, spies };
}

const card = () => screen.findByTestId("add-photo");
const picker = (section: HTMLElement) => section.querySelector("input[type=file]") as HTMLInputElement;
const choose = (section: HTMLElement, name = "cat.png") => {
  const file = new File([new Uint8Array([137, 80, 78, 71])], name, { type: "image/png" });
  fireEvent.change(picker(section), { target: { files: [file] } });
  return file;
};
const portraitImage = () => document.querySelector(".ps-look-hero .ps-pet-portrait img")?.getAttribute("src") ?? null;

describe("补一张照片：入口出不出现", () => {
  it("规则：只有 live、自己的宠物、一张照片都没有时才出现", () => {
    expect(canAddPhoto(null, "own_pet")).toBe(true);
    expect(canAddPhoto(PHOTO, "own_pet")).toBe(false);
    expect(canAddPhoto(null, "adopted_original")).toBe(false);
    expect(canAddPhoto(null, "adopted_real_archive")).toBe(false);
    expect(canAddPhoto(null, null)).toBe(false);
    mode.dataMode = "fixture";
    expect(canAddPhoto(null, "own_pet")).toBe(false);
  });

  it("自己的宠物、一张照片都没有：出现入口——先选图，说清照片只有家里人看得到；还没选图时没有上传按钮", async () => {
    setup(petBrief());
    const section = await card();
    expect(within(section).getByRole("heading", { level: 3, name: "补一张 TA 的照片" })).toBeTruthy();
    expect(within(section).getByText(ADD_PHOTO_PRIVACY)).toBeTruthy();
    expect(picker(section).getAttribute("accept")).toBe("image/*");
    expect(within(section).getByText("选一张照片")).toBeTruthy();
    expect(within(section).queryByRole("button", { name: /放上这张照片/ })).toBeNull();
    expect(document.body.textContent).not.toMatch(/photo_exists|MEDIA_REJECTED|接口/);
  });

  it("已经有自己上传的照片：不出现", async () => {
    setup(petBrief({ photo_url: PHOTO }));
    expect(await screen.findByRole("heading", { level: 2, name: "奶茶" })).toBeTruthy();
    await screen.findByTestId("character-adjust");
    expect(screen.queryByTestId("add-photo")).toBeNull();
  });

  it("已有的是没照片时自动生成的形象照（它也占着照片位，photo_url 不为空）：不出现——换掉它是替换，要等用户拍板", async () => {
    setup(petBrief({ photo_url: "/api/v1/web/media/pets/pet-a/photo" }));
    await screen.findByTestId("character-adjust");
    expect(screen.queryByTestId("add-photo")).toBeNull();
  });

  it("领养来的伙伴（原创居民、真实原型）没有照片也不出现：TA 用的是在星球上的样子", async () => {
    setup(petBrief({ origin: "adopted_original" }));
    await screen.findByTestId("character-adjust");
    expect(screen.queryByTestId("add-photo")).toBeNull();
    cleanup();
    setup(petBrief({ origin: "adopted_real_archive" }));
    await screen.findByTestId("character-adjust");
    expect(screen.queryByTestId("add-photo")).toBeNull();
  });
});

describe("补一张照片：上传", () => {
  it("选图后先预览，点“放上这张照片”才上传；上传中不能再点（只发一次）；成功后头像换成照片、入口消失、说一句放好了；不生成证件照", async () => {
    let finish!: (value: PetPrivateSummary) => void;
    const { state, spies } = setup(petBrief(), () => new Promise<PetPrivateSummary>((resolve) => (finish = resolve)));
    const section = await card();
    const file = choose(section);
    expect(within(section).getByRole("img", { name: "准备放上的奶茶的照片" }).getAttribute("src")).toBe("blob:preview-1");
    expect(within(section).getByText("换一张")).toBeTruthy();
    // 选了图只是预览：等一拍（上传是异步发出的），确认真的没有上传，“放上这张照片”可以点
    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(spies.addPhoto).not.toHaveBeenCalled();
    expect((within(section).getByRole("button", { name: /放上这张照片/ }) as HTMLButtonElement).disabled).toBe(false);

    const send = within(section).getByRole("button", { name: /放上这张照片/ });
    fireEvent.click(send);
    await waitFor(() => expect((within(section).getByRole("button", { name: /放上这张照片/ }) as HTMLButtonElement).disabled).toBe(true));
    expect(picker(section).disabled).toBe(true);
    fireEvent.click(within(section).getByRole("button", { name: /放上这张照片/ }));
    expect(spies.addPhoto).toHaveBeenCalledTimes(1);
    expect(spies.addPhoto).toHaveBeenCalledWith("pet-a", file, expect.stringMatching(/\S/));

    const charactersBefore = spies.character.mock.calls.length;
    state.pet = petBrief({ photo_url: PHOTO });
    state.character = HAS_PHOTO;
    finish(summary());
    expect((await screen.findByText(ADD_PHOTO_DONE)).getAttribute("role")).toBe("status");
    await waitFor(() => expect(screen.queryByTestId("add-photo")).toBeNull());
    expect(portraitImage()).toBe(PHOTO);
    // 刷新了家庭与这只的形象；没有替主人生成证件照（按钮照现有规则出现，由主人自己点）
    expect(spies.list.mock.calls.length).toBeGreaterThan(1);
    await waitFor(() => expect(spies.character.mock.calls.length).toBeGreaterThan(charactersBefore));
    expect(spies.regenerateIdPhoto).not.toHaveBeenCalled();
    expect(spies.regenerateCharacter).not.toHaveBeenCalled();
    expect(await screen.findByRole("button", { name: "生成证件照" })).toBeTruthy();
  });
});

describe("补一张照片：失败说人话", () => {
  const conflict = (reason: string, generated = false) =>
    new ApiError({ kind: "http", status: 409, code: "CONFLICT", message: "TA 已经有照片了，现在只能补、不能换。", details: { reason, generated } });

  it("三种原因各一句，其余用统一的玩家说法（不露错误码）", () => {
    expect(addPhotoFailureText(conflict("photo_exists", true))).toBe("TA 已经有照片了。");
    expect(addPhotoFailureText(conflict("not_own_pet"))).toBe("领养来的伙伴用的是 TA 在星球上的样子。");
    expect(addPhotoFailureText(new ApiError({ kind: "http", status: 422, code: "MEDIA_REJECTED", message: "图片无法使用。", details: { reason: "unsupported_type" } }))).toBe("这张图用不了，换一张试试。");
    const other = new ApiError({ kind: "http", status: 500, code: "INTERNAL_ERROR", message: "boom", retryable: true });
    expect(addPhotoFailureText(other)).toBe(other.playerMessage);
  });

  it("图片用不了（MEDIA_REJECTED）：入口留着，说“换一张试试”；换一张图就换一把幂等键；同一张图重试沿用原来那把", async () => {
    const results: Array<() => Promise<PetPrivateSummary>> = [
      async () => { throw new ApiError({ kind: "http", status: 422, code: "MEDIA_REJECTED", message: "图片无法使用。", details: { reason: "unsupported_type" } }); },
      async () => { throw new ApiError({ kind: "network", status: null, code: "NETWORK_ERROR", message: "network" }); },
      () => new Promise<PetPrivateSummary>(() => undefined),
    ];
    const { spies } = setup(petBrief(), () => results.shift()!());
    const section = await card();
    choose(section, "a.heic");
    fireEvent.click(within(section).getByRole("button", { name: /放上这张照片/ }));
    expect((await within(section).findByRole("alert")).textContent).toBe("这张图用不了，换一张试试。");
    expect(screen.getByTestId("add-photo")).toBe(section);

    choose(section, "b.png");
    expect(within(section).queryByRole("alert")).toBeNull();
    fireEvent.click(within(section).getByRole("button", { name: /放上这张照片/ }));
    const alert = await within(section).findByRole("alert");
    expect(alert.textContent).toBe(toApiError(new ApiError({ kind: "network", status: null, code: "NETWORK_ERROR", message: "network" })).playerMessage);
    fireEvent.click(within(section).getByRole("button", { name: /放上这张照片/ }));
    await waitFor(() => expect(spies.addPhoto).toHaveBeenCalledTimes(3));
    const keys = spies.addPhoto.mock.calls.map((call) => call[2]);
    expect(keys[1]).not.toBe(keys[0]);
    expect(keys[2]).toBe(keys[1]);
  });

  it("已经有照片（photo_exists）：说“TA 已经有照片了”，刷新后头像换成那张照片、入口消失", async () => {
    const { state } = setup(petBrief(), async () => {
      state.pet = petBrief({ photo_url: PHOTO });
      throw conflict("photo_exists", true);
    });
    const section = await card();
    choose(section);
    fireEvent.click(within(section).getByRole("button", { name: /放上这张照片/ }));
    await waitFor(() => expect(screen.queryByTestId("add-photo")).toBeNull());
    expect(screen.getByText("TA 已经有照片了。").getAttribute("role")).toBe("status");
    expect(portraitImage()).toBe(PHOTO);
  });

  it("其实是领养来的（not_own_pet）：说“领养来的伙伴用的是 TA 在星球上的样子”，刷新后入口消失", async () => {
    const { state } = setup(petBrief(), async () => {
      state.pet = petBrief({ origin: "adopted_original" });
      throw conflict("not_own_pet");
    });
    const section = await card();
    choose(section);
    fireEvent.click(within(section).getByRole("button", { name: /放上这张照片/ }));
    await waitFor(() => expect(screen.queryByTestId("add-photo")).toBeNull());
    expect(screen.getByText("领养来的伙伴用的是 TA 在星球上的样子。").getAttribute("role")).toBe("status");
  });
});

describe("live 服务（待批的签名 addPhoto(petId, photo, idempotencyKey)）：PUT /pets/{id}/photo，multipart 字段 photo，带幂等键与 CSRF", () => {
  it("请求的方法、路径、表单字段、幂等键与 CSRF 都对；返回宠物摘要", async () => {
    document.cookie = "petsoul_csrf=csrf-1; path=/";
    const sent: Array<{ path: string; method: string; key: string | null; csrf: string | null; body: unknown }> = [];
    const fetchImpl = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const headers = (init?.headers ?? {}) as Record<string, string>;
      sent.push({ path: String(input), method: init?.method ?? "GET", key: headers["Idempotency-Key"] ?? null, csrf: headers["X-CSRF-Token"] ?? null, body: init?.body });
      return new Response(JSON.stringify(summary()), { status: 200, headers: { "Content-Type": "application/json" } });
    }) as typeof fetch;
    const services = buildServices(loadFeatureModules(), { mode: "live", api: createApiClient("/api/v1/web", fetchImpl) });
    const file = new File([new Uint8Array([137, 80, 78, 71])], "a.png", { type: "image/png" });
    const result = await services.pets.addPhoto("pet a/1", file, "key-p");
    expect(sent).toHaveLength(1);
    expect(sent[0]).toMatchObject({ path: "/api/v1/web/pets/pet%20a%2F1/photo", method: "PUT", key: "key-p", csrf: "csrf-1" });
    expect(sent[0].body).toBeInstanceOf(FormData);
    const sentFile = (sent[0].body as FormData).get("photo") as File;
    expect([sentFile.name, sentFile.size, sentFile.type]).toEqual(["a.png", 4, "image/png"]);
    expect([...(sent[0].body as FormData).keys()]).toEqual(["photo"]);
    expect(result.photo_url).toBe(PHOTO);
    document.cookie = "petsoul_csrf=; max-age=0; path=/";
  });

  it("演示模式：不上传照片（不发请求，说明演示不上传）", async () => {
    const fetchImpl = vi.fn() as unknown as typeof fetch;
    const services = buildServices(loadFeatureModules(), { mode: "fixture", api: createApiClient("/api/v1/web", fetchImpl) });
    await expect(services.pets.addPhoto("pet-a", new File([], "a.png"), "k")).rejects.toMatchObject({ code: "CAPABILITY_UNAVAILABLE" });
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});
