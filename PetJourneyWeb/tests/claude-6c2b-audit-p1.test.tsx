/**
 * claude-6c2b · 巡检 P1（2026-09-24）：
 * 1) 朋友圈 /circle：每张卡的小标签只用中文（social.css 的 .ps-post::before，原来是“朋友圈 JOURNAL”）；
 *    老数据里同一位作者一字不差、都没带照片的几条只留最新一条（feed.ts 的 collapseRepeats；新的重复后端已经挡住）。
 * 2) 给玩家看的出错、未开放说法：
 *    - 还没开放（CAPABILITY_UNAVAILABLE / NOT_CONFIGURED）→ “这里暂时还没开放 / 准备好了会出现在这里”，能力名只在收起的“技术信息”里；
 *    - 后端没有这条路（路由级 404/405，原话“没有找到这个接口。”、不带 details）→ 标题“没有找到”＋一句人话，原话与错误码只在“技术信息”里；
 *    - 业务上的“找不到”（后端带 resource / reason，原话如“没有找到这张证件。”）照用原话：它本来就是写给玩家的，比笼统的一句清楚。
 * 3) 集市锁卡：家与家之间买卖没开放时用前端自己的一句，不显示后端那句带开发安排的原话（“主线稳定后再评估……”）。
 * （/me/look 没照片的死胡同在 tests/claude-6c2b-look.test.tsx；说法守卫在 tests/claude-6c2b-ui-wording.test.ts。）
 * 4) 程序自己出的错（23:5x，驾驶分身转）：toApiError 包进来的异常（TypeError 之类）玩家只看“操作暂时没有完成，请重试。”，原文只进“技术信息”，
 *    出错页标题也不说“信号暂时中断”；真的网络失败（client.ts 自己造的）照旧是中文原话与“信号暂时中断”。
 * AUDIT_P1_SOCIAL_CSS 只给变异对照指到副本用。
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, MemoryRouter, RouterProvider } from "react-router";
import type { MarketView, Post, WebErrorEnvelope } from "@/shared/contracts";
import { ApiError, PLAYER_ERROR_TEXT, toApiError } from "@/shared/api/errors";
import { createApiClient } from "@/shared/api/client";
import { loadFeatureModules } from "@/app/modules";
import { buildRoutes } from "@/app/router";
import { buildServices, ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { ErrorState } from "@/shared/ui";
import { collapseRepeats } from "@/features/social/feed";
import { LISTING_CLOSED } from "@/features/collection/module";
import { fixtureMarket } from "@/fixtures/home";

// 同一个文件里要切 fixture / live：env 用 getter 读一个可改的开关。
const mode = vi.hoisted(() => ({ dataMode: "fixture" as "fixture" | "live" }));
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
  mode.dataMode = "fixture";
  sessionStorage.clear();
  vi.stubGlobal("scrollTo", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

/** 给玩家看的页面上不该出现的开发说法（与 ui-wording 守卫的 TECH 同一组，外加“能力”“NOT_FOUND”）。 */
const DEV_WORDS = /接口|搭建中|未接入|能力|NOT_FOUND|CAPABILITY/;

/* ---------------- 1) 朋友圈：老数据的重复只留最新一条 ---------------- */

const SAME_LINE = "在家附近的星球小路待了一会儿。香港的风很舒服。";

function post(id: string, over: { author?: string; kind?: Post["author"]["actor_kind"]; text?: string; at: string; media?: Post["media"] }): Post {
  const actorId = over.author ?? "pet-qiuqiu";
  return {
    post_id: id,
    author: { actor_kind: over.kind ?? "pet", actor_id: actorId, display_name: actorId === "pet-qiuqiu" ? "秋秋" : "团子", avatar_url: null, is_real_household: true },
    text: over.text ?? SAME_LINE,
    media: over.media ?? [],
    source_event_id: `ev-${id}`,
    visit_id: null,
    visibility: "public",
    created_at: over.at,
    reaction_count: 0,
    comment_count: 1,
    viewer_reacted: false,
    data_origin: "live",
  };
}

const PHOTO = (id: string): Post["media"] => [{ media_id: `m-${id}`, kind: "image", url: `/api/v1/web/media/posts/${id}.png`, alt: "在小路上", generated: true }];
const ids = (posts: Post[]) => posts.map((p) => p.post_id);

describe("朋友圈：同一作者一字不差、没带照片的只留最新一条（collapseRepeats）", () => {
  it("同一作者连发 5 条同一句：只留最新一条；别的动态照留，先后不变", () => {
    const feed = [
      post("p5", { at: "2026-09-24T05:18:00Z" }),
      post("t1", { author: "pet-tuanzi", text: "今天在菜园浇了水。", at: "2026-09-24T04:00:00Z" }),
      post("p4", { at: "2026-09-24T02:18:00Z" }),
      post("p3", { at: "2026-09-23T23:18:00Z" }),
      post("p2", { at: "2026-09-23T20:18:00Z" }),
      post("p1", { at: "2026-09-23T17:18:00Z" }),
    ];
    expect(ids(collapseRepeats(feed))).toEqual(["p5", "t1"]);
  });

  it("按发布时间认“最新”，不按在列表里的位置", () => {
    const feed = [post("old", { at: "2026-09-23T17:18:00Z" }), post("new", { at: "2026-09-24T05:18:00Z" })];
    expect(ids(collapseRepeats(feed))).toEqual(["new"]);
  });

  it("别的作者说了同一句不算重复；同一个编号但身份不同（宠物 / 主人）也不算同一位作者", () => {
    const feed = [
      post("a", { at: "2026-09-24T05:00:00Z" }),
      post("b", { author: "pet-tuanzi", at: "2026-09-24T04:00:00Z" }),
      post("c", { kind: "owner", at: "2026-09-24T03:00:00Z" }),
    ];
    expect(ids(collapseRepeats(feed))).toEqual(["a", "b", "c"]);
  });

  it("带照片的一律照留（照片各不相同），也不把同一句没照片的那条挤掉", () => {
    const feed = [
      post("photo2", { at: "2026-09-24T05:00:00Z", media: PHOTO("photo2") }),
      post("photo1", { at: "2026-09-24T04:00:00Z", media: PHOTO("photo1") }),
      post("plain2", { at: "2026-09-24T03:00:00Z" }),
      post("plain1", { at: "2026-09-24T02:00:00Z" }),
    ];
    expect(ids(collapseRepeats(feed))).toEqual(["photo2", "photo1", "plain2"]);
  });

  it("去掉首尾空白后比；中间差一个字就不算一字不差", () => {
    const feed = [
      post("n", { at: "2026-09-24T05:00:00Z", text: `  ${SAME_LINE}\n` }),
      post("o", { at: "2026-09-24T04:00:00Z" }),
      post("x", { at: "2026-09-24T03:00:00Z", text: SAME_LINE.replace("小路", "小径") }),
    ];
    expect(ids(collapseRepeats(feed))).toEqual(["n", "x"]);
  });

  it("没有动态时是空的；不改动传进来的数组", () => {
    expect(collapseRepeats([])).toEqual([]);
    const feed = [post("b", { at: "2026-09-24T05:00:00Z" }), post("a", { at: "2026-09-24T04:00:00Z" })];
    const copy = [...feed];
    collapseRepeats(feed);
    expect(feed).toEqual(copy);
  });
});

/* ---------------- 页面渲染（演示模式经真实路由表，替换其中一个服务） ---------------- */

function renderApp(path: string, override: (base: ServiceMap) => Partial<ServiceMap>) {
  const modules = loadFeatureModules();
  const base = buildServices(modules, { mode: "fixture", api: createApiClient("/api/v1/web") });
  const services = { ...base, ...override(base) } as ServiceMap;
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

describe("朋友圈页（/circle）：老数据的重复在页面上只剩一条", () => {
  it("同一作者 5 条一字不差的只显示最新那条（它的评论入口指向最新那条），别的动态照常", async () => {
    const feed = vi.fn(async () => ({
      items: [
        post("p5", { at: "2026-09-24T05:18:00Z" }),
        post("t1", { author: "pet-tuanzi", text: "今天在菜园浇了水。", at: "2026-09-24T04:00:00Z" }),
        post("p4", { at: "2026-09-24T02:18:00Z" }),
        post("p3", { at: "2026-09-23T23:18:00Z" }),
        post("p2", { at: "2026-09-23T20:18:00Z" }),
        post("p1", { at: "2026-09-23T17:18:00Z" }),
      ],
      next_cursor: null,
    }));
    renderApp("/circle", (base) => ({ social: { ...base.social, feed } }));
    const threads = await screen.findAllByRole("link", { name: /查看评论/ });
    expect(threads.map((link) => link.getAttribute("href"))).toEqual(["/posts/p5", "/posts/t1"]);
    expect(document.querySelectorAll(".ps-post")).toHaveLength(2);
    expect(screen.getAllByText(SAME_LINE)).toHaveLength(1);
    expect(screen.getByText("今天在菜园浇了水。")).toBeTruthy();
    expect(feed).toHaveBeenCalledTimes(1);
  });
});

describe("朋友圈卡片的小标签只用中文（social.css）", () => {
  const cssFile = process.env.AUDIT_P1_SOCIAL_CSS ?? resolve(dirname(fileURLToPath(import.meta.url)), "..", "src", "features", "social", "social.css");
  const css = readFileSync(cssFile, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

  it(".ps-post::before 写的是“朋友圈”，没有英文字母", () => {
    const contents = [...css.matchAll(/\.ps-post::?before\s*\{([^}]*)\}/g)].flatMap((m) => [...m[1].matchAll(/content\s*:\s*("[^"]*"|'[^']*')/g)].map((c) => c[1].slice(1, -1)));
    expect(contents).toEqual(["朋友圈"]);
    // 整份样式里凡是 content 写了字的，都不许带英文字母（防止换个选择器又把 JOURNAL 加回来）。
    const allContents = [...css.matchAll(/content\s*:\s*("[^"]*"|'[^']*')/g)].map((c) => c[1].slice(1, -1));
    for (const text of allContents) expect(text, text).not.toMatch(/[A-Za-z]/);
  });
});

/* ---------------- 2) 出错与未开放的说法 ---------------- */

function envelope(code: WebErrorEnvelope["error"]["code"], message: string, details: Record<string, unknown> | null, requestId = "req_p1_0001"): WebErrorEnvelope {
  return { error: { code, message, request_id: requestId, retryable: false, details } };
}

/** 后端真实会给的几种（web_platform/errors.py）：路由级 404/405 不带 details；WebAPIError.not_found 带 resource；能力没开 501 带 capability。 */
const ROUTE_404 = () => ApiError.fromEnvelope(404, envelope("NOT_FOUND", "没有找到这个接口。", null), null);
const ROUTE_405 = () => ApiError.fromEnvelope(405, envelope("NOT_FOUND", "没有找到这个接口。", null), null);
const RESOURCE_404 = () => ApiError.fromEnvelope(404, envelope("NOT_FOUND", "没有找到这张证件。", { resource: "这张证件" }), null);
const REASON_404 = () => ApiError.fromEnvelope(404, envelope("NOT_FOUND", "TA 还没出过门。", { reason: "no_journey" }), null);
const CAPABILITY_501 = () => ApiError.fromEnvelope(501, envelope("CAPABILITY_UNAVAILABLE", "这项能力尚未接入。", { capability: "food.recommendations", status: "not_implemented" }), null);
const NOT_CONFIGURED_503 = () => ApiError.fromEnvelope(503, envelope("NOT_CONFIGURED", "这项能力尚未接入。", { capability: "map.amap", status: "not_configured" }), null);

describe("ApiError.playerMessage：给玩家看的一句", () => {
  it("还没开放（未实现 / 未配置 / 前端自己判的）一律“这里暂时还没开放，准备好了会出现在这里。”", () => {
    for (const err of [CAPABILITY_501(), NOT_CONFIGURED_503(), ApiError.capability("food.recommendations")]) {
      expect(err.playerMessage).toBe(PLAYER_ERROR_TEXT.unavailable);
    }
    expect(ApiError.capability("x.y").message).toBe("这里暂时还没开放。");
  });

  it("后端没有这条路（404 / 405、不带 details）：换成人话，原话留在 message 里给“技术信息”", () => {
    for (const err of [ROUTE_404(), ROUTE_405()]) {
      expect(err.unknownRoute).toBe(true);
      expect(err.isNotFound).toBe(true);
      expect(err.playerMessage).toBe(PLAYER_ERROR_TEXT.notFound);
      expect(err.message).toBe("没有找到这个接口。");
    }
    // 空 details 也按路由级算
    expect(ApiError.fromEnvelope(404, envelope("NOT_FOUND", "没有找到这个接口。", {}), null).playerMessage).toBe(PLAYER_ERROR_TEXT.notFound);
  });

  it("业务上的找不到（带 resource / reason）、前端自己造的找不到、其余错误：照用原话", () => {
    expect(RESOURCE_404().playerMessage).toBe("没有找到这张证件。");
    expect(REASON_404().playerMessage).toBe("TA 还没出过门。");
    expect(RESOURCE_404().unknownRoute).toBe(false);
    const local = new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: "这条动态不存在或已撤下。" });
    expect(local.unknownRoute).toBe(false);
    expect(local.playerMessage).toBe("这条动态不存在或已撤下。");
    const conflict = ApiError.fromEnvelope(409, envelope("CONFLICT", "TA 正在路上，等回来再说。", { reason: "already_traveling" }), null);
    expect(conflict.playerMessage).toBe("TA 正在路上，等回来再说。");
    // 别的错误码的 404 形状（非 NOT_FOUND）不算路由级
    expect(ApiError.fromEnvelope(404, envelope("FORBIDDEN", "没有权限访问这项内容。", null), null).unknownRoute).toBe(false);
  });

  it("两句人话本身不带开发说法", () => {
    for (const text of Object.values(PLAYER_ERROR_TEXT)) expect(text, text).not.toMatch(DEV_WORDS);
  });
});

function renderError(error: unknown, onRetry?: () => void) {
  return render(
    <MemoryRouter>
      <ErrorState error={error} onRetry={onRetry} />
    </MemoryRouter>,
  );
}

/** 页面上拿掉收起的“技术信息”以后剩下的字（玩家平时看到的）。 */
function visibleText(container: HTMLElement): string {
  const rest = container.cloneNode(true) as HTMLElement;
  rest.querySelectorAll("details").forEach((node) => node.remove());
  return rest.textContent ?? "";
}

function techText(container: HTMLElement): string {
  const details = container.querySelector("details.ps-state__tech") as HTMLDetailsElement | null;
  expect(details).toBeTruthy();
  expect(details!.open).toBe(false);
  expect(details!.querySelector("summary")?.textContent).toBe("技术信息");
  return details!.querySelector(".ps-state__meta")?.textContent ?? "";
}

const title = (container: HTMLElement) => container.querySelector(".ps-state__title")?.textContent;

describe("ErrorState：还没开放、找不到都说人话，原话与错误码收进“技术信息”", () => {
  it("还没开放：“这里暂时还没开放 / 准备好了会出现在这里。”；能力名只在“技术信息”里，后端原话哪儿都不显示", () => {
    const { container } = renderError(CAPABILITY_501());
    expect(title(container)).toBe("这里暂时还没开放");
    expect(visibleText(container)).toContain("准备好了会出现在这里。");
    expect(visibleText(container)).not.toMatch(DEV_WORDS);
    expect(techText(container)).toBe("food.recommendations");
    expect(container.textContent).not.toContain("尚未接入");
    expect(container.querySelector(".ps-state--disabled")).toBeTruthy();
  });

  it("后端没有这条路（“没有找到这个接口。”）：标题“没有找到”＋人话，原话、NOT_FOUND、request_id 只在“技术信息”里", () => {
    const { container } = renderError(ROUTE_404(), () => undefined);
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(title(container)).toBe("没有找到");
    expect(visibleText(container)).toContain(PLAYER_ERROR_TEXT.notFound);
    expect(visibleText(container)).not.toMatch(DEV_WORDS);
    expect(visibleText(container)).not.toContain("没有找到这个接口");
    const tech = techText(container);
    expect(tech).toContain("NOT_FOUND");
    expect(tech).toContain("没有找到这个接口。");
    expect(tech).toContain("request_id req_p1_0001");
    expect(screen.getByRole("button", { name: "重试" })).toBeTruthy();
  });

  it("业务上的找不到：标题“没有找到”，正文照用后端写给玩家的原话；原话不在“技术信息”里重复", () => {
    const { container } = renderError(RESOURCE_404());
    expect(title(container)).toBe("没有找到");
    expect(visibleText(container)).toContain("没有找到这张证件。");
    expect(visibleText(container)).not.toContain(PLAYER_ERROR_TEXT.notFound);
    const tech = techText(container);
    expect(tech).toContain("NOT_FOUND");
    expect(tech).not.toContain("没有找到这张证件");
  });

  it("别的失败标题照旧是“没能完成这一步”，正文是原话", () => {
    const { container } = renderError(ApiError.fromEnvelope(409, envelope("CONFLICT", "TA 正在路上，等回来再说。", { reason: "already_traveling" }), null));
    expect(title(container)).toBe("没能完成这一步");
    expect(visibleText(container)).toContain("TA 正在路上，等回来再说。");
  });
});

/* ---------------- 3) 集市锁卡 ---------------- */

/** 后端原话（web_market/service.py 的 PLAYER_LISTING_NOTE）：带着开发安排，不给玩家看。 */
const SERVER_NOTE = "玩家之间的挂牌交易还没开放（主线稳定后再评估一种物资的固定价挂牌）；这里是杂货铺和居民订单，都是星球居民。";

function renderMarket(view: MarketView) {
  const market = vi.fn(async () => view);
  renderApp("/market", (base) => ({ economy: { ...base.economy, market } }));
  return market;
}

describe("集市锁卡：家与家之间买卖没开放时说玩家能懂的一句", () => {
  it("没开放：显示前端这句，不显示后端带开发安排的原话，也没有括号里的计划", async () => {
    const market = renderMarket({ ...fixtureMarket(), player_listing_enabled: false, player_listing_note: SERVER_NOTE });
    expect(await screen.findByText(LISTING_CLOSED)).toBeTruthy();
    expect(market).toHaveBeenCalled();
    expect(document.body.textContent).not.toContain("主线稳定后");
    expect(document.body.textContent).not.toContain("挂牌");
    expect(LISTING_CLOSED).not.toMatch(/[（(]/);
    expect(LISTING_CLOSED).not.toMatch(DEV_WORDS);
  });

  it("开放以后：照用服务端那句说明（到时候由后端写给玩家）", async () => {
    renderMarket({ ...fixtureMarket(), player_listing_enabled: true, player_listing_note: "现在可以和别的家互相买卖收成了。" });
    expect(await screen.findByText("现在可以和别的家互相买卖收成了。")).toBeTruthy();
    expect(screen.queryByText(LISTING_CLOSED)).toBeNull();
  });
});

/* ---------------- 4) 程序自己出的错（2026-09-24 23:5x，驾驶分身转） ---------------- */

describe("程序自己出的错：原文只进“技术信息”，玩家看“操作暂时没有完成，请重试。”；真的网络失败照旧是 client 的中文", () => {
  const BUG = () => new TypeError("Cannot read properties of undefined (reading 'session_id')");
  /** 真的网络失败：fetch 自己抛（断网），client.ts 包成中文原话的 ApiError。 */
  const offline = () => createApiClient("/api/v1/web", async () => {
    throw new TypeError("Failed to fetch");
  });

  it("toApiError 包进来的异常：playerMessage 是那一句；原文留在 message；kind / code / 可重试照旧（别处按它决定要不要重试）", () => {
    const err = toApiError(BUG());
    expect(err.playerMessage).toBe(PLAYER_ERROR_TEXT.failed);
    expect(err.message).toBe("Cannot read properties of undefined (reading 'session_id')");
    expect(err.fromException).toBe(true);
    expect([err.kind, err.code, err.retryable]).toEqual(["network", "NETWORK_ERROR", true]);
    // 不是 Error 的值同样
    expect(toApiError("oops").playerMessage).toBe(PLAYER_ERROR_TEXT.failed);
    // 本来就是 ApiError 的原样返回，不打标记
    const api = new ApiError({ kind: "http", status: 409, code: "CONFLICT", message: "TA 正在路上，等回来再说。" });
    expect(toApiError(api)).toBe(api);
    expect(api.fromException).toBe(false);
    expect(api.playerMessage).toBe("TA 正在路上，等回来再说。");
  });

  it("真的网络失败（client 自己造的）：照旧是中文原话“连不上服务，请检查网络后重试。”，不换成那一句", async () => {
    const err = await offline().request<never>("/meta").catch((e: unknown) => toApiError(e));
    expect(err.fromException).toBe(false);
    expect(err.kind).toBe("network");
    expect(err.playerMessage).toBe("连不上服务，请检查网络后重试。");
  });

  it("出错页：程序错误标题不说“信号暂时中断”（不是网络问题），正文是那一句，英文原文只在收起的“技术信息”里；真的网络失败标题照旧", async () => {
    const { container } = renderError(BUG(), () => undefined);
    expect(title(container)).toBe("没能完成这一步");
    expect(visibleText(container)).toContain(PLAYER_ERROR_TEXT.failed);
    expect(visibleText(container)).not.toMatch(/Cannot read|undefined|TypeError/);
    expect(techText(container)).toContain("Cannot read properties of undefined (reading 'session_id')");
    cleanup();
    const network = await offline().request("/meta").catch((e: unknown) => e);
    const again = renderError(network, () => undefined);
    expect(title(again.container)).toBe("信号暂时中断");
    expect(visibleText(again.container)).toContain("连不上服务，请检查网络后重试。");
    expect(visibleText(again.container)).not.toContain(PLAYER_ERROR_TEXT.failed);
  });

  it("那一句本身不带开发说法", () => {
    expect(PLAYER_ERROR_TEXT.failed).not.toMatch(DEV_WORDS);
    expect(PLAYER_ERROR_TEXT.failed).not.toMatch(/[A-Za-z]/);
  });
});
