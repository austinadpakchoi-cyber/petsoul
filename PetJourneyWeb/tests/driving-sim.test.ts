/**
 * 爪爪驾校：前后端复算一致性。
 * - 样例 tests/fixtures/driving-golden.json 由后端 scripts/gen_driving_fixtures.py 生成（Python 复算结果）；
 * - 这里用 TypeScript 版复算同样的操作，按同样的分段逐位比对车辆状态、判定事件与最终快照；
 * - 另测本地引擎记录的操作能被独立复算出同一结果，以及上传器的顺序、重发与拒绝。
 */
import { describe, expect, it } from "vitest";
import golden from "./fixtures/driving-golden.json";
import type { InputChunk, InputResult } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { DriveEngine } from "@/features/driving_school/drive/engine";
import { Uploader } from "@/features/driving_school/drive/uploader";
import { lightPhase, Replay } from "@/features/driving_school/sim/replay";
import type { Course, InputEventT, Snapshot } from "@/features/driving_school/sim/types";
import { demoCourse } from "@/fixtures/driving";

interface GoldenCase {
  name: string;
  course: Course;
  events: InputEventT[];
  ticks: number;
  marks: { tick: number; car: number[] }[];
  final: Snapshot;
}

const cases = (golden as unknown as { cases: GoldenCase[] }).cases;

function sameBits(actual: number[], expected: number[], where: string) {
  expect(actual.length, where).toBe(expected.length);
  actual.forEach((value, i) => {
    if (!Object.is(value, expected[i])) throw new Error(`${where}[${i}]: ${value} !== ${expected[i]}`);
  });
}

describe("driving replay matches the server bit for bit", () => {
  it("has the golden cases", () => {
    expect(cases.length).toBeGreaterThanOrEqual(9);
  });

  for (const c of cases) {
    it(c.name, () => {
      const replay = new Replay(c.course);
      let mark = 0;
      for (let start = 0; start < c.ticks; start += 97) {
        const upto = Math.min(c.ticks, start + 97);
        replay.apply(
          c.events.filter((e) => e.t >= start && e.t < upto),
          upto,
        );
        const car = replay.car;
        const expected = c.marks[mark++];
        expect(replay.tick, `${c.name} tick`).toBe(expected.tick);
        sameBits([car.x, car.y, car.hx, car.hy, car.v, car.s, car.gear], expected.car, `${c.name}@${expected.tick}`);
        if (replay.status !== "running") break;
      }
      expect(mark).toBe(c.marks.length);
      const snap = replay.snapshot();
      sameBits(snap.car, c.final.car, `${c.name} final car`);
      sameBits(snap.front, c.final.front, `${c.name} final front`);
      expect(snap).toEqual(c.final);
      // 快照可以 JSON 往返后继续复算（续考）
      const resumed = new Replay(c.course, JSON.parse(JSON.stringify(snap)) as Snapshot);
      expect(resumed.snapshot()).toEqual(snap);
    });
  }

  it("covers red lines, missing signals and finishing", () => {
    const outcomes = Object.fromEntries(cases.map((c) => [c.name, c.final]));
    expect(outcomes["route.a"].status).toBe("done");
    expect(outcomes["route.a"].events.filter((e) => e.p > 0)).toEqual([]);
    expect(outcomes["route.a.red_light"].fail).toBe("red_light");
    expect(outcomes["route.b.no_signals"].events.map((e) => e.k)).toEqual(expect.arrayContaining(["start_no_signal", "turn_no_signal", "invite_opened"]));
    expect(outcomes["reverse_park.a"].status).toBe("done");
  });

  it("uses only server-provided constants for the traffic light", () => {
    const route = demoCourse("route", "a").route!;
    const [green, yellow] = route.light.cycle;
    const start = (route.light.cycle.reduce((a, b) => a + b, 0) - route.light.offset) % route.light.cycle.reduce((a, b) => a + b, 0);
    expect(lightPhase(route, start)).toBe("green");
    expect(lightPhase(route, start + green)).toBe("yellow");
    expect(lightPhase(route, start + green + yellow)).toBe("red");
  });
});

describe("local drive engine", () => {
  it("records only changes, and an independent replay of the chunks reproduces the same state", () => {
    const course = demoCourse("reverse_park", "a");
    const engine = new DriveEngine(course);
    const chunks: InputChunk[] = [];
    engine.setThrottle(true);
    for (let i = 0; i < 40; i++) engine.advance();
    engine.setSteer(5);
    engine.setSteer(7); // 同一 tick 内多次改变只记最后的值
    for (let i = 0; i < 40; i++) engine.advance();
    chunks.push(engine.takeChunk(0)!);
    engine.setThrottle(false);
    engine.setBrake(true);
    for (let i = 0; i < 60; i++) engine.advance();
    expect(engine.shift(-1)).toBe(true);
    engine.setBrake(false);
    engine.setThrottle(true);
    for (let i = 0; i < 50; i++) engine.advance();
    chunks.push(engine.takeChunk(0)!);
    expect(engine.takeChunk(0)).toBeNull();

    expect(chunks[0]).toMatchObject({ item_index: 0, from_tick: 0, upto_tick: 80 });
    expect(chunks[1]).toMatchObject({ from_tick: 80, upto_tick: 190 });
    expect(chunks[0].events).toEqual([
      { t: 0, c: "t", v: 1 },
      { t: 40, c: "s", v: 7 },
    ]);
    expect(engine.replay.car.gear).toBe(-1);

    const server = new Replay(course);
    for (const chunk of chunks) server.apply(chunk.events as InputEventT[], chunk.upto_tick);
    expect(DriveEngine.agrees(engine.replay.snapshot(), server.snapshot())).toBe(true);
    expect(server.snapshot()).toEqual(engine.replay.snapshot());
  });

  it("refuses to shift while moving, like the server", () => {
    const engine = new DriveEngine(demoCourse("reverse_park", "a"));
    engine.setThrottle(true);
    for (let i = 0; i < 10; i++) engine.advance();
    expect(engine.replay.car.v).toBeGreaterThan(0);
    expect(engine.shift(-1)).toBe(false);
  });

  it("resumes from a server snapshot with the pedals released", () => {
    const course = demoCourse("side_park", "a");
    const first = new DriveEngine(course);
    first.setThrottle(true);
    for (let i = 0; i < 30; i++) first.advance();
    const resumed = new DriveEngine(course, first.replay.snapshot());
    expect(resumed.tick).toBe(30);
    expect(resumed.throttle).toBe(false);
    resumed.advance();
    expect(resumed.takeChunk(0)!.events).toEqual([{ t: 30, c: "t", v: 0 }]);
  });
});

describe("chunk uploader", () => {
  const chunk = (from: number, upto: number): InputChunk => ({ item_index: 0, from_tick: from, upto_tick: upto, events: [] });
  const ok = (c: InputChunk) => ({ committed_tick: c.upto_tick }) as unknown as InputResult;
  const flush = () => new Promise((r) => setTimeout(r, 0));

  it("sends chunks strictly in order and resends the same chunk after a network error", async () => {
    const sent: number[] = [];
    let fail = true;
    const results: number[] = [];
    const offline: boolean[] = [];
    const uploader = new Uploader(
      async (c) => {
        sent.push(c.from_tick);
        if (c.from_tick === 30 && fail) {
          fail = false;
          throw new ApiError({ kind: "network", code: "NETWORK_ERROR", message: "offline", retryable: true });
        }
        return ok(c);
      },
      { result: (_r, c) => results.push(c.upto_tick), rejected: () => undefined, offline: (v) => offline.push(v) },
    );
    uploader.push(chunk(0, 30));
    uploader.push(chunk(30, 60));
    uploader.push(chunk(60, 90));
    await flush();
    await flush();
    expect(offline).toEqual([true]);
    uploader.retryNow();
    for (let i = 0; i < 5; i++) await flush();
    expect(sent).toEqual([0, 30, 30, 60]);
    expect(results).toEqual([30, 60, 90]);
    expect(offline).toEqual([true, false]);
    expect(uploader.idle).toBe(true);
  });

  it("keeps sending queued chunks after the page leaves (detach), without calling back", async () => {
    const sent: number[] = [];
    const callbacks: string[] = [];
    let release: () => void = () => undefined;
    const gate = new Promise<void>((r) => (release = r));
    const uploader = new Uploader(
      async (c) => {
        sent.push(c.from_tick);
        if (c.from_tick === 0) await gate;
        return ok(c);
      },
      { result: () => callbacks.push("result"), rejected: () => callbacks.push("rejected"), offline: () => callbacks.push("offline") },
    );
    uploader.push(chunk(0, 30));
    uploader.push(chunk(30, 42)); // 暂停时交出的最后一段，还在排队
    uploader.detach();
    release();
    for (let i = 0; i < 5; i++) await flush();
    expect(sent).toEqual([0, 30]);
    expect(callbacks).toEqual([]);
    expect(uploader.idle).toBe(true);
  });

  it("drops the queue and reports a rejection (409) for resync", async () => {
    const rejected: string[] = [];
    const uploader = new Uploader(
      async () => {
        throw new ApiError({ kind: "http", status: 409, code: "CONFLICT", message: "gap", details: { reason: "gap" } });
      },
      { result: () => undefined, rejected: (e) => rejected.push(String(e.details?.reason)), offline: () => undefined },
    );
    uploader.push(chunk(0, 30));
    uploader.push(chunk(30, 60));
    for (let i = 0; i < 3; i++) await flush();
    expect(rejected).toEqual(["gap"]);
    expect(uploader.idle).toBe(true);
  });
});
