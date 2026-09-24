/**
 * 访客星球 /world 与居民公开主页（claude-6c2b 星球访客页分身，2026-09-24）。
 * 钉住：一进来就看到居民与后台事实（此刻、住在哪、梦想、最近的公开小事），没有地图、不产生坐标；
 * 没有公开照片时用同物种插画，演示小灰猫只在演示模式、只给猫；主要动作与登录入口；说人话。
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { HouseholdBrief, PetPresence, PetSpecies, Post, PublicPetView, PublicResident, PublicWorld, SessionState } from "@/shared/contracts";
import { PetSpeciesValues } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";

// 变异自检用：PLANET_CSS_DIR 可指向一份 pets 目录副本，默认读 src/features/pets。
const PLANET_CSS = resolve(process.env.PLANET_CSS_DIR ?? resolve(dirname(fileURLToPath(import.meta.url)), "..", "src", "features", "pets"), "planet.css");

const mocked = vi.hoisted(() => ({ env: { dataMode: "live" as "live" | "fixture", isDev: false, apiBase: "/api/v1/web" } }));
vi.mock("@/shared/config/env", () => mocked);

import { PublicPetPage, PublicWorldPage } from "@/features/pets/PublicWorldPage";
import { ResidentHome } from "@/features/pets/ResidentHome";
import { agoText, extraPosts, nowLine, portraitPhotoLabel, presenceGroup, presenceSummary, residentPortrait } from "@/features/pets/residentView";

/** 住在哪实际显示出来的文字（ResidentHome 渲染后的整段）。 */
function homeText(residence: string, city: string): string {
  const view = render(<ResidentHome resident={{ residence, city }} />);
  const text = view.container.textContent ?? "";
  view.unmount();
  return text;
}

afterEach(() => {
  cleanup();
  mocked.env.dataMode = "live";
});

const guest: SessionState = { authenticated: false, user: null, csrf_required: false, expires_at: null, onboarding: null };
const member: SessionState = {
  authenticated: true, user: { user_id: "u-1", username: "member", display_name: null, auth_method: "web_password" }, csrf_required: false, expires_at: null,
  onboarding: { step: "active", pet_id: "p-1", home_id: "h-1", reception_session_id: null, reception_skipped: false, home_activated_at: "2026-09-23T00:00:00Z", pet_origin: "own_pet" },
} as SessionState;

function post(id: string, text: string, author: string, at = "2026-09-24T02:00:00Z"): Post {
  return {
    post_id: id, author: { actor_kind: "pet", actor_id: `pet-${id}`, display_name: author, avatar_url: null, is_real_household: false }, text, media: [],
    source_event_id: `ev-${id}`, visit_id: null, visibility: "public", created_at: at, reaction_count: 0, comment_count: 0, viewer_reacted: false, data_origin: "live",
  } as Post;
}

function resident(overrides: Partial<PublicResident>): PublicResident {
  return {
    pet_id: "PJ-1", candidate_id: "c-1", name: "云朵", species: "rabbit", personality: "害羞、会给朋友留胡萝卜", dream: "去山顶看云海",
    origin: "adopted_original", source_note: "PetSoul 原创伙伴", residence: "星球居民驿站·西贡海边", city: "香港", living_since: "2026-09-23T19:20:00Z",
    presence: "at_home", doing: "在驿站休息", place_name: null, recent_posts: [], ...overrides,
  };
}

const RESIDENTS: PublicResident[] = [
  resident({ pet_id: "PJ-A", name: "栗子", species: "dog", personality: "热情、走路会蹦", dream: "想当一次小小飞行员", presence: "visiting", doing: "在家附近的星球小路", place_name: "家附近的星球小路", recent_posts: [post("p1", "在家附近的星球小路待了一会儿。", "栗子")] }),
  resident({ pet_id: "PJ-B", name: "花卷", species: "cat", personality: "外向、好奇", dream: "逛遍小市集", residence: "星球居民驿站·中环", presence: "in_transit", doing: "在去花店帮忙的路上" }),
  resident({ pet_id: "PJ-C", name: "云朵", species: "rabbit" }),
];

function world(overrides: Partial<PublicWorld> = {}): PublicWorld {
  return {
    server_time: "2026-09-24T05:00:00Z",
    entries: [
      { route: "browse", label: "先逛逛", needs_login: false, note: null },
      { route: "own_pet", label: "带我的宠物来", needs_login: true, note: null },
      { route: "adopt", label: "认识一位新伙伴", needs_login: true, note: null },
    ],
    residents: RESIDENTS,
    // p1 已经在栗子的卡片上出现过；p9 是别的公开宠物的小事
    recent_posts: [post("p1", "在家附近的星球小路待了一会儿。", "栗子"), post("p9", "今天在码头看了很久的船。", "海盐", "2026-09-24T04:30:00Z")],
    living_residents: RESIDENTS.length,
    cache_seconds: 30,
    data_origin: "live",
    ...overrides,
  };
}

/** 只给页面该用的服务；碰到别的（比如地图配置、底图）直接报错。 */
function renderAt(path: string, services: Partial<ServiceMap>) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const map = new Proxy(services as ServiceMap, {
    get(target, prop: string) {
      if (prop in target) return target[prop as keyof ServiceMap];
      throw new Error(`unexpected service ${prop}`);
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ServicesProvider services={map}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/world" element={<PublicWorldPage />} />
            <Route path="/world/residents/:petId" element={<PublicPetPage />} />
          </Routes>
        </MemoryRouter>
      </ServicesProvider>
    </QueryClientProvider>,
  );
}

function worldServices(data: PublicWorld, session: SessionState = guest): Partial<ServiceMap> {
  return {
    session: { current: async () => session } as unknown as ServiceMap["session"],
    pets: { publicWorld: async () => data } as unknown as ServiceMap["pets"],
  };
}

describe("展示规则：只把后台事实换成人话", () => {
  it("在哪只按 presence 分组，不从文字里猜", () => {
    const expected: Record<PetPresence, string> = { at_home: "home", visiting: "out", at_destination: "out", in_transit: "road", returning: "road", unknown: "unknown", not_activated: "unknown" };
    for (const [presence, group] of Object.entries(expected)) expect(presenceGroup(presence as PetPresence)).toBe(group);
    expect(presenceSummary(RESIDENTS).map((item) => item.text)).toEqual(["1 位在驿站", "1 位在外面", "1 位在路上"]);
    expect(presenceSummary([])).toEqual([]);
  });

  it("此刻那一行：地点名已在 doing 里就不重复；住在哪 = 驿站（城市），不再拼分隔点", () => {
    expect(nowLine({ doing: "在家附近的星球小路", place_name: "家附近的星球小路" })).toBe("在家附近的星球小路");
    expect(nowLine({ doing: "在店里坐着", place_name: "海边咖啡馆" })).toBe("在店里坐着（海边咖啡馆）");
    expect(nowLine({ doing: "在驿站休息", place_name: null })).toBe("在驿站休息");
    // 服务端的驿站名自己带“·”（U+00B7，隔离后端实测）；前端只加括号，同一行里只剩驿站名自带的那一个点
    expect(homeText("星球居民驿站·中环", "香港")).toBe("星球居民驿站·中环（香港）");
    expect(homeText("星球居民驿站·中环", "")).toBe("星球居民驿站·中环");
    expect(homeText("香港 星球居民驿站", "香港")).toBe("香港 星球居民驿站");
    const line = `${homeText("星球居民驿站·中环", "香港")}${nowLine({ doing: "在店里坐着", place_name: "星球邮局·分拣处" })}`;
    expect(line.match(/[·・•]/g)).toEqual(["·", "·"]);
  });

  it("相对时间以服务器时间为准", () => {
    const now = Date.parse("2026-09-24T05:00:00Z");
    expect(agoText("2026-09-24T04:59:40Z", now)).toBe("刚刚");
    expect(agoText("2026-09-24T04:30:00Z", now)).toBe("30 分钟前");
    expect(agoText("2026-09-24T02:00:00Z", now)).toBe("3 小时前");
    expect(agoText("2026-09-22T05:00:00Z", now)).toBe("2 天前");
    expect(agoText("不是时间", now)).toBe("");
  });

  it("星球上最近的小事去掉卡片上已经出现的那条", () => {
    expect(extraPosts(world().recent_posts, RESIDENTS).map((p) => p.post_id)).toEqual(["p9"]);
  });

  it("同一位作者一字不差的同一句话（不同时间记下的）也只出现一次", () => {
    // 实测隔离后端：秋秋在 05:18 与 02:18 各有一条“在家附近的星球小路待了一会儿……”，卡片上是新的那条
    const card = post("new", "在家附近的星球小路待了一会儿。", "栗子", "2026-09-24T04:50:00Z");
    const older = post("old", "在家附近的星球小路待了一会儿。", "栗子", "2026-09-24T02:00:00Z");
    const residents = [{ ...RESIDENTS[0], recent_posts: [card, older] }];
    const sameAuthor = { ...older, author: card.author };
    const other = post("o1", "今天在码头看了很久的船。", "海盐");
    const otherAgain = { ...post("o2", "今天在码头看了很久的船。", "海盐", "2026-09-24T01:00:00Z"), author: other.author };
    expect(extraPosts([card, sameAuthor, other, otherAgain], residents).map((p) => p.post_id)).toEqual(["o1"]);
  });
});

describe("头像：同物种插画，演示小灰猫只在演示模式、只给猫", () => {
  it("live：有公开照片用照片；没有照片一律同物种插画（猫也不用演示猫）", () => {
    expect(residentPortrait("dog", "/api/v1/web/public/media/pets/PJ-A/photo")).toEqual({ kind: "photo", src: "/api/v1/web/public/media/pets/PJ-A/photo", demo: false });
    for (const species of PetSpeciesValues) expect(residentPortrait(species, null)).toEqual({ kind: "species", species });
  });

  it("读屏怎么说照片：按来历分开——原创居民是“形象（AI 生成）”，其余是“照片”，演示猫是“演示照片”", () => {
    expect(portraitPhotoLabel("花卷", "adopted_original", false)).toBe("花卷的形象（AI 生成）");
    expect(portraitPhotoLabel("花卷", "adopted_real_archive", false)).toBe("花卷的照片");
    expect(portraitPhotoLabel("花卷", "own_pet", false)).toBe("花卷的照片");
    expect(portraitPhotoLabel("花卷", null, false)).toBe("花卷的照片");
    expect(portraitPhotoLabel("小岚", "adopted_original", true)).toBe("小岚（演示照片）");
  });

  it("演示模式：只有猫会用演示小灰猫，其余物种都是自己的插画", () => {
    mocked.env.dataMode = "fixture";
    for (const species of PetSpeciesValues) {
      const source = residentPortrait(species as PetSpecies, null);
      if (species === "cat") expect(source).toMatchObject({ kind: "photo", demo: true });
      else expect(source).toEqual({ kind: "species", species });
    }
  });
});

describe("/world：一进来就看到居民", () => {
  it("每位居民的名字、物种、性格、此刻、住在哪、梦想、最近的小事都在；认识 TA 进居民主页", async () => {
    renderAt("/world", worldServices(world()));
    expect(await screen.findByRole("heading", { level: 1, name: "此刻有 3 位居民在星球上生活" })).toBeTruthy();
    const cards = screen.getAllByTestId("resident-card");
    expect(cards).toHaveLength(3);
    // 读屏的标题层级：h1 页面 → h2 居民列表 → h3 每位居民
    expect(screen.getAllByRole("heading").map((h) => `${h.tagName}${h.textContent}`).slice(0, 4)).toEqual(["H1此刻有 3 位居民在星球上生活", "H2星球上的居民", "H3栗子", "H3花卷"]);
    expect(within(screen.getByRole("list", { name: "星球上的居民" })).getAllByTestId("resident-card")).toHaveLength(3);
    const dog = within(cards[0]);
    expect(dog.getByRole("heading", { level: 3 }).textContent).toBe("栗子");
    expect(cards[0].querySelector(".ps-world-resident__species")?.textContent).toBe("狗");
    expect(screen.getByRole("article", { name: "栗子" })).toBe(cards[0]);
    expect(cards[0].textContent).toContain("热情、走路会蹦");
    expect(cards[0].textContent).toContain("此刻在家附近的星球小路");
    expect(cards[0].textContent).toContain("住在星球居民驿站·西贡海边（香港）");
    // 320 宽时“（香港）”不能被拆成两行
    expect(cards[0].querySelector(".ps-world-nowrap")?.textContent).toBe("（香港）");
    expect(cards[0].textContent).toContain("梦想想当一次小小飞行员");
    expect(cards[0].textContent).toContain("在家附近的星球小路待了一会儿。");
    expect(cards[0].textContent).toContain("3 小时前");
    expect(dog.getByRole("link", { name: "认识 TA：栗子" }).getAttribute("href")).toBe("/world/residents/PJ-A");
    expect(within(cards[1]).getByRole("link", { name: "认识 TA：花卷" }).getAttribute("href")).toBe("/world/residents/PJ-B");
    expect(cards[1].textContent).toContain("此刻在去花店帮忙的路上");
    // 大家此刻在哪（只数 presence）
    expect(screen.getByRole("list", { name: "大家此刻在哪" }).textContent).toBe("1 位在驿站1 位在外面1 位在路上");
    // 卡片上出现过的小事不再重复；别的公开小事单独列出
    const posts = screen.getByRole("region", { name: "星球上最近的小事" });
    expect(posts.textContent).toContain("今天在码头看了很久的船。");
    expect(posts.textContent).not.toContain("在家附近的星球小路待了一会儿。");
  });

  it("居民卡用接口给的照片（avatar_url）：有就用照片；为空用同物种插画；照片打不开退回插画并标“插画”", async () => {
    const withPhotos = world({
      residents: [
        // 真实原型档案里的居民：真的照片
        { ...RESIDENTS[0], origin: "adopted_real_archive", avatar_url: "/api/v1/web/public/media/pets/PJ-A/photo" },
        // 原创居民：形象是生成的
        { ...RESIDENTS[1], origin: "adopted_original", avatar_url: "/api/v1/web/public/media/pets/PJ-B/photo" },
        { ...RESIDENTS[2], avatar_url: null },
      ],
    });
    renderAt("/world", worldServices(withPhotos));
    const cards = await screen.findAllByTestId("resident-card");
    const dog = within(cards[0]).getByRole("img", { name: "栗子的照片" });
    expect(dog.querySelector("img")?.getAttribute("src")).toBe("/api/v1/web/public/media/pets/PJ-A/photo");
    expect(dog.textContent).toBe("");
    // 原创居民读作“形象（AI 生成）”；画面上不加角标
    const generated = within(cards[1]).getByRole("img", { name: "花卷的形象（AI 生成）" });
    expect(generated.textContent).toBe("");
    // 花卷的照片打不开：退回猫的插画，标“插画”
    fireEvent.error(generated.querySelector("img")!);
    const fallback = within(cards[1]).getByRole("img", { name: "猫的插画，不是花卷本人的照片" });
    expect(fallback.querySelector("img")?.getAttribute("src")).toContain("species-cat.webp");
    expect(fallback.textContent).toBe("插画");
    // 云朵没有照片：兔子的插画
    expect(within(cards[2]).getByRole("img", { name: "兔子的插画，不是云朵本人的照片" }).textContent).toBe("插画");
  });

  it("没有公开照片：狗是狗的插画、兔子是兔子的插画，页面上没有演示猫", async () => {
    renderAt("/world", worldServices(world()));
    const cards = await screen.findAllByTestId("resident-card");
    const dogPortrait = within(cards[0]).getByRole("img", { name: "狗的插画，不是栗子本人的照片" });
    expect(dogPortrait.querySelector("img")?.getAttribute("src")).toContain("species-dog.webp");
    expect(within(cards[2]).getByRole("img", { name: "兔子的插画，不是云朵本人的照片" }).querySelector("img")?.getAttribute("src")).toContain("species-rabbit.webp");
    expect(dogPortrait.textContent).toBe("插画");
    const sources = [...document.querySelectorAll("img, image")].map((el) => el.getAttribute("src") ?? el.getAttribute("href") ?? "");
    expect(sources.some((src) => /demo-cat/.test(src))).toBe(false);
  });

  it("演示模式：猫可以用演示小灰猫，狗仍然是狗的插画", async () => {
    mocked.env.dataMode = "fixture";
    renderAt("/world", worldServices(world({ data_origin: "fixture" })));
    const cards = await screen.findAllByTestId("resident-card");
    expect(within(cards[0]).getByRole("img", { name: "狗的插画，不是栗子本人的照片" }).querySelector("img")?.getAttribute("src")).toContain("species-dog.webp");
    const cat = within(cards[1]).getByRole("img", { name: "花卷（演示照片）" });
    expect(cat.querySelector("img")?.getAttribute("src")).toMatch(/demo-cat/);
    expect(screen.getByText("演示居民")).toBeTruthy();
  });

  it("没有地图、不产生坐标：头图是装饰，只按物种画，最多 6 只", async () => {
    const many = Array.from({ length: 8 }, (_, i) => resident({ pet_id: `PJ-${i}`, name: `居民${i}`, species: PetSpeciesValues[i % PetSpeciesValues.length] }));
    renderAt("/world", worldServices(world({ residents: many, living_residents: 8, recent_posts: [] })));
    await screen.findAllByTestId("resident-card");
    const scene = screen.getByTestId("planet-scene");
    expect(scene.getAttribute("aria-hidden")).toBe("true");
    expect([...scene.querySelectorAll("[data-species]")].map((el) => el.getAttribute("data-species"))).toEqual(many.slice(0, 6).map((r) => r.species));
    expect(scene.textContent).toBe("");
    expect(document.querySelector("[data-testid='planet-map'], [data-testid='planet-pin'], .ps-map")).toBeNull();
  });

  it("访客：主要动作是寻找我的 TA（注册），另有已经有 TA 了？登录；不再有“看全部居民”", async () => {
    renderAt("/world", worldServices(world()));
    expect((await screen.findByRole("link", { name: "寻找我的 TA" })).getAttribute("href")).toBe("/register");
    expect(screen.getByRole("link", { name: "已经有 TA 了？登录" }).getAttribute("href")).toBe("/login");
    expect(screen.getByRole("link", { name: "返回" }).getAttribute("href")).toBe("/welcome");
    expect(screen.queryByRole("button", { name: /看全部居民/ })).toBeNull();
    expect(document.getElementById("residents")?.tagName).toBe("UL");
  });

  it("契约没给“带我的宠物来”入口时，不出现注册按钮；登录入口照旧", async () => {
    renderAt("/world", worldServices(world({ entries: [{ route: "browse", label: "先逛逛", needs_login: false, note: null }] })));
    expect(await screen.findByRole("link", { name: "已经有 TA 了？登录" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "寻找我的 TA" })).toBeNull();
  });

  it("已登录并已入住：回到我的家，不显示登录入口，也不显示写给访客的话", async () => {
    renderAt("/world", worldServices(world(), member));
    expect((await screen.findByRole("link", { name: "回到我的家" })).getAttribute("href")).toBe("/map");
    expect(screen.queryByRole("link", { name: "已经有 TA 了？登录" })).toBeNull();
    expect(screen.queryByRole("link", { name: "寻找我的 TA" })).toBeNull();
    expect(document.body.textContent).not.toMatch(/注册|登录/);
  });

  it("没有居民：如实说今天没有，不列空卡片", async () => {
    renderAt("/world", worldServices(world({ residents: [], living_residents: 0, recent_posts: [] })));
    expect(await screen.findByRole("heading", { level: 1, name: "今天暂时没有可认识的居民" })).toBeTruthy();
    expect(screen.queryAllByTestId("resident-card")).toHaveLength(0);
    expect(screen.getByText("居民们回来后，会出现在这里。")).toBeTruthy();
  });

  it("说人话：页面文字里除了 TA 没有英文词", async () => {
    renderAt("/world", worldServices(world()));
    await screen.findAllByTestId("resident-card");
    const words = (document.body.textContent ?? "").match(/[A-Za-z]{2,}/g) ?? [];
    expect(words.filter((word) => word !== "TA")).toEqual([]);
  });
});

describe("居民主页：和访客星球同一套样子，只写公开事实", () => {
  function view(species: PetSpecies, avatar: string | null, overrides: Partial<PublicPetView> = {}): PublicPetView {
    const r = resident({
      pet_id: "PJ-A", name: "栗子", species, personality: "热情、走路会蹦", dream: "想当一次小小飞行员", source_note: "原创星球居民",
      presence: "visiting", doing: "在家附近的星球小路", place_name: "家附近的星球小路",
    });
    return {
      profile: {
        pet_id: "PJ-A", display_name: "栗子", species, avatar_url: avatar, bio: "栗子对路边的新鲜事几乎都有兴趣，出门时常常因为一块新招牌停下很久。",
        origin_label: "PetSoul 原创伙伴", visibility: "public", follower_count: 0, post_count: 2, viewer_follows: false, is_own: false, data_origin: "live",
      },
      resident: r,
      adoptable: true,
      posts: [post("h1", "在家附近的星球小路待了一会儿。", "栗子", "2026-09-24T04:00:00Z"), post("h2", "今天认识了一只爱唱歌的小鸟。", "栗子", "2026-09-23T04:00:00Z")],
      ...overrides,
    };
  }

  function petServices(data: PublicPetView | (() => Promise<PublicPetView>), session: SessionState = guest): Partial<ServiceMap> {
    return {
      session: { current: async () => session } as unknown as ServiceMap["session"],
      pets: { publicPet: typeof data === "function" ? data : async () => data } as unknown as ServiceMap["pets"],
    };
  }

  /** 已登录时共用的“迎接 TA”自己读 /households，并在确认后调 pets.adopt。 */
  function signedInServices(data: PublicPetView, session: SessionState, homes: HouseholdBrief[], adopt = vi.fn((_candidateId: string, _key: string, _householdId?: string | null) => new Promise<never>(() => undefined))) {
    const list = vi.fn(async () => homes);
    const services: Partial<ServiceMap> = {
      session: { current: async () => session } as unknown as ServiceMap["session"],
      pets: { publicPet: async () => data, adopt } as unknown as ServiceMap["pets"],
      households: { list } as unknown as ServiceMap["households"],
    };
    return { services, list, adopt };
  }

  const seaside: HouseholdBrief = { household_id: "hh-1", name: "海边的家", home_id: "home-1", role: "admin", home_activated: true, member_count: 2, pets: [] };

  it("头部、此刻、住在哪、性格、梦想、最近的小事都在；标题层级 h1 → h2", async () => {
    renderAt("/world/residents/PJ-A", petServices(view("dog", null)));
    expect(await screen.findByRole("heading", { level: 1, name: "栗子" })).toBeTruthy();
    expect(document.querySelector(".ps-resident-page__head .ps-world-resident__species")?.textContent).toBe("狗");
    expect(screen.getByText("来自：原创星球居民")).toBeTruthy();
    expect(screen.getAllByRole("heading").map((h) => `${h.tagName}${h.textContent}`)).toEqual(["H1栗子", "H2此刻", "H2TA 的性格", "H2TA 的梦想", "H2TA 最近的小事"]);
    const now = screen.getByRole("region", { name: "此刻" });
    expect(now.textContent).toBe("此刻在家附近的星球小路住在星球居民驿站·西贡海边（香港）");
    expect(now.className).toContain("is-out");
    expect(now.querySelector(".ps-world-nowrap")?.textContent).toBe("（香港）");
    const trait = screen.getByRole("region", { name: "TA 的性格" });
    expect(trait.textContent).toContain("热情、走路会蹦");
    expect(trait.textContent).toContain("出门时常常因为一块新招牌停下很久");
    expect(screen.getByRole("region", { name: "TA 的梦想" }).textContent).toContain("想当一次小小飞行员");
    const posts = within(screen.getByRole("region", { name: "TA 最近的小事" })).getAllByRole("listitem");
    expect(posts.map((li) => li.querySelector("p")?.textContent)).toEqual(["在家附近的星球小路待了一会儿。", "今天认识了一只爱唱歌的小鸟。"]);
    expect(posts[0].querySelector("small")?.textContent).toMatch(/前$|^刚刚$/);
    expect(screen.getByRole("link", { name: "再看看其他居民" }).getAttribute("href")).toBe("/world");
    expect(screen.getByRole("link", { name: "返回" }).getAttribute("href")).toBe("/world");
  });

  it("性格和简介一样时只写一遍；来自哪里未知就不写", async () => {
    const same = view("rabbit", null);
    same.profile = { ...same.profile, bio: "热情、走路会蹦", origin_label: null };
    same.resident = { ...same.resident!, source_note: null };
    renderAt("/world/residents/PJ-A", petServices(same));
    const trait = await screen.findByRole("region", { name: "TA 的性格" });
    expect(within(trait).getAllByText("热情、走路会蹦")).toHaveLength(1);
    expect(document.querySelector(".ps-resident-page__source")).toBeNull();
    expect(document.body.textContent).not.toContain("来自");
  });

  it("访客、可以领养：领养这一位（注册时带上想领养谁），登录也带上；说清楚不会自动领养", async () => {
    renderAt("/world/residents/PJ-A", petServices(view("dog", null)));
    expect((await screen.findByRole("link", { name: "领养 栗子" })).getAttribute("href")).toBe("/register?entry=adopt&pet_id=PJ-A");
    expect(screen.getByRole("link", { name: "已经有账号？登录后继续" }).getAttribute("href")).toBe("/login?entry=adopt&pet_id=PJ-A");
    expect(screen.getByText(/注册后由你确认才领养，不会自动领养/)).toBeTruthy();
    expect(screen.queryByRole("link", { name: "回到我的家" })).toBeNull();
  });

  it("访客、不能领养（公开主页的家养宠物）：和访客星球一样是寻找我的 TA 与登录；没有此刻和梦想", async () => {
    renderAt("/world/residents/PJ-A", petServices(view("cat", null, { resident: null, adoptable: false })));
    expect((await screen.findByRole("link", { name: "寻找我的 TA" })).getAttribute("href")).toBe("/register");
    expect(screen.getByRole("link", { name: "已经有 TA 了？登录" }).getAttribute("href")).toBe("/login");
    expect(screen.getByText("TA 暂时不能被领养。")).toBeTruthy();
    expect(screen.queryByRole("region", { name: "此刻" })).toBeNull();
    expect(screen.queryByRole("region", { name: "TA 的梦想" })).toBeNull();
    expect(screen.getByRole("region", { name: "关于 TA" }).textContent).toContain("出门时常常因为一块新招牌停下很久");
    expect(screen.getByText("来自：PetSoul 原创伙伴")).toBeTruthy();
  });

  it("已登录、已入住、TA 可以领养：出现迎接按钮（迎进自己的家）；两个出口还在；不显示写给访客的话，也不写“接入中 / 暂时不能”", async () => {
    // 主窗口巡检 P1（2026-09-24）：旧主页登录后只剩一行“仍在接入中”，还留着写给访客的“登录后仍由你确认”
    const { services, list, adopt } = signedInServices(view("dog", null), member, [seaside]);
    renderAt("/world/residents/PJ-A", services);
    const welcome = await screen.findByRole("button", { name: "迎接 TA 到海边的家：栗子" });
    expect((welcome as HTMLButtonElement).disabled).toBe(false);
    expect(list).toHaveBeenCalled();
    expect(screen.getByRole("link", { name: "回到我的家" }).getAttribute("href")).toBe("/map");
    expect(screen.getByRole("link", { name: "再看看其他居民" }).getAttribute("href")).toBe("/world");
    expect(screen.queryByRole("link", { name: /领养|登录|寻找我的 TA/ })).toBeNull();
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/注册|登录|接入中|暂时还不能|暂时不能/);
    expect(document.querySelector(".ps-resident-page__note")).toBeNull();
    // 点一下只打开确认，不会直接领养
    fireEvent.click(welcome);
    expect(screen.getByRole("group", { name: "确认领养 栗子" })).toBeTruthy();
    expect(adopt).not.toHaveBeenCalled();
  });

  it("已登录、TA 不能领养：没有迎接按钮，也不去读家庭列表；只留回到我的家和再看看其他居民两个出口", async () => {
    const { services, list } = signedInServices(view("cat", null, { resident: null, adoptable: false }), member, [seaside]);
    renderAt("/world/residents/PJ-A", services);
    expect((await screen.findByRole("link", { name: "回到我的家" })).getAttribute("href")).toBe("/map");
    expect(screen.getByRole("link", { name: "再看看其他居民" }).getAttribute("href")).toBe("/world");
    expect(screen.queryByRole("button", { name: /迎接 TA/ })).toBeNull();
    expect(list).not.toHaveBeenCalled();
    expect(within(document.querySelector("footer.ps-world-cta") as HTMLElement).getAllByRole("link").map((a) => a.textContent)).toEqual(["回到我的家"]);
    cleanup();
    // 居民资料还在、但此刻不能领养（例如刚被别人领走）：同样不给迎接按钮
    const taken = signedInServices(view("dog", null, { adoptable: false }), member, [seaside]);
    renderAt("/world/residents/PJ-A", taken.services);
    expect(await screen.findByRole("link", { name: "回到我的家" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /迎接 TA/ })).toBeNull();
    expect(taken.list).not.toHaveBeenCalled();
  });

  it("已登录还没有伙伴、没有家：迎接 TA（新建家庭）；确认之后才用这位居民的候选编号领养；出口是继续寻找我的 TA", async () => {
    const newcomer = { ...member, onboarding: { ...member.onboarding!, step: "needs_companion" as const, pet_id: null, home_id: null } } as SessionState;
    const { services, adopt } = signedInServices(view("dog", null), newcomer, []);
    renderAt("/world/residents/PJ-A", services);
    // 家庭列表读回来之前按钮是灰的（名字一样），等它能点再点
    await waitFor(() => expect((screen.getByRole("button", { name: "迎接 TA：栗子" }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "迎接 TA：栗子" }));
    expect(adopt).not.toHaveBeenCalled();
    fireEvent.click(within(screen.getByRole("group", { name: "确认领养 栗子" })).getByRole("button", { name: "确认领养" }));
    await waitFor(() => expect(adopt).toHaveBeenCalledTimes(1));
    expect(adopt.mock.calls[0][0]).toBe("c-1");
    expect(adopt.mock.calls[0][2]).toBeNull();
    expect(screen.getByRole("link", { name: "继续寻找我的 TA" }).getAttribute("href")).toBe("/onboarding");
  });

  it("还没有公开的小事：如实说没有，不编", async () => {
    renderAt("/world/residents/PJ-A", petServices(view("dog", null, { posts: [] })));
    expect(await screen.findByText("TA 还没有公开的小事。")).toBeTruthy();
  });

  it("找不到（404）：说清楚没有找到，可以回星球看看；访客行动区照常", async () => {
    renderAt("/world/residents/PJ-X", petServices(async () => { throw new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: "没有找到这只宠物的公开主页。" }); }));
    expect(await screen.findByRole("heading", { level: 1, name: "没有找到这位居民的公开主页" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "再看看其他居民" }).getAttribute("href")).toBe("/world");
    expect(screen.getByRole("link", { name: "寻找我的 TA" }).getAttribute("href")).toBe("/register");
  });

  it("说人话：页面文字里除了 TA 没有英文词", async () => {
    renderAt("/world/residents/PJ-A", petServices(view("dog", null)));
    await screen.findByRole("heading", { level: 1, name: "栗子" });
    const words = (document.body.textContent ?? "").match(/[A-Za-z]{2,}/g) ?? [];
    // “PetSoul 原创伙伴”是服务端给的来历原文，照原样显示
    expect(words.filter((word) => word !== "TA" && word !== "PetSoul")).toEqual([]);
  });

  it("演示模式里的狗没有照片：显示狗的插画，不是演示猫", async () => {
    mocked.env.dataMode = "fixture";
    renderAt("/world/residents/PJ-A", petServices(view("dog", null)));
    const portrait = await screen.findByRole("img", { name: "狗的插画，不是栗子本人的照片" });
    expect(portrait.querySelector("img")?.getAttribute("src")).toContain("species-dog.webp");
  });

  it("照片打不开：退回同物种插画并标“插画”；主页没给照片时用居民自己的 avatar_url", async () => {
    renderAt("/world/residents/PJ-A", petServices(view("dog", "/api/v1/web/public/media/pets/PJ-A/photo")));
    fireEvent.error((await screen.findByRole("img", { name: "栗子的形象（AI 生成）" })).querySelector("img")!);
    expect(screen.getByRole("img", { name: "狗的插画，不是栗子本人的照片" }).textContent).toBe("插画");
    cleanup();
    const fromResident = view("dog", null);
    fromResident.resident = { ...fromResident.resident!, avatar_url: "/api/v1/web/public/media/pets/PJ-A/photo" };
    renderAt("/world/residents/PJ-A", petServices(fromResident));
    expect((await screen.findByRole("img", { name: "栗子的形象（AI 生成）" })).querySelector("img")?.getAttribute("src")).toBe("/api/v1/web/public/media/pets/PJ-A/photo");
  });

  it("有公开照片就用：原创居民读作“形象（AI 生成）”，真实原型读作“照片”，不是居民（没有来历）按照片读；画面上都不加角标", async () => {
    const url = "/api/v1/web/public/media/pets/PJ-A/photo";
    renderAt("/world/residents/PJ-A", petServices(view("dog", url)));
    const original = await screen.findByRole("img", { name: "栗子的形象（AI 生成）" });
    expect(original.querySelector("img")?.getAttribute("src")).toBe(url);
    expect(original.textContent).toBe("");
    cleanup();
    const archive = view("dog", url);
    archive.resident = { ...archive.resident!, origin: "adopted_real_archive" };
    renderAt("/world/residents/PJ-A", petServices(archive));
    expect((await screen.findByRole("img", { name: "栗子的照片" })).textContent).toBe("");
    cleanup();
    renderAt("/world/residents/PJ-A", petServices(view("dog", url, { resident: null, adoptable: false })));
    expect((await screen.findByRole("img", { name: "栗子的照片" })).querySelector("img")?.getAttribute("src")).toBe(url);
  });
});

describe("样式：深浅两套都来自主题令牌", () => {
  it("共用的“迎接 TA”放进行动区：主按钮叶绿色；确认框标题用正文色（深色下不再深墨字压深绿底）", () => {
    const css = readFileSync(PLANET_CSS, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
    expect(css).toMatch(/\.ps-world-cta \.ps-btn--primary \{[^}]*background: var\(--c-leaf\);/);
    expect(css).toMatch(/\.ps-world-cta \.ps-adopt-confirm strong \{[^}]*color: var\(--c-ink\);/);
  });

  it("planet.css（访客星球与居民主页）去掉注释后不含任何写死的颜色", () => {
    const css = readFileSync(PLANET_CSS, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
    expect(css).toContain(".ps-resident-page__now");
    expect(css.match(/#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\(|(?<![\w-])(?:white|black)(?![\w-])/g) ?? []).toEqual([]);
  });
});
