/**
 * 旅行心愿的演示数据（TRV-06）。明确的演示：编号 fx- 开头，页面上处处挂“演示”（由读数据的一侧按 fixture 模式告诉页面）。
 * 只在 fixture 模式按需加载（journey/module.tsx 的 visits.travelWish 演示实现与 ./data 的 useDemoPlans 里的动态 import），
 * 主包里没有它，live 模式绝不回退到这里。
 * 来源：claude-6c2b 分身 2026-09-24 手写；不对应任何真实账号、宠物、商家、班次或资料来源。
 * 形状全部是生成的契约类型（generated.ts 9c5f1b88 版）：TravelWish、TravelPlan（current_revision + revisions，手账在修订的 journals 里）……
 * 计划页的“计划 + 心愿”组合（PlanBundle）是本地读模型，见 ./model。
 * - 当前活动心愿（GET /travel/wish 的演示）：广州，资料还在查、还没有计划——没有计划的心愿只能从 /guides/wish 进，地图那一行也指向它。
 * - 其余是几份计划（GET /travel/plans/{plan_id} 的演示）：等攒够星币、资料待确认、可以出发、已出发、已回来、已取消。
 *   真实情况下 TA 同一时间只惦记一个地方（方案第 8 节），这里放在一起只为看版面。
 * - 目的地只用演示世界里已有的地区（transport / venue 演示数据里的广州南站、东京羽田、澳门码头、中环码头、香港西九龙、深圳湾、
 *   香港市区、示例海边咖啡馆、香港机场），地名带“（示意）”或“（演示店）”；坐标是 WGS-84（I 定稿），用那些演示数据里的示意坐标。
 * - 地图外链 nav_url 照后端形态写（高德 URI、WGS-84、经度在前、不唤起 App），只有核实过的地点才有——这是演示数据的写法，
 *   页面只读 nav_url，不拿坐标自己拼（后端给，I 定）。
 * - 资料来源只用 RFC 2606 保留的 example.org / example.com / example.net，机构名带“（演示）”，不冒充真实机构。
 *   计划里的来源只含已核验事实引用到的（后端定）；没核实的事实靠它自己带的抓取 / 发布时间。
 * - 不编现实票价：唯一报数的现实参考写明“（演示）”、币种、适用区间、估算；另有两条没核实的，页面写“还没核实”，不写 0、也不报数。
 * - 路费（§30）：fare 是这趟的标价、用没用券都不变；已出发那趟用了驾校借车券（fare 20，演示世界里自己开车兜风的标价，
 *   fare_waived 为真＝实付 0、省下 20）；已回来那趟实付 8 星币（去附近喝一杯的标价）；出发前 journey 为 null。攒钱目标从不当路费。
 * - 手账（修订的 journals）：页上的字跟着那一版计划（标题、一句话、站点、提醒、雨天备选、来源）；到访只在回忆页（memory）的站点上，
 *   已回来那趟的回忆页里只有主目的地有真实到访事件。
 * - 时间一律带 +08:00；有效期左闭右开（§29.3）。
 */
import type { TravelFact, TravelJournal, TravelPlan, TravelPlanRevision, TravelSource, TravelStop, TravelWish } from "@/shared/contracts";
import type { PlanBundle } from "./model";

const PET = "fx-pet-001"; // 演示世界的样板宠物编号（页面不写死名字）

function wish(seed: Pick<TravelWish, "wish_id" | "status" | "destination_key" | "destination_name" | "city" | "owner_reason" | "funds_goal"> & Partial<TravelWish>): TravelWish {
  return {
    pet_id: PET,
    wish_revision: 1,
    waiting_reasons: [],
    research_state: "ready",
    research_round: 1,
    plan_id: null,
    plan_revision: null,
    journey_id: null,
    reconsider_after: null,
    last_considered_at: null,
    plan_stale: false,
    target_coins: null,
    current_coins: null,
    candidates: [],
    ...seed,
  };
}

/** 演示数据里的后端地图外链（高德 URI、WGS-84、经度在前、不唤起 App）：只给核实过的地点。 */
function amap(name: string, lat: number, lng: number): string {
  return `https://uri.amap.com/marker?position=${lng},${lat}&name=${encodeURIComponent(name)}&coordinate=wgs84&callnative=0`;
}

/** station_id 按下标 "st-{i}"，主目的地是 st-0（I 答）；计划阶段的到访恒为空。核实过的地点带后端的 nav_url。 */
function stop(index: number, seed: Pick<TravelStop, "name" | "why" | "tip" | "fact_ids" | "lat" | "lng"> & Partial<TravelStop>): TravelStop {
  const verified = seed.verified ?? true;
  const navUrl = verified && seed.lat != null && seed.lng != null ? amap(seed.name, seed.lat, seed.lng) : null;
  return { station_id: `st-${index}`, role: index === 0 ? "main" : "suggested", verified, nav_url: navUrl, visited_event_ids: [], ...seed };
}

function fact(seed: Pick<TravelFact, "fact_id" | "category" | "subject" | "value" | "source_ids"> & Partial<TravelFact>): TravelFact {
  return {
    verification: "search",
    conclusion: null,
    verdict: "verified",
    blocks_departure: false,
    retrieved_at: null,
    published_at: null,
    observed_at: null,
    valid_from: null,
    valid_until: null,
    ...seed,
  };
}

function source(seed: Pick<TravelSource, "source_id"> & Partial<TravelSource>): TravelSource {
  return { url: null, publisher: null, retrieved_at: null, published_at: null, ...seed };
}

function revision(seed: Pick<TravelPlanRevision, "plan_id" | "wish_id" | "destination_key" | "title" | "summary" | "stops" | "facts" | "sources" | "created_at"> & Partial<TravelPlanRevision>): TravelPlanRevision {
  return {
    plan_revision: 1,
    wish_revision_at_build: 1,
    pet_id: PET,
    operation_id: null,
    rain_alternative: null,
    owner_tips: [],
    preconditions: [],
    valid_from: null,
    valid_until: null,
    journey: null,
    journals: [],
    ...seed,
  };
}

/**
 * 一页手账：页上的字照这一版计划排（和后端 web_travel/journal.py 的版式一致——标题、一句话、提醒、雨天备选、站点、来源），
 * 回忆页的站点带真实到访事件（visited：站点序号 → 事件编号）。
 */
function journal(
  rev: TravelPlanRevision,
  seed: Pick<TravelJournal, "phase" | "image_status" | "created_at"> & Partial<TravelJournal>,
  visited: Record<number, string[]> = {},
): TravelJournal {
  return {
    journal_id: `tj-${rev.plan_id}-${seed.phase}`,
    journal_revision: 1,
    plan_id: rev.plan_id,
    plan_revision: rev.plan_revision,
    title: rev.title,
    summary: rev.summary,
    stations: rev.stops.map((s, i) => ({
      station_id: `st-${i}`,
      name: s.name,
      role: s.role,
      why: null,
      tip: null,
      fact_ids: s.fact_ids,
      verified: false,
      lat: s.lat,
      lng: s.lng,
      nav_url: null,
      visited_event_ids: visited[i] ?? [],
    })),
    owner_tips: rev.owner_tips,
    rain_alternative: rev.rain_alternative,
    sources: rev.sources,
    identity_mode: "none",
    identity_note: null,
    template_revision: "journal-t0",
    image_url: null,
    image_refused: null,
    redraw_ticket: null,
    event_ids: Object.values(visited).flat(),
    updated_at: null,
    ...seed,
  };
}

/** 修订挂上它的手账（journals 属于这一版修订）。 */
function withJournals(rev: TravelPlanRevision, make: (rev: TravelPlanRevision) => TravelJournal[]): TravelPlanRevision {
  return { ...rev, journals: make(rev) };
}

/** 一份计划：旧版都留着，current_revision 指最新那一版。 */
function plan(...revisions: TravelPlanRevision[]): TravelPlan {
  const current = revisions[revisions.length - 1];
  return { plan_id: current.plan_id, wish_id: current.wish_id, current_revision: current.plan_revision, revisions };
}

/** 地点身份：示例地图核对（演示）。 */
function placeFact(id: string, value: string, subject: string, sourceId: string): TravelFact {
  return fact({ fact_id: id, category: "destination_identity", value, subject, source_ids: [sourceId], verification: "map" });
}

/** 当前活动心愿：资料准备中（研究正在进行，还没有计划）。 */
export const DEMO_CURRENT_WISH: TravelWish = wish({
  wish_id: "fx-wish-guangzhou",
  status: "active",
  destination_key: "fx-dest-guangzhou",
  destination_name: "广州",
  city: "广州",
  owner_reason: "想坐一次爪爪铁路，去看看广州的早晨是什么样子。先把资料查清楚再说。",
  funds_goal: 30,
  waiting_reasons: ["research_pending"],
  research_state: "running",
  reconsider_after: "2026-09-25T07:30:00+08:00",
  last_considered_at: "2026-09-24T07:30:00+08:00",
  candidates: [{ destination_key: "fx-dest-guangzhou", title: "广州（示意）", executable: false, blocked_by: ["research_pending"] }],
});

/** 等攒够星币：资料齐了，钱不够（演示世界里飞东京的路费就是 120 星币，这里把它当攒钱目标）。机票的现实参考没核实。计划手账的配图被拒了。 */
const tokyo: PlanBundle = {
  wish: wish({
    wish_id: "fx-wish-tokyo",
    status: "active",
    destination_key: "fx-dest-tokyo",
    destination_name: "东京",
    city: "东京",
    owner_reason: "想坐喵航去东京，看看那边的电车是不是也叮叮地响。路费有点贵，我先攒着。",
    funds_goal: 120,
    waiting_reasons: ["missing_funds"],
    target_coins: 120,
    current_coins: 45,
    last_considered_at: "2026-09-24T07:30:00+08:00",
    plan_id: "fx-plan-tokyo",
    plan_revision: 1,
  }),
  plan: plan(
    withJournals(
      revision({
        plan_id: "fx-plan-tokyo",
        wish_id: "fx-wish-tokyo",
        destination_key: "fx-dest-tokyo",
        operation_id: "fx-op-tokyo-1",
        title: "坐喵航去东京看电车",
        summary: "攒够了就从香港机场坐喵航 Cat222 飞东京，下了飞机换爪爪铁路进城，找一条能看电车的路慢慢走（演示航线）。",
        stops: [
          stop(0, { name: "东京（示意）", why: "下了飞机进城，找一条能看电车的路。", tip: "地图上先定在羽田机场一带（示意）。", fact_ids: ["fx-fact-tokyo-place", "fx-fact-tokyo-route"], lat: 35.549, lng: 139.779 }),
          stop(1, { name: "香港机场（示意）", why: "登机前在窗边看一会儿飞机。", tip: null, fact_ids: ["fx-fact-hkg-place"], lat: 22.308, lng: 113.918 }),
        ],
        owner_tips: [
          { text: "出境要带星球护照", fact_ids: ["fx-fact-tokyo-passport"] },
          { text: "路上时间长，TA 会在飞机上多睡一会儿", fact_ids: ["fx-fact-tokyo-route"] },
        ],
        rain_alternative: "下雨就在车站里看电车进站",
        facts: [
          placeFact("fx-fact-tokyo-place", "东京（示意）", "st-0", "fx-src-map-tokyo"),
          placeFact("fx-fact-hkg-place", "香港机场（示意）", "st-1", "fx-src-map-tokyo"),
          fact({ fact_id: "fx-fact-tokyo-route", category: "route", value: "喵航飞东京，再换爪爪铁路进城（演示航线）", subject: "st-0", source_ids: ["fx-src-air"], blocks_departure: true }),
          fact({ fact_id: "fx-fact-tokyo-passport", category: "notice", value: "出境要带星球护照（演示）", subject: "st-0", source_ids: ["fx-src-air"] }),
          // 没核实：价钱不报数（value 为 null 或带着数都一样）。
          fact({ fact_id: "fx-fact-tokyo-fare", category: "ticket_price", value: null, subject: "st-0", source_ids: [], verdict: "unverified", retrieved_at: "2026-09-23T21:05:00+08:00" }),
        ],
        sources: [
          source({ source_id: "fx-src-map-tokyo", publisher: "示例地图核对（演示）", retrieved_at: "2026-09-23T21:02:00+08:00" }),
          source({ source_id: "fx-src-air", url: "https://example.com/demo/flight-notes", publisher: "示例航线资料（演示）", retrieved_at: "2026-09-23T21:05:00+08:00", published_at: "2026-09-20T00:00:00+08:00" }),
        ],
        created_at: "2026-09-23T21:10:00+08:00",
      }),
      // 配图被拒（拒绝码只进“技术信息”）：没有图，手账文字照样在。
      (rev) => [journal(rev, { phase: "plan", image_status: null, image_refused: "fx-refused-demo", created_at: "2026-09-23T21:12:00+08:00" })],
    ),
  ),
};

/** 资料待确认：船班过期、码头公告两份说法不一、天气没有可用来源。写“还在确认”，不写“以现场为准”。还没有手账。 */
const macau: PlanBundle = {
  wish: wish({
    wish_id: "fx-wish-macau",
    status: "active",
    destination_key: "fx-dest-macau",
    destination_name: "澳门",
    city: "澳门",
    owner_reason: "想坐船去看海，想知道船开出去以后，海是什么颜色。",
    funds_goal: 40,
    waiting_reasons: ["fact_stale", "fact_conflicting", "fact_unverified"],
    plan_id: "fx-plan-macau",
    plan_revision: 1,
  }),
  plan: plan(
    revision({
      plan_id: "fx-plan-macau",
      wish_id: "fx-wish-macau",
      destination_key: "fx-dest-macau",
      operation_id: "fx-op-macau-1",
      title: "坐船去澳门看海",
      summary: "上午从中环码头坐海獭轮渡过去，下了船在码头附近的海边走走，傍晚坐船回来（演示航线）。",
      valid_from: "2026-09-27T00:00:00+08:00",
      valid_until: "2026-09-28T00:00:00+08:00",
      stops: [
        stop(0, { name: "澳门码头一带（示意）", why: "下了船在海边走走，看浪。", tip: "去程、回程都坐海獭轮渡（演示航线）。", fact_ids: ["fx-fact-macau-place", "fx-fact-macau-ferry"], lat: 22.197, lng: 113.557 }),
        stop(1, { name: "中环码头（示意）", why: "上船前在码头看一会儿船进出。", tip: null, fact_ids: ["fx-fact-central-place"], lat: 22.287, lng: 114.157 }),
        // 地点本身没核实：没有地图外链（坐标也没有）。
        stop(2, { name: "码头边的观海长椅（示意）", why: "TA 听说能坐着看船。", tip: null, fact_ids: ["fx-fact-bench-place"], verified: false, lat: null, lng: null }),
      ],
      owner_tips: [
        { text: "去澳门要带星球护照", fact_ids: ["fx-fact-macau-passport"] },
        { text: "9月27日码头开不开，两份资料说法不一，还在确认", fact_ids: ["fx-fact-macau-notice-a", "fx-fact-macau-notice-b"] },
        { text: "船上风大，靠窗坐，别站在甲板边", fact_ids: ["fx-fact-macau-deck"] },
      ],
      rain_alternative: "下雨就把看海留到下一次，在码头里看船进出",
      // 出发时必须仍然有效的关键事实：船班（过期了）、船票（有效到 9 月 30 日）。
      preconditions: ["fx-fact-macau-ferry", "fx-fact-macau-fare"],
      facts: [
        placeFact("fx-fact-macau-place", "澳门码头一带（示意）", "st-0", "fx-src-map-macau"),
        placeFact("fx-fact-central-place", "中环码头（示意）", "st-1", "fx-src-map-macau"),
        fact({ fact_id: "fx-fact-bench-place", category: "destination_identity", value: "码头边的观海长椅（示意）", subject: "st-2", source_ids: [], verdict: "unverified", verification: "map" }),
        // 今天才抓到，但资料本身是 9 月 10 日发布的：抓取时间不能刷新资料的年代。过期的事实引用的来源不在计划的来源表里，时间在事实自己身上。
        fact({ fact_id: "fx-fact-macau-ferry", category: "route", value: "每 30 分钟一班（演示）", subject: "st-0", source_ids: ["fx-src-ferry"], verdict: "stale", blocks_departure: true, retrieved_at: "2026-09-24T05:41:00+08:00", published_at: "2026-09-10T00:00:00+08:00" }),
        fact({ fact_id: "fx-fact-macau-notice-a", category: "notice", value: "9月27日码头维修（演示）", subject: "st-0", source_ids: ["fx-src-notice-a"], verdict: "conflicting", blocks_departure: true, retrieved_at: "2026-09-24T05:42:00+08:00", published_at: "2026-09-22T00:00:00+08:00" }),
        fact({ fact_id: "fx-fact-macau-notice-b", category: "notice", value: "9月27日照常开放（演示）", subject: "st-0", source_ids: ["fx-src-notice-b"], verdict: "conflicting", blocks_departure: true, retrieved_at: "2026-09-24T05:42:00+08:00", published_at: "2026-09-23T00:00:00+08:00" }),
        // 没有可用来源（§5.2 fact_unverified）。
        fact({ fact_id: "fx-fact-macau-weather", category: "weather", value: "9月27日天晴（演示，未核实）", subject: "st-0", source_ids: [], verdict: "unverified", blocks_departure: true, verification: "weather_api", retrieved_at: "2026-09-24T05:44:00+08:00" }),
        fact({ fact_id: "fx-fact-macau-passport", category: "notice", value: "出入境要带星球护照（演示）", subject: "st-0", source_ids: ["fx-src-pier"] }),
        fact({ fact_id: "fx-fact-macau-deck", category: "notice", value: "船上靠窗的座位风小（演示）", subject: "st-0", source_ids: ["fx-src-fare"] }),
        fact({ fact_id: "fx-fact-macau-fare", category: "ticket_price", value: { amount: 100, currency: "HKD", estimated: true }, subject: "st-0", source_ids: ["fx-src-fare"], valid_from: "2026-09-01T00:00:00+08:00", valid_until: "2026-10-01T00:00:00+08:00" }),
        // 没核实的价钱：value 里带着数也不报。
        fact({ fact_id: "fx-fact-macau-bus", category: "ticket_price", value: { amount: 12, currency: "MOP", estimated: true }, subject: "st-0", source_ids: ["fx-src-fare"], verdict: "unverified" }),
      ],
      sources: [
        source({ source_id: "fx-src-map-macau", publisher: "示例地图核对（演示）", retrieved_at: "2026-09-24T05:40:00+08:00" }),
        source({ source_id: "fx-src-fare", url: "https://example.org/demo/fares", publisher: "示例票价资料（演示）", retrieved_at: "2026-09-24T05:43:00+08:00", published_at: "2026-09-20T00:00:00+08:00" }),
        // 没有机构名：页面显示域名。
        source({ source_id: "fx-src-pier", url: "https://example.net/demo/pier-news", retrieved_at: "2026-09-24T05:45:00+08:00" }),
      ],
      created_at: "2026-09-24T05:46:00+08:00",
    }),
  ),
};

// 西九龙：旧版（第 1 版）留着，页面显示 current_revision（第 2 版）。
const westKowloonV2 = withJournals(
  revision({
    plan_id: "fx-plan-west-kowloon",
    wish_id: "fx-wish-west-kowloon",
    destination_key: "fx-dest-west-kowloon",
    plan_revision: 2,
    operation_id: "fx-op-wkl-2",
    title: "去西九龙看灯",
    summary: "傍晚坐车去西九龙，沿海边走到天黑看对岸的灯，晚上坐车回家。",
    valid_from: "2026-09-26T00:00:00+08:00",
    valid_until: "2026-09-27T00:00:00+08:00",
    stops: [
      stop(0, { name: "香港西九龙一带（示意）", why: "沿海边慢慢走，等天黑看对岸的灯。", tip: "坐车约 30 分钟（演示）。", fact_ids: ["fx-fact-wkl-place", "fx-fact-wkl-route"], lat: 22.304, lng: 114.166 }),
      stop(1, { name: "中环码头（示意）", why: "回家路上看一眼夜里的船。", tip: null, fact_ids: ["fx-fact-wkl-central-place"], lat: 22.287, lng: 114.157 }),
    ],
    owner_tips: [{ text: "海边晚上凉，早点回家", fact_ids: ["fx-fact-wkl-weather"] }],
    rain_alternative: "下雨就去示例·海边咖啡馆（演示店）坐坐",
    // 出发时必须仍然有效：9 月 26 日的天气预报（有效到当天）。
    preconditions: ["fx-fact-wkl-weather"],
    facts: [
      placeFact("fx-fact-wkl-place", "香港西九龙一带（示意）", "st-0", "fx-src-map-wkl"),
      placeFact("fx-fact-wkl-central-place", "中环码头（示意）", "st-1", "fx-src-map-wkl"),
      fact({ fact_id: "fx-fact-wkl-route", category: "route", value: "坐车约 30 分钟（演示）", subject: "st-0", source_ids: ["fx-src-road-wkl"] }),
      fact({ fact_id: "fx-fact-wkl-weather", category: "weather", value: "9月26日多云，晚上转凉（演示预报）", subject: "st-0", source_ids: ["fx-src-weather-wkl"], verification: "weather_api", valid_from: "2026-09-26T00:00:00+08:00", valid_until: "2026-09-27T00:00:00+08:00" }),
    ],
    sources: [
      source({ source_id: "fx-src-map-wkl", publisher: "示例地图核对（演示）", retrieved_at: "2026-09-24T05:10:00+08:00" }),
      source({ source_id: "fx-src-road-wkl", url: "https://example.com/demo/road-notes", publisher: "示例路线资料（演示）", retrieved_at: "2026-09-24T05:12:00+08:00", published_at: "2026-09-18T00:00:00+08:00" }),
      source({ source_id: "fx-src-weather-wkl", url: "https://example.com/demo/weather", publisher: "示例天气资料（演示）", retrieved_at: "2026-09-24T05:15:00+08:00", published_at: "2026-09-24T05:00:00+08:00" }),
    ],
    created_at: "2026-09-24T05:20:00+08:00",
  }),
  // 手账图结果未确认（unknown），后端给了重画票；画里的 TA 照着证件照画。
  (rev) => [journal(rev, { phase: "plan", image_status: "unknown", redraw_ticket: "fx-redraw-wkl", identity_mode: "photo", created_at: "2026-09-24T05:22:00+08:00" })],
);

/** 可以出发：资料齐、星币够。手账图结果未确认（unknown），文字照常，后端给了重画票，所以说“稍后可以重画”。 */
const westKowloon: PlanBundle = {
  wish: wish({
    wish_id: "fx-wish-west-kowloon",
    status: "ready",
    destination_key: "fx-dest-west-kowloon",
    destination_name: "香港西九龙",
    city: "香港",
    owner_reason: "想去海边吹吹风，看对岸的灯一盏一盏亮起来。",
    funds_goal: 12,
    plan_id: "fx-plan-west-kowloon",
    plan_revision: 2,
  }),
  plan: plan(
    { ...westKowloonV2, plan_revision: 1, operation_id: "fx-op-wkl-1", summary: "旧版：白天坐车去西九龙，在海边走一圈就回家（演示）。", journals: [], created_at: "2026-09-23T18:00:00+08:00" },
    westKowloonV2,
  ),
};

/** 已出发：还在路上，回忆手账还没有，所以一站都不盖章、也不写“下次”。用了驾校借车券，省下 20 星币。计划手账在画（照着证件照画）。 */
const shenzhenBay: PlanBundle = {
  wish: wish({
    wish_id: "fx-wish-shenzhen-bay",
    status: "linked",
    destination_key: "fx-dest-shenzhen-bay",
    destination_name: "深圳湾",
    city: "深圳",
    owner_reason: "想早起去看一次日出，听说那边的天很宽。",
    funds_goal: 18,
    plan_id: "fx-plan-shenzhen-bay",
    plan_revision: 1,
    journey_id: "fx-journey-shenzhen-bay",
  }),
  plan: plan(
    withJournals(
      revision({
        plan_id: "fx-plan-shenzhen-bay",
        wish_id: "fx-wish-shenzhen-bay",
        destination_key: "fx-dest-shenzhen-bay",
        operation_id: "fx-op-szb-1",
        title: "去深圳湾看日出",
        summary: "天没亮就自己开车过去，看完日出再慢慢开回来（演示路线）。",
        valid_from: "2026-09-24T00:00:00+08:00",
        valid_until: "2026-09-25T00:00:00+08:00",
        stops: [
          stop(0, { name: "深圳湾（示意）", why: "找个能看见海的地方，等太阳出来。", tip: "开车约 50 分钟（演示）。", fact_ids: ["fx-fact-szb-place", "fx-fact-szb-route"], lat: 22.515, lng: 113.944 }),
          stop(1, { name: "香港市区（示意）", why: "回程路过，买一点小零食。", tip: null, fact_ids: ["fx-fact-hkc-place"], lat: 22.282, lng: 114.158 }),
        ],
        owner_tips: [
          { text: "要带星球驾照", fact_ids: ["fx-fact-szb-licence"] },
          { text: "开车时只听歌，不看视频", fact_ids: ["fx-fact-szb-licence"] },
        ],
        rain_alternative: "下雨看不到日出，就改天再去",
        facts: [
          placeFact("fx-fact-szb-place", "深圳湾（示意）", "st-0", "fx-src-map-szb"),
          placeFact("fx-fact-hkc-place", "香港市区（示意）", "st-1", "fx-src-map-szb"),
          fact({ fact_id: "fx-fact-szb-route", category: "route", value: "开车约 50 分钟（演示）", subject: "st-0", source_ids: ["fx-src-road-szb"] }),
          fact({ fact_id: "fx-fact-szb-licence", category: "notice", value: "自己开车要带星球驾照（演示）", subject: "st-0", source_ids: ["fx-src-road-szb"] }),
        ],
        sources: [
          source({ source_id: "fx-src-map-szb", publisher: "示例地图核对（演示）", retrieved_at: "2026-09-23T19:40:00+08:00" }),
          source({ source_id: "fx-src-road-szb", url: "https://example.com/demo/road-notes", publisher: "示例路线资料（演示）", retrieved_at: "2026-09-23T19:45:00+08:00", published_at: "2026-09-15T00:00:00+08:00" }),
        ],
        // 用了驾校借车券：fare 仍是标价 20（演示世界里自己开车兜风的标价），实付 0、省下 20。
        journey: { journey_id: "fx-journey-shenzhen-bay", fare: 20, fare_waived: true },
        created_at: "2026-09-23T19:50:00+08:00",
      }),
      (rev) => [journal(rev, { phase: "plan", image_status: "processing", identity_mode: "photo", created_at: "2026-09-23T19:52:00+08:00" })],
    ),
  ),
};

/** 已回来：计划三站，回忆手账里只有主目的地有真实到访 → 只给它盖章，另两站写“下次”。实付路费 8 星币。回忆手账的图这次没画成，有重画票。 */
const cafe: PlanBundle = {
  wish: wish({
    wish_id: "fx-wish-harbour-cafe",
    status: "completed",
    destination_key: "fx-dest-harbour-cafe",
    destination_name: "香港的海边咖啡馆",
    city: "香港",
    owner_reason: "想找个靠窗的位置坐一会儿，看路上的人走来走去。",
    funds_goal: 8,
    plan_id: "fx-plan-harbour-cafe",
    plan_revision: 1,
    journey_id: "fx-journey-harbour-cafe",
  }),
  plan: plan(
    withJournals(
      revision({
        plan_id: "fx-plan-harbour-cafe",
        wish_id: "fx-wish-harbour-cafe",
        destination_key: "fx-dest-harbour-cafe",
        operation_id: "fx-op-cafe-1",
        title: "去海边咖啡馆坐坐",
        summary: "下午走过去，找个靠窗的位置坐一会儿；喝完去码头看船，天黑前回家。",
        valid_from: "2026-09-22T00:00:00+08:00",
        valid_until: "2026-09-23T00:00:00+08:00",
        stops: [
          stop(0, { name: "示例·海边咖啡馆（演示店）", why: "靠窗坐一会儿，点一杯游戏饮品。", tip: null, fact_ids: ["fx-fact-cafe-place"], lat: 22.2855, lng: 114.1577 }),
          stop(1, { name: "中环码头（示意）", why: "喝完去码头看船。", tip: null, fact_ids: ["fx-fact-cafe-central-place"], lat: 22.287, lng: 114.157 }),
          stop(2, { name: "香港市区（示意）", why: "顺路逛逛。", tip: null, fact_ids: ["fx-fact-cafe-hkc-place"], lat: 22.282, lng: 114.158 }),
        ],
        owner_tips: [{ text: "店里的鹦鹉居民会点头打招呼，它是星球居民", fact_ids: ["fx-fact-cafe-parrot"] }],
        rain_alternative: "下雨就在店里多坐一会儿",
        facts: [
          placeFact("fx-fact-cafe-place", "示例·海边咖啡馆（演示店）", "st-0", "fx-src-map-cafe"),
          placeFact("fx-fact-cafe-central-place", "中环码头（示意）", "st-1", "fx-src-map-cafe"),
          placeFact("fx-fact-cafe-hkc-place", "香港市区（示意）", "st-2", "fx-src-map-cafe"),
          fact({ fact_id: "fx-fact-cafe-parrot", category: "notice", value: "店里有一位鹦鹉居民（演示）", subject: "st-0", source_ids: ["fx-src-map-cafe"] }),
        ],
        sources: [source({ source_id: "fx-src-map-cafe", publisher: "示例地图核对（演示）", retrieved_at: "2026-09-21T19:30:00+08:00" })],
        journey: { journey_id: "fx-journey-harbour-cafe", fare: 8, fare_waived: false },
        created_at: "2026-09-21T19:40:00+08:00",
      }),
      (rev) => [
        // 出发前的计划页：没接插画（image_status 为空）。
        journal(rev, { phase: "plan", image_status: null, created_at: "2026-09-21T19:42:00+08:00" }),
        // 回来后的回忆页：只收真实到访事件（主目的地一站）；图这次没画成，有重画票；没有可用的参考照片，不画 TA（原因码只进“技术信息”）。
        journal(
          rev,
          { phase: "memory", image_status: "failed", redraw_ticket: "fx-redraw-cafe", identity_mode: "none", identity_note: "no_reference", created_at: "2026-09-22T19:00:00+08:00" },
          { 0: ["fx-journey-harbour-cafe:visit_started"] },
        ),
      ],
    ),
  ),
};

/** 已取消：没有出发，不盖章、也不写“下次”，也没有路费。还没有手账。 */
const airport: PlanBundle = {
  wish: wish({
    wish_id: "fx-wish-airport",
    status: "cancelled",
    destination_key: "fx-dest-airport",
    destination_name: "香港机场",
    city: "香港",
    owner_reason: "想去机场看飞机起飞，看它们一架一架钻进云里。",
    funds_goal: 10,
    plan_id: "fx-plan-airport",
    plan_revision: 1,
  }),
  plan: plan(
    revision({
      plan_id: "fx-plan-airport",
      wish_id: "fx-wish-airport",
      destination_key: "fx-dest-airport",
      operation_id: "fx-op-airport-1",
      title: "去机场看飞机",
      summary: "坐车去机场，在窗边看飞机起飞。",
      valid_from: "2026-09-21T00:00:00+08:00",
      valid_until: "2026-09-22T00:00:00+08:00",
      stops: [stop(0, { name: "香港机场（示意）", why: "找个能看见跑道的窗边。", tip: null, fact_ids: ["fx-fact-airport-place"], lat: 22.308, lng: 113.918 })],
      facts: [placeFact("fx-fact-airport-place", "香港机场（示意）", "st-0", "fx-src-map-airport")],
      sources: [source({ source_id: "fx-src-map-airport", publisher: "示例地图核对（演示）", retrieved_at: "2026-09-20T17:50:00+08:00" })],
      created_at: "2026-09-20T18:00:00+08:00",
    }),
  ),
};

/** 列表顺序：想去 / 准备中在前，出发之后的在后。演示时间都带 +08:00，页面暂定的时区（Asia/Shanghai）显示出来就是香港当地时间。 */
export const DEMO_PLANS: readonly PlanBundle[] = [tokyo, macau, westKowloon, shenzhenBay, cafe, airport];
