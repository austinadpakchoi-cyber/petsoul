/**
 * 从小窝回到地图并对准 TA（方案 v2.1 第 5 节“回到地图并对准 TA”）。
 * 小窝的“‹ 地图”与“我出门啦”便笺都去 mapFocusHref(当前宠物)，即 /map?focus=<宠物 id>。
 * 地图读到后选中并跟随这只宠物、不接上次存下的镜头；处理完用 replace 去掉参数，刷新、前进后退都不会再触发。
 * 只认当前家庭里的宠物（acceptedFocus），别的值忽略；从别处进地图（底栏、深链）不带参数，照旧接上次的状态。
 */
import type { WorldScene } from "./model";

export const FOCUS_PARAM = "focus";

/** 回到地图并对准这只宠物的地址；不知道是哪只时就是普通的地图首页。 */
export function mapFocusHref(petId: string | null | undefined): string {
  return petId ? `/map?${FOCUS_PARAM}=${encodeURIComponent(petId)}` : "/map";
}

/**
 * 地址里要对准的宠物，认不认：必须是地图上自己家的宠物（我的 / 家人的）；
 * live 还要在当前家庭的宠物名单里（householdPetIds）。演示模式没有家庭名单（传 null），演示场景里自己家的就算。
 */
export function acceptedFocus(requested: string | null, scene: WorldScene, householdPetIds: ReadonlySet<string> | null): string | null {
  if (!requested) return null;
  const pet = scene.pets.find((p) => p.petId === requested);
  if (!pet || (pet.relation !== "mine" && pet.relation !== "household")) return null;
  return householdPetIds === null || householdPetIds.has(requested) ? requested : null;
}
