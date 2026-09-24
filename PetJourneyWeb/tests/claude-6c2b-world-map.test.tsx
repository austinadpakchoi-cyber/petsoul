/**
 * claude-6c2b · 地图首页原型（/map）：坐标换算与后端同式；世界状态只认事实（去打工 ≠ 在打工、没几何不画线、没出过门不猜家）；
 * 主面板文案；演示剧本循环；地图配置取不到时退回示意底且状态照常。
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import type { WorldPetState, WorldState } from "@/shared/contracts";
import { ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { outOfChina, wgs84ToGcj02 } from "@/features/world_map/coords";
import { alongRoute, legProgress, positionAt } from "@/features/world_map/model";
import { petPortraitUrl } from "@/features/pets/PetPortrait";
import { focusPetId, sceneFromWorldState, worldPetFromState } from "@/features/world_map/worldState";
import { panelCopy } from "@/features/world_map/copy";
import { DEMO_DAY, demoDayLength, demoScene, segmentAt, segmentStart } from "@/features/world_map/demoScript";
import { fetchMapConfig } from "@/features/world_map/mapConfig";
import { MapHomePage } from "@/features/world_map/MapHomePage";
import { createFixtureDrivingService } from "@/features/driving_school/service";

vi.mock("@/shared/config/env", () => ({ env: { dataMode: "fixture", isDev: false, apiBase: "/api/v1/web" } }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("坐标：与后端 app/web_providers/coords.py 同一公式", () => {
  // 参考值由后端函数算出（2026-09-24）。
  it.each([
    [24.4366, 118.1135, 24.4339577, 118.118459],
    [22.2819, 114.1581, 22.279181, 114.1630951],
    [39.9087, 116.3975, 39.9101035, 116.4037436],
  ])("WGS-84 (%f, %f) → GCJ-02", (lat, lng, glat, glng) => {
    const g = wgs84ToGcj02(lat, lng);
    expect(g.lat).toBeCloseTo(glat, 6);
    expect(g.lng).toBeCloseTo(glng, 6);
  });

  it("境外坐标原样返回", () => {
    expect(outOfChina(35.681, 139.767)).toBe(true);
    expect(wgs84ToGcj02(35.681, 139.767)).toEqual({ lat: 35.681, lng: 139.767 });
  });
});

describe("沿路线按时间推进", () => {
  const route = [
    { lat: 24.44, lng: 118.11 },
    { lat: 24.44, lng: 118.12 },
    { lat: 24.44, lng: 118.13 },
  ];

  it("按距离比例取点，并给出走过的那一截", () => {
    expect(alongRoute(route, 0)!.point).toEqual(route[0]);
    expect(alongRoute(route, 1)!.point).toEqual(route[2]);
    const half = alongRoute(route, 0.5)!;
    expect(half.point.lng).toBeCloseTo(118.12, 6);
    expect(half.passed[half.passed.length - 1]).toEqual(half.point);
    expect(alongRoute([], 0.5)).toBeNull();
  });

  it("进度按出发/到达时间计算并夹在 0–1", () => {
    const leg = { mode: "walk" as const, route, departsAt: 1_000, arrivesAt: 11_000 };
    expect(legProgress(leg, 0)).toBe(0);
    expect(legProgress(leg, 6_000)).toBeCloseTo(0.5, 6);
    expect(legProgress(leg, 20_000)).toBe(1);
  });
});

/* ---------- live：W1 统一世界状态 → 地图模型（只做形状转换，不补不猜） ---------- */

const NOW = Date.parse("2026-09-24T10:00:00Z");
const HOME_POINT = { lat: 24.441642, lng: 118.112039 };
const CAFE_POINT = { lat: 24.4351, lng: 118.1152 };
const iso = (ms: number) => new Date(ms).toISOString();

function w1Pet(over: Omit<Partial<WorldPetState>, "activity"> & { activity?: Partial<WorldPetState["activity"]> } = {}): WorldPetState {
  const { activity, ...rest } = over;
  return {
    pet_id: "p-1",
    name: "栗子",
    species: "cat",
    avatar_url: "/media/pets/p-1.jpg",
    relation: "mine",
    home: { center: HOME_POINT, precision_m: 900, label: "环岛路附近的海边" },
    leg: null,
    position: { ...HOME_POINT, basis: "home_area", precision_m: 900 },
    version: 3,
    ...rest,
    activity: {
      kind: "home",
      phase: "home",
      pose: "idle",
      title: "在小窝",
      doing: null,
      place: null,
      since: null,
      until: null,
      job: null,
      journey_id: null,
      visit_id: null,
      ...activity,
    },
  };
}

const state = (...pets: WorldPetState[]): WorldState => ({ server_time: iso(NOW), coord_system: "wgs84", cache_seconds: 15, pets });

describe("live：W1 统一世界状态 → 地图模型", () => {
  it("在家：家的模糊中心与半径原样带过来，姿态透传（作息接不上时后端给 idle，不冒 zzz）", () => {
    const pet = sceneFromWorldState(state(w1Pet())).pets[0];
    expect(pet.home).toEqual({ center: HOME_POINT, precisionM: 900, label: "环岛路附近的海边" });
    expect(pet.position).toEqual(HOME_POINT);
    expect(pet.basis).toBe("home_area");
    expect(pet.activity.pose).toBe("idle");
    expect(pet.photoUrl).toBe("/media/pets/p-1.jpg");
    expect(panelCopy(pet, NOW, null).headline).toBe("栗子在小窝里");
  });

  it("头像：W1 有证件照小头像就用它；没有（null）时退回家庭资料里的照片；都没有才是 null（画爪印），不拿别人的照片", () => {
    const photos = new Map([["p-1", "/api/v1/web/media/pets/p-1/photo"]]);
    expect(sceneFromWorldState(state(w1Pet({ avatar_url: "/media/id-photos/a-1/avatar" })), photos).pets[0].photoUrl).toBe("/media/id-photos/a-1/avatar");
    expect(sceneFromWorldState(state(w1Pet({ avatar_url: null })), photos).pets[0].photoUrl).toBe("/api/v1/web/media/pets/p-1/photo");
    expect(sceneFromWorldState(state(w1Pet({ avatar_url: null }))).pets[0].photoUrl).toBeNull();
    // 别的宠物（p-2）只拿自己那一项；家庭资料里没有它，就不会借 p-1 的照片。
    expect(sceneFromWorldState(state(w1Pet({ pet_id: "p-2", avatar_url: null })), photos).pets[0].photoUrl).toBeNull();
  });

  it("在家睡着（后端 pose=sleeping）：面板直接说在睡觉，读屏也能知道", () => {
    const sleeping = worldPetFromState(w1Pet({ activity: { pose: "sleeping" } }));
    expect(panelCopy(sleeping, NOW, null).headline).toBe("栗子在小窝里睡觉");
    expect(panelCopy(worldPetFromState(w1Pet({ activity: { pose: "idle" } })), NOW, null).headline).toBe("栗子在小窝里");
  });

  it("在路上：有几何和起止时间才沿线插值；since / until 是这一阶段的起止", () => {
    const pet = worldPetFromState(
      w1Pet({
        activity: { kind: "cafe", phase: "going", pose: "walking", title: "去附近喝一杯", place: { name: "街角的咖啡馆", ...CAFE_POINT, attribution: null }, since: iso(NOW - 5 * 60_000), until: iso(NOW + 10 * 60_000) },
        leg: { mode: "walk", route: [HOME_POINT, CAFE_POINT], departs_at: iso(NOW - 5 * 60_000), arrives_at: iso(NOW + 10 * 60_000) },
        position: { lat: 24.44, lng: 118.113, basis: "route", precision_m: 50 },
      }),
    );
    expect(pet.leg).toMatchObject({ mode: "walk", departsAt: NOW - 5 * 60_000, arrivesAt: NOW + 10 * 60_000 });
    expect(pet.activity.pose).toBe("walking");
    const p = positionAt(pet, NOW)!;
    expect(p.lat).toBeLessThan(HOME_POINT.lat);
    expect(p.lat).toBeGreaterThan(CAFE_POINT.lat);
    expect(panelCopy(pet, NOW, legProgress(pet.leg!, NOW)).detail).toContain("还要 10 分钟");
  });

  it("缺几何或缺时间：不沿线插值，用服务端给的点；交通方式 transit 归到公交", () => {
    const noTimes = worldPetFromState(w1Pet({ activity: { phase: "going", kind: "trip", pose: "riding" }, leg: { mode: "transit", route: [HOME_POINT, CAFE_POINT], departs_at: null, arrives_at: null }, position: { lat: 24.439, lng: 118.113, basis: "route", precision_m: 80 } }));
    expect(noTimes.leg).toBeNull();
    expect(positionAt(noTimes, NOW)).toEqual({ lat: 24.439, lng: 118.113 });
    const bus = worldPetFromState(w1Pet({ activity: { phase: "going", kind: "trip", pose: "riding" }, leg: { mode: "transit", route: [HOME_POINT, CAFE_POINT], departs_at: iso(NOW), arrives_at: iso(NOW + 60_000) } }));
    expect(bus.leg?.mode).toBe("bus");
  });

  it("没有出处的坐标不画：position 为 null 就不知道在哪", () => {
    const pet = worldPetFromState(w1Pet({ position: null, activity: { phase: "unknown", pose: "unknown" } }));
    expect(pet.position).toBeNull();
    expect(pet.basis).toBe("unknown");
    expect(positionAt(pet, NOW)).toBeNull();
    expect(panelCopy(pet, NOW, null).headline).toBe("还没同步到栗子此刻在哪");
  });

  it("打工：going 只能是在去打工的路上，working 才是在打工（后端给的阶段原样用）", () => {
    const going = worldPetFromState(w1Pet({ activity: { kind: "job", phase: "going", pose: "walking", title: "渔港帮工", job: { title: "渔港帮工", pay: 25, paid: false }, place: { name: "渔港", ...CAFE_POINT, attribution: null } } }));
    expect(panelCopy(going, NOW, 0.3).headline).toBe("栗子在去打工的路上");
    const working = worldPetFromState(w1Pet({ activity: { kind: "job", phase: "there", pose: "working", title: "渔港帮工", doing: null, job: { title: "渔港帮工", pay: 25, paid: false }, place: { name: "渔港", ...CAFE_POINT, attribution: null }, until: iso(NOW + 60 * 60_000) } }));
    const copy = panelCopy(working, NOW, null);
    expect(copy.headline).toBe("栗子在渔港打工");
    // 是几点几分，不是时长（曾误用时长格式显示成“29836769:44 收工”）。
    expect(copy.detail).toMatch(/(^|· )\d{2}:\d{2} 收工/);
    expect(copy.detail).toContain("工钱 25 星币，收工后到账");
    expect(working.activity.pose).toBe("working");
  });

  it("家里多只宠物都上地图；默认看当前选中的那只，否则看自己的第一只", () => {
    const scene = sceneFromWorldState(state(w1Pet({ pet_id: "p-1", relation: "household", name: "豆包" }), w1Pet({ pet_id: "p-2", relation: "mine", name: "栗子" })));
    expect(scene.pets.map((p) => p.name)).toEqual(["豆包", "栗子"]);
    expect(focusPetId(scene, "p-1")).toBe("p-1");
    expect(focusPetId(scene, "gone")).toBe("p-2");
    expect(focusPetId(sceneFromWorldState(state()), null)).toBeNull();
  });
});

describe("演示剧本（仅 fixture）", () => {
  it("一天循环：在家 → 散步 → 回家 → 喝一杯 → 回家 → 去打工 → 收工回家", () => {
    const phases = DEMO_DAY.map((s) => `${s.kind}:${s.phase}`);
    expect(phases).toEqual([
      "home:home", "stroll:going", "stroll:there", "stroll:returning", "home:home",
      "cafe:going", "cafe:there", "cafe:returning", "home:home",
      "job:going", "job:there", "job:returning", "home:home",
    ]);
    // 每段的姿态是剧本里写明的结构化字段（地图表情只看它），不是从 doing 文字里猜的。
    expect(DEMO_DAY.map((s) => s.pose)).toEqual([
      "sleeping", "walking", "exploring", "walking", "eating",
      "walking", "cafe", "walking", "sunbathing",
      "walking", "working", "walking", "sleeping",
    ]);
    expect(demoScene(segmentStart(0) + 60_000, 0).pets[0].activity.pose).toBe("sleeping");
    expect(segmentAt(segmentStart(3) + 1).index).toBe(3);
    expect(segmentAt(demoDayLength() + segmentStart(5) + 1).index).toBe(5);
  });

  it("走路段沿真实路线走，到了在目的地，在家在家的点；工钱收工后才到账", () => {
    const day0 = 0;
    const going = demoScene(segmentStart(1) + 60_000, day0).pets[0];
    expect(going.activity.phase).toBe("going");
    expect(going.leg!.route.length).toBeGreaterThan(10);
    const there = demoScene(segmentStart(2) + 60_000, day0).pets[0];
    expect(there.position).toEqual(there.activity.place && { lat: there.activity.place.lat, lng: there.activity.place.lng });
    const atHome = demoScene(segmentStart(4) + 60_000, day0).pets[0];
    expect(atHome.position).toEqual(atHome.home!.center);
    const working = demoScene(segmentStart(10) + 60_000, day0).pets[0];
    expect(working.activity.job).toMatchObject({ paid: false });
    const back = demoScene(segmentStart(11) + 60_000, day0).pets[0];
    expect(back.activity.job).toMatchObject({ paid: true });
    const returning = demoScene(segmentStart(3) + 1, day0).pets[0];
    expect(returning.leg!.route[0]).toEqual(going.leg!.route[going.leg!.route.length - 1]);
  });
});

describe("地图配置", () => {
  it("接口不在、格式不对或缺字段：一律当作不可用，不崩", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("nope", { status: 404 })));
    await expect(fetchMapConfig()).resolves.toMatchObject({ available: false, unavailable_reason: "http_404" });
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ provider: "amap", available: true, js_key: "k", service_host: null })));
    await expect(fetchMapConfig()).resolves.toMatchObject({ available: false, unavailable_reason: "incomplete" });
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("offline"); }));
    await expect(fetchMapConfig()).resolves.toMatchObject({ available: false, unavailable_reason: "unreachable" });
  });

  it("配置里绝不带安全密钥字段（只认 js_key / service_host）", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ provider: "amap", available: true, js_key: "k", service_host: "https://x/_AMapService", style: null, overseas_tiles: false, unavailable_reason: null })));
    const config = await fetchMapConfig();
    expect(Object.keys(config)).not.toContain("security_code");
    expect(JSON.stringify(config)).not.toMatch(/jscode|securityJsCode/);
  });
});

describe("地图首页（fixture 演示）", () => {
  function renderMap(driving: ServiceMap["driving"]) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    // 家庭上下文会先取 households 服务（fixture 下不调用）；驾校服务给主面板的驾校那一行（按阶段出不出）；其余任何业务服务被读到都算失败。
    const allowed: Record<string, unknown> = { households: { list: () => { throw new Error("fixture 不应请求家庭列表"); } }, driving };
    const services = new Proxy(allowed as unknown as ServiceMap, { get: (t, prop) => { if (String(prop) in t) return (t as unknown as Record<string, unknown>)[String(prop)]; throw new Error(`unexpected service ${String(prop)}`); } });
    return render(
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
  it("地图取不到：退回示意底，主面板照常说 TA 在做什么，演示标记常驻；业务服务只向驾校要状态，驾校那一行按阶段出现或不出现", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 404 })));
    renderMap(createFixtureDrivingService({ stage: "wish", latency: 0 }));
    expect(await screen.findByText("演示剧本 · 不是真实数据")).toBeTruthy();
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("地图暂时没连上"));
    const panel = screen.getByRole("region", { name: /此刻$/ });
    expect(panel.querySelector("h2")?.textContent).toMatch(/团子/);
    expect(screen.getByRole("navigation", { name: "主导航（新版预览）" }).textContent).toMatch(/地图.*通讯器.*回忆/);
    expect(screen.getByRole("link", { name: "我的" }).getAttribute("href")).toBe("/me");
    expect(screen.getByRole("link", { name: "回忆" }).getAttribute("href")).toBe("/memories");
    expect(screen.getByRole("link", { name: "进小窝" }).getAttribute("href")).toBe("/home?from=map");
    // 头像不用名字首字：演示宠物没有照片，就用授权的测试小灰猫；并带着此刻的状态表情。
    const avatar = panel.querySelector(".ps-mood");
    expect(avatar?.getAttribute("data-mood")).toBeTruthy();
    expect(avatar?.querySelector("img")?.getAttribute("src")).toMatch(/demo-cat-portrait/);
    expect(avatar?.querySelector(".ps-pet-portrait")?.textContent).toBe("");
    // 驾校（演示服务）：TA 想学开车（wish）→ 面板有这一行，点它去驾校
    // 第 1 步追加：愿望那一行用宠物的名字（演示里是团子）。
    const wish = await screen.findByRole("link", { name: /^团子说想学开车/ });
    expect(wish.getAttribute("href")).toBe("/school");
    cleanup();
    // 还没开始学（none）→ 驾校状态读回来了，也没有这一行
    const none = createFixtureDrivingService({ latency: 0 });
    const status = vi.fn(none.status);
    renderMap({ ...none, status });
    expect(await screen.findByRole("region", { name: /此刻$/ })).toBeTruthy();
    await waitFor(() => expect(status).toHaveBeenCalled());
    await status.mock.results[0].value;
    await new Promise((r) => setTimeout(r, 30));
    expect(screen.queryByRole("link", { name: /驾校|想学开车/ })).toBeNull();
    expect(screen.queryByRole("group", { name: /^提醒/ })).toBeNull();
  });

  it("演示模式：没有照片的宠物头像是测试小灰猫；有照片就用照片", () => {
    expect(petPortraitUrl(null)).toMatch(/demo-cat-portrait/);
    expect(petPortraitUrl("/media/pets/p1.jpg")).toBe("/media/pets/p1.jpg");
  });
});

