import type { FarmWatch, GuardState } from "@/shared/contracts";

/**
 * 菜园“谁在看着”的统一说法：自家菜园（主人视角）与邻居菜园（访客视角）共用同一套等级。
 * 服务端裁决（`web_farm/service.py`）：
 * - 主人巡院（宠物都不在家时才有）：巡院期间去摘会被发现；
 * - 宠物在家：醒着的很容易发现、打盹的有可能发现，几只一起更难偷，但有封顶——**不是绝对防偷**；
 * - 没人看着：摘得到（仍受每批合计上限与每人一次限制）。
 * 不写具体概率（由服务端决定、可能调整）。拿不到“谁在看”（邻居页缺 `watch`、自家缺 `guarding_pets`）时只说“可能”。
 */
export type WatchLevel = "nobody" | "resting" | "awake" | "patrol" | "unknown";
export type WatchTone = "calm" | "careful" | "alert";

export const WATCH_TONE: Record<WatchLevel, WatchTone> = {
  nobody: "calm",
  resting: "careful",
  awake: "alert",
  patrol: "alert",
  unknown: "careful",
};

/** 邻居页：服务端给了 `watch` 就按它；旧数据没有时按 `guarded` 退回——有人看着但不知道是谁，只能说“可能”。 */
export function levelFromWatch(watch: FarmWatch | null | undefined, guarded: boolean): WatchLevel {
  switch (watch) {
    case "nobody":
      return "nobody";
    case "pet_resting":
      return "resting";
    case "pet_awake":
      return "awake";
    case "owner_patrol":
      return "patrol";
    default:
      return guarded ? "unknown" : "nobody";
  }
}

/** 自家菜园：`guarding_pets` 是“在家且醒着”的宠物；空数组 = 在家的都在打盹；字段缺失 = 不知道醒没醒。 */
export function levelFromGuard(guard: Pick<GuardState, "basis" | "guarding_pets">): WatchLevel {
  if (guard.basis === "owner_patrol") return "patrol";
  if (guard.basis === "pet_at_home") {
    if (guard.guarding_pets === undefined) return "unknown";
    return guard.guarding_pets.length > 0 ? "awake" : "resting";
  }
  return "nobody";
}

/** 去邻居家摘菜的人看到的一句话（门边泡泡）。 */
export function visitorWatchText(level: WatchLevel, petName: string): string {
  switch (level) {
    case "nobody":
      return "院子里没人看着，熟了的可以摘一颗。";
    case "resting":
      return `${petName} 在打盹——动作轻一点，也可能把 TA 惊醒。`;
    case "awake":
      return `${petName} 醒着守在院子里——很容易被发现。`;
    case "patrol":
      return `${petName} 的主人正在巡院——这时候去摘会被发现。`;
    case "unknown":
      return `有人看着 ${petName} 的菜园——去摘可能会被发现。`;
  }
}

/** 主人在自家菜园看到的一句话（门边泡泡）。巡院时写到几点为止。 */
export function ownerWatchText(level: WatchLevel, petName: string, until?: string | null): string {
  switch (level) {
    case "nobody":
      return `${petName} 出门了，院子里没人看着，邻居可能来摘一点。`;
    case "resting":
      return `${petName} 在家打盹，邻居来摘有可能被发现，也可能摘走一点。`;
    case "awake":
      return `${petName} 醒着守着菜园，邻居来摘很容易被发现，但不是绝对防偷。`;
    case "patrol":
      return until ? `你在巡院，守到 ${clockText(until)}；这段时间邻居来摘会被发现。` : "你在巡院；这段时间邻居来摘会被发现。";
    case "unknown":
      return `${petName} 在家看着菜园，邻居来摘可能被发现，但不是绝对防偷。`;
  }
}

/** 门牌 / 列表上的短状态（两页同一套词；只有巡院按视角区分“你”与“主人”）。 */
export function watchShort(level: WatchLevel, perspective: "owner" | "visitor"): string {
  if (level === "patrol") return perspective === "owner" ? "你在巡院" : "主人在巡院";
  return { nobody: "没人看着", resting: "TA 在打盹", awake: "TA 醒着守着", unknown: "有人看着" }[level];
}

function clockText(iso: string): string {
  return new Date(iso).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}
