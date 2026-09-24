/**
 * 爪爪驾校：fixture 服务按服务端同一套规则运行（解锁顺序、首次＋补考、7×24 小时冷却、只结算一次、片段连续、拿证与领证），
 * 以及页面流程（报名 → 科目页 → 开考确认写明机会与冷却 → 考局 → 成绩单；星球圈入口；体验版不连后端）。
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import golden from "./fixtures/driving-golden.json";
import type { SchoolSession, SchoolSubject } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { createApiClient } from "@/shared/api/client";
import { loadFeatureModules } from "@/app/modules";
import { buildRoutes } from "@/app/router";
import { buildServices, ServicesProvider } from "@/shared/services/registry";
import type { DrivingSchoolService, ServiceMap } from "@/shared/services/types";
import { buildSlotRegistry, SlotProvider } from "@/shared/slots/Slot";
import { createFixtureDrivingService } from "@/features/driving_school/service";
import type { Course, InputEventT } from "@/features/driving_school/sim/types";
import { DEMO_QUESTIONS } from "@/fixtures/driving";

afterEach(cleanup);
beforeAll(() => {
  // jsdom 没有 canvas：画面测试只看结构与文字
  HTMLCanvasElement.prototype.getContext = (() => null) as unknown as HTMLCanvasElement["getContext"];
});

const scripts = new Map((golden as unknown as { cases: { name: string; events: InputEventT[]; ticks: number }[] }).cases.map((c) => [c.name, c]));
const DAY = 24 * 3600 * 1000;

function clock() {
  let t = Date.parse("2026-09-22T10:00:00Z");
  return { now: () => t, advance: (ms: number) => (t += ms) };
}

async function reason(promise: Promise<unknown>): Promise<string> {
  try {
    await promise;
  } catch (e) {
    return String((e as ApiError).details?.reason);
  }
  throw new Error("expected a rejection");
}

let keySeq = 0;
const key = () => `test:${++keySeq}`;

async function takeQuiz(svc: DrivingSchoolService, subject: "s1" | "s4", correct: boolean, mode: "formal" | "practice" = "formal") {
  let s = await svc.createSession({ subject, mode, item: null }, key());
  s = await svc.begin(s.session_id);
  for (const q of DEMO_QUESTIONS[subject]) {
    const swapped = () => {
      const [a, b] = Object.keys(q.answer.matches!);
      return { [a]: q.answer.matches![b], [b]: q.answer.matches![a] };
    };
    const answer = correct
      ? q.answer
      : q.kind === "choice"
        ? { choice: q.options.find((o) => o.option_id !== q.answer.choice)!.option_id }
        : q.kind === "order"
          ? { order: [...q.answer.order!].reverse() }
          : { matches: swapped() };
    await svc.answer(s.session_id, { question_id: q.question_id, answer: { choice: answer.choice ?? null, order: answer.order ?? null, matches: answer.matches ?? null } });
  }
  return svc.submit(s.session_id);
}

/** 用后端生成的标准操作（golden）把每一项开完；scriptSuffix 可以选“闯红灯”等变体。 */
async function drive(svc: DrivingSchoolService, session: SchoolSession, scriptSuffix = ""): Promise<SchoolSession> {
  const id = session.session_id;
  for (let i = session.drive!.current_item; i < session.drive!.items.length; i++) {
    const course = session.drive!.items[i].course as unknown as Course;
    const script = scripts.get(course.course_id + scriptSuffix);
    if (!script) throw new Error(`no script for ${course.course_id}${scriptSuffix}`);
    for (let from = 0; from < script.ticks; from += 300) {
      const upto = Math.min(script.ticks, from + 300);
      const result = await svc.inputs(id, { item_index: i, from_tick: from, upto_tick: upto, events: script.events.filter((e) => e.t >= from && e.t < upto) });
      if (result.item_status !== "running") break;
    }
    const now = await svc.session(id);
    if (now.state === "settled") return now;
  }
  return svc.session(id);
}

async function timeOut(svc: DrivingSchoolService, session: SchoolSession): Promise<SchoolSession> {
  const limit = (session.drive!.items[0].course as unknown as Course).time_limit_ticks;
  for (let from = 0; from < limit; from += 900) await svc.inputs(session.session_id, { item_index: 0, from_tick: from, upto_tick: Math.min(limit, from + 900), events: [] });
  return svc.session(session.session_id);
}

async function formal(svc: DrivingSchoolService, subject: SchoolSubject) {
  const s = await svc.createSession({ subject, mode: "formal", item: null }, key());
  return svc.begin(s.session_id);
}

describe("driving school rules (fixture mirrors the server)", () => {
  it("unlocks in order, gives a first attempt plus one retake, then cools down 7×24h from the second failure", async () => {
    const c = clock();
    const svc = createFixtureDrivingService({ stage: "wish", now: c.now, latency: 0 });
    expect(await reason(svc.createSession({ subject: "s1", mode: "formal", item: null }, key()))).toBe("not_enrolled");
    let status = await svc.enroll();
    expect(status.stage).toBe("enrolled");
    expect(status.subjects.map((s) => s.state)).toEqual(["available", "locked", "locked", "locked"]);
    expect(await reason(svc.createSession({ subject: "s2", mode: "formal", item: null }, key()))).toBe("locked");

    const s1 = await takeQuiz(svc, "s1", true);
    expect(s1.result).toMatchObject({ passed: true, score: 30, max_score: 30, next: { kind: "passed" } });
    status = await svc.status();
    expect(status.subjects[1]).toMatchObject({ state: "available", attempts_left: 2, next_attempt: "first" });

    // 首次：开考后放弃，需要二次确认，计为不通过
    const first = await formal(svc, "s2");
    expect(first.attempt_kind).toBe("first");
    expect(await reason(svc.abandon(first.session_id, false))).toBe("confirm_required");
    const abandoned = await svc.abandon(first.session_id, true);
    expect(abandoned.result).toMatchObject({ passed: false, fatal: { kind: "abandoned" }, next: { kind: "retake", attempts_left: 1 } });

    // 补考：换一个场地变体；超时即不通过
    const retake = await formal(svc, "s2");
    expect(retake.attempt_kind).toBe("retake");
    expect((retake.drive!.items[0].course as unknown as Course).variant).toBe("b");
    const failed = await timeOut(svc, retake);
    expect(failed.result).toMatchObject({ passed: false, fatal: { kind: "timeout" }, next: { kind: "cooldown", attempts_left: 0 } });
    expect(Date.parse(failed.result!.next!.cooldown_until!)).toBe(Date.parse(failed.settled_at!) + 7 * DAY);

    status = await svc.status();
    expect(status.subjects[1]).toMatchObject({ state: "cooldown", attempts_left: 0 });
    expect(await reason(svc.createSession({ subject: "s2", mode: "formal", item: null }, key()))).toBe("cooldown");
    const practice = await svc.createSession({ subject: "s2", mode: "practice", item: "reverse_park" }, key());
    expect(practice.mode).toBe("practice");

    c.advance(7 * DAY - 3600 * 1000);
    expect((await svc.status()).subjects[1].state).toBe("cooldown");
    c.advance(3600 * 1000 + 1000);
    expect((await svc.status()).subjects[1]).toMatchObject({ state: "available", round_no: 2, next_attempt: "first", attempts_left: 2 });
    // 已通过的科目一直保留
    expect((await svc.status()).subjects[0].state).toBe("passed");
    expect(await reason(svc.createSession({ subject: "s1", mode: "formal", item: null }, key()))).toBe("already_passed");
  });

  it("settles only once, keeps chunks contiguous and treats identical resends as no-ops", async () => {
    const svc = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
    const quiz = await takeQuiz(svc, "s1", false);
    const again = await svc.submit(quiz.session_id);
    expect(again.result).toEqual(quiz.result);
    expect(quiz.result).toMatchObject({ passed: false, score: 0, next: { kind: "retake" } });

    let s = await svc.createSession({ subject: "s2", mode: "practice", item: "reverse_park" }, key());
    s = await svc.begin(s.session_id);
    const script = scripts.get("reverse_park.a")!;
    const chunk = { item_index: 0, from_tick: 0, upto_tick: 97, events: script.events.filter((e) => e.t < 97) };
    const first = await svc.inputs(s.session_id, chunk);
    const resend = await svc.inputs(s.session_id, chunk);
    expect(resend.committed_tick).toBe(first.committed_tick);
    expect(resend.snapshot).toEqual(first.snapshot);
    expect(await reason(svc.inputs(s.session_id, { ...chunk, from_tick: 200, upto_tick: 230, events: [] }))).toBe("gap");
    expect(await reason(svc.inputs(s.session_id, { ...chunk, events: [{ t: 3, c: "s", v: 4 }] }))).toBe("resync");
    expect(await reason(svc.inputs(s.session_id, { item_index: 0, from_tick: 97, upto_tick: 2000, events: [] }))).toBe("invalid_input");
    expect(await reason(svc.inputs(s.session_id, { item_index: 0, from_tick: 97, upto_tick: 120, events: [{ t: 99, c: "s", v: 40 }] }))).toBe("invalid_input");
  });

  it("auto-brakes on a red line and ends the run (practice shows the same judgement)", async () => {
    const svc = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
    const s = await svc.begin((await svc.createSession({ subject: "s3", mode: "practice", item: null }, key())).session_id);
    const done = await drive(svc, s, ".red_light");
    expect(done.state).toBe("settled");
    expect(done.result).toMatchObject({ passed: false, fatal: { kind: "red_light" }, next: { kind: "practice" } });
    const snap = done.drive!.items[0].snapshot as { car: number[] };
    expect(snap.car[4]).toBe(0);
  });

  it("four passes issue the license and a car voucher; the ceremony happens once", async () => {
    const svc = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
    expect(await reason(svc.ceremony())).toBe("not_licensed");
    await takeQuiz(svc, "s1", true);
    const s2 = await drive(svc, await formal(svc, "s2"));
    expect(s2.result).toMatchObject({ passed: true, score: 100 });
    expect(s2.result!.items.map((i) => i.status)).toEqual(["done", "done", "done"]);
    const s3 = await drive(svc, await formal(svc, "s3"));
    expect(s3.result).toMatchObject({ passed: true, score: 100 });
    const s4 = await takeQuiz(svc, "s4", true);
    expect(s4.result!.next).toMatchObject({ kind: "licensed" });
    const status = await svc.status();
    expect(status).toMatchObject({ stage: "licensed", voucher_available: true, ceremony_done: false });
    expect(status.license).toMatchObject({ kind: "driver_license", status: "active" });
    const first = await svc.ceremony();
    expect(first).toMatchObject({ first_time: true, memento: { kind: "license_photo", tradable: false, bound_to_pet: true } });
    expect(first.pet_says).toContain("换我载你去看世界");
    const replay = await svc.ceremony();
    expect(replay.first_time).toBe(false);
    expect((await svc.status()).ceremony_done).toBe(true);
  });
});

describe("driving school fixture export for contract validation", () => {
  it("exports fixture responses so the backend Pydantic models can check them (npm run contract:check)", async () => {
    const svc = createFixtureDrivingService({ stage: "wish", latency: 0 });
    const entries: { name: string; type: string; value: unknown }[] = [];
    const add = (name: string, type: string, value: unknown) => entries.push({ name: `driving.${name}`, type, value });
    add("status.wish", "DrivingSchoolStatus", await svc.status());
    add("curriculum", "SchoolCurriculum", await svc.curriculum());
    await svc.enroll();
    const practice = await svc.begin((await svc.createSession({ subject: "s1", mode: "practice", item: null }, key())).session_id);
    const q = DEMO_QUESTIONS.s1[0];
    add("answer.practice", "AnswerResult", await svc.answer(practice.session_id, { question_id: q.question_id, answer: { choice: q.answer.choice!, order: null, matches: null } }));
    add("session.quiz.practice", "SchoolSession", await svc.session(practice.session_id));
    add("session.quiz.settled", "SchoolSession", await takeQuiz(svc, "s1", true));
    const running = await formal(svc, "s2");
    add("session.drive.running", "SchoolSession", running);
    const script = scripts.get("reverse_park.a")!;
    add("inputs", "InputResult", await svc.inputs(running.session_id, { item_index: 0, from_tick: 0, upto_tick: 97, events: script.events.filter((e) => e.t < 97) }));
    add("session.drive.settled", "SchoolSession", await svc.abandon(running.session_id, true));
    for (const [i, brief] of (await svc.history()).entries()) add(`history.${i}`, "SessionBrief", brief);
    const licensed = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
    await takeQuiz(licensed, "s1", true);
    await drive2(licensed);
    await takeQuiz(licensed, "s4", true);
    add("status.licensed", "DrivingSchoolStatus", await licensed.status());
    add("ceremony", "CeremonyResult", await licensed.ceremony());
    const out = resolve(dirname(fileURLToPath(import.meta.url)), "..", ".runtime", "contract-examples");
    mkdirSync(out, { recursive: true });
    writeFileSync(resolve(out, "driving-school.json"), JSON.stringify(entries, null, 1), "utf-8");
    expect(entries.length).toBeGreaterThan(10);

    async function drive2(s: DrivingSchoolService) {
      await drive(s, await formal(s, "s2"));
      await drive(s, await formal(s, "s3"));
    }
  });
});

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

describe("driving school pages", () => {
  it("registers the school routes, with the exam, ceremony and trial as full-screen pages", () => {
    const routes = buildRoutes(loadFeatureModules());
    const [tabbed, bare] = routes;
    const tabbedPaths = (tabbed.children ?? []).map((c) => c.path);
    const barePaths = (bare.children ?? []).map((c) => c.path);
    expect(tabbedPaths).toEqual(expect.arrayContaining(["school", "school/subject/:subject", "school/result/:sessionId"]));
    expect(barePaths).toEqual(expect.arrayContaining(["school/session/:sessionId", "school/ceremony", "school/try"]));
  });

  it("owner enrolls the pet, reads the rules and books an exam only after a confirmation that states the retake and cooldown rules", async () => {
    const svc = createFixtureDrivingService({ stage: "wish", latency: 0 });
    const router = renderApp("/school", svc);
    fireEvent.click(await screen.findByRole("button", { name: /报名爪爪驾校/ }));
    await screen.findByText(/四个科目 · 已通过 0\/4/);
    fireEvent.click(screen.getByRole("link", { name: /认识路上的规则/ }));
    await screen.findByRole("heading", { name: "认识路上的规则" });
    expect(screen.getByText(/答错一题/)).toBeTruthy();
    fireEvent.click(await screen.findByRole("button", { name: "约首次考试" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/每轮有首次考试和一次补考/)).toBeTruthy();
    expect(within(dialog).getByText(/要等 7 天/)).toBeTruthy();
    expect(within(dialog).getByText(/点“开始考试”才算一次考试/)).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "去考场" }));
    await waitFor(() => expect(router.state.location.pathname).toMatch(/^\/school\/session\//));
    // 考局还没开始：不计次
    expect((await svc.status()).subjects[0].attempts_used).toBe(0);
    const start = await screen.findByRole("button", { name: "开始考试" });
    await waitFor(() => expect((start as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(start);
    await screen.findByRole("heading", { name: DEMO_QUESTIONS.s1[0].prompt });
    // 正式考试不给对错提示
    fireEvent.click(screen.getByRole("radio", { name: DEMO_QUESTIONS.s1[0].options[0].label }));
    await screen.findByText(/已保存。交卷前可以随时改/);
    expect(screen.queryByText("答对了")).toBeNull();
    expect(screen.queryByText("这题再想想")).toBeNull();
  });

  it("practice explains each answer right away", async () => {
    const svc = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
    const s = await svc.createSession({ subject: "s1", mode: "practice", item: null }, key());
    renderApp(`/school/session/${s.session_id}`, svc);
    const start = await screen.findByRole("button", { name: "开始练习" });
    await waitFor(() => expect((start as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(start);
    const q = DEMO_QUESTIONS.s1[0];
    fireEvent.click(await screen.findByRole("radio", { name: q.options[1].label }));
    await screen.findByText("这题再想想");
    expect(screen.getByText(q.explanation)).toBeTruthy();
  });

  it("leaving a formal exam keeps it open; abandoning needs a second confirmation and counts as a failure", async () => {
    const svc = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
    const s = await formal(svc, "s1");
    const router = renderApp(`/school/session/${s.session_id}`, svc);
    fireEvent.click(await screen.findByRole("button", { name: "离开" }));
    fireEvent.click(await screen.findByRole("button", { name: "放弃这场考试" }));
    expect(screen.getByText(/计为本轮首次考试没通过/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "确定放弃" }));
    await waitFor(() => expect(router.state.location.pathname).toBe(`/school/result/${s.session_id}`));
    await screen.findByText(/中途放弃/);
    expect(await screen.findByText(/还有一次补考机会/)).toBeTruthy();
  });

  it("shows the drive exam layout with steering, pedals and gears", async () => {
    const svc = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
    const s = await svc.begin((await svc.createSession({ subject: "s2", mode: "practice", item: "reverse_park" }, key())).session_id);
    renderApp(`/school/session/${s.session_id}`, svc);
    await screen.findByRole("slider", { name: "方向盘" });
    expect(screen.getByRole("button", { name: "刹车" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "油门" })).toBeTruthy();
    expect(screen.getByRole("group", { name: "挡位" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "按钮" }));
    expect(await screen.findByRole("button", { name: /向左转/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: "开始" })).toBeTruthy();
  });

  it("home shows no school card, not even once the pet is enrolled (map-first plan v2.1 §8.2: progress lives in the map panel)", async () => {
    renderApp("/home", createFixtureDrivingService({ latency: 0 }));
    await screen.findAllByText(/团子/);
    await new Promise((r) => setTimeout(r, 300));
    expect(screen.queryByRole("link", { name: /爪爪驾校/ })).toBeNull();
    cleanup();
    renderApp("/home", createFixtureDrivingService({ stage: "enrolled", latency: 0 }));
    // 方案 8.2：学车进度挪到地图主状态面板，小窝不再放驾校卡。
    await screen.findAllByText(/团子/);
    await new Promise((r) => setTimeout(r, 300));
    expect(screen.queryByRole("link", { name: /爪爪驾校/ })).toBeNull();
  });

  it("the friends circle no longer lists the school (map-first plan v2.1 §8.1), and the trial runs without the backend", async () => {
    const svc = createFixtureDrivingService({ stage: "wish", latency: 0 });
    renderApp("/circle", svc);
    // 方案 8.1：驾校入口不再挂在朋友圈（原“星球”标签）顶部；TA 想学开车时出现在地图主状态面板，主人主动的入口在证件卡包。
    await screen.findByText("宠物们自己的公开动态");
    expect(screen.queryByRole("link", { name: /爪爪驾校/ })).toBeNull();
    cleanup();
    const offline: DrivingSchoolService = new Proxy({} as DrivingSchoolService, {
      get: () => () => Promise.reject(new Error("体验版不应该调用驾校服务")),
    });
    renderApp("/school/try", offline);
    expect(await screen.findByRole("button", { name: "开始" })).toBeTruthy();
    expect(screen.getByText("体验版 · 不计成绩")).toBeTruthy();
  });
});
