/**
 * claude-6c2b（分身）· 爪爪驾校在驾校模块以外露面的地方（第一批）：
 * - 收藏 /collection：驾校借车券（car_voucher）、领证合影（license_photo）说人话——不露原始 kind；
 *   借车券的用途只写服务端 note 原文（没有 note 就不写），状态只写“还没用”（后端只返回没用掉的）；
 *   领证合影照片画好了才显示（标 AI 生成），否则是画出内容的纸质纪念卡（第二批：TA 的头像、龟教练、爪印章、日期、TA 的话；
 *   照片在冲洗 / 没成 / 待确认时底下多一行说明）；TA 的话照原文；
 *   借车券的标签写当前宠物的名字（第二批），拿不到名字时写“TA”；
 *   演示收藏只在 ?school_demo=licensed 时多一张借车券，别的演示数据不变；明信片占位框的字 ≥ 4.5:1（第二批）。
 * - 驾照详情 /credentials/:id：多一段“有了驾照以后”（有资格自己开车兜风、要租车、坐车船飞机不需要驾照）；
 *   收藏里真有借车券时才写那一行（用途是服务端 note），链到收藏；收藏读不到时只少这一行。
 * - 两只宠物：收藏页与驾照页读的都是当前这一只的收藏（请求带它的 pet_id，显示它的券）。
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import type { CollectionItem, CredentialDetail, CredentialSummary, HomeSnapshot, HouseholdBrief, HouseholdPetBrief } from "@/shared/contracts";
import { ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { HouseholdProvider } from "@/shared/session/householdContext";
import { fixtureHomeSnapshot } from "@/fixtures/home";
import { fixtureCollection } from "@/fixtures/social";
import collectionModule from "@/features/collection/module";
import { boundChipText, kindText, schoolDemoKeepsakes } from "@/features/collection/schoolKeepsakes";
import { SCHOOL_ART } from "@/features/driving_school/assets";
import { CredentialPage } from "@/features/life/CredentialPage";

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
  window.history.replaceState({}, "", "/");
});

/** 后端发券时写的那句（web_driving/service.py _grant_license）。 */
const VOUCHER_NOTE = "第一次自己开车兜风时，借驾校的车，不用租车费（用一次）";
const PET_LINE = "我会慢慢开，先载你去海边。";

const item = (over: Partial<CollectionItem> & Pick<CollectionItem, "item_id" | "kind" | "title">): CollectionItem => ({
  item_key: null,
  obtained_at: "2026-09-21T04:00:00Z",
  tradable: false,
  bound_to_pet: true,
  source_event_id: "license:cr-dl",
  data_origin: "live",
  ...over,
});

const VOUCHER = item({ item_id: "it-v", kind: "car_voucher", title: "驾校借车券", note: VOUCHER_NOTE });
const PHOTO_READY = item({ item_id: "it-p", kind: "license_photo", title: "领证合影", note: PET_LINE, image_url: "/api/v1/web/media/collection/it-p", image_status: "ready" });
const PHOTO_DRAWING = item({ item_id: "it-p2", kind: "license_photo", title: "领证合影", note: null, image_url: null, image_status: "processing" });
const PHOTO_PAPER = item({ item_id: "it-p3", kind: "license_photo", title: "领证合影", note: PET_LINE, image_url: null, image_status: null });
const MYSTERY = item({ item_id: "it-x", kind: "mystery_kind", title: "一件新纪念" });

function pet(id: string, name: string): HouseholdPetBrief {
  return { pet_id: id, name, species: "dog", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-08-01T04:00:00Z", added_by_you: true };
}

function household(pets: HouseholdPetBrief[]): HouseholdBrief[] {
  return [{ household_id: "hh-1", name: "我们的家", home_id: "home-1", role: "admin", home_activated: true, member_count: 1, pets }];
}

function homeFor(p: HouseholdPetBrief): HomeSnapshot {
  const base = fixtureHomeSnapshot();
  return { ...base, pet: { ...base.pet, pet_id: p.pet_id, name: p.name, species: p.species, photo_url: p.photo_url, photo_generated: false }, data_origin: "live" };
}

const LICENSE: CredentialSummary = {
  credential_id: "cr-dl",
  kind: "driver_license",
  label: "爪爪驾驶证",
  status: "active",
  number: "PAW-DL-2026-QRSTUV",
  issued_at: "2026-09-21T04:00:00Z",
  title: "PetSoul · 爪爪驾驶证 · 小型车（C）",
  condition: "在爪爪驾校通过四科考试后签发（科目一到科目四）",
  private: false,
  links: [],
};
const ID_CARD: CredentialSummary = { ...LICENSE, credential_id: "cr-id", kind: "identity_card", label: "星球居民证", number: "PS-ID-2026-ABCDEF", title: "星球居民证", condition: "入住星球时签发" };

const detail = (summary: CredentialSummary): CredentialDetail => ({ summary, fields: [{ label: "名字", value: "栗子" }], balance: null, ledger: [], stamps: [], care_notes: [] });

type Collection = (petId: string | null, signal?: AbortSignal) => Promise<CollectionItem[]>;

/** 只给页面真正会用的服务；页面去拿别的服务就当场报错（和卡包测试同一种严格替身）。 */
function strict(services: Record<string, unknown>): ServiceMap {
  return new Proxy(services as unknown as ServiceMap, {
    get(target, prop: string) {
      if (prop in target) return target[prop as keyof ServiceMap];
      throw new Error(`unexpected service ${prop}`);
    },
  });
}

type Home = (petId: string | null, signal?: AbortSignal) => Promise<HomeSnapshot>;

function renderLive(
  entry: string,
  collection: Collection,
  pets: HouseholdPetBrief[] = [pet("pet-1", "栗子")],
  credentials: CredentialSummary[] = [LICENSE, ID_CARD],
  options: { home?: Home } = {},
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const current = (id: string) => pets.find((p) => p.pet_id === id) ?? pets[0];
  const services = strict({
    households: { list: async () => household(pets) },
    world: { home: options.home ?? (async (petId: string | null) => homeFor(current(petId ?? pets[0].pet_id))) },
    platform: { meta: async () => ({ api_prefix: "/api/v1/web", contract_version: "t", server_time: "2026-09-24T04:00:00Z", backend_version: "t", data_origin: "live", auth_methods_available: [], applied_migrations: [], capabilities: [] }) },
    pets: { character: async () => ({ pet_id: "pet-1", status: "absent", active: null, candidate: null, can_regenerate: false, blocked_reason: null, id_photo: null }) },
    life: {
      credentials: async () => credentials,
      jobs: async () => [],
      credential: async (id: string) => detail(credentials.find((c) => c.credential_id === id)!),
    },
    economy: { collection },
  });
  const collectionRoute = collectionModule.routes!.find((route) => route.path === "collection")!;
  return render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={services}>
        <MemoryRouter initialEntries={[entry]}>
          <HouseholdProvider userId="u-1">
            <Routes>
              <Route path="/collection" element={collectionRoute.element} />
              <Route path="/credentials/:credentialId" element={<CredentialPage />} />
            </Routes>
          </HouseholdProvider>
        </MemoryRouter>
      </ServicesProvider>
    </QueryClientProvider>,
  );
}

const cardOf = (title: string, index = 0) => screen.getAllByText(title, { selector: "strong" })[index].closest(".ps-collection-item") as HTMLElement;

describe("收藏：驾校的两样东西说人话", () => {
  it("借车券：写“爪爪驾校 · 还没用”，用途是服务端 note 原文，标签写当前宠物的名字“绑定栗子，不能交易”；页面上没有任何原始 kind", async () => {
    renderLive("/collection", async () => [VOUCHER, PHOTO_READY, MYSTERY]);
    await screen.findByText("驾校借车券");
    const voucher = cardOf("驾校借车券");
    expect(voucher.textContent).toContain("爪爪驾校 · 还没用");
    expect(within(voucher).getByTestId("voucher-use").textContent).toBe(`怎么用${VOUCHER_NOTE}`);
    expect(within(voucher).getByText("绑定栗子，不能交易")).toBeTruthy();
    expect(voucher.textContent).not.toContain("TA");
    expect(voucher.textContent).not.toContain("个人纪念");
    // 认不出的种类只写“纪念”
    expect(cardOf("一件新纪念").textContent).toContain("纪念");
    expect(document.body.textContent).not.toMatch(/car_voucher|license_photo|mystery_kind/);
  });

  it("借车券没有 note：不写用途（不编），其余照常", async () => {
    renderLive("/collection", async () => [{ ...VOUCHER, note: null }]);
    await screen.findByText("驾校借车券");
    expect(screen.queryByTestId("voucher-use")).toBeNull();
    expect(cardOf("驾校借车券").textContent).toContain("爪爪驾校 · 还没用");
  });

  it("领证合影：照片画好了才显示（标 AI 生成、读屏有说明），TA 的话照原文；是纸卡", async () => {
    renderLive("/collection", async () => [PHOTO_READY]);
    await screen.findByText("领证合影");
    const card = cardOf("领证合影");
    const img = within(card).getByRole("img", { name: "栗子和你的领证合影" });
    expect(img.getAttribute("src")).toBe(PHOTO_READY.image_url);
    expect(card.textContent).toContain("AI 生成的纪念合影，不是真实照片");
    expect(card.textContent).toContain(`“${PET_LINE}”`);
    expect(card.textContent).toContain("爪爪驾校 · 领证那天");
    expect(card.className).toContain("ps-card--paper");
    expect(within(card).getByText("个人纪念，不可交易")).toBeTruthy();
  });

  it("领证合影没有照片：是一张画出内容的纸质纪念卡——TA 的头像、龟教练、爪印章、领证日期、TA 的话；不写“没有生成照片”，不像缺图", async () => {
    renderLive("/collection", async () => [PHOTO_PAPER]);
    await screen.findByText("领证合影");
    const card = cardOf("领证合影");
    const memento = within(card).getByTestId("license-memento");
    expect(memento.getAttribute("aria-label")).toBe("栗子和龟教练·慢慢的领证纪念卡");
    // 头像是 TA 自己的样子（live 没有照片：爪印，读屏说“暂无照片”），不写名字首字
    const avatar = within(within(memento).getByTestId("memento-pet")).getByRole("img", { name: "栗子，暂无照片" });
    expect(avatar.querySelector("img")).toBeNull();
    expect(within(memento).getByTestId("memento-pet").textContent).toBe("栗子");
    expect(within(memento).getByTestId("memento-coach").textContent).toBe("龟教练·慢慢");
    expect(within(memento).getByTestId("memento-stamp")).toBeTruthy();
    expect(memento.textContent).toContain("2026年9月21日 · 在爪爪驾校领证");
    expect(memento.textContent).toContain(`“${PET_LINE}”`);
    // 没有开生成照片（状态为空）时，纸质卡就是这张纪念：不加状态说明，不写“没有生成照片”，也没有相机图标
    expect(within(memento).queryByTestId("memento-status")).toBeNull();
    expect(card.textContent).not.toMatch(/没有生成照片|缺图/);
    expect(card.querySelector("[data-icon='camera'], .ps-collection-item__envelope")).toBeNull();
    // TA 的话只写一次（在卡里）
    expect(card.textContent!.split(PET_LINE)).toHaveLength(2);
  });

  it("龟教练用新素材（SCHOOL_ART.coach.portrait，和领证仪式那张同一张图）；图片加载失败就退回代码画的线稿", async () => {
    renderLive("/collection", async () => [PHOTO_PAPER]);
    const coach = within(await screen.findByTestId("license-memento")).getByTestId("memento-coach");
    const art = within(coach).getByTestId("memento-coach-art");
    expect(art.getAttribute("src")).toBe(SCHOOL_ART.coach.portrait);
    expect(art.getAttribute("alt")).toBe(""); // 名字写在下面那行字里，图是装饰
    expect(coach.querySelector(".ps-memento__turtle")).toBeNull();
    fireEvent.error(art);
    expect(within(coach).queryByTestId("memento-coach-art")).toBeNull();
    expect(coach.querySelector("svg.ps-memento__turtle")).toBeTruthy();
    expect(coach.textContent).toBe("龟教练·慢慢");
  });

  it("有 TA 的照片时，纪念卡上的头像就是那张照片", async () => {
    renderLive("/collection", async () => [PHOTO_PAPER], [{ ...pet("pet-1", "栗子"), photo_url: "/api/v1/web/media/pets/pet-1/photo" }]);
    const memento = await screen.findByTestId("license-memento");
    const avatar = within(within(memento).getByTestId("memento-pet")).getByRole("img", { name: "栗子" });
    expect(avatar.querySelector("img")?.getAttribute("src")).toBe("/api/v1/web/media/pets/pet-1/photo");
  });

  it("照片还在冲洗 / 没生成成功 / 待确认：纪念卡照样画出来，底下多一行说明；没有 TA 的话就不写引号", async () => {
    renderLive("/collection", async () => [
      PHOTO_DRAWING,
      { ...PHOTO_DRAWING, item_id: "it-f", image_status: "failed" },
      { ...PHOTO_DRAWING, item_id: "it-u", image_status: "unknown" },
    ]);
    await screen.findAllByText("领证合影");
    const statuses = screen.getAllByTestId("memento-status").map((node) => node.textContent);
    expect(statuses).toEqual(["合影照片还在冲洗，洗好了会换上", "合影照片没有生成成功，留下这张纸质纪念卡", "合影照片的状态还没确认"]);
    for (const memento of screen.getAllByTestId("license-memento")) {
      expect(within(memento).getByTestId("memento-coach")).toBeTruthy();
      expect(memento.textContent).not.toContain("“");
    }
    expect(screen.queryByRole("img", { name: /领证合影/ })).toBeNull();
  });

  it("kindText：认得的说人话，认不出的只写“纪念”（原型链上的名字也不会查出东西）", () => {
    expect(kindText("car_voucher")).toBe("爪爪驾校 · 还没用");
    expect(kindText("license_photo")).toBe("爪爪驾校 · 领证那天");
    expect(kindText("postcard")).toBe("明信片");
    expect(kindText("constructor")).toBe("纪念");
    expect(kindText("brand_new_kind")).toBe("纪念");
  });

  it("boundChipText：借车券写绑的是哪一只；中文名紧挨着写，英文名与“TA”前面留空格；名字空了写“TA”；别的收藏仍是“个人纪念”", () => {
    expect(boundChipText("car_voucher", "栗子")).toBe("绑定栗子，不能交易");
    expect(boundChipText("car_voucher", "Coco")).toBe("绑定 Coco，不能交易");
    expect(boundChipText("car_voucher", "  ")).toBe("绑定 TA，不能交易");
    expect(boundChipText("car_voucher")).toBe("绑定 TA，不能交易");
    expect(boundChipText("license_photo", "栗子")).toBe("个人纪念，不可交易");
  });

  it("演示模式：没有家庭上下文，名字取演示家园的样板宠物；演示家园读不到时退回“TA”", async () => {
    mode.value = "fixture";
    const demoHome: Home = async () => homeFor(pet("fx-pet-001", "团子"));
    const first = renderLive("/collection", async () => [VOUCHER, PHOTO_PAPER], undefined, undefined, { home: demoHome });
    expect(await screen.findByText("绑定团子，不能交易")).toBeTruthy();
    expect((await screen.findByTestId("license-memento")).getAttribute("aria-label")).toBe("团子和龟教练·慢慢的领证纪念卡");
    first.unmount();

    renderLive("/collection", async () => [VOUCHER], undefined, undefined, {
      home: async () => {
        throw new Error("演示家园读不到");
      },
    });
    expect(await screen.findByText("绑定 TA，不能交易")).toBeTruthy();
  });
});

describe("演示收藏：只在 ?school_demo=licensed 时多一张借车券", () => {
  it("licensed 才有，用途与后端同一句；其余阶段一张都没有（演示的已拿证还没领证，没有合影）", () => {
    const [voucher, ...rest] = schoolDemoKeepsakes("licensed");
    expect(rest).toHaveLength(0);
    expect(voucher).toMatchObject({ kind: "car_voucher", title: "驾校借车券", note: VOUCHER_NOTE, bound_to_pet: true, tradable: false, data_origin: "fixture" });
    for (const stage of [undefined, "none", "wish", "enrolled"] as const) expect(schoolDemoKeepsakes(stage)).toEqual([]);
  });

  it("演示服务：带 ?school_demo=licensed 打开时，借车券排在原有演示收藏之后；不带时没有借车券", async () => {
    // 2026-09-24 到站自拍那批：演示收藏最后固定多一张手写的到站明信片（入住时寄的，最早），所以这里只比到站明信片之前的部分。
    const make = () => collectionModule.services!.economy!.fixture!({} as never) as ServiceMap["economy"];
    const withoutArrival = (list: CollectionItem[]) => list.filter((item) => !(item.source_event_id ?? "").startsWith("arrival:"));
    window.history.replaceState({}, "", "/collection");
    const plain = await make().collection(null);
    expect(withoutArrival(plain)).toEqual(fixtureCollection());
    window.history.replaceState({}, "", "/collection?school_demo=licensed");
    const licensed = withoutArrival(await make().collection(null));
    expect(licensed.slice(0, -1)).toEqual(fixtureCollection());
    expect(licensed.at(-1)).toMatchObject({ kind: "car_voucher", note: VOUCHER_NOTE });
  });
});

describe("驾照详情：有了驾照以后", () => {
  it("写清资格与租车；收藏里有借车券时多一行（服务端 note 原文），链到收藏", async () => {
    const collection = vi.fn<Collection>(async () => [VOUCHER]);
    renderLive("/credentials/cr-dl", collection);
    const use = await screen.findByTestId("license-use");
    expect(within(use).getByRole("heading", { name: "有了驾照以后" })).toBeTruthy();
    expect(use.textContent).toContain("栗子有资格自己开车去兜风了，要租一辆小车；坐车、坐船、坐飞机本来就不需要驾照。");
    const line = await within(use).findByTestId("license-voucher");
    expect(line.textContent).toContain(`还有一张驾校借车券：${VOUCHER_NOTE}`);
    expect(within(line).getByRole("link", { name: "去收藏里看" }).getAttribute("href")).toBe("/collection");
    expect(collection).toHaveBeenCalledWith("pet-1", expect.anything());
  });

  it("借车券用掉了（收藏里没有）：只写资格，不写借车券", async () => {
    renderLive("/credentials/cr-dl", async () => [PHOTO_READY]);
    const use = await screen.findByTestId("license-use");
    await waitFor(() => expect(use.textContent).toContain("有资格自己开车去兜风"));
    expect(within(use).queryByTestId("license-voucher")).toBeNull();
    expect(use.textContent).not.toContain("借车券");
  });

  it("收藏读不到：驾照页照常，只少借车券这一行", async () => {
    renderLive("/credentials/cr-dl", async () => {
      throw new Error("收藏暂时读不到");
    });
    expect(await screen.findByTestId("cred-front")).toBeTruthy();
    expect(screen.getByTestId("license-use")).toBeTruthy();
    expect(screen.queryByTestId("license-voucher")).toBeNull();
  });

  it("别的证件（星球居民证）没有这一段", async () => {
    renderLive("/credentials/cr-id", async () => [VOUCHER]);
    expect(await screen.findByTestId("cred-front")).toBeTruthy();
    expect(screen.queryByTestId("license-use")).toBeNull();
  });
});

/* ---------------- 字色实算（读磁盘上的 CSS；变异自检时 DS_TOUCH_COLLECTION_CSS 指向一份改过的副本） ---------------- */

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const COLLECTION_CSS = process.env.DS_TOUCH_COLLECTION_CSS ?? resolve(ROOT, "src/features/collection/collection.css");
const TOKENS_CSS = resolve(ROOT, "src/shared/theme/tokens.css");
const stripComments = (text: string) => text.replace(/\/\*[\s\S]*?\*\//g, "");

function declsOf(body: string): Map<string, string> {
  const out = new Map<string, string>();
  for (const part of body.split(";")) {
    const at = part.indexOf(":");
    if (at > 0) out.set(part.slice(0, at).trim(), part.slice(at + 1).trim());
  }
  return out;
}

function tokenTable(scheme: "light" | "dark"): Map<string, string> {
  const text = stripComments(readFileSync(TOKENS_CSS, "utf8"));
  const table = declsOf(/:root\s*\{([^}]*)\}/.exec(text)![1]);
  if (scheme === "dark") for (const [k, v] of declsOf(/@media\s*\(prefers-color-scheme:\s*dark\)\s*\{\s*:root\s*\{([^}]*)\}/.exec(text)![1])) table.set(k, v);
  return table;
}

/** 顶层规则（整行以选择器开头）的某个属性；规则必须恰好一条。 */
function topRule(selector: string, prop: string): string {
  const text = stripComments(readFileSync(COLLECTION_CSS, "utf8"));
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const found = [...text.matchAll(new RegExp(`(?:^|\\n)${escaped}\\s*\\{([^}]*)\\}`, "g"))];
  expect(found.length, `collection.css 里 ${selector} 应恰好一条`).toBe(1);
  const value = declsOf(found[0][1]).get(prop);
  expect(value, `${selector} 的 ${prop}`).toBeDefined();
  return value!;
}

type RGB = [number, number, number];
function rgb(value: string, table: Map<string, string>, depth = 0): RGB {
  if (depth > 8) throw new Error(`令牌引用太深：${value}`);
  const v = value.trim();
  const ref = /^var\(\s*(--[\w-]+)\s*\)$/.exec(v);
  if (ref) return rgb(table.get(ref[1]) ?? `missing ${ref[1]}`, table, depth + 1);
  const hex = /^#([0-9a-f]{6})$/i.exec(v);
  if (hex) return [0, 2, 4].map((i) => parseInt(hex[1].slice(i, i + 2), 16)) as RGB;
  const mix = /^color-mix\(\s*in srgb\s*,\s*(.+?)\s+(\d+(?:\.\d+)?)%\s*,\s*(.+?)\s*\)$/.exec(v);
  if (mix) {
    const p = Number(mix[2]) / 100;
    const [a, b] = [rgb(mix[1], table, depth + 1), rgb(mix[3], table, depth + 1)];
    return a.map((c, i) => c * p + b[i] * (1 - p)) as RGB;
  }
  throw new Error(`不认识的颜色写法：${value}`);
}

function ratio(fg: string, bg: string, scheme: "light" | "dark"): number {
  const table = tokenTable(scheme);
  const lum = (c: RGB) => c.map((x) => x / 255).map((s) => (s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4)).reduce((sum, s, i) => sum + s * [0.2126, 0.7152, 0.0722][i], 0);
  const [hi, lo] = [lum(rgb(fg, table)), lum(rgb(bg, table))].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

describe("字色：收藏里驾校两样东西的字，浅色、深色都 ≥ 4.5:1", () => {
  it("纸卡（领证合影、明信片）上 TA 的话、照片说明：浅色压在暖白卡面上，深色压在暖纸上", () => {
    // 浅色：.ps-collection-item 的卡面盖过了纸卡底色；深色：.ps-collection-item.ps-card--paper 回到 --paper
    const lightCard = topRule(".ps-collection-item", "background");
    for (const selector of [".ps-card--paper .ps-collection-item__note", ".ps-card--paper .ps-collection-item__image figcaption"]) {
      const fg = topRule(selector, "color");
      expect(ratio(fg, lightCard, "light"), `${selector} 浅色`).toBeGreaterThanOrEqual(4.5);
      expect(ratio(fg, "var(--paper)", "dark"), `${selector} 深色`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("纸质纪念卡：卡底是纸色；名字压在画面带上，TA 的话、日期、状态说明压在卡底上，浅深两套都 ≥ 4.5:1", () => {
    const card = topRule(".ps-memento", "background");
    const scene = topRule(".ps-memento__scene", "background");
    for (const scheme of ["light", "dark"] as const) {
      expect(ratio(topRule(".ps-memento__name", "color"), scene, scheme), `名字 ${scheme}`).toBeGreaterThanOrEqual(4.5);
      for (const selector of [".ps-memento__quote", ".ps-memento__foot", ".ps-memento__status"]) {
        expect(ratio(topRule(selector, "color"), card, scheme), `${selector} ${scheme}`).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it("明信片占位框（没有自拍时）的字：两种条纹底上都 ≥ 4.5:1（条纹是固定色，浅深一样）", () => {
    const stripes = topRule(".ps-collection-item__envelope", "background").match(/#[0-9a-f]{6}/gi) ?? [];
    expect(stripes.length).toBeGreaterThanOrEqual(2);
    const fg = topRule(".ps-collection-item__envelope", "color");
    for (const stripe of stripes) for (const scheme of ["light", "dark"] as const) expect(ratio(fg, stripe, scheme), `${stripe} ${scheme}`).toBeGreaterThanOrEqual(4.5);
  });

  it("借车券“怎么用”：标签与正文压在 --c-surface 上", () => {
    const bg = topRule(".ps-voucher-use", "background");
    for (const scheme of ["light", "dark"] as const) {
      expect(ratio(topRule(".ps-voucher-use__label", "color"), bg, scheme), `标签 ${scheme}`).toBeGreaterThanOrEqual(4.5);
      expect(ratio(topRule(".ps-voucher-use p", "color"), bg, scheme), `正文 ${scheme}`).toBeGreaterThanOrEqual(4.5);
    }
  });
});

describe("两只宠物：跟着当前这一只走", () => {
  const PETS = [pet("pet-1", "栗子"), pet("pet-2", "豆豆")];
  const byPet: Collection = async (petId) => (petId === "pet-2" ? [{ ...VOUCHER, item_id: "it-v2", note: "豆豆的券：第一次自己开车兜风时不用租车费" }] : [VOUCHER]);

  it("驾照页：当前是豆豆，就读豆豆的收藏、写豆豆的券", async () => {
    sessionStorage.setItem("petsoul:current-pet:u-1", "pet-2");
    const collection = vi.fn<Collection>(byPet);
    renderLive("/credentials/cr-dl", collection, PETS);
    const line = await screen.findByTestId("license-voucher");
    expect(line.textContent).toContain("豆豆的券");
    expect(line.textContent).not.toContain(VOUCHER_NOTE);
    expect(screen.getByTestId("license-use").textContent).toContain("豆豆有资格");
    expect(collection.mock.calls.every(([petId]) => petId === "pet-2")).toBe(true);
  });

  it("收藏页：当前是豆豆，列的是豆豆的借车券；标签与纪念卡写的也是豆豆", async () => {
    sessionStorage.setItem("petsoul:current-pet:u-1", "pet-2");
    const collection = vi.fn<Collection>(async (petId) => [...(await byPet(petId)), PHOTO_PAPER]);
    renderLive("/collection", collection, PETS);
    const use = await screen.findByTestId("voucher-use");
    expect(use.textContent).toContain("豆豆的券");
    expect(screen.getByText("绑定豆豆，不能交易")).toBeTruthy();
    const memento = screen.getByTestId("license-memento");
    expect(memento.getAttribute("aria-label")).toBe("豆豆和龟教练·慢慢的领证纪念卡");
    expect(within(memento).getByTestId("memento-pet").textContent).toBe("豆豆");
    expect(screen.queryByText("绑定栗子，不能交易")).toBeNull();
    expect(collection.mock.calls.every(([petId]) => petId === "pet-2")).toBe(true);
  });
});
