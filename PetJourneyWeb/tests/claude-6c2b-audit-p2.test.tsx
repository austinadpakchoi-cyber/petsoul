/**
 * claude-6c2b · 2026-09-24 全站巡检第二批 P2（主窗口派单）：
 * 1. 入住选地方：只列能选的；卡片按接口给的城市写“安家在香港”（原来“可能落在 香港”）；没开放的不一一列出，只说“更多地方以后开放。”
 * 2. 欢迎页：影片区铺满整屏（原来一律扣 26px，生产没有模式条，底部露一条浅色边）；有模式条时照旧扣掉它。
 * 3. 到家那句的出处：欢迎语没有来源字段，不标出处；“来自你确认过的生活叮嘱”只写在细节（各带叮嘱编号）上面，没有细节就不写。
 * 4. 通讯器：送达状态只写主人发出的消息；TA 发来的不写“已送达 TA 的世界”，图没画成也不写“没送出去”。
 * 5. 接待页：输入说明放在对话前面，不再卡在贴底区上沿；矮屏头图收矮，首屏让出“先认识 X”。
 * 样式断言只读 CSS 文件（jsdom 不排版）；变异自检可用 P2_IDENTITY_CSS / P2_RECEPTION_CSS / P2_HOME_CSS 指向副本。版面由 live 截图核对。
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import type { HabitatOption, HomePlaceView, HomeSnapshot, HouseholdBrief, HouseholdPetBrief, MessageSummary, MessageThread, OnboardingState, PetPublicProfile, ReceptionSession, SessionState, WelcomeDetail } from "@/shared/contracts";
import { ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { HouseholdProvider } from "@/shared/session/householdContext";
import { fixtureHomeSnapshot } from "@/fixtures/home";
import { habitatWhere, MoveInPage } from "@/features/identity/pages";
import { ArrivalMoment } from "@/features/home/ArrivalMoment";
import { HomeWelcomeBanner } from "@/features/home/HomeWelcomeBanner";
import { ReceptionPage } from "@/features/reception/ReceptionPage";
import communicatorModule from "@/features/communicator/module";
import { demoAnnouncementFeed } from "@/features/communicator/announcements";

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

/* ---------------- 工具 ---------------- */

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

/** 读样式表（去掉注释）；变异自检时由环境变量指向副本。 */
function cssOf(envKey: string, rel: string): string {
  return readFileSync(process.env[envKey] ?? resolve(ROOT, rel), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
}

/** 取某条规则的声明（选择器按空白归一后全等；context 是所在的 @media，顶层为空串）。找不到返回 null。 */
function declarationsOf(text: string, selector: string, context = ""): Map<string, string> | null {
  const stack: string[] = [];
  let buf = "";
  for (const ch of text) {
    if (ch === "{") {
      stack.push(buf.trim().replace(/\s+/g, " "));
      buf = "";
    } else if (ch === "}") {
      const prelude = stack.pop() ?? "";
      const ctx = stack.filter((s) => s.startsWith("@")).join(" ");
      if (!prelude.startsWith("@") && prelude === selector && ctx === context) {
        const map = new Map<string, string>();
        for (const part of buf.split(";")) {
          const at = part.indexOf(":");
          if (at > 0) map.set(part.slice(0, at).trim(), part.slice(at + 1).trim());
        }
        return map;
      }
      buf = "";
    } else {
      buf += ch;
    }
  }
  return null;
}

/**
 * 同一个选择器分几条写时（例如排版一条、颜色一条）按出现顺序合并，后写的覆盖先写的——与浏览器对同权重规则的取法一致。
 * 只给“注册 / 登录纸色表单的原色”那两条用：删掉“认识 TA”那一半选择器后，它们和前面的排版规则同名了（claude-6c2b 2026-09-25）。
 */
function mergedDeclarationsOf(text: string, selector: string, context = ""): Map<string, string> {
  const merged = new Map<string, string>();
  const stack: string[] = [];
  let buf = "";
  for (const ch of text) {
    if (ch === "{") {
      stack.push(buf.trim().replace(/\s+/g, " "));
      buf = "";
    } else if (ch === "}") {
      const prelude = stack.pop() ?? "";
      const ctx = stack.filter((s) => s.startsWith("@")).join(" ");
      if (!prelude.startsWith("@") && prelude === selector && ctx === context) {
        for (const part of buf.split(";")) {
          const at = part.indexOf(":");
          if (at > 0) merged.set(part.slice(0, at).trim(), part.slice(at + 1).trim());
        }
      }
      buf = "";
    } else {
      buf += ch;
    }
  }
  return merged;
}

function strict(services: Record<string, unknown>): ServiceMap {
  return new Proxy(services as unknown as ServiceMap, {
    get(target, prop: string) {
      if (prop in target) return target[prop as keyof ServiceMap];
      throw new Error(`unexpected service ${prop}`);
    },
  });
}

function renderWith(element: React.ReactNode, services: Record<string, unknown>, entry: string, path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={strict(services)}>
        <MemoryRouter initialEntries={[entry]}>
          <Routes>
            <Route path={path} element={element} />
          </Routes>
        </MemoryRouter>
      </ServicesProvider>
    </QueryClientProvider>,
  );
}

const USER = "owner-1";
function onboardingAt(step: OnboardingState["step"], petId = "pet-1", receptionSessionId: string | null = null): OnboardingState {
  return { step, pet_id: petId, home_id: "home-1", reception_session_id: receptionSessionId, reception_skipped: false, home_activated_at: null, pet_origin: "own_pet" };
}
function signedIn(step: OnboardingState["step"], receptionSessionId: string | null = null): SessionState {
  return { authenticated: true, user: { user_id: USER, username: "lin", display_name: null, auth_method: "web_password" }, csrf_required: false, expires_at: null, onboarding: onboardingAt(step, "pet-1", receptionSessionId) };
}
const profile = { pet_id: "pet-1", display_name: "花生", species: "dog", avatar_url: null } as unknown as PetPublicProfile;

/* ---------------- 1. 入住选地方 ---------------- */

describe("入住选地方：只列能选的，按接口给的城市写清楚安家在哪", () => {
  const option = (examples: string[]): HabitatOption => ({ habitat: "seaside", label: "海边", examples, open: true });

  it.each([
    [["香港"], "安家在香港"],
    [["厦门", "青岛"], "安家在厦门或青岛"],
    [["厦门", "青岛", "三亚"], "安家在厦门、青岛或三亚"],
    [[" 香港 "], "安家在香港"],
    [[], "由星球安排片区"],
  ])("城市 %j → “%s”（不写“可能落在”，不多空格）", (examples, text) => {
    expect(habitatWhere(option(examples))).toBe(text);
  });

  function placeView(options: HabitatOption[]): HomePlaceView {
    return {
      place: { habitat: "city", habitat_label: "城市", city: "香港", area_label: "中环", display: "香港·中环", timezone: "Asia/Hong_Kong", chosen: false },
      options,
      can_change: true,
    };
  }
  const OPEN: HabitatOption[] = [
    { habitat: "seaside", label: "海边", examples: ["香港"], open: true },
    { habitat: "city", label: "城市", examples: ["香港"], open: true },
  ];
  const CLOSED: HabitatOption[] = [
    { habitat: "grassland", label: "草原", examples: ["呼伦贝尔"], open: false },
    { habitat: "desert", label: "沙漠", examples: ["敦煌"], open: false },
    { habitat: "forest", label: "森林", examples: ["西双版纳"], open: false },
  ];
  function renderMoveIn(options: HabitatOption[]) {
    return renderWith(<MoveInPage />, {
      session: { current: async () => signedIn("ready_to_move_in"), homePlace: async () => placeView(options), moveIn: vi.fn() },
      pets: { publicProfile: async () => profile },
    }, "/onboarding/move-in", "/onboarding/move-in");
  }

  it("有没开放的类型：卡片写“安家在香港”；没开放的一个都不列，只有一句“更多地方以后开放。”", async () => {
    renderMoveIn([...OPEN, ...CLOSED]);
    const choices = await screen.findByRole("group", { name: "选择家的环境" });
    expect(within(choices).getAllByRole("button").map((b) => b.querySelector("small")?.textContent)).toEqual(["安家在香港", "安家在香港"]);
    expect(screen.getAllByText("更多地方以后开放。")).toHaveLength(1);
    const section = choices.closest("section")!;
    for (const word of ["草原", "沙漠", "森林", "还没开放", "可能落在"]) expect(section.textContent).not.toContain(word);
  });

  it("全都开放：不说“更多地方以后开放。”", async () => {
    renderMoveIn(OPEN);
    await screen.findByRole("group", { name: "选择家的环境" });
    expect(screen.queryByText("更多地方以后开放。")).toBeNull();
  });
});

/* ---------------- 2. 欢迎页铺满 ---------------- */

describe("欢迎页：影片区铺满整屏", () => {
  const css = () => cssOf("P2_IDENTITY_CSS", "src/features/identity/identity.css");
  it("没有模式条（生产）：最小高度就是整屏 100dvh，不再扣 26px", () => {
    expect(declarationsOf(css(), ".ps-welcome-page")?.get("min-height")).toBe("100dvh");
  });
  it("顶上有模式条（演示 / 开发）：扣掉模式条的高度，与原来一样", () => {
    expect(declarationsOf(css(), ".ps-ribbon + .ps-welcome-page")?.get("min-height")).toBe("calc(100dvh - 26px)");
  });
});

/* ---------------- 3. 到家那句的出处 ---------------- */

describe("到家那句：欢迎语不标出处，只有细节标“来自你确认过的生活叮嘱”", () => {
  const SOURCE = "来自你确认过的生活叮嘱";
  function snapshotWith(details: WelcomeDetail[]): HomeSnapshot {
    const base = fixtureHomeSnapshot();
    return {
      ...base,
      presence: "at_home",
      pet: { ...base.pet, pet_id: "pet-1", name: "花生", photo_url: null },
      welcome: { pet_id: "pet-1", confirmation_id: "cf-1", projection_version: 1, greeting: "我到家啦，这里闻起来像你。", details },
    } as HomeSnapshot;
  }
  const detail = { kind: "favorite_object" as const, text: "窗台上的软垫", note_id: "n-1", note_version: 1 };

  it("到家时刻 · 只有欢迎语（叮嘱是“听到零食袋会跑过来”，没投影出细节）：不写出处", () => {
    render(<ArrivalMoment snapshot={snapshotWith([])} onClose={vi.fn()} />);
    const dialog = screen.getByRole("dialog", { name: "花生 到家了" });
    expect(within(dialog).getByText("“我到家啦，这里闻起来像你。”")).toBeTruthy();
    expect(within(dialog).queryByText(SOURCE)).toBeNull();
  });

  it("到家时刻 · 有细节：出处写在细节上面、和细节在一起，欢迎语不在这一块里", () => {
    render(<ArrivalMoment snapshot={snapshotWith([detail])} onClose={vi.fn()} />);
    const dialog = screen.getByRole("dialog", { name: "花生 到家了" });
    const label = within(dialog).getByText(SOURCE);
    const notes = label.closest(".ps-arrival__notes") as HTMLElement;
    expect(notes).not.toBeNull();
    expect(within(notes).getByRole("list", { name: "家里会记着" }).textContent).toBe("窗台上的软垫");
    expect(notes.textContent).not.toContain("我到家啦");
    expect(label.compareDocumentPosition(within(notes).getByRole("list")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("家里的欢迎卡 · 只有欢迎语：不写出处", () => {
    render(<HomeWelcomeBanner snapshot={snapshotWith([])} />);
    const card = screen.getByTestId("home-welcome");
    expect(card.textContent).toContain("我到家啦，这里闻起来像你。");
    expect(card.textContent).not.toContain(SOURCE);
  });

  it("家里的欢迎卡 · 有细节：出处和细节在一起，欢迎语不在这一块里", () => {
    render(<HomeWelcomeBanner snapshot={snapshotWith([detail])} />);
    const card = screen.getByTestId("home-welcome");
    const notes = card.querySelector(".ps-welcome__notes") as HTMLElement;
    expect(notes?.textContent).toContain(SOURCE);
    expect(notes.textContent).toContain("窗台上的软垫");
    expect(notes.textContent).not.toContain("我到家啦");
  });

  it("欢迎卡是纸卡：出处这行用纸墨（深色主题下不变浅）", () => {
    const color = declarationsOf(cssOf("P2_HOME_CSS", "src/features/home/home.css"), ".ps-welcome__meta")?.get("color") ?? "";
    expect(color).toMatch(/^var\(--paper/);
  });
});

/* ---------------- 4. 通讯器的送达状态 ---------------- */

describe("通讯器：送达状态只写主人发出的消息", () => {
  const pet: HouseholdPetBrief = { pet_id: "pet-1", name: "花生", species: "dog", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-24T00:00:00Z", added_by_you: true };
  const households: HouseholdBrief[] = [{ household_id: "hh-1", name: null, home_id: "home-1", role: "admin", home_activated: true, member_count: 1, pets: [pet] }];
  function message(id: string, over: Partial<MessageSummary>): MessageSummary {
    return { message_id: id, client_message_id: null, sender: "pet", text: id, state: "delivered", created_at: "2026-09-24T00:00:00Z", photo_url: null, channel: "private", ...over } as MessageSummary;
  }
  function renderThread(items: MessageSummary[], entry = "/communicator") {
    const base = fixtureHomeSnapshot();
    const thread: MessageThread = { pet_id: "pet-1", items, next_cursor: null, data_origin: "live" };
    const element = communicatorModule.routes!.find((route) => route.path === "communicator")!.element;
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <ServicesProvider services={strict({
          households: { list: async () => households },
          world: { home: async () => ({ ...base, pet: { ...base.pet, pet_id: "pet-1", name: "花生" }, data_origin: "live" }) },
          communicator: { thread: async () => thread, send: vi.fn(), announcements: async () => demoAnnouncementFeed() },
          transport: { guides: async () => [] },
          economy: { collection: async () => [] },
          social: { friends: async () => [] },
        })}>
          <MemoryRouter initialEntries={[entry]}>
            <HouseholdProvider userId={USER}>
              <Routes>
                <Route path="/communicator" element={element} />
              </Routes>
            </HouseholdProvider>
          </MemoryRouter>
        </ServicesProvider>
      </QueryClientProvider>,
    );
  }
  const bubble = async (text: string) => (await screen.findByText(text)).closest(".ps-msg") as HTMLElement;
  const stateOf = (b: HTMLElement) => b.querySelector(".ps-msg__state")?.textContent ?? null;

  it("主人发出的：已送达写“已送达 TA 的世界”，等回复写后端给的说明", async () => {
    renderThread([
      message("今天吃了吗", { sender: "owner", state: "delivered" }),
      message("晚安", { sender: "owner", state: "awaiting_reply", status_note: "TA 睡着啦，醒来会看到" }),
    ]);
    expect(stateOf(await bubble("今天吃了吗"))).toBe("已送达 TA 的世界");
    expect(stateOf(await bubble("晚安"))).toBe("TA 睡着啦，醒来会看到");
  });

  it("TA 发来的：不写“已送达 TA 的世界”；随信的图没画成也不写“没送出去”（图的情况上面单独写了）", async () => {
    renderThread([
      message("吃啦！", { state: "delivered" }),
      message("给你看我拍的", { state: "failed", photo_status: "failed" }),
      message("在画了", { state: "processing", photo_status: "processing" }),
    ]);
    for (const text of ["吃啦！", "给你看我拍的", "在画了"]) {
      const b = await bubble(text);
      expect(stateOf(b)).toBeNull();
      expect(b.textContent).not.toMatch(/已送达 TA 的世界|没送出去|照片冲洗中/);
    }
    expect((await bubble("给你看我拍的")).textContent).toContain("随信画面未生成成功，文字已送达");
  });

  it("家庭频道：TA 发来的只标“家庭频道”，主人发出的标“已送达 TA 的世界 · 家庭频道”", async () => {
    renderThread([
      message("全家好", { channel: "family" }),
      message("收到", { sender: "owner", channel: "family" }),
    ], "/communicator?channel=family");
    expect(stateOf(await bubble("全家好"))).toBe("家庭频道");
    expect(stateOf(await bubble("收到"))).toBe("已送达 TA 的世界 · 家庭频道");
  });
});

/* ---------------- 5. 接待页的输入说明与矮屏 ---------------- */

describe("接待页：输入说明在对话前面；矮屏头图收矮", () => {
  const receptionSession: ReceptionSession = {
    session_id: "rs-1", pet_id: "pet-1", branch: "own_pet", mode: "guided_notes", status: "active",
    host: { host_id: "h", display_name: "星球接待员", role_label: "PetSoul 的 AI 接待角色", avatar_url: null, is_ai: true, disclosure: "我是 AI 接待角色。" },
    turns: [{ turn_id: "t-1", seq: 1, speaker: "host", text: "有什么想交代的吗？", created_at: "2026-09-24T00:00:00Z" }],
    candidates: [], draft_revision: 1, draft_expires_at: null, data_origin: "live",
  };

  it("说明在“你和接待员”下面、对话前面，输入框的读屏说明仍连着它", async () => {
    renderWith(<ReceptionPage />, {
      session: { current: async () => signedIn("reception_optional", "rs-1") },
      pets: { publicProfile: async () => profile },
      reception: { start: vi.fn(async () => receptionSession), get: async () => receptionSession, skip: vi.fn() },
      world: { home: vi.fn() },
    }, "/onboarding/reception", "/onboarding/reception");
    const turns = await screen.findByRole("list", { name: "接待对话" });
    const hint = document.getElementById("reception-input-hint")!;
    expect(hint.textContent).toBe("说一件，就整理成一条待你确认的叮嘱；不说也可以，以后还能补充");
    expect(hint.compareDocumentPosition(turns) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(hint.parentElement?.lastElementChild).not.toBe(hint);
    expect(screen.getByLabelText("再交代一件小事").getAttribute("aria-describedby")).toBe("reception-input-hint");
  });

  it("矮屏（高不过 640px）头图收到 140px 以内，头像卡跟着上移；高屏的头图规则不变", () => {
    const css = cssOf("P2_RECEPTION_CSS", "src/features/reception/reception.css");
    const short = declarationsOf(css, ".ps-reception-hero__scene", "@media (max-height: 640px)");
    expect(short).not.toBeNull();
    expect(Number.parseFloat(short!.get("height") ?? "999")).toBeLessThanOrEqual(140);
    expect(Number.parseFloat(declarationsOf(css, ".ps-reception-portrait", "@media (max-height: 640px)")?.get("top") ?? "999")).toBeLessThanOrEqual(48);
    expect(declarationsOf(css, ".ps-reception-hero__scene")?.get("height")).toBe("clamp(176px, 52vw, 280px)");
  });
});

/* ---------------- 6. 入住流程各页跟着主题（切换栏分身发现、主窗口追加） ---------------- */

describe("入住流程各页的底色、标题、入住页卡片跟着主题，不写死颜色", () => {
  const HARDCODED = /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\(|(?<![\w-])(?:white|black)(?![\w-])/;
  const css = () => cssOf("P2_IDENTITY_CSS", "src/features/identity/identity.css");
  // 选择器 → 要检查的颜色属性（这些属性必须来自主题变量 var(--c-…)，整条规则里不许出现写死的颜色）
  const THEMED: Array<[string, string[]]> = [
    [".ps-entry-page", ["background"]],
    [".ps-entry-heading", ["color"]],
    [".ps-entry-heading__kicker", ["color"]],
    [".ps-entry-heading p", ["color"]],
    [".ps-entry-heading__steps span", ["background"]],
    [".ps-entry-heading__steps span.is-active", ["background"]],
    [".ps-entry-dock", ["background"]],
    [".ps-entry-dock__hint", ["color"]],
    [".ps-entry-dock__error span", ["color"]],
    [".ps-movein-page", ["background"]],
    [".ps-movein-hero", ["border", "background", "color", "box-shadow"]],
    [".ps-movein-hero__pet", ["border", "background", "color", "box-shadow"]],
    [".ps-movein-hero__pet small", ["background", "color"]],
    [".ps-movein-hero__kicker", ["color"]],
    [".ps-movein-hero p", ["color"]],
    [".ps-movein-section", ["color"]],
    [".ps-movein-note", ["color"]],
    [".ps-movein-closed", ["color"]],
    [".ps-habitat-card", ["border", "background", "color", "box-shadow"]],
    [".ps-habitat-card:focus-visible", ["outline"]],
    [".ps-habitat-card.is-selected", ["border-color", "box-shadow"]],
    [".ps-habitat-card__art", ["background", "color"]],
    [".ps-habitat-card.is-seaside .ps-habitat-card__art, .ps-habitat-card.is-lakeside .ps-habitat-card__art", ["background", "color"]],
    [".ps-habitat-card.is-city .ps-habitat-card__art", ["background", "color"]],
    [".ps-habitat-card__check", ["background", "color"]],
    [".ps-habitat-card small", ["color"]],
    [".ps-switch-row", ["border", "background"]],
    [".ps-switch-row strong", ["color"]],
    [".ps-switch-row small", ["color"]],
    [".ps-switch", ["background"]],
    [".ps-switch::after", ["background", "box-shadow"]],
    [".ps-switch:checked", ["background"]],
    [".ps-switch:focus-visible", ["outline"]],
    [".ps-movein-away", ["border", "background", "color"]],
    [".ps-movein-away strong", ["color"]],
  ];

  it.each(THEMED)("%s：颜色来自主题变量，没有写死的颜色", (selector, props) => {
    const rule = declarationsOf(css(), selector);
    expect(rule, `找不到规则 ${selector}`).not.toBeNull();
    for (const [prop, value] of rule!) expect(HARDCODED.test(value), `${selector} { ${prop}: ${value} }`).toBe(false);
    for (const prop of props) expect(rule!.get(prop) ?? "", `${selector} 的 ${prop}`).toMatch(/var\(--c-/);
  });

  it("贴底区的渐变收在所在页面的底色上：入住页把自己的底色告诉贴底区", () => {
    expect(declarationsOf(css(), ".ps-entry-dock")?.get("background")).toContain("var(--entry-dock-bg, var(--c-surface))");
    const page = declarationsOf(css(), ".ps-movein-page");
    expect(page?.get("--entry-dock-bg")).toBe(page?.get("background"));
  });

  it("深色主题下，跟着变深的入住页上字标换成浅色；注册 / 登录的纸色表单上照旧用原色", () => {
    const dark = "@media (prefers-color-scheme: dark)";
    expect(declarationsOf(css(), ".ps-entry-page .ps-entry-heading .ps-brand-logo > img", dark)?.get("filter") ?? "").toContain("invert(1)");
    expect(declarationsOf(css(), ".ps-auth-sheet .ps-entry-heading .ps-brand-logo > img", dark)?.get("filter")).toBe("none");
  });

  it("固定暖纸底上的标题（注册 / 登录的纸色表单）仍是深墨，深色主题下不变浅", () => {
    const fixed = mergedDeclarationsOf(css(), ".ps-auth-sheet .ps-entry-heading");
    expect(fixed?.get("color")).toBe("#292827");
    expect(mergedDeclarationsOf(css(), ".ps-auth-sheet .ps-entry-heading p")?.get("color")).toBe("#7e756d");
  });
});
