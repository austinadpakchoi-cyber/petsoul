/**
 * claude-6c2b（分身）· 我的 · 我的举报（/me/reports）。
 * - 解析（类型用契约 MyReports / ReportOutcomeItem；路由还没关联 response_model，照样逐条校验）：坏条目丢掉、
 *   结局 / 状态不是契约列出的值也丢掉、同一编号只留一条；外层坏了抛可重试的错误（读不出来不等于没举报过）。
 * - 处理结果只显示服务端的 message 原文，不按 outcome / status 自己拼（它们只决定颜色）；开头放服务端的 note 原文；
 *   主人自己写的理由原样给。不露内部编号与原始代码：report_id、target_id、status、outcome、理由代码（owner_reported）
 *   都不出现在页面文字里，编号也不进页面属性。
 * - 空：你还没有举报过。能力未接入（没装运营后台，503 NOT_CONFIGURED）：“这里暂时还没开放”（2026-09-24 前叫“这里还在搭建中”），不编内容、不说“你还没有举报过”。
 *   出错：可重试，重试成功后显示列表。
 * - live 经真实服务装配（假的 ApiClient）：请求 /reports/mine、在服务里就过解析；外层坏了显示可重试的出错。
 * - 演示模式经真实路由表：能力未接入（不编举报记录）；“我的”页“账号”一组里有“我的举报”，指向 /me/reports，点进去就是这页。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import type { HouseholdBrief, MyReports, SessionState } from "@/shared/contracts";
import { ApiError, isApiError } from "@/shared/api/errors";
import { createApiClient, type ApiClient } from "@/shared/api/client";
import { loadFeatureModules } from "@/app/modules";
import { buildRoutes } from "@/app/router";
import { buildServices, ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { MyReportsPage } from "@/features/me/MyReportsPage";
import { formatWhen, parseMyReports, readableReason, targetLabel } from "@/features/me/myReports";

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

const NOTE = "这里只有你自己提交的举报。处理结果只说结局，不透露是谁处理的、内部怎么判断的。";
const RECEIVED = "已收到，运营同学会尽快查看。";
const NO_VIOLATION = "已处理：查看后没有发现需要处理的问题。";

/** 本机时区的某个时刻（格式化按本机时区，这样断言不随测试机时区变）。 */
const localIso = (y: number, m: number, d: number, h: number, min: number) => new Date(y, m - 1, d, h, min).toISOString();

/** 一条后端原样的举报（字段照 app/web_admin/moderation.py 的 reporter_outcomes）。 */
const report = (over: Record<string, unknown> = {}): Record<string, unknown> => ({
  report_id: "rep-0001",
  target_kind: "post",
  target_id: "post-secret-42",
  reason: "owner_reported",
  created_at: localIso(2026, 9, 23, 21, 13),
  status: "received",
  outcome: "received",
  resolved_at: null,
  message: RECEIVED,
  ...over,
});

const SIGNED_IN: SessionState = {
  authenticated: true,
  user: { user_id: "owner-1", display_name: "小林", username: "lin", auth_method: "web_password" },
  csrf_required: false,
  expires_at: null,
  onboarding: { step: "active", pet_id: "pet-a", home_id: "home-1", reception_session_id: null, reception_skipped: false, home_activated_at: null, pet_origin: "own_pet" },
};

const HOUSEHOLD: HouseholdBrief = {
  household_id: "house-1",
  name: "海边的家",
  home_id: "home-1",
  role: "admin",
  home_activated: true,
  member_count: 1,
  pets: [{ pet_id: "pet-a", name: "奶茶", species: "cat", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-20T00:00:00Z", added_by_you: true }],
};

const notConfigured = () =>
  new ApiError({ kind: "capability", status: 503, code: "NOT_CONFIGURED", message: "social.report_outcomes 未配置", details: { capability: "social.report_outcomes" } });

/* ---------------- 渲染 ---------------- */

function strictServices(services: Record<string, unknown>): ServiceMap {
  return new Proxy(services as unknown as ServiceMap, {
    get(target, prop: string) {
      if (prop in target) return target[prop as keyof ServiceMap];
      throw new Error(`unexpected service ${prop}`);
    },
  });
}

function renderReports(services: ServiceMap) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [
      { path: "/me/reports", element: <MyReportsPage /> },
      { path: "/me", element: <p>这里是我的页</p> },
    ],
    { initialEntries: ["/me/reports"] },
  );
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={services}>
        <RouterProvider router={router} />
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return router;
}

/** live：会话与家庭照常，social 只有 myReports。 */
function liveWith(myReports: (signal?: AbortSignal) => Promise<MyReports>) {
  const spy = vi.fn(myReports);
  const services = strictServices({ session: { current: async () => SIGNED_IN }, households: { list: async () => [HOUSEHOLD] }, social: { myReports: spy } });
  return { spy, services };
}

/** 假的 ApiClient：按路径回预设的原始 JSON，记下请求过的路径；没登记的路径直接报错。 */
function fakeApi(routes: Record<string, () => unknown>) {
  const paths: string[] = [];
  const api: ApiClient = {
    base: "/api/v1/web",
    async request<T>(path: string): Promise<T> {
      paths.push(path);
      const handler = routes[path];
      if (!handler) throw new Error(`unexpected request ${path}`);
      return handler() as T;
    },
  };
  return { api, paths };
}

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

const reportItems = () => within(screen.getByRole("list", { name: "你的举报" })).getAllByRole("listitem");
const INTERNAL = ["rep-0001", "rep-0002", "post-secret-42", "cmt-secret-77", "owner_reported", "received", "resolved", "no_violation_found", "content_removed", "outcome", "status"];

/* ---------------- 解析与说法（纯函数） ---------------- */

describe("我的举报：解析与说法", () => {
  it("逐条按契约校验：必需字段缺了或类型不对、结局 / 状态不是契约列出的值，整条丢掉；resolved_at 缺省按 null；同一编号只留第一条；note 去首尾空白", () => {
    const view = parseMyReports({
      note: `  ${NOTE}  `,
      reports: [
        report({ report_id: "ok-1" }),
        report({ report_id: "ok-2", target_kind: "comment", status: "resolved", outcome: "content_removed", resolved_at: localIso(2026, 9, 24, 1, 0), message: "已处理：这条内容已不再公开展示。", reason: "他在评论里骂人" }),
        { ...report({ report_id: "ok-3" }), resolved_at: undefined },
        report({ report_id: "ok-1", message: "重复的一条" }),
        report({ report_id: "" }),
        report({ report_id: 17 }),
        report({ report_id: "bad-time", created_at: "昨天" }),
        report({ report_id: "no-message", message: "   " }),
        report({ report_id: "bad-kind", target_kind: 3 }),
        report({ report_id: "bad-reason", reason: 42 }),
        report({ report_id: "null-reason", reason: null }),
        { ...report({ report_id: "no-target" }), target_id: undefined },
        report({ report_id: "bad-resolved", resolved_at: "不是时间" }),
        report({ report_id: "bad-status", status: "pending" }),
        report({ report_id: "odd-status", status: { code: "x" } }),
        report({ report_id: "bad-outcome", outcome: "under_review" }),
        "不是对象",
        null,
        7,
      ],
    });
    expect(view.reports.map((item) => item.report_id)).toEqual(["ok-1", "ok-2", "ok-3"]);
    expect(view.reports[0].message).toBe(RECEIVED);
    expect(view.reports[2].resolved_at).toBeNull();
    expect(view.note).toBe(NOTE);
    // note 按契约是文本：没给或不是文本就当没有说明。
    expect(parseMyReports({ reports: [], note: 5 }).note).toBe("");
    expect(parseMyReports({ reports: [] }).note).toBe("");
  });

  it("外层坏了（不是对象、reports 不是列表）：抛可重试的错误，不当成“没有举报”", () => {
    for (const bad of [null, "x", [], { reports: null }, { reports: {} }, { note: NOTE }]) {
      let error: unknown = null;
      try {
        parseMyReports(bad);
      } catch (caught) {
        error = caught;
      }
      expect(isApiError(error) && error.retryable).toBe(true);
    }
  });

  it("说法：动态 / 评论 / 别的一律“一条内容”；像代码的理由不给看；时间按本机时区，不是今年加年份", () => {
    expect(targetLabel("post")).toBe("一条动态");
    expect(targetLabel("comment")).toBe("一条评论");
    expect(targetLabel("profile")).toBe("一条内容");
    expect(readableReason("owner_reported")).toBeNull();
    expect(readableReason("spam")).toBeNull();
    expect(readableReason("a.b:c-d")).toBeNull();
    expect(readableReason("   ")).toBeNull();
    expect(readableReason(null)).toBeNull();
    expect(readableReason("  他在评论里骂人  ")).toBe("他在评论里骂人");
    const now = new Date(2026, 8, 24, 12, 0);
    expect(formatWhen(localIso(2026, 9, 24, 5, 13), now)).toBe("9月24日 05:13");
    expect(formatWhen(localIso(2025, 12, 31, 23, 5), now)).toBe("2025年12月31日 23:05");
    expect(formatWhen("不是时间", now)).toBeNull();
    expect(formatWhen(null, now)).toBeNull();
  });
});

/* ---------------- 页面（live） ---------------- */

describe("我的举报：页面", () => {
  it("有记录：开头是 note 原文；每条写举报的是动态还是评论、什么时候举报的、结果原样；主人写的理由显示，编号与原始代码都不露", async () => {
    const view = parseMyReports({
      note: NOTE,
      reports: [
        report({ report_id: "rep-0001", target_id: "post-secret-42", created_at: localIso(2026, 9, 23, 21, 13) }),
        report({
          report_id: "rep-0002",
          target_kind: "comment",
          target_id: "cmt-secret-77",
          created_at: localIso(2026, 9, 22, 8, 5),
          status: "resolved",
          outcome: "no_violation_found",
          resolved_at: localIso(2026, 9, 22, 9, 30),
          message: NO_VIOLATION,
          reason: "他在评论里说难听的话",
        }),
      ],
    });
    const { spy, services } = liveWith(async () => view);
    renderReports(services);
    expect(await screen.findByText(NOTE)).toBeTruthy();
    expect(screen.getByRole("heading", { level: 1, name: "我的举报" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "返回我的" }).getAttribute("href")).toBe("/me");
    const [first, second] = reportItems();
    expect(reportItems()).toHaveLength(2);
    expect(first.textContent).toContain("一条动态");
    expect(first.textContent).toContain("9月23日 21:13 举报");
    expect(first.querySelector(".ps-report__result")?.textContent).toBe(RECEIVED);
    expect(first.querySelector(".ps-report__reason")).toBeNull(); // 理由是代码 owner_reported：不显示
    expect(first.querySelector(".ps-report__meta")).toBeNull();
    expect(second.textContent).toContain("一条评论");
    expect(second.textContent).toContain("9月22日 08:05 举报");
    expect(second.querySelector(".ps-report__reason")?.textContent).toBe("你写的理由：他在评论里说难听的话");
    expect(second.querySelector(".ps-report__result")?.textContent).toBe(NO_VIOLATION);
    expect(second.querySelector(".ps-report__meta")?.textContent).toBe("处理于 9月22日 09:30");
    const main = document.querySelector("main")?.textContent ?? "";
    for (const internal of INTERNAL) expect(main).not.toContain(internal);
    // 编号也不放进页面属性（例如 data-*、id、key 渲染出来的东西）。
    const html = document.querySelector("main")?.innerHTML ?? "";
    for (const id of ["rep-0001", "rep-0002", "post-secret-42", "cmt-secret-77"]) expect(html).not.toContain(id);
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("处理结果只显示服务端的 message 原文，不按 outcome / status 自己拼；它们只决定颜色", async () => {
    // 措辞故意和后端默认的四句都不一样：页面要是按结局代码自己配文案，这里就会露馅。
    const removed = "（口径测试）已处理：谢谢你告诉我们，这条已经收起来了。";
    const waiting = "（口径测试）收到啦，会有人来看。";
    const view = parseMyReports({
      note: NOTE,
      reports: [
        report({ report_id: "rep-a", status: "resolved", outcome: "content_removed", resolved_at: localIso(2026, 9, 23, 8, 0), message: removed }),
        report({ report_id: "rep-b", status: "received", outcome: "received", message: waiting }),
      ],
    });
    const { services } = liveWith(async () => view);
    renderReports(services);
    await screen.findByText(NOTE);
    const [first, second] = reportItems();
    expect(first.querySelector(".ps-report__result")?.textContent).toBe(removed);
    expect(second.querySelector(".ps-report__result")?.textContent).toBe(waiting);
    const main = document.querySelector("main")?.textContent ?? "";
    for (const wording of ["已处理：这条内容已不再公开展示。", "已收到，运营同学会尽快查看。", "已处理：查看后没有发现需要处理的问题。", "已处理：复核后这条内容恢复公开展示。"]) {
      expect(main).not.toContain(wording);
    }
    // 结局、状态只决定样式：已处理的是一种颜色，处理中是另一种。
    expect(first.getAttribute("data-settled")).toBe("yes");
    expect(second.getAttribute("data-settled")).toBe("no");
  });

  it("空：温和地说“你还没有举报过”，note 照样放在开头", async () => {
    const { services } = liveWith(async () => parseMyReports({ reports: [], note: NOTE }));
    renderReports(services);
    expect(await screen.findByText("你还没有举报过")).toBeTruthy();
    expect(screen.getByText(NOTE)).toBeTruthy();
    expect(screen.queryByRole("list", { name: "你的举报" })).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("能力未接入（没装运营后台，503 NOT_CONFIGURED）：这里暂时还没开放；不编内容，不说“你还没有举报过”；能力名收在“技术信息”里", async () => {
    const { services } = liveWith(async () => {
      throw notConfigured();
    });
    renderReports(services);
    expect(await screen.findByText("这里暂时还没开放")).toBeTruthy();
    expect(screen.queryByText("你还没有举报过")).toBeNull();
    expect(screen.queryByRole("list", { name: "你的举报" })).toBeNull();
    expect(screen.queryByText(NOTE)).toBeNull();
    expect(screen.queryByRole("button", { name: "重试" })).toBeNull();
    const tech = document.querySelector("details.ps-state__tech") as HTMLDetailsElement;
    expect(tech.open).toBe(false);
    expect(tech.textContent).toContain("social.report_outcomes");
  });

  it("出错（服务端 500）：没能完成这一步，可以重试；重试成功后显示列表", async () => {
    let calls = 0;
    const { spy, services } = liveWith(async () => {
      calls += 1;
      if (calls === 1) throw new ApiError({ kind: "http", status: 500, code: "INTERNAL_ERROR", message: "服务端出错了", retryable: true });
      return parseMyReports({ reports: [report()], note: NOTE });
    });
    renderReports(services);
    expect((await screen.findByRole("alert")).textContent).toContain("没能完成这一步");
    expect(screen.queryByText("你还没有举报过")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(await screen.findByText(NOTE)).toBeTruthy();
    expect(reportItems()).toHaveLength(1);
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it("live 经真实服务装配：请求 /reports/mine、在服务里就过解析（坏条目丢掉）；外层坏了显示可重试的出错，不说“没有举报”", async () => {
    const good = fakeApi({
      "/session": () => SIGNED_IN,
      "/households": () => [HOUSEHOLD],
      "/reports/mine": () => ({ note: NOTE, reports: [report({ report_id: "rep-a" }), report({ report_id: "rep-b", created_at: "坏时间" }), report({ report_id: "rep-c", target_kind: "comment" }), { nothing: true }] }),
    });
    renderReports(buildServices(loadFeatureModules(), { mode: "live", api: good.api }));
    expect(await screen.findByText(NOTE)).toBeTruthy();
    expect(reportItems().map((item) => item.querySelector("strong")?.textContent)).toEqual(["一条动态", "一条评论"]);
    expect(good.paths).toContain("/reports/mine");
    cleanup();

    const broken = fakeApi({ "/session": () => SIGNED_IN, "/households": () => [HOUSEHOLD], "/reports/mine": () => ({ reports: "oops" }) });
    renderReports(buildServices(loadFeatureModules(), { mode: "live", api: broken.api }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("举报记录暂时读不出来，请稍后再试。");
    expect(screen.getByRole("button", { name: "重试" })).toBeTruthy();
    expect(screen.queryByText("你还没有举报过")).toBeNull();
  });
});

/* ---------------- 演示模式与入口（真实路由表与演示服务） ---------------- */

describe("我的举报：演示模式与入口", () => {
  it("“我的”页“形象与账号”一组里有“我的举报”（在账号与设置前面），指向 /me/reports；点进去：演示模式没有举报记录，显示“这里暂时还没开放”，不编记录", async () => {
    const router = renderApp("/me");
    const accountGroup = await screen.findByRole("list", { name: "形象与账号" });
    const links = within(accountGroup).getAllByRole("link");
    expect(links.map((link) => link.getAttribute("href"))).toEqual(["/me/look", "/me/reports", "/settings"]);
    const entry = screen.getByRole("link", { name: /^我的举报/ });
    expect(entry.getAttribute("href")).toBe("/me/reports");
    expect(entry.textContent).toContain("举报过的内容和处理结果");
    fireEvent.click(entry);
    expect(await screen.findByText("这里暂时还没开放")).toBeTruthy();
    expect(router.state.location.pathname).toBe("/me/reports");
    expect(screen.getByRole("heading", { level: 1, name: "我的举报" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "返回我的" }).getAttribute("href")).toBe("/me");
    expect(screen.queryByRole("list", { name: "你的举报" })).toBeNull();
    expect(screen.queryByText("你还没有举报过")).toBeNull();
  });
});
