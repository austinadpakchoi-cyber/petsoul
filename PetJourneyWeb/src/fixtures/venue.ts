/**
 * 到访 fixture：一家明确的“示例”咖啡馆（不是真实商家）。真实商家资料区与原创动物世界内饰分开展示；
 * 没有依据时不编造菜单、价格、装修、员工或宠物准入。
 */
import type { Visit, VisitActionRequest } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { atMin } from "./world";

const visits: Record<string, Visit> = {
  "fx-visit-001": {
    visit_id: "fx-visit-001",
    journey_id: "fx-journey-001",
    pet_id: "fx-pet-001",
    place: {
      provider: "fixture",
      place_id: "fixture:cafe-otter",
      name: "示例·海边咖啡馆（演示店）",
      address: null,
      lat: 22.2855,
      lng: 114.1577,
      coord_system: "wgs84",
      category: "咖啡馆",
      source_updated_at: null,
      attribution: "演示资料：不对应真实商家",
      data_origin: "fixture",
    },
    state: "active",
    template: "cafe",
    planned_arrival_utc: atMin(-15),
    arrived_at: atMin(-12),
    leaving_at: atMin(40),
    recommendation_id: "fx-rec-light-1",
    activities: [
      { activity_id: "fx-va-seat", kind: "choose_seat", label: "选个座位", state: "available", result_text: null },
      { activity_id: "fx-va-drink", kind: "order_drink", label: "点一杯游戏饮品", state: "available", result_text: null },
      { activity_id: "fx-va-photo", kind: "take_photo", label: "拍一张合影", state: "available", result_text: null },
      { activity_id: "fx-va-greet", kind: "greet_resident", label: "和店里的居民打招呼", state: "available", result_text: null },
    ],
    interior_is_original: true,
    data_origin: "fixture",
  },
};

const RESULTS: Record<string, string> = {
  "fx-va-seat": "TA 挑了靠窗的位置，尾巴搭在椅背上。",
  "fx-va-drink": "点了一杯“云朵奶泡”（动物世界的游戏饮品，不是真实菜单）。",
  "fx-va-photo": "合影已送去冲洗，稍后会出现在通讯里（演示，未生成图片）。",
  "fx-va-greet": "店里的鹦鹉居民点了点头。它是星球居民，不是真实玩家。",
};

const done = new Map<string, Visit>();

export function fixtureVisit(visitId: string): Visit {
  const visit = visits[visitId];
  if (!visit) throw new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: "没有找到这次到访。" });
  return visit;
}

export function fixtureVisitAct(visitId: string, body: VisitActionRequest, key: string): Visit {
  const replay = done.get(key);
  if (replay) return replay;
  const visit = fixtureVisit(visitId);
  const next: Visit = {
    ...visit,
    activities: visit.activities.map((a) => (a.activity_id === body.activity_id ? { ...a, state: "done", result_text: RESULTS[a.activity_id] ?? "完成了。" } : a)),
  };
  visits[visitId] = next;
  done.set(key, next);
  return next;
}
