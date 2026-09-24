/**
 * claude-6c2b（分身）· 到站自拍的前端显示（docs/coordination/ARRIVAL-SELFIE-DESIGN-2026-09-24.md）。
 * TA 第一次入住后，家庭频道来一条“我到站啦！…”带自拍（先 processing，画好 ready），收藏里一张到站明信片（source_event_id = arrival:<pet_id>）。
 * - 通讯器：照片画好了的说明是通用的“AI 生成的自拍，不是真实照片”（不再写“虚构旅行 / 到访”）；unknown 写“这张照片还没确认”，
 *   不当成失败、也不当成没有；processing、failed 照旧。到站消息的来源号不外露，所以这里不认“是不是到站”。
 * - 收藏：按来源号认出到站明信片——照片写“{名字}到站后拍的第一张自拍（AI 生成…）”；冲洗中 / 待确认是纸色的显影相纸，不是缺图的虚线框；
 *   没有自拍（image_status 为空）就是一张手写明信片（TA 的话、寄自哪里、日期、爪印邮票）；别的明信片照旧。
 * - 演示收藏里多一张手写的到站明信片（最后一张），给截图用；两只宠物时写的是当前这一只的名字。
 */
import { readdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import type { CollectionItem, HomeSnapshot, HouseholdBrief, HouseholdPetBrief, MessageSummary, MessageThread } from "@/shared/contracts";
import { ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { HouseholdProvider } from "@/shared/session/householdContext";
import { fixtureHomeSnapshot } from "@/fixtures/home";
import { fixtureCollection } from "@/fixtures/social";
import collectionModule from "@/features/collection/module";
import communicatorModule from "@/features/communicator/module";
import { demoAnnouncementFeed } from "@/features/communicator/announcements";
import { isArrivalPostcard } from "@/features/collection/ArrivalPostcard";

const mode = vi.hoisted(() => ({ value: "live" as "live" | "fixture" }));
vi.mock("@/shared/config/env", () => ({
  env: {
    get dataMode() {
      return mode.value;
    },
    isDev: false,
    apiBase: "/api/v1/web",
  },
}));

beforeEach(() => {
  mode.value = "live";
  sessionStorage.clear();
  vi.stubGlobal("scrollTo", vi.fn());
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const SELFIE = "/api/v1/web/media/illustrations/il-arrival-1";

function pet(id: string, name: string): HouseholdPetBrief {
  return { pet_id: id, name, species: "cat", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-24T04:00:00Z", added_by_you: true };
}
const household = (pets: HouseholdPetBrief[]): HouseholdBrief[] => [{ household_id: "hh-1", name: "我们的家", home_id: "home-1", role: "admin", home_activated: true, member_count: 1, pets }];
function homeFor(p: HouseholdPetBrief): HomeSnapshot {
  const base = fixtureHomeSnapshot();
  return { ...base, pet: { ...base.pet, pet_id: p.pet_id, name: p.name, species: p.species, photo_url: p.photo_url, photo_generated: false }, data_origin: "live" };
}

function strict(services: Record<string, unknown>): ServiceMap {
  return new Proxy(services as unknown as ServiceMap, {
    get(target, prop: string) {
      if (prop in target) return target[prop as keyof ServiceMap];
      throw new Error(`unexpected service ${prop}`);
    },
  });
}

/* ---------------- 通讯器 ---------------- */

const ARRIVAL_TEXT = "我到站啦！这是我在西贡的海边拍的第一张自拍～到站明信片也寄出了，在收藏里能看到。";

function arrivalMessage(over: Partial<MessageSummary>): MessageSummary {
  return {
    message_id: "msg-arrival",
    client_message_id: null,
    sender: "pet",
    text: ARRIVAL_TEXT,
    state: "delivered",
    created_at: "2026-09-24T04:00:30Z",
    photo_url: null,
    photo_status: "processing",
    channel: "family",
    source_event_id: null, // 到站消息的来源号不外露（后端既有口径）
    ...over,
  } as MessageSummary;
}

function renderCommunicator(messages: MessageSummary[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const p = pet("pet-1", "团子");
  const thread: MessageThread = { pet_id: "pet-1", items: messages, next_cursor: null, data_origin: "live" };
  const element = communicatorModule.routes!.find((route) => route.path === "communicator")!.element;
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider
        services={strict({
          households: { list: async () => household([p]) },
          world: { home: async () => homeFor(p) },
          communicator: { thread: async () => thread, send: vi.fn(), announcements: async () => demoAnnouncementFeed() },
          transport: { guides: async () => [] },
          economy: { collection: async () => [] },
          social: { friends: async () => [] },
        })}
      >
        <MemoryRouter initialEntries={["/communicator?channel=family"]}>
          <HouseholdProvider userId="u-1">
            <Routes>
              <Route path="/communicator" element={element} />
            </Routes>
          </HouseholdProvider>
        </MemoryRouter>
      </ServicesProvider>
    </QueryClientProvider>,
  );
}

const bubble = async () => (await screen.findByText(ARRIVAL_TEXT)).closest(".ps-msg") as HTMLElement;

describe("通讯器：到站消息里的自拍", () => {
  it("画好了（ready）：照片的说明与读屏名都是通用说法“AI 生成的自拍，不是真实照片”，不再写虚构旅行 / 到访", async () => {
    renderCommunicator([arrivalMessage({ photo_status: "ready", photo_url: SELFIE })]);
    const b = await bubble();
    const img = within(b).getByRole("img", { name: "TA 发来的自拍（AI 生成）" });
    expect(img.getAttribute("src")).toBe(SELFIE);
    expect(b.querySelector("figcaption")?.textContent).toBe("AI 生成的自拍，不是真实照片");
    expect(b.textContent).not.toMatch(/虚构旅行|到访/);
  });

  it("还在画（processing）：照旧写“随信画面正在生成”，不放图", async () => {
    renderCommunicator([arrivalMessage({ photo_status: "processing" })]);
    const b = await bubble();
    expect(b.querySelector(".ps-msg__photo-pending")?.textContent).toBe("随信画面正在生成");
    expect(b.querySelector("img")).toBeNull();
  });

  it("结果没确认（unknown）：写“这张照片还没确认”——不当成失败，也不是什么都不显示", async () => {
    renderCommunicator([arrivalMessage({ photo_status: "unknown" })]);
    const b = await bubble();
    expect(b.querySelector(".ps-msg__photo-pending")?.textContent).toBe("这张照片还没确认");
    expect(b.textContent).not.toMatch(/未生成成功|没有生成/);
  });

  it("没画成（failed）：照旧写“随信画面未生成成功，文字已送达”", async () => {
    renderCommunicator([arrivalMessage({ photo_status: "failed" })]);
    const b = await bubble();
    expect(b.querySelector(".ps-msg__photo-pending")?.textContent).toBe("随信画面未生成成功，文字已送达");
  });

  it("到站消息的来源号不外露：气泡上没有“来自这趟旅途”", async () => {
    renderCommunicator([arrivalMessage({ photo_status: "ready", photo_url: SELFIE })]);
    const b = await bubble();
    expect(b.textContent).not.toContain("来自这趟旅途");
  });
});

/* ---------------- 收藏 ---------------- */

const NOTE = "我到站啦！这里是香港·西贡的海边，以后我就住在这儿了。给家里寄一张到站明信片，这是我在新家写下的第一句话～";

function arrivalPostcard(over: Partial<CollectionItem> = {}): CollectionItem {
  return {
    item_id: "it-arrival",
    kind: "postcard",
    item_key: null,
    title: "来自西贡的海边的到站明信片",
    obtained_at: "2026-09-24T04:00:30Z",
    tradable: false,
    bound_to_pet: true,
    source_event_id: "arrival:pet-1",
    data_origin: "live",
    note: NOTE,
    image_url: null,
    image_status: null,
    place: "西贡的海边",
    city: "香港",
    ...over,
  };
}

function renderCollection(items: (petId: string | null) => Promise<CollectionItem[]>, pets: HouseholdPetBrief[] = [pet("pet-1", "团子")]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const element = collectionModule.routes!.find((route) => route.path === "collection")!.element;
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={strict({ households: { list: async () => household(pets) }, world: { home: async () => homeFor(pets[0]) }, economy: { collection: items } })}>
        <MemoryRouter initialEntries={["/collection"]}>
          <HouseholdProvider userId="u-1">
            <Routes>
              <Route path="/collection" element={element} />
            </Routes>
          </HouseholdProvider>
        </MemoryRouter>
      </ServicesProvider>
    </QueryClientProvider>,
  );
}

const card = async (title = "来自西贡的海边的到站明信片") => (await screen.findByText(title, { selector: "strong" })).closest(".ps-collection-item") as HTMLElement;

describe("收藏：到站明信片", () => {
  it("按来源号认：arrival: 开头的明信片才是；旅途明信片、别的种类都不是", () => {
    expect(isArrivalPostcard(arrivalPostcard())).toBe(true);
    expect(isArrivalPostcard(arrivalPostcard({ source_event_id: "jn-1a2b:visit_ended" }))).toBe(false);
    expect(isArrivalPostcard(arrivalPostcard({ source_event_id: null }))).toBe(false);
    expect(isArrivalPostcard(arrivalPostcard({ kind: "badge" }))).toBe(false);
  });

  it("自拍画好了：写“{名字}到站后拍的第一张自拍（AI 生成…）”，不是旅行自拍；手写部分照样有", async () => {
    renderCollection(async () => [arrivalPostcard({ image_status: "ready", image_url: SELFIE })]);
    const c = await card();
    const img = within(c).getByRole("img", { name: "团子到站后拍的第一张自拍" });
    expect(img.getAttribute("src")).toBe(SELFIE);
    expect(within(c).getByTestId("arrival-photo").textContent).toContain("团子到站后拍的第一张自拍（AI 生成，不是真实照片）");
    expect(c.textContent).not.toMatch(/虚构旅行自拍|到店照片/);
    expect(within(c).getByTestId("arrival-card").textContent).toContain(`“${NOTE}”`);
    expect(c.querySelector(".ps-collection-item__envelope")).toBeNull();
  });

  it("冲洗中：一张纸色的显影相纸写“到站自拍冲洗中，洗好了会换上”，不是缺图的虚线框，也不放图", async () => {
    renderCollection(async () => [arrivalPostcard({ image_status: "processing" })]);
    const c = await card();
    expect(within(c).getByTestId("arrival-developing").textContent).toBe("到站自拍冲洗中，洗好了会换上");
    expect(c.querySelector(".ps-collection-item__envelope")).toBeNull();
    expect(within(c).queryByRole("img", { name: /自拍/ })).toBeNull();
  });

  it("结果没确认：同一张相纸写“这张到站自拍还没确认”，不当成失败", async () => {
    renderCollection(async () => [arrivalPostcard({ image_status: "unknown" })]);
    const c = await card();
    expect(within(c).getByTestId("arrival-developing").textContent).toBe("这张到站自拍还没确认");
    expect(c.textContent).not.toMatch(/没有生成成功/);
  });

  it("没有自拍（为空）：就是一张手写明信片——TA 的话、寄自哪里与日期、爪印邮票；不提自拍，也没有相纸", async () => {
    renderCollection(async () => [arrivalPostcard()]);
    const c = await card();
    const handwritten = within(c).getByTestId("arrival-card");
    expect(handwritten.textContent).toContain(`“${NOTE}”`);
    expect(handwritten.textContent).toContain("寄自 香港·西贡的海边 · 9月24日");
    expect(within(handwritten).getByTestId("arrival-stamp")).toBeTruthy();
    expect(within(c).queryByTestId("arrival-developing")).toBeNull();
    expect(within(c).queryByTestId("arrival-photo")).toBeNull();
    expect(c.textContent).not.toMatch(/自拍/);
    expect(c.className).toContain("ps-card--paper");
  });

  it("没画成（failed）：手写明信片照样在，下面一行说明；不画相纸", async () => {
    renderCollection(async () => [arrivalPostcard({ image_status: "failed" })]);
    const c = await card();
    expect(within(c).getByTestId("arrival-status").textContent).toBe("到站自拍没有生成成功，留下这张手写明信片");
    expect(within(c).queryByTestId("arrival-developing")).toBeNull();
    expect(within(c).getByTestId("arrival-card").textContent).toContain(NOTE);
  });

  it("别的明信片（旅途邮局寄的）照旧：虚线信封与原来的说法", async () => {
    renderCollection(async () => [arrivalPostcard({ item_id: "it-trip", title: "海边咖啡馆明信片", source_event_id: "jn-1a2b:visit_ended", note: null })]);
    const c = await card("海边咖啡馆明信片");
    expect(c.querySelector(".ps-collection-item__envelope")?.textContent).toContain("这张明信片没有自拍");
    expect(within(c).queryByTestId("arrival-postcard")).toBeNull();
  });

  it("两只宠物：当前是豆豆，照片说明写豆豆", async () => {
    sessionStorage.setItem("petsoul:current-pet:u-1", "pet-2");
    renderCollection(async (petId) => (petId === "pet-2" ? [arrivalPostcard({ source_event_id: "arrival:pet-2", image_status: "ready", image_url: SELFIE })] : []), [pet("pet-1", "团子"), pet("pet-2", "豆豆")]);
    const c = await card();
    expect(within(c).getByRole("img", { name: "豆豆到站后拍的第一张自拍" })).toBeTruthy();
    expect(c.textContent).not.toContain("团子");
  });

  it("演示收藏：最后多一张手写的到站明信片（不带图、不冒充 AI 自拍），其余演示收藏不变", async () => {
    const list = await (collectionModule.services!.economy!.fixture!({} as never) as ServiceMap["economy"]).collection(null);
    expect(list.slice(0, fixtureCollection().length)).toEqual(fixtureCollection());
    const last = list.at(-1)!;
    expect(isArrivalPostcard(last)).toBe(true);
    expect(last).toMatchObject({ kind: "postcard", image_status: null, image_url: null, data_origin: "fixture" });
    expect(last.title.endsWith("到站明信片")).toBe(true);
  });
});

/* ---------------- 字色（读磁盘上的 CSS） ---------------- */

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const strip = (text: string) => text.replace(/\/\*[\s\S]*?\*\//g, "");
/** 变异自检时 DS_TOUCH_COLLECTION_CSS 指向一份改过的 collection.css 副本（和 ds-touchpoints 同一个开关）；别的文件照读磁盘。 */
function cssText(file: string): string {
  const override = file === "src/features/collection/collection.css" ? process.env.DS_TOUCH_COLLECTION_CSS : undefined;
  return readFileSync(override ?? resolve(ROOT, file), "utf8");
}
function rule(file: string, selector: string, prop: string): string {
  const text = strip(cssText(file));
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const found = [...text.matchAll(new RegExp(`(?:^|\\n)${escaped}\\s*\\{([^}]*)\\}`, "g"))];
  expect(found.length, `${selector} 应恰好一条`).toBe(1);
  const decl = found[0][1].split(";").map((part) => part.split(":")).find(([name]) => name.trim() === prop);
  expect(decl, `${selector} 的 ${prop}`).toBeDefined();
  return decl!.slice(1).join(":").trim();
}

describe("类名不撞：到站明信片的类名只在 collection.css 里定义", () => {
  it("小窝“到家了”弹层用的是 .ps-arrival*（固定定位的遮罩与卡片），到站明信片用 .ps-arrival-postcard*，别处的样式表都不定义它", () => {
    // 2026-09-24 实拍撞过一次：起初也叫 .ps-arrival，收藏页被 home.css 的遮罩样式整页盖住。jsdom 不排版，只有这条能提前拦住。
    const cssFiles: string[] = [];
    const walk = (dir: string) => {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const path = resolve(dir, entry.name);
        if (entry.isDirectory()) walk(path);
        else if (entry.name.endsWith(".css")) cssFiles.push(path);
      }
    };
    walk(resolve(ROOT, "src"));
    const definers = cssFiles.filter((file) => /\.ps-arrival-postcard\b/.test(strip(readFileSync(file, "utf8")))).map((file) => file.replace(/\\/g, "/").split("/src/")[1]);
    expect(definers).toEqual(["features/collection/collection.css"]);
    const collectionCss = strip(readFileSync(resolve(ROOT, "src/features/collection/collection.css"), "utf8"));
    expect(collectionCss).not.toMatch(/\.ps-arrival(?![-\w])/);
  });
});

describe("星形装饰不压标题：收藏卡标题行最后一个元素给右上角的 ✦ 留位置", () => {
  it("没有“演示数据”标记（live）时标题块自己留 ≥ 28px；有标记时标记的 margin-right 留 ≥ 28px——两条路都让开星星", () => {
    // 2026-09-24 实测（scratchpad ds-touch/shots-star.mjs，按 ::before 的位置与标题每行的矩形算相交）：
    // 改前 live 的长标题在 320 / 390 宽下第一行末尾都压在星星上；改后 6 张卡都不相交。jsdom 不排版，这里钉住两条让位规则。
    const px = (value: string) => Number.parseFloat(value);
    expect(px(rule("src/features/collection/collection.css", ".ps-collection-item__head > div:last-child", "padding-right"))).toBeGreaterThanOrEqual(28);
    expect(px(rule("src/features/collection/collection.css", ".ps-collection-item__head .ps-origin", "margin-right"))).toBeGreaterThanOrEqual(28);
  });

  it("到站明信片的寄出日期整段不拆行（不在“9月 / 24日”中间断开）", () => {
    expect(rule("src/features/collection/collection.css", ".ps-arrival-postcard__day", "white-space")).toBe("nowrap");
    expect(rule("src/features/collection/collection.css", ".ps-arrival-postcard__from", "flex-wrap")).toBe("wrap");
  });
});

describe("字色：到站明信片上的字都用纸墨（纸色底，昼夜一样）", () => {
  it("TA 的话、寄自哪里、相纸上的字、照片说明、状态说明都压在 --paper 上，用的是纸墨色（≥ 4.5:1，见 ds-touchpoints 的实算）", () => {
    // 纸墨是固定色：--paper-ink 约 11:1、--paper-secondary-ink 约 4.6:1（在 --paper 上）；这里钉住“用的是纸墨，不是跟主题走的颜色”
    const PAPER_INK = /^var\(--paper-(?:ink|secondary-ink)\)$/;
    for (const selector of [".ps-arrival-postcard__note", ".ps-arrival-postcard__from", ".ps-arrival-postcard__developing", ".ps-arrival-postcard__photo figcaption", ".ps-arrival-postcard__status"]) {
      expect(rule("src/features/collection/collection.css", selector, "color"), selector).toMatch(PAPER_INK);
    }
    for (const selector of [".ps-arrival-postcard__card", ".ps-arrival-postcard__developing", ".ps-arrival-postcard__photo"]) {
      expect(rule("src/features/collection/collection.css", selector, "background"), selector).toBe("var(--paper)");
    }
  });
});
