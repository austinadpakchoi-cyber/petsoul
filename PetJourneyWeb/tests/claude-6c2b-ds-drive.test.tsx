/**
 * 爪爪驾校·驾驶体验（claude-6c2b 分身，2026-09-24 第一批）：
 * 1) 拇指区与误触：“转向方式”不放在操作区（改在“开始”卡、暂停卡）；挡位只放 D / R，转向灯另起一行；样式里热区不小于 44px、踏板间距不小于 12px。
 * 2) 压线 / 碰锥 / 到位 / 快超时：场地描边、分数变红、画面里贴“−5 压线”标记、剩余 30 秒变红并提示；深色下提示的字色对比度达标。
 * 3) 顶栏在 320 宽不截断：第几项跟在项目名后，副标题只留“科目 · 练习 / 首次考试 / 补考”；速度不写英文单位。
 * 4) 巡检 P1：科二连考一项做完、还没点“开始下一项”时，顶部得分不把这一项的扣分算两次（服务端回的 deducted 是整场累计）。
 * 5) 巡检 P2：练习的准备页按这一局实际的题数、通过线和项目说明，不照搬正式考试的规则。
 * 驾驶循环在 jsdom 里真跑：画布换成只记录调用的假 2D 上下文，requestAnimationFrame 换成手动推帧。
 * 变异自检用：环境变量 DS_DRIVE_CSS 可指向一份 school.css 副本（只读），默认读 src/features/driving_school/school.css。
 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import golden from "./fixtures/driving-golden.json";
import type { DriveItemProgress, InputChunk, InputResult, WebErrorEnvelope } from "@/shared/contracts";
import { createApiClient } from "@/shared/api/client";
import { ApiError, PLAYER_ERROR_TEXT } from "@/shared/api/errors";
import { loadFeatureModules } from "@/app/modules";
import { buildRoutes } from "@/app/router";
import { buildServices, ServicesProvider } from "@/shared/services/registry";
import type { DrivingSchoolService, ServiceMap } from "@/shared/services/types";
import { buildSlotRegistry, SlotProvider } from "@/shared/slots/Slot";
import { createFixtureDrivingService } from "@/features/driving_school/service";
import { type DriveBackend, DriveRunner, pauseCopy, type PauseWhy } from "@/features/driving_school/drive/DriveRunner";
import { ReplayViewer, type ReplaySeek } from "@/features/driving_school/drive/ReplayViewer";
import {
  BUILDING_DARK_ALPHA,
  BUSH_MAX_R,
  COACH_AVATAR,
  createStaticLayerCache,
  draw,
  drawCached,
  DRIVE_BUILDING_URLS,
  DRIVE_SPRITE_URLS,
  type DriveSprites,
  EMBLEM,
  fitCamera,
  FOLLOW_MARGIN,
  followCamera,
  type Frame,
  LABEL_CAR_GAP,
  loadDriveSprites,
  type Palette,
  PLATE_PAD,
  readPalette,
  ROOF_TILE_METERS,
  ROOF_WINDOW,
  SHADE,
  TILE_METERS,
} from "@/features/driving_school/drive/render";
import { SCHOOL_ART } from "@/features/driving_school/assets";
import { createHash } from "node:crypto";
import { Replay } from "@/features/driving_school/sim/replay";
import type { Course, InputEventT, Snapshot } from "@/features/driving_school/sim/types";
import { DEMO_CURRICULUM, demoCourse } from "@/fixtures/driving";

const HERE = dirname(fileURLToPath(import.meta.url));
const SCHOOL_CSS = process.env.DS_DRIVE_CSS ?? resolve(HERE, "..", "src", "features", "driving_school", "school.css");
const TOKENS_CSS = resolve(HERE, "..", "src", "shared", "theme", "tokens.css");
const cases = (golden as unknown as { cases: { name: string; events: InputEventT[]; ticks: number }[] }).cases;

/* ---------------- 驾驶循环的测试替身：假画布 + 手动推帧 ---------------- */

/**
 * ctx：哪块画布上的调用——main＝直接交给 draw 的画布，canvas＝页面或离屏 <canvas>（压暗素材就画在离屏画布上）；
 * st：这一笔落下时的画笔状态（第五批加，用来逐笔比对：填色、描边色、不透明度、线宽、字体、对齐、基线、合成方式）
 */
type Call = { fn: string; args: unknown[]; ctx?: string; st?: unknown[] };
const STATE_KEYS = ["fillStyle", "strokeStyle", "globalAlpha", "lineWidth", "font", "textAlign", "textBaseline", "globalCompositeOperation"] as const;
let calls: Call[] = [];
let frames: FrameRequestCallback[] = [];
let clock = 0;
const realGetContext = HTMLCanvasElement.prototype.getContext;
const realRaf = window.requestAnimationFrame;
const realCaf = window.cancelAnimationFrame;

function fakeContext(tag = "main"): CanvasRenderingContext2D {
  const state: Record<string | symbol, unknown> = {};
  return new Proxy(state, {
    get(target, prop) {
      if (prop === "measureText") return (text: string) => ({ width: String(text).length * 7 });
      // 平铺纹理：记下用哪张图建的，以及每次 setTransform 的矩阵（查“纹理钉在世界坐标上”）
      if (prop === "createPattern")
        return (img: unknown, repeat: string) => {
          calls.push({ fn: "createPattern", args: [img, repeat], ctx: tag });
          return { source: img, setTransform: (m: unknown) => calls.push({ fn: "pattern.setTransform", args: [img, m], ctx: tag }) };
        };
      if (prop in target) return target[prop];
      return (...args: unknown[]) => {
        calls.push({ fn: String(prop), args, ctx: tag, st: STATE_KEYS.map((k) => target[k]) });
      };
    },
    set(target, prop, value) {
      target[prop] = value;
      return true;
    },
  }) as unknown as CanvasRenderingContext2D;
}

beforeEach(() => {
  calls = [];
  frames = [];
  clock = performance.now();
  // 转向方式会记在本机：别让前一条用例切到“按钮”影响后面的用例
  window.localStorage.removeItem("petsoul.school.steerMode");
  HTMLCanvasElement.prototype.getContext = (() => fakeContext("canvas")) as unknown as HTMLCanvasElement["getContext"];
  window.requestAnimationFrame = (cb: FrameRequestCallback) => {
    frames.push(cb);
    return frames.length;
  };
  window.cancelAnimationFrame = () => undefined;
});

afterEach(() => {
  cleanup();
  HTMLCanvasElement.prototype.getContext = realGetContext;
  window.requestAnimationFrame = realRaf;
  window.cancelAnimationFrame = realCaf;
});

/** 推 n 帧（每帧略多于一个 tick）；until 为真就提前停。返回实际推了几帧。 */
function pump(n: number, until?: () => boolean): number {
  for (let i = 0; i < n; i++) {
    if (until?.()) return i;
    const due = frames;
    frames = [];
    // 单调递增且每帧至少一个 tick（循环挂载时取的 performance.now() 可能比 beforeEach 的晚）
    clock = Math.max(clock, performance.now()) + 1000 / 30 + 0.5;
    calls = [];
    act(() => {
      for (const cb of due) cb(clock);
    });
  }
  return n;
}

const texts = () => calls.filter((c) => c.fn === "fillText").map((c) => String(c.args[0]));
const key = (type: "keyDown" | "keyUp", k: string) => act(() => void fireEvent[type](window, { key: k }));

function item(course: Course, snapshot: Snapshot | null = null, status = "running"): DriveItemProgress {
  return {
    item: course.item,
    title: course.title,
    course: course as unknown as Record<string, unknown>,
    status,
    committed_tick: snapshot?.tick ?? 0,
    events: [],
    sim_events: snapshot?.events ?? [],
    snapshot: snapshot as unknown as Record<string, unknown> | null,
  };
}

function runner(props: Partial<Parameters<typeof DriveRunner>[0]> & { items: DriveItemProgress[] }) {
  return render(
    <DriveRunner
      title="科目二 · 首次考试"
      startIndex={0}
      practice={false}
      reasons={DEMO_CURRICULUM.reasons}
      petLines={DEMO_CURRICULUM.pet_lines.steady}
      hints={{}}
      backend={null}
      exitLabel="离开考场"
      onExit={() => undefined}
      onFinished={() => undefined}
      onVoid={() => undefined}
      {...props}
    />,
  );
}

const statValue = (label: string) => screen.getByLabelText(label).querySelector("strong")!.textContent;

/* ---------------- 1) 拇指区与误触 ---------------- */

describe("操作区：拇指区里只放开车用的键，热区不小于 44px", () => {
  it("“转向方式”不在操作区，而在“开始”卡里；切到按钮后，左右键并排、回正单独一个键", () => {
    runner({ items: [item(demoCourse("reverse_park", "a"))], practice: true });
    const controls = document.querySelector(".ds-exam__controls") as HTMLElement;
    expect(within(controls).queryByRole("group", { name: "转向方式" })).toBeNull();
    const overlay = document.querySelector(".ds-exam .ds-overlay") as HTMLElement;
    const toggle = within(overlay).getByRole("group", { name: "转向方式" });
    fireEvent.click(within(toggle).getByRole("button", { name: "按钮" }));
    const steer = within(controls).getByRole("group", { name: "转向" });
    const keys = within(steer).getAllByRole("button");
    expect(keys.map((b) => b.getAttribute("aria-label") ?? b.textContent)).toEqual(["向左转（按住持续转）", "向右转（按住持续转）", "回正"]);
    expect(keys[2].classList.contains("ds-key--center")).toBe(true);
  });

  it("挡位组只有 D、R 两个键；科三的转向灯另起一组，也是两个键", () => {
    runner({ items: [item(demoCourse("route", "a"))], practice: true });
    const controls = document.querySelector(".ds-exam__controls") as HTMLElement;
    const gears = within(controls).getByRole("group", { name: "挡位" });
    expect(within(gears).getAllByRole("button").map((b) => b.textContent?.trim())).toEqual(["D", "R"]);
    const blinkers = within(controls).getByRole("group", { name: "转向灯" });
    expect(within(blinkers).getAllByRole("button").map((b) => b.getAttribute("aria-label"))).toEqual(["左转向灯", "右转向灯"]);
    expect(gears.contains(blinkers)).toBe(false);
  });

  it("暂停卡里也能换转向方式（离开再回来时标题是“欢迎回来”，第二批改的说法）", () => {
    const course = demoCourse("reverse_park", "a");
    const replay = new Replay(course);
    replay.apply([], 5);
    runner({ items: [item(course, replay.snapshot())], practice: true });
    const overlay = document.querySelector(".ds-exam .ds-overlay") as HTMLElement;
    expect(within(overlay).getByText("欢迎回来")).toBeTruthy();
    expect(within(overlay).getByRole("group", { name: "转向方式" })).toBeTruthy();
  });
});

/* ---------------- 样式：热区、间距、对比度（只读 CSS） ---------------- */

type Rule = { selector: string; context: string; body: string };

function parseRules(file: string): Rule[] {
  const src = readFileSync(file, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  const rules: Rule[] = [];
  const stack: string[] = [];
  let buf = "";
  for (const ch of src) {
    if (ch === "{") {
      stack.push(buf.trim().replace(/\s+/g, " "));
      buf = "";
    } else if (ch === "}") {
      const prelude = stack.pop() ?? "";
      if (!prelude.startsWith("@")) rules.push({ selector: prelude, context: stack.filter((s) => s.startsWith("@")).join(" "), body: buf.trim() });
      buf = "";
    } else buf += ch;
  }
  return rules;
}

function decl(selector: string, prop: string, context = ""): string {
  const found = parseRules(SCHOOL_CSS).filter((r) => r.selector === selector && r.context === context);
  expect(found.length, `school.css 里 ${context} ${selector} 应恰好一条`).toBe(1);
  const part = found[0].body.split(";").find((p) => p.split(":")[0].trim() === prop);
  expect(part, `${selector} 的 ${prop}`).toBeDefined();
  return part!.slice(part!.indexOf(":") + 1).trim();
}

const DARK = "@media (prefers-color-scheme: dark)";
function tokens(scheme: "light" | "dark"): Map<string, string> {
  const table = new Map<string, string>();
  for (const context of scheme === "dark" ? ["", DARK] : [""]) {
    const root = parseRules(TOKENS_CSS).find((r) => r.selector === ":root" && r.context === context)!;
    for (const part of root.body.split(";")) {
      const at = part.indexOf(":");
      if (at > 0) table.set(part.slice(0, at).trim(), part.slice(at + 1).trim());
    }
  }
  return table;
}

function px(value: string): number {
  const t = tokens("light");
  const v = value.trim();
  const ref = /^var\((--[\w-]+)\)$/.exec(v);
  if (ref) return px(t.get(ref[1])!);
  const m = /^(\d+(?:\.\d+)?)px$/.exec(v);
  if (!m) throw new Error(`不认识的长度：${value}`);
  return Number(m[1]);
}

function rgb(value: string, table: Map<string, string>): number[] {
  const ref = /^var\((--[\w-]+)\)$/.exec(value.trim());
  if (ref) return rgb(table.get(ref[1])!, table);
  const hex = /^#([0-9a-f]{6})$/i.exec(value.trim());
  if (!hex) throw new Error(`不认识的颜色：${value}`);
  return [0, 2, 4].map((i) => parseInt(hex[1].slice(i, i + 2), 16));
}

function ratio(fg: string, bg: string, scheme: "light" | "dark"): number {
  const table = tokens(scheme);
  const lum = (c: number[]) => {
    const [r, g, b] = c.map((x) => {
      const s = x / 255;
      return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const [a, b] = [lum(rgb(fg, table)), lum(rgb(bg, table))].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}

describe("样式：操作区热区与间距", () => {
  it("挡位 / 转向灯、方向键、回正、顶栏暂停键、转向方式都不小于 44px", () => {
    expect(px(decl(".ds-gear", "min-height"))).toBeGreaterThanOrEqual(44);
    expect(px(decl(".ds-gear", "min-width"))).toBeGreaterThanOrEqual(44);
    expect(px(decl(".ds-key", "min-height"))).toBeGreaterThanOrEqual(44);
    expect(px(decl(".ds-key", "min-width"))).toBeGreaterThanOrEqual(44);
    expect(px(decl(".ds-wheel__center", "min-height"))).toBeGreaterThanOrEqual(44);
    expect(px(decl(".ds-exam > .ds-exam__top .ps-btn", "min-height"))).toBeGreaterThanOrEqual(44);
    expect(px(decl(".ds-exam > .ds-exam__top .ps-btn", "min-width"))).toBeGreaterThanOrEqual(44);
    expect(px(decl(".ds-exam .ds-segmented button", "min-height"))).toBeGreaterThanOrEqual(44);
  });

  it("刹车与油门至少隔 12px，左右两列至少隔 16px，列内热区至少隔 10px；挡位行是两列", () => {
    expect(px(decl(".ds-pedals", "gap"))).toBeGreaterThanOrEqual(12);
    expect(px(decl(".ds-controls", "gap"))).toBeGreaterThanOrEqual(16);
    expect(px(decl(".ds-controls__left, .ds-controls__right", "gap"))).toBeGreaterThanOrEqual(10);
    expect(decl(".ds-gears", "grid-template-columns")).toBe("minmax(0, 1fr) minmax(0, 1fr)");
  });

  it("320×568 的高度预算：挡位 + 转向灯 + 踏板最小高度 + 两道间距 ≤ 操作区内容高（216 − 上下内边距）", () => {
    const need = 44 + 44 + px(decl(".ds-pedals", "min-height")) + 2 * px(decl(".ds-controls__left, .ds-controls__right", "gap"));
    const box = px(decl(".ds-exam__controls", "min-height"));
    expect(need).toBeLessThanOrEqual(box - 8 - 12);
  });

  for (const scheme of ["light", "dark"] as const) {
    it(`${scheme}：扣分 / 到位提示的字与底、剩余时间与分数的警示红，对比度 ≥ 4.5`, () => {
      const dark = scheme === "dark";
      const bad = dark ? decl('.ds-toast--bad, .ds-toast--good, .ds-hold, .ds-check[aria-pressed="true"]', "color", DARK) : decl(".ds-toast--bad", "color");
      expect(ratio(bad, decl(".ds-toast--bad", "background"), scheme)).toBeGreaterThanOrEqual(4.5);
      const good = dark ? bad : decl(".ds-toast--good", "color");
      expect(ratio(good, decl(".ds-toast--good", "background"), scheme)).toBeGreaterThanOrEqual(4.5);
      expect(ratio(dark ? bad : decl(".ds-hold", "color"), decl(".ds-hold", "background"), scheme)).toBeGreaterThanOrEqual(4.5);
      expect(ratio(decl(".ds-exam__stat[data-low] strong, .ds-exam__stat[data-hit] strong", "color"), "var(--c-surface)", scheme)).toBeGreaterThanOrEqual(4.5);
    });
  }
});

/* ---------------- 2) 压线 / 碰锥 / 到位 / 快超时 ---------------- */

describe("静音也看得懂：压线、碰锥、到位、快超时", () => {
  it("压线：场地描红、分数变红、画面里贴“−5 压线”；碰锥再贴“−10 碰到训练锥”；标记 1.5 秒后撤掉", () => {
    runner({ items: [item(demoCourse("reverse_park", "a"))], practice: true, title: "科目二 · 练习" });
    fireEvent.click(screen.getByRole("button", { name: "开始" }));
    // 离线复算搜出来的操作：方向 4 档、按住油门，约第 119 个 tick 压线、第 145 个 tick 碰锥
    for (let i = 0; i < 4; i++) key("keyDown", "ArrowLeft");
    key("keyDown", "ArrowUp");
    pump(400, () => !!screen.queryByText("压线 −5"));
    expect(screen.getByText("压线 −5")).toBeTruthy();
    pump(1);
    const field = document.querySelector(".ds-exam__field") as HTMLElement;
    expect(field.dataset.flash).toBe("bad");
    expect(screen.getByLabelText("练习得分（不计成绩）").hasAttribute("data-hit")).toBe(true);
    expect(texts()).toContain("−5 压线");
    pump(200, () => !!screen.queryByText("碰到训练锥 −10"));
    pump(1);
    expect(texts()).toContain("−10 碰到训练锥");
    key("keyUp", "ArrowUp");
    key("keyDown", " ");
    pump(60);
    expect(texts()).not.toContain("−5 压线");
    expect(texts()).not.toContain("−10 碰到训练锥");
  });

  it("到位：提示写明“到位！”，场地描绿", async () => {
    const course = demoCourse("reverse_park", "a");
    const script = cases.find((c) => c.name === "reverse_park.a")!;
    const whole = new Replay(course);
    whole.apply(script.events, script.ticks);
    const doneAt = whole.events.find((e) => e.k === "done")!.t;
    const near = new Replay(course);
    near.apply(script.events, doneAt - 3);
    runner({ items: [item(course, near.snapshot())], practice: true });
    fireEvent.click(screen.getByRole("button", { name: "继续" }));
    pump(30, () => !!screen.queryByText(/^到位！/));
    expect(screen.getByText(`到位！${DEMO_CURRICULUM.pet_lines.steady.park}`)).toBeTruthy();
    expect((document.querySelector(".ds-exam__field") as HTMLElement).dataset.flash).toBe("good");
  });

  it("剩余 30 秒起：剩余时间标成警示，并提示一次“还剩 30 秒”", () => {
    const course = demoCourse("reverse_park", "a");
    const replay = new Replay(course);
    replay.apply([], course.time_limit_ticks - 30 * 30 - 3);
    runner({ items: [item(course, replay.snapshot())] });
    expect(screen.getByLabelText("剩余时间").hasAttribute("data-low")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "继续" }));
    pump(8);
    expect(screen.getByLabelText("剩余时间").hasAttribute("data-low")).toBe(true);
    expect(screen.getAllByText("还剩 30 秒")).toHaveLength(1);
  });
});

/* ---------------- 3) 顶栏 ---------------- */

describe("顶栏在 320 宽不截断", () => {
  it("第几项跟在项目名后，副标题只留科目与场次；速度写“公里/时”", () => {
    const items = [item(demoCourse("reverse_park", "a")), item(demoCourse("side_park", "a"), null, "pending"), item(demoCourse("curve", "a"), null, "pending")];
    runner({ items });
    const title = document.querySelector(".ds-exam__title") as HTMLElement;
    expect(title.querySelector("strong")!.textContent).toBe("倒车入库1/3");
    expect(title.querySelector(":scope > span")!.textContent).toBe("科目二 · 首次考试");
    const hud = document.querySelector(".ds-field__hud") as HTMLElement;
    expect(hud.textContent).toContain("0 公里/时");
    expect(hud.textContent).not.toMatch(/km\/h/i);
  });
});

/* ---------------- 4) 巡检 P1：连考时分数不重复扣 ---------------- */

describe("巡检 P1：科二连考，一项做完、等“开始下一项”时顶部得分不重复扣", () => {
  it("这一项扣 5 分、服务端回整场累计 5 分：顶部显示 95，不是 90；点开始下一项后仍是 95", async () => {
    const course = demoCourse("reverse_park", "a");
    const script = cases.find((c) => c.name === "reverse_park.a")!;
    const whole = new Replay(course);
    whole.apply(script.events, script.ticks);
    const doneAt = whole.events.find((e) => e.k === "done")!.t;
    const near = new Replay(course);
    near.apply(script.events, doneAt - 3);
    const snap = near.snapshot();
    // 这一项先前压过一次线（−5）：服务端快照里带着这条判定
    snap.events = [...snap.events, { t: 10, k: "line", ref: "road_far", p: 5, f: 0 }];
    const uploads: InputChunk[] = [];
    const backend: DriveBackend = {
      upload: async (chunk: InputChunk): Promise<InputResult> => {
        uploads.push(chunk);
        const done = chunk.upto_tick > doneAt;
        return {
          session_id: "s",
          session_state: "running",
          item_index: chunk.item_index,
          current_item: done ? 1 : 0,
          item_status: done ? "done" : "running",
          committed_tick: chunk.upto_tick,
          new_events: [],
          deducted: 5,
          snapshot: null,
          result: null,
        };
      },
      pause: async () => ({}),
      reload: async () => {
        throw new Error("这条用例不该重新同步");
      },
    };
    const items = [item(course, snap), item(demoCourse("side_park", "a"), null, "pending")];
    runner({ items, backend });
    expect(statValue("当前得分")).toBe("95");
    fireEvent.click(screen.getByRole("button", { name: "继续" }));
    pump(30, () => uploads.some((c) => c.upto_tick > doneAt));
    await waitFor(() => expect(screen.getByText("倒车入库完成！")).toBeTruthy());
    expect(statValue("当前得分")).toBe("95");
    fireEvent.click(screen.getByRole("button", { name: "开始下一项" }));
    expect(statValue("当前得分")).toBe("95");
  });
});

/* ---------------- 5) 巡检 P2：练习的准备页按这一局实际内容说明 ---------------- */

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
}

describe("巡检 P2：练习的准备页不照搬正式考试规则", () => {
  it("科一练习：按实际题数说题数与达标线（与服务端判分同一算法）", async () => {
    const svc = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
    const s = await svc.createSession({ subject: "s1", mode: "practice", item: null }, "k:p1");
    const n = s.quiz!.questions.length;
    const max = n * 10;
    renderApp(`/school/session/${s.session_id}`, svc);
    await screen.findByRole("button", { name: "开始练习" });
    expect(screen.getByText(`这一局练习 ${n} 道题，每题 10 分，达到 ${Math.floor((s.pass_score * max) / 100)} 分（满分 ${max}）算练习达标；每答一题马上讲解，不计成绩。`)).toBeTruthy();
    expect(screen.queryByText(/10 道题/)).toBeNull();
  });

  it("科二单项练习：只说这一项，不写“三项连考 / 综合 80 分通过”", async () => {
    const svc = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
    const s = await svc.createSession({ subject: "s2", mode: "practice", item: "reverse_park" }, "k:p2");
    renderApp(`/school/session/${s.session_id}`, svc);
    await screen.findByRole("button", { name: "开始练习" });
    expect(screen.getByText(`这一局只练「倒车入库」：完成这一项、达到 ${s.pass_score} 分算练习达标，不计成绩。`)).toBeTruthy();
    expect(screen.queryByText(/一场连考|三项都完成/)).toBeNull();
    expect(screen.getByText("红线（自动制动，这一局练习到此结束）")).toBeTruthy();
  });

  it("正式考试照旧写正式规则（对照）", async () => {
    const svc = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
    const s = await svc.createSession({ subject: "s1", mode: "formal", item: null }, "k:f1");
    renderApp(`/school/session/${s.session_id}`, svc);
    await screen.findByRole("button", { name: "开始考试" });
    const info = DEMO_CURRICULUM.subjects.find((x) => x.subject === "s1")!;
    expect(screen.getByText(`${info.format}。${info.pass_rule}。`)).toBeTruthy();
  });
});

/* ================= 第二批（2026-09-24）================= */

describe("第二批·深色对比度：方向盘图形 ≥ 3，踏板、选中的挡位 / 转向灯、勾好的检查、按住的转向键、顶栏小字 ≥ 4.5", () => {
  for (const scheme of ["light", "dark"] as const) {
    it(`${scheme}`, () => {
      const dark = scheme === "dark";
      const surface = "var(--c-surface)";
      const wheel = dark ? decl(".ds-wheel__rim, .ds-wheel__spoke", "stroke", DARK) : decl(".ds-wheel__rim", "stroke");
      expect(ratio(wheel, surface, scheme), "方向盘").toBeGreaterThanOrEqual(3);
      const pedalInk = dark ? decl(".ds-pedal", "color", DARK) : decl(".ds-pedal", "color");
      const brakeBg = dark ? decl(".ds-pedal--brake", "background", DARK) : decl(".ds-pedal--brake", "background");
      expect(ratio(pedalInk, brakeBg, scheme), "刹车").toBeGreaterThanOrEqual(4.5);
      expect(ratio(pedalInk, decl(".ds-pedal--gas", "background"), scheme), "油门").toBeGreaterThanOrEqual(4.5);
      const gearInk = decl('.ds-gear[aria-pressed="true"]', "color");
      expect(ratio(gearInk, decl('.ds-gear[aria-pressed="true"]', "background"), scheme), "选中的挡位").toBeGreaterThanOrEqual(4.5);
      expect(ratio(gearInk, decl('.ds-gear--blink[aria-pressed="true"]', "background"), scheme), "打开的转向灯").toBeGreaterThanOrEqual(4.5);
      const checkInk = dark ? decl('.ds-toast--bad, .ds-toast--good, .ds-hold, .ds-check[aria-pressed="true"]', "color", DARK) : decl('.ds-check[aria-pressed="true"]', "color");
      expect(ratio(checkInk, decl('.ds-check[aria-pressed="true"]', "background"), scheme), "勾好的检查").toBeGreaterThanOrEqual(4.5);
      expect(ratio(decl(".ds-key[data-held]", "color"), decl(".ds-key[data-held]", "background"), scheme), "按住的转向键").toBeGreaterThanOrEqual(4.5);
      expect(ratio(decl(".ds-exam__stat span", "color"), surface, scheme), "顶栏小字").toBeGreaterThanOrEqual(4.5);
    });
  }

  it("“通用”里的分段按钮（转向方式、回放选项目）不小于 44px（主窗口批准只改这一条）", () => {
    expect(px(decl(".ds-segmented button", "min-height"))).toBeGreaterThanOrEqual(44);
  });

  it("视频邀请卡不用 transform 居中（入场动画 ds-pop 的 from 帧会盖掉它，卡片会斜着滑进来）", () => {
    const rule = parseRules(SCHOOL_CSS).find((r) => r.selector === ".ds-invite" && r.context === "")!;
    expect(rule.body).not.toMatch(/(?:^|;)\s*transform\s*:/);
    expect(decl(".ds-invite", "left")).toBe("0");
    expect(decl(".ds-invite", "right")).toBe("0");
    expect(decl(".ds-invite", "margin")).toBe("0 auto");
  });
});

describe("第二批·暂停卡：一个标题说清为什么停，一句话说清什么都不会丢", () => {
  it("每种原因的标题各不相同，不出现“服务器 / 同步”这类词；练习不提抽题", () => {
    const whys: PauseWhy[] = ["manual", "hidden", "offline", "back", "resume", "resynced", "lost"];
    const titles = whys.map((w) => pauseCopy(w, false).title);
    expect(new Set(titles).size).toBe(whys.length);
    for (const w of whys) {
      for (const practice of [true, false]) {
        const { title, line } = pauseCopy(w, practice);
        expect(`${title}${line}`).not.toMatch(/服务器|同步|复核/);
      }
    }
    expect(pauseCopy("manual", true).line).not.toMatch(/抽题/);
    expect(pauseCopy("manual", false).line).toMatch(/不会重新抽题/);
  });

  it("断网自动暂停；联网后改说“信号恢复了”（巡检第 5 批：原来一直停在“网络断开”）；卡里只有一句说明、一个主按钮", () => {
    runner({ items: [item(demoCourse("reverse_park", "a"))], practice: true });
    fireEvent.click(screen.getByRole("button", { name: "开始" }));
    pump(3);
    act(() => void window.dispatchEvent(new Event("offline")));
    let card = document.querySelector(".ds-exam .ds-overlay__card") as HTMLElement;
    expect(within(card).getByText("信号断了，已自动暂停")).toBeTruthy();
    act(() => void window.dispatchEvent(new Event("online")));
    card = document.querySelector(".ds-exam .ds-overlay__card") as HTMLElement;
    expect(within(card).getByText("信号恢复了")).toBeTruthy();
    expect(card.querySelectorAll("p")).toHaveLength(1);
    expect(within(card).getByRole("button", { name: "继续" })).toBeTruthy();
  });
});

describe("第二批·手感：方向盘跟手转、中心有死区；键盘 ↓ 也是刹车", () => {
  function wheelAt100() {
    const wheel = screen.getByRole("slider", { name: "方向盘" });
    wheel.getBoundingClientRect = () => ({ left: 0, top: 0, right: 100, bottom: 100, width: 100, height: 100, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect;
    return wheel;
  }

  /** 方向盘当前显示的角度（atan2 往返会带一点浮点误差，按近似比） */
  const shownAngle = (wheel: HTMLElement) => Number(/rotate\((-?[\d.e-]+)deg\)/.exec(wheel.style.transform)![1]);
  const moveTo = (wheel: HTMLElement, deg: number) => {
    // 以圆心为原点转到 deg 度（屏幕坐标 y 向下，顺时针为正 → 向右打）
    const a = (deg * Math.PI) / 180;
    fireEvent.pointerMove(wheel, { clientX: 50 + 50 * Math.cos(a), clientY: 50 + 50 * Math.sin(a), pointerId: 1 });
  };

  it("拖动时跟着手指连续转（转 24° 就显示 24°），每 10° 一档（24° 是 2 档），松手转到所在那一档（20°）", () => {
    runner({ items: [item(demoCourse("reverse_park", "a"))], practice: true });
    const wheel = wheelAt100();
    fireEvent.pointerDown(wheel, { clientX: 100, clientY: 50, pointerId: 1 });
    moveTo(wheel, 24);
    expect(shownAngle(wheel)).toBeCloseTo(24, 6);
    expect(wheel.getAttribute("aria-valuenow")).toBe("2");
    fireEvent.pointerUp(wheel, { pointerId: 1 });
    expect(wheel.style.transform).toBe("rotate(20deg)");
    expect(wheel.getAttribute("aria-valuetext")).toBe("向右 2 档");
  });

  it("满舵是 120°（12 档）：再往下转也不超过 120°（巡检触屏实测 P2：原来要转满半圈）", () => {
    runner({ items: [item(demoCourse("reverse_park", "a"))], practice: true });
    const wheel = wheelAt100();
    fireEvent.pointerDown(wheel, { clientX: 100, clientY: 50, pointerId: 1 });
    for (const deg of [40, 80, 120]) moveTo(wheel, deg);
    expect(shownAngle(wheel)).toBeCloseTo(120, 6);
    expect(wheel.getAttribute("aria-valuenow")).toBe("12");
    moveTo(wheel, 160);
    expect(shownAngle(wheel)).toBe(120);
    fireEvent.pointerUp(wheel, { pointerId: 1 });
    expect(wheel.getAttribute("aria-valuetext")).toBe("向右 12 档");
  });

  it("手指从中心穿过去不会让方向盘猛跳半圈（死区里不转、不记起点）", () => {
    runner({ items: [item(demoCourse("reverse_park", "a"))], practice: true });
    const wheel = wheelAt100();
    fireEvent.pointerDown(wheel, { clientX: 100, clientY: 50, pointerId: 1 });
    fireEvent.pointerMove(wheel, { clientX: 52, clientY: 51, pointerId: 1 });
    fireEvent.pointerMove(wheel, { clientX: 0, clientY: 50, pointerId: 1 });
    expect(wheel.style.transform).toBe("rotate(0deg)");
    expect(wheel.getAttribute("aria-valuenow")).toBe("0");
  });

  it("↓ 和空格一样是刹车：按下时刹车键显示按下，松开恢复", () => {
    runner({ items: [item(demoCourse("reverse_park", "a"))], practice: true });
    fireEvent.click(screen.getByRole("button", { name: "开始" }));
    key("keyDown", "ArrowDown");
    expect(screen.getByRole("button", { name: "刹车" }).getAttribute("aria-pressed")).toBe("true");
    key("keyUp", "ArrowDown");
    expect(screen.getByRole("button", { name: "刹车" }).getAttribute("aria-pressed")).toBe("false");
  });
});

describe("第二批·巡检转来的考局反馈", () => {
  it("正式考试停进车位也显示“到位了，保持停稳”（结果反馈，不是答案提示），和提示排在右上同一列", () => {
    const course = demoCourse("reverse_park", "a");
    const script = cases.find((c) => c.name === "reverse_park.a")!;
    const whole = new Replay(course);
    whole.apply(script.events, script.ticks);
    const doneAt = whole.events.find((e) => e.k === "done")!.t;
    const near = new Replay(course);
    near.apply(script.events, doneAt - 20);
    runner({ items: [item(course, near.snapshot())], practice: false });
    fireEvent.click(screen.getByRole("button", { name: "继续" }));
    pump(20, () => !!screen.queryByText(/到位了，保持停稳/));
    const hold = screen.getByText(/到位了，保持停稳/);
    expect(hold.closest(".ds-field__feed")).toBeTruthy();
  });

  it("红线后先停在考场的结果卡上，点“看成绩单”才离开（成绩已经交给考场）", async () => {
    const finished: unknown[] = [];
    const backend: DriveBackend = {
      upload: async (chunk: InputChunk): Promise<InputResult> => ({
        session_id: "s",
        session_state: "settled",
        item_index: chunk.item_index,
        current_item: 0,
        item_status: "failed",
        committed_tick: chunk.upto_tick,
        new_events: [],
        deducted: 0,
        snapshot: null,
        result: { passed: false, score: 0, max_score: 100, pass_score: 80, deductions: [], fatal: { kind: "red_light", label: "闯了红灯", points: 0, item: "route", t: 20, ref: null, question_id: null }, review: [], items: [], pet_says: "", next: null } as unknown as InputResult["result"],
      }),
      pause: async () => ({}),
      reload: async () => {
        throw new Error("不该重新同步");
      },
    };
    runner({ items: [item(demoCourse("reverse_park", "a"))], backend, onFinished: (r) => finished.push(r) });
    fireEvent.click(screen.getByRole("button", { name: "开始" }));
    pump(40);
    await waitFor(() => expect(screen.getByText("红线：闯了红灯")).toBeTruthy());
    expect(finished).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "看成绩单" }));
    expect(finished).toHaveLength(1);
  });

  it("开考说明列出扣分项（规格 §4.3，数据来自课程）", async () => {
    const svc = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
    const s = await svc.createSession({ subject: "s3", mode: "practice", item: null }, "k:p3");
    renderApp(`/school/session/${s.session_id}`, svc);
    await screen.findByRole("button", { name: "开始练习" });
    const section = screen.getByRole("region", { name: "扣分项" });
    const info = DEMO_CURRICULUM.subjects.find((x) => x.subject === "s3")!;
    expect(info.deductions.length).toBeGreaterThan(3);
    const rows = within(section).getAllByRole("listitem").map((li) => li.textContent);
    expect(rows).toEqual(info.deductions.map((d) => `${d.label}−${d.points}`));
  });

  it("离开考场的对话框：Esc 等于回去接着考", async () => {
    const svc = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
    const s = await svc.begin((await svc.createSession({ subject: "s1", mode: "formal", item: null }, "k:esc")).session_id);
    renderApp(`/school/session/${s.session_id}`, svc);
    fireEvent.click(await screen.findByRole("button", { name: "离开" }));
    expect(screen.getByRole("alertdialog", { name: "离开考场" })).toBeTruthy();
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("alertdialog", { name: "离开考场" })).toBeNull());
  });

  it("考局页不再静态引入两个答题 / 驾驶组件（按考局类型按需加载）", () => {
    const src = readFileSync(resolve(HERE, "..", "src", "features", "driving_school", "pages", "SessionPage.tsx"), "utf8");
    expect(src).not.toMatch(/^import\s+\{[^}]*\b(QuizRunner|DriveRunner)\b[^}]*\}\s+from/m);
    expect(src).toMatch(/lazy\(\(\) => import\("\.\.\/drive\/DriveRunner"\)/);
    expect(src).toMatch(/lazy\(\(\) => import\("\.\.\/quiz\/QuizRunner"\)/);
  });
});

describe("第二批·回放：看得懂错在哪一刻，可以定位", () => {
  const wild = () => {
    const course = demoCourse("reverse_park", "a");
    const script = cases.find((c) => c.name === "reverse_park.a.wild")!;
    return { ...item(course), status: "failed", events: script.events as DriveItemProgress["events"], committed_tick: 514 };
  };

  it("播到扣分那一刻，画面里贴“−5 压线”，下面写明第几秒", () => {
    render(<ReplayViewer items={[wild()]} reasons={DEMO_CURRICULUM.reasons} />);
    fireEvent.change(screen.getByRole("slider", { name: "回放时间" }), { target: { value: "70" } });
    expect(texts()).toContain("−5 压线");
    expect(screen.getByText("第 0:02 · −5 压线")).toBeTruthy();
  });

  it("定位：切到那一项、跳到事发前 1.5 秒、停住；同一处换个 nonce 可以再跳一次", () => {
    const other = { ...item(demoCourse("side_park", "a")), status: "done", committed_tick: 30 };
    const view = (seek: ReplaySeek | null) => <ReplayViewer items={[other, wild()]} reasons={DEMO_CURRICULUM.reasons} seek={seek} />;
    const { rerender } = render(view(null));
    const slider = () => screen.getByRole("slider", { name: "回放时间" }) as HTMLInputElement;
    rerender(view({ item: "reverse_park", tick: 100, nonce: 1 }));
    expect(slider().value).toBe("55");
    expect(screen.getByRole("button", { name: "倒车入库" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "播放" })).toBeTruthy();
    fireEvent.change(slider(), { target: { value: "300" } });
    rerender(view({ item: "reverse_park", tick: 100, nonce: 2 }));
    expect(slider().value).toBe("55");
  });
});

describe("第二批·素材接口：小车 / 装饰图到了就用图，没到就用代码画", () => {
  const course = demoCourse("reverse_park", "a");
  const frame = (): Frame => ({
    course,
    pose: { x: course.start.x, y: course.start.y, hx: course.start.hx, hy: course.start.hy },
    steer: 0,
    gear: 1,
    brake: false,
    blink: 0,
    tick: 0,
    knocked: [],
    route: null,
    pressedLine: null,
    practice: false,
    predicted: null,
    blinkOn: true,
  });
  const paint = (sprites: DriveSprites | null, extra: Partial<Frame> = {}) => {
    calls = [];
    const pal = readPalette(document.body);
    draw(fakeContext(), 320, 300, fitCamera(course.view, 320, 300), { ...frame(), ...extra }, pal, sprites);
    return calls.filter((c) => c.fn === "drawImage");
  };

  it("没有素材：一张图都不画（全是代码画法）", () => {
    expect(paint(null)).toHaveLength(0);
    expect(paint({ car: null, grass: null, asphalt: null, decor: {}, version: 0 })).toHaveLength(0);
  });

  it("有小车图和树的图：车身、每棵树都用图画，场地线仍由代码画", () => {
    const car = { id: "car" } as unknown as CanvasImageSource;
    const tree = { id: "tree" } as unknown as CanvasImageSource;
    const images = paint({ car, grass: null, asphalt: null, decor: { tree: [tree] }, version: 2 });
    expect(images.filter((c) => c.args[0] === car)).toHaveLength(1);
    expect(images.filter((c) => c.args[0] === tree)).toHaveLength(course.decor.filter((d) => d.type === "tree").length);
    expect(calls.some((c) => c.fn === "stroke")).toBe(true);
  });

  it("加载：图片宽大于 0 才算到了（version 加 1）；宽为 0 或出错就不填，继续用代码画", () => {
    const made: { onload: (() => void) | null; onerror: (() => void) | null; naturalWidth: number; src: string; decoding: string }[] = [];
    const make = () => {
      const img = { onload: null, onerror: null, naturalWidth: 0, src: "", decoding: "" };
      made.push(img);
      return img as unknown as HTMLImageElement;
    };
    const sprites = loadDriveSprites({ car: "/car.png", decor: { tree: ["/tree.png"] } }, make, 1);
    expect(made.map((m) => m.src)).toEqual(["/car.png", "/tree.png"]);
    made[0].naturalWidth = 380;
    made[0].onload?.();
    made[1].onload?.();
    expect(sprites.car).toBe(made[0]);
    expect(sprites.decor.tree?.[0]).toBeUndefined();
    expect(sprites.version).toBe(1);
  });

  it("状态徽标占住的左上角：落进去的建筑名 / 场地名挪到徽标下面（巡检第 6 批：320 宽压住“农场路口”）", () => {
    const withLabel = { ...course, decor: [...course.decor, { type: "building", poly: [[-16, 13], [-12, 13], [-12, 15], [-16, 15]] as [number, number][], label: "测试楼" }] };
    const at = (avoid: { w: number; h: number } | null) => {
      calls = [];
      draw(fakeContext(), 320, 300, fitCamera(withLabel.view, 320, 300), { ...frame(), course: withLabel, avoid }, readPalette(document.body), null);
      const call = calls.find((c) => c.fn === "fillText" && c.args[0] === "测试楼")!;
      return Number(call.args[2]);
    };
    // 这栋楼的名字画在 (27, 81) 附近：徽标框 200×100 盖住它 → 挪到框下面；框只有 200×40 时本来就不挨着 → 原地不动
    const free = at(null);
    expect(free).toBeLessThan(100);
    expect(at({ w: 200, h: 100 })).toBeGreaterThan(100);
    expect(at({ w: 200, h: 40 })).toBe(free);
  });
});

/* ================= 第三批（2026-09-24）：科三视频邀请在矮屏上不挡路 ================= */

describe("第三批·科三视频邀请：矮屏收成场地最上方的窄条，不挡路面和车（巡检 R32）", () => {
  it("320×568：邀请出现后的整个窗口里，窄条和每块路面、车身的包围盒都不相交（按后端标准路线逐 tick 复算）", () => {
    const W = 320;
    const H = 568;
    // 场地尺寸按 CSS 算：顶栏 10%（至少 56px）、操作区 30%（至少 216px），中间就是场地（第一批实测 320×295.2）
    expect(decl(".ds-exam__top", "flex")).toBe("0 0 10%");
    expect(decl(".ds-exam__controls", "flex")).toBe("0 0 30%");
    const fieldH = H - Math.max(px(decl(".ds-exam__top", "min-height")), H * 0.1) - Math.max(px(decl(".ds-exam__controls", "min-height")), H * 0.3);
    expect(fieldH).toBeCloseTo(295.2, 5);
    // 窄条：矮屏规则（568 ≤ 780，媒体查询生效）；宽度沿用基础规则 min(320px, 100% − 24px)、左右居中
    const MEDIA = "@media (max-height: 780px)";
    expect(H).toBeLessThanOrEqual(780);
    expect(decl(".ds-invite", "width")).toBe("min(320px, calc(100% - 24px))");
    const width = Math.min(320, W - 24);
    const top = px(decl(".ds-invite", "top", MEDIA));
    const strip = { x0: (W - width) / 2, x1: (W + width) / 2, y0: top, y1: top + px(decl(".ds-invite", "height", MEDIA)) };
    const hits = (b: { x0: number; x1: number; y0: number; y1: number } | null) => !!b && b.x0 < strip.x1 && b.x1 > strip.x0 && b.y0 < strip.y1 && b.y1 > strip.y0;

    for (const name of ["route.a", "route.b.no_signals"]) {
      const c = (golden as unknown as { cases: { name: string; course: Course; events: InputEventT[]; ticks: number }[] }).cases.find((x) => x.name === name)!;
      const course = c.course;
      const body = course.car;
      const replay = new Replay(course);
      let shownAt = -1;
      let checked = 0;
      for (let t = 0; t < c.ticks && replay.status === "running"; t++) {
        const fresh = replay.apply(c.events.filter((e) => e.t === t), t + 1);
        if (shownAt < 0 && fresh.some((e) => e.k === "invite_shown")) shownAt = t;
        if (shownAt < 0 || t - shownAt > course.route!.invite.window_ticks) continue;
        const car = replay.car;
        const cam = followCamera({ x: car.x, y: car.y, hx: car.hx, hy: car.hy }, W, fieldH);
        const X = (x: number) => (x - cam.cx) * cam.scale + W / 2;
        const Y = (y: number) => fieldH / 2 - (y - cam.cy) * cam.scale;
        // 投影后的包围盒，裁到场地里；完全在场地外就是 null
        const box = (pts: [number, number][]) => {
          const xs = pts.map((p) => X(p[0]));
          const ys = pts.map((p) => Y(p[1]));
          const b = { x0: Math.max(0, Math.min(...xs)), x1: Math.min(W, Math.max(...xs)), y0: Math.max(0, Math.min(...ys)), y1: Math.min(fieldH, Math.max(...ys)) };
          return b.x0 < b.x1 && b.y0 < b.y1 ? b : null;
        };
        for (const d of course.decor.filter((x) => x.type === "asphalt")) {
          expect(hits(box(d.poly!)), `${name} 第 ${t} tick：窄条压到路面 ${JSON.stringify(d.poly![0])}`).toBe(false);
        }
        const local: [number, number][] = [
          [-body.rear, -body.width / 2],
          [body.wheelbase + body.front, -body.width / 2],
          [body.wheelbase + body.front, body.width / 2],
          [-body.rear, body.width / 2],
        ];
        const corners = local.map(([a, b]): [number, number] => [car.x + car.hx * a - car.hy * b, car.y + car.hy * a + car.hx * b]);
        expect(hits(box(corners)), `${name} 第 ${t} tick：窄条压到车`).toBe(false);
        checked += 1;
      }
      // 前提：邀请确实出现过、整个窗口都查到了（否则“不相交”是空的）
      expect(shownAt, `${name} 邀请出现`).toBeGreaterThan(0);
      expect(checked, `${name} 查过的 tick 数`).toBeGreaterThan(course.route!.invite.window_ticks);
    }
  });

  it("窄条里两行字、两个键：键不小于 44px、不折行；窄条在的时候右上角的提示列挪到它下面", () => {
    const MEDIA = "@media (max-height: 780px)";
    expect(px(decl(".ds-invite .ps-btn", "min-height", MEDIA))).toBeGreaterThanOrEqual(44);
    expect(decl(".ds-invite .ps-row", "flex-wrap", MEDIA)).toBe("nowrap");
    const stripBottom = px(decl(".ds-invite", "top", MEDIA)) + px(decl(".ds-invite", "height", MEDIA));
    expect(px(decl(".ds-exam__field[data-invite] .ds-field__feed", "top", MEDIA))).toBeGreaterThan(stripBottom);
    runner({ items: [item(demoCourse("route", "a"))], practice: true });
    const field = document.querySelector(".ds-exam__field") as HTMLElement;
    expect(field.hasAttribute("data-invite")).toBe(false);
  });
});

/* ================= 第四批（2026-09-24）：接入 UI-ASSET-009 素材 ================= */

describe("第四批·素材接入（UI-ASSET-009）", () => {
  const ASSET_DIR = resolve(HERE, "..", "public", "ui-assets", "UI-ASSET-009", "v1");
  const fakeImg = (id: string, w = 160, h = 160) => ({ id, naturalWidth: w, naturalHeight: h, width: w, height: h }) as unknown as CanvasImageSource;
  const baseFrame = (course: Course): Frame => ({
    course,
    pose: { x: course.start.x, y: course.start.y, hx: course.start.hx, hy: course.start.hy },
    steer: 0,
    gear: 1,
    brake: false,
    blink: 0,
    tick: 0,
    knocked: [],
    route: null,
    pressedLine: null,
    practice: false,
    predicted: null,
    blinkOn: true,
  });
  const sprites = (over: Partial<DriveSprites>): DriveSprites => ({ car: null, grass: null, asphalt: null, decor: {}, version: 1, ...over });
  const light = () => readPalette(document.body);
  /** 深色调色板：按 tokens.css 深色值替换用到的键（ink 变浅就会走深色的压暗） */
  const darkPalette = (): Palette => {
    const t = tokens("dark");
    const v = (name: string) => t.get(name)!;
    return { ...light(), grass: v("--c-leaf-soft"), road: v("--c-deep-ink"), paint: v("--c-on-deep"), center: v("--c-sun"), curb: v("--c-ink-3"), ink: v("--c-ink"), leaf: v("--c-leaf"), danger: v("--c-danger") };
  };
  /** 只看主画布上的调用（压暗素材时离屏画布上的 drawImage(原图) 不算画进画面） */
  const paintWith = (course: Course, spr: DriveSprites | null, pal: Palette = light(), extra: Partial<Frame> = {}, w = 320, h = 300) => {
    calls = [];
    draw(fakeContext("main"), w, h, fitCamera(course.view, w, h), { ...baseFrame(course), ...extra }, pal, spr);
    return calls.filter((c) => c.ctx === "main");
  };

  it("网址全部取自 SCHOOL_ART（field 的车、2 倍屏大图、草地、柏油、树 A/B、灌木、锥桶、旗；第五批加教练头像 coach.portrait），不另写路径；科三建筑网址交付前为空", () => {
    const f = SCHOOL_ART.field;
    expect(DRIVE_SPRITE_URLS).toEqual({
      car: f.car,
      carLarge: f.carLarge,
      grass: f.grass,
      asphalt: f.asphalt,
      decor: { tree: [f.treeA, f.treeB], bush: [f.bush], cone: [f.cone], flag: [f.flag], coach: [SCHOOL_ART.coach.portrait] },
      buildings: {},
    });
  });

  it("任何一张加载失败都退回代码画法：图片全部报错时，画出来的每一笔都和没有素材时一样", () => {
    const made: { onload: (() => void) | null; onerror: (() => void) | null; src: string; naturalWidth: number }[] = [];
    const make = () => {
      const img = { onload: null, onerror: null, src: "", naturalWidth: 0, decoding: "" };
      made.push(img);
      return img as unknown as HTMLImageElement;
    };
    const failed = loadDriveSprites(DRIVE_SPRITE_URLS, make, 1);
    // 第四批 8 张，第五批加教练头像 1 张；科三建筑网址为空，不加载
    expect(made).toHaveLength(9);
    for (const img of made) img.onerror?.();
    expect([failed.car, failed.grass, failed.asphalt]).toEqual([null, null, null]);
    for (const name of ["reverse_park", "route"] as const) {
      const course = demoCourse(name, "a");
      const plain = paintWith(course, null).map((c) => c.fn);
      const withFailed = paintWith(course, failed).map((c) => c.fn);
      expect(withFailed).toEqual(plain);
      expect(withFailed).not.toContain("drawImage");
      expect(withFailed).not.toContain("createPattern");
    }
  });

  it("小车：2 倍屏以上加载大图；按模拟车身矩形画（3.8:1.7），灯画在图上面，TA 画进车顶圆窗（车尾起 37%）", () => {
    const srcs = (dpr: number) => {
      const made: { src: string }[] = [];
      loadDriveSprites({ car: "/c.webp", carLarge: "/c-large.webp" }, () => {
        const img = { src: "", onload: null, onerror: null, decoding: "" };
        made.push(img);
        return img as unknown as HTMLImageElement;
      }, dpr);
      return made.map((m) => m.src);
    };
    expect(srcs(1)).toEqual(["/c.webp"]);
    expect(srcs(2)).toEqual(["/c-large.webp"]);
    expect(srcs(3)).toEqual(["/c-large.webp"]);

    const course = demoCourse("reverse_park", "a");
    const car = fakeImg("car", 380, 170);
    const log = paintWith(course, sprites({ car }), light(), { brake: true });
    const S = fitCamera(course.view, 320, 300).scale;
    const body = course.car;
    const at = log.findIndex((c) => c.fn === "drawImage" && c.args[0] === car);
    expect(at).toBeGreaterThanOrEqual(0);
    const [, x, y, w, h] = log[at].args as number[];
    expect(x).toBeCloseTo(-body.rear * S, 6);
    expect(y).toBeCloseTo((-body.width / 2) * S, 6);
    expect(w / h).toBeCloseTo(3.8 / 1.7, 6);
    expect(w).toBeCloseTo((body.rear + body.wheelbase + body.front) * S, 6);
    // 刹车灯（两块 fillRect）在车图之后画
    expect(log.slice(at).filter((c) => c.fn === "fillRect").length).toBeGreaterThanOrEqual(2);
    // TA 的脑袋：车图之后第一个圆，圆心在车尾起 37%、车身中线上
    const head = log.slice(at).find((c) => c.fn === "arc")!;
    const len = (body.rear + body.wheelbase + body.front) * S;
    expect(head.args[0]).toBeCloseTo(-body.rear * S + ROOF_WINDOW.fromRear * len, 6);
    expect(head.args[1]).toBe(0);
    expect(head.args[2]).toBeCloseTo(ROOF_WINDOW.petRadius * body.width * S, 6);
  });

  it("地面：草地、柏油平铺成纹理，纹理原点钉在世界坐标（镜头移 2 米，纹理跟着移 2 米，不“游”）", () => {
    const course = demoCourse("reverse_park", "a");
    const grass = fakeImg("grass", 256, 256);
    const asphalt = fakeImg("asphalt", 256, 256);
    const spr = sprites({ grass, asphalt });
    const transformAt = (cx: number) => {
      calls = [];
      const cam = fitCamera(course.view, 320, 300);
      draw(fakeContext(), 320, 300, { ...cam, cx }, baseFrame(course), light(), spr);
      const find = (img: unknown) => calls.filter((c) => c.fn === "pattern.setTransform").find((c) => c.args[0] === img)?.args[1] as { a: number; d: number; e: number; f: number };
      // 浅色下柏油压过色（是离屏画布），草地原样
      const asphaltSource = calls.find((c) => c.fn === "createPattern" && c.args[0] !== grass)?.args[0];
      return { cam, grass: find(grass), asphalt: find(asphaltSource) };
    };
    const a = transformAt(0);
    const b = transformAt(2);
    const S = a.cam.scale;
    expect(a.grass.a).toBeCloseTo((S * TILE_METERS.grass) / 256, 9);
    expect(a.asphalt.a).toBeCloseTo((S * TILE_METERS.asphalt) / 256, 9);
    expect(b.grass.e - a.grass.e).toBeCloseTo(-2 * S, 9);
    expect(b.asphalt.e - a.asphalt.e).toBeCloseTo(-2 * S, 9);
    expect(b.grass.f).toBeCloseTo(a.grass.f, 9);
  });

  it("柏油纹理（平均亮度按素材实算）上的白线、黄线、停止线、车位线、判定线对比度 ≥ 3；深色压暗后仍 ≥ 3", () => {
    // 纹理平均颜色：Pillow 按 sRGB 通道平均（scratchpad/ds-drive/asset-stats.py），绑定到交付单的 SHA-256
    const file = readFileSync(resolve(ASSET_DIR, "field-asphalt-tile.webp"));
    expect(createHash("sha256").update(file).digest("hex")).toBe("35c835d5935e715e52e3e246e102a208afaae8d46b55b8c7a716107588ff5ef2");
    const AVG = [106.4, 108.29, 108.08];
    const hex = (rgb: number[]) => `#${rgb.map((c) => Math.round(c).toString(16).padStart(2, "0")).join("")}`;
    const mix = (a: number[], b: number[], p: number) => a.map((c, i) => c * (1 - p) + b[i] * p);
    for (const scheme of ["light", "dark"] as const) {
      const t = tokens(scheme);
      const rgbOf = (name: string) => rgb(`var(${name})`, t);
      const PAL: Record<string, string> = { road: "--c-deep-ink", grass: "--c-leaf-soft" };
      const rule = SHADE[scheme].asphalt;
      const bg = rule ? mix(AVG, rgbOf(PAL[rule.color]), rule.alpha) : AVG;
      const road = hex(bg);
      const lines: [string, number[]][] = [
        ["白线 / 停止线 / 车位线 / 衬边", rgbOf("--c-on-deep")],
        ["黄线（中心线、区域虚线）", rgbOf("--c-sun")],
        ["路沿 / 隔离判定线", rgbOf("--c-ink-3")],
        ["车道虚线（70% 不透明）", mix(bg, rgbOf("--c-on-deep"), 0.7)],
      ];
      for (const [what, color] of lines) {
        expect(ratio(hex(color), road, scheme), `${scheme} ${what}`).toBeGreaterThanOrEqual(3);
      }
    }
  });

  it("装饰：树 A/B 轮流，半径 ≤ 1 米的画成灌木；锥桶图按判定圆的尺寸画；终点旗只插在装着目标区中心的区域上", () => {
    const [A, B, bush, cone, flag] = ["treeA", "treeB", "bush", "cone", "flag"].map((id) => fakeImg(id, 64, 64));
    const spr = sprites({ decor: { tree: [A, B], bush: [bush], cone: [cone], flag: [flag] } });
    const route = demoCourse("route", "a");
    const trees = route.decor.filter((d) => d.type === "tree");
    const used = paintWith(route, spr).filter((c) => c.fn === "drawImage" && [A, B, bush].includes(c.args[0] as CanvasImageSource)).map((c) => (c.args[0] as { id: string }).id);
    expect(used).toEqual(trees.map((d, i) => ((d.r ?? 1) <= BUSH_MAX_R ? "bush" : i % 2 === 0 ? "treeA" : "treeB")));
    expect(used).toContain("bush");

    // 锥桶：以锥桶为原点画，边长＝2×max(4, 判定半径×比例尺×1.2)；放大画面时跟着判定圆一起变大
    for (const w of [320, 1280]) {
      const park = demoCourse("reverse_park", "a");
      const S = fitCamera(park.view, w, 300).scale;
      const draws = paintWith(park, spr, light(), {}, w, 300).filter((c) => c.fn === "drawImage" && c.args[0] === cone);
      expect(draws).toHaveLength(park.cones.length);
      const r = Math.max(4, park.cones[0].r * S * 1.2);
      expect(draws[0].args.slice(1)).toEqual([-r, -r, r * 2, r * 2]);
    }

    // 终点旗：弯道的终点区装着目标区中心 → 1 面；倒车入库的“起始区”不装 → 0 面
    expect(paintWith(demoCourse("curve", "a"), spr).filter((c) => c.fn === "drawImage" && c.args[0] === flag)).toHaveLength(1);
    expect(paintWith(demoCourse("reverse_park", "a"), spr, light(), { practice: true }).filter((c) => c.fn === "drawImage" && c.args[0] === flag)).toHaveLength(0);
  });

  it("深色：纹理、装饰、车都换成压暗过的离屏图，不直接画白天的原图；浅色下装饰和车用原图", () => {
    const course = demoCourse("reverse_park", "a");
    const A = fakeImg("treeA");
    const car = fakeImg("car", 380, 170);
    const grass = fakeImg("grass", 256, 256);
    const spr = sprites({ car, grass, decor: { tree: [A] } });
    const lightDraws = paintWith(course, spr).filter((c) => c.fn === "drawImage").map((c) => c.args[0]);
    expect(lightDraws).toContain(A);
    expect(lightDraws).toContain(car);
    const darkLog = paintWith(course, spr, darkPalette());
    const darkDraws = darkLog.filter((c) => c.fn === "drawImage").map((c) => c.args[0]);
    expect(darkDraws).not.toContain(A);
    expect(darkDraws).not.toContain(car);
    expect(darkDraws.filter((x) => x instanceof HTMLCanvasElement).length).toBeGreaterThanOrEqual(course.decor.filter((d) => d.type === "tree").length + 1);
    // 草地纹理用的是压暗后的图
    const patternSources = darkLog.filter((c) => c.fn === "createPattern").map((c) => c.args[0]);
    expect(patternSources).not.toContain(grass);
    expect(patternSources.some((x) => x instanceof HTMLCanvasElement)).toBe(true);
  });

  it("续考时视频邀请已经弹出、还没处理：继续开以后卡片接着显示（对照：邀请还没弹出时不显示）", () => {
    const course = demoCourse("route", "a");
    const script = cases.find((c) => c.name === "route.a")!;
    const at = (tick: number) => {
      const r = new Replay(course);
      r.apply(script.events, tick);
      return r.snapshot();
    };
    const pending = at(1090);
    expect(pending.route?.invite_tick).not.toBeNull();
    expect(pending.route?.invite_done).toBe(0);
    runner({ items: [item(course, pending)], practice: true });
    fireEvent.click(screen.getByRole("button", { name: "继续" }));
    expect(screen.getByRole("alertdialog", { name: "手机收到视频邀请" })).toBeTruthy();
    cleanup();
    const before = at(1070);
    expect(before.route?.invite_tick).toBeNull();
    runner({ items: [item(course, before)], practice: true });
    fireEvent.click(screen.getByRole("button", { name: "继续" }));
    expect(screen.queryByRole("alertdialog", { name: "手机收到视频邀请" })).toBeNull();
  });

  it("深色：代码画的房子（纸色夜里不变）再压一层，每栋多一次填色；房名纸墨字在压暗后的纸色、纸影色上仍 ≥ 4.5", () => {
    const route = demoCourse("route", "a");
    const houses = route.decor.filter((d) => d.type === "building").length;
    const fills = (pal: Palette) => paintWith(route, null, pal).filter((c) => c.fn === "fill").length;
    expect(fills(darkPalette()) - fills(light())).toBe(houses);
    const t = tokens("dark");
    const rgbOf = (name: string) => rgb(`var(${name})`, t);
    const hex = (c: number[]) => `#${c.map((v) => Math.round(v).toString(16).padStart(2, "0")).join("")}`;
    for (const paper of ["--paper", "--paper-shade"]) {
      const bg = rgbOf(paper).map((v, i) => v * (1 - BUILDING_DARK_ALPHA) + rgbOf("--c-deep-ink")[i] * BUILDING_DARK_ALPHA);
      expect(ratio("var(--paper-ink)", hex(bg), "dark"), paper).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("静态层离屏缓存：镜头固定只画一次；跟车镜头在余量内只挪贴图、走出余量才重画；换明暗重画；压着的线不烤进缓存", () => {
    const tree = fakeImg("tree");
    const spr = sprites({ decor: { tree: [tree] } });
    // 场地类：连画三帧，静态层只画一次，每帧主画布贴一次缓存
    const park = demoCourse("reverse_park", "a");
    const cache = createStaticLayerCache();
    const camP = fitCamera(park.view, 320, 300);
    for (let i = 0; i < 3; i++) drawCached(fakeContext("main"), 320, 300, camP, { ...baseFrame(park), tick: i }, light(), spr, cache, 2);
    expect(cache.renders).toBe(1);
    expect(cache.margin).toBe(0);
    calls = [];
    drawCached(fakeContext("main"), 320, 300, camP, baseFrame(park), light(), spr, cache, 2);
    const main = calls.filter((c) => c.ctx === "main");
    expect(main.filter((c) => c.fn === "drawImage" && c.args[0] === cache.canvas)).toHaveLength(1);
    expect(main.filter((c) => c.fn === "drawImage" && c.args[0] === tree)).toHaveLength(0);
    // 压着的线：缓存不因为压线重画（没烤进去），主画布上多出衬边、红线、车身红框三笔（对照：同一帧不压线）
    const mainStrokes = (pressedLine: string | null) => {
      calls = [];
      drawCached(fakeContext("main"), 320, 300, camP, { ...baseFrame(park), pressedLine }, light(), spr, cache, 2);
      return calls.filter((c) => c.ctx === "main" && c.fn === "stroke").length;
    };
    const plain = mainStrokes(null);
    const withLine = mainStrokes(park.lines[0].id);
    expect(cache.renders).toBe(1);
    expect(withLine - plain).toBe(3);
    // 换深色：重画
    drawCached(fakeContext("main"), 320, 300, camP, baseFrame(park), darkPalette(), spr, cache, 2);
    expect(cache.renders).toBe(2);

    // 科三跟车：余量＝长边 × FOLLOW_MARGIN；镜头挪 1 米在余量内，不重画，贴图位置跟着挪；挪出余量就重画
    const route = demoCourse("route", "a");
    const rc = createStaticLayerCache();
    const cam0 = followCamera({ x: 20, y: 2, hx: 1, hy: 0 }, 320, 300);
    drawCached(fakeContext("main"), 320, 300, cam0, baseFrame(route), light(), spr, rc, 2);
    expect(rc.renders).toBe(1);
    expect(rc.margin).toBe(Math.round(320 * FOLLOW_MARGIN));
    calls = [];
    const cam1 = { ...cam0, cx: cam0.cx + 1 };
    drawCached(fakeContext("main"), 320, 300, cam1, baseFrame(route), light(), spr, rc, 2);
    expect(rc.renders).toBe(1);
    const blit = calls.find((c) => c.ctx === "main" && c.fn === "drawImage" && c.args[0] === rc.canvas)!;
    expect(blit.args[1]).toBeCloseTo(-1 * cam0.scale - rc.margin, 9);
    expect(blit.args[2]).toBeCloseTo(-rc.margin, 9);
    const far = { ...cam0, cx: cam0.cx + (rc.margin / cam0.scale) * 1.5 };
    drawCached(fakeContext("main"), 320, 300, far, baseFrame(route), light(), spr, rc, 2);
    expect(rc.renders).toBe(2);
  });

  it("回放只加载一次素材（拖动时间轴、播放时不再每次渲染都新建一批图片）", () => {
    const RealImage = window.Image;
    let made = 0;
    window.Image = class extends RealImage {
      constructor() {
        super();
        made += 1;
      }
    } as typeof Image;
    try {
      const course = demoCourse("reverse_park", "a");
      const script = cases.find((c) => c.name === "reverse_park.a.wild")!;
      render(<ReplayViewer items={[{ ...item(course), status: "failed", events: script.events as DriveItemProgress["events"], committed_tick: 514 }]} reasons={DEMO_CURRICULUM.reasons} />);
      const first = made;
      expect(first).toBeGreaterThan(0);
      for (const v of ["30", "60", "90", "120"]) fireEvent.change(screen.getByRole("slider", { name: "回放时间" }), { target: { value: v } });
      expect(made).toBe(first);
    } finally {
      window.Image = RealImage;
    }
  });
});

/* ================= 第五批（2026-09-24）：龟教练头像、场地名牌让开车、科三建筑预接 UI-ASSET-010 ================= */

describe("第五批·场地细节", () => {
  const fakeImg = (id: string, w = 160, h = 160) => ({ id, naturalWidth: w, naturalHeight: h, width: w, height: h }) as unknown as CanvasImageSource;
  const light = () => readPalette(document.body);
  const darkPalette = (): Palette => {
    const t = tokens("dark");
    const v = (name: string) => t.get(name)!;
    return { ...light(), grass: v("--c-leaf-soft"), road: v("--c-deep-ink"), paint: v("--c-on-deep"), center: v("--c-sun"), curb: v("--c-ink-3"), ink: v("--c-ink"), leaf: v("--c-leaf"), danger: v("--c-danger") };
  };
  const frameAt = (course: Course, pose?: Frame["pose"], extra: Partial<Frame> = {}): Frame => ({
    course,
    pose: pose ?? { x: course.start.x, y: course.start.y, hx: course.start.hx, hy: course.start.hy },
    steer: 0,
    gear: 1,
    brake: false,
    blink: 0,
    tick: 0,
    knocked: [],
    route: null,
    pressedLine: null,
    practice: true,
    predicted: null,
    blinkOn: true,
    ...extra,
  });
  const camFor = (f: Frame, w: number, h: number) => (f.course.kind === "route" ? followCamera(f.pose, w, h) : fitCamera(f.course.view, w, h));
  /** 逐笔序列化：函数名、参数（数字保留 4 位小数，图片记 id，离屏画布记 canvas，纹理记来源）、落笔时的画笔状态 */
  const token = (v: unknown): string => {
    if (v === null || v === undefined) return String(v);
    if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(4);
    if (typeof v !== "object") return String(v);
    if (Array.isArray(v)) return `[${v.map(token).join(",")}]`;
    if (v instanceof HTMLCanvasElement) return "canvas";
    const o = v as Record<string, unknown>;
    if (typeof o.id === "string") return `img:${o.id}`;
    if ("source" in o) return `pattern:${token(o.source)}`;
    return `{${Object.entries(o).map(([k, x]) => `${k}:${token(x)}`).join(",")}}`;
  };
  const serialize = (log: Call[]) => log.map((c) => `${c.fn}(${c.args.map(token).join(",")})|${(c.st ?? []).map(token).join("|")}`);
  /** 第四批的素材（UI-ASSET-009）用假图片：车、草地、柏油、树 A/B、灌木、锥桶、旗 */
  const b4Sprites = (): DriveSprites => ({
    car: fakeImg("car", 380, 170),
    grass: fakeImg("grass", 256, 256),
    asphalt: fakeImg("asphalt", 256, 256),
    decor: { tree: [fakeImg("treeA", 64, 64), fakeImg("treeB", 64, 64)], bush: [fakeImg("bush", 64, 64)], cone: [fakeImg("cone", 64, 64)], flag: [fakeImg("flag", 64, 64)] },
    version: 8,
  });
  /** 按 DRIVE_SPRITE_URLS 加载、每张都报错 */
  const failedSprites = () => {
    const made: { onerror: (() => void) | null }[] = [];
    const s = loadDriveSprites(DRIVE_SPRITE_URLS, () => {
      const img = { onload: null, onerror: null, src: "", naturalWidth: 0, decoding: "" };
      made.push(img);
      return img as unknown as HTMLImageElement;
    }, 1);
    for (const img of made) img.onerror?.();
    return s;
  };
  /**
   * 逐笔记录一组画面：6 种场地 × 明暗 × 两种尺寸 × 有无徽标框 × 三种素材情况（没有 / 全部加载失败 / 只有第四批素材）× 三种分层；
   * 车停在起点这类远离场地名牌的位置（名牌不用挪），有徽标框的一组再加压线、刹车、转向灯、碰倒锥桶、扣分牌子。
   */
  const recordAll = () => {
    const lines: string[] = [];
    const routePoses: Frame["pose"][] = [{ x: 2, y: 1.4, hx: 1, hy: 0 }, { x: 208, y: -30, hx: 0, hy: -1 }];
    const courses: [string, "a" | "b"][] = [["reverse_park", "a"], ["reverse_park", "b"], ["side_park", "a"], ["curve", "a"], ["reverse_straight", "a"], ["route", "a"]];
    for (const [name, v] of courses) {
      const course = demoCourse(name, v);
      const poses = course.kind === "route" ? routePoses : [undefined];
      for (const pose of poses)
        for (const pal of [light(), darkPalette()])
          for (const [w, h] of [[320, 295], [390, 506]])
            for (const avoid of [null, { w: 130, h: 34 }])
              for (const [tag, spr] of [["none", null], ["failed", failedSprites()], ["b4", b4Sprites()]] as const)
                for (const layers of ["all", "static", "dynamic"] as const) {
                  const busy = avoid
                    ? { pressedLine: course.lines[0].id, brake: true, blink: 1, knocked: course.cones.slice(0, 1).map((c) => c.id), marks: [{ x: 0, y: 0, text: "−5 压线", tone: "bad" as const }] }
                    : {};
                  const f = frameAt(course, pose, { avoid, ...busy });
                  calls = [];
                  draw(fakeContext("main"), w, h, camFor(f, w, h), f, pal, spr, layers);
                  lines.push(`## ${name}.${v} ${JSON.stringify(pose ?? null)} ${pal.ink} ${w}x${h} ${avoid ? "avoid" : "-"} ${tag} ${layers}`);
                  lines.push(...serialize(calls.filter((c) => c.ctx === "main")));
                }
    }
    return lines;
  };

  it("没有屋顶 / 标志网址、教练头像没到（或加载失败）、车不挨着场地名牌时：每一笔都和第五批之前一模一样（逐笔记录的指纹绑定改动前的 render.ts a2ffeb10）", () => {
    const lines = recordAll();
    // 指纹对不上时，设 DS_DRIVE_DUMP 把逐笔记录写到文件里比对（只写不读）
    if (process.env.DS_DRIVE_DUMP) writeFileSync(process.env.DS_DRIVE_DUMP, lines.join("\n"), "utf8");
    expect(lines.length).toBeGreaterThan(90000);
    const digest = createHash("sha256").update(lines.join("\n")).digest("hex");
    // 这个指纹是第五批动手之前、在第四批交付的 render.ts（sha256 a2ffeb10…）上跑同一组画面算出来的（93320 行）
    expect(digest).toBe("a2847d26b1cdb79bfb89b6ab6ea03bd5075a812f1b0d3ea9fb9535e9fc8e73d5");
  });

  /* ---------- 几何小工具（用例自己再算一遍，不借 render 里的实现） ---------- */
  type Rect = { x0: number; y0: number; x1: number; y1: number };
  type Pt = [number, number];
  const goldenCases = (golden as unknown as { cases: { name: string; course: Course; events: InputEventT[]; ticks: number }[] }).cases;
  const overlap = (a: Rect, b: Rect) => a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;
  const inside = (a: Rect, w: number, h: number) => a.x0 >= 0 && a.y0 >= 0 && a.x1 <= w && a.y1 <= h;
  const centroidOf = (poly: Pt[]): Pt => [poly.reduce((s, p) => s + p[0], 0) / poly.length, poly.reduce((s, p) => s + p[1], 0) / poly.length];
  /** 凸多边形与矩形相交（分离轴） */
  const polyHitsRect = (poly: Pt[], b: Rect) => {
    const rect: Pt[] = [[b.x0, b.y0], [b.x1, b.y0], [b.x1, b.y1], [b.x0, b.y1]];
    const axes: Pt[] = [[1, 0], [0, 1], ...poly.map((p, i): Pt => [poly[(i + 1) % poly.length][1] - p[1], p[0] - poly[(i + 1) % poly.length][0]])];
    return axes.every(([nx, ny]) => {
      const a = poly.map(([x, y]) => x * nx + y * ny);
      const c = rect.map(([x, y]) => x * nx + y * ny);
      return Math.max(...a) > Math.min(...c) && Math.max(...c) > Math.min(...a);
    });
  };
  /** 线段穿不穿过矩形（Liang–Barsky 裁剪） */
  const segHitsRect = (a: Pt, b: Pt, r: Rect) => {
    let t0 = 0;
    let t1 = 1;
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    const clip = (p: number, q: number) => {
      if (p === 0) return q >= 0;
      const t = q / p;
      if (p < 0) {
        if (t > t1) return false;
        t0 = Math.max(t0, t);
      } else {
        if (t < t0) return false;
        t1 = Math.min(t1, t);
      }
      return true;
    };
    return clip(-dx, a[0] - r.x0) && clip(dx, r.x1 - a[0]) && clip(-dy, a[1] - r.y0) && clip(dy, r.y1 - a[1]);
  };
  const segDist = (p: Pt, a: Pt, b: Pt) => {
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)));
    return Math.hypot(p[0] - a[0] - dx * t, p[1] - a[1] - dy * t);
  };
  const toCanvas = (cam: { cx: number; cy: number; scale: number }, w: number, h: number) => ({
    X: (x: number) => (x - cam.cx) * cam.scale + w / 2,
    Y: (y: number) => h / 2 - (y - cam.cy) * cam.scale,
  });
  /** 计分线平时的线宽（和画线的规则一致：路沿 / 隔离粗一些） */
  const lineWidth = (kind: string, S: number) => (kind === "curb" || kind === "barrier" ? Math.max(3, S * 0.3) : Math.max(2, S * 0.15));
  /** 判定线在画布上的两端与半线宽（计分线＋停止线） */
  const judgeOnCanvas = (course: Course, cam: { cx: number; cy: number; scale: number }, w: number, h: number) => {
    const { X, Y } = toCanvas(cam, w, h);
    const S = cam.scale;
    return [
      ...course.lines.map((l) => ({ id: l.id, a: [X(l.a[0]), Y(l.a[1])] as Pt, b: [X(l.b[0]), Y(l.b[1])] as Pt, half: lineWidth(l.kind, S) / 2 })),
      ...course.decor.filter((d) => d.type === "stopline").map((d, i) => ({ id: `stopline${i}`, a: [X(d.a![0]), Y(d.a![1])] as Pt, b: [X(d.b![0]), Y(d.b![1])] as Pt, half: Math.max(3, S * 0.35) / 2 })),
    ];
  };
  /** 车身矩形（外扩 pad）在画布上的四角：按 drawCar 的平移、旋转再算一遍 */
  const bodyOnCanvas = (course: Course, pose: Frame["pose"], cam: { cx: number; cy: number; scale: number }, w: number, h: number, pad: number): Pt[] => {
    const { X, Y } = toCanvas(cam, w, h);
    const S = cam.scale;
    const a = Math.atan2(-pose.hy, pose.hx);
    const car = course.car;
    const x0 = -car.rear * S - pad;
    const x1 = (car.wheelbase + car.front) * S + pad;
    const hw = (car.width / 2) * S + pad;
    const local: Pt[] = [[x0, -hw], [x1, -hw], [x1, hw], [x0, hw]];
    return local.map(([u, v]): Pt => [X(pose.x) + u * Math.cos(a) - v * Math.sin(a), Y(pose.y) + u * Math.sin(a) + v * Math.cos(a)]);
  };
  /** 车的可见外沿比车身矩形多出来的宽度：压线红框的半线宽、代码画的车轮（0.13 米）里取大的，再留 1px */
  const carReach = (S: number) => Math.max(Math.max(2.5, S * 0.18) / 2, S * 0.13) + 1;
  /** 一行字占的框（假画布量字：每个字 7px；字号从落笔时的 font 里读） */
  const textBoxOf = (c: Call): Rect => {
    const px = Number(/([\d.]+)px/.exec(String(c.st?.[4]))?.[1]);
    const w = String(c.args[0]).length * 7;
    const x = Number(c.args[1]);
    const y = Number(c.args[2]);
    return { x0: x - w / 2, y0: y - px / 2, x1: x + w / 2, y1: y + px / 2 };
  };
  const plateBoxOf = (c: Call): Rect => {
    const t = textBoxOf(c);
    return { x0: t.x0 - PLATE_PAD.x, y0: t.y0 - PLATE_PAD.y, x1: t.x1 + PLATE_PAD.x, y1: t.y1 + PLATE_PAD.y };
  };
  /** 第 i 笔之前那条路径（从最近的 beginPath 起）的外框 */
  const pathBox = (log: Call[], i: number): Rect => {
    let j = i;
    while (j > 0 && log[j].fn !== "beginPath") j--;
    const pts: Pt[] = [];
    for (const c of log.slice(j, i)) {
      const n = c.args.map(Number);
      if (c.fn === "moveTo" || c.fn === "lineTo") pts.push([n[0], n[1]]);
      if (c.fn === "quadraticCurveTo") pts.push([n[0], n[1]], [n[2], n[3]]);
    }
    return { x0: Math.min(...pts.map((p) => p[0])), y0: Math.min(...pts.map((p) => p[1])), x1: Math.max(...pts.map((p) => p[0])), y1: Math.max(...pts.map((p) => p[1])) };
  };
  /** 第 i 笔之前那条路径的顶点（moveTo / lineTo） */
  const pathPoints = (log: Call[], i: number): Pt[] => {
    let j = i;
    while (j > 0 && log[j].fn !== "beginPath") j--;
    return log.slice(j, i).filter((c) => c.fn === "moveTo" || c.fn === "lineTo").map((c): Pt => [Number(c.args[0]), Number(c.args[1])]);
  };
  const expectBox = (got: Rect, want: Rect) => {
    for (const k of ["x0", "y0", "x1", "y1"] as const) expect(got[k], k).toBeCloseTo(want[k], 6);
  };
  const isImg = (c: Call, img: unknown) => c.fn === "drawImage" && c.args[0] === img;
  const mainLog = () => calls.filter((c) => c.ctx === "main");
  const PARKS: [string, "a" | "b"][] = [["reverse_park", "a"], ["reverse_park", "b"], ["side_park", "a"], ["side_park", "b"], ["curve", "a"], ["curve", "b"], ["reverse_straight", "a"], ["reverse_turn", "a"]];

  /* ---------- 1. 场地上的龟教练 ---------- */

  it("龟教练：直接用 SCHOOL_ART.coach.portrait（field 不加键）画圆头像——圆心在原来教练的位置、半径＝原来身体椭圆的长半轴，纸色圆底＋纸色圈＋35% 纸墨细线；外沿离每条计分线 ≥ 1px（不够就挪开，大小不变）；名字在头像上方不压头像", () => {
    expect(DRIVE_SPRITE_URLS.decor?.coach).toEqual([SCHOOL_ART.coach.portrait]);
    expect(Object.keys(SCHOOL_ART.field).sort()).toEqual(["asphalt", "bush", "car", "carLarge", "cone", "flag", "grass", "treeA", "treeB"]);
    const coach = fakeImg("coach", 512, 512);
    const pal = light();
    const moved: string[] = [];
    for (const [name, v] of PARKS) {
      const course = demoCourse(name, v);
      const d = course.decor.find((x) => x.type === "coach")!;
      for (const [w, h] of [[320, 295], [390, 506], [768, 600], [1280, 600]]) {
        const cam = fitCamera(course.view, w, h);
        const S = cam.scale;
        const { X, Y } = toCanvas(cam, w, h);
        calls = [];
        draw(fakeContext("main"), w, h, cam, frameAt(course), pal, { car: null, grass: null, asphalt: null, decor: { coach: [coach] }, version: 1 });
        const log = mainLog();
        const i = log.findIndex((c) => isImg(c, coach));
        expect(i, `${name}.${v} ${w}×${h} 画了头像`).toBeGreaterThan(-1);
        const [sx, sy, sw, sh, dx, dy, dw, dh] = (log[i].args as number[]).slice(1);
        // 取图中间 78% 的方块，画成 2R 见方
        expect(sw).toBeCloseTo(512 * COACH_AVATAR.crop, 9);
        expect(sh).toBeCloseTo(sw, 9);
        expect(sx).toBeCloseTo((512 - sw) / 2, 9);
        expect(sy).toBeCloseTo((512 - sh) / 2, 9);
        const R = Math.max(8, S * 0.6) * COACH_AVATAR.scale;
        expect(dw).toBeCloseTo(2 * R, 9);
        expect(dh).toBeCloseTo(2 * R, 9);
        const ax = dx + R;
        const ay = dy + R;
        const off = Math.hypot(ax - X(d.x!), ay - Y(d.y!));
        expect(off, `${name}.${v} ${w}×${h} 头像离原位`).toBeLessThan(4);
        if (off > 1e-9) moved.push(`${name}.${v}@${w}`);
        // 裁圆：drawImage 之前 clip，clip 的圆半径 R − 圈宽/2；再往前是纸色圆底（半径 R + 圈宽/2）
        const clipAt = log.slice(0, i).map((c) => c.fn).lastIndexOf("clip");
        expect(clipAt).toBeGreaterThan(-1);
        const clipArc = log.slice(0, clipAt).reverse().find((c) => c.fn === "arc")!;
        expect((clipArc.args as number[]).slice(0, 3).map((n, k) => n - [ax, ay, R - COACH_AVATAR.ring / 2][k]).every((e) => Math.abs(e) < 1e-9)).toBe(true);
        const discFillAt = log.slice(0, clipAt).map((c) => c.fn).lastIndexOf("fill");
        expect(log[discFillAt].st?.[0]).toBe(pal.paper);
        const discArc = log.slice(0, discFillAt).reverse().find((c) => c.fn === "arc")!;
        expect(Number(discArc.args[2])).toBeCloseTo(R + COACH_AVATAR.ring / 2, 9);
        // 最外一道细线：纸墨、35%、1px，外沿＝R＋圈宽/2＋1
        const hair = log.slice(i).find((c) => c.fn === "stroke")!;
        expect(hair.st?.slice(1, 4)).toEqual([pal.paperInk, 0.35, 1]);
        const outer = R + COACH_AVATAR.ring / 2 + 1;
        // 离每条计分线（按画出来的线宽）至少 1px
        for (const l of judgeOnCanvas(course, cam, w, h)) {
          expect(segDist([ax, ay], l.a, l.b) - l.half - outer, `${name}.${v} ${w}×${h} ${l.id}`).toBeGreaterThanOrEqual(COACH_AVATAR.lineGap - 1e-6);
        }
        // 名字在头像上方，不压头像
        const name0 = log.find((c) => c.fn === "fillText" && c.args[0] === "龟教练")!;
        const lb = textBoxOf(name0);
        expect(overlap(lb, { x0: ax - outer, y0: ay - outer, x1: ax + outer, y1: ay + outer })).toBe(false);
        expect(lb.y1).toBeLessThanOrEqual(ay - outer);
      }
    }
    // 320 宽的侧方停车、倒车入库头像离远端路沿线不够 1px，挪开了（证明“挪开”真的被用到）
    expect(moved).toEqual(expect.arrayContaining(["side_park.a@320", "reverse_park.a@320"]));
  });

  it("龟教练（深色）：头像用压暗过的离屏图（和别的装饰一样 45% 路面深墨），纸色圆底也压同一层；头像加载失败退回原来的代码画法", () => {
    const coach = fakeImg("coach", 512, 512);
    const course = demoCourse("reverse_park", "a");
    const cam = fitCamera(course.view, 390, 506);
    const dark = darkPalette();
    calls = [];
    draw(fakeContext("main"), 390, 506, cam, frameAt(course), dark, { car: null, grass: null, asphalt: null, decor: { coach: [coach] }, version: 1 });
    const log = mainLog();
    expect(log.some((c) => isImg(c, coach))).toBe(false);
    const clipAt = log.map((c) => c.fn).indexOf("clip");
    const drawn = log.slice(clipAt).find((c) => c.fn === "drawImage")!;
    expect(drawn.args[0]).toBeInstanceOf(HTMLCanvasElement);
    const fills = log.slice(0, clipAt).filter((c) => c.fn === "fill").slice(-2);
    expect(fills.map((c) => [c.st?.[0], c.st?.[2]])).toEqual([[dark.paper, 1], [dark.road, SHADE.dark.decor.alpha]]);

    // 加载失败：和没有头像时一样，是原来的椭圆身子＋脑袋，名字在原来的位置（y − 1.5r）
    const made: { onerror: (() => void) | null; src: string }[] = [];
    const failed = loadDriveSprites({ decor: { coach: [SCHOOL_ART.coach.portrait] } }, () => {
      const img = { onload: null, onerror: null, src: "", naturalWidth: 0, decoding: "" };
      made.push(img);
      return img as unknown as HTMLImageElement;
    }, 1);
    expect(made.map((m) => m.src)).toEqual([SCHOOL_ART.coach.portrait]);
    made[0].onerror?.();
    calls = [];
    draw(fakeContext("main"), 390, 506, cam, frameAt(course), light(), failed);
    const fallback = serialize(mainLog());
    calls = [];
    draw(fakeContext("main"), 390, 506, cam, frameAt(course), light(), null);
    expect(fallback).toEqual(serialize(mainLog()));
    expect(fallback.some((l) => l.startsWith("ellipse("))).toBe(true);
  });

  it("龟教练的名字：头像上方落进左上角徽标框时改写到头像下方——徽标框从 0 到 160px 高，名字都不压头像", () => {
    const coach = fakeImg("coach", 512, 512);
    for (const [name, v] of [["reverse_park", "a"], ["side_park", "a"]] as const) {
      const course = demoCourse(name, v);
      const cam = fitCamera(course.view, 320, 295);
      for (let hb = 0; hb <= 160; hb += 4) {
        calls = [];
        draw(fakeContext("main"), 320, 295, cam, frameAt(course, undefined, { avoid: { w: 130, h: hb } }), light(), { car: null, grass: null, asphalt: null, decor: { coach: [coach] }, version: 1 });
        const log = mainLog();
        const img = log.find((c) => isImg(c, coach))!;
        const [dx, dy, dw] = (img.args as number[]).slice(5);
        const R = dw / 2;
        const outer = R + COACH_AVATAR.ring / 2 + 1;
        const avatar = { x0: dx + R - outer, y0: dy + R - outer, x1: dx + R + outer, y1: dy + R + outer };
        const text = log.find((c) => c.fn === "fillText" && c.args[0] === "龟教练")!;
        expect(overlap(textBoxOf(text), avatar), `${name}.${v} 徽标框高 ${hb}`).toBe(false);
      }
    }
  });

  /* ---------- 2. 场地名牌让开车 ---------- */

  it("起始区（第四批 320 截图只露“起”）：车停进起始区，名牌挪到区域外、垫纸色名牌（纸墨字 ≥ 4.5）；在车图、压线红线、刹车灯之前画，也不和车身框相交、不压判定线；车在别处时照旧写在区域中心、白字无底", () => {
    const course = demoCourse("reverse_park", "a");
    const zone = course.decor.find((d) => d.label === "起始区")!;
    const [zx, zy] = centroidOf(zone.poly!);
    const body = course.car;
    const mid = (body.wheelbase + body.front - body.rear) / 2;
    const pal = light();
    const [w, h] = [320, 295];
    const cam = fitCamera(course.view, w, h);
    const { X, Y } = toCanvas(cam, w, h);
    calls = [];
    draw(fakeContext("main"), w, h, cam, frameAt(course, { x: zx - mid, y: zy, hx: 1, hy: 0 }, { pressedLine: course.lines[0].id, brake: true }), pal, b4Sprites());
    const log = mainLog();
    const at = log.findIndex((c) => c.fn === "fillText" && c.args[0] === "起始区");
    const text = log[at];
    expect(text.st?.[0]).toBe(pal.paperInk);
    const fillAt = log.slice(0, at).map((c) => c.fn).lastIndexOf("fill");
    expect(log[fillAt].st?.[0]).toBe(pal.paper);
    const plate = pathBox(log, fillAt);
    expectBox(plate, plateBoxOf(text));
    expect(Math.hypot(Number(text.args[1]) - X(zx), Number(text.args[2]) - Y(zy))).toBeGreaterThan(10);
    expect(inside(plate, w, h)).toBe(true);
    // 车身框：按记录下来的平移、旋转和车图位置算四角，外扩 LABEL_CAR_GAP
    const carAt = log.findIndex((c) => c.fn === "drawImage" && (c.args[0] as { id?: string }).id === "car");
    const tr = log.slice(0, carAt).reverse().find((c) => c.fn === "translate")!.args.map(Number);
    const rot = Number(log.slice(0, carAt).reverse().find((c) => c.fn === "rotate")!.args[0]);
    const [lx, ly, lw, lh] = (log[carAt].args as number[]).slice(1);
    const g = LABEL_CAR_GAP;
    const local: Pt[] = [[lx - g, ly - g], [lx + lw + g, ly - g], [lx + lw + g, ly + lh + g], [lx - g, ly + lh + g]];
    const hull = local.map(([u, v]): Pt => [tr[0] + u * Math.cos(rot) - v * Math.sin(rot), tr[1] + u * Math.sin(rot) + v * Math.cos(rot)]);
    expect(polyHitsRect(hull, plate)).toBe(false);
    // 原来的位置（区域中心）确实被车盖住
    expect(polyHitsRect(hull, { x0: X(zx) - 10.5, y0: Y(zy) - 5, x1: X(zx) + 10.5, y1: Y(zy) + 5 })).toBe(true);
    // 画的先后：名牌 → 压着的线（红）→ 车图 → 刹车灯
    const redAt = log.findIndex((c) => c.fn === "stroke" && c.st?.[1] === pal.danger);
    const brakeAt = log.findIndex((c) => c.fn === "fillRect" && c.st?.[0] === pal.danger);
    expect(redAt).toBeGreaterThan(at);
    expect(carAt).toBeGreaterThan(at);
    expect(brakeAt).toBeGreaterThan(at);
    // 不压判定线（320 宽放上方会压到远端路沿线，所以放到了下方）
    for (const l of judgeOnCanvas(course, cam, w, h)) {
      expect(segHitsRect(l.a, l.b, { x0: plate.x0 - l.half, y0: plate.y0 - l.half, x1: plate.x1 + l.half, y1: plate.y1 + l.half }), l.id).toBe(false);
    }
    expect(plate.y0).toBeGreaterThan(Y(Math.min(...zone.poly!.map((p) => p[1]))));
    // 纸墨字在纸底上（浅色；深色的纸底压 25% 见第四批用例）
    expect(ratio("var(--paper-ink)", "var(--paper)", "light")).toBeGreaterThanOrEqual(4.5);

    // 对照：车在起点，名牌照旧在区域中心、白字、前面没有纸牌
    calls = [];
    draw(fakeContext("main"), w, h, cam, frameAt(course), pal, b4Sprites());
    const log2 = mainLog();
    const at2 = log2.findIndex((c) => c.fn === "fillText" && c.args[0] === "起始区");
    expect(Number(log2[at2].args[1])).toBeCloseTo(X(zx), 9);
    expect(Number(log2[at2].args[2])).toBeCloseTo(Y(zy), 9);
    expect(log2[at2].st?.[0]).toBe(pal.paint);
    expect(log2.slice(0, at2).filter((c) => c.fn === "fill").pop()?.st?.[0]).not.toBe(pal.paper);
  });

  it("名牌挪开时上、下、右、左依次试：挨着车的一侧、落进左上角徽标框的一侧都跳过", () => {
    const course = demoCourse("reverse_park", "a");
    const zone = course.decor.find((d) => d.label === "起始区")!;
    const [zx, zy] = centroidOf(zone.poly!);
    const top = Math.max(...zone.poly!.map((p) => p[1]));
    const bottom = Math.min(...zone.poly!.map((p) => p[1]));
    const mid = (course.car.wheelbase + course.car.front - course.car.rear) / 2;
    const [w, h] = [390, 506];
    const cam = fitCamera(course.view, w, h);
    const { Y } = toCanvas(cam, w, h);
    const place = (pose: Frame["pose"], avoid: Frame["avoid"] = null) => {
      calls = [];
      draw(fakeContext("main"), w, h, cam, frameAt(course, pose, { avoid }), light(), null);
      const text = mainLog().find((c) => c.fn === "fillText" && c.args[0] === "起始区")!;
      return { plate: plateBoxOf(text), plated: text.st?.[0] === light().paperInk };
    };
    // 基准：车在区域正中 → 390 宽上方放得下，放上方
    const base = place({ x: zx - mid, y: zy, hx: 1, hy: 0 });
    expect(base.plated).toBe(true);
    expect(base.plate.y1).toBeLessThan(Y(top));
    // ① 车压在区域上沿：上方挨着车 → 跳过，放到下方，且不压车
    const onTop = { x: zx - mid, y: top, hx: 1, hy: 0 };
    const p1 = place(onTop);
    expect(p1.plated).toBe(true);
    expect(p1.plate.y0).toBeGreaterThan(Y(bottom));
    expect(polyHitsRect(bodyOnCanvas(course, onTop, cam, w, h, carReach(cam.scale)), p1.plate)).toBe(false);
    // ② 徽标框盖住区域上方 → 跳过，放到下方，且不进徽标框
    const avoid = { w, h: Y(top) - 1 };
    const p2 = place({ x: zx - mid, y: zy, hx: 1, hy: 0 }, avoid);
    expect(p2.plated).toBe(true);
    expect(overlap(p2.plate, { x0: 0, y0: 0, x1: avoid.w, y1: avoid.h })).toBe(false);
    expect(p2.plate.y0).toBeGreaterThan(Y(bottom));
  });

  it("场地名牌：按标准操作逐 tick 复算（科二、弯道、科三，320 与 390 宽），名牌从不和车相交（车身外扩压线红框、车轮宽度再留 1px）；挪开时不出画布、不进徽标框、不压判定线", () => {
    const avoid = { w: 130, h: 34 };
    const hud: Rect = { x0: 0, y0: 0, x1: avoid.w, y1: avoid.h };
    const pal = light();
    const crossings: string[] = [];
    for (const name of ["reverse_park.a", "reverse_park.b", "side_park.a", "side_park.b", "curve.a", "curve.b", "route.a", "route.b.no_signals"]) {
      const c = goldenCases.find((x) => x.name === name)!;
      const course = c.course;
      const zone = course.decor.find((d) => d.type === "zone" && d.label)!;
      const zc = centroidOf(zone.poly!);
      for (const [w, h] of [[320, 295], [390, 506]]) {
        const replay = new Replay(course);
        let seen = 0;
        let moved = 0;
        for (let t = 0; t < c.ticks && replay.status === "running"; t++) {
          replay.apply(c.events.filter((e) => e.t === t), t + 1);
          const car = replay.car;
          const pose = { x: car.x, y: car.y, hx: car.hx, hy: car.hy };
          const f = frameAt(course, pose, { avoid, tick: t });
          const cam = camFor(f, w, h);
          const { X, Y } = toCanvas(cam, w, h);
          // 区域离画面很远（科三大部分时间）就不画了
          if (X(zc[0]) < -300 || X(zc[0]) > w + 300 || Y(zc[1]) < -300 || Y(zc[1]) > h + 300) continue;
          calls = [];
          draw(fakeContext("main"), w, h, cam, f, pal, null, "dynamic");
          const text = calls.find((x) => x.fn === "fillText" && x.args[0] === zone.label)!;
          const plated = text.st?.[0] === pal.paperInk;
          const box = plated ? plateBoxOf(text) : textBoxOf(text);
          if (box.x1 <= 0 || box.x0 >= w || box.y1 <= 0 || box.y0 >= h) continue;
          seen += 1;
          expect(polyHitsRect(bodyOnCanvas(course, pose, cam, w, h, carReach(cam.scale)), box), `${name} ${w}×${h} 第 ${t} tick：名牌压到车`).toBe(false);
          if (!plated) continue;
          moved += 1;
          expect(inside(box, w, h), `${name} ${w}×${h} 第 ${t} tick：名牌出画布`).toBe(true);
          expect(overlap(box, hud), `${name} ${w}×${h} 第 ${t} tick：名牌进徽标框`).toBe(false);
          for (const l of judgeOnCanvas(course, cam, w, h)) {
            if (segHitsRect(l.a, l.b, { x0: box.x0 - l.half, y0: box.y0 - l.half, x1: box.x1 + l.half, y1: box.y1 + l.half })) crossings.push(`${name} ${w}×${h} t${t} ${l.id}`);
          }
        }
        expect(seen, `${name} ${w}×${h} 看得见名牌的 tick 数`).toBeGreaterThan(0);
        expect(moved, `${name} ${w}×${h} 车开进区域、名牌挪开的 tick 数`).toBeGreaterThan(0);
      }
    }
    expect(crossings).toEqual([]);
  });

  /* ---------- 3. 科三建筑预接 UI-ASSET-010 ---------- */

  const STYLES = ["house", "barn", "farm", "post", "school", "canteen"] as const;
  const roofImgs = () => Object.fromEntries(STYLES.map((s) => [s, fakeImg(`roof-${s}`, 256, 256)])) as Record<string, CanvasImageSource>;
  const emblemImgs = () => Object.fromEntries(["farm", "post", "school", "canteen", "house"].map((s) => [s, fakeImg(`emblem-${s}`, 128, 128)])) as Record<string, CanvasImageSource>;
  const withBuildings = (roof: Record<string, CanvasImageSource>, emblem: Record<string, CanvasImageSource>): DriveSprites => ({ ...b4Sprites(), roof, emblem });

  it("科三建筑网址交付前为空；加载器按样式加载屋顶、标志（宽大于 0 才算到、version 加 1；报错的不填）", () => {
    expect(DRIVE_BUILDING_URLS).toEqual({});
    expect(DRIVE_SPRITE_URLS.buildings).toBe(DRIVE_BUILDING_URLS);
    const made: { onload: (() => void) | null; onerror: (() => void) | null; naturalWidth: number; src: string }[] = [];
    const s = loadDriveSprites({ buildings: { roof: { house: "/roof-house.webp", post: "/roof-post.webp" }, emblem: { post: "/emblem-post.webp" } } }, () => {
      const img = { onload: null, onerror: null, src: "", naturalWidth: 0, decoding: "" };
      made.push(img);
      return img as unknown as HTMLImageElement;
    }, 1);
    expect(made.map((m) => m.src)).toEqual(["/roof-house.webp", "/roof-post.webp", "/emblem-post.webp"]);
    made[0].naturalWidth = 256;
    made[0].onload?.();
    made[1].onerror?.();
    made[2].naturalWidth = 128;
    made[2].onload?.();
    expect(s.roof).toEqual({ house: made[0] });
    expect(s.emblem).toEqual({ post: made[2] });
    expect(s.version).toBe(2);
  });

  it("屋顶：纹理平铺、原点钉在世界坐标（镜头移 2 米，纹理跟着移 2 米），填进每栋建筑的多边形；只在静态层画（进离屏缓存）", () => {
    const route = demoCourse("route", "a");
    const buildings = route.decor.filter((d) => d.type === "building");
    const roof = roofImgs();
    const spr = withBuildings(roof, {});
    const pose = { x: 80, y: 2, hx: 1, hy: 0 };
    const run = (dxm: number) => {
      const base = followCamera(pose, 390, 506);
      const cam = { ...base, cx: base.cx + dxm };
      calls = [];
      draw(fakeContext("main"), 390, 506, cam, frameAt(route, pose), light(), spr);
      return { cam, log: mainLog() };
    };
    const a = run(0);
    const b = run(2);
    const S = a.cam.scale;
    for (const s of STYLES) {
      const m = (log: Call[]) => log.filter((c) => c.fn === "pattern.setTransform" && c.args[0] === roof[s]).map((c) => c.args[1] as { a: number; d: number; e: number; f: number });
      const ma = m(a.log);
      const mb = m(b.log);
      expect(ma.length, s).toBe(buildings.filter((d) => d.style === s).length);
      expect(ma[0].a).toBeCloseTo((S * ROOF_TILE_METERS) / 256, 9);
      expect(ma[0].d).toBeCloseTo((S * ROOF_TILE_METERS) / 256, 9);
      expect(ma[0].e).toBeCloseTo(toCanvas(a.cam, 390, 506).X(0), 9);
      expect(ma[0].f).toBeCloseTo(toCanvas(a.cam, 390, 506).Y(0), 9);
      expect(mb[0].e - ma[0].e).toBeCloseTo(-2 * S, 9);
      expect(mb[0].f).toBeCloseTo(ma[0].f, 9);
    }
    // 每栋一次：填色用的是这栋样式的屋顶纹理，填的路径就是这栋的多边形
    const { X, Y } = toCanvas(a.cam, 390, 506);
    const roofFills = a.log.map((c, i) => [c, i] as const).filter(([c]) => c.fn === "fill" && (c.st?.[0] as { source?: unknown } | undefined)?.source !== undefined && Object.values(roof).includes((c.st?.[0] as { source: CanvasImageSource }).source));
    expect(roofFills).toHaveLength(buildings.length);
    roofFills.forEach(([c, i], k) => {
      expect((c.st?.[0] as { source: unknown }).source).toBe(roof[buildings[k].style!]);
      const pts = pathPoints(a.log, i);
      expect(pts.length).toBe(buildings[k].poly!.length);
      pts.forEach(([x, y], j) => {
        expect(x).toBeCloseTo(X(buildings[k].poly![j][0]), 9);
        expect(y).toBeCloseTo(Y(buildings[k].poly![j][1]), 9);
      });
    });
    // 分层：动态层不碰屋顶（纹理和标志都烤进静态层）
    calls = [];
    draw(fakeContext("main"), 390, 506, a.cam, frameAt(route, pose), light(), spr, "dynamic");
    expect(mainLog().filter((c) => c.fn === "createPattern" || c.fn === "pattern.setTransform")).toEqual([]);
  });

  it("标志：只画在有名字的建筑中心、24–40px；名字挪到标志下方——三种尺寸 × 有无屋顶 × 有无徽标框（含逼它避让的框），名字都不压标志；屋顶纹理上的名字垫纸色名牌", () => {
    const route = demoCourse("route", "a");
    const named = route.decor.filter((d) => d.type === "building" && d.label);
    expect(named.map((d) => d.style).sort()).toEqual(["canteen", "farm", "post", "school"]);
    const emblem = emblemImgs();
    for (const [w, h] of [[320, 295], [390, 506], [1280, 600]]) {
      for (const withRoof of [false, true]) {
        for (const d of named) {
          const [cx, cy] = centroidOf(d.poly!);
          const cam = { cx, cy, scale: Math.min(w, h) / 40 };
          const { X, Y } = toCanvas(cam, w, h);
          const S = cam.scale;
          const e = Math.min(EMBLEM.max, Math.max(EMBLEM.min, S * EMBLEM.meters));
          expect(e).toBeGreaterThanOrEqual(24);
          expect(e).toBeLessThanOrEqual(40);
          const emblemBox = { x0: X(cx) - e / 2, y0: Y(cy) - e / 2, x1: X(cx) + e / 2, y1: Y(cy) + e / 2 };
          for (const avoid of [null, { w: 130, h: 34 }, { w, h: Y(cy) + e / 2 + 6 }]) {
            calls = [];
            draw(fakeContext("main"), w, h, cam, frameAt(route, { x: cx, y: cy - 40, hx: 1, hy: 0 }, { avoid }), light(), withBuildings(withRoof ? roofImgs() : {}, emblem));
            const log = mainLog();
            // 有名字的建筑各画一次自己样式的标志；没名字的房子（house）就算有标志图也不画
            expect(log.filter((c) => isImg(c, emblem.house))).toEqual([]);
            const draws = log.filter((c) => isImg(c, emblem[d.style!]));
            expect(draws).toHaveLength(1);
            const [x, y, ew, eh] = (draws[0].args as number[]).slice(1);
            expectBox({ x0: x, y0: y, x1: x + ew, y1: y + eh }, emblemBox);
            const text = log.find((c) => c.fn === "fillText" && c.args[0] === d.label)!;
            const plated = text.st?.[0] === light().paperInk && log[log.indexOf(text) - 1]?.fn === "fill";
            expect(plated, `${d.label} ${w}×${h} 有屋顶 ${withRoof}`).toBe(withRoof);
            const box = withRoof ? plateBoxOf(text) : textBoxOf(text);
            expect(overlap(box, emblemBox), `${d.label} ${w}×${h} 屋顶 ${withRoof} 徽标框 ${JSON.stringify(avoid)}`).toBe(false);
            expect(box.y0).toBeGreaterThanOrEqual(emblemBox.y1);
            if (withRoof) expectBox(pathBox(log, log.indexOf(text) - 1), box);
          }
        }
      }
    }
  });

  it("屋顶深色：和原来的房子一样再压 25% 路面深墨，标志在压暗之前画、一起变暗；浅色不压；屋顶上的名牌纸底同样压 25%", () => {
    const route = demoCourse("route", "a");
    const post = route.decor.find((d) => d.style === "post")!;
    const [cx, cy] = centroidOf(post.poly!);
    const roof = roofImgs();
    const emblem = emblemImgs();
    const seq = (pal: Palette) => {
      calls = [];
      draw(fakeContext("main"), 390, 506, { cx, cy, scale: 390 / 40 }, frameAt(route, { x: cx, y: cy - 40, hx: 1, hy: 0 }), pal, withBuildings(roof, emblem));
      const log = mainLog();
      const fillAt = log.findIndex((c) => c.fn === "fill" && (c.st?.[0] as { source?: unknown } | undefined)?.source === roof.post);
      const end = log.findIndex((c, i) => i > fillAt && c.fn === "stroke");
      return log.slice(fillAt, end + 1).map((c) => (c.fn === "drawImage" ? `drawImage:${(c.args[0] as { id: string }).id}` : `${c.fn}:${token(c.st?.[0])}:${token(c.st?.[2])}`));
    };
    const dark = darkPalette();
    expect(seq(dark)).toEqual([`fill:pattern:img:roof-post:${token(1)}`, "drawImage:emblem-post", `fill:${dark.road}:${token(BUILDING_DARK_ALPHA)}`, `stroke:${dark.road}:0.3500`]);
    expect(seq(light())).toEqual([`fill:pattern:img:roof-post:${token(1)}`, "drawImage:emblem-post", `stroke:pattern:img:roof-post:0.3500`]);
    // 名牌：纸底后面再压一层 25% 深墨，然后写纸墨字
    calls = [];
    draw(fakeContext("main"), 390, 506, { cx, cy, scale: 390 / 40 }, frameAt(route, { x: cx, y: cy - 40, hx: 1, hy: 0 }), dark, withBuildings(roof, emblem), "dynamic");
    const log = mainLog();
    const at = log.findIndex((c) => c.fn === "fillText" && c.args[0] === "邮局");
    expect(log.slice(at - 2, at + 1).map((c) => [c.fn, c.st?.[0], c.st?.[2]])).toEqual([["fill", dark.paper, 1], ["fill", dark.road, BUILDING_DARK_ALPHA], ["fillText", dark.paperInk, 1]]);
  });

  it("屋顶 / 标志网址都有但全部加载失败：科三每一笔和没有这些网址时一样", () => {
    const made: { onerror: (() => void) | null }[] = [];
    const urls = { buildings: { roof: Object.fromEntries(STYLES.map((s) => [s, `/roof-${s}.webp`])), emblem: { farm: "/e-farm.webp", post: "/e-post.webp", school: "/e-school.webp", canteen: "/e-canteen.webp" } } };
    const failed = loadDriveSprites(urls, () => {
      const img = { onload: null, onerror: null, src: "", naturalWidth: 0, decoding: "" };
      made.push(img);
      return img as unknown as HTMLImageElement;
    }, 1);
    expect(made).toHaveLength(10);
    for (const img of made) img.onerror?.();
    const route = demoCourse("route", "a");
    for (const pal of [light(), darkPalette()]) {
      for (const layers of ["all", "static", "dynamic"] as const) {
        const f = frameAt(route, { x: 150, y: 2, hx: 1, hy: 0 }, { avoid: { w: 130, h: 34 } });
        calls = [];
        draw(fakeContext("main"), 390, 506, camFor(f, 390, 506), f, pal, failed, layers);
        const a = serialize(mainLog());
        calls = [];
        draw(fakeContext("main"), 390, 506, camFor(f, 390, 506), f, pal, null, layers);
        expect(a).toEqual(serialize(mainLog()));
      }
    }
  });
});

/* ================= 出错说法（2026-09-24 主窗口派活）：驾校里直接显示出错原因的地方给玩家看人话 ================= */

describe("出错说法：驾校页面显示出错原因一律用 ApiError.playerMessage——路由级 404、能力没开说人话，业务 404 照用后端原话", () => {
  /** 后端真实会给的形状（web_platform/errors.py 的路由级兜底；routers/web/driving.py 的 _translate） */
  const envelope = (code: WebErrorEnvelope["error"]["code"], message: string, details: Record<string, unknown> | null): WebErrorEnvelope => ({
    error: { code, message, request_id: "req_ds_err_0001", retryable: false, details },
  });
  // 路由级 404：后端没有这条路（前后端版本对不上时），原话“没有找到这个接口。”，不带 details
  const ROUTE_404 = () => ApiError.fromEnvelope(404, envelope("NOT_FOUND", "没有找到这个接口。", null), null);
  // 业务 404：驾校唯一的业务“找不到”（session_not_found），带 details.reason，原话本来就是写给玩家的
  const BUSINESS_404 = () => ApiError.fromEnvelope(404, envelope("NOT_FOUND", "没有这场考试或练习。", { reason: "session_not_found" }), null);
  // 能力没开（驾校整体关掉）：原话带“能力”“接入”这类开发说法
  const CAPABILITY_OFF = () => ApiError.fromEnvelope(501, envelope("CAPABILITY_UNAVAILABLE", "这项能力尚未接入。", { capability: "driving.school", status: "not_implemented" }), null);
  const CASES: [string, () => ApiError, string][] = [
    ["路由级 404（不带 details）", ROUTE_404, PLAYER_ERROR_TEXT.notFound],
    ["业务 404（带 details.reason）", BUSINESS_404, "没有这场考试或练习。"],
    ["能力没开", CAPABILITY_OFF, PLAYER_ERROR_TEXT.unavailable],
  ];
  /** 演示服务的某一条换成直接报错（其余照常，考局状态共用同一份） */
  const failing = (base: DrivingSchoolService, method: keyof DrivingSchoolService, error: () => ApiError): DrivingSchoolService => ({ ...base, [method]: () => Promise.reject(error()) });
  const click = async (name: string | RegExp): Promise<void> => {
    fireEvent.click(await screen.findByRole("button", { name }));
  };
  /** 已经开始答题的科一练习 */
  const runningQuiz = async (svc: DrivingSchoolService) => {
    const s = await svc.createSession({ subject: "s1", mode: "practice", item: null }, "k:err:quiz");
    await svc.begin(s.session_id);
    return `/school/session/${s.session_id}`;
  };
  /** 答一题：单选点第一个选项，排序题点“确定这个顺序”；都不是就下一题 */
  const answerOne = async () => {
    await screen.findByRole("navigation", { name: "题目进度" });
    for (let i = 0; i < 12; i++) {
      const radios = screen.queryAllByRole("radio");
      if (radios.length) return void fireEvent.click(radios[0]);
      const order = screen.queryByRole("button", { name: "确定这个顺序" });
      if (order) return void fireEvent.click(order);
      fireEvent.click(screen.getByRole("button", { name: "下一题" }));
    }
    throw new Error("没找到能直接保存的题");
  };
  /** 翻到最后一题，“看练习结果”→“确定交卷” */
  const submitQuiz = async () => {
    await screen.findByRole("navigation", { name: "题目进度" });
    for (let i = 0; i < 30 && !screen.queryByRole("button", { name: "看练习结果" }); i++) fireEvent.click(screen.getByRole("button", { name: "下一题" }));
    await click("看练习结果");
    await click("确定交卷");
  };

  type Spot = { where: string; stage: "wish" | "enrolled" | "licensed"; method: keyof DrivingSchoolService; open: (svc: DrivingSchoolService) => Promise<string>; act: () => Promise<void> };
  const SPOTS: Spot[] = [
    { where: "SchoolHomePage：报名", stage: "wish", method: "enroll", open: async () => "/school", act: () => click(/报名爪爪驾校/) },
    { where: "SubjectPage：约正式考试 → 去考场", stage: "enrolled", method: "createSession", open: async () => "/school/subject/s1", act: async () => { await click("约首次考试"); await click("去考场"); } },
    { where: "SubjectPage：开始练习", stage: "enrolled", method: "createSession", open: async () => "/school/subject/s1", act: () => click("做一套练习题") },
    { where: "SubjectPage：驾校状态取不到", stage: "enrolled", method: "status", open: async () => "/school/subject/s1", act: async () => undefined },
    {
      where: "SessionPage：准备页点开始",
      stage: "enrolled",
      method: "begin",
      open: async (svc) => `/school/session/${(await svc.createSession({ subject: "s1", mode: "practice", item: null }, "k:err:begin")).session_id}`,
      act: () => click("开始练习"),
    },
    { where: "SessionPage：退出对话框里结束练习", stage: "enrolled", method: "abandon", open: runningQuiz, act: async () => { await click("结束"); await click("结束练习"); } },
    { where: "QuizRunner：保存答案", stage: "enrolled", method: "answer", open: runningQuiz, act: answerOne },
    { where: "QuizRunner：交卷", stage: "enrolled", method: "submit", open: runningQuiz, act: submitQuiz },
    { where: "CeremonyPage：开始领证", stage: "licensed", method: "ceremony", open: async () => "/school/ceremony", act: () => click("开始领证") },
  ];

  for (const spot of SPOTS) {
    it(`${spot.where}（${spot.method} 报错）`, async () => {
      for (const [kind, error, expected] of CASES) {
        const base = createFixtureDrivingService({ stage: spot.stage, latency: 0 });
        const path = await spot.open(base);
        renderApp(path, failing(base, spot.method, error));
        await spot.act();
        // 出错的那一行（.ds-error，role=alert）写的就是给玩家的这一句
        await waitFor(() => expect([...document.querySelectorAll(".ds-error")].map((n) => n.textContent), `${spot.where} · ${kind}`).toContain(expected));
        for (const node of document.querySelectorAll(".ds-error")) {
          expect(node.getAttribute("role")).toBe("alert");
          expect(node.textContent, `${spot.where} · ${kind}`).not.toMatch(/接口|能力|接入/);
        }
        const page = document.body.textContent ?? "";
        expect(page, `${spot.where} · ${kind}`).not.toContain("没有找到这个接口");
        expect(page, `${spot.where} · ${kind}`).not.toContain("这项能力尚未接入");
        cleanup();
      }
    });
  }

  it("DriveRunner：上传被后端以 platform_fault 作废时显示后端写给玩家的原话（这一处保留 message：能走到这里的错误 playerMessage 与 message 一字不差）；路由级 404 不作废、不显示原话，走重新同步", async () => {
    const PLATFORM_FAULT = () => ApiError.fromEnvelope(409, envelope("CONFLICT", "考局出现异常，已作废，不计次。", { reason: "platform_fault" }), null);
    expect(PLATFORM_FAULT().playerMessage).toBe(PLATFORM_FAULT().message);
    const course = demoCourse("reverse_park", "a");
    for (const [error, voids] of [[PLATFORM_FAULT, true], [ROUTE_404, false]] as const) {
      const voidedWith: string[] = [];
      let reloads = 0;
      const backend: DriveBackend = {
        upload: () => Promise.reject(error()),
        pause: async () => ({}),
        reload: async () => {
          reloads += 1;
          throw new Error("取不到服务器记录");
        },
      };
      runner({ items: [item(course)], practice: true, backend, onVoid: (m: string) => voidedWith.push(m) });
      fireEvent.click(screen.getByRole("button", { name: "开始" }));
      key("keyDown", "ArrowUp");
      pump(120, () => voidedWith.length > 0 || reloads > 0);
      await waitFor(() => expect(voidedWith.length + reloads).toBeGreaterThan(0));
      key("keyUp", "ArrowUp");
      if (voids) {
        expect(voidedWith).toEqual(["考局出现异常，已作废，不计次。"]);
      } else {
        expect(voidedWith).toEqual([]);
        expect(reloads).toBeGreaterThan(0);
        expect(document.body.textContent).not.toContain("没有找到这个接口");
      }
      cleanup();
    }
  });

  it("成绩单“下一步”那句（ResultPage 的 next.message）不是出错原话，是后端 grading.next_step 写给玩家的五句之一，保留原样（演示服务同一套）", async () => {
    const svc = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
    const s = await svc.createSession({ subject: "s1", mode: "practice", item: null }, "k:err:next");
    await svc.begin(s.session_id);
    const settled = await svc.submit(s.session_id);
    expect(settled.result?.next?.message).toBe("练习不计成绩，想练多少次都可以。");
    renderApp(`/school/result/${s.session_id}`, svc);
    expect(await screen.findByText("练习不计成绩，想练多少次都可以。")).toBeTruthy();
  });
});

/* ================= 准备页出错显示（2026-09-24 主窗口批准，只改 SessionPage） ================= */

describe("准备页：“开始”“不练了”没成功时，那一句写在各自按钮下面（在准备页里、有页边距），role=alert，出错后滚进视野", () => {
  const envelope = (code: WebErrorEnvelope["error"]["code"], message: string, details: Record<string, unknown> | null): WebErrorEnvelope => ({
    error: { code, message, request_id: "req_ds_prep_0001", retryable: false, details },
  });
  // 路由级 404（不带 details）→ 人话；业务 404（sessions.require 的 session_not_found，开始和放弃都会遇到）→ 后端原话
  const CASES: [string, () => ApiError, string][] = [
    ["路由级 404", () => ApiError.fromEnvelope(404, envelope("NOT_FOUND", "没有找到这个接口。", null), null), PLAYER_ERROR_TEXT.notFound],
    ["业务 404", () => ApiError.fromEnvelope(404, envelope("NOT_FOUND", "没有这场考试或练习。", { reason: "session_not_found" }), null), "没有这场考试或练习。"],
  ];
  const SPOTS: [string, "begin" | "abandon", string][] = [
    ["开始练习", "begin", "开始练习"],
    ["不练了", "abandon", "不练了"],
  ];
  for (const [what, method, buttonName] of SPOTS) {
    it(`点“${what}”没成功（${method} 报错）`, async () => {
      // jsdom 没有布局、没有 scrollIntoView：换成只记录“把谁滚进了视野”
      const scrolled: { el: Element; arg: unknown }[] = [];
      const proto = HTMLElement.prototype as unknown as { scrollIntoView?: (arg?: unknown) => void };
      const had = proto.scrollIntoView;
      proto.scrollIntoView = function (this: Element, arg?: unknown) {
        scrolled.push({ el: this, arg });
      };
      try {
        for (const [kind, error, expected] of CASES) {
          scrolled.length = 0;
          const base = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
          const s = await base.createSession({ subject: "s1", mode: "practice", item: null }, `k:prep:${method}`);
          renderApp(`/school/session/${s.session_id}`, { ...base, [method]: () => Promise.reject(error()) });
          const button = await screen.findByRole("button", { name: buttonName });
          await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
          fireEvent.click(button);
          const line = await screen.findByText(expected);
          const where = `${what} · ${kind}`;
          expect(line.tagName, where).toBe("P");
          expect(line.getAttribute("role"), where).toBe("alert");
          expect(line.classList.contains("ds-error"), where).toBe(true);
          // 在准备页里（有页边距），紧跟在这颗按钮后面
          expect(line.closest(".ds-prepare"), where).toBeTruthy();
          expect(button.nextElementSibling, where).toBe(line);
          // 页面上没有落在准备页外面的出错行
          expect([...document.querySelectorAll(".ds-error")].every((n) => n.closest(".ds-prepare")), where).toBe(true);
          // 出错后把这一行滚进视野（矮屏上按钮常在首屏最下面）
          expect(scrolled.some((x) => x.el === line && (x.arg as { block?: string } | undefined)?.block === "nearest"), where).toBe(true);
          expect(document.body.textContent, where).not.toContain("没有找到这个接口");
          cleanup();
        }
      } finally {
        proto.scrollIntoView = had;
      }
    });
  }
});
