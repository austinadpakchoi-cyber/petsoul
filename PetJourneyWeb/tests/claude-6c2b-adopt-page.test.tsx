/**
 * claude-6c2b · 领养页 /adopt（巡检 P1）与入住表单、添伙伴页（巡检入住复测 P2）。
 * 领养页：头像用居民同一套（照片 / 同物种插画标“插画”，演示灰猫只给猫）；名字旁写物种；“梦想”前不再漂着“✧”；
 *   已有家的不堆在列表里，收成一行链到 /world；“认识 TA”去居民主页、“迎接 TA”才弹确认（不领养），没有 pet_id 只有“迎接 TA”。
 * 入住表单：物种不预选；名字、物种缺哪样，按钮旁就写哪样（按钮灰着时不让人猜）；缺东西时回车也不提交。
 * 添伙伴页：没起名的家不再写笼统的“当前家庭”，与切换栏同一套说法（“麦芽的家”）。
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import type { AdoptionCandidate, HouseholdBrief, HouseholdPetBrief, SessionState } from "@/shared/contracts";
import { ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { HouseholdProvider } from "@/shared/session/householdContext";
import { AddCompanionPage, AdoptPage, OnboardingPage } from "@/features/pets/pages";

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
});
afterEach(() => cleanup());

const guest = { authenticated: false, user: null, csrf_required: false, expires_at: null, onboarding: null } as SessionState;
const signedIn = {
  authenticated: true,
  user: { user_id: "u-1", display_name: null, username: "tester", auth_method: "web_password" },
  csrf_required: true,
  expires_at: null,
  onboarding: { step: "needs_companion", pet_id: null, home_id: null, reception_session_id: null, reception_skipped: false, home_activated_at: null, pet_origin: null, entry: null },
} as unknown as SessionState;

function strict(services: Record<string, unknown>): ServiceMap {
  return new Proxy(services as unknown as ServiceMap, {
    get(target, prop: string) {
      if (prop in target) return target[prop as keyof ServiceMap];
      throw new Error(`unexpected service ${prop}`);
    },
  });
}

function Where() {
  const location = useLocation();
  return <p data-testid="where">{location.pathname + location.search}</p>;
}

function renderAt(path: string, element: React.ReactNode, services: Record<string, unknown>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={strict(services)}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path={path} element={element} />
            <Route path="*" element={<Where />} />
          </Routes>
        </MemoryRouter>
      </ServicesProvider>
    </QueryClientProvider>,
  );
}

/* ---------------- 领养页 ---------------- */

const candidate = (over: Partial<AdoptionCandidate> & Pick<AdoptionCandidate, "candidate_id" | "name" | "species">): AdoptionCandidate => ({
  personality: "爱唱歌", dream: "在灯塔上看一次日出", origin: "adopted_original", source_note: "PetSoul 原创伙伴", background_available: false, availability: "available", data_origin: "live",
  pet_id: null, photo_url: null, ...over,
}) as AdoptionCandidate;

const ACHENG = candidate({ candidate_id: "c-dog", name: "阿澄", species: "dog", pet_id: "PJ-E33E3792", photo_url: "/api/v1/web/public/media/pets/PJ-E33E3792/photo" });
const QIUQIU = candidate({ candidate_id: "c-bird", name: "秋秋", species: "bird", pet_id: "PJ-5427BA15" });
const YUNDUO = candidate({ candidate_id: "c-rabbit", name: "云朵", species: "rabbit", pet_id: "PJ-22672A03" });
const LEGACY = candidate({ candidate_id: "c-legacy", name: "旧候选", species: "hamster" });
const homed = (id: string, name: string) => candidate({ candidate_id: id, name, species: "cat", availability: "adopted" });

function renderAdopt(list: AdoptionCandidate[], session: SessionState = signedIn) {
  const adopt = vi.fn(async () => ({ pet_id: "PJ-NEW", candidate_id: "c", adopted_at: "2026-09-24T00:00:00Z" }));
  const services: Record<string, unknown> = { session: { current: async () => session }, pets: { adoptionCandidates: async () => list, adopt } };
  // 领养页的“迎接 TA”用共用组件：live 且登录时它要读这个人的家（待领养阶段通常一个家都没有）。
  if (mode.dataMode === "live") services.households = { list: async () => [] };
  renderAt("/adopt", <AdoptPage />, services);
  return { adopt };
}

const cardOf = async (name: string) => (await screen.findByText(name, { selector: "strong" })).closest(".ps-adopt-card") as HTMLElement;

describe("领养页 /adopt", () => {
  it("头像：有照片用照片，没有用同物种插画并标“插画”；名字旁写物种（小鸟、兔子一眼看得出）", async () => {
    renderAdopt([ACHENG, QIUQIU, YUNDUO]);
    const acheng = await cardOf("阿澄");
    // 原创居民的形象是生成的原创设计：读屏说“形象（AI 生成）”，与星球页一致（ResidentPortrait 的 origin）。
    const photo = within(acheng).getByRole("img", { name: "阿澄的形象（AI 生成）" });
    expect(photo.querySelector("img")?.getAttribute("src")).toBe("/api/v1/web/public/media/pets/PJ-E33E3792/photo");
    expect(within(acheng).getByText("狗").className).toBe("ps-world-resident__species");
    const qiuqiu = await cardOf("秋秋");
    expect(within(qiuqiu).getByRole("img", { name: "小鸟的插画，不是秋秋本人的照片" })).toBeTruthy();
    expect(within(qiuqiu).getByText("插画")).toBeTruthy();
    expect(within(qiuqiu).getByText("小鸟").className).toBe("ps-world-resident__species");
    expect(within(await cardOf("云朵")).getByText("兔子").className).toBe("ps-world-resident__species");
  });

  it("不是原创居民（真实档案）的照片：读屏仍说“照片”", async () => {
    renderAdopt([candidate({ candidate_id: "c-real", name: "旺财", species: "dog", origin: "adopted_real_archive", pet_id: "PJ-REAL", photo_url: "/api/v1/web/public/media/pets/PJ-REAL/photo" })]);
    expect(within(await cardOf("旺财")).getByRole("img", { name: "旺财的照片" })).toBeTruthy();
  });

  it("“梦想”前不再漂着“✧”：梦想一行里没有图标，文字从“梦想”开始", async () => {
    renderAdopt([QIUQIU]);
    const dream = within(await cardOf("秋秋")).getByText("梦想：在灯塔上看一次日出");
    expect(dream.querySelector("svg")).toBeNull();
    expect(dream.previousElementSibling?.tagName.toLowerCase()).not.toBe("svg");
    expect(dream.textContent?.startsWith("梦想")).toBe(true);
  });

  it("已经有家的居民不堆在列表里：收成一行，链到 /world", async () => {
    renderAdopt([ACHENG, QIUQIU, homed("h-1", "阿绒"), homed("h-2", "豆豆"), homed("h-3", "布丁")]);
    await cardOf("阿澄");
    expect(document.querySelectorAll(".ps-adopt-card")).toHaveLength(2);
    expect(screen.queryByText("阿绒")).toBeNull();
    expect(screen.queryByRole("button", { name: /已经有家了/ })).toBeNull();
    expect(screen.getByRole("link", { name: "还有 3 位居民已经有家了，去星球上认识 TA 们" }).getAttribute("href")).toBe("/world");
  });

  it("全都有家了：说现在没有在等一个家的居民，并给去星球的那一行", async () => {
    renderAdopt([homed("h-1", "阿绒"), homed("h-2", "豆豆")]);
    expect(await screen.findByText("现在没有在等一个家的居民")).toBeTruthy();
    expect(screen.getByRole("link", { name: "2 位居民都已经有家了，去星球上认识 TA 们" }).getAttribute("href")).toBe("/world");
  });

  it("没有已经有家的：不出那一行", async () => {
    renderAdopt([ACHENG]);
    await cardOf("阿澄");
    expect(screen.queryByRole("link", { name: /已经有家了/ })).toBeNull();
  });

  it("两个动作分开：“认识 TA”去居民主页；“迎接 TA”才弹确认（不领养）；没有 pet_id 只有“迎接 TA”", async () => {
    const { adopt } = renderAdopt([ACHENG, LEGACY]);
    const acheng = await cardOf("阿澄");
    expect(within(acheng).getByRole("link", { name: "认识 TA：阿澄" }).getAttribute("href")).toBe("/world/residents/PJ-E33E3792");
    const legacy = await cardOf("旧候选");
    expect(within(legacy).queryByRole("link", { name: /认识 TA/ })).toBeNull();
    expect(within(legacy).getByRole("button", { name: "迎接 TA：旧候选" })).toBeTruthy();

    const welcome = within(acheng).getByRole("button", { name: "迎接 TA：阿澄" }) as HTMLButtonElement;
    await waitFor(() => expect(welcome.disabled).toBe(false));
    fireEvent.click(welcome);
    const box = within(acheng).getByRole("group", { name: "确认领养 阿澄" });
    expect(within(box).getByText("确定迎接 阿澄 吗？")).toBeTruthy();
    expect(within(acheng).queryByRole("link", { name: "认识 TA：阿澄" })).toBeNull();
    expect(adopt).not.toHaveBeenCalled();
  });

  it("演示模式：没有照片的猫用授权的演示灰猫，别的物种用插画（演示灰猫只给猫）", async () => {
    mode.dataMode = "fixture";
    renderAdopt([candidate({ candidate_id: "fx-1", name: "小岚", species: "cat", data_origin: "fixture" }), candidate({ candidate_id: "fx-3", name: "阿绒", species: "rabbit", data_origin: "fixture" })], guest);
    expect(within(await cardOf("小岚")).getByRole("img", { name: "小岚（演示照片）" })).toBeTruthy();
    expect(within(await cardOf("阿绒")).getByRole("img", { name: "兔子的插画，不是阿绒本人的照片" })).toBeTruthy();
  });
});

/* ---------------- 入住表单：缺什么写什么、物种不预选 ---------------- */

describe("入住表单（认识 TA 02/04）", () => {
  function renderOnboarding() {
    const createOwn = vi.fn((_input: { name: string; species: string }, _key: string) => new Promise<never>(() => undefined));
    renderAt("/onboarding", <OnboardingPage />, { session: { current: async () => signedIn }, pets: { createOwn } });
    return { createOwn };
  }
  const submit = () => screen.getByRole("button", { name: "继续，去见接待员" }) as HTMLButtonElement;

  it("物种不预选：七个选项一个都没选中", async () => {
    renderOnboarding();
    await screen.findByLabelText("02 / TA 叫什么名字？");
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    expect(radios).toHaveLength(7);
    expect(radios.filter((radio) => radio.checked)).toHaveLength(0);
  });

  it("按钮灰着时就写缺什么，并挂在按钮的说明上；补齐一样少说一样，全齐了提示消失、按钮可点", async () => {
    renderOnboarding();
    await screen.findByLabelText("02 / TA 叫什么名字？");
    const hint = () => screen.queryByRole("status");
    expect(hint()?.textContent).toBe("先写下 TA 的名字，再选一下 TA 是什么动物");
    expect(submit().disabled).toBe(true);
    expect(submit().getAttribute("aria-describedby")).toBe(hint()?.id);

    fireEvent.change(screen.getByLabelText("02 / TA 叫什么名字？"), { target: { value: "团子" } });
    expect(hint()?.textContent).toBe("选一下 TA 是什么动物");
    expect(submit().disabled).toBe(true);

    fireEvent.click(screen.getByRole("radio", { name: "狗" }));
    expect(hint()).toBeNull();
    expect(submit().disabled).toBe(false);
    expect(submit().getAttribute("aria-describedby")).toBeNull();

    fireEvent.change(screen.getByLabelText("02 / TA 叫什么名字？"), { target: { value: "  " } });
    expect(hint()?.textContent).toBe("先写下 TA 的名字");
  });

  it("缺东西时回车也不提交；补齐后照常带上选的物种", async () => {
    const { createOwn } = renderOnboarding();
    const nameInput = await screen.findByLabelText("02 / TA 叫什么名字？");
    fireEvent.change(nameInput, { target: { value: "团子" } });
    fireEvent.submit(nameInput.closest("form")!);
    // mutate 会隔一个微任务才调 mutationFn：先等一拍再断言“没提交”，免得假绿。
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)); });
    expect(createOwn).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("radio", { name: "兔子" }));
    fireEvent.submit(nameInput.closest("form")!);
    await waitFor(() => expect(createOwn).toHaveBeenCalledTimes(1));
    expect(createOwn.mock.calls[0][0]).toMatchObject({ name: "团子", species: "rabbit" });
  });
});

/* ---------------- 添伙伴页：家名 ---------------- */

describe("添伙伴页 /pets/new 的家名", () => {
  const pet = (pet_id: string, name: string) =>
    ({ pet_id, name, species: "dog", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-20T00:00:00Z", added_by_you: true }) as unknown as HouseholdPetBrief;
  const home = (name: string | null) => ({ household_id: "h-1", name, role: "admin", home_activated: true, home_id: "home-1", member_count: 1, pets: [pet("p-1", "麦芽")] }) as unknown as HouseholdBrief;

  function renderAddCompanion(household: HouseholdBrief) {
    renderAt("/pets/new", <HouseholdProvider userId="u-1"><AddCompanionPage /></HouseholdProvider>, {
      session: { current: async () => signedIn },
      households: { list: async () => [household] },
      pets: { createOwn: vi.fn() },
    });
  }
  const chip = async () => (await screen.findByText("只加入这个家，不会新建家庭。现有伙伴、家园位置和库存保持原样。")).closest(".ps-companion-card")!.querySelector(".ps-chip");

  it("没起名：写“麦芽的家”，不再是笼统的“当前家庭”", async () => {
    renderAddCompanion(home(null));
    expect((await chip())?.textContent).toBe("麦芽的家");
    expect(screen.queryByText("当前家庭")).toBeNull();
  });

  it("起了名：用名字（去掉首尾空白）", async () => {
    renderAddCompanion(home(" 海边的家 "));
    expect((await chip())?.textContent).toBe("海边的家");
  });
});

/* ---------------- 确认框标题的深色对比度（静态检查：读真样式表与真主题色，按 WCAG 算） ---------------- */

describe("迎接确认框的标题：深色下也看得清（字对底 ≥ 4.5）", () => {
  const read = (rel: string) => readFileSync(join(process.cwd(), rel), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  const pets = read("src/features/pets/pets.css");
  const tokens = read("src/shared/theme/tokens.css");
  /** 取出 @media (prefers-color-scheme: dark) 块的内容（按花括号配对）。 */
  const darkBlocks = (text: string) => {
    const out: string[] = [];
    let from = 0;
    for (;;) {
      const at = text.indexOf("@media (prefers-color-scheme: dark)", from);
      if (at < 0) return out;
      const open = text.indexOf("{", at);
      let depth = 0;
      let i = open;
      for (; i < text.length; i += 1) {
        if (text[i] === "{") depth += 1;
        else if (text[i] === "}" && (depth -= 1) === 0) break;
      }
      out.push(text.slice(open + 1, i));
      from = i + 1;
    }
  };
  const vars = (block: string) => Object.fromEntries([...block.matchAll(/(--[a-z0-9-]+):\s*(#[0-9a-f]{6})/gi)].map((m) => [m[1], m[2].toLowerCase()]));
  const light = vars(tokens.slice(0, tokens.indexOf("@media (prefers-color-scheme: dark)")));
  const dark = { ...light, ...vars(darkBlocks(tokens).join(" ")) };
  const tokenOf = (text: string, selector: string, prop: string) => {
    const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return text.match(new RegExp(String.raw`(?:^|[}\s])${escaped}\s*\{[^}]*?(?:^|[;\s])${prop}:\s*var\((--[a-z0-9-]+)\)`))?.[1] ?? null;
  };
  const luminance = (hex: string) => {
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const contrast = (a: string, b: string) => {
    const [x, y] = [luminance(a), luminance(b)].sort((m, n) => n - m);
    return (x + 0.05) / (y + 0.05);
  };

  it("前提：主题色读到了，底是 --c-leaf-soft；深墨色在深色下确实看不清（这条检查有牙齿）", () => {
    expect(tokenOf(pets, ".ps-adopt-confirm", "background")).toBe("--c-leaf-soft");
    expect(dark["--c-leaf-soft"]).toMatch(/^#/);
    expect(contrast(dark["--c-deep-ink"], dark["--c-leaf-soft"])).toBeLessThan(2);
  });

  it("浅色：标题（深墨色）对确认框底 ≥ 4.5", () => {
    const ink = tokenOf(pets, ".ps-adopt-confirm strong", "color");
    expect(ink).toBe("--c-deep-ink");
    expect(contrast(light[ink!], light["--c-leaf-soft"])).toBeGreaterThanOrEqual(4.5);
  });

  it("深色：样式表在深色块里把标题换成正文色，对确认框底 ≥ 4.5", () => {
    const ink = tokenOf(darkBlocks(pets).join(" "), ".ps-adopt-confirm strong", "color");
    expect(ink).toBe("--c-ink");
    expect(contrast(dark[ink!], dark["--c-leaf-soft"])).toBeGreaterThanOrEqual(4.5);
  });
});
