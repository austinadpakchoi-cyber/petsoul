/**
 * claude-6c2b（巡检分身）· 2026-09-24 巡检后的接待 / 叮嘱 / 证件照修复：
 * - P0：两只宠物时“补充叮嘱”记给当前宠物（切换栏选中的那只），不是入住阶段里记着的那只；入住中仍用正在入住的那只。
 * - P1：输入框和“交代这一句”在贴底区里（不再被贴底按钮压住）；贴底区的按钮组里只有主行动。
 * - P1：“先回去”“完成”“回到接待”看来路：站内有来路就回来路，直接打开时回上级页“我的”；回接待是退一步，不压新的一页。
 * - P1：证件照在服务端不允许时（can_regenerate 为 false）不给按钮，用人话说原因；没有照片的宠物写“还没有 TA 的照片”。
 * - 叫法：那份叮嘱叫“生活叮嘱”，新加一条的动作叫“补充叮嘱”；补充时整理页不再写“入住准备 · 03 / 04”。
 * - “接待员会怎么记你说的话”展开项至少 40px 高（静态读 reception.css：jsdom 不套样式）。
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import type {
  CharacterIdPhoto,
  CharacterState,
  HouseholdBrief,
  IntakeCandidate,
  IntakeConfirmationResult,
  OnboardingState,
  PetPublicProfile,
  ReceptionSession,
  SessionState,
  WebMeta,
} from "@/shared/contracts";
import { ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { AdjustCharacter } from "@/features/home/PetFigure";
import { CareNotesPage } from "@/features/reception/CareNotesPage";
import { ReceptionPage } from "@/features/reception/ReceptionPage";

vi.mock("@/shared/config/env", () => ({ env: { dataMode: "live", isDev: false, apiBase: "/api/v1/web" } }));

beforeEach(() => {
  sessionStorage.clear();
  vi.stubGlobal("scrollTo", vi.fn());
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

/* ---------------- 数据 ---------------- */

const NIANGAO = "pet-niangao";
const DOUBAO = "pet-doubao";
const NAMES: Record<string, string> = { [NIANGAO]: "年糕", [DOUBAO]: "豆包" };

function onboarding(step: OnboardingState["step"], petId: string): OnboardingState {
  return { step, pet_id: petId, home_id: "home-1", reception_session_id: null, reception_skipped: false, home_activated_at: null, pet_origin: "own_pet" };
}

function signedIn(step: OnboardingState["step"], petId: string): SessionState {
  return { authenticated: true, user: { user_id: "owner-1", username: "lin", display_name: null, auth_method: "web_password" }, csrf_required: false, expires_at: null, onboarding: onboarding(step, petId) };
}

const household: HouseholdBrief = {
  household_id: "house-1",
  name: "海边的家",
  home_id: "home-1",
  role: "admin",
  home_activated: true,
  member_count: 1,
  pets: [NIANGAO, DOUBAO].map((pet_id) => ({ pet_id, name: NAMES[pet_id], species: "cat", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-24T00:00:00Z", added_by_you: true })),
} as HouseholdBrief;

const profileOf = (petId: string) => ({ pet_id: petId, display_name: NAMES[petId] ?? "TA", species: "cat", avatar_url: null }) as unknown as PetPublicProfile;

const candidate = {
  candidate_id: "c-1", kind: "habit", subject: "pet", text: "喜欢窗台晒太阳", source_turn_id: "t-2", source_excerpt: "它最喜欢在窗台晒太阳",
  needs_clarification: false, suggested_slot: null, suggested_slot_value: null, state: "unconfirmed",
} as IntakeCandidate;

function receptionSession(petId: string, candidates: IntakeCandidate[] = []): ReceptionSession {
  return {
    session_id: `rs-${petId}`, pet_id: petId, branch: "own_pet", mode: "guided_notes", status: "active",
    host: { host_id: "h", display_name: "星球接待员", role_label: "PetSoul 的 AI 接待角色", avatar_url: null, is_ai: true, disclosure: "我是 AI 接待角色。" },
    turns: [{ turn_id: "t-1", seq: 1, speaker: "host", text: "有什么想交代的吗？", created_at: "2026-09-24T00:00:00Z" }],
    candidates, draft_revision: 1, draft_expires_at: null, data_origin: "live",
  };
}

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

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}</output>;
}

type Entry = string | { pathname: string; search?: string; state?: unknown };

/** 接待页、整理页挂在真实路径上，其余路径是落点探针。entries 的最后一条是打开的那页，前面的是站内来路。 */
function renderFlow(entries: Entry[], services: Record<string, unknown>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={strictServices(services)}>
        <MemoryRouter initialEntries={entries} initialIndex={entries.length - 1}>
          <Routes>
            <Route path="/onboarding/reception" element={<ReceptionPage />} />
            <Route path="/onboarding/notes" element={<CareNotesPage />} />
            <Route path="*" element={<LocationProbe />} />
          </Routes>
        </MemoryRouter>
      </ServicesProvider>
    </QueryClientProvider>,
  );
}

const landedAt = () => screen.queryByTestId("location")?.textContent ?? null;

function receptionServices({ session, candidates = [], households = vi.fn(async () => [household]) }: { session: SessionState; candidates?: IntakeCandidate[]; households?: () => Promise<HouseholdBrief[]> }) {
  const start = vi.fn(async (body: { pet_id: string }, _key: string) => receptionSession(body.pet_id, candidates));
  const get = vi.fn(async (sessionId: string) => receptionSession(sessionId.replace(/^rs-/, ""), candidates));
  const skip = vi.fn(async (sessionId: string) => receptionSession(sessionId.replace(/^rs-/, ""), candidates));
  const publicProfile = vi.fn(async (petId: string) => profileOf(petId));
  const addTurn = vi.fn(async (sessionId: string, _body: { text: string; expected_revision: number }, _key: string) => receptionSession(sessionId.replace(/^rs-/, ""), [candidate]));
  const confirm = vi.fn(async () => ({
    confirmation_id: "cf-1", session_id: "rs-x", draft_revision: 1, persist_state: "persisted", notes: [], grants: [], onboarding: session.onboarding, data_origin: "live",
  }) as unknown as IntakeConfirmationResult);
  return {
    start, get, skip, publicProfile, addTurn, confirm, households,
    services: {
      session: { current: async () => session },
      households: { list: households },
      pets: { publicProfile },
      reception: { start, get, skip, addTurn, confirm },
      world: { home: vi.fn() },
    },
  };
}

const startedFor = (start: { mock: { calls: unknown[][] } }) => start.mock.calls.map((call) => (call[0] as { pet_id: string }).pet_id);

/* ---------------- P0：补充叮嘱记给当前宠物 ---------------- */

describe("补充叮嘱记给当前宠物（切换栏选中的那只），入住中仍用正在入住的那只", () => {
  it("两只宠物、切到豆包后补充：读的是豆包的主页、开的是豆包的接待；入住阶段里记着的年糕一次都没用", async () => {
    sessionStorage.setItem("petsoul:current-pet:owner-1", DOUBAO);
    const api = receptionServices({ session: signedIn("active", NIANGAO) });
    renderFlow(["/onboarding/reception?mode=supplement"], api.services);
    expect(await screen.findByRole("heading", { name: "再聊聊 豆包" })).toBeTruthy();
    await waitFor(() => expect(startedFor(api.start)).toEqual([DOUBAO]));
    expect(api.publicProfile.mock.calls.map((call) => call[0])).toEqual([DOUBAO]);
    // 补充时顶上有切换栏，选中的就是豆包：主人看得到这条叮嘱是给谁的。
    const bar = screen.getByRole("group", { name: "切换当前宠物" });
    expect(within(bar).getByRole("button", { name: /查看 豆包/ }).getAttribute("aria-pressed")).toBe("true");
  });

  it("在接待页顶上切到年糕：改开年糕的接待，而且换一把开场幂等键（不沿用豆包那次的）", async () => {
    sessionStorage.setItem("petsoul:current-pet:owner-1", DOUBAO);
    const api = receptionServices({ session: signedIn("active", NIANGAO) });
    renderFlow(["/onboarding/reception?mode=supplement"], api.services);
    await screen.findByRole("heading", { name: "再聊聊 豆包" });
    fireEvent.click(screen.getByRole("button", { name: /查看 年糕/ }));
    expect(await screen.findByRole("heading", { name: "再聊聊 年糕" })).toBeTruthy();
    await waitFor(() => expect(startedFor(api.start)).toEqual([DOUBAO, NIANGAO]));
    const [first, second] = api.start.mock.calls.map((call) => call[1]);
    expect(first).not.toBe(second);
  });

  it("已入住后没带 ?mode=supplement 进来（入住阶段是 active）也按当前宠物", async () => {
    sessionStorage.setItem("petsoul:current-pet:owner-1", DOUBAO);
    const api = receptionServices({ session: signedIn("active", NIANGAO) });
    renderFlow(["/onboarding/reception"], api.services);
    expect(await screen.findByRole("heading", { name: "再聊聊 豆包" })).toBeTruthy();
    await waitFor(() => expect(startedFor(api.start)).toEqual([DOUBAO]));
  });

  it("入住中（第二只豆包正在入住）：用正在入住的豆包，不读家庭上下文——即使当前宠物是年糕", async () => {
    sessionStorage.setItem("petsoul:current-pet:owner-1", NIANGAO);
    const households = vi.fn(async () => [household]);
    const api = receptionServices({ session: signedIn("reception_optional", DOUBAO), households });
    renderFlow(["/onboarding/reception?branch=own_pet"], api.services);
    expect(await screen.findByRole("heading", { name: "先认识 豆包" })).toBeTruthy();
    await waitFor(() => expect(startedFor(api.start)).toEqual([DOUBAO]));
    expect(households).not.toHaveBeenCalled();
    expect(screen.queryByRole("group", { name: "切换当前宠物" })).toBeNull();
  });
});

/* ---------------- P1：输入框在贴底区里 ---------------- */

describe("输入框和“交代这一句”在贴底区里，按钮组里只有主行动", () => {
  it.each([
    ["入住中", signedIn("reception_optional", DOUBAO), "/onboarding/reception", "接待的下一步", ["先带 豆包 去入住"]],
    ["补充", signedIn("active", NIANGAO), "/onboarding/reception?mode=supplement", "补充叮嘱的下一步", ["先回去"]],
  ] as const)("%s", async (_label, session, entry, groupName, actions) => {
    sessionStorage.setItem("petsoul:current-pet:owner-1", DOUBAO);
    const api = receptionServices({ session });
    renderFlow([entry], api.services);
    const group = await screen.findByRole("group", { name: groupName });
    const send = screen.getByRole("button", { name: "交代这一句" });
    const input = screen.getByLabelText("再交代一件小事");
    const dock = group.closest(".ps-entry-dock");
    expect(dock).not.toBeNull();
    expect(dock!.contains(send)).toBe(true);
    expect(dock!.contains(input)).toBe(true);
    // 正文里不再有输入框（原来它在对话末尾、被贴底区压住）
    expect(document.querySelector(".ps-reception-body textarea")).toBeNull();
    expect(within(group).getAllByRole("button").map((button) => button.textContent)).toEqual([...actions]);
    // 说一句照样能发出去
    fireEvent.change(input, { target: { value: "它喜欢把脸埋进旧毛衣里" } });
    fireEvent.click(send);
    await waitFor(() => expect(api.addTurn).toHaveBeenCalledTimes(1));
    expect(api.addTurn.mock.calls[0][1]).toMatchObject({ text: "它喜欢把脸埋进旧毛衣里" });
  });
});

/* ---------------- P1：出口看来路 ---------------- */

describe("补充叮嘱的出口：站内有来路就回来路，直接打开时回上级页“我的”", () => {
  it("接待页：从通讯器来，“先回去”退回通讯器", async () => {
    const api = receptionServices({ session: signedIn("active", NIANGAO) });
    renderFlow(["/communicator", "/onboarding/reception?mode=supplement"], api.services);
    const group = await screen.findByRole("group", { name: "补充叮嘱的下一步" });
    fireEvent.click(within(group).getByRole("button", { name: "先回去" }));
    await waitFor(() => expect(api.skip).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(landedAt()).toBe("/communicator"));
  });

  it("整理页：从通讯器来 → 整理 → 存好 →“完成”一次退回通讯器（不是退回接待页）", async () => {
    const api = receptionServices({ session: signedIn("active", NIANGAO), candidates: [candidate] });
    renderFlow(["/communicator", "/onboarding/reception?mode=supplement"], api.services);
    const group = await screen.findByRole("group", { name: "补充叮嘱的下一步" });
    fireEvent.click(within(group).getByRole("button", { name: "整理这 1 条叮嘱" }));
    fireEvent.click(await screen.findByRole("radio", { name: "只留在这里" }));
    fireEvent.click(screen.getByRole("button", { name: "这样记就对了" }));
    const done = await screen.findByRole("link", { name: "完成" });
    // 链接地址仍是上级页（修饰键 / 中键新开时去那里）；普通点击退回来路。
    expect(done.getAttribute("href")).toBe("/me");
    fireEvent.click(done);
    await waitFor(() => expect(landedAt()).toBe("/communicator"));
  });

  it("整理页的“回到接待”是退一步：退回原来那一页接待，接待页的“先回去”仍回通讯器", async () => {
    const api = receptionServices({ session: signedIn("active", NIANGAO), candidates: [candidate] });
    renderFlow(["/communicator", "/onboarding/reception?mode=supplement"], api.services);
    fireEvent.click(within(await screen.findByRole("group", { name: "补充叮嘱的下一步" })).getByRole("button", { name: "整理这 1 条叮嘱" }));
    const confirmGroup = await screen.findByRole("group", { name: "确认叮嘱" });
    fireEvent.click(within(confirmGroup).getByRole("button", { name: "回到接待" }));
    const group = await screen.findByRole("group", { name: "补充叮嘱的下一步" });
    fireEvent.click(within(group).getByRole("button", { name: "先回去（以后还能补充）" }));
    await waitFor(() => expect(landedAt()).toBe("/communicator"));
  });

  // 从接待页点“整理”来的整理页带着来路（接待页写进路由状态）；这里直接把那份状态放进历史，只看空便笺时的两个出口。
  const fromReception = { pathname: "/onboarding/notes", search: "?session=rs-pet-niangao", state: { fromReception: true, leaveSteps: 2 } };

  it("整理页（从接待页来）、一句都没说：“先回去”一次退回通讯器", async () => {
    const api = receptionServices({ session: signedIn("active", NIANGAO) });
    renderFlow(["/communicator", "/onboarding/reception?mode=supplement", fromReception], api.services);
    fireEvent.click(await screen.findByRole("button", { name: "先回去" }));
    await waitFor(() => expect(api.skip).toHaveBeenCalledWith("rs-pet-niangao"));
    await waitFor(() => expect(landedAt()).toBe("/communicator"));
  });

  it("整理页（从接待页来）、一句都没说：“回到接待说一件小事”退回原来那页接待，那里的“先回去”回通讯器", async () => {
    const api = receptionServices({ session: signedIn("active", NIANGAO) });
    renderFlow(["/communicator", "/onboarding/reception?mode=supplement", fromReception], api.services);
    const link = await screen.findByRole("link", { name: "回到接待说一件小事" });
    expect(link.getAttribute("href")).toBe("/onboarding/reception?mode=supplement");
    fireEvent.click(link);
    const group = await screen.findByRole("group", { name: "补充叮嘱的下一步" });
    fireEvent.click(within(group).getByRole("button", { name: "先回去" }));
    await waitFor(() => expect(landedAt()).toBe("/communicator"));
  });

  it("整理页直接打开（没有来路）、一句都没说：“先回去”去上级页“我的”", async () => {
    const api = receptionServices({ session: signedIn("active", NIANGAO) });
    renderFlow(["/onboarding/notes?session=rs-pet-niangao"], api.services);
    fireEvent.click(await screen.findByRole("button", { name: "先回去" }));
    await waitFor(() => expect(api.skip).toHaveBeenCalledWith("rs-pet-niangao"));
    await waitFor(() => expect(landedAt()).toBe("/me"));
  });
});

/* ---------------- 叫法：生活叮嘱 / 补充叮嘱 ---------------- */

describe("叫法：那份叮嘱叫“生活叮嘱”，新加一条的动作叫“补充叮嘱”", () => {
  it("补充时的接待页：顶栏“补充叮嘱”，场景标签“PetSoul · 生活叮嘱”，不再有“生活手册”", async () => {
    const api = receptionServices({ session: signedIn("active", NIANGAO) });
    const view = renderFlow(["/onboarding/reception?mode=supplement"], api.services);
    await screen.findByRole("group", { name: "补充叮嘱的下一步" });
    expect(screen.getByText("补充叮嘱")).toBeTruthy();
    expect(view.container.querySelector(".ps-reception-hero__label")?.textContent).toBe("✦ PetSoul · 生活叮嘱");
    expect(view.container.textContent).not.toMatch(/生活手册|入住叮嘱/);
  });

  it("入住中的整理页：顶栏“生活叮嘱”，仍有“入住准备 · 03 / 04”和四站步骤条", async () => {
    const api = receptionServices({ session: signedIn("reception_optional", DOUBAO), candidates: [candidate] });
    const view = renderFlow(["/onboarding/notes?session=rs-pet-doubao"], api.services);
    await screen.findByRole("group", { name: "确认叮嘱" });
    expect(screen.getByText("生活叮嘱")).toBeTruthy();
    expect(screen.getByText("入住准备 · 03 / 04")).toBeTruthy();
    expect(screen.getByRole("img", { name: "入住准备第 3 步，共 4 步" })).toBeTruthy();
    expect(view.container.textContent).not.toContain("入住叮嘱");
  });

  it("补充时的整理页：不再写“入住准备 · 03 / 04”，也没有四站步骤条", async () => {
    const api = receptionServices({ session: signedIn("active", NIANGAO), candidates: [candidate] });
    const view = renderFlow(["/onboarding/notes?session=rs-pet-niangao"], api.services);
    await screen.findByRole("group", { name: "确认叮嘱" });
    expect(screen.getByText("生活叮嘱")).toBeTruthy();
    expect(screen.getByText("再记下几件小事")).toBeTruthy();
    expect(view.container.textContent).not.toMatch(/入住准备|入住叮嘱/);
    expect(screen.queryByRole("img", { name: /入住准备第/ })).toBeNull();
  });
});

/* ---------------- P1：证件照按钮只在服务端允许时出现 ---------------- */

const meta = (): WebMeta => ({
  api_prefix: "/api/v1/web", contract_version: "0.4.5", server_time: "2026-09-24T00:00:00Z", backend_version: "test", data_origin: "live", auth_methods_available: [], applied_migrations: [],
  capabilities: ["character.state", "character.regenerate", "character.id_photo"].map((key) => ({ key, module: "character", status: "available", note: null })),
} as unknown as WebMeta);

function idPhoto(overrides: Partial<CharacterIdPhoto> = {}): CharacterIdPhoto {
  return { status: "absent", source: null, url: null, avatar_url: null, width: null, height: null, content_sha256: null, reference_version: null, revision: null, reason: null, task_id: null, ...overrides };
}

function characterState(overrides: Partial<CharacterState> = {}): CharacterState {
  return { pet_id: "pet-1", status: "absent", active: null, candidate: null, can_regenerate: false, blocked_reason: null, id_photo: idPhoto(), ...overrides };
}

function renderAdjust(state: CharacterState) {
  const regenerateIdPhoto = vi.fn(async () => ({ accepted: true, status: "queued", task_id: "t-1", reason: null }));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>
      <ServicesProvider services={{ platform: { meta: async () => meta() }, pets: { regenerateIdPhoto, regenerateCharacter: vi.fn() } } as unknown as ServiceMap}>
        <MemoryRouter>{children}</MemoryRouter>
      </ServicesProvider>
    </QueryClientProvider>
  );
  const view = render(<AdjustCharacter petId="pet-1" state={state} />, { wrapper });
  return { ...view, regenerateIdPhoto };
}

const idPhotoButton = () => screen.queryByRole("button", { name: /证件照/ });

describe("证件照：服务端不允许时不给按钮，用人话说原因", () => {
  it("图片服务不可用（能力表仍说可用）：没有“生成证件照”，写明证件照服务暂时不可用，也不会发请求", async () => {
    const view = renderAdjust(characterState({ blocked_reason: "provider_unavailable" }));
    expect(await screen.findByTestId("id-photo-blocked")).toBeTruthy();
    expect(screen.getByTestId("id-photo-blocked").textContent).toBe("证件照服务暂时不可用，稍后再看看。");
    expect(idPhotoButton()).toBeNull();
    expect(view.regenerateIdPhoto).not.toHaveBeenCalled();
    expect(view.container.textContent).not.toContain("provider_unavailable");
  });

  it("没有照片的宠物：写“还没有 TA 的照片”，不给死路按钮，也不承诺补传照片的入口", async () => {
    const view = renderAdjust(characterState({ blocked_reason: "no_reference_photo" }));
    expect((await screen.findByTestId("id-photo-blocked")).textContent).toBe("还没有 TA 的照片，暂时没法准备证件照。");
    expect(idPhotoButton()).toBeNull();
    expect(view.container.textContent).not.toMatch(/上传|补传/);
  });

  it("形象正在准备（can_regenerate 因此为 false、没有 blocked_reason）：等形象好了再来，不给按钮", async () => {
    renderAdjust(characterState({ status: "queued", candidate: { status: "queued", pose: "neutral_full", reference_version: 1, style_version: "v1", queued_at: "2026-09-24T00:00:00Z", reason: null, task_id: "t-9" } }));
    expect((await screen.findByTestId("id-photo-blocked")).textContent).toBe("形象正在准备，好了以后再来生成证件照。");
    expect(idPhotoButton()).toBeNull();
  });

  it("已有生成的证件照、服务端不允许：不给“重画证件照”，说明写“重画”", async () => {
    renderAdjust(characterState({ blocked_reason: "provider_unavailable", id_photo: idPhoto({ status: "ready", source: "generated", url: "/api/v1/web/media/id-photos/ip-1", revision: 1 }) }));
    expect((await screen.findByTestId("id-photo-blocked")).textContent).toBe("证件照服务暂时不可用，稍后再看看。");
    expect(screen.queryByRole("button", { name: "重画证件照" })).toBeNull();
  });

  it("不允许又没给原因（上一套形象失败后被挡住）：一句泛化说法，不给按钮", async () => {
    renderAdjust(characterState({ status: "failed", candidate: { status: "failed", pose: "neutral_full", reference_version: 1, style_version: "v1", queued_at: "2026-09-24T00:00:00Z", reason: "rejected", task_id: "t-8" } }));
    expect((await screen.findByTestId("id-photo-blocked")).textContent).toBe("现在还不能生成证件照。");
    expect(idPhotoButton()).toBeNull();
  });

  it("对照：服务端允许（can_regenerate 为 true）时照常给“生成证件照”，没有“不允许”的说明", async () => {
    renderAdjust(characterState({ can_regenerate: true }));
    expect(await screen.findByRole("button", { name: "生成证件照" })).toBeTruthy();
    expect(screen.queryByTestId("id-photo-blocked")).toBeNull();
  });
});

/* ---------------- 点按区域：展开项至少 40px（静态读样式表） ---------------- */

describe("“接待员会怎么记你说的话”展开项的点按区域", () => {
  it("reception.css 里它的 min-height 不小于 40px", () => {
    const css = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), "../src/features/reception/reception.css"), "utf8");
    const block = css.match(/\.ps-host__about summary\s*\{([^}]*)\}/);
    expect(block, "找不到 .ps-host__about summary 的规则").not.toBeNull();
    const minHeight = block![1].match(/min-height:\s*(\d+)px/);
    expect(minHeight, "规则里没有 min-height").not.toBeNull();
    expect(Number(minHeight![1])).toBeGreaterThanOrEqual(40);
  });
});
