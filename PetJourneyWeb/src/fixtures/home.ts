/**
 * 家园 fixture：宠物外出旅行、主人守家；一小块菜园与统一钱包（travel_coin 唯一口径）。
 * 作物、数值均为演示值，不是已冻结的经济配置。农场动作按幂等键只结算一次（模拟服务端语义）。
 */
import type { FarmActionRequestInput, FarmActionResult, GuardState, HomeSnapshot, InventoryItem, MarketResult, MarketView, PatrolResult, PlotSummary, ResidentOrder } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { fixtureHomeWelcome } from "./reception";
import { atMin, fixturePet } from "./world";

interface HomeState {
  version: number;
  balance: number;
  plots: PlotSummary[];
  pantry: Record<string, number>;
  patrolUntil: number | null;
  patrolStarted: number | null;
  fulfilled: Set<string>;
}

const LABELS: Record<string, { label: string; price: number }> = {
  sun_pea: { label: "太阳豌豆", price: 2 },
  star_tomato: { label: "星星番茄", price: 2 },
  moon_radish: { label: "月光萝卜", price: 3 },
  sea_salt_pea: { label: "海盐豌豆", price: 4 },
};

const state: HomeState = {
  version: 1,
  balance: 120,
  plots: [
    { plot_id: "fx-plot-1", cycle_id: "fx-cycle-1", crop_key: "star_tomato", crop_label: "星星番茄", stage: "ripe", ripe_at: atMin(-30), steal_total: 3, steal_remaining: 2 },
    { plot_id: "fx-plot-2", cycle_id: "fx-cycle-2", crop_key: "moon_radish", crop_label: "月光萝卜", stage: "growing", ripe_at: atMin(95), steal_total: 3, steal_remaining: 3 },
    { plot_id: "fx-plot-3", cycle_id: null, crop_key: null, crop_label: null, stage: "empty", ripe_at: null, steal_total: null, steal_remaining: null },
  ],
  pantry: { star_tomato: 3 },
  patrolUntil: null,
  patrolStarted: null,
  fulfilled: new Set(),
};

function pantryList(): InventoryItem[] {
  return Object.entries(state.pantry)
    .filter(([, qty]) => qty > 0)
    .map(([key, qty]) => ({ item_key: key, label: LABELS[key]?.label ?? key, qty, unit_price: LABELS[key]?.price ?? 1, tradable: true }));
}

function guardState(): GuardState {
  const now = Date.now();
  const until = state.patrolUntil && state.patrolUntil > now ? new Date(state.patrolUntil).toISOString() : null;
  const next = state.patrolStarted && state.patrolStarted + 30 * 60_000 > now ? new Date(state.patrolStarted + 30 * 60_000).toISOString() : null;
  // 演示宠物在旅途中：只有主人巡院窗口内才算有人守着。
  return until ? { guarding: true, basis: "owner_patrol", until, next_patrol_at: next } : { guarding: false, basis: "none", until: null, next_patrol_at: next };
}

function wallet() {
  return { currency: "travel_coin", balance: state.balance, updated_at: new Date().toISOString() };
}

export function fixturePatrol(): PatrolResult {
  const now = Date.now();
  if (!(state.patrolUntil && state.patrolUntil > now)) {
    if (state.patrolStarted && state.patrolStarted + 30 * 60_000 > now) {
      throw new ApiError({ kind: "http", status: 409, code: "CONFLICT", message: "刚巡过院，歇一会儿再去。", details: { reason: "cooldown" } });
    }
    state.patrolStarted = now;
    state.patrolUntil = now + 10 * 60_000;
  }
  return { guard: guardState(), message: "你在院子里转了一圈，这段时间邻居摘不走菜。（演示）" };
}

function fixtureOrders(): ResidentOrder[] {
  const end = new Date();
  end.setHours(24, 0, 0, 0);
  const orders = [
    { order_id: "fx-order-1", resident: "鹦鹉邮差", item_key: "star_tomato", qty: 3, reward: 9 },
    { order_id: "fx-order-2", resident: "松鼠面包师", item_key: "sun_pea", qty: 2, reward: 6 },
  ];
  return orders.map((o) => ({
    ...o,
    item_label: LABELS[o.item_key].label,
    shop_value: o.qty * LABELS[o.item_key].price,
    fulfilled: state.fulfilled.has(o.order_id),
    can_fulfill: !state.fulfilled.has(o.order_id) && (state.pantry[o.item_key] ?? 0) >= o.qty,
    expires_at: end.toISOString(),
  }));
}

export function fixtureMarket(): MarketView {
  return {
    pantry: pantryList(),
    wallet: wallet(),
    orders: fixtureOrders(),
    player_listing_enabled: false,
    player_listing_note: "玩家挂牌交易还没开放；这里是杂货铺和居民订单（演示）。",
    data_origin: "fixture",
  };
}

const marketSettled = new Map<string, MarketResult>();

export function fixtureSell(itemKey: string, qty: number, key: string): MarketResult {
  const replay = marketSettled.get(key);
  if (replay) return replay;
  if ((state.pantry[itemKey] ?? 0) < qty) throw new ApiError({ kind: "http", status: 409, code: "CONFLICT", message: "仓库里不够。", details: { reason: "not_enough" } });
  state.pantry[itemKey] -= qty;
  const coins = qty * (LABELS[itemKey]?.price ?? 1);
  state.balance += coins;
  const label = LABELS[itemKey]?.label ?? itemKey;
  const result: MarketResult = { wallet: wallet(), pantry: pantryList(), gained_coins: coins, message: "杂货铺收下了 " + qty + " 个" + label + "，+" + coins + " 旅费。（演示）" };
  marketSettled.set(key, result);
  return result;
}

export function fixtureFulfill(orderId: string): MarketResult {
  const order = fixtureOrders().find((o) => o.order_id === orderId);
  if (!order) throw new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: "没有这张订单。" });
  if (!order.fulfilled) {
    if (!order.can_fulfill) throw new ApiError({ kind: "http", status: 409, code: "CONFLICT", message: "仓库里不够。", details: { reason: "not_enough" } });
    state.pantry[order.item_key] -= order.qty;
    state.balance += order.reward;
    state.fulfilled.add(orderId);
  }
  return { wallet: wallet(), pantry: pantryList(), gained_coins: order.reward, message: order.resident + "收到了 " + order.qty + " 个" + order.item_label + "。（演示）" };
}


const settled = new Map<string, FarmActionResult>();

export function fixtureHomeSnapshot(): HomeSnapshot {
  return {
    home_id: "fx-home-001",
    server_time: new Date().toISOString(),
    version: state.version,
    pet: fixturePet,
    presence: "in_transit",
    guard: guardState(),
    wallet: wallet(),
    pantry: pantryList(),
    plots: state.plots,
    journey: { journey_id: "fx-journey-001", itinerary_version: 1, headline: "TA 正在旅途中（演示行程）", current_visit_id: null, current_leg_id: "fx-leg-flight" },
    welcome: fixtureHomeWelcome(fixturePet.pet_id),
    unread: { messages: 2, circle: 3 },
    missing_capabilities: [],
    data_origin: "fixture",
  };
}

export function fixtureFarmAct(body: FarmActionRequestInput, key: string): FarmActionResult {
  const replay = settled.get(key);
  if (replay) return replay;
  const plot = state.plots.find((p) => p.plot_id === body.plot_id);
  if (!plot) throw new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: "没有这块地。" });
  const gained: string[] = [];
  if (body.action === "harvest") {
    if (plot.stage !== "ripe") throw new ApiError({ kind: "http", status: 409, code: "CONFLICT", message: "还没成熟。" });
    plot.stage = "harvested";
    const cropKey = plot.crop_key ?? "sun_pea";
    state.pantry[cropKey] = (state.pantry[cropKey] ?? 0) + 3;
    gained.push(`${plot.crop_label} ×3 进了仓库`);
  } else if (body.action === "plant") {
    if (plot.stage !== "empty" && plot.stage !== "harvested") throw new ApiError({ kind: "http", status: 409, code: "CONFLICT", message: "这块地还在种着。" });
    Object.assign(plot, { stage: "growing", crop_key: body.crop_key ?? "sun_pea", crop_label: "太阳豌豆", ripe_at: atMin(120), cycle_id: `fx-cycle-${Date.now()}`, steal_total: 3, steal_remaining: 3 });
  } else {
    throw new ApiError({ kind: "http", status: 409, code: "CONFLICT", message: "自己家的菜不用偷。" });
  }
  state.version += 1;
  const result: FarmActionResult = { plot: { ...plot }, wallet: wallet(), gained_items: gained };
  settled.set(key, result);
  return result;
}
