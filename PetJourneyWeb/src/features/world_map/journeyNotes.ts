/**
 * 两种从“这一趟”来的提醒（第 1 步）：都只在行程快照对齐后出现，只关于面板上这只（带 petId）。
 * - 一起听 / 一起看（listen）：当前这一段（快照 current_leg_id）上还没结束、带媒体会话的车上活动；文字用服务端的 entry.label，
 *   能加入时后面加“· 一起听 / · 一起看”；点它在地图上打开播放面板（?sheet=media:<会话>），不换当前宠物。
 *   你已经在一起听这一段（本机播放器正跟着这个会话）时这一行不出现——播放条已经在了。
 * - 这趟旅途（trip，寻味）：快照有到达上下文、并且寻味推荐现在能用时才出现（food_discovery 的 useFoodPicksAvailable：
 *   /meta 里 food.recommendations 为 available）；标题用寻味模块自己的 foodCardTitle（按家所在的城市说：同城“在附近”、
 *   异地“到{city}后”、不知道家在哪“在{city}”），不再抄那句话。点它去 /journey/food（先把当前宠物换成面板上这只）。
 */
import type { PlayerState } from "@/features/companion_media/playerStore";
import { foodCardTitle } from "@/features/food_discovery/availability";
import { currentMediaEntry, type JourneyDetails } from "./journeyDetails";
import { sheetHref } from "./mapSheet";
import type { PanelNote } from "./panelNotes";

/** 本机播放器处在这些状态，就算“你已经在一起听 / 看了”（播放条在）。 */
const TOGETHER: ReadonlyArray<PlayerState["mode"]> = ["joining", "synced", "buffering", "blocked"];

/** 寻味那一行要的两样：推荐现在能不能用、家在哪座城市（面板上这只的家园快照 place.city；不知道为 null）。 */
export interface FoodNoteContext {
  available: boolean;
  homeCity: string | null;
}

export function journeyNotes(details: JourneyDetails, petId: string | null, player: Pick<PlayerState, "sessionId" | "mode">, food: FoodNoteContext): PanelNote[] {
  if (details.status !== "aligned" || !petId) return [];
  const { snapshot } = details;
  const notes: PanelNote[] = [];
  const entry = currentMediaEntry(snapshot);
  const together = entry !== null && player.sessionId === entry.media_session_id && TOGETHER.includes(player.mode);
  if (entry && !together) {
    const verb = entry.badge === "music" ? "一起听" : "一起看";
    notes.push({
      id: "listen",
      kind: "listen",
      text: entry.actions.includes("join") ? `${entry.label} · ${verb}` : entry.label,
      to: sheetHref(`media:${entry.media_session_id}`),
      onMap: true,
      petId,
    });
  }
  const arrival = snapshot.arrival_context;
  if (arrival && food.available) notes.push({ id: "trip", kind: "trip", text: foodCardTitle(arrival, food.homeCity), to: "/journey/food", petId });
  return notes;
}
