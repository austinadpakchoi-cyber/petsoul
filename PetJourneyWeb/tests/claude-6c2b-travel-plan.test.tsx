/**
 * claude-6c2b（分身）· 旅行心愿（TRV-06：计划页 + 地图面板那一行；心愿已按 TRV-00 合同 v1 接 live；计划类型用生成的）。
 * 依据：方案第 5、6、7、9、10、12 节；合同 v1 §5、§7、§8、§11.5、§18.4、§22、§23、§28–§31；工作单 TRV-06；TRV-07 版式；
 *       I 的答复（主窗口转）；后端 schemas/web/travel.py 的字段说明。
 * 钉住：
 * - 十二个等待原因码：合同手抄清单 ↔ generated 的 TravelWaitingReasonValues ↔ 页面的文案表，三方双向一致；每个码说人话、不露码；
 *   语义不混：missing_funds 不说额度 / 次数，quota_denied 不说星币，research_unknown 不说搜不到，fact_stale 不说地方不存在。
 * - 每种业务状态说人话；标题有宠物名字就用名字，拿不到写“TA”。页面显示 current_revision 那一版（旧版都留着），页头带这一版计划的标题。
 * - 顺路建议单独标出（虚线卡）；出发前不盖章（数据里混进事件也不盖，带对照）；到访只认这一版计划的回忆手账站点上的真实事件
 *   （计划阶段的站点、别的版本都不认）；已回来没去成写“下次”；同一版里地点的键是 plan_revision + station_id（空时用序号）。
 * - 手账从这一版修订的 journals 里取（有回忆页显示回忆页，同一种页取最新一版）；图没有 / 在画 / 没画成 / 结果未确认 / 没有配图各说各的，
 *   unknown 不说没画成；正在画写“画着呢”；只有 failed / unknown 且有重画凭据才说“稍后可以重画”——重画命令后端还没挂，是一句说明、不是按钮；
 *   被拒的拒绝码、“不画 TA”的原因码只进“技术信息”；画里的 TA 从哪来说人话（不露 photo / none）；手账这一页上的字在图外照常可读。
 * - 出发前会再确认的资料（preconditions）：想去 / 可以出发时列出来，过期的标出来，找不到的照实说。
 * - 钱：攒钱目标不是路费（绝不拿它当路费）；路费只认这一版计划上的行程摘要（fare 是标价，fare_waived 为真＝用了券、实付 0）；
 *   现实参考只报已核实、认得出（金额、币种、写明是否估算）、有日期的价钱；没写 estimated 整条不报金额；不写 0；平台账不上页面。
 * - 来源带时间；过期、说法不一、没核实、没采用的标出来；依据它们的地点与提醒也标“待确认”；没有支持事实的提醒不出现（照 DTO 说明）。
 * - 外链只收 http(s)、新窗口、带 rel；地图链接只用后端给的 nav_url（没有就不给，不拿 lat/lng 自己拼）。
 * - 时区按暂定的 Asia/Shanghai，代码里标“暂定”、写明待用户决定。
 * - 演示数据处处有“演示”。
 * - 路由：/guides/wish（当前心愿；没有计划的只能从这里进）与 /guides/plan/:planId；列表两块、点卡片进、返回 /guides；
 *   “去过的”在演示下不再是一直转的骨架屏（修的是 fixture 下查询不发的 bug）；计划不在了、要先选宠物都有人话。
 * - live：/guides/wish 走 GET /travel/wish（visits.travelWish，显式带当前宠物）；没有心愿、出错都不造假；
 *   计划页走 GET /travel/plans/{plan_id}（visits.travelPlan，同样显式带当前宠物；2026-09-24 23:3x 接上，详细用例在 claude-6c2b-plan-live.test.tsx）。
 * - 地图面板那一行：“想去 {目的地} · {还差什么第一条}”，点进 /guides/wish；排在驾校之后；只关于这只宠物（petId）。
 * - 切宠物时停在 /guides/wish、/guides/plan/… 都退回 /guides。
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, MemoryRouter, Route, RouterProvider, Routes } from "react-router";
import {
  TravelWaitingReasonValues,
  type HouseholdBrief,
  type TravelGuide,
  type TravelJournal,
  type TravelJourneySummary,
  type TravelPlanRevision,
  type TravelWaitingReason,
  type TravelWish,
} from "@/shared/contracts";
import { createApiClient, type ApiClient } from "@/shared/api/client";
import { ApiError } from "@/shared/api/errors";
import { loadFeatureModules } from "@/app/modules";
import { buildRoutes } from "@/app/router";
import { buildServices, ServicesProvider } from "@/shared/services/registry";
import type { ServiceContext, ServiceMap, VisitService } from "@/shared/services/types";
import { HouseholdProvider, listForPetScopedPath } from "@/shared/session/householdContext";
import { createFixtureDrivingService } from "@/features/driving_school/service";
import { GuideBookPage } from "@/features/journey/GuideBookPage";
import journeyModule from "@/features/journey/module";
import { PetRequired, PlanContent, PlanMissing, PlanPage, WishPage } from "@/features/journey/travelPlan/PlanPage";
import { isPetRequired, isPlanNotFound, useCurrentWish } from "@/features/journey/travelPlan/data";
import { DEMO_CURRENT_WISH, DEMO_PLANS } from "@/features/journey/travelPlan/fixture";
import { PROVISIONAL_ZONE, viewOfPlan, viewOfWish, WAITING_REASON_CHIPS, wishNoteLine, type PlanBundle, type PlanView, type ViewOptions } from "@/features/journey/travelPlan/model";
import { useWishNote } from "@/features/journey/travelPlan/wishNote";
import { MapHomePage } from "@/features/world_map/MapHomePage";
import { arrangeNotes, type PanelNote } from "@/features/world_map/panelNotes";

// 同一个文件里要切 fixture / live：env 用 getter 读一个可改的开关（页面在渲染时才读 env.dataMode）。
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
  // 主布局里有滚动恢复；jsdom 没有 scrollTo。
  vi.stubGlobal("scrollTo", vi.fn());
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/* ---------------- 工具 ---------------- */

const modules = loadFeatureModules();
const HERE = dirname(fileURLToPath(import.meta.url));
const sourceOf = (...parts: string[]) => readFileSync(resolve(HERE, "..", "src", "features", "journey", "travelPlan", ...parts), "utf8");

/** 整个应用（真实路由表 + 主布局），fixture 服务（journey 模块的 visits.travelWish 演示实现也在里面）。 */
function renderApp(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const services = buildServices(modules, { mode: "fixture", api: createApiClient("/api/v1/web") });
  const router = createMemoryRouter(buildRoutes(modules), { initialEntries: [path] });
  const view = render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={services}>
        <RouterProvider router={router} />
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return { router, ...view };
}

const DEMO: ViewOptions = { isDemo: true };
const demoWish = (): TravelWish => structuredClone(DEMO_CURRENT_WISH);

function demoPlan(planId: string): PlanBundle {
  const found = DEMO_PLANS.find((b) => b.plan.plan_id === planId);
  expect(found, `演示数据里没有 ${planId}`).toBeTruthy();
  return structuredClone(found!);
}

/** 当前那一版（测试里改数据用）。 */
const rev = (b: PlanBundle): TravelPlanRevision => b.plan.revisions.find((r) => r.plan_revision === b.plan.current_revision)!;
/** 当前那一版里某一种手账页（测试里改数据用；没有就是 undefined）。 */
const journalOf = (b: PlanBundle, phase: TravelJournal["phase"]): TravelJournal | undefined => rev(b).journals.find((j) => j.phase === phase);

const planView = (b: PlanBundle, o: ViewOptions = {}) => viewOfPlan(b, { ...DEMO, ...o });
const wishView = (w: TravelWish, o: ViewOptions = {}) => viewOfWish(w, { ...DEMO, ...o });

function renderView(view: PlanView) {
  return render(
    <MemoryRouter>
      <PlanContent view={view} />
    </MemoryRouter>,
  );
}

function section(container: HTMLElement, heading: string): HTMLElement {
  const h2 = [...container.querySelectorAll("h2")].find((el) => el.textContent === heading);
  expect(h2, `没有“${heading}”这一块`).toBeTruthy();
  return h2!.closest("section") as HTMLElement;
}

function placeItem(container: HTMLElement, placeId: string): HTMLElement {
  const el = container.querySelector<HTMLElement>(`[data-place-id="${placeId}"]`);
  expect(el, `没有地点 ${placeId}`).toBeTruthy();
  return el!;
}

const text = (el: Element | null | undefined) => el?.textContent ?? "";

/** 玩家看得见的文字：默认收起的“技术信息”（原因码、拒绝码）除外。 */
function plainText(el: Element): string {
  const copy = el.cloneNode(true) as Element;
  copy.querySelectorAll("details.ps-state__tech").forEach((d) => d.remove());
  return copy.textContent ?? "";
}

/** 合同 §5.2 的全集（手抄；改合同时这里必须一起改）。 */
const CONTRACT_WAITING_REASONS = [
  "missing_funds",
  "quota_denied",
  "research_pending",
  "research_unknown",
  "research_failed",
  "fact_stale",
  "plan_stale",
  "fact_unverified",
  "fact_conflicting",
  "weather_unsuitable",
  "commitment_active",
  "maintenance",
];

/** 页面上不能出现的原始代码：业务 / 研究 / 图片状态、原因码、核验结论与方法、事实类别、币种码、坐标系、票据、画像方式。 */
const RAW_CODES = [
  "active", "ready", "linked", "completed", "cancelled",
  ...CONTRACT_WAITING_REASONS,
  "queued", "running", "processing", "failed", "unknown",
  "verified", "stale", "conflicting", "unverified", "rejected",
  "destination_identity", "ticket_price", "opening", "price", "notice", "route",
  "search", "weather_api", "official_page", "HKD", "MOP", "wgs84", "fixture", "redraw", "refused", "memory",
  "photo", "none", "journal", "estimated",
];

function expectPlainLanguage(pageText: string) {
  for (const code of RAW_CODES) expect(pageText, `页面露出了代码 ${code}`).not.toContain(code);
  expect(pageText).not.toMatch(/[a-z]+_[a-z]+/);
}

const ALL_DEMO_VIEWS: Array<[string, () => PlanView]> = [
  ["当前心愿（广州）", () => wishView(demoWish())],
  ...DEMO_PLANS.map((b): [string, () => PlanView] => [b.plan.plan_id, () => planView(demoPlan(b.plan.plan_id))]),
];

/* ---------------- 1. 原因码与状态说人话 ---------------- */

describe("十二个等待原因码：三方一致、每个说人话、语义不混", () => {
  it("合同手抄清单 ↔ generated 的 TravelWaitingReasonValues ↔ 页面文案表：三方双向一致（多一个少一个都红）", () => {
    const sorted = (xs: readonly string[]) => [...xs].sort();
    expect(sorted(TravelWaitingReasonValues)).toEqual(sorted(CONTRACT_WAITING_REASONS));
    expect(sorted(Object.keys(WAITING_REASON_CHIPS))).toEqual(sorted(CONTRACT_WAITING_REASONS));
  });

  it.each(CONTRACT_WAITING_REASONS)("%s：有自己的状态标签和“还差什么”，都是人话、不露码", (code) => {
    const w = demoWish();
    w.waiting_reasons = [code as TravelWaitingReason];
    w.target_coins = 120;
    w.current_coins = 45;
    const view = wishView(w);
    expect(view.status.label).toBe(WAITING_REASON_CHIPS[code as TravelWaitingReason].label);
    expect(view.waiting).toHaveLength(1);
    expect(view.waiting[0].text).not.toBe("还有一件事在确认");
    const { container } = renderView(view);
    expectPlainLanguage(plainText(container));
  });

  const one = (code: TravelWaitingReason) => {
    const w = demoWish();
    w.waiting_reasons = [code];
    w.target_coins = 120;
    w.current_coins = 45;
    return wishView(w);
  };

  it("missing_funds 说还差多少星币、不说额度；quota_denied 说今天的次数、不说星币——两句话不一样", () => {
    const funds = one("missing_funds");
    const quota = one("quota_denied");
    expect(funds.waiting[0].text).toBe("还差 75 星币");
    expect(funds.status.label).toBe("等攒够星币");
    expect(`${funds.waiting[0].text}${funds.waiting[0].detail}`).not.toMatch(/额度|次数/);
    expect(quota.waiting[0].text).toContain("次数");
    expect(quota.waiting[0].text).not.toContain("星币");
    expect(quota.status.label).not.toBe(funds.status.label);
  });

  it("research_unknown 说“还没确认”、不说搜不到；fact_stale 不说地方不存在；commitment_active 只用中性措辞", () => {
    const unknown = one("research_unknown");
    expect(unknown.waiting[0].text).toBe("查资料的结果还没确认");
    expect(unknown.waiting[0].text).not.toMatch(/搜不到|没查到|查不到/);
    expect(one("fact_stale").waiting[0].text).not.toMatch(/不存在|找不到/);
    expect(one("commitment_active").waiting[0].text).toBe("家里有安排，先不出门");
    expect(one("maintenance").status.label).toBe("维护中");
    // plan_stale 本批没有生产者（合同 §20.1）：文案照备，不列入可见状态验收。
    expect(one("plan_stale").waiting[0].text).toBe("计划是按之前的想法排的，要重新排一下");
  });

  it("不认识的原因码、状态码：只说中性的话，不露码", () => {
    const w = demoWish();
    w.waiting_reasons = ["ops_hold_internal" as TravelWaitingReason];
    const a = renderView(wishView(w));
    expect(text(section(a.container, "还差什么"))).toContain("还有一件事在确认");
    expect(text(a.container)).not.toContain("ops_hold_internal");
    cleanup();
    const paused = demoWish();
    paused.status = "paused_by_ops" as TravelWish["status"];
    const view = wishView(paused);
    expect(view.status.label).toBe("状态待确认");
    expect(view.title).toBe("TA 的旅行计划");
    expect(text(renderView(view).container)).not.toContain("paused_by_ops");
  });

  it("多条原因时先说资料、再说钱、再说天气和约定；第一条同时是状态标签、列表那句和地图那一行", () => {
    const w = demoWish();
    w.waiting_reasons = ["commitment_active", "weather_unsuitable", "missing_funds", "fact_stale"];
    w.target_coins = 120;
    w.current_coins = 45;
    const view = wishView(w);
    expect(view.waiting.map((item) => item.text)).toEqual(["有资料过期了，还在确认", "还差 75 星币", "天气不太合适，等一等", "家里有安排，先不出门"]);
    expect(view.status.label).toBe("资料待确认");
    expect(view.cardLine).toBe("有资料过期了，还在确认");
    expect(wishNoteLine(view)).toBe("想去 广州 · 有资料过期了，还在确认");
  });
});

describe("每种业务状态说人话；标题有名字用名字", () => {
  it("前提：演示覆盖五种业务状态；手账图 unknown、failed、processing、被拒各一例；有一份计划留着旧版；有回忆页；研究正在进行的心愿一例", () => {
    const statuses = [DEMO_CURRENT_WISH.status, ...DEMO_PLANS.map((b) => b.wish.status)];
    expect(new Set(statuses)).toEqual(new Set(["active", "ready", "linked", "completed", "cancelled"]));
    const journals = DEMO_PLANS.flatMap((b) => b.plan.revisions.flatMap((r) => r.journals));
    expect(journals.map((j) => j.image_status)).toEqual(expect.arrayContaining(["unknown", "failed", "processing"]));
    expect(journals.filter((j) => j.image_refused)).toHaveLength(1);
    expect(journals.filter((j) => j.phase === "memory")).toHaveLength(1);
    // 手账挂在修订上：每一页的 plan_revision 都等于它所在那一版。
    for (const b of DEMO_PLANS) for (const r of b.plan.revisions) for (const j of r.journals) expect(j.plan_revision, j.journal_id).toBe(r.plan_revision);
    expect(DEMO_PLANS.some((b) => b.plan.revisions.length > 1)).toBe(true);
    expect(DEMO_CURRENT_WISH.research_state).toBe("running");
    expect(DEMO_CURRENT_WISH.plan_id).toBeNull();
  });

  it.each([
    ["当前心愿", "资料准备中", "TA 想去 广州", () => wishView(demoWish())],
    ["fx-plan-tokyo", "等攒够星币", "TA 想去 东京", () => planView(demoPlan("fx-plan-tokyo"))],
    ["fx-plan-macau", "资料待确认", "TA 想去 澳门", () => planView(demoPlan("fx-plan-macau"))],
    ["fx-plan-west-kowloon", "可以出发", "TA 准备去 香港西九龙", () => planView(demoPlan("fx-plan-west-kowloon"))],
    ["fx-plan-shenzhen-bay", "已出发", "TA 出发去 深圳湾 了", () => planView(demoPlan("fx-plan-shenzhen-bay"))],
    ["fx-plan-harbour-cafe", "已回来", "TA 从 香港的海边咖啡馆 回来了", () => planView(demoPlan("fx-plan-harbour-cafe"))],
    ["fx-plan-airport", "已取消", "去 香港机场 的心愿先放下了", () => planView(demoPlan("fx-plan-airport"))],
  ] as const)("%s：状态标签“%s”，标题“%s”，页面没有原始代码", (_id, chip, title, make) => {
    const view = make();
    expect(view.title).toBe(title);
    const { container } = renderView(view);
    expect(text(container.querySelector(".ps-plan-hero .ps-chip"))).toBe(chip);
    expectPlainLanguage(plainText(container));
  });

  it("有宠物名字就用名字；名字是空白才写“TA”", () => {
    expect(planView(demoPlan("fx-plan-tokyo"), { petName: "栗子" }).title).toBe("栗子 想去 东京");
    expect(wishView(demoWish(), { petName: "栗子" }).title).toBe("栗子 想去 广州");
    expect(planView(demoPlan("fx-plan-tokyo"), { petName: "  " }).title).toBe("TA 想去 东京");
  });

  it("页头带这一版计划的标题（TravelPlanRevision.title）；还没有计划的心愿没有这一行", () => {
    const tokyo = renderView(planView(demoPlan("fx-plan-tokyo")));
    expect(text(tokyo.container.querySelector(".ps-plan-hero__plan"))).toBe("坐喵航去东京看电车");
    cleanup();
    const b = demoPlan("fx-plan-west-kowloon");
    b.plan.current_revision = 1;
    expect(planView(b).planTitle).toBe("去西九龙看灯");
    expect(renderView(wishView(demoWish())).container.querySelector(".ps-plan-hero__plan")).toBeNull();
  });

  it("资料准备中：正在查写“TA 正在查资料”，排队写“资料还在准备”；标签都是“资料准备中”", () => {
    expect(wishView(demoWish()).waiting[0].text).toBe("TA 正在查资料");
    const queued = demoWish();
    queued.research_state = "queued";
    const view = wishView(queued);
    expect(view.waiting[0].text).toBe("资料还在准备");
    expect(view.status.label).toBe("资料准备中");
  });

  it("等攒够星币：写还差多少、目标、现有，并写明钱包快照截至什么时候（last_considered_at）", () => {
    const view = planView(demoPlan("fx-plan-tokyo"));
    expect(view.waiting[0].text).toBe("还差 75 星币");
    expect(view.waiting[0].detail).toBe("要攒到 120 星币；截至 2026年9月24日 07:30 有 45");
  });

  it("资料待确认：分别说清过期、说法不一、没核实的是什么（只列卡住出行的），写“还在确认”，不写“以现场为准”", () => {
    const { container } = renderView(planView(demoPlan("fx-plan-macau")));
    const waiting = text(section(container, "还差什么"));
    expect(waiting).toContain("有资料过期了，还在确认过期的是：路线");
    expect(waiting).toContain("有资料说法不一，还在确认说法不一的是：临时公告");
    expect(waiting).toContain("有关键资料还没核实，还在确认还没核实的是：天气");
    expect(text(container)).not.toMatch(/以现场为准|不存在|找不到这个地方/);
  });

  it("页面显示 current_revision 那一版（旧版都留着）：西九龙显示第 2 版；把 current_revision 指回第 1 版就显示旧版", () => {
    const b = demoPlan("fx-plan-west-kowloon");
    expect(b.plan.revisions.map((r) => r.plan_revision)).toEqual([1, 2]);
    const current = planView(b);
    expect(current.planRevision).toBe(2);
    expect(current.arrangement).toBe("傍晚坐车去西九龙，沿海边走到天黑看对岸的灯，晚上坐车回家。");
    b.plan.current_revision = 1;
    const old = planView(b);
    expect(old.planRevision).toBe(1);
    expect(old.arrangement).toContain("旧版");
    expect(old.main.id).toBe("1:st-0");
    // 旧版那一版没有手账：手账跟着修订走，不拿第 2 版的手账顶。
    expect(old.journal).toMatchObject({ state: "none", heading: "手账", text: null });
  });
});

/* ---------------- 2. 顺路建议、出发前不盖章 ---------------- */

describe("顺路建议单独标出；出发前没有到访章", () => {
  it.each([
    ["当前心愿", 0, () => wishView(demoWish())],
    ["fx-plan-tokyo", 1, () => planView(demoPlan("fx-plan-tokyo"))],
    ["fx-plan-macau", 2, () => planView(demoPlan("fx-plan-macau"))],
    ["fx-plan-west-kowloon", 1, () => planView(demoPlan("fx-plan-west-kowloon"))],
  ] as const)("%s：顺路建议 %i 条，都在“顺路建议”一块、各自标“顺路建议”；全页没有“到过”“下次”", (_id, count, make) => {
    const { container } = renderView(make());
    const along = section(container, "顺路建议");
    expect(text(along)).toContain("不算到访");
    const items = along.querySelectorAll(".ps-plan-place");
    expect(items).toHaveLength(count);
    items.forEach((item) => expect(text(item.querySelector(".ps-plan-tag"))).toBe("顺路建议"));
    expect(text(section(container, "主目的地"))).not.toContain("顺路建议");
    expect(container.querySelectorAll(".ps-plan-stamp")).toHaveLength(0);
    expect(text(container)).not.toMatch(/到过|下次/);
  });

  it("顺路建议是虚线卡：地点卡的类名跟着 TravelStopRole（suggested），样式表里有这个类（第②期换类型时一度对不上）", () => {
    const { container } = renderView(planView(demoPlan("fx-plan-macau")));
    const along = section(container, "顺路建议");
    along.querySelectorAll(".ps-plan-place").forEach((item) => expect(item.classList.contains("ps-plan-place--suggested")).toBe(true));
    expect(section(container, "主目的地").querySelector(".ps-plan-place")?.classList.contains("ps-plan-place--main")).toBe(true);
    const css = sourceOf("plan.css");
    expect(css).toMatch(/\.ps-plan-place--suggested\s*\{[^}]*dashed/);
    expect(css).not.toContain(".ps-plan-place--suggestion");
  });

  it("不变量：可以出发（还没出门）时，即使这一版的回忆手账里混进了到访事件也不盖章；同一份数据标成已回来就会盖（对照）", () => {
    const b = demoPlan("fx-plan-west-kowloon");
    const r = rev(b);
    const planJournal = journalOf(b, "plan")!;
    r.journals.push({ ...planJournal, journal_id: `tj-${r.plan_id}-memory`, phase: "memory", stations: r.stops.map((s) => ({ ...s, visited_event_ids: ["x-evt"] })) });
    expect(renderView(planView(b)).container.querySelectorAll(".ps-plan-stamp")).toHaveLength(0);
    cleanup();
    b.wish.status = "completed";
    expect(renderView(planView(b)).container.querySelectorAll(".ps-plan-place .ps-plan-stamp--visited")).toHaveLength(2);
  });

  it("同一版里地点的键是 plan_revision + station_id；计划阶段 station_id 为空时用序号", () => {
    const wkl = renderView(planView(demoPlan("fx-plan-west-kowloon")));
    expect([...wkl.container.querySelectorAll("[data-place-id]")].map((el) => el.getAttribute("data-place-id"))).toEqual(["2:st-0", "2:st-1"]);
    cleanup();
    const cafe = renderView(planView(demoPlan("fx-plan-harbour-cafe")));
    expect([...cafe.container.querySelectorAll("[data-place-id]")].map((el) => el.getAttribute("data-place-id"))).toEqual(["1:st-0", "1:st-1", "1:st-2"]);
    cleanup();
    const b = demoPlan("fx-plan-west-kowloon");
    rev(b).stops.forEach((s) => (s.station_id = null));
    const bare = renderView(planView(b));
    expect([...bare.container.querySelectorAll("[data-place-id]")].map((el) => el.getAttribute("data-place-id"))).toEqual(["2:#0", "2:#1"]);
  });
});

/* ---------------- 3. 回来后只给真实事件盖章 ---------------- */

describe("到访只认这一版计划的回忆手账里的真实事件；已回来没去成的写“下次”", () => {
  const memoryOf = (b: PlanBundle) => journalOf(b, "memory")!.stations;
  const placeStamps = (container: HTMLElement) => container.querySelectorAll(".ps-plan-place .ps-plan-stamp");

  it("演示：计划三站（计划阶段的站点到访恒为空），回忆手账里只有主目的地有到访 → 主目的地“到过”，两条顺路建议“下次”", () => {
    const b = demoPlan("fx-plan-harbour-cafe");
    expect(rev(b).stops.every((s) => s.visited_event_ids.length === 0)).toBe(true);
    expect(memoryOf(b).filter((s) => s.visited_event_ids.length)).toHaveLength(1);
    const { container } = renderView(planView(b));
    expect(text(placeItem(container, "1:st-0").querySelector(".ps-plan-stamp"))).toBe("到过");
    expect(text(placeItem(container, "1:st-1").querySelector(".ps-plan-stamp"))).toBe("下次");
    expect(text(placeItem(container, "1:st-2").querySelector(".ps-plan-stamp"))).toBe("下次");
    expect(container.querySelectorAll(".ps-plan-place .ps-plan-stamp--visited")).toHaveLength(1);
    expect(text(container.querySelector(".ps-plan-hero__summary"))).toBe("去了 1 个地方，2 个留到下次");
  });

  it("真实事件落在顺路建议上：给那一站盖章，主目的地反而是“下次”", () => {
    const b = demoPlan("fx-plan-harbour-cafe");
    memoryOf(b)[0].visited_event_ids = [];
    memoryOf(b)[1].visited_event_ids = ["e-2"];
    const { container } = renderView(planView(b));
    expect(text(placeItem(container, "1:st-1").querySelector(".ps-plan-stamp"))).toBe("到过");
    expect(text(placeItem(container, "1:st-0").querySelector(".ps-plan-stamp"))).toBe("下次");
    expect(text(placeItem(container, "1:st-2").querySelector(".ps-plan-stamp"))).toBe("下次");
  });

  it("回忆手账里一站都没有真实事件：全是“下次”；计划阶段站点上混进的事件不算（只认回忆手账）", () => {
    const b = demoPlan("fx-plan-harbour-cafe");
    memoryOf(b).forEach((s) => (s.visited_event_ids = []));
    rev(b).stops.forEach((s) => (s.visited_event_ids = ["x-evt"]));
    const { container } = renderView(planView(b));
    expect(container.querySelectorAll(".ps-plan-place .ps-plan-stamp--visited")).toHaveLength(0);
    expect(container.querySelectorAll(".ps-plan-place .ps-plan-stamp--next")).toHaveLength(3);
    expect(text(container.querySelector(".ps-plan-hero__summary"))).toBe("这趟没有到访记录，3 个地方留到下次");
  });

  it("同一版之内按 name + role 对应回忆站点（计划阶段 station_id 可空）；同名不同角色不算", () => {
    const b = demoPlan("fx-plan-harbour-cafe");
    rev(b).stops.forEach((s) => (s.station_id = null));
    expect(planView(b).main.stamp?.label).toBe("到过");
    const other = demoPlan("fx-plan-harbour-cafe");
    memoryOf(other)[0].role = "suggested";
    expect(planView(other).main.stamp?.label).toBe("下次");
  });

  it("跨版本不认（不变量）：回忆页是另一版计划的，这一版一站都不盖，也不写“下次”；还没有回忆页时同样不盖", () => {
    const b = demoPlan("fx-plan-harbour-cafe");
    journalOf(b, "memory")!.plan_revision = 2;
    const cross = renderView(planView(b));
    expect(placeStamps(cross.container)).toHaveLength(0);
    expect(text(cross.container.querySelector(".ps-plan-hero__summary"))).toBe("TA 回来了，到访记录还在整理");
    cleanup();
    for (const keep of [() => false, (j: TravelJournal) => j.phase === "plan"]) {
      const c = demoPlan("fx-plan-harbour-cafe");
      rev(c).journals = rev(c).journals.filter(keep);
      const { container } = renderView(planView(c));
      expect(placeStamps(container)).toHaveLength(0);
      // 只剩计划页时，手账页上的站点也不盖章、不写“下次”（章只在回忆页）。
      expect(container.querySelectorAll(".ps-plan-stamp")).toHaveLength(0);
      cleanup();
    }
  });

  it("已出发：还在路上、还没有回忆手账——一站都不盖章，也不写“下次”", () => {
    const { container } = renderView(planView(demoPlan("fx-plan-shenzhen-bay")));
    expect(container.querySelectorAll(".ps-plan-stamp")).toHaveLength(0);
    expect(text(container)).not.toContain("下次");
    expect(text(container.querySelector(".ps-plan-hero__summary"))).toBe("TA 已经在路上；回来以后，真的到过的地方才盖章");
  });

  it("已取消：没有出发，不盖章，也不写“下次”", () => {
    const { container } = renderView(planView(demoPlan("fx-plan-airport")));
    expect(container.querySelectorAll(".ps-plan-stamp")).toHaveLength(0);
    expect(text(container.querySelector(".ps-plan-hero__summary"))).toBe("这个心愿先放下了，没有出发");
  });
});

/* ---------------- 4. 手账图 ---------------- */

describe("手账从这一版的 journals 里取；图没有 / 在画 / 没画成 / 结果未确认 / 没有配图各说各的，文字照常", () => {
  function expectTextIntact(container: HTMLElement, b: PlanBundle) {
    const r = rev(b);
    expect(text(section(container, "我为什么想去"))).toContain(b.wish.owner_reason);
    expect(text(section(container, "主目的地"))).toContain(r.stops[0].name);
    expect(text(section(container, "行动安排"))).toContain(r.summary);
    expect(section(container, "资料来源").querySelectorAll("li").length).toBe(r.facts.length);
  }
  const redrawOf = (container: HTMLElement) => container.querySelector(".ps-plan-journal__redraw");

  it("有回忆页显示回忆页（标题“回忆手账”），没有就显示计划页；同一种页取最新一版（journal_revision 最大）", () => {
    expect(planView(demoPlan("fx-plan-harbour-cafe")).journal).toMatchObject({ heading: "回忆手账", state: "failed" });
    const planOnly = demoPlan("fx-plan-harbour-cafe");
    rev(planOnly).journals = rev(planOnly).journals.filter((j) => j.phase === "plan");
    expect(planView(planOnly).journal).toMatchObject({ heading: "计划手账", state: "none" });
    const redrawn = demoPlan("fx-plan-harbour-cafe");
    const memory = journalOf(redrawn, "memory")!;
    rev(redrawn).journals.push({ ...memory, journal_revision: 2, image_status: "ready", image_url: "/media/journal/fx-cafe-memory-2.webp", redraw_ticket: null });
    expect(planView(redrawn).journal).toMatchObject({ state: "ready", imageUrl: "/media/journal/fx-cafe-memory-2.webp" });
    // 顺序不影响：新的一版排在前面也取它。
    rev(redrawn).journals.reverse();
    expect(planView(redrawn).journal.imageUrl).toBe("/media/journal/fx-cafe-memory-2.webp");
  });

  it("结果未确认（unknown）：写“手账结果还没确认”、不说没画成；没有图；有重画票就说“稍后可以重画”；文字都在", () => {
    const b = demoPlan("fx-plan-west-kowloon");
    expect(journalOf(b, "plan")).toMatchObject({ image_status: "unknown", redraw_ticket: "fx-redraw-wkl" });
    const { container } = renderView(planView(b));
    const figure = container.querySelector("figure.ps-plan-journal")!;
    expect(text(figure)).toContain("手账结果还没确认");
    expect(text(figure)).not.toContain("没画成");
    expect(figure.querySelector("img")).toBeNull();
    expect(text(redrawOf(container))).toBe("稍后可以在这里重画这张手账。");
    expectTextIntact(container, b);
  });

  it("没画成（failed）：写“这次手账没画成”；没有图；有重画票就说“稍后可以重画”；回忆手账的标题；文字都在", () => {
    const b = demoPlan("fx-plan-harbour-cafe");
    expect(journalOf(b, "memory")).toMatchObject({ image_status: "failed", redraw_ticket: "fx-redraw-cafe" });
    const { container } = renderView(planView(b));
    expect(text(section(container, "回忆手账"))).toContain("这次手账没画成");
    expect(container.querySelector("figure.ps-plan-journal img")).toBeNull();
    expect(redrawOf(container)).toBeTruthy();
    expectTextIntact(container, b);
  });

  it("重画的路由还没建：入口只是一句说明，不是按钮、也不是链接，点不了（不假装能重画）", () => {
    const { container } = renderView(planView(demoPlan("fx-plan-west-kowloon")));
    const journal = section(container, "计划手账");
    const note = redrawOf(container)!;
    expect(note.tagName).toBe("P");
    expect(within(journal).queryByRole("button")).toBeNull();
    expect(note.querySelector("a, button")).toBeNull();
    expect(text(journal)).not.toMatch(/已经重画|重画好了|正在重画/);
  });

  it("没有重画票就没有重画入口（failed、unknown 都一样）；有票但不是 failed / unknown 也没有", () => {
    for (const [id, phase] of [["fx-plan-west-kowloon", "plan"], ["fx-plan-harbour-cafe", "memory"]] as const) {
      const b = demoPlan(id);
      journalOf(b, phase)!.redraw_ticket = null;
      expect(planView(b).journal.canRedraw, id).toBe(false);
      expect(redrawOf(renderView(planView(b)).container), id).toBeNull();
      cleanup();
    }
    const drawing = demoPlan("fx-plan-shenzhen-bay");
    journalOf(drawing, "plan")!.redraw_ticket = "fx-redraw-odd";
    expect(planView(drawing).journal).toMatchObject({ state: "drawing", canRedraw: false });
  });

  it("配图被拒：写“这次没有配图”；没有图；拒绝码只在默认收起的“技术信息”里；文字都在", () => {
    const b = demoPlan("fx-plan-tokyo");
    expect(journalOf(b, "plan")).toMatchObject({ image_status: null, image_refused: "fx-refused-demo" });
    const { container } = renderView(planView(b));
    const figure = container.querySelector("figure.ps-plan-journal")!;
    expect(text(figure)).toContain("这次没有配图");
    expect(text(figure)).toContain("文字都在这一页，照常可以看。");
    expect(figure.querySelector("img")).toBeNull();
    const tech = figure.querySelector("details.ps-state__tech")!;
    expect(tech.hasAttribute("open")).toBe(false);
    expect(text(tech.querySelector("summary"))).toBe("技术信息");
    expect(text(tech.querySelector(".ps-state__meta"))).toBe("fx-refused-demo");
    expect(plainText(container)).not.toContain("fx-refused-demo");
    expect(redrawOf(container)).toBeNull();
    expectTextIntact(container, b);
  });

  it("正在画（processing）写“画着呢”、不给重画；没接插画（null）与还没有手账都写“只有文字”、不给重画", () => {
    const szb = renderView(planView(demoPlan("fx-plan-shenzhen-bay")));
    expect(text(szb.container.querySelector("figure.ps-plan-journal"))).toContain("画着呢");
    expect(redrawOf(szb.container)).toBeNull();
    cleanup();
    const nullStatus = demoPlan("fx-plan-west-kowloon");
    journalOf(nullStatus, "plan")!.image_status = null;
    expect(planView(nullStatus).journal).toMatchObject({ state: "none", heading: "计划手账", caption: "这一页只有文字，没有手账图", canRedraw: false });
    const noJournal = demoPlan("fx-plan-west-kowloon");
    rev(noJournal).journals = [];
    expect(planView(noJournal).journal).toMatchObject({ state: "none", heading: "手账", canRedraw: false, text: null });
  });

  it("画好了（ready）：显示图、不给重画；地名仍是图外文字；（不变量）手账的 plan_revision 与这一版不同时提醒一句按上一版画的", () => {
    const b = demoPlan("fx-plan-west-kowloon");
    const journal = journalOf(b, "plan")!;
    journal.image_status = "ready";
    journal.image_url = "/media/journal/fx-west-kowloon.webp";
    const a = renderView(planView(b));
    const figure = a.container.querySelector("figure.ps-plan-journal")!;
    expect(figure.querySelector("img")?.getAttribute("src")).toBe("/media/journal/fx-west-kowloon.webp");
    expect(text(figure)).not.toContain("香港西九龙一带（示意）");
    expect(text(figure)).not.toContain("上一版");
    expect(redrawOf(a.container)).toBeNull();
    cleanup();
    journal.plan_revision = 1; // 计划现在是第 2 版
    expect(text(renderView(planView(b)).container.querySelector("figure.ps-plan-journal"))).toContain("这张手账是按上一版计划画的，以这一页的文字为准");
  });

  it("图片地址只收 http(s) 与站内路径：javascript:、协议相对、data: 都不显示成图，改说“还没确认”（画好了不会有重画票，也不给重画）", () => {
    for (const url of ["javascript:alert(1)", "//evil.example/x.png", "data:image/png;base64,AAAA"]) {
      const b = demoPlan("fx-plan-west-kowloon");
      const journal = journalOf(b, "plan")!;
      journal.image_status = "ready";
      journal.image_url = url;
      expect(planView(b).journal, url).toMatchObject({ state: "unknown", imageUrl: null, caption: "手账结果还没确认", canRedraw: false });
    }
  });
});

describe("画里的 TA 从哪来（identity_mode）：说人话、不露 photo / none；只在有图或正在画时说", () => {
  const identityOf = (container: HTMLElement) => container.querySelector("figure.ps-plan-journal .ps-plan-journal__identity");

  it("照着证件照画（photo）：正在画时写“画里的 TA 照着 TA 的证件照画”", () => {
    const b = demoPlan("fx-plan-shenzhen-bay");
    expect(journalOf(b, "plan")).toMatchObject({ image_status: "processing", identity_mode: "photo" });
    const { container } = renderView(planView(b));
    expect(text(identityOf(container))).toBe("画里的 TA 照着 TA 的证件照画");
    expect(container.querySelector("figure.ps-plan-journal details.ps-state__tech")).toBeNull();
    expect(plainText(container)).not.toMatch(/photo|none/);
  });

  it("不画 TA（none）：写“这页手账不画 TA 的样子”；原因码（identity_note）只在默认收起的“技术信息”里", () => {
    const b = demoPlan("fx-plan-shenzhen-bay");
    Object.assign(journalOf(b, "plan")!, { identity_mode: "none", identity_note: "no_reference" });
    const { container } = renderView(planView(b));
    expect(text(identityOf(container))).toBe("这页手账不画 TA 的样子");
    expect(text(container.querySelector("figure.ps-plan-journal details.ps-state__tech .ps-state__meta"))).toBe("no_reference");
    expect(plainText(container)).not.toMatch(/no_reference|none|photo/);
  });

  it("画好了也说（ready + photo）；没画成、结果未确认、没有配图、没接插画时不说；不认识的取值不说", () => {
    const ready = demoPlan("fx-plan-shenzhen-bay");
    Object.assign(journalOf(ready, "plan")!, { image_status: "ready", image_url: "/media/journal/fx-szb.webp" });
    expect(planView(ready).journal.identity).toBe("画里的 TA 照着 TA 的证件照画");
    for (const status of ["failed", "unknown", null] as const) {
      const b = demoPlan("fx-plan-shenzhen-bay");
      journalOf(b, "plan")!.image_status = status;
      expect(planView(b).journal.identity, String(status)).toBeNull();
    }
    expect(planView(demoPlan("fx-plan-tokyo")).journal.identity).toBeNull(); // 被拒
    const odd = demoPlan("fx-plan-shenzhen-bay");
    (journalOf(odd, "plan") as { identity_mode: string }).identity_mode = "sketch";
    const oddView = planView(odd);
    expect(oddView.journal.identity).toBeNull();
    expect(text(renderView(oddView).container)).not.toContain("sketch");
  });
});

describe("手账这一页上写的字：图外照常可读（标题、一句话、站点、提醒、雨天备选）", () => {
  const pageOf = (container: HTMLElement) => within(container).queryByRole("group", { name: "手账上写着" });

  it("计划页（东京，配图被拒）：标题、一句话、两站（顺路建议标出、没有章）、提醒、雨天备选都在，跟着这一版计划", () => {
    const b = demoPlan("fx-plan-tokyo");
    const { container } = renderView(planView(b));
    const page = pageOf(container)!;
    expect(text(page.querySelector("h3"))).toBe("坐喵航去东京看电车");
    expect(text(page)).toContain(rev(b).summary);
    const stations = [...page.querySelectorAll(".ps-plan-journal__stations li")];
    expect(stations.map((li) => text(li))).toEqual(["东京（示意）", "香港机场（示意）顺路建议"]);
    expect(page.querySelectorAll(".ps-plan-stamp")).toHaveLength(0);
    expect([...page.querySelectorAll(".ps-plan-lines li")].map((li) => text(li))).toEqual(["出境要带星球护照", "路上时间长，TA 会在飞机上多睡一会儿"]);
    expect(text(page)).toContain("雨天备选：下雨就在车站里看电车进站");
  });

  it("回忆页（咖啡馆）：站点带章——只有真实到访的主目的地“到过”，另两站“下次”", () => {
    const { container } = renderView(planView(demoPlan("fx-plan-harbour-cafe")));
    const page = pageOf(container)!;
    const stamps = [...page.querySelectorAll(".ps-plan-journal__stations li")].map((li) => [text(li.querySelector("span")), text(li.querySelector(".ps-plan-stamp"))]);
    expect(stamps).toEqual([
      ["示例·海边咖啡馆（演示店）", "到过"],
      ["中环码头（示意）", "下次"],
      ["香港市区（示意）", "下次"],
    ]);
  });

  it("手账页上的字用手账自己的（不是拿计划的顶）；页上的提醒同样照 DTO 说明：没有支持事实的不出现", () => {
    const b = demoPlan("fx-plan-tokyo");
    const journal = journalOf(b, "plan")!;
    journal.title = "手账自己的标题";
    journal.owner_tips = [...journal.owner_tips, { text: "没有依据的一句（手账）", fact_ids: [] }];
    const { container } = renderView(planView(b));
    const page = pageOf(container)!;
    expect(text(page.querySelector("h3"))).toBe("手账自己的标题");
    expect(text(page)).not.toContain("没有依据的一句（手账）");
    expect(page.querySelectorAll(".ps-plan-lines li")).toHaveLength(2);
  });

  it("没有手账（澳门）就没有这一块", () => {
    expect(pageOf(renderView(planView(demoPlan("fx-plan-macau"))).container)).toBeNull();
  });
});

/* ---------------- 5. 出发前会再确认 ---------------- */

describe("出发前会再确认的资料（preconditions）", () => {
  const preOf = (container: HTMLElement) => [...container.querySelectorAll(".ps-plan-pre li")].map((li) => text(li));

  it("澳门（想去）：船班过期了标“待确认”；船票已核对写有效到哪天（左闭右开，到 9 月 30 日）", () => {
    const { container } = renderView(planView(demoPlan("fx-plan-macau")));
    expect(text(section(container, "出发前会再确认"))).toContain("出发那一刻，TA 会再确认这几条资料还有效；过期了就先不出发，重新查一遍。");
    expect(preOf(container)).toEqual(["路线：每 30 分钟一班（演示）过期了，待确认", "票价：约 100 港币（演示），估算有效到 2026年9月30日"]);
    expect(container.querySelectorAll(".ps-plan-pre .ps-plan-tag--pending")).toHaveLength(1);
  });

  it("西九龙（可以出发）：天气预报有效到 9 月 26 日", () => {
    const { container } = renderView(planView(demoPlan("fx-plan-west-kowloon")));
    expect(preOf(container)).toEqual(["天气：9月26日多云，晚上转凉（演示预报）有效到 2026年9月26日"]);
  });

  it("引用的资料找不到了：照实说“这条资料找不到了，待确认”，不当成已核对", () => {
    const b = demoPlan("fx-plan-west-kowloon");
    rev(b).preconditions.push("fx-fact-does-not-exist");
    const view = planView(b);
    expect(view.preconditions[1]).toMatchObject({ topic: "其他资料", detail: null, pendingText: "这条资料找不到了，待确认", until: null });
  });

  it("出发以后、取消了、没有前置资料、还没有计划：都没有这一块", () => {
    const departed = demoPlan("fx-plan-shenzhen-bay");
    rev(departed).preconditions = ["fx-fact-szb-route"];
    expect(planView(departed).preconditions).toEqual([]);
    const cancelled = demoPlan("fx-plan-airport");
    rev(cancelled).preconditions = ["fx-fact-airport-place"];
    expect(planView(cancelled).preconditions).toEqual([]);
    expect(planView(demoPlan("fx-plan-tokyo")).preconditions).toEqual([]);
    const { container } = renderView(wishView(demoWish()));
    expect([...container.querySelectorAll("h2")].map((h) => h.textContent)).not.toContain("出发前会再确认");
  });
});

/* ---------------- 6. 三种钱分开 ---------------- */

describe("星币：攒钱目标不是路费；路费只认这一版计划上的行程摘要（fare 是标价，fare_waived 为真＝用了券、实付 0）", () => {
  const coinsText = (view: PlanView) => {
    const { container } = renderView(view);
    const el = container.querySelector('[data-money="coins"]');
    const out = el ? text(el) : null;
    cleanup();
    return out;
  };
  const withJourney = (id: string, journey: TravelJourneySummary | null) => {
    const b = demoPlan(id);
    rev(b).journey = journey;
    return b;
  };

  it("出发前说“攒钱目标”（不说路费），并写现有与还差多少；可以出发时写“已经攒够”", () => {
    const tokyo = coinsText(planView(demoPlan("fx-plan-tokyo")));
    expect(tokyo).toContain("攒钱目标 120 星币");
    expect(tokyo).toContain("截至 2026年9月24日 07:30 有 45，还差 75");
    expect(tokyo).not.toContain("路费");
    const ready = coinsText(planView(demoPlan("fx-plan-west-kowloon")));
    expect(ready).toContain("攒钱目标 12 星币");
    expect(ready).toContain("已经攒够");
  });

  it("演示：出发前的几份计划都还没关联行程（journey 为 null）；已出发那趟用了驾校借车券（这趟不用租车费、标价 20 星币划掉），已回来那趟路费 8 星币", () => {
    for (const id of ["fx-plan-tokyo", "fx-plan-macau", "fx-plan-west-kowloon", "fx-plan-airport"]) expect(rev(demoPlan(id)).journey, id).toBeNull();
    expect(rev(demoPlan("fx-plan-shenzhen-bay")).journey).toEqual({ journey_id: "fx-journey-shenzhen-bay", fare: 20, fare_waived: true });
    expect(coinsText(planView(demoPlan("fx-plan-shenzhen-bay")))).toContain("用了驾校借车券，这趟不用租车费");
    expect(coinsText(planView(demoPlan("fx-plan-shenzhen-bay")))).toContain("标价 20 星币");
    expect(coinsText(planView(demoPlan("fx-plan-harbour-cafe")))).toContain("路费 8 星币");
  });

  it.each([
    ["用了驾校借车券（fare 仍是标价，实付 0）", "用了驾校借车券，这趟不用租车费", { journey_id: "j-1", fare: 20, fare_waived: true }],
    ["没用券、fare > 0", "路费 8 星币", { journey_id: "j-1", fare: 8, fare_waived: false }],
    ["fare 为 0（散步、打工）", "这趟不花路费", { journey_id: "j-1", fare: 0, fare_waived: false }],
    ["fare 为 0 又标着用券（产生不出来的组合）：不写“省下 0”", "这趟不花路费", { journey_id: "j-1", fare: 0, fare_waived: true }],
  ] as const)("出发之后 · %s：写“%s”", (_label, expected, journey) => {
    for (const id of ["fx-plan-harbour-cafe", "fx-plan-shenzhen-bay"]) {
      const out = coinsText(planView(withJourney(id, { ...journey })));
      expect(out, id).toContain(expected);
      expect(out, id).not.toMatch(/省下 0|(^|[^0-9])0 星币/);
    }
  });

  it("用券那趟不算作花出去的钱：不出现“路费 N 星币”“花了”“付过”“实付”，fare 只作为划掉的标价出现", () => {
    const out = coinsText(planView(demoPlan("fx-plan-shenzhen-bay")))!;
    expect(out).toContain("用了驾校借车券，这趟不用租车费");
    expect(out).not.toMatch(/路费 \d+ 星币|花了|付过|实付/);
    // 标价只在划线里：<s> 里就是 fare，前面写明“标价”。
    const { container } = renderView(planView(demoPlan("fx-plan-shenzhen-bay")));
    const struck = container.querySelectorAll('[data-money="coins"] s');
    expect(struck).toHaveLength(1);
    expect(text(struck[0])).toBe("20 星币");
    expect(text(struck[0].parentElement)).toBe("标价 20 星币");
    // 没用券的那趟没有划线。
    cleanup();
    expect(renderView(planView(demoPlan("fx-plan-harbour-cafe"))).container.querySelector('[data-money="coins"] s')).toBeNull();
  });

  it("journey 为 null（还没关联行程）：出发之后也不显示路费", () => {
    for (const id of ["fx-plan-harbour-cafe", "fx-plan-shenzhen-bay"]) expect(coinsText(planView(withJourney(id, null))), id).toBeNull();
  });

  it("出发后提前结束（取消但有行程）的回顾也写路费；没出发就取消的没有这一行", () => {
    expect(coinsText(planView(demoPlan("fx-plan-airport")))).toBeNull();
    const b = withJourney("fx-plan-airport", { journey_id: "j-early", fare: 10, fare_waived: false });
    expect(coinsText(planView(b))).toContain("路费 10 星币");
  });

  it("形状不对（缺字段、fare 是负数或不是数）：不显示路费", () => {
    const odd = [{ journey_id: "j-old" }, { journey_id: "j-bad", fare: -3, fare_waived: false }, { journey_id: "j-str", fare: "8", fare_waived: false }, { journey_id: "j-nb", fare: 8, fare_waived: "no" }];
    for (const journey of odd) expect(coinsText(planView(withJourney("fx-plan-harbour-cafe", journey as unknown as TravelJourneySummary))), journey.journey_id).toBeNull();
  });

  it("绝不拿攒钱目标当路费：目标 999、路费 8 → 只说 8；用券、没有行程、形状不对时 999 也不出现在页面上", () => {
    const journeys: Array<TravelJourneySummary | null> = [
      { journey_id: "j-1", fare: 8, fare_waived: false },
      { journey_id: "j-1", fare: 20, fare_waived: true },
      null,
      { journey_id: "j-old" } as unknown as TravelJourneySummary,
    ];
    for (const journey of journeys) {
      const b = withJourney("fx-plan-harbour-cafe", journey);
      b.wish.funds_goal = 999;
      b.wish.target_coins = 999;
      const { container } = renderView(planView(b));
      expect(text(container)).not.toContain("999");
      if (journey?.fare === 8) expect(text(container.querySelector('[data-money="coins"]'))).toContain("路费 8 星币");
      cleanup();
    }
  });
});

describe("现实参考费用挂在价钱类事实上：只报已核实、认得出、有日期的；币种中文名、估算；其余不报金额", () => {
  const fareOf = (b: PlanBundle) => rev(b).facts.find((f) => f.fact_id === "fx-fact-macau-fare")!;

  it("澳门：两条现实参考——船票（已核实，演示）带适用区间（左闭右开，9月30日为止）与“估算”；接驳巴士没核实，value 里带着数也不报；都不提星币", () => {
    const { container } = renderView(planView(demoPlan("fx-plan-macau")));
    const real = container.querySelector('[data-money="real"]')!;
    const rows = [...real.querySelectorAll("li")].map((li) => [text(li.querySelector("strong")), text(li.querySelector("small"))]);
    expect(rows).toEqual([
      ["澳门码头一带（示意）的票价：约 100 港币（演示）", "2026年9月1日 至 2026年9月30日 · 估算"],
      ["澳门码头一带（示意）的票价：还没核实（演示）", "2026年9月20日 · 待核"],
    ]);
    expect(text(real)).not.toMatch(/12|澳门元|星币/);
    expect(text(container.querySelector('[data-money="coins"]'))).not.toMatch(/港币|澳门元|人民币/);
    // 资料来源那一块同样不写没核实的数（只标“还没核实，待确认”）。
    expect(text(container)).not.toMatch(/12 澳门元/);
    const busSource = [...section(container, "资料来源").querySelectorAll("li")].filter((li) => text(li).includes("票价还没核实，待确认"));
    expect(busSource).toHaveLength(1);
    expect(busSource[0].querySelector(".ps-plan-sources__value")).toBeNull();
  });

  it("东京：价钱没核实（value 为 null）写“还没核实”，不写 0；日期用事实自己的抓取日", () => {
    const { container } = renderView(planView(demoPlan("fx-plan-tokyo")));
    const real = container.querySelector('[data-money="real"]')!;
    expect(text(real.querySelector("strong"))).toBe("东京（示意）的票价：还没核实（演示）");
    expect(text(real.querySelector("small"))).toBe("2026年9月23日 · 待核");
    expect(text(real)).not.toMatch(/(^|[^0-9])0\s*(港币|星币)/);
  });

  it("A 的口径：价钱里没写 estimated 就认不出来——整条不报金额（也不标“估算”），资料来源那条也不写数", () => {
    const b = demoPlan("fx-plan-macau");
    fareOf(b).value = { amount: 100, currency: "HKD" };
    const view = planView(b);
    expect(view.realCosts[0]).toEqual({ key: "fx-fact-macau-fare", text: "澳门码头一带（示意）的票价：金额说不准，先不写（演示）", meta: "2026年9月1日 至 2026年9月30日" });
    expect(view.sources.find((s) => s.id === "fx-fact-macau-fare")!.detail).toBeNull();
    const { container } = renderView(view);
    expect(text(container)).not.toMatch(/100 港币|估算/);
  });

  it("estimated 写的不是 true / false（字符串、数字）同样认不出来；写明 false 就不标“估算”", () => {
    for (const estimated of ["yes", 1, null]) {
      const b = demoPlan("fx-plan-macau");
      fareOf(b).value = { amount: 100, currency: "HKD", estimated };
      expect(planView(b).realCosts[0].text, String(estimated)).toBe("澳门码头一带（示意）的票价：金额说不准，先不写（演示）");
    }
    const exact = demoPlan("fx-plan-macau");
    fareOf(exact).value = { amount: 100, currency: "HKD", estimated: false };
    expect(planView(exact).realCosts[0]).toMatchObject({ text: "澳门码头一带（示意）的票价：约 100 港币（演示）", meta: "2026年9月1日 至 2026年9月30日" });
  });

  it.each([
    ["CNY", "人民币"],
    ["HKD", "港币"],
    ["MOP", "澳门元"],
    ["JPY", "日元"],
    ["USD", "美元"],
    ["TWD", "新台币"],
    ["EUR", "EUR"],
  ])("币种 %s 显示成“%s”（六种中文名，其余照三字母代码）", (code, name) => {
    const b = demoPlan("fx-plan-macau");
    fareOf(b).value = { amount: 100, currency: code, estimated: true };
    expect(planView(b, { isDemo: false }).realCosts[0].text).toBe(`澳门码头一带（示意）的票价：约 100 ${name}`);
  });

  it("已核实但币种不是三字母大写、金额不是非负数、value 形状不对：不报金额，写“金额说不准，先不写”；资料没有任何日期同样不报", () => {
    for (const value of [{ amount: 100, currency: "hkd", estimated: true }, { amount: -1, currency: "HKD", estimated: true }, { amount: "100", currency: "HKD", estimated: true }, "约 100 港币", null]) {
      const b = demoPlan("fx-plan-macau");
      fareOf(b).value = value;
      expect(planView(b).realCosts[0].text, JSON.stringify(value)).toBe("澳门码头一带（示意）的票价：金额说不准，先不写（演示）");
    }
    const b = demoPlan("fx-plan-macau");
    Object.assign(fareOf(b), { valid_from: null, valid_until: null, source_ids: [], published_at: null, retrieved_at: null });
    expect(planView(b).realCosts[0]).toEqual({ key: "fx-fact-macau-fare", text: "澳门码头一带（示意）的票价：金额说不准，先不写（演示）", meta: "资料没有注明日期" });
  });

  it("结论不是已核实（过期、说法不一、没采用）的价钱一律不报数，写“还没核实”", () => {
    for (const verdict of ["stale", "conflicting", "rejected"] as const) {
      const b = demoPlan("fx-plan-macau");
      fareOf(b).verdict = verdict;
      expect(planView(b).realCosts[0].text, verdict).toBe("澳门码头一带（示意）的票价：还没核实（演示）");
    }
  });

  it("平台调用的账目（模型、请求号、用量、计费）即使混进数据也不出现在页面和视图里", () => {
    const b = demoPlan("fx-plan-macau") as PlanBundle & { receipts?: unknown[] };
    b.receipts = [{ operation_id: "op-7", requested_model: "deepseek-v4-flash", provider_request_id: "req_fx_0137", usage: { input_tokens: 1200 }, billed_amount: 0.0137, billed_currency: "USD" }];
    expect(JSON.stringify(planView(b))).not.toMatch(/0\.0137|USD|req_fx|deepseek|tokens/);
    expect(text(renderView(planView(b)).container)).not.toMatch(/0\.0137|USD|美元|req_fx|deepseek|token/i);
  });
});

/* ---------------- 7. 来源 ---------------- */

describe("资料来源带时间；过期、说法不一、没核实、没采用的标出来", () => {
  it("澳门：每条写明是什么、来源、抓取与发布时间；过期 / 说法不一 / 没核实各有说法；已核对的标已核对", () => {
    const { container } = renderView(planView(demoPlan("fx-plan-macau")));
    const items = [...section(container, "资料来源").querySelectorAll("li")];
    const byValue = (value: string) => items.find((li) => text(li.querySelector(".ps-plan-sources__value")) === value)!;
    // 过期的事实引用的来源不在计划的来源表里（只收已核验事实的来源）：时间取事实自己的，不说成“没有来源”。
    const ferry = byValue("每 30 分钟一班（演示）");
    expect(text(ferry)).toContain("路线过期了，待确认");
    expect(text(ferry)).toContain("抓取于 2026年9月24日 05:41");
    expect(text(ferry)).toContain("发布于 2026年9月10日");
    expect(text(ferry)).not.toContain("来源没有注明");
    for (const value of ["9月27日码头维修（演示）", "9月27日照常开放（演示）"]) expect(text(byValue(value))).toContain("说法不一，待确认");
    expect(text(byValue("9月27日天晴（演示，未核实）"))).toContain("还没核实，待确认");
    const fare = byValue("约 100 港币（演示），估算");
    expect(text(fare)).toContain("已核对");
    expect(text(fare)).toContain("来源：示例票价资料（演示）");
    expect(text(fare)).toContain("适用：2026年9月1日 至 2026年9月30日");
    expect(text(fare)).not.toContain("待确认");
    const place = byValue("澳门码头一带（示意）");
    expect(text(place)).toContain("抓取于 2026年9月24日 05:40");
    expect(text(place)).toContain("资料本身没有注明日期");
    const bench = byValue("码头边的观海长椅（示意）");
    expect(text(bench)).toContain("还没核实，待确认");
    expect(text(bench)).toContain("资料本身没有注明日期");
    expect(text(byValue("出入境要带星球护照（演示）"))).toContain("来源：example.net");
  });

  it("没有采用的资料（rejected）写“没有采用”、不显示它的内容；已核对的事实却对不上任何来源写“来源没有注明”", () => {
    const b = demoPlan("fx-plan-macau");
    rev(b).facts[0].verdict = "rejected";
    rev(b).facts[1].source_ids = ["fx-src-does-not-exist"];
    const view = planView(b);
    expect(view.sources[0]).toMatchObject({ pendingText: "没有采用", detail: null });
    expect(view.sources[1].refs.map((r) => r.publisher)).toEqual(["来源没有注明"]);
  });

  it("value 不是字符串也不是价钱（对象、数组）：不把对象原样倒给玩家", () => {
    const b = demoPlan("fx-plan-macau");
    rev(b).facts[0].value = { lat: 22.1, lng: 113.5, raw: "internal" };
    rev(b).facts[1].value = ["a", "b"];
    const view = planView(b);
    expect(view.sources[0].detail).toBeNull();
    expect(view.sources[1].detail).toBeNull();
    expect(text(renderView(view).container)).not.toMatch(/internal|\[object|lat/);
  });

  it("依据有问题的资料：地点卡标“资料待确认”，提醒标“待确认”；依据已核对资料的不标；地点核对看后端的 verified", () => {
    const { container } = renderView(planView(demoPlan("fx-plan-macau")));
    expect(text(placeItem(container, "1:st-0"))).toContain("资料待确认"); // 船班过期
    expect(text(placeItem(container, "1:st-1"))).not.toContain("待确认");
    expect(text(placeItem(container, "1:st-1"))).toContain("地点已核对");
    expect(text(placeItem(container, "1:st-2"))).toContain("资料待确认"); // 地点本身没核实
    expect(text(placeItem(container, "1:st-2"))).toContain("地点待确认");
    const tips = [...section(container, "提醒").querySelectorAll("li")];
    expect(tips.map((li) => Boolean(li.querySelector(".ps-plan-tag--pending")))).toEqual([false, true, false]);
  });

  it("提醒和支持它的事实一一对应（照 DTO 说明）：没有 fact_ids 的提醒不出现", () => {
    const b = demoPlan("fx-plan-macau");
    rev(b).owner_tips.push({ text: "没有依据的一句提醒", fact_ids: [] });
    const { container } = renderView(planView(b));
    expect(section(container, "提醒").querySelectorAll("li")).toHaveLength(3);
    expect(text(container)).not.toContain("没有依据的一句提醒");
  });

  it("时间按 TA 所在城市的时区显示（暂定 Asia/Shanghai）：UTC 21:41 是次日 05:41；认不出的时间不显示", () => {
    const b = demoPlan("fx-plan-macau");
    rev(b).facts.find((f) => f.fact_id === "fx-fact-macau-ferry")!.retrieved_at = "2026-09-23T21:41:00Z";
    rev(b).facts.find((f) => f.fact_id === "fx-fact-macau-notice-a")!.retrieved_at = "not-a-time";
    const view = planView(b);
    const byId = (id: string) => view.sources.find((s) => s.id === id)!;
    expect(byId("fx-fact-macau-ferry").times).toContain("抓取于 2026年9月24日 05:41");
    expect(byId("fx-fact-macau-notice-a").times.some((t) => t.startsWith("抓取于"))).toBe(false);
  });

  it("时区在代码里标成“暂定”、写明待用户决定（不写成“默认”）；给了别的时区就按那个时区换算", () => {
    expect(PROVISIONAL_ZONE).toBe("Asia/Shanghai");
    const model = sourceOf("model.ts");
    expect(model).toMatch(/暂定时区：Asia\/Shanghai/);
    expect(model).toContain("待用户决定");
    expect(model).not.toMatch(/DEFAULT_ZONE|默认 Asia\/Shanghai/);
    const b = demoPlan("fx-plan-macau");
    rev(b).facts.find((f) => f.fact_id === "fx-fact-macau-ferry")!.retrieved_at = "2026-09-23T21:41:00Z";
    expect(planView(b, { timezone: "Asia/Tokyo" }).sources.find((s) => s.id === "fx-fact-macau-ferry")!.times).toContain("抓取于 2026年9月24日 06:41");
  });

  it("发布时间落在当地零点只写日期（不写“00:00”）；不在零点的写到分钟；抓取时间照常到分钟", () => {
    const macau = planView(demoPlan("fx-plan-macau"));
    const ferry = macau.sources.find((s) => s.id === "fx-fact-macau-ferry")!;
    expect(ferry.times).toEqual(["抓取于 2026年9月24日 05:41", "发布于 2026年9月10日"]);
    const fare = macau.sources.find((s) => s.id === "fx-fact-macau-fare")!;
    expect(fare.refs[0].times).toEqual(["抓取于 2026年9月24日 05:43", "发布于 2026年9月20日"]);
    const weather = planView(demoPlan("fx-plan-west-kowloon")).sources.find((s) => s.id === "fx-fact-wkl-weather")!;
    expect(weather.refs[0].times).toEqual(["抓取于 2026年9月24日 05:15", "发布于 2026年9月24日 05:00"]);
    expect(text(renderView(macau).container)).not.toContain("00:00");
  });

  it("有效期左闭右开（§29.3）：[9月26日 0点, 9月27日 0点) 只写“9月26日”，计划的“按这一天的资料安排”同样", () => {
    const view = planView(demoPlan("fx-plan-west-kowloon"));
    expect(view.sources.find((s) => s.id === "fx-fact-wkl-weather")!.times).toContain("适用：2026年9月26日");
    expect(view.validity).toBe("2026年9月26日");
  });
});

/* ---------------- 8. 外链 ---------------- */

describe("外链只收 http(s)、新窗口、带 rel；地图链接只用后端给的 nav_url", () => {
  it.each(ALL_DEMO_VIEWS)("%s：所有链接都是新窗口、rel=\"noopener noreferrer\"、http(s)", (_id, make) => {
    const { container } = renderView(make());
    container.querySelectorAll("a").forEach((a) => {
      expect(a.getAttribute("target")).toBe("_blank");
      expect(a.getAttribute("rel")).toBe("noopener noreferrer");
      expect(a.getAttribute("href")).toMatch(/^https?:\/\//);
    });
  });

  it("前提：演示里确实有来源链接和地图链接（否则上面的检查什么都没查）；没核实的地点（观海长椅）没有 nav_url、没有地图链接", () => {
    const b = demoPlan("fx-plan-macau");
    const { container } = renderView(planView(b));
    expect(section(container, "资料来源").querySelectorAll("a").length).toBeGreaterThanOrEqual(4);
    expect(container.querySelectorAll('a[href^="https://uri.amap.com/marker?"]')).toHaveLength(2);
    expect(rev(b).stops[2]).toMatchObject({ verified: false, nav_url: null });
    expect(placeItem(container, "1:st-2").querySelector("a")).toBeNull();
  });

  it("地图链接就是后端的 nav_url 原样；nav_url 为空时即使有坐标也不给链接（不拿 lat/lng 自己拼）；不是 http(s) 也不给", () => {
    const b = demoPlan("fx-plan-west-kowloon");
    const a = renderView(planView(b));
    const link = placeItem(a.container, "2:st-0").querySelector("a")!;
    expect(link.getAttribute("href")).toBe(rev(b).stops[0].nav_url);
    expect(text(link)).toBe("在地图上看 ↗");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    cleanup();
    rev(b).stops[0].nav_url = null;
    rev(b).stops[1].nav_url = "javascript:alert(1)";
    expect(rev(b).stops[0]).toMatchObject({ lat: 22.304, lng: 114.166 });
    const c = renderView(planView(b));
    expect(placeItem(c.container, "2:st-0").querySelector("a")).toBeNull();
    expect(placeItem(c.container, "2:st-1").querySelector("a")).toBeNull();
    expect(c.container.querySelector('a[href*="amap"]')).toBeNull();
  });

  it("来源地址不是 http(s)（javascript:、data:、ftp:）：不做成链接，只写机构名；没有机构名显示域名；域名也没有写“来源没有注明”", () => {
    const b = demoPlan("fx-plan-macau");
    const src = (id: string) => rev(b).sources.find((s) => s.source_id === id)!;
    src("fx-src-fare").url = "javascript:alert(1)";
    src("fx-src-map-macau").url = "ftp://example.org/map";
    const view = planView(b);
    const ref = (factId: string) => view.sources.find((s) => s.id === factId)!.refs[0];
    expect(ref("fx-fact-macau-fare")).toMatchObject({ href: null, publisher: "示例票价资料（演示）" });
    expect(ref("fx-fact-macau-place")).toMatchObject({ href: null, publisher: "示例地图核对（演示）" });
    expect(ref("fx-fact-macau-passport")).toMatchObject({ publisher: "example.net", href: "https://example.net/demo/pier-news" });
    src("fx-src-pier").url = "data:text/html,<script>alert(1)</script>";
    expect(planView(b).sources.find((s) => s.id === "fx-fact-macau-passport")!.refs[0]).toMatchObject({ publisher: "来源没有注明", href: null });
  });
});

/* ---------------- 9. 演示标识 ---------------- */

describe("演示数据处处有“演示”", () => {
  it("编号 fx- 开头；地名带“示意”或“演示”；资料来源只用保留域名；坐标要么成对给出（WGS-84 范围内）要么都没有；nav_url 只给核实过的地点", () => {
    expect(DEMO_CURRENT_WISH.wish_id.startsWith("fx-")).toBe(true);
    let coords = 0;
    for (const b of DEMO_PLANS) {
      expect(b.plan.plan_id.startsWith("fx-")).toBe(true);
      for (const r of b.plan.revisions) {
        for (const s of r.stops) {
          expect(s.name).toMatch(/示意|演示/);
          if (!s.verified) expect(s.nav_url, s.name).toBeNull();
          if (s.lat == null || s.lng == null) {
            expect([s.lat, s.lng], s.name).toEqual([null, null]);
            continue;
          }
          expect(Math.abs(s.lat)).toBeLessThanOrEqual(90);
          expect(Math.abs(s.lng)).toBeLessThanOrEqual(180);
          coords += 1;
        }
        for (const src of r.sources) if (src.url) expect(new URL(src.url).hostname).toMatch(/^example\.(org|com|net)$/);
      }
    }
    expect(coords).toBeGreaterThanOrEqual(10);
  });

  it.each(ALL_DEMO_VIEWS)("%s：计划页挂“演示计划”", (_id, make) => {
    const { container } = renderView(make());
    expect(text(container.querySelector(".ps-plan-hero .ps-origin"))).toBe("演示计划");
  });
});

/* ---------------- 10. 列表与路由（fixture，真实路由表） ---------------- */

describe("攻略手账列表分两块；点卡片进心愿页 / 计划页，返回 /guides", () => {
  it("fixture /guides：“想去 / 准备中”在前、“去过的”在后；当前心愿进 /guides/wish，计划进 /guides/plan/…；卡片与标题旁都有“演示”", async () => {
    const { container } = renderApp("/guides");
    const wishing = await screen.findByRole("region", { name: "想去 / 准备中" });
    const past = screen.getByRole("region", { name: "去过的" });
    expect(wishing.compareDocumentPosition(past) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect([...container.querySelectorAll("[data-shelf]")].map((el) => el.getAttribute("data-shelf"))).toEqual(["wishing", "past"]);
    const first = [...wishing.querySelector(".ps-plan-cards:not(.ps-plan-cards--after)")!.querySelectorAll<HTMLElement>(".ps-plan-card")];
    expect(first.map((card) => card.getAttribute("href"))).toEqual(["/guides/wish", "/guides/plan/fx-plan-tokyo", "/guides/plan/fx-plan-macau", "/guides/plan/fx-plan-west-kowloon"]);
    expect(first.map((card) => text(card.querySelector(".ps-chip")))).toEqual(["资料准备中", "等攒够星币", "资料待确认", "可以出发"]);
    expect(first.map((card) => text(card.querySelector(".ps-plan-card__line")))).toEqual(["TA 正在查资料", "还差 75 星币", "有资料过期了，还在确认", "都准备好了"]);
    const after = wishing.querySelector(".ps-plan-cards--after")!;
    expect([...after.querySelectorAll(".ps-plan-card .ps-chip")].map((el) => el.textContent)).toEqual(["已出发", "已回来", "已取消"]);
    expect(text(wishing.querySelector(".ps-plan-shelf__head .ps-origin"))).toBe("演示");
    wishing.querySelectorAll(".ps-plan-card").forEach((card) => expect(text(card.querySelector(".ps-origin"))).toBe("演示"));
    expect(text(wishing)).toContain("真实情况下，TA 同一时间只惦记一个地方");
    expectPlainLanguage(text(wishing));
  });

  it("“去过的”在演示下不再是一直转的骨架屏：演示攻略为空时说“还没有攻略手账”", async () => {
    renderApp("/guides");
    const past = await screen.findByRole("region", { name: "去过的" });
    expect(await within(past).findByText("还没有攻略手账")).toBeTruthy();
    expect(past.querySelector(".ps-skeleton")).toBeNull();
  });

  it("点“TA 想去 广州”（资料还在查、没有计划）进 /guides/wish；只有一个 h1；顶栏返回退回 /guides", async () => {
    const { router } = renderApp("/guides");
    const wishing = await screen.findByRole("region", { name: "想去 / 准备中" });
    fireEvent.click(within(wishing).getByRole("link", { name: /TA 想去 广州/ }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/guides/wish"));
    expect(await screen.findByRole("heading", { level: 1, name: "TA 想去 广州" })).toBeTruthy();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByText("TA 查好资料以后，路线和提醒会写在这里。")).toBeTruthy();
    const back = screen.getByRole("link", { name: "返回" });
    expect(back.getAttribute("href")).toBe("/guides");
    fireEvent.click(back);
    await waitFor(() => expect(router.state.location.pathname).toBe("/guides"));
  });

  it("点“TA 想去 东京”进 /guides/plan/fx-plan-tokyo", async () => {
    const { router } = renderApp("/guides");
    const wishing = await screen.findByRole("region", { name: "想去 / 准备中" });
    fireEvent.click(within(wishing).getByRole("link", { name: /TA 想去 东京/ }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/guides/plan/fx-plan-tokyo"));
    expect(await screen.findByRole("heading", { level: 1, name: "TA 想去 东京" })).toBeTruthy();
  });

  it.each(["/guides/wish", "/guides/plan/fx-plan-macau"])("直接打开 %s：只有一个“返回”去 /guides；二级页不显示底栏", async (path) => {
    const { router, container } = renderApp(path);
    await screen.findByRole("article");
    const backs = screen.getAllByRole("link", { name: "返回" });
    expect(backs).toHaveLength(1);
    expect(backs[0].getAttribute("href")).toBe("/guides");
    expect(screen.queryByRole("navigation", { name: "主导航" })).toBeNull();
    expect(container.querySelector(".ps-shell")?.className).toContain("ps-shell--no-tabs");
    fireEvent.click(backs[0]);
    await waitFor(() => expect(router.state.location.pathname).toBe("/guides"));
  });

  it("fixture 里没有这份计划：说“这份计划还没写好，或者已经不在了”（演示没有原因码，不出“技术信息”），返回仍去 /guides；那句下面的“回到手账列表”点了就回 /guides", async () => {
    const { container, router } = renderApp("/guides/plan/fx-plan-nowhere");
    const title = await screen.findByText("这份计划还没写好，或者已经不在了");
    expect(title.closest(".ps-state")?.querySelector("details")).toBeNull();
    expect(container.querySelector("details.ps-state__tech")).toBeNull();
    expect(screen.getByRole("link", { name: "返回" }).getAttribute("href")).toBe("/guides");
    const toList = screen.getByRole("link", { name: "回到手账列表" });
    expect(toList.getAttribute("href")).toBe("/guides");
    expect(toList.closest(".ps-state")).toBe(title.closest(".ps-state"));
    fireEvent.click(toList);
    await waitFor(() => expect(router.state.location.pathname).toBe("/guides"));
  });

  it("I 已定：计划接口答 404 + plan_not_found（形状同 no_journey）→“这份计划还没写好，或者已经不在了”，错误码与原因码只收进默认收起的“技术信息”", () => {
    const notFound = new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: "没有这份计划。", requestId: "req-9", details: { reason: "plan_not_found" } });
    expect(isPlanNotFound(notFound)).toBe(true);
    // 对照：别的 404 原因、别的状态、不是接口错误，都不算“计划不在了”（照常走出错页，可重试）。
    expect(isPlanNotFound(new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: "x", details: { reason: "no_journey" } }))).toBe(false);
    expect(isPlanNotFound(new ApiError({ kind: "http", status: 409, code: "CONFLICT", message: "x", details: { reason: "plan_not_found" } }))).toBe(false);
    expect(isPlanNotFound(new Error("boom"))).toBe(false);
    const { container } = render(
      <MemoryRouter>
        <PlanMissing error={notFound} />
      </MemoryRouter>,
    );
    expect(text(container.querySelector(".ps-state__title"))).toBe("这份计划还没写好，或者已经不在了");
    // 说了“回到手账列表看看”，这句下面就有去手账列表（/guides）的按钮；“技术信息”排在按钮后面。
    const toList = within(container).getByRole("link", { name: "回到手账列表" });
    expect(toList.getAttribute("href")).toBe("/guides");
    const sentence = [...container.querySelectorAll(".ps-state div")].find((el) => el.textContent === "回到手账列表看看。")!;
    expect(sentence).toBeTruthy();
    expect(sentence.compareDocumentPosition(toList) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(toList.compareDocumentPosition(container.querySelector("details")!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const tech = container.querySelector("details")!;
    expect(tech.hasAttribute("open")).toBe(false);
    expect(text(tech.querySelector("summary"))).toBe("技术信息");
    expect(text(tech.querySelector(".ps-state__meta"))).toBe("NOT_FOUND · plan_not_found · request_id req-9");
    // 收起的部分之外只有人话。
    expect(plainText(container)).not.toMatch(/NOT_FOUND|plan_not_found|req-9/);
  });

  it("I 已定：旅行路由定不了是哪只宠物时 409 + pet_required →“需要先选一只宠物”，原因码只进“技术信息”", () => {
    const petRequired = new ApiError({ kind: "http", status: 409, code: "CONFLICT", message: "请先选宠物。", details: { reason: "pet_required" } });
    expect(isPetRequired(petRequired)).toBe(true);
    expect(isPetRequired(new ApiError({ kind: "http", status: 409, code: "CONFLICT", message: "x", details: { reason: "not_enrolled" } }))).toBe(false);
    expect(isPetRequired(new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: "x", details: { reason: "pet_required" } }))).toBe(false);
    const { container } = render(<PetRequired error={petRequired} />);
    expect(text(container.querySelector(".ps-state__title"))).toBe("需要先选一只宠物");
    expect(text(container.querySelector("details.ps-state__tech .ps-state__meta"))).toBe("CONFLICT · pet_required");
    expect(plainText(container)).not.toMatch(/CONFLICT|pet_required/);
  });

  it("只看某一趟旅程的手账（?journey=）时不显示“想去 / 准备中”", async () => {
    renderApp("/guides?journey=j-1");
    await screen.findByText("翻开 TA 的旅行笔记");
    await new Promise((r) => setTimeout(r, 300));
    expect(screen.queryByRole("region", { name: "想去 / 准备中" })).toBeNull();
    expect(screen.queryByText("去过的")).toBeNull();
  });
});

/* ---------------- 11. live：GET /travel/wish ---------------- */

const household = {
  household_id: "hh-1",
  name: "我们的家",
  home_id: "home-1",
  role: "admin",
  home_activated: true,
  member_count: 1,
  pets: [{ pet_id: "p-1", name: "栗子", species: "cat", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-20T00:00:00Z", added_by_you: true }],
} as unknown as HouseholdBrief;

const guide = (id: string): TravelGuide => ({
  guide_id: id,
  journey_id: `j-${id}`,
  city: "厦门",
  destination_title: "海边",
  title: "海边的一天",
  summary: null,
  stops: [],
  owner_tips: [],
  composed_by: "template",
  image_status: null,
  image_url: null,
  created_at: "2026-09-22T08:00:00Z",
  status: "completed",
});

/** live 的一个心愿（形状就是 generated 的 TravelWish）。 */
const liveWish = (over: Partial<TravelWish> = {}): TravelWish => ({
  wish_id: "w-live-1",
  pet_id: "p-1",
  wish_revision: 3,
  status: "active",
  destination_key: "seaside",
  destination_name: "海边步道",
  city: "厦门",
  owner_reason: "想去海边听一会儿浪。",
  funds_goal: 20,
  waiting_reasons: ["missing_funds"],
  research_state: "ready",
  research_round: 1,
  plan_id: null,
  plan_revision: null,
  journey_id: null,
  reconsider_after: null,
  last_considered_at: "2026-09-24T07:00:00Z",
  plan_stale: false,
  target_coins: 20,
  current_coins: 5,
  candidates: [],
  ...over,
});

function renderLive(path: string, element: ReactElement, routePath: string, travelWish: VisitService["travelWish"], travelPlan?: VisitService["travelPlan"]) {
  mode.dataMode = "live";
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const guides = vi.fn(async () => [guide("g-1")]);
  const services = { households: { list: async () => [household] }, transport: { guides }, visits: { travelWish, ...(travelPlan ? { travelPlan } : {}) } } as unknown as ServiceMap;
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={services}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path={routePath} element={<HouseholdProvider userId="u-1">{element}</HouseholdProvider>} />
          </Routes>
        </MemoryRouter>
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return { guides };
}

describe("live：心愿走 GET /travel/wish（显式带当前宠物）；没有、出错、要先选宠物都不造假；计划页走 GET /travel/plans/{plan_id}", () => {
  it("journey 模块的 live 服务：GET /travel/wish，带当前宠物；fixture 实现给演示心愿", async () => {
    const request = vi.fn(async () => null);
    const ctx = { mode: "live", api: { request, base: "/api/v1/web" } as unknown as ApiClient } as ServiceContext;
    const live = journeyModule.services!.visits!.live!(ctx) as VisitService;
    const signal = new AbortController().signal;
    await expect(live.travelWish("p-1", signal)).resolves.toBeNull();
    expect(request).toHaveBeenCalledWith("/travel/wish", { query: { pet_id: "p-1" }, signal });
    const fixture = journeyModule.services!.visits!.fixture!({ ...ctx, mode: "fixture" }) as VisitService;
    // 演示实现不看 petId（演示世界的家庭上下文没有当前宠物，不发请求）；live 从不传 null。
    expect((await fixture.travelWish(null))?.wish_id).toBe(DEMO_CURRENT_WISH.wish_id);
  });

  it("live 一律显式传当前宠物的 id：家庭名单读到之前不读心愿（不拿 null 让后端去推）", async () => {
    let release: (value: HouseholdBrief[]) => void = () => {};
    const list = vi.fn(() => new Promise<HouseholdBrief[]>((resolve) => (release = resolve)));
    const travelWish = vi.fn(async (_petId: string | null, _signal?: AbortSignal) => null);
    mode.dataMode = "live";
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <ServicesProvider services={{ households: { list }, visits: { travelWish } } as unknown as ServiceMap}>
          <MemoryRouter initialEntries={["/guides/wish"]}>
            <HouseholdProvider userId="u-1">
              <WishPage />
            </HouseholdProvider>
          </MemoryRouter>
        </ServicesProvider>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(list).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 30));
    expect(travelWish).not.toHaveBeenCalled();
    release([household]);
    await waitFor(() => expect(travelWish).toHaveBeenCalledTimes(1));
    expect(travelWish).toHaveBeenCalledWith("p-1", expect.anything());
    expect(travelWish.mock.calls.every(([petId]) => petId === "p-1")).toBe(true);
  });

  it("不变量（正常装配下到不了：live 路由总有家庭上下文和当前宠物）：拿不到当前宠物时不读心愿、绝不传 null，页面说“需要先选一只宠物”", async () => {
    mode.dataMode = "live";
    const travelWish = vi.fn(async (_petId: string | null, _signal?: AbortSignal) => null);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <ServicesProvider services={{ visits: { travelWish } } as unknown as ServiceMap}>
          <MemoryRouter initialEntries={["/guides/wish"]}>
            <WishPage />
          </MemoryRouter>
        </ServicesProvider>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("需要先选一只宠物")).toBeTruthy();
    await new Promise((r) => setTimeout(r, 30));
    expect(travelWish).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toMatch(/搭建中|演示/);
    expect(document.querySelector("details.ps-state__tech")).toBeNull();
  });

  it("/guides：没有活动心愿（200 + null）时不出“想去 / 准备中”，页面与原来一样；没有任何演示", async () => {
    const travelWish = vi.fn(async () => null);
    renderLive("/guides", <GuideBookPage />, "/guides", travelWish);
    expect(await screen.findByText("海边的一天")).toBeTruthy();
    await waitFor(() => expect(travelWish).toHaveBeenCalledWith("p-1", expect.anything()));
    await new Promise((r) => setTimeout(r, 30)); // 让 null 落进查询结果再看（有心愿时同一处会出现这一块，见下一条）
    expect(screen.queryByRole("region", { name: "想去 / 准备中" })).toBeNull();
    expect(screen.queryByText("去过的")).toBeNull();
    expect(document.body.textContent).not.toMatch(/演示|TA 想去/);
  });

  it("/guides：有活动心愿时列一张真的心愿卡（进 /guides/wish、用宠物名字、不挂演示）；原有攻略在“去过的”里", async () => {
    renderLive("/guides", <GuideBookPage />, "/guides", vi.fn(async () => liveWish()));
    const wishing = await screen.findByRole("region", { name: "想去 / 准备中" });
    const cards = within(wishing).getAllByRole("link");
    expect(cards.map((c) => c.getAttribute("href"))).toEqual(["/guides/wish"]);
    expect(text(cards[0])).toContain("栗子 想去 海边步道");
    expect(text(cards[0])).toContain("还差 15 星币");
    expect(text(wishing)).not.toContain("演示");
    expect(within(screen.getByRole("region", { name: "去过的" })).getByText("海边的一天")).toBeTruthy();
  });

  it("/guides/wish：读到心愿就显示（标题用宠物名字、不挂演示、钱包快照时间）；心愿已有计划时给去计划页的链接", async () => {
    renderLive("/guides/wish", <WishPage />, "/guides/wish", vi.fn(async () => liveWish({ plan_id: "plan-9", plan_revision: 2 })));
    expect(await screen.findByRole("heading", { level: 1, name: "栗子 想去 海边步道" })).toBeTruthy();
    expect(document.body.textContent).not.toContain("演示");
    expect(document.body.textContent).toContain("要攒到 20 星币；截至 2026年9月24日 15:00 有 5");
    expect(screen.getByRole("link", { name: "看这份计划" }).getAttribute("href")).toBe("/guides/plan/plan-9");
  });

  it("/guides/wish：没有活动心愿说“栗子 现在没有惦记的地方”；读取出错显示出错，都不拿演示顶上", async () => {
    renderLive("/guides/wish", <WishPage />, "/guides/wish", vi.fn(async () => null));
    expect(await screen.findByText("栗子 现在没有惦记的地方")).toBeTruthy();
    cleanup();
    renderLive("/guides/wish", <WishPage />, "/guides/wish", vi.fn(async () => Promise.reject(new Error("boom"))));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/演示|广州/);
  });

  it("/guides/wish：真收到 409 pet_required 时说“需要先选一只宠物”，不白屏、不一直转、不当成普通出错", async () => {
    const error = new ApiError({ kind: "http", status: 409, code: "CONFLICT", message: "请先选宠物。", details: { reason: "pet_required" } });
    renderLive("/guides/wish", <WishPage />, "/guides/wish", vi.fn(async () => Promise.reject(error)));
    expect(await screen.findByText("需要先选一只宠物")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByText("正在翻开 TA 的计划…")).toBeNull();
    expect(plainText(document.body)).not.toMatch(/pet_required|CONFLICT/);
  });

  it("/guides/plan/:planId：live 读 GET /travel/plans/{plan_id}（显式带当前宠物），不拿演示数据顶上；404 plan_not_found 说人话（详细用例见 claude-6c2b-plan-live.test.tsx）", async () => {
    const travelPlan = vi.fn(async (_planId: string, _petId: string | null, _signal?: AbortSignal) => {
      throw new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: "没有这份计划。", details: { reason: "plan_not_found" } });
    });
    renderLive("/guides/plan/fx-plan-tokyo", <PlanPage />, "/guides/plan/:planId", vi.fn(async () => null), travelPlan);
    expect(await screen.findByText("这份计划还没写好，或者已经不在了")).toBeTruthy();
    expect(travelPlan).toHaveBeenCalledWith("fx-plan-tokyo", "p-1", expect.anything());
    expect(document.body.textContent).not.toMatch(/演示|东京|星币|这里暂时还没开放/);
    expect(screen.getByRole("link", { name: "返回" }).getAttribute("href")).toBe("/guides");
  });
});

/* ---------------- 12. 地图面板那一行 ---------------- */

describe("地图面板的心愿那一行", () => {
  it("文字：想去 / 可以出发时“想去 {目的地} · {还差什么第一条}”；出发之后、取消都不出现", () => {
    expect(wishNoteLine(wishView(demoWish()))).toBe("想去 广州 · TA 正在查资料");
    expect(wishNoteLine(planView(demoPlan("fx-plan-tokyo")))).toBe("想去 东京 · 还差 75 星币");
    expect(wishNoteLine(planView(demoPlan("fx-plan-west-kowloon")))).toBe("想去 香港西九龙 · 都准备好了");
    for (const id of ["fx-plan-shenzhen-bay", "fx-plan-harbour-cafe", "fx-plan-airport"]) expect(wishNoteLine(planView(demoPlan(id))), id).toBeNull();
  });

  /** 同时报出那一行和底下那条读取的状态（同一个查询键，共用缓存）：断言“没有这一行”之前先等读取真的落定，免得空过。 */
  function NoteProbe({ onNote }: { onNote: (note: PanelNote | null, state: string) => void }) {
    const note = useWishNote();
    const read = useCurrentWish();
    onNote(note, read.state === "ready" ? (read.data ? "ready" : "ready-null") : read.state);
    return null;
  }

  function renderNote(services: Record<string, unknown>) {
    let latest: PanelNote | null = null;
    let state = "not-rendered";
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <ServicesProvider services={services as unknown as ServiceMap}>
          <MemoryRouter>
            <HouseholdProvider userId="u-1">
              <NoteProbe
                onNote={(note, s) => {
                  latest = note;
                  state = s;
                }}
              />
            </HouseholdProvider>
          </MemoryRouter>
        </ServicesProvider>
      </QueryClientProvider>,
    );
    return { noteOf: () => latest, stateOf: () => state };
  }

  it("live：带 petId（心愿自己的 pet_id）、点进 /guides/wish；面板显示别的宠物时被 arrangeNotes 滤掉", async () => {
    mode.dataMode = "live";
    const travelWish = vi.fn(async () => liveWish());
    const { noteOf } = renderNote({ households: { list: async () => [household] }, visits: { travelWish } });
    await waitFor(() => expect(noteOf()).not.toBeNull());
    const note = noteOf()!;
    expect(note).toEqual({ id: "wish", kind: "wish", text: "想去 海边步道 · 还差 15 星币", to: "/guides/wish", petId: "p-1" });
    expect(travelWish).toHaveBeenCalledWith("p-1", expect.anything());
    expect(arrangeNotes([note], "p-2")).toEqual([]);
    expect(arrangeNotes([note], "p-1")).toEqual([note]);
  });

  it("live：服务没给、报错、要先选宠物、没有活动心愿：都没有这一行（服务在查询函数里才取，不会把面板带崩）", async () => {
    mode.dataMode = "live";
    const strict = new Proxy({ households: { list: async () => [household] } } as Record<string, unknown>, {
      get: (target, key) => {
        if (typeof key === "string" && key in target) return target[key];
        throw new Error(`unexpected service ${String(key)}`);
      },
    });
    const petRequired = new ApiError({ kind: "http", status: 409, code: "CONFLICT", message: "x", details: { reason: "pet_required" } });
    const cases: Array<[string, Record<string, unknown>, string]> = [
      ["服务没给", strict, "error"],
      ["报错", { households: { list: async () => [household] }, visits: { travelWish: async () => Promise.reject(new Error("boom")) } }, "error"],
      ["要先选宠物", { households: { list: async () => [household] }, visits: { travelWish: async () => Promise.reject(petRequired) } }, "error"],
      ["没有活动心愿（200 + null）", { households: { list: async () => [household] }, visits: { travelWish: async () => null } }, "ready-null"],
    ];
    for (const [label, services, settled] of cases) {
      const { noteOf, stateOf } = renderNote(services);
      // 先等读取真的落定（家庭名单读到了、心愿读过了），再看有没有这一行。
      await waitFor(() => expect(stateOf(), label).toBe(settled));
      expect(noteOf(), label).toBeNull();
      cleanup();
    }
  });

  function renderMap(driving: unknown) {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 404 })));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const allowed: Record<string, unknown> = {
      households: { list: () => Promise.reject(new Error("fixture 不应请求家庭列表")) },
      driving,
      visits: { travelWish: async () => structuredClone(DEMO_CURRENT_WISH) },
    };
    const services = new Proxy(allowed, {
      get: (target, key) => {
        if (typeof key === "string" && key in target) return target[key];
        throw new Error(`unexpected service ${String(key)}`);
      },
    }) as unknown as ServiceMap;
    render(
      <QueryClientProvider client={client}>
        <ServicesProvider services={services}>
          <MemoryRouter initialEntries={["/map"]}>
            <Routes>
              <Route path="/map" element={<MapHomePage />} />
            </Routes>
          </MemoryRouter>
        </ServicesProvider>
      </QueryClientProvider>,
    );
  }

  it("演示地图：面板多一行“想去 广州 · TA 正在查资料”，点它去 /guides/wish", async () => {
    renderMap(createFixtureDrivingService({ latency: 0 }));
    const panel = await screen.findByRole("region", { name: /此刻$/ });
    const link = await within(panel).findByRole("link", { name: "想去 广州 · TA 正在查资料" });
    expect(link.getAttribute("href")).toBe("/guides/wish");
  });

  it("演示地图：驾校也有一行时，收起先说驾校（心愿排在驾校之后）；点开按 驾校 > 心愿 排", async () => {
    renderMap(createFixtureDrivingService({ stage: "enrolled", latency: 0 }));
    const panel = await screen.findByRole("region", { name: /此刻$/ });
    const group = await within(panel).findByRole("group", { name: "提醒，共 2 条" });
    const items = () => within(group).getAllByRole("listitem").map((li) => li.textContent);
    expect(items()).toEqual(["驾校 · 科目一可以约考了"]);
    fireEvent.click(within(group).getByRole("button", { name: "还有 1 条" }));
    expect(items()).toEqual(["驾校 · 科目一可以约考了", "想去 广州 · TA 正在查资料"]);
  });
});

/* ---------------- 13. 切宠物 ---------------- */

describe("切宠物", () => {
  it("停在 /guides/wish 或某份计划上切宠物：退回 /guides（householdContext 的 /guides/<段> 规则，没有改它）", () => {
    expect(listForPetScopedPath("/guides/wish")).toBe("/guides");
    expect(listForPetScopedPath("/guides/plan/fx-plan-tokyo")).toBe("/guides");
    expect(listForPetScopedPath("/guides")).toBeNull();
  });
});
