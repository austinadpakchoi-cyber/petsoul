/**
 * 回忆页入口上的一句话：只从对应服务的真实结果里数，不推断、不补。
 * 打工的三种状态各说各的：going 是“去上班的路上”，绝不写成在打工（方案第 4.1 节“计划不是正在做”）。
 * 页面上状态写在前、岗位名写在后：岗位名常是“在书店理书”这类说法，单独放在前面容易被读成“正在干活”。
 */
import type { CredentialSummary, JobRecord, PhotoRequestView } from "@/shared/contracts";

/** 已持有的证件：active（正在用）与 used（用过、留作纪念）。not_obtained / in_progress / expired 不算。 */
export function heldCredentialCount(list: readonly CredentialSummary[]): number {
  return list.filter((credential) => credential.status === "active" || credential.status === "used").length;
}

/** 打工记录的状态说法；不认识的状态返回 null（只写岗位名，不猜）。 */
export function jobStatusText(status: string): string | null {
  switch (status) {
    case "going":
      return "去上班的路上";
    case "working":
      return "在干活";
    case "done":
      return "干完了";
    default:
      return null;
  }
}

/** 最近一条打工记录：开始时间最晚的那条；时间读不出来的排在最后，同样早晚时保留原顺序。 */
export function latestJob(list: readonly JobRecord[]): JobRecord | null {
  let best: JobRecord | null = null;
  let bestAt = Number.NEGATIVE_INFINITY;
  for (const job of list) {
    const parsed = Date.parse(job.starts_at);
    const at = Number.isFinite(parsed) ? parsed : Number.NEGATIVE_INFINITY;
    if (best === null || at > bestAt) {
      best = job;
      bestAt = at;
    }
  }
  return best;
}

/** 相册里的照片：画好了的（ready）才算一张；还在画的（processing）单独数。没画成、结果未确认的不算照片。 */
export function photoCounts(list: readonly PhotoRequestView[]): { ready: number; drawing: number } {
  let ready = 0;
  let drawing = 0;
  for (const item of list) {
    if (item.photo_status === "ready") ready += 1;
    else if (item.photo_status === "processing") drawing += 1;
  }
  return { ready, drawing };
}
