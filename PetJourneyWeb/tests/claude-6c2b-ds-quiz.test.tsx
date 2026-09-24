/**
 * 爪爪驾校答题体验（claude-6c2b 答题分身，2026-09-24 第一批）：
 * - 触屏拖放：拖动中高亮松手会放进的那一格、松手放进去；没放进任何格就留在原处，也不被当成一次点选；
 * - 不用拖的替代：先点标志再点位置（走 click，读屏“双击激活”、键盘回车同样可用）；点放好的标志拿回来；
 *   手里选着别的标志时点放好的那格就换掉；Esc 取消；每一步在读屏播报区说清放到了哪里；
 * - 选项状态与讲解：单选圈区分选中；练习讲解后在选项 / 每一格上写明对错（不只靠颜色），讲解卡滚进视野；
 *   正式考试只标选中、不给对错；
 * - 320×568：题目区里的块不许被压扁（场景插画原来会被挤没）——jsdom 没有布局，只能读样式表核规则还在。
 * - 巡检 P2：题号点按区不小于 40px（320 宽不换行、不挤，这一行自己横向滑动）；讲解里 TA 的话用宠物名字署名（与成绩单一致）。
 * 第二批：换题后题目区回到顶部；正式考试保存后“已保存”那一行滚进视野；排先后可以点两项交换（↑ ↓ 保留）；
 *   标志与放标志格子的边框在浅色下图形对比 ≥ 3（按令牌实算）。
 * 用 fixture 服务（与服务端同一套判定）出卷，在真实的服务、家庭上下文里直接渲染 QuizRunner。
 * 变异自检：DS_QUIZ_CSS 可指向 school.css 的一份副本（只读），默认读 src/features/driving_school/school.css。
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import type { SchoolSession } from "@/shared/contracts";
import { createApiClient } from "@/shared/api/client";
import { loadFeatureModules } from "@/app/modules";
import { buildServices, ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { HouseholdProvider } from "@/shared/session/householdContext";
import { createFixtureDrivingService } from "@/features/driving_school/service";
import { dotColumns, QuizRunner } from "@/features/driving_school/quiz/QuizRunner";
import { Scene } from "@/features/driving_school/quiz/Scene";
import { DEMO_QUESTIONS } from "@/fixtures/driving";

const CSS_PATH = process.env.DS_QUIZ_CSS ?? resolve(dirname(fileURLToPath(import.meta.url)), "..", "src", "features", "driving_school", "school.css");

let pointAt: Element | null = null;
const scrolled = vi.fn();
const originalFromPoint = document.elementFromPoint;
const originalScrollIntoView = Element.prototype.scrollIntoView;

beforeEach(() => {
  pointAt = null;
  scrolled.mockClear();
  // jsdom 没有布局：手指下面是哪个元素由用例指定；scrollIntoView 记下调用。
  document.elementFromPoint = (() => pointAt) as typeof document.elementFromPoint;
  Element.prototype.scrollIntoView = function (this: Element, arg?: boolean | ScrollIntoViewOptions) {
    scrolled(this, arg);
  };
});
afterEach(() => {
  cleanup();
  document.elementFromPoint = originalFromPoint;
  Element.prototype.scrollIntoView = originalScrollIntoView;
});

async function openQuiz(subject: "s1" | "s4", mode: "practice" | "formal") {
  const svc = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
  const created = await svc.createSession({ subject, mode, item: null }, `t-${Math.random()}`);
  const session: SchoolSession = await svc.begin(created.session_id);
  const services: ServiceMap = { ...buildServices(loadFeatureModules(), { mode: "fixture", api: createApiClient("/api/v1/web") }), driving: svc };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  // 与考局页同样的外层：服务、查询、路由与家庭上下文（考局页由 WorldGate 提供家庭上下文）
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={services}>
        <MemoryRouter initialEntries={[`/school/session/${session.session_id}`]}>
          <HouseholdProvider userId={null}>
            <QuizRunner
              session={session}
              practice={mode === "practice"}
              exitLabel="结束"
              onExit={() => {}}
              onAnswer={(body) => svc.answer(session.session_id, body)}
              onSubmit={async () => {}}
            />
          </HouseholdProvider>
        </MemoryRouter>
      </ServicesProvider>
    </QueryClientProvider>,
  );
  await screen.findByRole("heading", { name: DEMO_QUESTIONS[subject][0].prompt });
  return { svc, session };
}

/** 科一演示卷第 3 题是拖放标志：两块标志、两个位置。 */
async function toMatch(mode: "practice" | "formal" = "practice") {
  await openQuiz("s1", mode);
  fireEvent.click(screen.getByRole("button", { name: "下一题" }));
  fireEvent.click(screen.getByRole("button", { name: "下一题" }));
  await screen.findByRole("heading", { name: DEMO_QUESTIONS.s1[2].prompt });
  const q = DEMO_QUESTIONS.s1[2];
  const chip = (label: string) => within(screen.getByRole("group", { name: /标志/ })).getByRole("button", { name: new RegExp(label.replace(/[“”]/g, ".")) });
  const target = (label: string) => screen.getAllByRole("listitem").find((li) => li.textContent?.includes(label))!;
  const live = () => document.querySelector(".ds-match [aria-live]")!.textContent ?? "";
  return { q, chip, target, live };
}

const STOP = "“停”字牌";
const WALK = "人行横道牌";
const JUNCTION = "没有红绿灯的路口前";
const ZEBRA = "斑马线旁边";

describe("拖放标志：触屏按住拖动", () => {
  it("拖动中高亮松手会放进的那一格、提示松手放到哪里；松手放进去，读屏说出放到了哪里", async () => {
    const { chip, target, live } = await toMatch();
    const walk = chip(WALK);
    fireEvent.pointerDown(walk, { pointerId: 1, pointerType: "touch", clientX: 60, clientY: 300 });
    pointAt = target(JUNCTION).querySelector(".ds-target__label");
    fireEvent.pointerMove(walk, { pointerId: 1, pointerType: "touch", clientX: 90, clientY: 420 });
    // 拖动中：那一格被标成“松手会放进这里”，另一格没有；提示和浮在指尖上的标志都在
    expect(target(JUNCTION).hasAttribute("data-over")).toBe(true);
    expect(target(ZEBRA).hasAttribute("data-over")).toBe(false);
    expect(within(target(JUNCTION)).getByRole("button").textContent).toBe("松手放这里");
    expect(screen.getByText(`松手放到“${JUNCTION}”`)).toBeTruthy();
    expect(document.querySelector(".ds-sign-ghost")?.textContent).toBe(WALK);
    // 手指移到空白处：高亮跟着撤掉
    pointAt = null;
    fireEvent.pointerMove(walk, { pointerId: 1, pointerType: "touch", clientX: 90, clientY: 700 });
    expect(target(JUNCTION).hasAttribute("data-over")).toBe(false);
    pointAt = target(ZEBRA);
    fireEvent.pointerMove(walk, { pointerId: 1, pointerType: "touch", clientX: 90, clientY: 520 });
    fireEvent.pointerUp(walk, { pointerId: 1, pointerType: "touch", clientX: 90, clientY: 520 });
    expect(document.querySelector(".ds-sign-ghost")).toBeNull();
    expect(within(target(ZEBRA)).getByRole("button").getAttribute("aria-label")).toBe(`${ZEBRA}：${WALK}。点一下拿回来`);
    expect(live()).toBe(`“${WALK}”放到了“${ZEBRA}”。`);
    // 拖完浏览器补发的 click 不算一次点选
    fireEvent.click(walk);
    expect(chip(WALK).getAttribute("aria-pressed")).toBe("false");
    expect(chip(WALK).getAttribute("aria-label")).toBe(`${WALK}（已放在“${ZEBRA}”）`);
  });

  it("松手时不在任何位置上：标志留在上面，读屏说明没有放进去", async () => {
    const { chip, target, live } = await toMatch();
    const stop = chip(STOP);
    fireEvent.pointerDown(stop, { pointerId: 2, pointerType: "touch", clientX: 200, clientY: 300 });
    fireEvent.pointerMove(stop, { pointerId: 2, pointerType: "touch", clientX: 230, clientY: 340 });
    fireEvent.pointerUp(stop, { pointerId: 2, pointerType: "touch", clientX: 230, clientY: 340 });
    expect(target(JUNCTION).textContent).not.toContain(STOP);
    expect(target(ZEBRA).textContent).not.toContain(STOP);
    expect(live()).toBe(`没有放进任何位置，${STOP}还在上面。`);
  });
});

describe("拖放标志：不用拖的替代（点选、键盘、读屏）", () => {
  it("先点标志再点位置；点放好的标志拿回来；选着别的标志点放好的那格就换掉；Esc 取消已选", async () => {
    const { chip, target, live } = await toMatch();
    // click 不带任何指针事件——读屏“双击激活”、键盘回车 / 空格就是这样到达按钮的
    fireEvent.click(chip(STOP));
    expect(chip(STOP).getAttribute("aria-pressed")).toBe("true");
    expect(live()).toBe(`已选${STOP}，再点它该放的位置。`);
    const slot = within(target(JUNCTION)).getByRole("button");
    expect(slot.getAttribute("aria-label")).toBe(`把${STOP}放到“${JUNCTION}”`);
    fireEvent.click(slot);
    expect(live()).toBe(`${STOP}放到了“${JUNCTION}”。`);
    expect(within(target(JUNCTION)).getByRole("button").getAttribute("aria-label")).toBe(`${JUNCTION}：${STOP}。点一下拿回来`);
    expect(chip(STOP).getAttribute("aria-pressed")).toBe("false");

    // 选着“人行横道牌”去点已经放了“停”字牌的那格：换掉，“停”字牌回到上面
    fireEvent.click(chip(WALK));
    const occupied = within(target(JUNCTION)).getByRole("button");
    expect(occupied.getAttribute("aria-label")).toBe(`把“${WALK}”放到“${JUNCTION}”，换下${STOP}`);
    fireEvent.click(occupied);
    expect(live()).toBe(`“${WALK}”放到了“${JUNCTION}”，换下了${STOP}。`);
    expect(chip(STOP).getAttribute("aria-label")).toBeNull();

    // 放错了：点放好的标志拿回来
    fireEvent.click(within(target(JUNCTION)).getByRole("button"));
    expect(live()).toBe(`已把“${WALK}”从“${JUNCTION}”拿回来。`);
    expect(within(target(JUNCTION)).getByRole("button").getAttribute("aria-label")).toBe(`${JUNCTION}：还空着，先选一个标志`);

    // 没选标志先点位置：不放，告诉怎么做
    fireEvent.click(within(target(ZEBRA)).getByRole("button"));
    expect(live()).toBe("先点一个标志，再点这里。");
    expect(target(ZEBRA).textContent).not.toContain(WALK);

    // Esc 取消已选
    fireEvent.click(chip(WALK));
    fireEvent.keyDown(chip(WALK), { key: "Escape" });
    expect(chip(WALK).getAttribute("aria-pressed")).toBe("false");
    expect(live()).toBe("已取消选择。");
  });

  it("点一下标志（没拖动）也是点选：指针按下抬起后由 click 选中", async () => {
    const { chip } = await toMatch();
    const walk = chip(WALK);
    fireEvent.pointerDown(walk, { pointerId: 3, pointerType: "touch", clientX: 60, clientY: 300 });
    fireEvent.pointerUp(walk, { pointerId: 3, pointerType: "touch", clientX: 61, clientY: 301 });
    fireEvent.click(walk);
    expect(chip(WALK).getAttribute("aria-pressed")).toBe("true");
  });
});

describe("选项状态与讲解", () => {
  it("练习：讲解后在选项上写明“正确答案 / 你选的”，每个选项都有单选圈，讲解卡滚进视野", async () => {
    await openQuiz("s1", "practice");
    const q = DEMO_QUESTIONS.s1[0];
    const radios = screen.getAllByRole("radio");
    expect(radios.map((r) => r.querySelector(".ds-option__mark"))).not.toContain(null);
    fireEvent.click(screen.getByRole("radio", { name: q.options[1].label }));
    await screen.findByText("这题再想想");
    const right = screen.getAllByRole("radio")[0];
    const mine = screen.getAllByRole("radio")[1];
    expect(right.getAttribute("data-verdict")).toBe("right");
    expect(within(right).getByText("正确答案")).toBeTruthy();
    expect(mine.getAttribute("aria-checked")).toBe("true");
    expect(within(mine).getByText("你选的")).toBeTruthy();
    expect(screen.getAllByRole("radio")[2].querySelector(".ds-answer-tag")).toBeNull();
    await waitFor(() => expect(scrolled).toHaveBeenCalled());
    expect((scrolled.mock.calls.at(-1)![0] as Element).classList.contains("ds-feedback")).toBe(true);
    // 答对时选项上写“你选对了”
    fireEvent.click(screen.getByRole("button", { name: "上一题" }));
    cleanup();
    await openQuiz("s4", "practice");
    const s4 = DEMO_QUESTIONS.s4[0];
    fireEvent.click(screen.getByRole("radio", { name: s4.options[1].label }));
    await screen.findByText("答对了");
    expect(within(screen.getAllByRole("radio")[1]).getByText("你选对了")).toBeTruthy();
  });

  it("正式考试：只标出选中（圈里实心），不给对错；写明已保存、交卷前可以改", async () => {
    await openQuiz("s1", "formal");
    const q = DEMO_QUESTIONS.s1[0];
    fireEvent.click(screen.getByRole("radio", { name: q.options[1].label }));
    await screen.findByText(/已保存。交卷前可以随时改/);
    expect(screen.getByRole("radio", { name: q.options[1].label }).getAttribute("aria-checked")).toBe("true");
    expect(document.querySelectorAll(".ds-answer-tag").length).toBe(0);
    expect(document.querySelectorAll("[data-verdict]").length).toBe(0);
    // 交卷前可以改
    fireEvent.click(screen.getByRole("radio", { name: q.options[0].label }));
    await waitFor(() => expect(screen.getByRole("radio", { name: q.options[0].label }).getAttribute("aria-checked")).toBe("true"));
    expect(screen.getByRole("radio", { name: q.options[1].label }).getAttribute("aria-checked")).toBe("false");
  });

  it("排先后与拖放：讲解后每一格标出对错；排序的上下移按钮收起，标志不能再动", async () => {
    await openQuiz("s1", "practice");
    fireEvent.click(screen.getByRole("button", { name: "下一题" }));
    await screen.findByRole("heading", { name: DEMO_QUESTIONS.s1[1].prompt });
    fireEvent.click(screen.getByRole("button", { name: "确定这个顺序" }));
    await screen.findByText("这题再想想");
    const rows = within(screen.getByRole("list", { name: "排列顺序" })).getAllByRole("listitem");
    expect(rows.map((r) => r.getAttribute("data-verdict"))).toEqual(["wrong", "wrong", "wrong", "wrong"]);
    expect(within(rows[0]).getByText("位置不对")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /往前移|往后移/ })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "下一题" }));
    await screen.findByRole("heading", { name: DEMO_QUESTIONS.s1[2].prompt });
    const q = DEMO_QUESTIONS.s1[2];
    // 按正确答案摆一格、错一格不行（两个标志只能各放一处），这里全摆对
    for (const [targetId, optionId] of Object.entries(q.answer.matches!)) {
      const optionLabel = q.options.find((o) => o.option_id === optionId)!.label;
      const targetLabel = q.targets.find((t) => t.target_id === targetId)!.label;
      fireEvent.click(within(screen.getByRole("group", { name: /标志/ })).getByRole("button", { name: new RegExp(optionLabel.replace(/[“”]/g, ".")) }));
      fireEvent.click(within(screen.getAllByRole("listitem").find((li) => li.textContent?.includes(targetLabel))!).getByRole("button"));
    }
    fireEvent.click(screen.getByRole("button", { name: "确定摆放" }));
    await screen.findByText("答对了");
    const targets = within(screen.getByRole("list", { name: "位置" })).getAllByRole("listitem");
    expect(targets.map((t) => t.getAttribute("data-verdict"))).toEqual(["right", "right"]);
    expect(within(targets[0]).getByText("放对了")).toBeTruthy();
    expect(within(targets[0]).getByRole("button")).toHaveProperty("disabled", true);
  });
});

describe("巡检 P2", () => {
  it("讲解里 TA 的话用宠物的名字署名（和成绩单一样），不再写“TA：”", async () => {
    await openQuiz("s1", "practice");
    fireEvent.click(screen.getByRole("radio", { name: DEMO_QUESTIONS.s1[0].options[0].label }));
    await screen.findByText("答对了");
    const line = document.querySelector(".ds-pet-line")!;
    await waitFor(() => expect(line.textContent).toBe(`团子：${DEMO_QUESTIONS.s1[0].pet_line}`));
  });
});

/** 去掉注释后按选择器取声明体（同一选择器多条时拼在一起）。 */
function cssRule(selector: string): string {
  const css = readFileSync(CSS_PATH, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "\\s*");
  const bodies = [...css.matchAll(new RegExp(`(?:^|[}\\s])${escaped}\\s*\\{([^}]*)\\}`, "g"))].map((m) => m[1]);
  expect(bodies.length, `${selector} 规则不见了`).toBeGreaterThan(0);
  return bodies.join(";");
}

describe("320×568 的版面（样式表；jsdom 没有布局，实际尺寸见浏览器截图）", () => {
  it("题目区的直接子元素 flex-shrink: 0（场景插画、讲解卡不会被挤没）", () => {
    expect(cssRule(".ds-question > *")).toMatch(/flex-shrink\s*:\s*0\b/);
  });

  it("题号点按区 40×40；按算好的列数排成网格（第五批：不再横向滑动）", () => {
    const dot = cssRule(".ds-dot");
    expect(dot).toMatch(/(?:^|;)\s*width\s*:\s*40px/);
    expect(dot).toMatch(/(?:^|;)\s*height\s*:\s*40px/);
    const strip = cssRule(".ds-dots");
    expect(strip).toMatch(/grid-template-columns\s*:\s*repeat\(\s*var\(--dot-cols[^)]*\)\s*,\s*40px\s*\)/);
    expect(strip).not.toMatch(/overflow-x\s*:\s*auto/);
  });
});

describe("第五批：题号放不下时折成几行，所有题号都在屏幕里", () => {
  // jsdom 把 clientWidth 定义在 Element.prototype 上：用例在 HTMLElement.prototype 上盖一层，结束时删掉这一层即还原
  afterEach(() => {
    delete (HTMLElement.prototype as unknown as Record<string, unknown>).clientWidth;
  });
  /** 题号那一行的宽度（jsdom 没有布局，用例指定）：320 宽时整行 320px，两边各留 12px 内边距 → 可用 296px。 */
  const stripWidth = (px: number) =>
    Object.defineProperty(HTMLElement.prototype, "clientWidth", {
      configurable: true,
      get(this: HTMLElement) {
        return this.classList.contains("ds-dots") ? px : 0;
      },
    });
  /** 一张 n 题的卷子（练习、没作答）：沿用演示题的内容，只换题号。 */
  function renderPaper(n: number) {
    const base = DEMO_QUESTIONS.s4[0];
    const questions = Array.from({ length: n }, (_, i) => ({ ...base, question_id: `paper.${i}`, answer: undefined, explanation: undefined, pet_line: undefined }));
    const session = {
      session_id: "paper",
      subject: "s4",
      title: "科目四：遇到情况怎么办",
      mode: "practice",
      item: null,
      attempt_kind: null,
      round_no: null,
      state: "running",
      pass_score: 90,
      created_at: "2026-09-24T00:00:00Z",
      begun_at: "2026-09-24T00:00:00Z",
      paused_at: null,
      settled_at: null,
      void_reason: null,
      quiz: { questions, answers: {}, feedback: {} },
      drive: null,
      result: null,
    } as unknown as SchoolSession;
    const services: ServiceMap = { ...buildServices(loadFeatureModules(), { mode: "fixture", api: createApiClient("/api/v1/web") }), driving: createFixtureDrivingService({ latency: 0 }) };
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ServicesProvider services={services}>
          <MemoryRouter>
            <HouseholdProvider userId={null}>
              <QuizRunner session={session} practice exitLabel="结束" onExit={() => {}} onAnswer={() => Promise.reject(new Error("不作答"))} onSubmit={async () => {}} />
            </HouseholdProvider>
          </MemoryRouter>
        </ServicesProvider>
      </QueryClientProvider>,
    );
    return screen.getByRole("navigation", { name: "题目进度" });
  }
  /** 按列数排出每个点的位置（居中、每格 40px），全部落在 [0, 视口宽] 里才算“都在屏幕里”。 */
  function allInside(nav: HTMLElement, viewport: number, pad = 12) {
    const cols = Number(nav.getAttribute("data-cols"));
    const dots = nav.querySelectorAll(".ds-dot").length;
    const left = pad + (viewport - 2 * pad - cols * 40) / 2;
    return Array.from({ length: dots }, (_, i) => left + (i % cols) * 40).every((x) => x >= 0 && x + 40 <= viewport);
  }

  it("科四 10 题、320 宽：5 + 5 两行，10 个点都在视口内，当前题（第 1 题）在第一行", () => {
    stripWidth(320);
    const nav = renderPaper(10);
    expect(nav.getAttribute("data-cols")).toBe("5");
    expect(nav.style.getPropertyValue("--dot-cols")).toBe("5");
    expect(allInside(nav, 320)).toBe(true);
    expect(nav.querySelectorAll(".ds-dot")[0].getAttribute("aria-current")).toBe("step");
  });

  it("390 宽：5 题一行放得下就一行；10 题放不下（10×40 > 366）也是 5 + 5；够宽的屏幕 10 题一行", () => {
    stripWidth(390);
    expect(renderPaper(5).getAttribute("data-cols")).toBe("5");
    cleanup();
    expect(renderPaper(10).getAttribute("data-cols")).toBe("5");
    cleanup();
    stripWidth(440);
    expect(renderPaper(10).getAttribute("data-cols")).toBe("10");
  });

  it("（顺带复核）犯困题夜景里的“哈——欠”：浅字＋深色描边垫在字下面，浅深两套主题字对描边都 ≥ 4.5", () => {
    const yawn = cssRule(".sc-yawn");
    const decl = (prop: string) => yawn.split(";").map((d) => d.trim()).find((d) => d.startsWith(`${prop}:`))?.slice(prop.length + 1).trim() ?? "";
    expect(decl("paint-order")).toBe("stroke");
    expect(parseFloat(decl("stroke-width"))).toBeGreaterThanOrEqual(2);
    const tokens = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), "..", "src", "shared", "theme", "tokens.css"), "utf8");
    const [light, dark] = tokens.split("@media (prefers-color-scheme: dark)");
    const hex = (block: string, expr: string) => {
      const name = expr.match(/^var\(--([\w-]+)\)$/)?.[1];
      const m = name ? block.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`)) : null;
      expect(m, `${expr} 不是能实算的令牌`).not.toBeNull();
      return [1, 3, 5].map((i) => parseInt(m![1].slice(i, i + 2), 16));
    };
    const lum = (c: number[]) => {
      const v = c.map((x) => x / 255).map((x) => (x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
      return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2];
    };
    const ratio = (a: number[], b: number[]) => {
      const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
      return (x + 0.05) / (y + 0.05);
    };
    for (const block of [light, light + dark]) {
      // 深色块只覆盖它写到的令牌：拼在浅色后面，同名取后出现的那个
      const pick = (expr: string) => {
        const name = expr.match(/^var\(--([\w-]+)\)$/)![1];
        const all = [...block.matchAll(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`, "g"))];
        expect(all.length, `令牌 --${name} 不见了`).toBeGreaterThan(0);
        return hex(`--${name}: ${all.at(-1)![1]}`, expr);
      };
      expect(ratio(pick(decl("fill")), pick(decl("stroke")))).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("列数的算法：放得下就一行，放不下就平均折行、每行不超过放得下的个数", () => {
    expect(dotColumns(10, 296)).toBe(5);
    expect(dotColumns(10, 366)).toBe(5);
    expect(dotColumns(10, 400)).toBe(10);
    expect(dotColumns(7, 296)).toBe(7);
    expect(dotColumns(8, 296)).toBe(4);
    expect(dotColumns(10, 150)).toBe(3);
    expect(dotColumns(10, 0)).toBe(10);
    for (const [n, w] of [[10, 296], [10, 366], [10, 150], [13, 296], [30, 296]]) expect(dotColumns(n, w) * 40).toBeLessThanOrEqual(w);
  });
});

/** 记下对某个元素 scrollTop 的每一次赋值（jsdom 不做布局，用自有属性接住）。 */
function watchScrollTop(el: Element) {
  const sets: number[] = [];
  let value = 0;
  Object.defineProperty(el, "scrollTop", {
    configurable: true,
    get: () => value,
    set: (v: number) => {
      value = v;
      sets.push(v);
    },
  });
  return sets;
}

describe("第二批：换题、已保存、排先后", () => {
  it("换题后题目区回到顶部（不停在上一题讲解卡的滚动位置）", async () => {
    await openQuiz("s1", "practice");
    const box = document.querySelector(".ds-question")!;
    const sets = watchScrollTop(box);
    fireEvent.click(screen.getByRole("radio", { name: DEMO_QUESTIONS.s1[0].options[1].label }));
    await screen.findByText("这题再想想");
    box.scrollTop = 193; // 讲解卡滚进视野后题目区停在这里（320×568 实测值）
    sets.length = 0;
    fireEvent.click(screen.getByRole("button", { name: "下一题" }));
    await screen.findByRole("heading", { name: DEMO_QUESTIONS.s1[1].prompt });
    expect(sets).toContain(0);
    expect(box.scrollTop).toBe(0);
  });

  it("正式考试：保存后把“已保存”那一行滚进视野（窄屏上它在选项下面）", async () => {
    await openQuiz("s1", "formal");
    scrolled.mockClear();
    fireEvent.click(screen.getByRole("radio", { name: DEMO_QUESTIONS.s1[0].options[0].label }));
    await screen.findByText(/已保存。交卷前可以随时改/);
    await waitFor(() => expect(scrolled).toHaveBeenCalled());
    const target = scrolled.mock.calls.at(-1)![0] as Element;
    expect(target.classList.contains("ds-saved")).toBe(true);
    expect(scrolled.mock.calls.at(-1)![1]).toMatchObject({ block: "nearest" });
  });

  it("排先后：点两项交换位置；再点同一项、按 Esc 都是取消；↑ ↓ 照样能挪；读屏说出现在是第几步", async () => {
    await openQuiz("s1", "practice");
    fireEvent.click(screen.getByRole("button", { name: "下一题" }));
    await screen.findByRole("heading", { name: DEMO_QUESTIONS.s1[1].prompt });
    const list = () => screen.getByRole("list", { name: "排列顺序" });
    const order = () => within(list()).getAllByRole("listitem").map((li) => li.querySelector(".ds-order__pick")!.textContent);
    const pickBtn = (text: string) => within(list()).getAllByRole("button").find((b) => b.classList.contains("ds-order__pick") && b.textContent === text)!;
    const live = () => document.querySelector(".ds-order-edit [aria-live]")!.textContent;
    expect(order()).toEqual(["调好后视镜", "绕车看一圈", "观察周围再起步", "坐好系上安全带"]);

    // 点“调好后视镜”，再点“坐好系上安全带”：两项交换
    fireEvent.click(pickBtn("调好后视镜"));
    expect(pickBtn("调好后视镜").getAttribute("aria-pressed")).toBe("true");
    expect(live()).toBe("已选“调好后视镜”（第 1 步），再点要和它交换的那一项。");
    expect(pickBtn("坐好系上安全带").getAttribute("aria-label")).toBe("第 4 步：坐好系上安全带。和“调好后视镜”交换");
    fireEvent.click(pickBtn("坐好系上安全带"));
    expect(order()).toEqual(["坐好系上安全带", "绕车看一圈", "观察周围再起步", "调好后视镜"]);
    expect(live()).toBe("“调好后视镜”和“坐好系上安全带”换了位置：“坐好系上安全带”现在是第 1 步，“调好后视镜”是第 4 步。");
    expect(pickBtn("调好后视镜").getAttribute("aria-pressed")).toBe("false");

    // 再点同一项：取消；Esc：取消
    fireEvent.click(pickBtn("绕车看一圈"));
    fireEvent.click(pickBtn("绕车看一圈"));
    expect(pickBtn("绕车看一圈").getAttribute("aria-pressed")).toBe("false");
    expect(live()).toBe("已取消选择。");
    fireEvent.click(pickBtn("绕车看一圈"));
    fireEvent.keyDown(pickBtn("绕车看一圈"), { key: "Escape" });
    expect(pickBtn("绕车看一圈").getAttribute("aria-pressed")).toBe("false");
    expect(order()).toEqual(["坐好系上安全带", "绕车看一圈", "观察周围再起步", "调好后视镜"]);

    // ↑ ↓ 保留
    fireEvent.click(screen.getByRole("button", { name: "把“绕车看一圈”往前移" }));
    expect(order()).toEqual(["绕车看一圈", "坐好系上安全带", "观察周围再起步", "调好后视镜"]);
    expect(live()).toBe("“绕车看一圈”移到了第 1 步。");
    // 按正确顺序排好后交卷：讲解说答对了（交换后的顺序真的交给了服务端）
    fireEvent.click(pickBtn("观察周围再起步"));
    fireEvent.click(pickBtn("调好后视镜"));
    expect(order()).toEqual(["绕车看一圈", "坐好系上安全带", "调好后视镜", "观察周围再起步"]);
    fireEvent.click(screen.getByRole("button", { name: "确定这个顺序" }));
    await screen.findByText("答对了");
    expect(pickBtn("绕车看一圈")).toHaveProperty("disabled", true);
  });
});

/** 按 tokens.css 实算 color-mix(in srgb, A p%, B) 与底色的对比度（浅色一套）。 */
function lightContrast(fgExpr: string, bgToken: string): number {
  const tokens = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), "..", "src", "shared", "theme", "tokens.css"), "utf8").split("@media")[0];
  const hex = (name: string) => {
    const m = tokens.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`));
    expect(m, `令牌 --${name} 不见了`).not.toBeNull();
    return [1, 3, 5].map((i) => parseInt(m![1].slice(i, i + 2), 16));
  };
  const color = (expr: string): number[] => {
    const mix = expr.match(/^color-mix\(in srgb,\s*var\(--([\w-]+)\)\s*([\d.]+)%,\s*var\(--([\w-]+)\)\)$/);
    if (mix) {
      const p = Number(mix[2]) / 100;
      const [a, b] = [hex(mix[1]), hex(mix[3])];
      return a.map((x, i) => x * p + b[i] * (1 - p));
    }
    const plain = expr.match(/^var\(--([\w-]+)\)$/);
    expect(plain, `看不懂的颜色：${expr}`).not.toBeNull();
    return hex(plain![1]);
  };
  const lum = (c: number[]) => {
    const v = c.map((x) => x / 255).map((x) => (x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
    return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2];
  };
  const [x, y] = [lum(color(fgExpr)), lum(hex(bgToken))].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

describe("第二批：标志与格子的边框，浅色下图形对比 ≥ 3（按令牌实算）", () => {
  const borderColor = (selector: string, prop = "border") => {
    const body = cssRule(selector);
    const decl = body.split(";").map((d) => d.trim()).find((d) => d.startsWith(`${prop}:`));
    expect(decl, `${selector} 没有 ${prop}`).toBeTruthy();
    const value = decl!.slice(prop.length + 1).trim();
    return prop === "border" ? value.replace(/^[\d.]+px\s+(solid|dashed)\s+/, "") : value;
  };
  it("标志：对页面底色、对自身浅琥珀底都 ≥ 3", () => {
    const c = borderColor(".ds-sign-chip");
    expect(lightContrast(c, "c-bg")).toBeGreaterThanOrEqual(3);
    expect(lightContrast(c, "c-sun-soft")).toBeGreaterThanOrEqual(3);
  });
  it("已放好的标志、放标志的格子与空位：虚线对页面底色、卡面都 ≥ 3", () => {
    const placed = borderColor(".ds-sign-chip[data-placed]", "border-color");
    const target = borderColor(".ds-target");
    const slot = borderColor(".ds-target__slot");
    for (const c of [placed, target, slot]) {
      expect(lightContrast(c, "c-bg")).toBeGreaterThanOrEqual(3);
      expect(lightContrast(c, "c-surface")).toBeGreaterThanOrEqual(3);
    }
  });
});

/**
 * 第三批：场景插画重画后，每道题要看懂的东西一样不少、含义不变。
 * 期望表按题库题干逐条写（PetJourneyBackend/app/web_driving/questions.py 里用到这个场景的题），不从 Scene.tsx 反推：
 * 场景里少了一样、换了颜色或换了标志，这里就红。
 */
const SCENE_PARTS: Record<string, string[]> = {
  stop_junction: ["road-junction", "stopline", "sign-stop", "car"], // “停”字牌、停止线
  stop_junction_night: ["road-junction", "stopline", "sign-stop", "car", "night"], // 晚上、没车、“停”字牌
  blue_arrow: ["road-straight", "sign-arrow_right", "car"], // 蓝色圆牌上向右的白色箭头（第四批：原来画成向上）
  lane_arrows: ["road-lanes", "lane-arrow-straight", "lane-arrow-right", "stopline", "car"], // 地上画着直行箭头的车道（第四批：原来是一块向左的圆牌）
  deer_sign: ["road-curve", "sign-deer", "resident-deer"], // 黄色三角牌里一只小鹿
  curve_sign: ["road-curve", "sign-curve", "car"], // 弯道警告
  children_sign: ["road-straight", "sign-children", "school"], // 学校附近
  zebra_penguin: ["road-zebra", "zebra", "stopline", "resident-penguin", "car"], // 企鹅在斑马线上
  zebra_waiting: ["road-zebra", "zebra", "stopline", "resident-rabbit", "car"], // 兔子准备过马路
  zebra_steps: ["road-zebra", "zebra", "stopline", "resident-penguin", "sign-crossing"],
  signal_flash: ["road-junction", "light", "flash-rays", "car"], // 黄灯一直在闪
  signal_green_walker: ["road-zebra", "zebra", "light", "resident-rabbit", "car"], // 绿灯但斑马线上还有居民
  signal_board: ["road-junction", "light"],
  ambulance_behind: ["road-straight", "vehicle-ambulance", "car"], // 救护车从后面开来
  firetruck_junction: ["road-junction", "vehicle-firetruck", "light"], // 绿灯、消防车
  ambulance_steps: ["road-straight", "vehicle-ambulance"],
  car_check: ["road-yard", "house-yard", "car"],
  seatbelt: ["cabin"],
  mirror_check: ["cabin"],
  no_parking: ["road-straight", "sign-no_parking", "yellow-grid", "car"], // 路边的黄色网格＋“禁止停车”牌（第四批补上网格）
  parking_board: ["road-parking", "bays", "sign-parking"],
  accessible_bay: ["road-parking", "bays", "sign-accessible"],
  school_gate: ["road-straight", "sign-children", "school", "resident-rabbit"], // 放学时的小学门口
  speed_sign: ["road-straight", "sign-speed", "car"], // 圆牌上写着 30
  narrow_street: ["road-narrow", "houses-narrow", "resident-puppy", "car"], // 小区窄路、有居民散步
  reverse_check: ["road-parking", "bays", "car"],
  reverse_puppy: ["road-parking", "bays", "resident-puppy", "car"], // 倒车时小狗跑过
  reverse_park: ["road-parking", "bays", "car"],
  sign_board: ["board"],
  drowsy_road: ["road-straight", "yawn", "night", "car"], // 困了、夜里
  night_road: ["road-curve", "night", "car"],
  rain_road: ["road-straight", "rain", "car"],
  fog_road: ["road-curve", "fog", "car"],
  phone_invite: ["cabin", "phone-invite"],
  phone_video: ["cabin", "phone-video"],
  market_reverse: ["road-parking", "bays", "resident-penguin", "car"],
  canteen_reverse: ["road-parking", "bays", "resident-rabbit", "car"],
  snack_drop: ["cabin", "drop-snack"],
  frame_drop: ["cabin", "drop-frame"],
};
/** 只在个别场景里出现的元素：出现在别的场景里也算变了意思（例如不该有雨的场景下起了雨）。 */
const EXCLUSIVE = ["night", "rain", "fog", "yawn", "school", "flash-rays", "vehicle-ambulance", "vehicle-firetruck", "phone-invite", "phone-video", "drop-snack", "drop-frame", "board", "yellow-grid", "lane-arrow-straight", "lane-arrow-right"];

function partsOf(scene: string): Element {
  render(<Scene scene={scene} />);
  const svg = document.querySelector(`svg[data-scene="${scene}"]`);
  expect(svg, `${scene} 没画出来`).not.toBeNull();
  return svg!;
}

describe("第三批：场景插画——每道题要看懂的东西一样不少", () => {
  for (const [scene, parts] of Object.entries(SCENE_PARTS)) {
    it(scene, () => {
      const svg = partsOf(scene);
      for (const part of parts) expect(svg.querySelectorAll(`[data-part="${part}"]`).length, `${scene} 缺 ${part}`).toBeGreaterThan(0);
      for (const part of EXCLUSIVE.filter((p) => !parts.includes(p))) expect(svg.querySelector(`[data-part="${part}"]`), `${scene} 多了 ${part}`).toBeNull();
    });
  }

  it("信号灯的颜色与题干一致：只有该亮的那一盏亮着", () => {
    const expectLit: Record<string, "red" | "green" | "flash"> = { signal_flash: "flash", signal_green_walker: "green", signal_board: "red", firetruck_junction: "green" };
    for (const [scene, lit] of Object.entries(expectLit)) {
      const light = partsOf(scene).querySelector('[data-part="light"]')!;
      expect(light.getAttribute("data-lit"), scene).toBe(lit);
      const on = [...light.querySelectorAll("circle.sc-lamp")].filter((c) => /sc-lamp--/.test(c.getAttribute("class") ?? "")).map((c) => c.getAttribute("class"));
      expect(on, scene).toEqual([{ red: "sc-lamp sc-lamp--red", green: "sc-lamp sc-lamp--green", flash: "sc-lamp sc-lamp--yellow sc-flash" }[lit]]);
      cleanup();
    }
  });

  it("标志上的字与题干一致（“停”、30、鹿、童、弯、P），斑马线 6 道、停车位 5 条线", () => {
    const text = (scene: string) => partsOf(scene).querySelector('[data-part^="sign-"]')!.textContent;
    expect(text("stop_junction")).toBe("停");
    cleanup();
    expect(text("speed_sign")).toBe("30");
    cleanup();
    expect(text("deer_sign")).toBe("鹿");
    cleanup();
    expect(text("children_sign")).toBe("童");
    cleanup();
    expect(text("curve_sign")).toBe("弯");
    cleanup();
    expect(text("parking_board")).toBe("P");
    cleanup();
    expect(partsOf("zebra_penguin").querySelectorAll('[data-part="zebra"] rect').length).toBe(6);
    cleanup();
    expect(partsOf("reverse_park").querySelectorAll('[data-part="bays"] path').length).toBe(5);
  });

  it("第四批 s1.dir.1：蓝色圆牌上的白色箭头朝右（题干“向右的白色箭头”）", () => {
    const d = partsOf("blue_arrow").querySelector('[data-part="sign-arrow_right"] .sc-sign-arrow')!.getAttribute("d")!;
    // 箭头头部是 “M a b L c d L e f”：尖端 (c, d) 在两翼右边、上下居中，才是朝右
    const head = d.match(/M\s*(-?[\d.]+)\s+(-?[\d.]+)\s*L\s*(-?[\d.]+)\s+(-?[\d.]+)\s*L\s*(-?[\d.]+)\s+(-?[\d.]+)\s*$/);
    expect(head, d).not.toBeNull();
    const [a, b, c, dd, e, f] = head!.slice(1).map(Number);
    expect(c).toBeGreaterThan(a);
    expect(c).toBeGreaterThan(e);
    expect(dd).toBeCloseTo((b + f) / 2, 5);
  });

  it("第四批 s1.dir.2：路面画车道箭头，小车就在画直行箭头的那条车道；不再有圆牌；两种箭头同样的白漆、不突出哪一条", () => {
    const svg = partsOf("lane_arrows");
    expect(svg.querySelector('[data-part^="sign-"]'), "向左的圆牌（意思是只准左转）和题目矛盾，应当去掉").toBeNull();
    const yOf = (d: string) => Number(d.match(/^M\s*-?[\d.]+\s+(-?[\d.]+)/)![1]);
    const straight = svg.querySelector('[data-part="lane-arrow-straight"]')!;
    const right = svg.querySelector('[data-part="lane-arrow-right"]')!;
    const car = svg.querySelector('[data-part="car"]')!.getAttribute("transform")!;
    const carY = Number(car.match(/translate\(\s*[\d.]+\s+([\d.]+)\s*\)/)![1]);
    expect(Math.abs(carY - yOf(straight.getAttribute("d")!))).toBeLessThan(6);
    expect(Math.abs(carY - yOf(right.getAttribute("d")!))).toBeGreaterThan(15);
    expect(straight.getAttribute("class")).toBe(right.getAttribute("class"));
  });

  it("第四批 s1.park.1：路边有黄色网格，就在“禁止停车”牌所在的这一侧路边", () => {
    const svg = partsOf("no_parking");
    const grid = svg.querySelector('[data-part="yellow-grid"]')!;
    expect(grid.querySelector(".sc-grid-box")).not.toBeNull();
    expect(grid.querySelector(".sc-grid-yellow")!.getAttribute("d")!.split("M").length - 1).toBeGreaterThan(10);
    const box = grid.querySelector(".sc-grid-box")!;
    const [x, y, w] = ["x", "y", "width"].map((k) => Number(box.getAttribute(k)));
    expect(x).toBeLessThan(262);
    expect(x + w).toBeGreaterThan(262); // 牌子立在网格旁（x=262）
    expect(y).toBeGreaterThanOrEqual(92); // 在路面上（直路 y 92–136）靠牌子这一侧
    expect(y).toBeLessThan(114);
  });

  it("未知的场景键退回一段普通道路和小车", () => {
    const svg = partsOf("no_such_scene");
    expect(svg.querySelector('[data-part="road-straight"]')).not.toBeNull();
    expect(svg.querySelector('[data-part="car"]')).not.toBeNull();
  });

  it("正式考试不透露答案：同一道题在练习、正式考试、讲解之后画面完全一样", async () => {
    const norm = (el: Element | null) => (el?.outerHTML ?? "").replace(/sc-(grain|sky|ws)-[\w-]+/g, "sc-$1-ID");
    await openQuiz("s1", "formal");
    const formal = norm(document.querySelector("svg.ds-scene"));
    cleanup();
    await openQuiz("s1", "practice");
    const practice = norm(document.querySelector("svg.ds-scene"));
    fireEvent.click(screen.getByRole("radio", { name: DEMO_QUESTIONS.s1[0].options[1].label }));
    await screen.findByText("这题再想想");
    const afterFeedback = norm(document.querySelector("svg.ds-scene"));
    expect(formal.length).toBeGreaterThan(500);
    expect(practice).toBe(formal);
    expect(afterFeedback).toBe(formal);
  });

  it("场景插画区段只有“黄灯在闪”一个动画，而且挂在 .sc-flash 上（减少动态效果区段会把它停住）", () => {
    const css = readFileSync(CSS_PATH, "utf8");
    const start = css.indexOf("/* 场景插画 */");
    const end = css.indexOf("/* ---------- 成绩单 ---------- */");
    expect(start).toBeGreaterThan(0);
    expect(end).toBeGreaterThan(start);
    const section = css.slice(start, end).replace(/\/\*[\s\S]*?\*\//g, "");
    const animated = [...section.matchAll(/([^{}]+)\{[^}]*\banimation\s*:/g)].map((m) => m[1].trim());
    expect(animated).toEqual([".sc-flash"]);
    expect(section).not.toMatch(/\btransition\s*:/);
    const reduce = css.slice(css.indexOf("@media (prefers-reduced-motion: reduce)"));
    expect(reduce).toMatch(/\.sc-flash[\s\S]*?animation:\s*none/);
  });
});
