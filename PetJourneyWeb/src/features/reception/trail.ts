/**
 * 补充叮嘱的“来路”（2026-09-24 巡检 P1：“先回去”“完成”写死回“我的”，从通讯器、小窝进来的也被带去“我的”）。
 * 和左上角返回键（shared/ui TopBar）同一条规矩：站内有来路就回来路；直接打开、没有站内上一页时回上级页“我的”。
 * 接待页点“整理”去整理页时多走了一步，所以把“离开补充流程要退几步”带过去：
 * 在整理页离开，一次退回来路，而不是退回接待页；回接待也是退一步，不再压一页新的接待（否则接待页的“先回去”会退回整理页）。
 */
import type { Location, NavigateFunction } from "react-router";

/** 补充叮嘱的上级页：入口在“我的”。 */
export const SUPPLEMENT_PARENT = "/me";

/** 整理页从接待页带来的路由状态。 */
export interface NotesTrail {
  fromReception: true;
  /** 离开补充流程要退几步回到来路；0 = 接待页是直接打开的，没有来路，去上级页。 */
  leaveSteps: number;
}

/** 这一页有没有站内上一页：与 TopBar 同一个判断（直接打开时，初始条目的 key 是 "default"）。 */
export function hasInAppHistory(location: Location): boolean {
  return location.key !== "default";
}

/** 接待页去整理页时带上的状态。 */
export function trailFromReception(location: Location): NotesTrail {
  return { fromReception: true, leaveSteps: hasInAppHistory(location) ? 2 : 0 };
}

/** 整理页读到的来路；不是从接待页点“整理”进来的（直接打开、刷新丢了状态）就是 null。 */
export function notesTrail(location: Location): NotesTrail | null {
  const state = location.state as Partial<NotesTrail> | null;
  if (state?.fromReception !== true || typeof state.leaveSteps !== "number" || state.leaveSteps < 0) return null;
  return { fromReception: true, leaveSteps: Math.floor(state.leaveSteps) };
}

/** 离开补充流程：有来路就退回来路，没有就去上级页“我的”。 */
export function leaveSupplement(navigate: NavigateFunction, steps: number): void {
  if (steps > 0) void navigate(-steps);
  else void navigate(SUPPLEMENT_PARENT);
}
