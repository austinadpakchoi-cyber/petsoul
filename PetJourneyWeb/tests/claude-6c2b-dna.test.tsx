/**
 * claude-6c2b（分身）· 我的 · TA 的档案（/me/dna）。
 * - 草稿提示只在 confirmed=false 时出现，说法按草稿的真实来源写；确认过的不提示。
 * - 行为倾向只读：每条附原话出处（“出自{栏目}：「原话」”）；说不准的原话列在“还没想明白的”，不强行归类；不露倍数与规则编号。
 * - 保存带的是进入编辑时读到的版本号；成功后回到只读并提示“已保存，TA 从现在起按这份来”，返回值直接写回缓存。
 * - 409 dna_version_conflict：提示“家人刚改过，先看看最新的再改”，不当成已保存（不写缓存、不回只读、改动还在）；
 *   “看看最新的”先确认再丢掉改动，确认后才重新读取。编辑中后台已读到家人的新版本：先提示，保存不再发出去。
 * - 从没保存过的草稿第一次保存带 expected_version=0（“读到的是还没保存过的”），服务端已有一份时回 409，照旧按冲突处理；
 *   保存过以后带读到的版本号。首存前先重读只是提前发现：家人已经确认过一份就不发。
 * - 进页面总会重新读一次，读完之前“改一改”先等一等。
 * - 有改动时取消、离开本页都先确认。标签：回车添上（输入法组字的回车不算）、去掉、没点“添上”的也一起保存、满了收起输入框。
 * - 称呼与小暗号按 personal_fields 标“只属于你”，小暗号按 private_fields 标“只在私信里用”。
 * - 演示模式（fixture，能力未接入）：温和说明“演示模式没有 TA 的档案”，不崩、不编数据、没有“改一改”。
 * - “我的”页有“TA 的档案”入口指向 /me/dna；头像一律是 PetPortrait，不写名字首字。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import type { BehaviorEvidence, HouseholdBrief, PetBehavior, PetDNA, PetDNAView, SessionState } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { createApiClient } from "@/shared/api/client";
import { loadFeatureModules } from "@/app/modules";
import { buildRoutes } from "@/app/router";
import { createQueryClient, queryKeys } from "@/shared/query/queryClient";
import { buildServices, ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { fixtureHomeSnapshot } from "@/fixtures/home";
import { DnaPage } from "@/features/me/DnaPage";
import { bodyFrom, draftNote, formFrom, formProblems, isVersionConflict, withPending } from "@/features/me/dnaModel";

// 同一个文件里要切 fixture / live：env 用 getter 读一个可改的开关（页面在渲染时才读 env.dataMode）。
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
  // 全屏页的布局里有滚动恢复、保存后回到顶部；jsdom 没有 scrollTo。
  vi.stubGlobal("scrollTo", vi.fn());
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/* ---------------- 测试数据 ---------------- */

const FIXTURE_PET = fixtureHomeSnapshot().pet;
const KEY = queryKeys.dnaFor("owner-1", "pet-a");

const EMPTY_DNA: PetDNA = {
  owner_title: null,
  nicknames: [],
  personality: null,
  voice_style: null,
  catchphrase: null,
  favorite_foods: [],
  favorite_places: [],
  hobbies: [],
  habits: [],
  fears: [],
  shared_memories: [],
};
const dnaOf = (over: Partial<PetDNA> = {}): PetDNA => ({ ...EMPTY_DNA, ...over });

const ev = (field: string, fieldLabel: string, phrase: string, polarity: BehaviorEvidence["polarity"], note: string | null = null, implied = false): BehaviorEvidence => ({
  field,
  field_label: fieldLabel,
  phrase,
  polarity,
  note,
  implied,
});

const BEHAVIOR: PetBehavior = {
  rules_version: "dna-behavior-2026.2",
  rhythm: "regular",
  sleep_start: "23:30",
  wake: "07:30",
  sociability: "homebody",
  curious: false,
  outings_per_day: 1,
  chattiness: 1,
  learn_rate: 1,
  summary: ["不爱熬夜：按平常作息（23:30 睡，07:30 起）", "恋家：少出门、话少"],
  traits: [
    { key: "night_owl", label: "爱熬夜", status: "negated", evidence: [ev("personality", "性格", "不爱熬夜", "negative", "“不”否定了这个说法")] },
    {
      key: "homebody",
      label: "恋家安静",
      status: "applied",
      evidence: [
        ev("personality", "性格", "喜欢安静", "positive"),
        ev("personality", "性格", "不爱热闹", "positive", "由“不爱热闹”反推（单独不足以归类）", true),
        ev("personality", "性格", "喜欢安静", "positive"),
      ],
    },
    { key: "sleepy", label: "爱睡觉", status: "uncertain", evidence: [ev("habits", "小习惯", "有时候睡一整天", "uncertain", "“有时候”：说法不确定，暂不归类")] },
  ],
  preferences: [
    { key: "route:long", label: "出远门", weight: 0.3, evidence: [], notes: ["恋家：不太想出远门"] },
    { key: "route:local:city_trip", label: "进城逛逛", weight: 1, evidence: [ev("personality", "性格", "不爱热闹", "negative", "“不”否定了这个说法")], notes: [] },
    { key: "job:bookstore", label: "在书店理书", weight: 2.25, evidence: [ev("hobbies", "爱好", "看书", "positive")], notes: [] },
  ],
  unclassified: ["有时候睡一整天"],
  sources: ["personality", "habits", "hobbies"],
};

const SAVED_DNA = dnaOf({
  owner_title: "姐姐",
  nicknames: ["岚岚"],
  personality: "不爱熬夜，不爱热闹，喜欢安静。",
  hobbies: ["看书"],
  fears: ["打雷"],
  shared_memories: ["一喊开饭就冲过来"],
});

const viewOf = (over: Partial<PetDNAView> = {}): PetDNAView => ({
  pet_id: "pet-a",
  dna: SAVED_DNA,
  confirmed: true,
  draft_sources: [],
  updated_at: "2026-09-23T08:00:00Z",
  private_fields: ["shared_memories"],
  behavior: BEHAVIOR,
  version: 3,
  personal_fields: ["owner_title", "shared_memories"],
  updated_by_you: true,
  ...over,
});

const draftOf = (over: Partial<PetDNAView> = {}): PetDNAView =>
  viewOf({ confirmed: false, version: null, draft_sources: ["reception_notes"], updated_at: null, updated_by_you: null, dna: dnaOf({ owner_title: "姐姐", habits: ["每天早上蹭蹭手"] }), ...over });

const householdPet = (photoUrl: string | null = null): HouseholdBrief["pets"][number] => ({
  pet_id: "pet-a",
  name: "奶茶",
  species: "cat",
  photo_url: photoUrl,
  origin: "own_pet",
  presence: "at_home",
  join_step: "moved_in",
  joined_at: "2026-09-20T00:00:00Z",
  added_by_you: true,
});

const household = (photoUrl: string | null = null): HouseholdBrief => ({
  household_id: "house-1",
  name: "海边的家",
  home_id: "home-1",
  role: "admin",
  home_activated: true,
  member_count: 2,
  pets: [householdPet(photoUrl)],
});

const SIGNED_IN: SessionState = {
  authenticated: true,
  user: { user_id: "owner-1", display_name: "小林", username: "lin", auth_method: "web_password" },
  csrf_required: false,
  expires_at: null,
  onboarding: { step: "active", pet_id: "pet-a", home_id: "home-1", reception_session_id: null, reception_skipped: false, home_activated_at: null, pet_origin: "own_pet" },
};

const conflictError = () =>
  new ApiError({ kind: "http", status: 409, code: "CONFLICT", message: "家人刚改过 TA 的 DNA，先看看最新的再改。", details: { reason: "dna_version_conflict", current_version: 4 } });

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

type DnaCall = [petId: string, signal?: AbortSignal];
type SaveCall = [petId: string, body: PetDNA, expectedVersion: number | null];

/** live：会话与家庭照常，pets 只有 dna / saveDna；dna 每次都读 current（测试中途可以换成“家人改过的新一份”）。 */
function liveDna(first: PetDNAView, save: (...args: SaveCall) => Promise<PetDNAView>, photoUrl: string | null = null) {
  const state = { current: first };
  const dna = vi.fn(async (..._args: DnaCall) => state.current);
  const saveDna = vi.fn(save);
  const services = {
    session: { current: async () => SIGNED_IN },
    households: { list: async () => [household(photoUrl)] },
    pets: { dna, saveDna },
  };
  return { state, dna, saveDna, services };
}

/**
 * 经数据路由渲染（页面用 useBlocker 拦离开，需要数据路由）；/me 只放一个占位。prime：进页面前缓存里已有的一份。
 * 用应用自己的 createQueryClient（15 秒内算新鲜等默认值与线上一致）；测试里裸 new 的 QueryClient 默认 staleTime 是 0，测不出“进页面要重读”。
 */
function renderDna(services: Record<string, unknown>, prime?: PetDNAView) {
  const client = createQueryClient();
  if (prime) client.setQueryData(KEY, prime);
  const router = createMemoryRouter(
    [
      { path: "/me/dna", element: <DnaPage /> },
      { path: "/me", element: <p>这里是我的页</p> },
    ],
    { initialEntries: ["/me/dna"] },
  );
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={strictServices(services)}>
        <RouterProvider router={router} />
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return { client, router };
}

/** fixture：真实路由表 + 真实演示服务。 */
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

const loaded = () => screen.findByRole("heading", { level: 3, name: "TA 的性子" });
const fieldRow = (key: string) => document.querySelector(`[data-field="${key}"]`) as HTMLElement;
const editForm = () => screen.queryByRole("form", { name: "改一改 TA 的档案" });
const INTERNAL_WORDS = /接口|模型|fixture|版本号|DNA|接入|能力|服务端|version|rules/;

async function startEditing() {
  fireEvent.click(await screen.findByRole("button", { name: "改一改" }));
  expect(editForm()).toBeTruthy();
}

/** 宠物头像一律是 TA 自己的样子：有图就是图，没图是爪印；任何情况下都不写名字首字。 */
function portraitOf(name: string): { image: string | null; paw: boolean; text: string } {
  const portrait = screen.getByRole("img", { name });
  return { image: portrait.querySelector("img")?.getAttribute("src") ?? null, paw: Boolean(portrait.querySelector("svg")), text: portrait.textContent ?? "" };
}

/* ---------------- 纯函数 ---------------- */

describe("档案的纯数据部分", () => {
  it("草稿提示按真实来源写：入住时说的话 / 领养时的介绍 / TA 的简介；什么来源都没有就请主人写", () => {
    expect(draftNote(["reception_notes"])).toBe("这是按你入住时说的话整理的，看看对不对，确认后 TA 就按这份来。");
    expect(draftNote(["adoption_profile", "reception_notes"])).toBe("这是按领养时的介绍和你入住时说的话整理的，看看对不对，确认后 TA 就按这份来。");
    expect(draftNote(["owner_bio"])).toBe("这是按 TA 的简介整理的，看看对不对，确认后 TA 就按这份来。");
    expect(draftNote([])).toBe("还没写过 TA 的档案。写下 TA 的样子，确认后 TA 就按这份来。");
    expect(draftNote(["something_new"])).toBe(draftNote([]));
  });

  it("请求体：每一栏都带上；空字符串写成 null；列表去空白、去重；没点“添上”的那条算进去（不重复、不超条数）", () => {
    const form = formFrom(dnaOf({ owner_title: "  姐姐 ", nicknames: ["岚岚", " 岚岚 ", "  "], personality: "   " }));
    const body = bodyFrom(form);
    expect(Object.keys(body).sort()).toEqual(Object.keys(EMPTY_DNA).sort());
    expect(body.owner_title).toBe("姐姐");
    expect(body.personality).toBeNull();
    expect(body.nicknames).toEqual(["岚岚"]);
    const merged = withPending(form, { nicknames: "团  子", fears: " ", hobbies: "看书" });
    expect(bodyFrom(merged).nicknames).toEqual(["岚岚", "团 子"]);
    expect(bodyFrom(merged).hobbies).toEqual(["看书"]);
    const full = formFrom(dnaOf({ fears: ["一", "二", "三", "四", "五", "六"] }));
    expect(withPending(full, { fears: "七" }).fears).toHaveLength(6);
  });

  it("保存前检查按字符数（和后端一样，一个表情算一个字）", () => {
    expect(formProblems(formFrom(dnaOf({ owner_title: "🐱".repeat(12) })))).toEqual([]);
    expect(formProblems(formFrom(dnaOf({ owner_title: "姐".repeat(13) })))[0]).toContain("最多写 12 个字");
    expect(formProblems(formFrom(dnaOf({ nicknames: ["一", "二", "三", "四", "五", "六"] })))[0]).toContain("最多 5 条");
  });

  it("冲突只认 details.reason = dna_version_conflict", () => {
    expect(isVersionConflict(conflictError())).toBe(true);
    expect(isVersionConflict(new ApiError({ kind: "http", status: 409, code: "CONFLICT", message: "别的冲突", details: { reason: "pet_asleep" } }))).toBe(false);
    expect(isVersionConflict(new Error("boom"))).toBe(false);
  });
});

/* ---------------- 读 ---------------- */

describe("TA 的档案 · 读", () => {
  it("草稿（confirmed=false）：出现“待你确认”和按来源写的一句提示；有内容时可以“就按这份”", async () => {
    const { services } = liveDna(draftOf(), async () => viewOf());
    renderDna(services);
    await loaded();
    expect(screen.getByText("这是按你入住时说的话整理的，看看对不对，确认后 TA 就按这份来。")).toBeTruthy();
    expect(screen.getByText("待你确认")).toBeTruthy();
    expect(screen.getByRole("button", { name: "就按这份" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "改一改" })).toBeTruthy();
    expect(screen.getByRole("heading", { level: 1, name: "TA 的档案" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "返回我的" }).getAttribute("href")).toBe("/me");
  });

  it("草稿什么都没写：只请主人写，不放“就按这份”（没有可确认的内容）", async () => {
    const { services } = liveDna(draftOf({ draft_sources: [], dna: EMPTY_DNA }), async () => viewOf());
    renderDna(services);
    await loaded();
    expect(screen.getByText("还没写过 TA 的档案。写下 TA 的样子，确认后 TA 就按这份来。")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "就按这份" })).toBeNull();
    expect(screen.getByRole("button", { name: "改一改" })).toBeTruthy();
  });

  it("确认过的：没有草稿提示与“待你确认”；头像是 TA 的照片，不写首字", async () => {
    const { services } = liveDna(viewOf(), async () => viewOf(), "/media/pets/pet-a.jpg");
    renderDna(services);
    await loaded();
    expect(screen.queryByText("待你确认")).toBeNull();
    expect(screen.queryByText(/看看对不对/)).toBeNull();
    expect(screen.queryByRole("button", { name: "就按这份" })).toBeNull();
    expect(screen.getByText("TA 正按这份来")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 2, name: "奶茶" })).toBeTruthy();
    expect(portraitOf("奶茶")).toEqual({ image: "/media/pets/pet-a.jpg", paw: false, text: "" });
  });

  it("共用那部分最后是家人改的：说一句“家人最近改过这份”；live 没照片是爪印，不写首字", async () => {
    const { services } = liveDna(viewOf({ updated_by_you: false }), async () => viewOf());
    renderDna(services);
    await loaded();
    expect(screen.getByText("家人最近改过这份，TA 正按它来")).toBeTruthy();
    expect(portraitOf("奶茶")).toEqual({ image: null, paw: true, text: "" });
  });

  it("只读：五组栏目；称呼与小暗号标“只属于你”，小暗号另标“只在私信里用”；没写的写“还没写”；没有输入框", async () => {
    const { services } = liveDna(viewOf(), async () => viewOf());
    renderDna(services);
    await loaded();
    for (const title of ["怎么称呼", "TA 的性子", "TA 喜欢的", "TA 的日常", "你们之间"]) expect(screen.getByRole("heading", { level: 3, name: title })).toBeTruthy();
    expect(fieldRow("owner_title").textContent).toContain("姐姐");
    expect(fieldRow("owner_title").textContent).toContain("只属于你");
    expect(fieldRow("owner_title").textContent).not.toContain("只在私信里用");
    expect(fieldRow("shared_memories").textContent).toContain("只属于你");
    expect(fieldRow("shared_memories").textContent).toContain("只在私信里用");
    expect(fieldRow("personality").querySelector(".ps-dna-badge")).toBeNull();
    expect(fieldRow("voice_style").textContent).toContain("还没写");
    expect([...fieldRow("hobbies").querySelectorAll("li")].map((li) => li.textContent)).toEqual(["看书"]);
    expect(document.querySelectorAll("input, textarea")).toHaveLength(0);
    expect(document.body.textContent).not.toMatch(INTERNAL_WORDS);
  });

  it("行为倾向只读：每条带原话出处；说不准的列在“还没想明白的”，不强行归类；只说倾向，不露倍数和规则编号", async () => {
    const { services } = liveDna(viewOf(), async () => viewOf());
    renderDna(services);
    await loaded();
    const section = screen.getByRole("region", { name: "TA 会怎么过日子" });
    const row = (label: string) => within(section).getByText(label).closest("li") as HTMLElement;
    expect(within(section).getByText("不爱熬夜：按平常作息（23:30 睡，07:30 起）")).toBeTruthy();
    expect(within(section).getByText("恋家：少出门、话少")).toBeTruthy();

    const homebody = row("恋家安静");
    expect(homebody.textContent).toContain("是这样");
    const quotes = [...homebody.querySelectorAll(".ps-dna-evidence__quote")].map((el) => el.textContent);
    expect(quotes).toEqual(["出自性格：「喜欢安静」", "出自性格：「不爱热闹」"]); // 同一句只列一次
    expect(homebody.querySelector(".is-implied")?.textContent).toContain("由“不爱热闹”反推");

    const nightOwl = row("爱熬夜");
    expect(nightOwl.textContent).toContain("不是这样");
    expect(nightOwl.textContent).toContain("出自性格：「不爱熬夜」");
    expect(nightOwl.textContent).toContain("“不”否定了这个说法");

    // 说不准的性子不列成一条倾向，原话放进“还没想明白的”。
    expect(within(section).queryByText("爱睡觉")).toBeNull();
    const unsure = within(section).getByRole("heading", { level: 4, name: "还没想明白的" }).parentElement as HTMLElement;
    expect(unsure.textContent).toContain("「有时候睡一整天」");

    const bookstore = row("在书店理书");
    expect(bookstore.textContent).toContain("更愿意");
    expect(bookstore.textContent).toContain("出自爱好：「看书」");
    const faraway = row("出远门");
    expect(faraway.textContent).toContain("不太愿意");
    expect(faraway.textContent).toContain("恋家：不太想出远门");
    expect(row("进城逛逛").textContent).toContain("照常");
    // 更愿意的在前，其次不太愿意，照常的在最后。
    const preferences = within(section).getByRole("heading", { level: 4, name: "想做的事、想去的地方" }).parentElement as HTMLElement;
    expect([...preferences.querySelectorAll(".ps-dna-lean strong")].map((el) => el.textContent)).toEqual(["在书店理书", "出远门", "进城逛逛"]);

    expect(section.textContent).not.toMatch(/2\.25|0\.3|倍|dna-behavior/);
    expect(document.body.textContent).not.toMatch(INTERNAL_WORDS);
  });

  it("没有行为倾向（老数据）就不出现这一块；全是默认、什么都没看出来时说“先按平常的节奏过”", async () => {
    const first = liveDna(viewOf({ behavior: null }), async () => viewOf());
    renderDna(first.services);
    await loaded();
    expect(screen.queryByRole("region", { name: "TA 会怎么过日子" })).toBeNull();
    cleanup();

    const quiet: PetBehavior = { ...BEHAVIOR, summary: [], traits: [], preferences: [], unclassified: [] };
    const second = liveDna(viewOf({ behavior: quiet }), async () => viewOf());
    renderDna(second.services);
    await loaded();
    expect(screen.getByRole("region", { name: "TA 会怎么过日子" }).textContent).toContain("还看不出 TA 的作息和喜好，先按平常的节奏过。");
  });
});

/* ---------------- 改与保存 ---------------- */

describe("TA 的档案 · 改与保存", () => {
  it("保存带进入编辑时读到的版本号；成功后回到只读、提示已保存，返回的新一份直接写回缓存", async () => {
    const saved = viewOf({ version: 4, dna: { ...SAVED_DNA, personality: "慢热，熟了以后特别黏人", fears: ["打雷", "吸尘器"] } });
    const api = liveDna(viewOf({ version: 3 }), async () => saved);
    const { client } = renderDna(api.services);
    await loaded();
    await startEditing();

    fireEvent.change(screen.getByLabelText("性格"), { target: { value: "慢热，熟了以后特别黏人" } });
    fireEvent.change(screen.getByLabelText("害怕的东西"), { target: { value: "吸尘器" } });
    fireEvent.keyDown(screen.getByLabelText("害怕的东西"), { key: "Enter" });
    expect(screen.getByRole("button", { name: "去掉「吸尘器」" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await screen.findByText("已保存，TA 从现在起按这份来。");
    expect(api.saveDna).toHaveBeenCalledTimes(1);
    const [petId, body, version] = api.saveDna.mock.calls[0];
    expect(petId).toBe("pet-a");
    expect(version).toBe(3);
    expect(body).toEqual({ ...SAVED_DNA, personality: "慢热，熟了以后特别黏人", fears: ["打雷", "吸尘器"] });
    // 回到只读：没有表单、没有输入框；显示的是返回的那一份；缓存就是返回值（不另外再读）。
    expect(editForm()).toBeNull();
    expect(document.querySelectorAll("input, textarea")).toHaveLength(0);
    expect(fieldRow("personality").textContent).toContain("慢热，熟了以后特别黏人");
    expect(client.getQueryData(KEY)).toEqual(saved);
    expect(api.dna).toHaveBeenCalledTimes(1);
  });

  it("409 dna_version_conflict：提示冲突，不当成已保存（不写缓存、不回只读、改动还在）；“看看最新的”先确认，确认后才重新读取", async () => {
    const api = liveDna(viewOf({ version: 3 }), async () => {
      throw conflictError();
    });
    const { client } = renderDna(api.services);
    await loaded();
    await startEditing();
    fireEvent.change(screen.getByLabelText("性格"), { target: { value: "我这边写的" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("家人刚改过，先看看最新的再改。");
    expect(alert.textContent).not.toContain("DNA"); // 不照搬服务端那句带内部叫法的话
    expect(api.saveDna.mock.calls[0][2]).toBe(3);
    expect(screen.queryByText(/已保存/)).toBeNull();
    expect(editForm()).toBeTruthy();
    // 已知家人改过：保存先停用（旧版本号再发也只会被拒），只能看最新的或取消。
    expect((screen.getByRole("button", { name: "保存" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.submit(editForm() as HTMLElement);
    expect(api.saveDna).toHaveBeenCalledTimes(1);
    expect((screen.getByLabelText("性格") as HTMLTextAreaElement).value).toBe("我这边写的");
    expect((client.getQueryData(KEY) as PetDNAView).version).toBe(3);
    expect((client.getQueryData(KEY) as PetDNAView).dna.personality).toBe(SAVED_DNA.personality);

    // 家人改过的新一份。
    api.state.current = viewOf({ version: 4, updated_by_you: false, dna: { ...SAVED_DNA, personality: "家人写的性格" } });

    // 先问一句：选“先留着”就什么都不动（不重新读取，改动还在）。
    fireEvent.click(screen.getByRole("button", { name: "看看最新的" }));
    const ask = screen.getByRole("dialog", { name: "看看最新的？" });
    fireEvent.click(within(ask).getByRole("button", { name: "先留着" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect((screen.getByLabelText("性格") as HTMLTextAreaElement).value).toBe("我这边写的");
    expect(api.dna).toHaveBeenCalledTimes(1);

    // 确认丢掉改动：重新读取，回到只读，显示家人的那一份。
    fireEvent.click(screen.getByRole("button", { name: "看看最新的" }));
    fireEvent.click(within(screen.getByRole("dialog", { name: "看看最新的？" })).getByRole("button", { name: "丢掉改动，看最新的" }));
    await screen.findByText("已换成最新的一份。想改的话，再点“改一改”。");
    expect(api.dna).toHaveBeenCalledTimes(2);
    expect(editForm()).toBeNull();
    expect(fieldRow("personality").textContent).toContain("家人写的性格");
    expect(screen.getByText("家人最近改过这份，TA 正按它来")).toBeTruthy();
    expect(api.saveDna).toHaveBeenCalledTimes(1);
  });

  it("编辑中后台已经读到家人改过的新一份：先提示冲突，保存按钮不再发出去（更不会换成新版本号去盖掉家人的）", async () => {
    const api = liveDna(viewOf({ version: 3 }), async () => viewOf({ version: 5 }));
    const { client } = renderDna(api.services);
    await loaded();
    await startEditing();
    fireEvent.change(screen.getByLabelText("说话的样子"), { target: { value: "慢吞吞" } });

    api.state.current = viewOf({ version: 4, updated_by_you: false, dna: { ...SAVED_DNA, personality: "家人写的性格" } });
    await act(() => client.invalidateQueries({ queryKey: KEY }));

    expect((await screen.findByRole("alert")).textContent).toContain("家人刚改过，先看看最新的再改。");
    const saveButton = screen.getByRole("button", { name: "保存" }) as HTMLButtonElement;
    expect(saveButton.disabled).toBe(true);
    fireEvent.submit(editForm() as HTMLElement);
    expect(api.saveDna).not.toHaveBeenCalled();
    expect((screen.getByLabelText("说话的样子") as HTMLInputElement).value).toBe("慢吞吞");
  });

  it("保存失败（信号断了）：说没保存上，改动还在，再点一次就能存", async () => {
    let attempt = 0;
    const api = liveDna(viewOf(), async (_petId, body) => {
      attempt += 1;
      if (attempt === 1) throw new ApiError({ kind: "network", code: "NETWORK_ERROR", message: "网络连接失败", retryable: true });
      return viewOf({ version: 4, dna: body });
    });
    renderDna(api.services);
    await loaded();
    await startEditing();
    fireEvent.change(screen.getByLabelText("口头禅"), { target: { value: "喵呜～" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    expect((await screen.findByRole("alert")).textContent).toBe("信号断了一下，没保存上，再试一次。");
    expect((screen.getByLabelText("口头禅") as HTMLInputElement).value).toBe("喵呜～");
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await screen.findByText("已保存，TA 从现在起按这份来。");
    expect(api.saveDna.mock.calls.map((call) => call[2])).toEqual([3, 3]);
    expect(fieldRow("catchphrase").textContent).toContain("喵呜～");
  });

  it("草稿“就按这份”：先重读确认还没人保存过，再带 expected_version=0（还没保存过）整份保存（即确认）", async () => {
    const draft = draftOf();
    const api = liveDna(draft, async () => viewOf({ version: 1, dna: draft.dna }));
    renderDna(api.services);
    await loaded();
    fireEvent.click(screen.getByRole("button", { name: "就按这份" }));
    await screen.findByText("已保存，TA 从现在起按这份来。");
    expect(api.dna).toHaveBeenCalledTimes(2);
    expect(api.saveDna).toHaveBeenCalledTimes(1);
    expect(api.saveDna).toHaveBeenCalledWith("pet-a", draft.dna, 0);
    expect(screen.queryByText("待你确认")).toBeNull();
    expect(screen.queryByText(/看看对不对/)).toBeNull();
  });

  it("草稿改完第一次保存带 0；保存过以后再改，带服务端返回的那一份的版本号（不再是 0）", async () => {
    let saved = 0; // 服务端版本：第一次保存后是 1，之后每次加 1
    const api = liveDna(draftOf(), async (_petId, body) => viewOf({ version: ++saved, dna: body }));
    renderDna(api.services);
    await loaded();
    await startEditing();
    fireEvent.change(screen.getByLabelText("口头禅"), { target: { value: "喵～" } });
    fireEvent.click(screen.getByRole("button", { name: "确认并保存" }));
    await screen.findByText("已保存，TA 从现在起按这份来。");
    expect(api.saveDna.mock.calls[0][2]).toBe(0);

    await startEditing();
    fireEvent.change(screen.getByLabelText("口头禅"), { target: { value: "咕噜咕噜" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(api.saveDna).toHaveBeenCalledTimes(2));
    expect(api.saveDna.mock.calls.map((call) => call[2])).toEqual([0, 1]);
    await waitFor(() => expect(fieldRow("catchphrase").textContent).toContain("咕噜咕噜"));
  });

  it("草稿首存时服务端回 409（重读之后才有人抢先确认了一份）：照旧按冲突处理，不当成已保存", async () => {
    const family = viewOf({ version: 1, updated_by_you: false, dna: { ...SAVED_DNA, personality: "家人写的性格" } });
    // 编辑态：带 0 发出去被拒，提示冲突、改动还在、保存停用；缓存里还是那份草稿。
    const api = liveDna(draftOf(), async () => {
      throw conflictError();
    });
    const { client } = renderDna(api.services);
    await loaded();
    await startEditing();
    fireEvent.change(screen.getByLabelText("性格"), { target: { value: "我写的" } });
    fireEvent.click(screen.getByRole("button", { name: "确认并保存" }));
    expect((await screen.findByRole("alert")).textContent).toContain("家人刚改过，先看看最新的再改。");
    expect(api.saveDna.mock.calls[0][2]).toBe(0);
    expect(screen.queryByText(/已保存/)).toBeNull();
    expect((screen.getByLabelText("性格") as HTMLTextAreaElement).value).toBe("我写的");
    expect((screen.getByRole("button", { name: "确认并保存" }) as HTMLButtonElement).disabled).toBe(true);
    expect((client.getQueryData(KEY) as PetDNAView).confirmed).toBe(false);
    cleanup();

    // 只读态“就按这份”被拒：同样提示冲突；没有本地改动，“看看最新的”直接换成家人确认的那一份。
    const readOnly = liveDna(draftOf(), async () => {
      throw conflictError();
    });
    renderDna(readOnly.services);
    await loaded();
    fireEvent.click(screen.getByRole("button", { name: "就按这份" }));
    expect((await screen.findByRole("alert")).textContent).toContain("家人刚改过，先看看最新的再改。");
    expect(readOnly.saveDna.mock.calls[0][2]).toBe(0);
    expect(screen.getByText("待你确认")).toBeTruthy();
    readOnly.state.current = family;
    fireEvent.click(screen.getByRole("button", { name: "看看最新的" }));
    await screen.findByText("已换成最新的一份。想改的话，再点“改一改”。");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(fieldRow("personality").textContent).toContain("家人写的性格");
    expect(screen.queryByText("待你确认")).toBeNull();
  });

  it("草稿第一次保存前重读，发现家人已经确认过一份：不发保存（只读态换成最新的，编辑态提示冲突）", async () => {
    const family = viewOf({ version: 1, updated_by_you: false, dna: { ...SAVED_DNA, personality: "家人写的性格" } });
    const api = liveDna(draftOf(), async () => viewOf());
    renderDna(api.services);
    await loaded();
    api.state.current = family;
    fireEvent.click(screen.getByRole("button", { name: "就按这份" }));
    await screen.findByText("已换成最新的一份。想改的话，再点“改一改”。");
    expect(api.saveDna).not.toHaveBeenCalled();
    expect(screen.queryByText("待你确认")).toBeNull();
    expect(fieldRow("personality").textContent).toContain("家人写的性格");
    cleanup();

    const again = liveDna(draftOf(), async () => viewOf());
    renderDna(again.services);
    await loaded();
    await startEditing();
    fireEvent.change(screen.getByLabelText("性格"), { target: { value: "我写的" } });
    again.state.current = family;
    fireEvent.click(screen.getByRole("button", { name: "确认并保存" }));
    expect((await screen.findByRole("alert")).textContent).toContain("家人刚改过，先看看最新的再改。");
    expect(again.saveDna).not.toHaveBeenCalled();
    expect((screen.getByLabelText("性格") as HTMLTextAreaElement).value).toBe("我写的");
  });

  it("进页面总会重新读一次（称呼在“我们的家”也能改）；读完之前“改一改”先等一等，编辑的底子是刚读到的那一份", async () => {
    let release: (view: PetDNAView) => void = () => undefined;
    const fresh = viewOf({ dna: { ...SAVED_DNA, owner_title: "妈妈" } });
    const dna = vi.fn(() => new Promise<PetDNAView>((resolve) => (release = resolve)));
    const saveDna = vi.fn(async () => fresh);
    renderDna(
      { session: { current: async () => SIGNED_IN }, households: { list: async () => [household()] }, pets: { dna, saveDna } },
      viewOf({ dna: { ...SAVED_DNA, owner_title: "旧称呼" } }),
    );
    await loaded();
    await waitFor(() => expect(dna).toHaveBeenCalledTimes(1));
    expect(fieldRow("owner_title").textContent).toContain("旧称呼");
    expect((screen.getByRole("button", { name: "改一改" }) as HTMLButtonElement).disabled).toBe(true);
    await act(async () => release(fresh));
    await waitFor(() => expect((screen.getByRole("button", { name: "改一改" }) as HTMLButtonElement).disabled).toBe(false));
    expect(fieldRow("owner_title").textContent).toContain("妈妈");
    fireEvent.click(screen.getByRole("button", { name: "改一改" }));
    expect((screen.getByLabelText("TA 怎么叫你") as HTMLInputElement).value).toBe("妈妈");
  });

  it("取消：没改动直接回到只读；有改动先确认（接着写 / 不改了）", async () => {
    const api = liveDna(viewOf(), async () => viewOf());
    renderDna(api.services);
    await loaded();
    await startEditing();
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(editForm()).toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();

    await startEditing();
    fireEvent.change(screen.getByLabelText("TA 怎么叫你"), { target: { value: "妈妈" } });
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    fireEvent.click(within(screen.getByRole("dialog", { name: "不改了？" })).getByRole("button", { name: "接着写" }));
    expect((screen.getByLabelText("TA 怎么叫你") as HTMLInputElement).value).toBe("妈妈");
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    fireEvent.click(within(screen.getByRole("dialog", { name: "不改了？" })).getByRole("button", { name: "不改了" }));
    expect(editForm()).toBeNull();
    expect(fieldRow("owner_title").textContent).toContain("姐姐");
    expect(api.saveDna).not.toHaveBeenCalled();
  });

  it("有改动时离开本页（左上角返回）：先确认；接着写就留下，离开才走", async () => {
    const api = liveDna(viewOf(), async () => viewOf());
    const { router } = renderDna(api.services);
    await loaded();
    await startEditing();
    fireEvent.change(screen.getByLabelText("性格"), { target: { value: "刚写了一半" } });

    fireEvent.click(screen.getByRole("link", { name: "返回我的" }));
    const ask = await screen.findByRole("dialog", { name: "要离开吗？" });
    fireEvent.click(within(ask).getByRole("button", { name: "接着写" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(router.state.location.pathname).toBe("/me/dna");
    expect((screen.getByLabelText("性格") as HTMLTextAreaElement).value).toBe("刚写了一半");

    fireEvent.click(screen.getByRole("link", { name: "返回我的" }));
    fireEvent.click(within(await screen.findByRole("dialog", { name: "要离开吗？" })).getByRole("button", { name: "离开" }));
    await screen.findByText("这里是我的页");
    expect(router.state.location.pathname).toBe("/me");
    expect(api.saveDna).not.toHaveBeenCalled();
  });

  it("标签：回车添上（输入法组字时的回车不算）、可以去掉、没点“添上”的那条保存时也算进去", async () => {
    const api = liveDna(viewOf(), async (_petId, body) => viewOf({ version: 4, dna: body }));
    renderDna(api.services);
    await loaded();
    await startEditing();
    const nick = screen.getByLabelText("家里叫 TA 的小名");
    fireEvent.change(nick, { target: { value: "团子" } });
    fireEvent.keyDown(nick, { key: "Enter", isComposing: true });
    fireEvent.keyDown(nick, { key: "Enter", keyCode: 229 });
    expect(screen.queryByRole("button", { name: "去掉「团子」" })).toBeNull();
    fireEvent.keyDown(nick, { key: "Enter" });
    expect(screen.getByRole("button", { name: "去掉「团子」" })).toBeTruthy();
    expect((screen.getByLabelText("家里叫 TA 的小名") as HTMLInputElement).value).toBe("");
    fireEvent.click(screen.getByRole("button", { name: "去掉「岚岚」" }));
    expect(screen.queryByRole("button", { name: "去掉「岚岚」" })).toBeNull();

    // “添上”按钮也能添；空白不算。
    const place = screen.getByLabelText("喜欢的地方");
    const placeAdd = within(place.parentElement as HTMLElement).getByRole("button", { name: "添上" }) as HTMLButtonElement;
    fireEvent.change(place, { target: { value: "   " } });
    expect(placeAdd.disabled).toBe(true);
    fireEvent.change(place, { target: { value: "窗台" } });
    fireEvent.click(placeAdd);
    expect(screen.getByRole("button", { name: "去掉「窗台」" })).toBeTruthy();
    expect((screen.getByLabelText("喜欢的地方") as HTMLInputElement).value).toBe("");
    fireEvent.change(screen.getByLabelText("爱吃的"), { target: { value: "冻干小鱼" } }); // 没点“添上”

    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await screen.findByText("已保存，TA 从现在起按这份来。");
    const body = api.saveDna.mock.calls[0][1];
    expect(body.nicknames).toEqual(["团子"]);
    expect(body.favorite_foods).toEqual(["冻干小鱼"]);
    expect(body.favorite_places).toEqual(["窗台"]);
  });

  it("单行栏目按回车（手机键盘的“完成”）不顺手提交整张表；输入法组字中的回车照常交给输入法", async () => {
    const api = liveDna(viewOf(), async () => viewOf());
    renderDna(api.services);
    await loaded();
    await startEditing();
    const voice = screen.getByLabelText("说话的样子");
    fireEvent.change(voice, { target: { value: "慢吞吞" } });
    // fireEvent 返回 false = 默认动作（隐式提交）被拦下。
    expect(fireEvent.keyDown(voice, { key: "Enter" })).toBe(false);
    expect(fireEvent.keyDown(voice, { key: "Enter", isComposing: true })).toBe(true);
    expect(fireEvent.keyDown(screen.getByLabelText("爱吃的"), { key: "Enter" })).toBe(false);
    expect(api.saveDna).not.toHaveBeenCalled();
    expect(editForm()).toBeTruthy();
  });

  it("列表满了：收起输入框，说明去掉一条才能再添；去掉一条后输入框回来", async () => {
    const api = liveDna(viewOf({ dna: { ...SAVED_DNA, fears: ["一", "二", "三", "四", "五", "六"] } }), async () => viewOf());
    renderDna(api.services);
    await loaded();
    await startEditing();
    expect(screen.queryByLabelText("害怕的东西")).toBeNull();
    expect(screen.getByText("最多 6 条，去掉一条才能再添。")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "去掉「六」" }));
    expect(screen.getByLabelText("害怕的东西")).toBeTruthy();
  });

  it("编辑态：个人那份与私信栏目说清去处；页面文字不露内部叫法", async () => {
    const api = liveDna(viewOf(), async () => viewOf());
    renderDna(api.services);
    await loaded();
    await startEditing();
    const form = editForm() as HTMLElement;
    expect(form.textContent).toContain("每位家人各写各的，别的家人看不到。");
    expect(form.textContent).toContain("只有你们俩懂的话、一起做过的傻事。每位家人各写各的，别的家人看不到；只在你和 TA 的私聊里用。");
    expect(form.textContent).toContain("也可以是 TA 常发出的声音。");
    expect(document.body.textContent).not.toMatch(INTERNAL_WORDS);
  });
});

/* ---------------- 演示模式与入口（经真实路由表） ---------------- */

describe("演示模式与“我的”入口（fixture，真实路由表与演示服务）", () => {
  it("/me/dna：温和说明“演示模式没有 TA 的档案”，不崩、不编数据、没有“改一改”；头像是演示图，不写首字", async () => {
    renderApp("/me/dna");
    expect(await screen.findByText("演示模式没有 TA 的档案")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 1, name: "TA 的档案" })).toBeTruthy();
    expect(screen.getByRole("heading", { level: 2, name: FIXTURE_PET.name })).toBeTruthy();
    expect(screen.getByRole("link", { name: "返回我的" }).getAttribute("href")).toBe("/me");
    const portrait = portraitOf(FIXTURE_PET.name);
    expect(portrait.image).toBeTruthy();
    expect(portrait.text).toBe("");
    expect(screen.queryByRole("button", { name: "改一改" })).toBeNull();
    expect(screen.queryByRole("button", { name: "就按这份" })).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByText("待你确认")).toBeNull();
    expect(document.querySelector(".ps-dna-field")).toBeNull();
    expect(document.body.textContent).not.toMatch(/接入|出错|失败|重试|没能|能力|服务端|接口|fixture|模型/);
  });

  it("/me：有“TA 的档案”入口，指向 /me/dna；点进去就是档案页", async () => {
    const router = renderApp("/me");
    const entry = await screen.findByRole("link", { name: /^TA 的档案/ });
    expect(entry.getAttribute("href")).toBe("/me/dna");
    expect(entry.textContent).toContain("性格、习惯和你们之间的小事");
    fireEvent.click(entry);
    expect(await screen.findByText("演示模式没有 TA 的档案")).toBeTruthy();
    expect(router.state.location.pathname).toBe("/me/dna");
  });
});
