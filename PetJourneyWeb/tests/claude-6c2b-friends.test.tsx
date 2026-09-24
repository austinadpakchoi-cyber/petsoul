/**
 * claude-6c2b（分身五）· 通讯器 · TA 的朋友（玩家端方案 4.1“关系不是位置”、7.1 通讯器）：
 * - 每个朋友：头像（PetPortrait，不写名字首字）、名字、宠物还是星球居民（居民明确标注）、见过几次、熟悉程度、
 *   “最近在某地见过”（没有地点就不写）；
 * - 熟悉程度按后端真实取值（初识 / 熟人 / 好朋友）映射，不认识的取值用中性的“朋友”兜底，原始值不出现在页面上；
 * - 文案只说“见过”：朋友分区里任何地方都不出现“此刻在”“正在”；
 * - 排序：见面次数多的在前，同次数按熟悉程度，再按最近一次见面；
 * - 能链的才链：宠物朋友 → /pets/:id（编号做 URL 编码）；星球居民只展示信息，没有链接、没有箭头；
 * - 空列表一句温和的话；请求失败可重试；演示（fixture）模式服务报“能力未接入”时不崩、不编朋友、不露能力代码；
 * - 通讯器顶上一排：我和 TA / 家庭来信 / TA 的朋友 三个分区 + “朋友圈”入口（/circle）同一层级；
 *   切分区只改 ?channel=，切回“我和 TA”去掉参数；直接打开朋友分区时一次消息都不请求（消息查询在朋友分区关闭，
 *   所以也不轮询——轮询这一半靠查询关闭的语义，本文件没有推时钟单独测）。
 * - 通讯器样式（含聊天部分）只用主题变量：communicator.css 去掉注释后没有写死的颜色，改过的几条聊天样式确实在用令牌。
 * - 朋友圈（/circle，原“星球”标签退役后的去处）：标题叫“朋友圈”，页面上不再出现“星球圈”；左上角返回回到
 *   /communicator?channel=friends；指星球世界的“星球居民”标签保留。
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, MemoryRouter, Route, RouterProvider, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FriendSummary, HomeSnapshot, HouseholdBrief, MessageThread } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { createApiClient } from "@/shared/api/client";
import { loadFeatureModules } from "@/app/modules";
import { buildRoutes } from "@/app/router";
import { buildServices, ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { HouseholdProvider } from "@/shared/session/householdContext";
import { fixtureHomeSnapshot } from "@/fixtures/home";
import communicatorModule from "@/features/communicator/module";
import { closenessOf, friendProfileHref, lastSeenText, meetCountText, sortFriends, speciesLabel } from "@/features/communicator/friends";

// 同一个文件里要切 fixture / live：env 用 getter 读一个可改的开关（页面与头像都在渲染时才读 env.dataMode）。
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

const PET_ID = "pet-mine";
const PET_NAME = "栗子";
const NOW_WORDS = /此刻在|正在/;

const friend = (over: Partial<FriendSummary> & Pick<FriendSummary, "friend_id" | "name">): FriendSummary => ({
  kind: "pet",
  species: "cat",
  meet_count: 1,
  closeness: "初识",
  first_met_at: "2026-09-20T08:00:00Z",
  last_met_at: "2026-09-22T08:00:00Z",
  last_place: "白鹭洲公园",
  ...over,
});

/** 接口原样的顺序（后端按最近一次见面倒序给）：故意和应显示的顺序不同。 */
const FRIENDS: FriendSummary[] = [
  friend({ friend_id: "pet-newbie", name: "豆包", species: "dog", meet_count: 1, closeness: "初识", last_place: "海边咖啡馆", last_met_at: "2026-09-23T09:00:00Z" }),
  friend({ friend_id: "npc:parrot_lu", name: "鹦鹉阿绿", kind: "resident", species: null, meet_count: 2, closeness: "熟人", last_place: "海边咖啡馆", last_met_at: "2026-09-22T09:00:00Z" }),
  friend({ friend_id: "pet-mystery", name: "团子", species: "sloth", meet_count: 3, closeness: "close_friend", last_place: null, last_met_at: "2026-09-21T09:00:00Z" }),
  friend({ friend_id: "pet a/1", name: "奶茶", species: "cat", meet_count: 5, closeness: "好朋友", last_place: "白鹭洲公园", last_met_at: "2026-09-20T09:00:00Z" }),
];
const EXPECTED_ORDER = ["奶茶", "团子", "鹦鹉阿绿", "豆包"];

function household(): HouseholdBrief {
  return {
    household_id: "house-1",
    name: "海边的家",
    home_id: "home-1",
    role: "admin",
    home_activated: true,
    member_count: 2,
    pets: [{ pet_id: PET_ID, name: PET_NAME, species: "cat", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-20T00:00:00Z", added_by_you: true }],
  };
}

function home(): HomeSnapshot {
  const base = fixtureHomeSnapshot();
  return { ...base, data_origin: "live", pet: { ...base.pet, pet_id: PET_ID, name: PET_NAME, photo_url: null } };
}

const emptyThread = (): MessageThread => ({ pet_id: PET_ID, items: [], next_cursor: null, data_origin: "live" });

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
  return <output data-testid="location">{`${location.pathname}${location.search}`}</output>;
}

const communicatorRoute = communicatorModule.routes?.find((route) => route.path === "communicator")?.element;

/** live：经通讯器模块自己注册的路由元素渲染，外面套与应用相同的家庭上下文。 */
function renderCommunicator(friends: (petId: string, signal?: AbortSignal) => Promise<FriendSummary[]>, entry = "/communicator?channel=friends") {
  const thread = vi.fn(async () => emptyThread());
  const friendsSpy = vi.fn(friends);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider
        services={strictServices({
          households: { list: async () => [household()] },
          world: { home: async () => home() },
          social: { friends: friendsSpy },
          communicator: { thread, send: vi.fn() },
          transport: { guides: async () => [] },
          economy: { collection: async () => [] },
        })}
      >
        <MemoryRouter initialEntries={[entry]}>
          <HouseholdProvider userId="owner-1">
            <Routes>
              <Route path="/communicator" element={communicatorRoute} />
              <Route path="*" element={null} />
            </Routes>
            <LocationProbe />
          </HouseholdProvider>
        </MemoryRouter>
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return { thread, friends: friendsSpy };
}

const friendList = () => screen.findByRole("list", { name: "TA 的朋友" });

/** 每张朋友卡片：li 自己（居民）或 li 里的链接（宠物）就是卡片。 */
function cards(list: HTMLElement): HTMLElement[] {
  return within(list)
    .getAllByRole("listitem")
    .map((item) => (item.querySelector<HTMLElement>(".ps-friend") ?? item));
}

function cardOf(list: HTMLElement, name: string): HTMLElement {
  const card = cards(list).find((c) => c.querySelector(".ps-friend__name")?.textContent === name);
  if (!card) throw new Error(`找不到 ${name} 的卡片`);
  return card;
}

/* ---------------- 纯函数 ---------------- */

describe("朋友的文字：按真实取值映射，不认识的兜底", () => {
  it("熟悉程度：后端的三个取值原样映射（前后空白不影响）；不认识的一律中性“朋友”，不回显原始值", () => {
    expect(closenessOf("初识")).toMatchObject({ label: "初识", tone: "new" });
    expect(closenessOf("熟人")).toMatchObject({ label: "熟人", tone: "familiar" });
    expect(closenessOf("好朋友")).toMatchObject({ label: "好朋友", tone: "close" });
    expect(closenessOf(" 好朋友 ")).toMatchObject({ label: "好朋友", tone: "close" });
    for (const raw of ["close_friend", "挚友", "", "   ", "constructor", "__proto__", "toString", null, undefined]) {
      const shown = closenessOf(raw);
      expect(shown).toMatchObject({ label: "朋友", tone: "unknown", rank: 0 });
      if (raw) expect(shown.label).not.toBe(raw);
    }
    expect(closenessOf("好朋友").rank).toBeGreaterThan(closenessOf("熟人").rank);
    expect(closenessOf("熟人").rank).toBeGreaterThan(closenessOf("初识").rank);
    expect(closenessOf("初识").rank).toBeGreaterThan(closenessOf("close_friend").rank);
  });

  it("物种：认识的写中文名，不认识的代码不显示", () => {
    expect(speciesLabel("cat")).toBe("猫");
    expect(speciesLabel("dog")).toBe("狗");
    expect(speciesLabel("other")).toBe("小动物");
    expect(speciesLabel("sloth")).toBeNull();
    expect(speciesLabel("constructor")).toBeNull();
    expect(speciesLabel(null)).toBeNull();
  });

  it("见过几次：有效次数才写；读不出来不写“见过 0 次”", () => {
    expect(meetCountText(1)).toBe("见过 1 次");
    expect(meetCountText(5)).toBe("见过 5 次");
    expect(meetCountText(2.7)).toBe("见过 2 次");
    expect(meetCountText(0)).toBeNull();
    expect(meetCountText(Number.NaN)).toBeNull();
    expect(meetCountText(Number.POSITIVE_INFINITY)).toBeNull();
  });

  it("“最近在某地见过”：只说见过，不说此刻在哪；没有地点就不写", () => {
    expect(lastSeenText("白鹭洲公园")).toBe("最近在白鹭洲公园见过");
    expect(lastSeenText("  海边咖啡馆 ")).toBe("最近在海边咖啡馆见过");
    expect(lastSeenText("白鹭洲公园")).not.toMatch(NOW_WORDS);
    for (const none of [null, undefined, "", "   "]) expect(lastSeenText(none)).toBeNull();
  });

  it("能链的才链：宠物朋友 → /pets/:id（编码）；星球居民、不认识的 kind、空编号都不给链接", () => {
    expect(friendProfileHref({ kind: "pet", friend_id: "pet-newbie" })).toBe("/pets/pet-newbie");
    expect(friendProfileHref({ kind: "pet", friend_id: "pet a/1" })).toBe("/pets/pet%20a%2F1");
    expect(friendProfileHref({ kind: "resident", friend_id: "npc:parrot_lu" })).toBeNull();
    expect(friendProfileHref({ kind: "visitor" as unknown as FriendSummary["kind"], friend_id: "x-1" })).toBeNull();
    expect(friendProfileHref({ kind: "pet", friend_id: "" })).toBeNull();
  });

  it("排序：见面次数多的在前；同次数按熟悉程度，再按最近一次见面，再按名字；不改动传入的数组", () => {
    const input = [...FRIENDS];
    expect(sortFriends(input).map((f) => f.name)).toEqual(EXPECTED_ORDER);
    expect(input).toEqual(FRIENDS);
    // 不认识的熟悉程度不会被排到最后：团子见了 3 次，排在只见过 2 次的熟人前面（上面已断言）。
    const tie = [
      friend({ friend_id: "a", name: "阿一", meet_count: 3, closeness: "熟人", last_met_at: "2026-09-23T00:00:00Z" }),
      friend({ friend_id: "b", name: "阿二", meet_count: 3, closeness: "好朋友", last_met_at: "2026-09-01T00:00:00Z" }),
      friend({ friend_id: "c", name: "阿三", meet_count: 3, closeness: "熟人", last_met_at: "2026-09-24T00:00:00Z" }),
      friend({ friend_id: "d", name: "阿四", meet_count: 3, closeness: "熟人", last_met_at: "2026-09-24T00:00:00Z" }),
    ];
    // 同次数：好朋友（b）在前；同为熟人：最近一次见面更早的（a）在后；c、d 同一时刻见面，按名字“阿三”“阿四”定序。
    expect(sortFriends(tie).map((f) => f.friend_id)).toEqual(["b", "c", "d", "a"]);
    expect(sortFriends([...tie].reverse()).map((f) => f.friend_id)).toEqual(["b", "c", "d", "a"]);
  });
});

/* ---------------- 页面（live） ---------------- */

describe("TA 的朋友：列表", () => {
  it("逐项显示：名字、宠物还是居民、见过几次、熟悉程度、最近在哪见过；按当前宠物请求；排序与字段都对；不请求消息", async () => {
    const { friends, thread } = renderCommunicator(async () => FRIENDS);
    const list = await friendList();
    expect(friends).toHaveBeenCalledTimes(1);
    expect(friends.mock.calls[0][0]).toBe(PET_ID);
    expect(await screen.findByText(`${PET_NAME} 的朋友`)).toBeTruthy(); // 家园已读到（消息请求若没关，此刻已经发出）
    expect(thread).not.toHaveBeenCalled();
    expect(cards(list).map((c) => c.querySelector(".ps-friend__name")?.textContent)).toEqual(EXPECTED_ORDER);

    const naicha = cardOf(list, "奶茶");
    expect(naicha.textContent).toContain("好朋友");
    expect(naicha.textContent).toContain("宠物 · 猫 · 见过 5 次");
    expect(naicha.textContent).toContain("最近在白鹭洲公园见过");

    const tuanzi = cardOf(list, "团子");
    expect(tuanzi.textContent).toContain("宠物 · 见过 3 次");
    expect(tuanzi.textContent).not.toContain("最近在");

    const parrot = cardOf(list, "鹦鹉阿绿");
    expect(parrot.textContent).toContain("熟人");
    expect(parrot.textContent).toContain("见过 2 次");
    expect(parrot.textContent).toContain("最近在海边咖啡馆见过");

    const doubao = cardOf(list, "豆包");
    expect(doubao.textContent).toContain("初识");
    expect(doubao.textContent).toContain("宠物 · 狗 · 见过 1 次");
    expect(doubao.textContent).toContain("最近在海边咖啡馆见过");
  });

  it("星球居民明确标注，并有一句说明；列表里没有居民时不出现这句说明", async () => {
    renderCommunicator(async () => FRIENDS);
    const list = await friendList();
    const parrot = cardOf(list, "鹦鹉阿绿");
    expect(within(parrot).getByText("星球居民")).toBeTruthy();
    expect(parrot.textContent).not.toContain("宠物");
    for (const name of ["奶茶", "团子", "豆包"]) expect(cardOf(list, name).textContent).not.toContain("星球居民");
    expect(screen.getByText("标着“星球居民”的，是一直住在这颗星球上的居民，不是别人家的宠物。")).toBeTruthy();

    cleanup();
    renderCommunicator(async () => FRIENDS.filter((f) => f.kind === "pet"));
    await friendList();
    expect(screen.queryByText(/星球居民/)).toBeNull();
  });

  it("文案只说“见过”：朋友分区与整页都不出现“此刻在”“正在”", async () => {
    renderCommunicator(async () => FRIENDS);
    const list = await friendList();
    expect(list.textContent).toMatch(/最近在.+见过/);
    expect(list.textContent).not.toMatch(NOW_WORDS);
    expect(document.body.textContent).not.toMatch(NOW_WORDS);
  });

  it("不认识的熟悉程度取值显示中性的“朋友”，原始值、不认识的物种代码都不出现在页面上", async () => {
    renderCommunicator(async () => FRIENDS);
    const list = await friendList();
    const tuanzi = cardOf(list, "团子");
    expect(within(tuanzi).getByText("朋友")).toBeTruthy();
    expect(document.body.textContent).not.toContain("close_friend");
    expect(document.body.textContent).not.toContain("sloth");
    expect(document.body.textContent).not.toContain("npc:");
  });

  it("头像是 TA 自己的样子（PetPortrait）：没有照片时是爪印，不写名字首字", async () => {
    renderCommunicator(async () => FRIENDS);
    const list = await friendList();
    for (const name of EXPECTED_ORDER) {
      const portrait = within(cardOf(list, name)).getByRole("img", { name });
      expect(portrait.classList.contains("ps-pet-portrait")).toBe(true);
      expect(portrait.querySelector("svg")).toBeTruthy(); // live 没照片：中性爪印
      expect(portrait.querySelector("img")).toBeNull(); // 不借演示猫
      expect(portrait.textContent).toBe(""); // 不写首字
      expect(within(list).queryByText(name.slice(0, 1), { exact: true })).toBeNull();
    }
  });

  it("能链的才链：宠物朋友链到 /pets/:id（编号编码）；居民没有链接也没有箭头", async () => {
    renderCommunicator(async () => FRIENDS);
    const list = await friendList();
    const links = within(list).getAllByRole("link");
    expect(links.map((a) => a.getAttribute("href"))).toEqual(["/pets/pet%20a%2F1", "/pets/pet-mystery", "/pets/pet-newbie"]);
    expect(links[0].getAttribute("aria-label")).toBe("奶茶的主页：好朋友，宠物 · 猫 · 见过 5 次，最近在白鹭洲公园见过");
    for (const link of links) expect(link.querySelector(".ps-friend__go")).toBeTruthy();

    const parrot = cardOf(list, "鹦鹉阿绿");
    expect(parrot.tagName).toBe("LI");
    expect(parrot.closest("a")).toBeNull();
    expect(parrot.querySelector("a")).toBeNull();
    expect(parrot.querySelector(".ps-friend__go")).toBeNull();
    expect(parrot.classList.contains("ps-friend--link")).toBe(false);
    expect(within(parrot).queryByRole("button")).toBeNull();

    fireEvent.click(links[2]);
    expect(screen.getByTestId("location").textContent).toBe("/pets/pet-newbie");
  });

  it("空列表：一句温和的“TA 还没在外面遇到朋友”", async () => {
    renderCommunicator(async () => []);
    expect(await screen.findByText("TA 还没在外面遇到朋友")).toBeTruthy();
    expect(screen.queryByRole("list", { name: "TA 的朋友" })).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(document.body.textContent).not.toMatch(NOW_WORDS);
  });

  it("请求失败：给可重试的错误态，点“重试”再请求一次，成功后显示列表", async () => {
    let calls = 0;
    const { friends } = renderCommunicator(async () => {
      calls += 1;
      if (calls === 1) throw new ApiError({ kind: "network", code: "NETWORK_ERROR", message: "网络连接失败", retryable: true });
      return FRIENDS;
    });
    const alert = await screen.findByRole("alert");
    fireEvent.click(within(alert).getByRole("button", { name: "重试" }));
    const list = await friendList();
    expect(friends).toHaveBeenCalledTimes(2);
    expect(cards(list)).toHaveLength(FRIENDS.length);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("服务端说不能重试的错误也给“重试”（朋友分区自己的错误态）", async () => {
    renderCommunicator(async () => {
      throw new ApiError({ kind: "http", status: 500, code: "INTERNAL_ERROR", message: "朋友记录暂时读不出来", retryable: false });
    });
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByRole("button", { name: "重试" })).toBeTruthy();
  });

  it("live 下能力未接入：温和说明，不露能力代码、不编朋友", async () => {
    renderCommunicator(async () => {
      throw ApiError.capability("social.friends", "这项能力尚未接入。");
    });
    expect(await screen.findByText("暂时看不到 TA 的朋友")).toBeTruthy();
    expect(screen.queryByRole("list", { name: "TA 的朋友" })).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(document.body.textContent).not.toMatch(/social\.friends|CAPABILITY|能力|接入/);
  });
});

/* ---------------- 通讯器顶上的一排 ---------------- */

describe("通讯器顶上的一排：三个分区 + 朋友圈入口", () => {
  it("TA 的朋友与朋友圈同一层级；朋友圈是去 /circle 的链接（不是分区按钮）", async () => {
    renderCommunicator(async () => FRIENDS, "/communicator");
    const group = await screen.findByRole("group", { name: "通讯器分区" });
    expect(within(group).getAllByRole("button").map((b) => b.textContent)).toEqual(["我和 TA", "家庭来信", "TA 的朋友"]);
    const circle = within(group).getByRole("link", { name: "朋友圈" });
    expect(circle.getAttribute("href")).toBe("/circle");
    expect(circle.hasAttribute("aria-pressed")).toBe(false);
    fireEvent.click(circle);
    expect(screen.getByTestId("location").textContent).toBe("/circle");
  });

  it("切到“TA 的朋友”只改 ?channel=friends，不再请求消息、输入框收起；切回“我和 TA”去掉参数、恢复消息与输入框", async () => {
    const { thread, friends } = renderCommunicator(async () => FRIENDS, "/communicator");
    const group = await screen.findByRole("group", { name: "通讯器分区" });
    expect(await screen.findByRole("textbox", { name: "消息内容" })).toBeTruthy();
    await waitFor(() => expect(thread).toHaveBeenCalledTimes(1));
    expect(friends).not.toHaveBeenCalled();

    fireEvent.click(within(group).getByRole("button", { name: "TA 的朋友" }));
    expect(screen.getByTestId("location").textContent).toBe("/communicator?channel=friends");
    await friendList();
    expect(within(group).getByRole("button", { name: "TA 的朋友" }).getAttribute("aria-pressed")).toBe("true");
    expect(within(group).getByRole("button", { name: "我和 TA" }).getAttribute("aria-pressed")).toBe("false");
    expect(screen.queryByRole("textbox", { name: "消息内容" })).toBeNull();
    expect(thread).toHaveBeenCalledTimes(1);

    fireEvent.click(within(group).getByRole("button", { name: "我和 TA" }));
    expect(screen.getByTestId("location").textContent).toBe("/communicator");
    expect(await screen.findByRole("textbox", { name: "消息内容" })).toBeTruthy();
    expect(screen.queryByRole("list", { name: "TA 的朋友" })).toBeNull();
  });

  it("旧链接 ?channel=family 照常打开家庭来信", async () => {
    const { friends } = renderCommunicator(async () => FRIENDS, "/communicator?channel=family");
    const group = await screen.findByRole("group", { name: "通讯器分区" });
    expect(within(group).getByRole("button", { name: "家庭来信" }).getAttribute("aria-pressed")).toBe("true");
    expect(await screen.findByText("家里还没有共同来信")).toBeTruthy();
    expect(friends).not.toHaveBeenCalled();
  });
});

/* ---------------- 演示（fixture），经真实路由表与演示服务 ---------------- */

describe("演示模式：不编朋友", () => {
  it("/communicator?channel=friends：服务报能力未接入时不崩，只给一句说明；不露能力代码，没有任何朋友", async () => {
    mode.dataMode = "fixture";
    const modules = loadFeatureModules();
    const services = buildServices(modules, { mode: "fixture", api: createApiClient("/api/v1/web") });
    await expect(services.social.friends("fx-pet-001")).rejects.toMatchObject({ code: "CAPABILITY_UNAVAILABLE" });
    const router = createMemoryRouter(buildRoutes(modules), { initialEntries: ["/communicator?channel=friends"] });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <ServicesProvider services={services}>
          <RouterProvider router={router} />
        </ServicesProvider>
      </QueryClientProvider>,
    );
    const pet = fixtureHomeSnapshot().pet;
    expect(await screen.findByText("演示里还没有朋友记录")).toBeTruthy();
    expect(await screen.findByText(`${pet.name} 的朋友`)).toBeTruthy();
    expect(screen.getByRole("group", { name: "通讯器分区" })).toBeTruthy();
    expect(screen.queryByRole("list", { name: "TA 的朋友" })).toBeNull();
    expect(document.querySelectorAll(".ps-friend")).toHaveLength(0);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(document.body.textContent).not.toMatch(/social\.friends|CAPABILITY|能力|接入|搭建中/);
    expect(document.body.textContent).not.toMatch(NOW_WORDS);
    // 新底栏里“通讯器”是当前项。
    const tabs = screen.getByRole("navigation", { name: "主导航" });
    expect(within(tabs).getByRole("link", { name: "通讯器" }).getAttribute("aria-current")).toBe("page");
  });
});

/* ---------------- 通讯器样式：只用主题变量 ---------------- */

describe("通讯器样式只用主题变量", () => {
  it("communicator.css 去掉注释后没有写死的颜色（#十六进制、rgb()/hsl()、white/black）；改过的聊天样式都在用令牌", () => {
    const file = resolve(dirname(fileURLToPath(import.meta.url)), "..", "src", "features", "communicator", "communicator.css");
    const css = readFileSync(file, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
    expect(css.match(/#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\(|(?<![\w-])(?:white|black)(?![\w-])/g) ?? []).toEqual([]);
    // 规则整条被删也会“没有写死的颜色”：所以再确认这几条还在、而且颜色来自令牌。
    for (const selector of [".ps-communicator-family-note", ".ps-msg__reply", ".ps-msg__links a", ".ps-msg__links span", ".ps-msg__photo-pending"]) {
      const body = new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\{([^}]*)\\}`).exec(css)?.[1] ?? "";
      expect(body, selector).toMatch(/(?:^|;)\s*color:\s*[^;]*var\(--c-/);
    }
  });
});

/* ---------------- 朋友圈（/circle）：标题与出口 ---------------- */

describe("朋友圈（/circle）：标题与出口", () => {
  function renderFixtureApp(path: string) {
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

  it("标题叫“朋友圈”，页面上不再出现“星球圈”；左上角返回回到通讯器的“TA 的朋友”", async () => {
    const router = renderFixtureApp("/circle");
    expect(await screen.findByText("朋友圈", { selector: ".ps-topbar__title" })).toBeTruthy();
    // 等动态流真的渲染出来（每张帖子卡片都有“查看评论”），再查整页文字，免得查的是一张还没加载的空页。
    expect((await screen.findAllByRole("link", { name: /查看评论/ })).length).toBeGreaterThan(0);
    expect(document.body.textContent).not.toContain("星球圈");
    const back = screen.getByRole("link", { name: "返回" });
    expect(back.getAttribute("href")).toBe("/communicator?channel=friends");
    fireEvent.click(back);
    await waitFor(() => expect(`${router.state.location.pathname}${router.state.location.search}`).toBe("/communicator?channel=friends"));
    expect(await screen.findByText("演示里还没有朋友记录")).toBeTruthy();
  });

  it("指星球世界的“星球居民”标签保留（动态详情评论区里的星球居民）", async () => {
    renderFixtureApp("/posts/fx-post-1");
    expect(await screen.findByText("星球居民", { selector: ".ps-chip" })).toBeTruthy();
  });
});
