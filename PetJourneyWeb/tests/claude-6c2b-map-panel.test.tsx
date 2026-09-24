/**
 * claude-6c2b · 地图主状态面板（分身任务，方案 v2.1 第 8.1 / 8.2、13 节）：
 * 1) 驾校提醒：wish 带 TA 的原话（wish_text 原文），enrolled / license_pending 按服务端进度字段说一句，
 *    已拿证、领证仪式还没做时“领证仪式在等你们”（去 /school/ceremony），none 与仪式做过之后不出现；
 *    live 与演示（驾校模块自己的 fixture 演示服务）都走；与驾校模块共用同一个查询键与缓存；
 *    驾校服务取不到（能力未接入、报错、根本不在）时面板照常、只是没有这一行；只关于当前宠物，面板点到别的宠物时不出现。
 * 2) 提醒先后与收起：信箱 > 驾校 > 系统提示；收起时只显示第一条和“还有 N 条”，点开看全部、再点收起；读屏读得到一共几条。
 * 3) 小窝标记换成 UI-ASSET-004：素材字节与交付单一致；底部中点对坐标（补偿画布底下 23px 透明边）；可点区域 ≥ 40px；无障碍名称与点击不变。
 * 4) 从小窝回地图：不带参数时不丢状态（选中的宠物、跟随、镜头中心与缩放、演示时钟接着走）；存储不可用或内容损坏时按默认；
 *    带 ?focus=<宠物 id>（小窝的“‹ 地图”“我出门啦”）时选中并对准那只、不接存下的镜头，处理完用 replace 去掉参数；只认当前家庭里的宠物。
 * 5) 朋友圈顶部不再渲染 circle.places（原“星球上的地方 · 爪爪驾校”）。
 */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, Link, MemoryRouter, RouterProvider } from "react-router";
import type { DrivingSchoolStatus, HomeSnapshot, HouseholdBrief, PostPage, SessionBrief, SessionState, SubjectStatus, WorldPetState, WorldState } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { queryKeys } from "@/shared/query/queryClient";
import { ServicesProvider } from "@/shared/services/registry";
import type { DrivingSchoolService, ServiceMap } from "@/shared/services/types";
import { HouseholdProvider } from "@/shared/session/householdContext";
import { buildSlotRegistry, Slot, SlotProvider } from "@/shared/slots/Slot";
import { slot } from "@/shared/modules/types";
import drivingModule from "@/features/driving_school/module";
import { useSchoolStatus } from "@/features/driving_school/hooks";
import { createFixtureDrivingService } from "@/features/driving_school/service";
import { CirclePage } from "@/features/social/pages";
import type { AMapNamespace } from "@/features/world_map/amapLoader";
import { demoScene, segmentStart } from "@/features/world_map/demoScript";
import { MapHomePage } from "@/features/world_map/MapHomePage";
import { HomeBackLink } from "@/features/home/HomeScene";
import { HOME_MARKER_ART, HOME_MARKER_SIZE, HomeMarkerView, homeMarkerShift } from "@/features/world_map/markers";
import { acceptedFocus, mapFocusHref } from "@/features/world_map/mapFocus";
import { mapSessionScope, readMapSession, resumeDemoClock, writeMapSession } from "@/features/world_map/mapSession";
import { arrangeNotes, NOTE_KINDS, type PanelNote } from "@/features/world_map/panelNotes";
import { schoolNoteContent, schoolNoteText, useSchoolNote } from "@/features/world_map/schoolNote";
import { StatusPanel } from "@/features/world_map/StatusPanel";

const mode = vi.hoisted(() => ({ env: { dataMode: "fixture" as "fixture" | "live", isDev: false, apiBase: "/api/v1/web" } }));
vi.mock("@/shared/config/env", () => mode);

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  delete window.AMap;
  FakeMap.all = [];
  window.sessionStorage.clear();
  mode.env.dataMode = "fixture";
});

/* ---------------- 驾校状态样例（形状与契约 DrivingSchoolStatus 一致） ---------------- */

const TITLES = { s1: "科目一：认识路上的规则", s2: "科目二：把小车开稳", s3: "科目三：第一次上路", s4: "科目四：遇到情况怎么办" } as const;
type SubjectId = keyof typeof TITLES;

function subject(id: SubjectId, over: Partial<SubjectStatus> = {}): SubjectStatus {
  return {
    subject: id,
    title: TITLES[id],
    theme: "",
    kind: id === "s1" || id === "s4" ? "quiz" : "drive",
    state: "locked",
    passed_at: null,
    passed_score: null,
    legacy: false,
    round_no: 1,
    attempts_used: 0,
    attempts_left: 2,
    next_attempt: "first",
    cooldown_until: null,
    unlock_hint: null,
    open_session_id: null,
    last_result: null,
    practice_count: 0,
    ...over,
  };
}

const passed = (id: SubjectId) => subject(id, { state: "passed", passed_at: "2026-09-21T00:00:00Z", passed_score: 100, attempts_left: 0, next_attempt: null });

/** 驾照（形状同契约 CredentialSummary；这里只用来表示“已经有驾照”）。 */
const LICENSE = {
  credential_id: "c-license",
  kind: "driver_license",
  label: "爪爪驾驶证",
  status: "active",
  number: "PAW-C-000001",
  issued_at: "2026-09-23T00:00:00Z",
  title: "PetSoul · 爪爪驾驶证",
  condition: "四科都通过后签发",
  private: false,
  links: [],
} as unknown as NonNullable<DrivingSchoolStatus["license"]>;

function school(over: Partial<DrivingSchoolStatus> = {}): DrivingSchoolStatus {
  return {
    stage: "enrolled",
    wish_text: null,
    enrolled_at: "2026-09-20T00:00:00Z",
    coach: { name: "龟教练·慢慢", line: "方向可以慢慢找，停车要稳稳当当。", intro: "" },
    subjects: [subject("s1", { state: "available" }), subject("s2", { unlock_hint: "先通过科目一" }), subject("s3", { unlock_hint: "先通过科目二" }), subject("s4", { unlock_hint: "先通过科目三" })],
    open_session: null,
    license: null,
    voucher_available: false,
    ceremony_done: false,
    temperament: "steady",
    rules_version: "v1",
    server_time: "2026-09-24T10:00:00Z",
    ...over,
  };
}

/** 科目一已过、科目二是正在学的那一门。 */
const learningS2 = (over: Partial<SubjectStatus>, extra: Partial<DrivingSchoolStatus> = {}) =>
  school({ subjects: [passed("s1"), subject("s2", over), subject("s3", { unlock_hint: "先通过科目二" }), subject("s4", { unlock_hint: "先通过科目三" })], ...extra });

/* 后端 web_credentials_wiring.wish_text 的真实句式（地点取样例）。 */
const WISH = "坐车的时候我一直盯着司机看……我也想学开车，以后换我开车载你去海边！";

describe("驾校提醒的文字：只取服务端字段", () => {
  it("wish：带上 TA 的原话（wish_text 原文，一字不改）；没有原话就只说想学", () => {
    expect(schoolNoteText(school({ stage: "wish", wish_text: WISH, enrolled_at: null }))).toBe(`TA 说想学开车：“${WISH}”`);
    expect(schoolNoteText(school({ stage: "wish", wish_text: null, enrolled_at: null }))).toBe("TA 说想学开车");
  });

  it("enrolled：第一门没过的科目 + 它的服务端状态（可约考 / 可约补考 / 没考完 / 等到几号）", () => {
    expect(schoolNoteText(school())).toBe("驾校 · 科目一可以约考了");
    expect(schoolNoteText(learningS2({ state: "available" }))).toBe("驾校 · 科目二可以约考了");
    expect(schoolNoteText(learningS2({ state: "available", next_attempt: "retake", attempts_used: 1, attempts_left: 1 }))).toBe("驾校 · 科目二可以约补考了");
    expect(schoolNoteText(learningS2({ state: "in_exam" }))).toBe("驾校 · 科目二的考试还没考完");
    // 截止时间取 cooldown_until（UTC 正午，东西 11 区内都是 9 月 30 日）。
    expect(schoolNoteText(learningS2({ state: "cooldown", attempts_used: 2, attempts_left: 0, next_attempt: null, cooldown_until: "2026-09-30T12:00:00Z" }))).toMatch(/^驾校 · 科目二 9月30日 \d{2}:\d{2} 后可以再约考$/);
  });

  it("有未结束的正式考试时先说它；科目名取服务端标题冒号前的部分，不在前端另存", () => {
    const open: SessionBrief = { session_id: "x-1", subject: "s2", mode: "formal", item: null, attempt_kind: "first", state: "running", passed: null, score: null, created_at: "2026-09-24T09:00:00Z", settled_at: null };
    expect(schoolNoteText(learningS2({ state: "in_exam", open_session_id: "x-1" }, { open_session: open }))).toBe("驾校 · 科目二的考试还没考完");
    const renamed = school({ subjects: [subject("s1", { state: "available", title: "科目壹：规则小课堂" }), subject("s2"), subject("s3"), subject("s4")] });
    expect(schoolNoteText(renamed)).toBe("驾校 · 科目壹可以约考了");
  });

  it("license_pending（四科已过、驾照签发中）如实说正在签发；none 不出现；字段不够不编", () => {
    const pending = school({ stage: "license_pending", subjects: [passed("s1"), passed("s2"), passed("s3"), passed("s4")] });
    expect(schoolNoteContent(pending)).toEqual({ text: "驾校 · 四科都过了，驾照正在签发", to: "/school" });
    expect(schoolNoteText(school({ stage: "none", enrolled_at: null }))).toBeNull();
    expect(schoolNoteText(school({ subjects: [] }))).toBeNull();
    expect(schoolNoteText(learningS2({ state: "cooldown", cooldown_until: null }))).toBeNull();
    expect(schoolNoteText(learningS2({ state: "cooldown", cooldown_until: "不是时间" }))).toBeNull();
  });

  it("已拿证、领证仪式还没做：“领证仪式在等你们”，去驾校自己的仪式入口；做过就不再出现；没有驾照不替 TA 说", () => {
    const licensed = (over: Partial<DrivingSchoolStatus>) => school({ stage: "licensed", subjects: [passed("s1"), passed("s2"), passed("s3"), passed("s4")], license: LICENSE, voucher_available: true, ...over });
    expect(schoolNoteContent(licensed({ ceremony_done: false }))).toEqual({ text: "驾校 · 领证仪式在等你们", to: "/school/ceremony" });
    expect(schoolNoteContent(licensed({ ceremony_done: true }))).toBeNull();
    expect(schoolNoteContent(licensed({ ceremony_done: false, license: null }))).toBeNull();
    // 其余阶段都去驾校总览
    expect(schoolNoteContent(school({ stage: "wish", wish_text: WISH, enrolled_at: null }))?.to).toBe("/school");
    expect(schoolNoteContent(school())?.to).toBe("/school");
  });

  it("驾校模块的演示服务：wish 用它给的原话、enrolled 说科目一可以约考、licensed（仪式没做）说仪式在等；none 与仪式做过之后不出现", async () => {
    const status = (stage?: "wish" | "enrolled" | "licensed") => createFixtureDrivingService({ stage, latency: 0 }).status();
    const wish = await status("wish");
    expect(wish.wish_text).toBeTruthy();
    expect(schoolNoteText(wish)).toBe(`TA 说想学开车：“${wish.wish_text}”`);
    expect(schoolNoteText(await status("enrolled"))).toBe("驾校 · 科目一可以约考了");
    expect(schoolNoteText(await status())).toBeNull();
    const licensed = createFixtureDrivingService({ stage: "licensed", latency: 0 });
    expect(schoolNoteText(await licensed.status())).toBe("驾校 · 领证仪式在等你们");
    await licensed.ceremony();
    expect(schoolNoteText(await licensed.status())).toBeNull();
  });
});

/* ---------------- 渲染工具 ---------------- */

function stubMapConfig(available: boolean) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      if (available && String(input).endsWith("/map/config")) {
        return Response.json({ provider: "amap", available: true, js_key: "test-only", service_host: "/_AMapService", style: null, style_dark: null, overseas_tiles: false, unavailable_reason: null });
      }
      return new Response("", { status: 404 });
    }),
  );
}

/** 只放行给定的服务；读到别的服务就抛错（包括驾校服务没给时）。 */
function strictServices(provided: Record<string, unknown>): ServiceMap {
  return new Proxy(provided as unknown as ServiceMap, {
    get: (target, key) => {
      if (typeof key === "string" && key in target) return (target as unknown as Record<string, unknown>)[key];
      throw new Error(`unexpected service ${String(key)}`);
    },
  });
}

/** home：小窝这一页放什么。默认是一个普通的 /map 链接（相当于底栏、深链进地图）；对准 TA 的用例放真的 HomeBackLink。 */
function renderRoutes(services: ServiceMap, path = "/map", home: ReactNode = <Link to="/map">回到地图</Link>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [
      { path: "/map", element: <MapHomePage /> },
      { path: "/home", element: home },
      { path: "/school", element: <p>驾校总览</p> },
      { path: "/school/ceremony", element: <p>领证仪式</p> },
    ],
    { initialEntries: [path] },
  );
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={services}>
        <RouterProvider router={router} />
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return { router, client };
}

/** 演示（fixture）：家庭上下文不请求家庭列表；驾校用驾校模块自己的演示服务（或测试给的替身）。 */
function demoServices(driving?: Partial<DrivingSchoolService>): ServiceMap {
  const households = { list: () => Promise.reject(new Error("fixture 不应请求家庭列表")) };
  return strictServices(driving ? { households, driving } : { households });
}

const panelOf = (name: RegExp | string) => screen.findByRole("region", { name });

/* ---------------- 高德替身：只记录镜头与覆盖物，标记内容挂进容器（与真实高德一样在页面里） ---------------- */

class FakeMarker {
  content: HTMLElement;
  constructor(options: Record<string, unknown>) {
    this.content = options.content as HTMLElement;
  }
  setPosition() {}
  setzIndex() {}
  show() {}
  hide() {}
}

class FakeShape {
  setPath() {}
  setCenter() {}
  setRadius() {}
  show() {}
  hide() {}
}

class FakeMap {
  static all: FakeMap[] = [];
  zoom: number;
  center: [number, number];
  destroyed = false;
  calls: string[] = [];
  private handlers = new Map<string, Array<() => void>>();
  constructor(
    public container: HTMLElement,
    public options: Record<string, unknown>,
  ) {
    this.zoom = options.zoom as number;
    this.center = options.center as [number, number];
    FakeMap.all.push(this);
  }
  add(overlay: unknown) {
    if (overlay instanceof FakeMarker) this.container.appendChild(overlay.content);
  }
  remove(overlay: unknown) {
    if (overlay instanceof FakeMarker) overlay.content.remove();
  }
  destroy() {
    this.destroyed = true;
  }
  on(event: string, handler: () => void) {
    this.handlers.set(event, [...(this.handlers.get(event) ?? []), handler]);
  }
  emit(event: string) {
    for (const handler of this.handlers.get(event) ?? []) handler();
  }
  setZoomAndCenter(zoom: number, center: [number, number]) {
    this.calls.push(`setZoomAndCenter:${zoom}`);
    this.zoom = zoom;
    this.center = center;
    this.emit("moveend");
  }
  panTo(center: [number, number]) {
    this.calls.push("panTo");
    this.center = center;
    this.emit("moveend");
  }
  getZoom() {
    return this.zoom;
  }
  getCenter() {
    return { lng: this.center[0], lat: this.center[1] };
  }
  getResolution() {
    return 1;
  }
  setFitView() {}
  setMapStyle() {}
}

function installFakeAmap() {
  window.AMap = { Map: FakeMap, Marker: FakeMarker, Polyline: FakeShape, Circle: FakeShape, Pixel: class {} } as unknown as AMapNamespace;
}

async function mapNumber(n: number): Promise<FakeMap> {
  await waitFor(() => expect(FakeMap.all.length).toBeGreaterThanOrEqual(n));
  return FakeMap.all[n - 1];
}

/** 用户拖动并停在别处（高德先发 dragstart，停下后发 moveend）。 */
function userMoves(map: FakeMap, zoom: number, center: [number, number]) {
  act(() => {
    map.emit("dragstart");
    map.zoom = zoom;
    map.center = center;
    map.emit("moveend");
  });
}

/* ---------------- live：会话、两只宠物的家、W1 世界状态 ---------------- */

const HOME_POINT = { lat: 24.441642, lng: 118.112039 };

function w1Pet(petId: string, name: string, relation: "mine" | "household"): WorldPetState {
  return {
    pet_id: petId,
    name,
    species: "cat",
    avatar_url: null,
    relation,
    home: { center: HOME_POINT, precision_m: 900, label: "环岛路附近的海边" },
    leg: null,
    position: { ...HOME_POINT, basis: "home_area", precision_m: 900 },
    version: 1,
    activity: { kind: "home", phase: "home", pose: "idle", title: "在小窝", doing: null, place: null, since: null, until: null, job: null, journey_id: null, visit_id: null },
  };
}

const household = {
  household_id: "hh-1",
  name: "我们的家",
  role: "admin",
  home_activated: true,
  pets: [
    { pet_id: "p-1", name: "栗子", species: "cat", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-20T00:00:00Z", added_by_you: true },
    { pet_id: "p-2", name: "豆包", species: "cat", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-21T00:00:00Z", added_by_you: true },
  ],
} as unknown as HouseholdBrief;

const signedIn = { authenticated: true, user: { user_id: "u-1" }, csrf_required: false, expires_at: null, onboarding: { step: "active" } } as unknown as SessionState;

/** extraPets：W1 里多给的宠物（例如在地图上、但不在当前家庭名单里的）。 */
function liveServices(driving: Partial<DrivingSchoolService>, options: { unread?: number; catchingUp?: boolean; extraPets?: WorldPetState[] } = {}): ServiceMap {
  const state: WorldState = { server_time: new Date().toISOString(), coord_system: "wgs84", cache_seconds: 15, pets: [w1Pet("p-1", "栗子", "mine"), w1Pet("p-2", "豆包", "household"), ...(options.extraPets ?? [])] };
  const home = { unread: { messages: options.unread ?? 0 }, catching_up: options.catchingUp ?? false } as unknown as HomeSnapshot;
  return strictServices({
    session: { current: async () => signedIn },
    households: { list: async () => [household] },
    world: { state: async (_petId?: string, _signal?: AbortSignal) => state, home: async () => home },
    driving,
  });
}

const followButton = () => screen.getByRole("button", { name: "定位 TA" });

/* ---------------- 1. 面板上的驾校提醒 ---------------- */

describe("地图主状态面板的驾校提醒（演示：驾校模块的演示服务）", () => {
  it("TA 想学开车：面板多一行，带 TA 的原话，点它去 /school", async () => {
    stubMapConfig(false);
    const driving = createFixtureDrivingService({ stage: "wish", latency: 0 });
    const { wish_text } = await driving.status();
    const { router } = renderRoutes(demoServices(driving));
    const panel = await panelOf(/此刻$/);
    // 第 1 步追加：愿望那一行用宠物的名字（演示里是团子），拿不到名字才说“TA”。
    const link = await within(panel).findByRole("link", { name: /^团子说想学开车/ });
    expect(link.textContent).toBe(`团子说想学开车：“${wish_text}”`);
    expect(link.getAttribute("href")).toBe("/school");
    fireEvent.click(link);
    await waitFor(() => expect(router.state.location.pathname).toBe("/school"));
  });

  it("学车中：按四科状态说一句进度（演示的起点是科目一可以约考）", async () => {
    stubMapConfig(false);
    renderRoutes(demoServices(createFixtureDrivingService({ stage: "enrolled", latency: 0 })));
    const panel = await panelOf(/此刻$/);
    expect((await within(panel).findByRole("link", { name: "驾校 · 科目一可以约考了" })).getAttribute("href")).toBe("/school");
  });

  it("已拿证、领证仪式还没做：面板多一行“领证仪式在等你们”，点它去驾校的仪式入口（那一页打开不会自己领证）", async () => {
    stubMapConfig(false);
    const { router } = renderRoutes(demoServices(createFixtureDrivingService({ stage: "licensed", latency: 0 })));
    const panel = await panelOf(/此刻$/);
    const link = await within(panel).findByRole("link", { name: "驾校 · 领证仪式在等你们" });
    expect(link.getAttribute("href")).toBe("/school/ceremony");
    fireEvent.click(link);
    await waitFor(() => expect(router.state.location.pathname).toBe("/school/ceremony"));
  });

  it.each([
    ["none（TA 没表达、主人也没去点）", undefined, false],
    ["licensed 且领证仪式已经做过", "licensed" as const, true],
  ])("%s：状态读回来了，也不出现这一行", async (_label, stage, ceremonyDone) => {
    stubMapConfig(false);
    const base = createFixtureDrivingService({ stage, latency: 0 });
    if (ceremonyDone) await base.ceremony();
    const status = vi.fn(base.status);
    const { client } = renderRoutes(demoServices({ ...base, status }));
    const panel = await panelOf(/此刻$/);
    await waitFor(() => expect(client.getQueryState(queryKeys.drivingStatus)?.status).toBe("success"));
    await new Promise((r) => setTimeout(r, 30));
    expect(status).toHaveBeenCalledTimes(1);
    expect(within(panel).queryByRole("link", { name: /驾校|想学开车/ })).toBeNull();
    expect(panel.querySelector("h2")?.textContent).toMatch(/团子/);
  });

  it.each([
    ["能力未接入", { status: () => Promise.reject(ApiError.capability("driving.status")) } as Partial<DrivingSchoolService>],
    ["服务端报错", { status: () => Promise.reject(new ApiError({ kind: "http", status: 500, code: "INTERNAL_ERROR", message: "boom", details: {} })) } as Partial<DrivingSchoolService>],
    ["根本不在（一读 driving 就抛错）", undefined],
  ])("驾校服务%s：面板照常，只是没有这一行", async (_label, driving) => {
    stubMapConfig(false);
    const { client } = renderRoutes(demoServices(driving));
    const panel = await panelOf(/此刻$/);
    await waitFor(() => expect(client.getQueryState(queryKeys.drivingStatus)?.status).toBe("error"));
    await new Promise((r) => setTimeout(r, 30));
    expect(within(panel).queryByRole("link", { name: /驾校|想学开车/ })).toBeNull();
    expect(panel.querySelector("h2")?.textContent).toMatch(/团子/);
    expect(within(panel).getByRole("link", { name: /捎句话/ })).toBeTruthy();
  });
});

describe("与驾校模块共用同一个查询键与缓存", () => {
  function Both() {
    const note = useSchoolNote();
    const own = useSchoolStatus();
    return <p data-testid="both">{`${note?.text ?? "-"}|${own.data?.stage ?? "-"}`}</p>;
  }

  function renderBoth(userId: string | null, services: ServiceMap) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <ServicesProvider services={services}>
          <MemoryRouter>
            <HouseholdProvider userId={userId}>
              <Both />
            </HouseholdProvider>
          </MemoryRouter>
        </ServicesProvider>
      </QueryClientProvider>,
    );
    return client;
  }

  it("fixture：键是 queryKeys.drivingStatus，两边只读一次", async () => {
    const status = vi.fn(async () => school({ stage: "wish", wish_text: WISH }));
    const client = renderBoth(null, strictServices({ households: {}, driving: { status } }));
    await waitFor(() => expect(screen.getByTestId("both").textContent).toBe(`TA 说想学开车：“${WISH}”|wish`));
    expect(status).toHaveBeenCalledTimes(1);
    expect(client.getQueryCache().findAll({ queryKey: ["driving", "status"] }).map((q) => q.queryKey)).toEqual([queryKeys.drivingStatus]);
  });

  it("live：键是 queryKeys.drivingStatusFor(用户, 当前宠物)，按当前宠物读、两边只读一次", async () => {
    mode.env.dataMode = "live";
    const status = vi.fn<DrivingSchoolService["status"]>(async () => learningS2({ state: "available" }));
    const client = renderBoth("u-1", strictServices({ households: { list: async () => [household] }, driving: { status } }));
    await waitFor(() => expect(screen.getByTestId("both").textContent).toBe("驾校 · 科目二可以约考了|enrolled"));
    expect(status).toHaveBeenCalledTimes(1);
    expect(status.mock.calls[0]).toEqual(["p-1", expect.anything()]);
    expect(client.getQueryCache().findAll({ queryKey: ["driving", "status"] }).map((q) => q.queryKey)).toEqual([queryKeys.drivingStatusFor("u-1", "p-1")]);
  });
});

describe("live：驾校提醒只关于当前宠物", () => {
  it("面板是当前宠物时出现；点地图上的另一只，面板换人，这一行不跟过去", async () => {
    mode.env.dataMode = "live";
    stubMapConfig(true);
    installFakeAmap();
    const status = vi.fn<DrivingSchoolService["status"]>(async () => learningS2({ state: "available" }));
    renderRoutes(liveServices({ status }));
    const mine = await panelOf("栗子此刻");
    expect((await within(mine).findByRole("link", { name: "驾校 · 科目二可以约考了" })).getAttribute("href")).toBe("/school");
    expect(status.mock.calls[0][0]).toBe("p-1");
    fireEvent.click(await screen.findByRole("button", { name: /^豆包在/ }));
    const other = await panelOf("豆包此刻");
    expect(within(other).queryByRole("link", { name: /驾校/ })).toBeNull();
  });
});

/* ---------------- 提醒的先后与收起 ---------------- */

const DEMO_PET_ID = "fx-pet-001";
const NOTES: PanelNote[] = [
  { id: "catching-up", kind: "system", text: "世界正在更新，工钱和来信稍后出现。" },
  { id: "school", kind: "school", text: "驾校 · 科目一可以约考了", to: "/school", petId: DEMO_PET_ID },
  { id: "mail", kind: "mail", text: "TA 发来 2 条消息", to: "/communicator" },
];
const itemsOf = (group: HTMLElement) => within(group).getAllByRole("listitem").map((li) => li.textContent);

describe("提醒的先后与收起（方案 3.2：收起时只显示最重要的一条）", () => {
  it("先后：TA 的来信 > 驾校 > 系统提示，与传进来的先后无关；同一种保持原来的先后；只关于别的宠物的、空的都去掉", () => {
    // 第 1 步：一起听、这趟旅途插在来信之后、驾校之前（主窗口定的最终顺序）。
    expect(NOTE_KINDS).toEqual(["mail", "listen", "trip", "school", "wish", "system"]);
    expect(arrangeNotes(NOTES, DEMO_PET_ID).map((n) => n.id)).toEqual(["mail", "school", "catching-up"]);
    expect(arrangeNotes([...NOTES].reverse(), DEMO_PET_ID).map((n) => n.id)).toEqual(["mail", "school", "catching-up"]);
    expect(arrangeNotes(NOTES, "someone-else").map((n) => n.id)).toEqual(["mail", "catching-up"]);
    const twoMails: PanelNote[] = [{ id: "m-2", kind: "mail", text: "b" }, { id: "s", kind: "system", text: "s" }, { id: "m-1", kind: "mail", text: "a" }];
    expect(arrangeNotes([null, ...twoMails, undefined], null).map((n) => n.id)).toEqual(["m-2", "m-1", "s"]);
  });

  it("收起时只显示第一条，后面跟“还有 N 条”；点开看全部、再点收起；读屏从分组名读到一共几条", () => {
    const pet = demoScene(segmentStart(0) + 60_000, 0).pets[0];
    render(
      <MemoryRouter>
        <StatusPanel pet={pet} nowMs={segmentStart(0) + 60_000} notes={arrangeNotes(NOTES, pet.petId)} onLocate={() => undefined} />
      </MemoryRouter>,
    );
    const group = screen.getByRole("group", { name: "提醒，共 3 条" });
    const list = within(group).getByRole("list");
    expect(itemsOf(group)).toEqual(["TA 发来 2 条消息"]);
    const more = within(group).getByRole("button", { name: "还有 2 条" });
    expect(more.getAttribute("aria-expanded")).toBe("false");
    expect(more.getAttribute("aria-controls")).toBe(list.id);
    fireEvent.click(more);
    expect(itemsOf(group)).toEqual(["TA 发来 2 条消息", "驾校 · 科目一可以约考了", "世界正在更新，工钱和来信稍后出现。"]);
    const less = within(group).getByRole("button", { name: "收起" });
    expect(less.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(less);
    expect(itemsOf(group)).toEqual(["TA 发来 2 条消息"]);
    expect(within(group).getByRole("button", { name: "还有 2 条" })).toBeTruthy();
  });

  it("只有一条时没有“还有 N 条”；没有提醒时整块都不出现", () => {
    const pet = demoScene(segmentStart(0) + 60_000, 0).pets[0];
    const { rerender } = render(
      <MemoryRouter>
        <StatusPanel pet={pet} nowMs={0} notes={arrangeNotes([NOTES[1]], pet.petId)} onLocate={() => undefined} />
      </MemoryRouter>,
    );
    const group = screen.getByRole("group", { name: "提醒，共 1 条" });
    expect(itemsOf(group)).toEqual(["驾校 · 科目一可以约考了"]);
    expect(within(group).queryByRole("button")).toBeNull();
    rerender(
      <MemoryRouter>
        <StatusPanel pet={pet} nowMs={0} notes={[]} onLocate={() => undefined} />
      </MemoryRouter>,
    );
    expect(screen.queryByRole("group", { name: /^提醒/ })).toBeNull();
  });

  it("live：来信、驾校、世界正在更新同时有——收起时先说来信，点开按 信箱 > 驾校 > 系统提示 排", async () => {
    mode.env.dataMode = "live";
    stubMapConfig(false);
    renderRoutes(liveServices({ status: async () => learningS2({ state: "available" }) }, { unread: 2, catchingUp: true }));
    const panel = await panelOf("栗子此刻");
    const group = await within(panel).findByRole("group", { name: "提醒，共 3 条" });
    expect(itemsOf(group)).toEqual(["TA 发来 2 条消息"]);
    fireEvent.click(within(group).getByRole("button", { name: "还有 2 条" }));
    expect(itemsOf(group)).toEqual(["TA 发来 2 条消息", "驾校 · 科目二可以约考了", "世界正在更新，工钱和来信稍后出现。"]);
  });
});

/* ---------------- 2. 小窝标记（UI-ASSET-004） ---------------- */

describe("小窝标记：UI-ASSET-004 v1", () => {
  it("素材就是交付单那一张：192×192 带透明通道的 WebP，SHA-256 与交付单一致", () => {
    const file = resolve(dirname(fileURLToPath(import.meta.url)), "..", "public", HOME_MARKER_ART.src.slice(1));
    const bytes = readFileSync(file);
    expect(createHash("sha256").update(bytes).digest("hex")).toBe("d91172615741cc72dd5940d1db97fc7479646de2db206bb725b5146540b0b078");
    expect(bytes.toString("ascii", 0, 4) + bytes.toString("ascii", 8, 16)).toBe("RIFFWEBPVP8X");
    expect(bytes[20] & 0x10).toBe(0x10);
    expect([1 + bytes.readUIntLE(24, 3), 1 + bytes.readUIntLE(27, 3)]).toEqual([HOME_MARKER_ART.canvas, HOME_MARKER_ART.canvas]);
  });

  it("锚点：小房子底部中点（画布 x=96、y=169）对坐标——整张画布下移 23/192，而不是拿画布底边对", () => {
    expect(HOME_MARKER_ART).toMatchObject({ canvas: 192, baseX: 96, baseY: 169 });
    expect(HOME_MARKER_SIZE).toBeGreaterThanOrEqual(40);
    expect(HOME_MARKER_SIZE).toBeLessThanOrEqual(44);
    expect(homeMarkerShift(44)).toEqual({ x: 0, y: 5.27 });
    expect(homeMarkerShift(36)).toEqual({ x: 0, y: 4.31 });
  });

  it("按钮本身就是可点区域；图只是装饰；无障碍名称与点击不变，点击不冒泡到地图", () => {
    const onOpen = vi.fn();
    const onMap = vi.fn();
    render(
      <div onClick={onMap}>
        <HomeMarkerView petName="团子" occupied={false} onOpen={onOpen} />
      </div>,
    );
    const button = screen.getByRole("button", { name: "团子的小窝，TA 出门了，进去看看" });
    const art = button.querySelector("img")!;
    expect(art.getAttribute("src")).toBe("/ui-assets/UI-ASSET-004/v1/map-home-marker.webp");
    expect(art.getAttribute("alt")).toBe("");
    expect([art.getAttribute("width"), art.getAttribute("height")]).toEqual(["44", "44"]);
    expect(button.style.getPropertyValue("--home-size")).toBe("44px");
    expect(button.style.getPropertyValue("--home-dx")).toBe("0px");
    expect(button.style.getPropertyValue("--home-dy")).toBe("5.27px");
    expect(button.className).toBe("ps-wmap-home");
    fireEvent.click(button);
    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(onMap).not.toHaveBeenCalled();
    cleanup();
    render(<HomeMarkerView petName="团子" occupied onOpen={onOpen} />);
    expect(screen.getByRole("button", { name: "团子的小窝，TA 在家，进去看看" }).className).toBe("ps-wmap-home is-occupied");
  });

  it("画在地图上：演示里小窝标记用这张图，点它进小窝", async () => {
    stubMapConfig(true);
    installFakeAmap();
    const { router } = renderRoutes(demoServices(createFixtureDrivingService({ latency: 0 })));
    const home = await screen.findByRole("button", { name: /^团子的小窝，TA (在家|出门了)，进去看看$/ });
    expect(home.querySelector("img")?.getAttribute("src")).toBe(HOME_MARKER_ART.src);
    fireEvent.click(home);
    await waitFor(() => expect(router.state.location.pathname).toBe("/home"));
  });
});

/* ---------------- 3. 从小窝回地图不丢状态 ---------------- */

describe("从小窝回地图：接着上次看", () => {
  it("演示：镜头中心与缩放、跟随开关、倍速、暂停和演示时钟都接着上次（不再从全国视图推近、不从头开始）", async () => {
    stubMapConfig(true);
    installFakeAmap();
    renderRoutes(demoServices(createFixtureDrivingService({ latency: 0 })));
    await screen.findByText("演示剧本 · 不是真实数据");
    const first = await mapNumber(1);
    expect(first.options).toMatchObject({ zoom: 4, center: [104.2, 35.9] });
    await waitFor(() => expect(first.calls).toContain("setZoomAndCenter:16"));
    fireEvent.click(screen.getByRole("button", { name: "240×" }));
    fireEvent.click(screen.getByRole("button", { name: "暂停" }));
    userMoves(first, 14.5, [118.1, 24.44]);
    expect(screen.getByRole("button", { name: "定位 TA" }).getAttribute("aria-pressed")).toBe("false");
    const before = readMapSession("demo").demo!;
    expect(before).toMatchObject({ speed: 240, paused: true });
    const headline = (await panelOf(/此刻$/)).querySelector("h2")?.textContent;

    fireEvent.click(screen.getByRole("link", { name: "进小窝" }));
    fireEvent.click(await screen.findByRole("link", { name: "回到地图" }));
    await screen.findByText("演示剧本 · 不是真实数据");
    const second = await mapNumber(2);
    expect(first.destroyed).toBe(true);
    expect(second.options).toMatchObject({ zoom: 14.5, center: [118.1, 24.44] });
    await new Promise((r) => setTimeout(r, 30));
    expect(second.calls.filter((c) => c.startsWith("setZoomAndCenter"))).toEqual([]);
    expect(screen.getByRole("button", { name: "定位 TA" }).getAttribute("aria-pressed")).toBe("false");
    expect(screen.getByRole("button", { name: "240×" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "继续" })).toBeTruthy();
    const after = readMapSession("demo").demo!;
    expect(after.dayStart).toBe(before.dayStart);
    expect(after.demoAt).toBe(before.demoAt);
    expect((await panelOf(/此刻$/)).querySelector("h2")?.textContent).toBe(headline);
  });

  it("演示：跟着 TA 时回来仍对准 TA，只是保留缩放（平移过去，不重新推近）", async () => {
    stubMapConfig(true);
    installFakeAmap();
    renderRoutes(demoServices(createFixtureDrivingService({ latency: 0 })));
    const first = await mapNumber(1);
    await waitFor(() => expect(first.calls).toContain("setZoomAndCenter:16"));
    act(() => {
      first.zoom = 15;
      first.emit("zoomend");
    });
    fireEvent.click(screen.getByRole("link", { name: "进小窝" }));
    fireEvent.click(await screen.findByRole("link", { name: "回到地图" }));
    const second = await mapNumber(2);
    expect(second.options).toMatchObject({ zoom: 15 });
    // 跟随平移沿用原有节奏（距上次平移超过 1.5 秒；挂载后第一次以页面时间原点算），所以多等一会儿。
    await waitFor(() => expect(second.calls).toContain("panTo"), { timeout: 3000 });
    expect(second.calls.filter((c) => c.startsWith("setZoomAndCenter"))).toEqual([]);
    expect(screen.getByRole("button", { name: "定位 TA" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("演示：没暂停时，离开的这段真实时间按倍速补上（同一天接着走，不从头开始）", async () => {
    const dayStart = Date.now() - 3 * 3600_000;
    const leftAt = dayStart + segmentStart(6) + 60_000;
    writeMapSession("demo", { demo: { dayStart, demoAt: leftAt, wallAt: Date.now() - 10_000, speed: 60, paused: false } });
    stubMapConfig(false);
    renderRoutes(demoServices(createFixtureDrivingService({ latency: 0 })));
    // 第 6 段是“在咖啡馆坐着”；从头开始的话会是“在小窝里睡觉”。
    expect((await panelOf(/此刻$/)).querySelector("h2")?.textContent).toBe("团子在街角的咖啡馆");
    const now = readMapSession("demo").demo!;
    expect(now.dayStart).toBe(dayStart);
    expect(now.demoAt - leftAt).toBeGreaterThanOrEqual(10_000 * 60);
  });

  it("live：点中的宠物、跟随与镜头，进小窝再回来都还在", async () => {
    mode.env.dataMode = "live";
    stubMapConfig(true);
    installFakeAmap();
    renderRoutes(liveServices({ status: async () => school({ stage: "none", enrolled_at: null }) }));
    await panelOf("栗子此刻");
    const first = await mapNumber(1);
    fireEvent.click(await screen.findByRole("button", { name: /^豆包在/ }));
    await panelOf("豆包此刻");
    userMoves(first, 13, [118.2, 24.5]);
    fireEvent.click(screen.getByRole("link", { name: "进小窝" }));
    fireEvent.click(await screen.findByRole("link", { name: "回到地图" }));
    expect(await panelOf("豆包此刻")).toBeTruthy();
    const second = await mapNumber(2);
    expect(second.options).toMatchObject({ zoom: 13, center: [118.2, 24.5] });
    expect(screen.getByRole("button", { name: "定位 TA" }).getAttribute("aria-pressed")).toBe("false");
    // 第 0b 步：左上“进小窝”按面板上那只进，回来时当前宠物已是豆包，“回来接着看”记在豆包名下。
    expect(readMapSession(mapSessionScope("u-1")).view).toEqual({ focusId: "p-2", selectedId: "p-2", following: false });
  });

  it("live：换过当前宠物（存下时的当前宠物不是这一只）就不接上次的选中与镜头，从头对准", async () => {
    mode.env.dataMode = "live";
    writeMapSession(mapSessionScope("u-1"), { view: { focusId: "p-9", selectedId: "p-2", following: false }, camera: { focusId: "p-9", center: [120, 30], zoom: 12 } });
    stubMapConfig(true);
    installFakeAmap();
    renderRoutes(liveServices({ status: async () => school({ stage: "none", enrolled_at: null }) }));
    expect(await panelOf("栗子此刻")).toBeTruthy();
    const first = await mapNumber(1);
    expect(first.options).toMatchObject({ zoom: 4, center: [104.2, 35.9] });
    await waitFor(() => expect(first.calls).toContain("setZoomAndCenter:16"));
    expect(screen.getByRole("button", { name: "定位 TA" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("存储读写都抛错（私密模式、被禁用）：地图照常，按默认跟着 TA、演示从头开始", async () => {
    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    stubMapConfig(false);
    renderRoutes(demoServices(createFixtureDrivingService({ latency: 0 })));
    expect((await panelOf(/此刻$/)).querySelector("h2")?.textContent).toMatch(/团子/);
    expect(screen.getByRole("button", { name: "定位 TA" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "60×" }).getAttribute("aria-pressed")).toBe("true");
    expect(getItem).toHaveBeenCalled();
    expect(setItem).toHaveBeenCalled();
  });

  it("存储内容损坏或不合法：坏的那一项回到默认，其余照用；按账号分开存", () => {
    window.sessionStorage.setItem("petsoul:world-map:v1:demo", "{不是 JSON");
    expect(readMapSession("demo")).toEqual({ view: null, camera: null, demo: null });
    const demo = { dayStart: 1, demoAt: 2, wallAt: 3, speed: 60, paused: true };
    window.sessionStorage.setItem("petsoul:world-map:v1:demo", JSON.stringify({ view: { focusId: null, selectedId: 7, following: true }, camera: { focusId: null, center: [500, 30], zoom: 16 }, demo }));
    expect(readMapSession("demo")).toEqual({ view: null, camera: null, demo });
    writeMapSession(mapSessionScope("u-1"), { view: { focusId: "p-1", selectedId: "p-2", following: false } });
    expect(readMapSession(mapSessionScope("u-2")).view).toBeNull();
    expect(readMapSession(mapSessionScope("u-1")).view).toEqual({ focusId: "p-1", selectedId: "p-2", following: false });
  });

  it("演示时钟补时：暂停着停在原处；没暂停按倍速补上；时间倒退不往回走", () => {
    const saved = { dayStart: 0, demoAt: 1_000, wallAt: 10_000, speed: 60, paused: false };
    expect(resumeDemoClock(saved, 12_000)).toBe(1_000 + 2_000 * 60);
    expect(resumeDemoClock({ ...saved, paused: true }, 12_000)).toBe(1_000);
    expect(resumeDemoClock(saved, 9_000)).toBe(1_000);
  });
});

/* ---------------- 从小窝回地图并对准 TA（?focus=，方案第 5 节） ---------------- */

describe("从小窝回地图并对准 TA：?focus=<宠物 id>", () => {
  const DRAGGED = { view: { focusId: null, selectedId: null, following: false }, camera: { focusId: null, center: [120, 30] as [number, number], zoom: 12 } };

  it("地址：/map?focus=<宠物 id>（编码）；不知道是哪只时就是普通的 /map；小窝的“‹ 地图”用的就是它", () => {
    expect(mapFocusHref(DEMO_PET_ID)).toBe("/map?focus=fx-pet-001");
    expect(mapFocusHref("a b/c")).toBe("/map?focus=a%20b%2Fc");
    expect(mapFocusHref(null)).toBe("/map");
    render(
      <MemoryRouter>
        <HomeBackLink petId={DEMO_PET_ID} />
        <HomeBackLink inline />
      </MemoryRouter>,
    );
    expect(screen.getAllByRole("link", { name: "回到地图" }).map((a) => a.getAttribute("href"))).toEqual(["/map?focus=fx-pet-001", "/map"]);
  });

  it("只认地图上自己家的宠物；live 还要在当前家庭的名单里；别的值一律不认", () => {
    const scene = demoScene(segmentStart(0) + 60_000, 0);
    expect(acceptedFocus(null, scene, null)).toBeNull();
    expect(acceptedFocus(DEMO_PET_ID, scene, null)).toBe(DEMO_PET_ID);
    expect(acceptedFocus("nobody", scene, null)).toBeNull();
    expect(acceptedFocus(DEMO_PET_ID, scene, new Set(["p-1"]))).toBeNull();
    expect(acceptedFocus(DEMO_PET_ID, scene, new Set([DEMO_PET_ID]))).toBe(DEMO_PET_ID);
    // 以后地图上会有别人家的公开宠物（W2）：不是自己家的，不认
    const stranger = { ...scene, pets: [{ ...scene.pets[0], relation: "public" as unknown as "mine" }] };
    expect(acceptedFocus(DEMO_PET_ID, stranger, null)).toBeNull();
  });

  it("演示：带 ?focus= 回来——选中并跟随那只、不接存下的镜头（重新对准）；处理完用 replace 去掉参数，存下的状态改成跟随", async () => {
    writeMapSession("demo", DRAGGED);
    stubMapConfig(true);
    installFakeAmap();
    const { router } = renderRoutes(demoServices(createFixtureDrivingService({ latency: 0 })), `/map?focus=${DEMO_PET_ID}`);
    const map = await mapNumber(1);
    expect(map.options).toMatchObject({ zoom: 4, center: [104.2, 35.9] });
    await waitFor(() => expect(map.calls).toContain("setZoomAndCenter:16"));
    expect(followButton().getAttribute("aria-pressed")).toBe("true");
    await waitFor(() => expect(router.state.location.search).toBe(""));
    expect(router.state.location.pathname).toBe("/map");
    expect(router.state.historyAction).toBe("REPLACE");
    expect(readMapSession("demo").view).toEqual({ focusId: null, selectedId: DEMO_PET_ID, following: true });
  });

  it("演示：?focus= 认不出（不是这个家的宠物）就不理会，照旧接上次的镜头与“不跟随”；参数同样用 replace 去掉", async () => {
    writeMapSession("demo", DRAGGED);
    stubMapConfig(true);
    installFakeAmap();
    const { router } = renderRoutes(demoServices(createFixtureDrivingService({ latency: 0 })), "/map?focus=someone-else");
    const map = await mapNumber(1);
    expect(map.options).toMatchObject({ zoom: 12, center: [120, 30] });
    expect(followButton().getAttribute("aria-pressed")).toBe("false");
    await waitFor(() => expect(router.state.location.search).toBe(""));
    expect(router.state.historyAction).toBe("REPLACE");
    await new Promise((r) => setTimeout(r, 30));
    expect(map.calls.filter((c) => c.startsWith("setZoomAndCenter"))).toEqual([]);
  });

  // 小窝“‹ 地图”两条来路（claude-6c2b 第 3 条，主窗口同意拆成两条）：有站内来路就后退，与顶栏返回同一规则；想重新对准 TA 点“定位 TA”。
  it("（a）从地图进来（真的小窝链接）：点“‹ 地图”是后退——回到原来那条 /map，历史条数不变；镜头与“不跟随”都是离开时的样子，不重新对准", async () => {
    stubMapConfig(true);
    installFakeAmap();
    const { router } = renderRoutes(demoServices(createFixtureDrivingService({ latency: 0 })), "/map", <HomeBackLink petId={DEMO_PET_ID} />);
    const first = await mapNumber(1);
    await waitFor(() => expect(first.calls).toContain("setZoomAndCenter:16"));
    userMoves(first, 13, [118.2, 24.5]);
    expect(followButton().getAttribute("aria-pressed")).toBe("false");
    const mapEntry = router.state.location.key;
    fireEvent.click(screen.getByRole("link", { name: "进小窝" }));
    const back = await screen.findByRole("link", { name: "回到地图" });
    expect(router.state.location.search).toBe("?from=map");
    const homeEntry = router.state.location.key;
    // 链接地址照旧是 /map?focus=…（新标签页打开、读屏以它为准），普通点按才是后退
    expect(back.getAttribute("href")).toBe(`/map?focus=${DEMO_PET_ID}`);
    fireEvent.click(back);
    const second = await mapNumber(2);
    expect(router.state.historyAction).toBe("POP");
    expect(router.state.location.key).toBe(mapEntry);
    expect(router.state.location.pathname + router.state.location.search).toBe("/map");
    expect(second.options).toMatchObject({ zoom: 13, center: [118.2, 24.5] });
    await new Promise((r) => setTimeout(r, 30));
    expect(second.calls.filter((c) => c.startsWith("setZoomAndCenter"))).toEqual([]);
    expect(followButton().getAttribute("aria-pressed")).toBe("false");
    // 历史条数不变：往前还是刚才那条小窝，没有多压一条 /map?focus=
    await act(async () => {
      await router.navigate(1);
    });
    expect(router.state.location.key).toBe(homeEntry);
    expect(router.state.location.search).toBe("?from=map");
  });

  it.each(["/home", "/home?from=map"])("（b）直接打开 %s（没有站内来路）：点“‹ 地图”用 replace 去 /map?focus=，历史条数不变；地图对准 TA、跟随打开；之后刷新接着跟随", async (entry) => {
    writeMapSession("demo", DRAGGED);
    stubMapConfig(true);
    installFakeAmap();
    const { router } = renderRoutes(demoServices(createFixtureDrivingService({ latency: 0 })), entry, <HomeBackLink petId={DEMO_PET_ID} />);
    const back = await screen.findByRole("link", { name: "回到地图" });
    expect(back.getAttribute("href")).toBe(`/map?focus=${DEMO_PET_ID}`);
    fireEvent.click(back);
    const map = await mapNumber(1);
    expect(router.state.historyAction).toBe("REPLACE");
    expect(map.options).toMatchObject({ zoom: 4, center: [104.2, 35.9] });
    await waitFor(() => expect(map.calls).toContain("setZoomAndCenter:16"));
    expect(followButton().getAttribute("aria-pressed")).toBe("true");
    await waitFor(() => expect(router.state.location.search).toBe(""));
    // 历史条数不变：小窝那一条被换掉了，往回退不会再回到小窝
    await act(async () => {
      await router.navigate(-1);
    });
    expect(router.state.location.pathname).toBe("/map");
    // 刷新：重新挂载、地址里没有参数，照旧接上次（这次对准 TA 之后）的状态
    cleanup();
    renderRoutes(demoServices(createFixtureDrivingService({ latency: 0 })), "/map");
    const again = await mapNumber(2);
    expect(again.options).toMatchObject({ zoom: 16 });
    expect(followButton().getAttribute("aria-pressed")).toBe("true");
  });

  it("live：?focus=<家里另一只> 选中并跟随那只；在地图上但不在当前家庭名单里的不认", async () => {
    mode.env.dataMode = "live";
    stubMapConfig(true);
    installFakeAmap();
    const none = { status: async () => school({ stage: "none", enrolled_at: null }) };
    const { router } = renderRoutes(liveServices(none), "/map?focus=p-2");
    expect(await panelOf("豆包此刻")).toBeTruthy();
    expect(followButton().getAttribute("aria-pressed")).toBe("true");
    await waitFor(() => expect(router.state.location.search).toBe(""));
    cleanup();
    window.sessionStorage.clear();
    const other = renderRoutes(liveServices(none, { extraPets: [w1Pet("p-3", "阿福", "household")] }), "/map?focus=p-3");
    expect(await panelOf("栗子此刻")).toBeTruthy();
    await waitFor(() => expect(other.router.state.location.search).toBe(""));
    expect(screen.queryByRole("region", { name: "阿福此刻" })).toBeNull();
  });

  it("live：已经在地图上又收到 ?focus=：不重新挂载，同样选中、跟随并把镜头推过去", async () => {
    mode.env.dataMode = "live";
    stubMapConfig(true);
    installFakeAmap();
    const { router } = renderRoutes(liveServices({ status: async () => school({ stage: "none", enrolled_at: null }) }));
    await panelOf("栗子此刻");
    const map = await mapNumber(1);
    await waitFor(() => expect(map.calls).toContain("setZoomAndCenter:16"));
    userMoves(map, 13, [118.2, 24.5]);
    const before = map.calls.length;
    await act(async () => {
      await router.navigate("/map?focus=p-2");
    });
    expect(await panelOf("豆包此刻")).toBeTruthy();
    await waitFor(() => expect(map.calls.slice(before)).toContain("setZoomAndCenter:16"));
    expect(followButton().getAttribute("aria-pressed")).toBe("true");
    await waitFor(() => expect(router.state.location.search).toBe(""));
    expect(FakeMap.all).toHaveLength(1);
  });
});

/* ---------------- 4. 朋友圈不再挂驾校入口 ---------------- */

describe("朋友圈顶部不再渲染 circle.places（原“星球上的地方 · 爪爪驾校”）", () => {
  // 驾校模块已不再登记 circle.places（死入口，主窗口 2026-09-24 第四批让驾校·页面分身删掉）。
  // 对照改成这里自己登记一个假的 circle.places 入口：插槽里确实有东西，页面一渲染它就会出现链接；朋友圈那条断言照旧。
  function ProbeSchoolEntry() {
    return <Link to="/school">爪爪驾校（对照用的假入口）</Link>;
  }
  function renderWithSchoolSlot(children: ReactNode) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const services = strictServices({
      social: { feed: async () => ({ items: [], next_cursor: null }) as unknown as PostPage },
      households: {},
      driving: createFixtureDrivingService({ stage: "wish", latency: 0 }),
    });
    render(
      <QueryClientProvider client={client}>
        <ServicesProvider services={services}>
          <SlotProvider registry={buildSlotRegistry([...(drivingModule.slots ?? []), slot("circle.places", "probe.school-entry", ProbeSchoolEntry)])}>
            <MemoryRouter>
              <HouseholdProvider userId={null}>{children}</HouseholdProvider>
            </MemoryRouter>
          </SlotProvider>
        </ServicesProvider>
      </QueryClientProvider>,
    );
  }

  it("对照：同一套插槽登记下，放一个 circle.places 就会出现爪爪驾校入口", async () => {
    renderWithSchoolSlot(<Slot name="circle.places" props={{}} />);
    expect((await screen.findByRole("link", { name: /爪爪驾校/ })).getAttribute("href")).toBe("/school");
  });

  it("朋友圈页面：顶栏和动态都出来了，没有爪爪驾校入口", async () => {
    renderWithSchoolSlot(<CirclePage />);
    await screen.findByText("宠物们自己的公开动态");
    await screen.findByText("还没有动态");
    expect(screen.queryByRole("link", { name: /爪爪驾校/ })).toBeNull();
  });
});
