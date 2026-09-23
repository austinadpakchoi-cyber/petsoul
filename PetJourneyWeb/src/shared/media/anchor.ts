/** 播放锚点（与后端 app/companion_media/anchor.py 同语义）。媒体时钟独立，不驱动交通。 */
import type { MediaAnchor, MediaKind, MediaSessionState, ParticipationMode } from "@/shared/contracts";

export const SYNC_TOLERANCE_MS: Record<MediaKind, number> = { audio: 1000, video: 2000 };
export const HEARTBEAT_MAX_AGE_S = 30;

export function positionAt(anchor: MediaAnchor, state: MediaSessionState, durationMs: number, nowMs: number): number {
  if (state !== "playing") return Math.max(0, Math.min(anchor.position_ms, durationMs));
  const elapsed = nowMs - Date.parse(anchor.server_time);
  return Math.floor(Math.max(0, Math.min(anchor.position_ms + elapsed * anchor.playback_rate, durationMs)));
}

export function participationCounts(mode: ParticipationMode, kind: MediaKind, driftMs: number, heartbeatAgeS: number): boolean {
  return mode === "synced" && heartbeatAgeS <= HEARTBEAT_MAX_AGE_S && Math.abs(driftMs) <= SYNC_TOLERANCE_MS[kind];
}
