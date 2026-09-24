/**
 * 地图主状态面板里的旅行心愿那一行（TRV-06 第②期；接的是 world_map/panelNotes 的扩展点，world_map 目录已交还，以后只改这里）。
 * - 当前宠物有活动心愿（想去 / 可以出发）时一行“想去 {目的地} · {还差什么第一条}”，点进 /guides/wish；
 * - 先后在 NOTE_KINDS 里：来信 > 驾校 > 旅行心愿 > 系统提示；
 * - 只关于这只宠物：带 petId（心愿自己的 pet_id），面板显示的是别的宠物时由 arrangeNotes 滤掉；
 * - 数据走 ./data 的 useCurrentWish（fixture 演示、live 走 GET /travel/wish）；取不到、没有活动心愿时没有这一行，不造假。
 */
import type { PanelNote } from "@/features/world_map/panelNotes";
import { useCurrentWish } from "./data";
import { viewOfWish, wishNoteLine } from "./model";

export function useWishNote(): PanelNote | null {
  const wish = useCurrentWish();
  if (wish.state !== "ready" || !wish.data) return null;
  const text = wishNoteLine(viewOfWish(wish.data));
  return text ? { id: "wish", kind: "wish", text, to: "/guides/wish", petId: wish.data.pet_id } : null;
}
