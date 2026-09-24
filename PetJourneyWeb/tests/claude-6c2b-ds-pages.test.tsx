/**
 * 爪爪驾校页面（claude-6c2b 驾校·页面分身，第一批，2026-09-24）：
 * 1) 总览一眼看懂：顶上“现在 / 下一步”卡说清走到哪一步、下一步做什么，整页只有一个主要动作；
 *    冷却写看的人本地的“几月几日 几点后可以再约”；有没考完的考试先接着考；已拿证待仪式时去领证是唯一的主要动作；
 *    报名前的科目行只说“报名后开放”，不说“可以约考 / 还剩几次机会 / 练习随时可以”（巡检 P2-1）。
 * 2) 成绩单：先结论（过没过、得分、及格线），再错在哪（每条扣分能跳到讲解或回放），最后下一步；
 *    全对时不再列一长串“对”（巡检 P2-2）；不露判定代码与英文。
 * 3) 科目页：上课 / 练习 / 正式考试三个入口分得清，各写一句现在的状态、点了跳到那一段；
 *    正式考试写清这是第几次机会、没过会怎样、冷却到几点、通过的样子；练习说明没有语病（巡检 P2-3）。
 * 全部走真实路由与驾校模块自己的演示服务（fixture 规则与服务端一致），不替身页面组件。
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import golden from "./fixtures/driving-golden.json";
import type { HomeSnapshot, HouseholdBrief, SchoolSession, SchoolSubject, SessionState } from "@/shared/contracts";
import { createApiClient, type ApiClient } from "@/shared/api/client";
import { ApiError } from "@/shared/api/errors";
import { fixtureHomeSnapshot } from "@/fixtures/home";
import { loadFeatureModules } from "@/app/modules";
import { buildRoutes } from "@/app/router";
import { buildServices, ServicesProvider } from "@/shared/services/registry";
import type { DrivingSchoolService, ServiceMap } from "@/shared/services/types";
import { buildSlotRegistry, SlotProvider } from "@/shared/slots/Slot";
import { createFixtureDrivingService } from "@/features/driving_school/service";
import type { Course, InputEventT } from "@/features/driving_school/sim/types";
import { DEMO_CURRICULUM, DEMO_QUESTIONS } from "@/fixtures/driving";
import { SEEK_LEAD_TICKS } from "@/features/driving_school/drive/ReplayViewer";
import { SCHOOL_ART } from "@/features/driving_school/assets";
import drivingModule from "@/features/driving_school/module";
import { formatTicks } from "@/features/driving_school/text";

// 默认演示模式；只有“切宠物”那条用例切到 live（与 tests/claude-6c2b-two-pets 同一种做法）。
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
});
afterEach(cleanup);
beforeAll(() => {
  // jsdom 没有 canvas：回放只看结构与文字
  HTMLCanvasElement.prototype.getContext = (() => null) as unknown as HTMLCanvasElement["getContext"];
});

const scripts = new Map((golden as unknown as { cases: { name: string; events: InputEventT[]; ticks: number }[] }).cases.map((c) => [c.name, c]));
let keySeq = 0;
const key = () => `ds-pages:${++keySeq}`;
/** 与页面同一种写法算期望值：看的人所在时区的“几月几日 几点”。 */
const clock = (iso: string) => new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(iso));

/** correct 可以逐题给（true＝这一题答对）。 */
async function quiz(svc: DrivingSchoolService, subject: "s1" | "s4", correctAll: boolean | boolean[]) {
  let s = await svc.createSession({ subject, mode: "formal", item: null }, key());
  s = await svc.begin(s.session_id);
  for (const [i, q] of DEMO_QUESTIONS[subject].entries()) {
    const correct = Array.isArray(correctAll) ? correctAll[i] : correctAll;
    const a = q.answer;
    const swapped = () => {
      const [x, y] = Object.keys(a.matches!);
      return { [x]: a.matches![y], [y]: a.matches![x] };
    };
    const ans = correct ? a : q.kind === "choice" ? { choice: q.options.find((o) => o.option_id !== a.choice)!.option_id } : q.kind === "order" ? { order: [...a.order!].reverse() } : { matches: swapped() };
    await svc.answer(s.session_id, { question_id: q.question_id, answer: { choice: ans.choice ?? null, order: ans.order ?? null, matches: ans.matches ?? null } });
  }
  return svc.submit(s.session_id);
}

async function abandon(svc: DrivingSchoolService, subject: SchoolSubject) {
  const s = await svc.begin((await svc.createSession({ subject, mode: "formal", item: null }, key())).session_id);
  return svc.abandon(s.session_id, true);
}

/** 用后端生成的标准操作（golden）开完练习；suffix 选“闯红灯”等变体。 */
async function drive(svc: DrivingSchoolService, subject: SchoolSubject, item: string | null, suffix: string): Promise<SchoolSession> {
  const s = await svc.begin((await svc.createSession({ subject, mode: "practice", item }, key())).session_id);
  for (let i = s.drive!.current_item; i < s.drive!.items.length; i++) {
    const script = scripts.get((s.drive!.items[i].course as unknown as Course).course_id + suffix)!;
    for (let from = 0; from < script.ticks; from += 300) {
      const upto = Math.min(script.ticks, from + 300);
      const r = await svc.inputs(s.session_id, { item_index: i, from_tick: from, upto_tick: upto, events: script.events.filter((e) => e.t >= from && e.t < upto) });
      if (r.item_status !== "running") break;
    }
    const now = await svc.session(s.session_id);
    if (now.state === "settled") return now;
  }
  return svc.session(s.session_id);
}

function renderApp(path: string, driving: DrivingSchoolService) {
  const modules = loadFeatureModules();
  const base = buildServices(modules, { mode: "fixture", api: createApiClient("/api/v1/web") });
  const services: ServiceMap = { ...base, driving };
  const router = createMemoryRouter(buildRoutes(modules), { initialEntries: [path] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={services}>
        <SlotProvider registry={buildSlotRegistry(modules.flatMap((m) => m.slots ?? []))}>
          <RouterProvider router={router} />
        </SlotProvider>
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return router;
}

const primaries = () => [...document.querySelectorAll("main .ps-btn--primary")].map((el) => el.textContent?.trim());

/* ---------------- 1. 总览 ---------------- */

describe("总览：一眼看懂现在在哪一步、下一步做什么", () => {
  it("已报名：顶上写第 2 步与四科进度，下一步去科目一；整页只有这一个主要动作", async () => {
    renderApp("/school", createFixtureDrivingService({ stage: "enrolled", latency: 0 }));
    const now = await screen.findByTestId("ds-now");
    expect(within(now).getByText("第 2 步 · 学四科 · 已通过 0/4")).toBeTruthy();
    expect(within(now).getByRole("heading", { name: "科目一可以约首次考试了" })).toBeTruthy();
    expect(within(now).getByText(/本轮还剩 2 次机会/)).toBeTruthy();
    expect(within(now).getByRole("link", { name: "去科目一：上课、练习、约考" }).getAttribute("href")).toBe("/school/subject/s1");
    expect(primaries()).toEqual(["去科目一：上课、练习、约考"]);
    // 四科紧跟在后面，每科写还剩几次机会或为什么还不能考
    const s1 = screen.getByRole("link", { name: /科目一：认识路上的规则/ });
    expect(s1.textContent).toMatch(/还剩 2 次机会 · 下一次是首次考试/);
    expect(screen.getByRole("link", { name: /科目二：把小车开稳/ }).textContent).toMatch(/先通过科目一才能约考/);
    // “现在”卡排在四科前面，教练卡挪到后面
    const order = [now, screen.getByRole("heading", { name: /四个科目/ }), document.querySelector(".ds-coach")!];
    for (let i = 1; i < order.length; i++) expect(order[i - 1].compareDocumentPosition(order[i]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("两次都没通过：写本地“几月几日 几点后可以再约”，科目行同样写几点；主要动作是去练习", async () => {
    const svc = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
    await quiz(svc, "s1", false);
    const second = await abandon(svc, "s1");
    const until = second.result!.next!.cooldown_until!;
    renderApp("/school", svc);
    const now = await screen.findByTestId("ds-now");
    expect(within(now).getByRole("heading").textContent).toBe(`科目一 ${clock(until)} 后可以再约考试`);
    expect(within(now).getByText(/还要等 \d+ 天/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /科目一：认识路上的规则/ }).textContent).toContain(`${clock(until)} 后可以再约`);
    expect(primaries()).toEqual(["去科目一练习"]);
  });

  it("有一场没考完的正式考试：先接着考它（链接到那一场）", async () => {
    const svc = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
    const open = await svc.createSession({ subject: "s1", mode: "formal", item: null }, key());
    renderApp("/school", svc);
    const now = await screen.findByTestId("ds-now");
    expect(within(now).getByRole("heading", { name: "科目一有一场正式考试还没考完" })).toBeTruthy();
    expect(within(now).getByText(/还不算次数/)).toBeTruthy();
    expect(within(now).getByRole("link", { name: "接着考科目一" }).getAttribute("href")).toBe(`/school/session/${open.session_id}`);
    expect(primaries()).toEqual(["接着考科目一"]);
  });

  it("四科全过、仪式还没做：去领证是唯一的主要动作（驾照小卡不再放第二个主按钮）", async () => {
    renderApp("/school", createFixtureDrivingService({ stage: "licensed", latency: 0 }));
    const now = await screen.findByTestId("ds-now");
    expect(within(now).getByText("第 3 步 · 领证")).toBeTruthy();
    expect(within(now).getByRole("link", { name: "去领证：盖章、合影" }).getAttribute("href")).toBe("/school/ceremony");
    expect(primaries()).toEqual(["去领证：盖章、合影"]);
    expect(screen.queryByRole("link", { name: "回看领证仪式" })).toBeNull();
  });

  it("报名前（TA 想学开车）：科目行只说“报名后开放”，不说可以约考、还剩几次、练习随时可以（巡检 P2-1）", async () => {
    renderApp("/school", createFixtureDrivingService({ stage: "wish", latency: 0 }));
    await screen.findByRole("button", { name: /报名爪爪驾校/ });
    const rows = screen.getAllByRole("link", { name: /^科目[一二三四]：/ });
    expect(rows).toHaveLength(4);
    for (const row of rows) {
      expect(row.textContent).toMatch(/报名后开放练习和考试/);
      expect(row.textContent).not.toMatch(/可以约考|还剩|本轮|随时可以/);
    }
    expect(primaries()).toEqual([expect.stringMatching(/报名爪爪驾校/)]);
  });
});

/* ---------------- 2. 成绩单 ---------------- */

describe("成绩单：先结论，再错在哪，最后下一步", () => {
  it("答题没通过：结论（没通过、得分、及格线）→ 错在哪 → 下一步；每条扣分能跳到那道题的讲解", async () => {
    const svc = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
    const r = await quiz(svc, "s1", false);
    renderApp(`/school/result/${r.session_id}`, svc);
    const verdict = await screen.findByTestId("ds-conclusion");
    expect(within(verdict).getByRole("heading", { name: "这次没通过" })).toBeTruthy();
    expect(verdict.textContent).toContain(`${r.result!.score} 分`);
    expect(verdict.textContent).toContain(`及格线 ${r.result!.pass_score} 分`);
    const wrong = screen.getByRole("heading", { name: "错在哪" });
    const next = screen.getByRole("heading", { name: "下一步" });
    expect(verdict.compareDocumentPosition(wrong) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(wrong.compareDocumentPosition(next) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByRole("link", { name: "先练一练，再约补考" }).getAttribute("href")).toBe("/school/subject/s1");
    // 跳到讲解：展开那道题并把焦点移过去
    const jumps = screen.getAllByRole("button", { name: "看讲解" });
    expect(jumps).toHaveLength(r.result!.deductions.length);
    const firstId = r.result!.deductions[0].question_id!;
    const target = document.getElementById(`ds-q-${firstId}`) as HTMLDetailsElement;
    target.open = false;
    fireEvent.click(jumps[0]);
    expect(document.activeElement).toBe(target);
    expect(target.open).toBe(true);
    expect(screen.getByRole("heading", { name: "错题讲解" })).toBeTruthy();
  });

  it("答对一部分：错题讲解只列答错的，序号仍是原来的第几题（巡检 P2-2 的另一半）", async () => {
    const svc = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
    const pattern = DEMO_QUESTIONS.s1.map((_, i) => i === 0);
    const r = await quiz(svc, "s1", pattern);
    renderApp(`/school/result/${r.session_id}`, svc);
    await screen.findByTestId("ds-conclusion");
    const listed = [...document.querySelectorAll(".ds-review")];
    expect(listed).toHaveLength(pattern.filter((ok) => !ok).length);
    expect(listed.every((el) => el.classList.contains("is-wrong"))).toBe(true);
    expect(listed[0].querySelector("summary")!.textContent).toMatch(/^2\. /);
  });

  it("答题全对：写全部答对、没有扣分，不再列一长串“对”（巡检 P2-2）", async () => {
    const svc = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
    const r = await quiz(svc, "s1", true);
    renderApp(`/school/result/${r.session_id}`, svc);
    const verdict = await screen.findByTestId("ds-conclusion");
    expect(within(verdict).getByRole("heading", { name: "通过了" })).toBeTruthy();
    expect(screen.getByText(`${DEMO_QUESTIONS.s1.length} 道题全部答对，没有扣分。`)).toBeTruthy();
    expect(screen.queryByRole("heading", { name: /错题/ })).toBeNull();
    expect(document.querySelectorAll(".ds-review")).toHaveLength(0);
    expect(screen.getByRole("link", { name: "看看下一科" })).toBeTruthy();
  });

  it("驾驶闯红灯：红线写第几秒、能跳到回放；各项与扣分都用中文，不露判定代码", async () => {
    const svc = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
    const r = await drive(svc, "s3", null, ".red_light");
    expect(r.result!.fatal!.kind).toBe("red_light");
    renderApp(`/school/result/${r.session_id}`, svc);
    const conclusion = await screen.findByTestId("ds-conclusion");
    // 分数够也不算：大号分数灰掉并写“这次不计分”，结论卡自己说清为什么（红线）
    expect(conclusion.querySelector(".ds-conclusion__score.is-void")).not.toBeNull();
    expect(within(conclusion).getByText("这次不计分")).toBeTruthy();
    expect(within(conclusion).getByText(`碰了红线（${r.result!.fatal!.label}），这次练习不算达标。`)).toBeTruthy();
    const fatal = screen.getByRole("note");
    expect(fatal.textContent).toMatch(/^红线：/);
    expect(fatal.textContent).toMatch(/第 (\d+ 分 )?\d+ 秒，已自动制动/);
    // “看回放”带上出事的那一项和那一刻（回放组件的定位参数接上前，先挂在回放卡上）
    const replay = document.getElementById("ds-replay")!;
    fireEvent.click(within(fatal).getByRole("button", { name: "看回放" }));
    expect(document.activeElement?.id).toBe("ds-replay");
    expect([replay.dataset.seekItem, replay.dataset.seekTick, replay.dataset.seekNonce]).toEqual([r.result!.fatal!.item, String(r.result!.fatal!.t), "1"]);
    fireEvent.click(within(fatal).getByRole("button", { name: "看回放" }));
    expect(replay.dataset.seekNonce).toBe("2");
    const main = document.querySelector("main")!.textContent!;
    expect(main).not.toMatch(/red_light|out_of_bounds|timeout|abandoned|route|reverse_park|side_park|\bdone\b|\bfailed\b|\bpending\b|\brunning\b|服务器/);
    expect(main).toMatch(/没完成/);
  });
});

describe("成绩单第二批：分数作废与回放定位", () => {
  it("练习里压线又出界：每条扣分的“看回放”带自己的项目和 tick，出界那条也是；结论写车开出了场地、这次不计分", async () => {
    const svc = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
    const r = await drive(svc, "s2", "reverse_park", ".wild");
    const timed = r.result!.deductions.filter((d) => d.t !== null && d.item);
    expect(timed.length, "前提：这一场有带时刻的扣分").toBeGreaterThan(0);
    expect(r.result!.fatal?.kind, "前提：这一场以出界结束").toBe("out_of_bounds");
    renderApp(`/school/result/${r.session_id}`, svc);
    const conclusion = await screen.findByTestId("ds-conclusion");
    expect(within(conclusion).getByText("这次不计分")).toBeTruthy();
    expect(within(conclusion).getByText("车开出了场地，这次练习不算达标。")).toBeTruthy();
    const rows = screen.getAllByRole("button", { name: "看回放" }).filter((b) => !screen.getByRole("note").contains(b));
    expect(rows.map((b) => [b.dataset.item, b.dataset.tick])).toEqual(timed.map((d) => [d.item, String(d.t)]));
    const replay = document.getElementById("ds-replay")!;
    fireEvent.click(rows[0]);
    expect([replay.dataset.seekItem, replay.dataset.seekTick]).toEqual([timed[0].item, String(timed[0].t)]);
    fireEvent.click(within(screen.getByRole("note")).getByRole("button", { name: "看回放" }));
    expect([replay.dataset.seekItem, replay.dataset.seekTick]).toEqual([r.result!.fatal!.item, String(r.result!.fatal!.t)]);
  });

  it("“看回放”真的定位：切到扣分发生的那一项，停在事发前一点（回放组件收到 seek）", async () => {
    const svc = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
    await quiz(svc, "s1", true);
    await abandon(svc, "s2"); // 首次没过 → 补考换 b 场地（b 场地的侧方停车有“开得毛躁”的标准操作）
    let s = await svc.begin((await svc.createSession({ subject: "s2", mode: "formal", item: null }, key())).session_id);
    const suffix: Record<string, string> = { "side_park.b": ".sloppy" };
    for (let i = s.drive!.current_item; i < s.drive!.items.length; i++) {
      const id = (s.drive!.items[i].course as unknown as Course).course_id;
      const script = scripts.get(id + (suffix[id] ?? ""))!;
      for (let from = 0; from < script.ticks; from += 300) {
        const upto = Math.min(script.ticks, from + 300);
        const r = await svc.inputs(s.session_id, { item_index: i, from_tick: from, upto_tick: upto, events: script.events.filter((e) => e.t >= from && e.t < upto) });
        if (r.item_status !== "running") break;
      }
      s = await svc.session(s.session_id);
      if (s.state === "settled") break;
    }
    s = await svc.session(s.session_id);
    const later = s.result!.deductions.find((d) => d.item === "side_park" && d.t !== null);
    expect(later, "前提：第二项（侧方停车）有带时刻的扣分").toBeTruthy();
    renderApp(`/school/result/${s.session_id}`, svc);
    await screen.findByTestId("ds-conclusion");
    const canvasLabel = () => document.querySelector("#ds-replay canvas")!.getAttribute("aria-label")!;
    const side = s.drive!.items.find((it) => it.item === "side_park")!;
    expect(canvasLabel().startsWith(side.title), "回放一开始停在第一项").toBe(false);
    const button = screen.getAllByRole("button", { name: "看回放" }).find((b) => b.dataset.item === "side_park" && b.dataset.tick === String(later!.t))!;
    fireEvent.click(button);
    const expected = `${side.title}回放，第 ${formatTicks(Math.max(0, Math.min(side.committed_tick, later!.t! - SEEK_LEAD_TICKS)))}`;
    await waitFor(() => expect(canvasLabel()).toBe(expected));
  });

  it("正式考试超时：同样把分数灰掉、写这次不计分，原因写这一场不通过", async () => {
    const svc = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
    await quiz(svc, "s1", true);
    const s = await svc.begin((await svc.createSession({ subject: "s2", mode: "formal", item: null }, key())).session_id);
    const limit = (s.drive!.items[0].course as unknown as Course).time_limit_ticks;
    for (let from = 0; from < limit; from += 900) await svc.inputs(s.session_id, { item_index: 0, from_tick: from, upto_tick: Math.min(limit, from + 900), events: [] });
    const done = await svc.session(s.session_id);
    expect(done.result!.fatal?.kind, "前提：以超时结束").toBe("timeout");
    renderApp(`/school/result/${done.session_id}`, svc);
    const conclusion = await screen.findByTestId("ds-conclusion");
    expect(within(conclusion).getByRole("heading", { name: "这次没通过" })).toBeTruthy();
    expect(conclusion.querySelector(".ds-conclusion__score.is-void")).not.toBeNull();
    expect(within(conclusion).getByText("这次不计分")).toBeTruthy();
    expect(within(conclusion).getByText("超时了，这一场不通过。")).toBeTruthy();
  });

  it("没碰红线的没通过：分数照常显示，不写“这次不计分”", async () => {
    const svc = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
    const r = await quiz(svc, "s1", false);
    renderApp(`/school/result/${r.session_id}`, svc);
    const conclusion = await screen.findByTestId("ds-conclusion");
    expect(conclusion.querySelector(".ds-conclusion__score.is-void")).toBeNull();
    expect(within(conclusion).queryByText("这次不计分")).toBeNull();
    expect(conclusion.textContent).toContain(`${r.result!.score} 分`);
  });
});

/* ---------------- 3. 科目页 ---------------- */

describe("科目页：上课、练习、正式考试三个入口分得清", () => {
  const entries = () => within(screen.getByRole("navigation", { name: "这一科的三个入口" })).getAllByRole("button");

  it("三个入口各写现在的状态，点了跳到那一段（焦点跟过去）；练习说明没有语病（巡检 P2-3）", async () => {
    renderApp("/school/subject/s1", createFixtureDrivingService({ stage: "enrolled", latency: 0 }));
    await screen.findByRole("heading", { name: "认识路上的规则" });
    const [lessons, practice, exam] = entries();
    const s1 = DEMO_CURRICULUM.subjects.find((s) => s.subject === "s1")!;
    expect(lessons.textContent).toBe(`上课${s1.duration}`);
    expect(practice.textContent).toBe("练习不计成绩");
    expect(exam.textContent).toBe("正式考试可以约首次考试");
    fireEvent.click(practice);
    expect(document.activeElement?.id).toBe("ds-practice");
    fireEvent.click(exam);
    expect(document.activeElement?.id).toBe("ds-exam");
    fireEvent.click(lessons);
    expect(document.activeElement?.id).toBe("ds-lessons");
    // 三段按上课 → 练习 → 正式考试排
    const [a, b, c] = ["ds-lessons", "ds-practice", "ds-exam"].map((id) => document.getElementById(id)!);
    expect(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(b.compareDocumentPosition(c) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText("练习时每道题答完马上讲解；正式考试交卷前不给任何提示。")).toBeTruthy();
    expect(document.body.textContent).not.toContain("练习时有答完");
  });

  it("补考：写这次是补考、还剩 1 次，没通过要等 7 天；开考确认也说这是最后一次机会", async () => {
    const svc = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
    await quiz(svc, "s1", false);
    renderApp("/school/subject/s1", svc);
    const card = await screen.findByTestId("ds-exam-card");
    expect(within(card).getByText("这次是补考 · 本轮还剩 1 次机会")).toBeTruthy();
    expect(within(card).getByText(/这是本轮最后一次机会：没通过的话要等 7 天才能再约/)).toBeTruthy();
    expect(entries()[2].textContent).toBe("正式考试可以约补考");
    fireEvent.click(within(card).getByRole("button", { name: "约补考" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/这是本轮最后一次机会：这次也没通过，要等 7 天/)).toBeTruthy();
    expect(within(dialog).getByText(/点“开始考试”才算一次考试/)).toBeTruthy();
  });

  it("冷却中：入口和考试卡都写本地几点后可以再约，没有约考按钮", async () => {
    const svc = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
    await quiz(svc, "s1", false);
    const second = await abandon(svc, "s1");
    const until = clock(second.result!.next!.cooldown_until!);
    renderApp("/school/subject/s1", svc);
    const card = await screen.findByTestId("ds-exam-card");
    expect(within(card).getByText(`${until} 后可以再约`)).toBeTruthy();
    expect(entries()[2].textContent).toBe(`正式考试${until} 后可约`);
    expect(within(card).queryByRole("button", { name: /^约/ })).toBeNull();
    expect(screen.getByRole("button", { name: "做一套练习题" })).toBeTruthy();
  });

  it("已通过：考试卡是通过的样子（分数、不用再考），入口写已通过", async () => {
    const svc = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
    const r = await quiz(svc, "s1", true);
    renderApp("/school/subject/s1", svc);
    const card = await screen.findByTestId("ds-exam-card");
    expect(card.className).toContain("is-passed");
    expect(within(card).getByText("已经考过了")).toBeTruthy();
    expect(card.textContent).toContain(`${r.result!.score} 分通过`);
    expect(card.textContent).toContain("不用再考");
    expect(within(card).queryByRole("button")).toBeNull();
    expect(entries()[2].textContent).toBe(`正式考试已通过 · ${r.result!.score} 分`);
    // 看成绩单的链接点按区不小于 44px（样式在 school.css 的总览 / 科目段）
    expect(within(card).getByRole("link", { name: /看成绩单/ }).className).toContain("ds-exam-card__last");
  });

  it("还没报名：练习和正式考试入口写报名后开放，页面上没有练习按钮", async () => {
    renderApp("/school/subject/s1", createFixtureDrivingService({ stage: "wish", latency: 0 }));
    await screen.findByRole("heading", { name: "认识路上的规则" });
    const [, practice, exam] = entries();
    expect(practice.textContent).toBe("练习报名后开放");
    expect(exam.textContent).toBe("正式考试报名后开放");
    expect(screen.queryByRole("button", { name: "做一套练习题" })).toBeNull();
    expect(screen.getByRole("link", { name: "去报名" }).getAttribute("href")).toBe("/school");
  });
});

/* ---------------- 5. 领证仪式（第二批） ---------------- */

describe("领证仪式：有仪式感、不拖沓，领完说清东西在哪", () => {
  it("打开只读、不会自己领证；有顶栏返回；按“开始领证”才领一次；领完是画出内容的纸质纪念卡，去处是卡包", async () => {
    const base = createFixtureDrivingService({ stage: "licensed", latency: 0 });
    let calls = 0;
    const svc: DrivingSchoolService = {
      ...base,
      ceremony: async (petId) => {
        calls += 1;
        return base.ceremony(petId);
      },
    };
    renderApp("/school/ceremony", svc);
    const start = await screen.findByRole("button", { name: "开始领证" });
    expect(calls, "打开页面不调用领证").toBe(0);
    expect(screen.getByRole("link", { name: "返回" }).getAttribute("href")).toBe("/school");
    expect(screen.getByText(/开启了“生成照片”会是一张写实合影/)).toBeTruthy();
    fireEvent.click(start);
    const card = await screen.findByTestId("ds-keepsake");
    expect(calls).toBe(1);
    // 纸质纪念卡：与收藏页同一设计（头像与龟教练并排、TA 的原话、日期、爪印章、读屏标签）
    expect(card.tagName).toBe("FIGURE");
    expect(card.getAttribute("aria-label")).toMatch(/^.+和龟教练·慢慢的领证纪念卡$/);
    expect(within(card).getByText("龟教练·慢慢")).toBeTruthy();
    expect(card.querySelector("blockquote")!.textContent).toMatch(/^“.+”$/);
    expect(card.querySelector(".ds-memento__stamp")).not.toBeNull();
    expect(card.textContent).toMatch(/\d{4}年\d{1,2}月\d{1,2}日 · 在爪爪驾校领证/);
    // 说清东西在哪；主要去处是卡包（/journey 已不在主导航里，不再指过去）
    expect(screen.getByRole("heading", { name: "领到的东西放在哪" })).toBeTruthy();
    expect(screen.getByText(/证件卡包（回忆 → 证件卡包）/)).toBeTruthy();
    expect(screen.getByText(/驾校借车券：在“明信片与小收藏”里/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "去明信片与小收藏看看" }).getAttribute("href")).toBe("/collection");
    const actions = screen.getByRole("navigation", { name: "领完证去哪" });
    expect(within(actions).getByRole("link", { name: "去卡包看驾照" }).getAttribute("href")).toBe("/life");
    expect(screen.queryByRole("link", { name: /旅途/ })).toBeNull();
    // 脚注：名字前后不多空格（巡检：“驾照绑定 团子，”）
    const foot = document.querySelector(".ds-footnote")!.textContent!;
    expect(foot).toMatch(/驾照绑定\S+，不能交易或转赠/);
    expect(foot).not.toMatch(/绑定 /);
    expect(calls).toBe(1);
  });

  it("有生成好的照片时：放照片并标明 AI 生成，不画纸质卡", async () => {
    const base = createFixtureDrivingService({ stage: "licensed", latency: 0 });
    const svc: DrivingSchoolService = {
      ...base,
      ceremony: async (petId) => {
        const r = await base.ceremony(petId);
        return { ...r, memento: r.memento && { ...r.memento, image_url: "data:image/gif;base64,R0lGODlhAQABAAAAACw=", image_status: "ready" } };
      },
    };
    renderApp("/school/ceremony", svc);
    fireEvent.click(await screen.findByRole("button", { name: "开始领证" }));
    const card = await screen.findByTestId("ds-keepsake");
    expect(card.querySelector("img")?.getAttribute("alt")).toMatch(/和你的领证合影$/);
    expect(within(card).getByText("AI 生成的领证纪念合影，不是真实照片")).toBeTruthy();
    expect(card.querySelector(".ds-memento__scene")).toBeNull();
  });
});

/* ---------------- 7. UI-ASSET-009 素材接入（第三批）：网址都从 SCHOOL_ART 取，加载失败退回原来的画法 ---------------- */

describe("驾校素材：横幅、龟教练、驾照底图，加载失败都退回原来的画法", () => {
  it("首页横幅：只放 780 宽的 webp（宽度描述符 + sizes，不用 1.98MB 的 PNG）、固定宽高、只作装饰；标题是页面文字；图片出错后只剩底色和标题", async () => {
    renderApp("/school", createFixtureDrivingService({ stage: "enrolled", latency: 0 }));
    const hero = await screen.findByTestId("ds-hero");
    const img = hero.querySelector("img")!;
    expect(img.getAttribute("src")).toBe(SCHOOL_ART.hero.src);
    expect(img.getAttribute("srcset")).toBe(`${SCHOOL_ART.hero.src} 780w`);
    expect(img.getAttribute("sizes")).toBe("(min-width: 560px) 528px, calc(100vw - 32px)");
    expect(img.getAttribute("srcset")).not.toContain(SCHOOL_ART.hero.large);
    expect([img.getAttribute("width"), img.getAttribute("height"), img.getAttribute("alt")]).toEqual(["780", "320", ""]);
    expect(within(hero).getByRole("heading", { level: 1, name: "爪爪驾校" })).toBeTruthy();
    // 横幅在“现在 / 下一步”卡前面，教练卡在后面
    expect(hero.compareDocumentPosition(screen.getByTestId("ds-now")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    fireEvent.error(img);
    expect(hero.querySelector("img")).toBeNull();
    expect(hero.className).toContain("ds-hero--plain");
    expect(within(hero).getByRole("heading", { level: 1, name: "爪爪驾校" })).toBeTruthy();
  });

  it("最近的练习与考试：碰了红线的练习（passed=false、分数 100）写“练习没达标，不计分”，不写 100 分；正式考试照常写分数和过没过", async () => {
    const svc = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
    const failed = await quiz(svc, "s1", false);
    const red = await drive(svc, "s3", null, ".red_light");
    expect([red.result!.passed, red.result!.score], "前提：碰红线的练习是 passed=false、分数 100").toEqual([false, 100]);
    renderApp("/school", svc);
    const rowOf = async (id: string) => (await screen.findAllByRole("link")).find((a) => a.getAttribute("href") === `/school/result/${id}`)!;
    const redRow = await waitFor(() => rowOf(red.session_id).then((row) => (row ? row : Promise.reject(new Error("还没出来")))));
    expect(redRow.textContent).toContain("练习没达标，不计分");
    expect(redRow.textContent).not.toMatch(/100 分/);
    expect((await rowOf(failed.session_id)).textContent).toContain(`${failed.result!.score} 分 · 未通过`);
  });

  it("驾校模块只在 journey.cards 登记驾照提示；朋友圈入口和小窝进度卡两处死登记已删", () => {
    expect((drivingModule.slots ?? []).map((s) => `${s.slot}:${s.id}`)).toEqual(["journey.cards:driving_school.hint"]);
  });

  it("首页龟教练头像用素材；出错退回原来画的乌龟", async () => {
    renderApp("/school", createFixtureDrivingService({ stage: "enrolled", latency: 0 }));
    await screen.findByTestId("ds-now");
    const face = document.querySelector(".ds-coach__face")!;
    const img = face.querySelector("img")!;
    expect([img.getAttribute("src"), img.getAttribute("alt")]).toEqual([SCHOOL_ART.coach.portrait, ""]);
    expect(face.querySelector(".ds-turtle-shell")).toBeNull();
    fireEvent.error(img);
    expect(face.querySelector("img")).toBeNull();
    expect(face.querySelector(".ds-turtle-shell")).not.toBeNull();
  });

  it("报名前：报名卡排在教练卡前面（加了横幅以后首屏要看得到报名按钮）", async () => {
    renderApp("/school", createFixtureDrivingService({ stage: "wish", latency: 0 }));
    const button = await screen.findByRole("button", { name: /报名爪爪驾校/ });
    const enroll = button.closest(".ds-enroll")!;
    expect(enroll.compareDocumentPosition(document.querySelector(".ds-coach")!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(enroll.querySelector(".ds-quote")).not.toBeNull();
  });

  it("首页驾照小卡用驾照正面底图；出错就是原来的纸色卡，字都还在", async () => {
    renderApp("/school", createFixtureDrivingService({ stage: "licensed", latency: 0 }));
    await screen.findByTestId("ds-now");
    const card = document.querySelector(".ds-license-mini")!;
    const img = card.querySelector("img")!;
    expect([img.getAttribute("src"), img.getAttribute("alt")]).toEqual([SCHOOL_ART.license.front, ""]);
    fireEvent.error(img);
    expect(card.querySelector("img")).toBeNull();
    expect(card.textContent).toMatch(/PetSoul · 爪爪驾驶证.*编号/);
  });

  it("科目页上课处：讲解姿势的龟教练，旁边写着教练名字；出错只剩文字", async () => {
    renderApp("/school/subject/s1", createFixtureDrivingService({ stage: "enrolled", latency: 0 }));
    await screen.findByRole("heading", { name: "认识路上的规则" });
    const tip = document.querySelector(".ds-lesson-coach")!;
    const img = tip.querySelector("img")!;
    expect([img.getAttribute("src"), img.getAttribute("alt")]).toEqual([SCHOOL_ART.coach.explain, ""]);
    expect(tip.textContent).toContain(DEMO_CURRICULUM.coach.name);
    fireEvent.error(img);
    expect(tip.querySelector("img")).toBeNull();
    expect(tip.textContent).toContain(DEMO_CURRICULUM.coach.name);
  });

  it.each([
    ["没通过", false, SCHOOL_ART.coach.explain, "没关系，把要练的地方再练几遍，下次会更稳。"],
    ["通过", true, SCHOOL_ART.coach.cheer, "稳稳当当，做得真好！"],
  ] as const)("成绩单%s：龟教练用对应的姿势，配一句鼓励；出错只剩文字", async (_label, correct, src, words) => {
    const svc = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
    const r = await quiz(svc, "s1", correct);
    renderApp(`/school/result/${r.session_id}`, svc);
    const coach = await screen.findByTestId("ds-result-coach");
    const img = coach.querySelector("img")!;
    expect([img.getAttribute("src"), img.getAttribute("alt")]).toEqual([src, ""]);
    expect(coach.textContent).toContain(words);
    fireEvent.error(img);
    expect(coach.querySelector("img")).toBeNull();
    expect(coach.textContent).toContain(words);
  });

  it("仪式页：确认页是举着空白卡的龟教练；驾照用正面底图；纪念卡里是教练头像，出错退回线稿", async () => {
    renderApp("/school/ceremony", createFixtureDrivingService({ stage: "licensed", latency: 0 }));
    const start = await screen.findByRole("button", { name: "开始领证" });
    const intro = document.querySelector(".ds-ceremony__coach")!;
    expect([intro.getAttribute("src"), intro.getAttribute("alt")]).toEqual([SCHOOL_ART.coach.ceremony, ""]);
    fireEvent.error(intro);
    expect(document.querySelector(".ds-ceremony__coach")).toBeNull();
    fireEvent.click(start);
    const card = await screen.findByTestId("ds-keepsake");
    const license = document.querySelector(".ds-license")!;
    const art = license.querySelector("img.ds-license__art")!;
    expect(art.getAttribute("src")).toBe(SCHOOL_ART.license.front);
    fireEvent.error(art);
    expect(license.querySelector("img.ds-license__art")).toBeNull();
    expect(license.textContent).toMatch(/持证.*编号/);
    const coach = card.querySelector(".ds-memento__coach")!;
    const portrait = coach.querySelector("img")!;
    expect([portrait.getAttribute("src"), portrait.getAttribute("alt")]).toEqual([SCHOOL_ART.coach.portrait, ""]);
    expect(coach.querySelector("svg.ds-memento__turtle")).toBeNull();
    fireEvent.error(portrait);
    expect(coach.querySelector("img")).toBeNull();
    expect(coach.querySelector("svg.ds-memento__turtle")).not.toBeNull();
  });
});

/* ---------------- 6. “通用”段里批准改的两条（第二批） ---------------- */

describe("school.css 通用段：看回放等链接的点按区、扣分数字的对比度", () => {
  const read = (p: string) => readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), "..", p), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  const css = read("src/features/driving_school/school.css");
  const tokens = read("src/shared/theme/tokens.css");
  const darkAt = tokens.indexOf("@media (prefers-color-scheme: dark)");
  const block = { light: tokens.slice(0, darkAt), dark: tokens.slice(darkAt) };
  const rule = (selector: string) => {
    const bodies = [...css.matchAll(/(^|\n)([^{}\n]+)\{([^}]*)\}/g)].filter((m) => m[2].trim() === selector).map((m) => m[3]);
    expect(bodies, `${selector} 应恰好一条`).toHaveLength(1);
    return bodies[0];
  };
  const hex = (scheme: "light" | "dark", name: string): string => {
    const find = (b: string) => b.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`))?.[1];
    const value = find(block[scheme]) ?? find(block.light);
    if (!value) throw new Error(`令牌 --${name} 没找到`);
    return value;
  };
  const rgb = (h: string) => [0, 2, 4].map((i) => parseInt(h.slice(1 + i, 3 + i), 16));
  const resolveColor = (value: string, scheme: "light" | "dark"): number[] => {
    const mix = value.match(/^color-mix\(in srgb, var\(--([\w-]+)\) (\d+)%, var\(--([\w-]+)\)\)$/);
    if (mix) {
      const [a, b, p] = [rgb(hex(scheme, mix[1])), rgb(hex(scheme, mix[3])), Number(mix[2]) / 100];
      return a.map((v, i) => Math.round(v * p + b[i] * (1 - p)));
    }
    const plain = value.match(/^var\(--([\w-]+)\)$/);
    if (!plain) throw new Error(`读不懂的颜色：${value}`);
    return rgb(hex(scheme, plain[1]));
  };
  const lum = (c: number[]) => c.map((v) => (v /= 255) <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4).reduce((s, v, i) => s + v * [0.2126, 0.7152, 0.0722][i], 0);
  const ratio = (a: number[], b: number[]) => {
    const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
    return (x + 0.05) / (y + 0.05);
  };

  it(".ds-link（回放标记、看成绩单等）点按区不小于 44px", () => {
    const px = Number(rule(".ds-link").match(/min-height:\s*(\d+)px/)?.[1]);
    expect(px).toBeGreaterThanOrEqual(44);
  });

  it.each(["light", "dark"] as const)(".ds-points 扣分数字在卡面上 %s 模式 ≥ 4.5:1", (scheme) => {
    const color = rule(".ds-points").match(/(?:^|;)\s*color:\s*([^;]+);/)![1].trim();
    expect(ratio(resolveColor(color, scheme), rgb(hex(scheme, "c-surface")))).toBeGreaterThanOrEqual(4.5);
  });

  // 第四批：驾照上宠物的头像在纸上，没有照片时的爪印占位用纸色底、纸墨爪印（与纪念卡同一做法），深色下不再是深绿圆块。
  it.each(["light", "dark"] as const)("驾照上宠物的无照片占位：%s 模式用纸色底、纸墨爪印（图形 ≥ 3:1），圈用纸影色", (scheme) => {
    const body = rule(".ds-license .ps-avatar.is-placeholder");
    const bg = body.match(/(?:^|;)\s*background:\s*([^;]+);/)![1].trim();
    const fg = body.match(/(?:^|;)\s*color:\s*([^;]+);/)![1].trim();
    expect([bg, fg]).toEqual(["var(--paper)", "var(--paper-secondary-ink)"]);
    expect(ratio(resolveColor(fg, scheme), resolveColor(bg, scheme))).toBeGreaterThanOrEqual(3);
    expect(rule(".ds-license .ps-avatar")).toMatch(/border-color:\s*var\(--paper/);
  });

  // 第三批：首页横幅上的标题是页面文字，底下衬主题底色渐变。按“图片是任意像素”的最坏情况推算，不依赖这张图长什么样。
  it.each(["light", "dark"] as const)("首页横幅：标题区里字对底 %s 模式最坏情况 ≥ 4.5:1（渐变衬底 × 任意图片像素）", (scheme) => {
    const textWidth = Number(rule(".ds-hero__text").match(/(?:^|;)\s*width:\s*(\d+)%/)![1]);
    const scrim = rule(".ds-hero::after").match(/background:\s*linear-gradient\(90deg,(.+)\);?\s*$/s)![1];
    const stops = [...scrim.matchAll(/(?:color-mix\(in srgb, var\(--c-bg\) (\d+)%, transparent\)|transparent) (\d+)%/g)].map((m) => ({ alpha: m[1] ? Number(m[1]) / 100 : 0, at: Number(m[2]) }));
    expect(stops.length, "渐变衬底的色标").toBeGreaterThanOrEqual(2);
    // 标题区（0 到 textWidth%）里衬底最薄的地方：色标之间线性过渡，最小值只会出现在色标或区间端点上
    const alphaAt = (x: number) => {
      const i = stops.findIndex((s) => s.at >= x);
      if (i <= 0) return i === 0 ? stops[0].alpha : stops[stops.length - 1].alpha;
      const [a, b] = [stops[i - 1], stops[i]];
      return a.alpha + ((b.alpha - a.alpha) * (x - a.at)) / (b.at - a.at);
    };
    const minAlpha = Math.min(...[0, textWidth, ...stops.map((s) => s.at).filter((x) => x <= textWidth)].map(alphaAt));
    const brightness = scheme === "dark" ? Number(css.match(/@media \(prefers-color-scheme: dark\) \{\s*\.ds-hero__img \{[^}]*brightness\(([\d.]+)\)/)![1]) : 1;
    const bg = rgb(hex(scheme, "c-bg"));
    const ink = rgb(hex(scheme, "c-ink"));
    const worst = Math.min(
      ...[0, 255 * brightness].map((pixel) => ratio(ink, bg.map((v) => v * minAlpha + pixel * (1 - minAlpha)))),
    );
    expect(worst).toBeGreaterThanOrEqual(4.5);
  });
});

/* ---------------- 4. 成绩单上切宠物（巡检第 4 批 P2） ---------------- */

const SIGNED_IN: SessionState = {
  authenticated: true,
  user: { user_id: "owner-1", display_name: "小林", username: "lin", auth_method: "web_password" },
  csrf_required: false,
  expires_at: null,
  onboarding: { step: "active", pet_id: "pet-a", home_id: "home-1", reception_session_id: null, reception_skipped: false, home_activated_at: null, pet_origin: "own_pet" },
};
const PETS = [
  { id: "pet-a", name: "奶茶" },
  { id: "pet-b", name: "豆豆" },
];
const HOUSEHOLD: HouseholdBrief = {
  household_id: "house-1",
  name: "海边的家",
  home_id: "home-1",
  role: "admin",
  home_activated: true,
  member_count: 1,
  pets: PETS.map((p) => ({ pet_id: p.id, name: p.name, species: "cat", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-20T00:00:00Z", added_by_you: true })),
};
const homeFor = (petId: string): HomeSnapshot => {
  const base = fixtureHomeSnapshot();
  return { ...base, data_origin: "live", presence: "at_home", journey: null, pet: { ...base.pet, pet_id: petId, name: PETS.find((p) => p.id === petId)!.name } } as HomeSnapshot;
};

describe("成绩单：切到另一只宠物", () => {
  it("不拿新宠物去读上一只的那一场（没有那次 404 请求），直接回驾校总览", async () => {
    mode.dataMode = "live";
    sessionStorage.setItem("petsoul:current-pet:owner-1", "pet-b");
    const school: Record<string, DrivingSchoolService> = {
      "pet-a": createFixtureDrivingService({ stage: "enrolled", latency: 0 }),
      "pet-b": createFixtureDrivingService({ stage: "enrolled", latency: 0 }),
    };
    const r = await quiz(school["pet-b"], "s1", false);
    const calls: { method: string; path: string; petId: string | null }[] = [];
    // 与后端同一个规矩：这一场只有它自己的宠物读得到，拿别的宠物去读回 404。
    const api: ApiClient = {
      base: "/api/v1/web",
      async request<T>(path: string, options: { method?: string; query?: Record<string, unknown> } = {}): Promise<T> {
        const method = options.method ?? "GET";
        const raw = options.query?.pet_id;
        const petId = raw === undefined || raw === null || raw === "" ? null : String(raw);
        calls.push({ method, path, petId });
        const reply = async (): Promise<unknown> => {
          if (path === "/session") return SIGNED_IN;
          if (path === "/households") return [HOUSEHOLD];
          if (path === "/home" && petId) return homeFor(petId);
          if (path === "/driving/curriculum") return school["pet-a"].curriculum();
          if (path === "/driving" && petId) return school[petId].status();
          if (path === "/driving/history") return [];
          if (path === `/driving/sessions/${r.session_id}`) {
            if (petId !== "pet-b") throw new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: "没有这场考试或练习。" });
            return school["pet-b"].session(r.session_id);
          }
          throw new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: `替身没有这条：${method} ${path}` });
        };
        return (await reply()) as T;
      },
    };
    const modules = loadFeatureModules();
    const router = createMemoryRouter(buildRoutes(modules), { initialEntries: [`/school/result/${r.session_id}`] });
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ServicesProvider services={buildServices(modules, { mode: "live", api })}>
          <RouterProvider router={router} />
        </ServicesProvider>
      </QueryClientProvider>,
    );
    await screen.findByTestId("ds-conclusion");
    const reads = () => calls.filter((c) => c.method === "GET" && c.path === `/driving/sessions/${r.session_id}`).map((c) => c.petId);
    expect(reads()).toEqual(["pet-b"]);
    fireEvent.click(screen.getByRole("button", { name: /^查看 奶茶/ }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/school"));
    // 回到的是奶茶自己的驾校总览（前提：切换真的生效了，页面按 pet-a 重新读过状态）
    await screen.findByTestId("ds-now");
    expect(calls.some((c) => c.path === "/driving" && c.petId === "pet-a")).toBe(true);
    expect(reads()).toEqual(["pet-b"]);
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("live：领完证“去卡包看驾照”直达那一张", () => {
  it("live 下链接是 /credentials/<驾照编号>（演示数据仍去卡包首页，见上面的仪式用例）", async () => {
    mode.dataMode = "live";
    sessionStorage.setItem("petsoul:current-pet:owner-1", "pet-b");
    const school = createFixtureDrivingService({ stage: "licensed", latency: 0 });
    const api: ApiClient = {
      base: "/api/v1/web",
      async request<T>(path: string, options: { method?: string; query?: Record<string, unknown> } = {}): Promise<T> {
        const petId = options.query?.pet_id ? String(options.query.pet_id) : null;
        const reply = async (): Promise<unknown> => {
          if (path === "/session") return SIGNED_IN;
          if (path === "/households") return [HOUSEHOLD];
          if (path === "/home" && petId) return homeFor(petId);
          if (path === "/driving/curriculum") return school.curriculum();
          if (path === "/driving" && petId === "pet-b") return school.status();
          if (path === "/driving/ceremony" && petId === "pet-b" && options.method === "POST") return school.ceremony();
          throw new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: `替身没有这条：${path}` });
        };
        return (await reply()) as T;
      },
    };
    const modules = loadFeatureModules();
    const router = createMemoryRouter(buildRoutes(modules), { initialEntries: ["/school/ceremony"] });
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ServicesProvider services={buildServices(modules, { mode: "live", api })}>
          <RouterProvider router={router} />
        </ServicesProvider>
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "开始领证" }));
    const actions = await screen.findByRole("navigation", { name: "领完证去哪" });
    const license = (await school.status()).license!;
    expect(license.credential_id, "前提：驾照有编号").toBeTruthy();
    expect(within(actions).getByRole("link", { name: "去卡包看驾照" }).getAttribute("href")).toBe(`/credentials/${license.credential_id}`);
  });
});
