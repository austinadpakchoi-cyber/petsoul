/**
 * 这次到访是什么样的地方：只按服务端给的字段分（场景模板 visit.template、地点来源 place.provider），不按地点名字猜。
 * - template 为 cafe / restaurant：有门店的地方——画店内原创场景，写“到店”；
 *   地图供应商（高德 / Google）或演示资料给的地点才有“商家资料”；星球内的地方（provider = world，世界规则设定）没有商家，只写“关于这个地方”；
 * - template 为 park：户外（家附近的小路、公园）——不画店内，画一小片户外，不写“到店”；
 * - 其他（generic：进城逛逛、打工）：不画场景图，不写“到店”。
 */
import type { PlaceProvider, Visit, VisitState } from "@/shared/contracts";

export type VisitSetting = "shop" | "outdoor" | "other";

export function visitSetting(visit: Pick<Visit, "template">): VisitSetting {
  if (visit.template === "cafe" || visit.template === "restaurant") return "shop";
  if (visit.template === "park") return "outdoor";
  return "other";
}

/** 有门店、而且地点资料来自地图供应商或演示资料时，才有“商家资料”。 */
export function hasMerchantInfo(visit: Pick<Visit, "template" | "place">): boolean {
  return visitSetting(visit) === "shop" && visit.place.provider !== "world";
}

/** 地点资料缺来源说明时的中文说法（不露 amap / world 这类代码）。 */
export const PROVIDER_TEXT: Record<PlaceProvider, string> = {
  amap: "地点资料：高德地图",
  google: "地点资料：Google 地图",
  fixture: "演示资料：不对应真实商家",
  world: "星球内的地方：世界规则设定，不对应现实地址或商家",
};

const SHOP_STATE: Record<VisitState, string> = { planned: "计划中", travelling: "在路上", arrived: "刚到", active: "在店里", completed: "已离店", cancelled: "已取消" };
const AWAY_STATE: Record<VisitState, string> = { planned: "计划中", travelling: "在路上", arrived: "刚到", active: "在这儿", completed: "已离开", cancelled: "已取消" };

export function visitStateText(state: VisitState, setting: VisitSetting): string {
  return (setting === "shop" ? SHOP_STATE : AWAY_STATE)[state];
}

/** 顶栏副标题与“手帐”那一句：只有门店写“到店”。 */
export function visitSubtitle(setting: VisitSetting): string {
  return setting === "shop" ? "到店活动" : setting === "outdoor" ? "出门散步" : "出门活动";
}

export function visitStory(setting: VisitSetting, petName: string): string {
  return setting === "shop" ? `${petName} 的到店手帐` : `${petName} 的出门手帐`;
}
