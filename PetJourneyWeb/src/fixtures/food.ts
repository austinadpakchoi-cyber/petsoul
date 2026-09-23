/**
 * 寻味 fixture：同一条演示路线上的“清淡 / 浓郁”两组偏好，展示推荐卡的差异。
 * 全部分店是明确的“示例”店，不是真实商家；证据 source_kind=fixture，永不进入现实品质证据池。
 * 排序与分值是手写示例，不是算法输出；没有实际用餐反馈，不能证明推荐准确。
 */
import type {
  Branch,
  EvidenceCitation,
  FoodMode,
  FoodPreference,
  FoodRecommendation,
  FoodRecommendationList,
  FoodRecommendationRequestInput,
  PreferenceSubject,
} from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";

export const FOOD_VARIANTS = [
  { id: "light", label: "清淡" },
  { id: "rich", label: "浓郁" },
] as const;

const PROVENANCE_BASE = {
  fact_version: "fixture-facts-r0",
  rule_version: "fixture-no-algorithm",
  data_status: "fixture" as const,
  coverage_note: "演示资料：3 家示例分店、每家 1–2 道示例菜；不是全城结果，也不是真实口碑。",
};

function place(id: string, name: string, lat: number, lng: number): Branch["place"] {
  return { provider: "fixture", place_id: `fixture:${id}`, name, address: null, lat, lng, coord_system: "wgs84", category: "餐厅", source_updated_at: null, attribution: "演示资料", data_origin: "fixture" };
}

const BRANCHES = {
  noodle: { branch_id: "fixture:noodle-west", name: "示例·清汤面馆（西区店）", brand: "示例清汤面馆", place: place("noodle-west", "示例·清汤面馆", 22.305, 114.17), ratings: [] },
  congee: { branch_id: "fixture:congee-harbour", name: "示例·海港粥铺", brand: null, place: place("congee-harbour", "示例·海港粥铺", 22.301, 114.172), ratings: [] },
  curry: { branch_id: "fixture:curry-corner", name: "示例·街角咖喱小馆", brand: null, place: place("curry-corner", "示例·街角咖喱小馆", 22.309, 114.168), ratings: [] },
} satisfies Record<string, Branch>;

function cite(id: string, aspect: string, observation: string): EvidenceCitation {
  return { evidence_id: id, source_kind: "fixture", source_label: "演示资料", aspect, observation, observed_at: null, sample_count: 0 };
}

function rec(
  id: string,
  mode: FoodMode,
  branch: Branch,
  group: FoodRecommendation["group"],
  rank: number | null,
  dishes: FoodRecommendation["dishes"],
  reasons: string[],
  notSuitable: string[],
  unknowns: string[],
  scores: FoodRecommendation["scores"],
  prefVersion: number,
): FoodRecommendation {
  return {
    recommendation_id: id,
    mode,
    branch,
    dishes,
    scores,
    eligibility: group === "needs_verification" ? "needs_verification" : "eligible",
    group,
    rank,
    reasons,
    not_suitable_when: notSuitable,
    unknowns,
    provenance: { ...PROVENANCE_BASE, generated_at: new Date().toISOString(), preference_version: prefVersion },
    freshness: "fresh",
    itinerary_version: mode === "pet_virtual_explore" ? 1 : null,
    data_origin: "fixture",
  };
}

const DISH = {
  clearNoodle: { dish_id: "fixture:noodle-west:clear-noodle", branch_id: BRANCHES.noodle.branch_id, name: "清汤细面（示例）", price: { amount_minor: 4800, currency: "HKD" }, flavor_traits: ["汤底清", "面有嚼劲"] },
  fishCongee: { dish_id: "fixture:congee-harbour:fish-congee", branch_id: BRANCHES.congee.branch_id, name: "鱼片粥（示例）", price: null, flavor_traits: ["清淡", "绵"] },
  curryBeef: { dish_id: "fixture:curry-corner:curry-beef", branch_id: BRANCHES.curry.branch_id, name: "咖喱牛腩饭（示例）", price: { amount_minor: 6800, currency: "HKD" }, flavor_traits: ["浓郁", "香料", "微辣"] },
  richBroth: { dish_id: "fixture:noodle-west:rich-broth", branch_id: BRANCHES.noodle.branch_id, name: "浓汤牛骨面（示例）", price: { amount_minor: 5800, currency: "HKD" }, flavor_traits: ["汤底浓", "油润"] },
};

function listFor(variant: string, mode: FoodMode): FoodRecommendation[] {
  const pv = variant === "rich" ? 2 : 1;
  const petVoice = mode === "pet_virtual_explore";
  if (variant === "rich") {
    return [
      rec("fx-rec-rich-1", mode, BRANCHES.curry, "primary", 1,
        [{ dish: DISH.curryBeef, why: "资料提到香料层次明显、酱汁浓稠，符合“浓郁”偏好。", evidence: [cite("fx-ev-3", "风味", "（演示）酱汁浓稠、香料明显")] }],
        [petVoice ? "我记得你爱浓一点的味道，这家的咖喱闻起来就很有劲。" : "符合你确认的“浓郁、能吃一点辣”。", "离到站点步行约 10 分钟（示例距离）。"],
        ["如果今天想吃清淡，这家不合适。", "资料说偏辣，怕辣的同行人需要注意。"],
        ["当天是否营业需要核实", "是否能调低辣度需要问店家"],
        { quality: null, match: 0.86, value: 0.7, logistics: 0.8, uncertainty: 0.5 }, pv),
      rec("fx-rec-rich-2", mode, BRANCHES.noodle, "alternative", 2,
        [{ dish: DISH.richBroth, why: "同一家面馆的浓汤款；资料只覆盖这一道。", evidence: [cite("fx-ev-4", "汤底", "（演示）骨汤较浓")] }],
        ["和清淡组是同一家分店，但推荐的菜不同。"],
        ["赶时间时可能要等位（历史记录，不是实时队列）。"],
        ["价格日期未知", "排队情况需要到店确认"],
        { quality: null, match: 0.72, value: 0.6, logistics: 0.9, uncertainty: 0.55 }, pv),
    ];
  }
  return [
    rec("fx-rec-light-1", mode, BRANCHES.noodle, "primary", 1,
      [{ dish: DISH.clearNoodle, why: "资料主要提到面条口感，汤底清；有一条偏咸反馈。", evidence: [cite("fx-ev-1", "面条口感", "（演示）面有嚼劲"), cite("fx-ev-2", "咸度", "（演示）一位食客觉得汤略咸")] }],
      [petVoice ? "我记得你喜欢清淡。这家面馆在我落地后的路线上。" : "符合你确认的“清淡、少油”。", "在停留窗口内能从容吃完（示例时间）。"],
      ["对咸度敏感时不一定合适：有偏咸反馈。"],
      ["能否少盐需要问店家", "当天供应与排队情况未知"],
      { quality: null, match: 0.82, value: 0.75, logistics: 0.9, uncertainty: 0.45 }, pv),
    rec("fx-rec-light-2", mode, BRANCHES.congee, "explore", null,
      [{ dish: DISH.fishCongee, why: "只有地点资料和菜名，缺少可分析的口味证据。", evidence: [] }],
      ["菜名看起来清淡，但证据不足，放在“可以试试”。"],
      [],
      ["没有菜品评价证据", "价格未知", "营业时间未核实"],
      { quality: null, match: null, value: null, logistics: 0.85, uncertainty: 0.85 }, pv),
  ];
}

export function fixturePreference(petId: string, subject: PreferenceSubject, variant = "light"): FoodPreference {
  const rich = variant === "rich";
  return {
    preference_id: `fx-pref-${subject}-${variant}`,
    subject,
    pet_id: petId,
    version: rich ? 2 : 1,
    label: rich ? "浓郁" : "清淡",
    taste: rich ? { sweet: 0, salty: 1, spicy: 1, oily: 1, aromatic_spice: 2, rich_broth: 2, crispy: null } : { sweet: 0, salty: -2, spicy: -1, oily: -2, aromatic_spice: -1, rich_broth: -1, crispy: null },
    budget: subject === "owner" ? { amount_minor: 8000, currency: "HKD" } : { amount_minor: 30, currency: "travel_coin" },
    max_wait_minutes: subject === "owner" ? 20 : null,
    party_size: subject === "owner" ? 2 : null,
    restrictions: subject === "owner" ? [{ kind: "avoid", label: "不吃香菜（仅自己可见）", private: true }] : [],
    source: "fixture",
    updated_at: new Date().toISOString(),
  };
}

export function fixtureRecommend(body: FoodRecommendationRequestInput, variant = "light"): FoodRecommendationList {
  if (body.mode === "pet_virtual_explore" && !body.pet_context) {
    throw new ApiError({ kind: "http", status: 422, code: "VALIDATION_FAILED", message: "宠物探索需要门到门的到达与停留窗口。" });
  }
  if (body.mode === "owner_real_dining" && (!body.owner_context || body.pet_context)) {
    throw new ApiError({ kind: "http", status: 422, code: "VALIDATION_FAILED", message: "现实用餐只使用你自己的日期与位置。" });
  }
  const items = listFor(variant, body.mode);
  return {
    mode: body.mode,
    preference: fixturePreference(body.pet_id, body.mode === "owner_real_dining" ? "owner" : "pet", variant),
    items,
    shortfall_note: items.length < 3 ? `只有 ${items.length} 家有可用资料，不硬凑三个推荐。` : null,
    data_origin: "fixture",
  };
}

export function fixtureRecommendation(id: string): FoodRecommendation {
  for (const variant of ["light", "rich"]) {
    for (const mode of ["pet_virtual_explore", "owner_real_dining"] as const) {
      const found = listFor(variant, mode).find((r) => r.recommendation_id === id);
      if (found) return found;
    }
  }
  throw new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: "没有找到这条推荐。" });
}
