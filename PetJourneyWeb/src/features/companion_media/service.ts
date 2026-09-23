import type { CompanionSession, Participation } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { participationCounts } from "@/shared/media/anchor";
import type { CompanionMediaService, ServiceContext } from "@/shared/services/types";
import { fixtureMediaSessions } from "@/fixtures/media";
import { delay, fixtureEpoch } from "@/fixtures/world";

export function createLiveCompanionMediaService({ api }: ServiceContext): CompanionMediaService {
  const path = (id: string) => `/media/sessions/${encodeURIComponent(id)}`;
  return {
    session: (id) => api.request<CompanionSession>(path(id)),
    join: (id, deviceId) => api.request<Participation>(`${path(id)}/join`, { method: "POST", body: { device_id: deviceId } }),
    command: (id, body, key) => api.request<CompanionSession>(`${path(id)}/commands`, { method: "POST", body, idempotencyKey: key }),
    heartbeat: (id, body) => api.request<Participation>(`${path(id)}/heartbeat`, { method: "POST", body }),
    leave: (id, deviceId) => api.request<Participation>(`${path(id)}/leave`, { method: "POST", body: { device_id: deviceId } }),
  };
}

/**
 * fixture：在内存里模拟服务端语义（revision 校验、幂等键、驾驶禁视频、参与只按实际同步心跳累计）。
 * 这只证明客户端对契约的处理，不代表服务端同步已实现。
 */
export function createFixtureCompanionMediaService(): CompanionMediaService {
  let builtAt = fixtureEpoch();
  let sessions = fixtureMediaSessions();
  const seenKeys = new Map<string, CompanionSession>();
  const participation = new Map<string, Participation>();

  function get(id: string): CompanionSession {
    // “重置演示时间”后按新的 fixture 时间基准重建会话锚点。
    if (fixtureEpoch() !== builtAt) {
      builtAt = fixtureEpoch();
      sessions = fixtureMediaSessions();
    }
    const s = sessions[id];
    if (!s) throw new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: "没有找到这个同行会话。" });
    return s;
  }

  return {
    session: (id) => delay(get(id), 120),
    async join(id, deviceId) {
      get(id);
      const p: Participation = { session_id: id, device_id: deviceId, mode: "joining", since: new Date().toISOString(), last_heartbeat_at: null, counted_ms: 0 };
      participation.set(`${id}:${deviceId}`, p);
      return delay(p, 80);
    },
    async command(id, body, key) {
      const cached = seenKeys.get(key);
      if (cached) return delay(cached, 60);
      const s = get(id);
      if (body.session_revision !== s.revision) {
        throw new ApiError({ kind: "http", status: 409, code: "VERSION_CONFLICT", message: "会话已被更新，请刷新后再试。", details: { current: s.revision } });
      }
      const nowIso = new Date().toISOString();
      const position = body.position_ms ?? s.anchor.position_ms;
      const next: CompanionSession =
        body.command === "pause"
          ? { ...s, state: "paused", interrupt_reason: "joint_pause", anchor: { position_ms: position, server_time: nowIso, playback_rate: 1 }, revision: s.revision + 1 }
          : body.command === "resume"
            ? { ...s, state: "playing", interrupt_reason: null, anchor: { position_ms: position, server_time: nowIso, playback_rate: 1 }, revision: s.revision + 1 }
            : { ...s, anchor: { position_ms: body.command === "restart" ? 0 : position, server_time: nowIso, playback_rate: 1 }, revision: s.revision + 1 };
      sessions[id] = next;
      seenKeys.set(key, next);
      return delay(next, 120);
    },
    async heartbeat(id, body) {
      const key = `${id}:${body.device_id}`;
      const prev = participation.get(key);
      const now = Date.now();
      const s = get(id);
      const drift = body.position_ms - (s.state === "playing" ? s.anchor.position_ms + (now - Date.parse(s.anchor.server_time)) : s.anchor.position_ms);
      const lastBeat = prev?.last_heartbeat_at ? Date.parse(prev.last_heartbeat_at) : now;
      const counts = body.media_edition === s.media.edition && participationCounts(body.player_state, s.media.kind, drift, (now - lastBeat) / 1000);
      const next: Participation = {
        session_id: id,
        device_id: body.device_id,
        mode: body.player_state,
        since: prev?.since ?? new Date(now).toISOString(),
        last_heartbeat_at: new Date(now).toISOString(),
        counted_ms: (prev?.counted_ms ?? 0) + (counts && prev ? now - lastBeat : 0),
      };
      participation.set(key, next);
      return delay(next, 40);
    },
    async leave(id, deviceId) {
      const key = `${id}:${deviceId}`;
      const prev = participation.get(key);
      const next: Participation = { session_id: id, device_id: deviceId, mode: "left", since: prev?.since ?? new Date().toISOString(), last_heartbeat_at: prev?.last_heartbeat_at ?? null, counted_ms: prev?.counted_ms ?? 0 };
      participation.set(key, next);
      return delay(next, 40);
    },
  };
}
