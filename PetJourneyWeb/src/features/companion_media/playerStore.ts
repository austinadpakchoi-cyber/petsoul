/**
 * 主人设备上的真实播放状态（与宠物活动、服务器媒体会话分开保存）。
 * - “跟着 TA”：加载同一版本 → seek 到服务器锚点 → 实际 playing 且偏差在容忍内才算 synced；
 * - “自己从头”：solo，不改变宠物进度，不标同步；
 * - 缓冲/被浏览器拦截/加载失败 → buffering / blocked / failed，绝不先显示“已同步”。
 * 媒体元素跨面板开合持久存在：收起面板音频可继续；视频收起时暂停你的播放并明确提示。
 */
import { useSyncExternalStore } from "react";
import type {
  CompanionHeartbeatRequest,
  CompanionSession,
  MediaKind,
  ParticipationMode,
} from "@/shared/contracts";
import { positionAt, SYNC_TOLERANCE_MS } from "@/shared/media/anchor";
import { serverNow } from "@/shared/time/clock";

export interface PlayerState {
  sessionId: string | null;
  edition: string | null;
  kind: MediaKind | null;
  title: string | null;
  mode: ParticipationMode;
  localMs: number;
  driftMs: number | null;
  message: string | null;
}

const initial: PlayerState = {
  sessionId: null,
  edition: null,
  kind: null,
  title: null,
  mode: "not_joined",
  localMs: 0,
  driftMs: null,
  message: null,
};

let state: PlayerState = initial;
const listeners = new Set<() => void>();
let element: HTMLMediaElement | null = null;
let activeSession: CompanionSession | null = null;
let driftTimer: number | null = null;
let heartbeatTimer: number | null = null;
let sourceKey: string | null = null;
let generation = 0;
let joined = false;
let hasPlayed = false;
export function getPlayerState(): PlayerState {
  return state;
}

/**
 * 参与上报（服务器只按有界心跳累计“实际同步”的陪伴时长）：加入 → 每 10 秒心跳（当前真实状态与播放位置）→ 离开。
 * 由同行影音模块用 CompanionMediaService 注册；上报失败不影响本地播放，也不会把本地状态当成已计入。
 */
export interface ParticipationReporter {
  join(sessionId: string, deviceId: string): Promise<unknown>;
  heartbeat(
    sessionId: string,
    body: CompanionHeartbeatRequest,
  ): Promise<unknown>;
  leave(sessionId: string, deviceId: string): Promise<unknown>;
}
let reporter: ParticipationReporter | null = null;
const HEARTBEAT_MS = 10_000;

export function setParticipationReporter(
  next: ParticipationReporter | null,
): void {
  reporter = next;
}

function sendHeartbeat() {
  if (!reporter || !state.sessionId || !state.edition) return;
  reporter
    .heartbeat(state.sessionId, {
      device_id: deviceId(),
      player_state: state.mode,
      position_ms: element ? Math.round(element.currentTime * 1000) : 0,
      media_edition: state.edition,
      client_time: new Date().toISOString(),
    })
    .catch(() => undefined);
}

function startHeartbeat() {
  stopHeartbeat();
  heartbeatTimer = window.setInterval(sendHeartbeat, HEARTBEAT_MS);
}

function stopHeartbeat() {
  if (heartbeatTimer !== null) window.clearInterval(heartbeatTimer);
  heartbeatTimer = null;
}

function set(patch: Partial<PlayerState>) {
  const before = state.mode;
  state = { ...state, ...patch };
  listeners.forEach((l) => l());
  // 状态变化（例如刚真正同步上、开始缓冲、被拦截）立即上报一次，服务器据此判断是否计入。
  if (patch.mode && patch.mode !== before && heartbeatTimer !== null)
    sendHeartbeat();
}

export function usePlayer(): PlayerState {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => state,
    () => state,
  );
}

export function getMediaElement(): HTMLMediaElement | null {
  return element;
}

function ensureElement(kind: MediaKind): HTMLMediaElement {
  if (
    element &&
    element.tagName.toLowerCase() === (kind === "video" ? "video" : "audio")
  )
    return element;
  disposeElement(); // 只换掉旧的媒体元素；不清空刚设置的会话状态与心跳
  const el = document.createElement(kind === "video" ? "video" : "audio");
  el.preload = "auto";
  if (el instanceof HTMLVideoElement) {
    el.playsInline = true;
    el.setAttribute("playsinline", "");
    el.controls = false;
    el.className = "ps-media-video";
  }
  el.addEventListener("waiting", () => {
    if (
      element === el &&
      (state.mode === "synced" || state.mode === "joining")
    ) {
      hasPlayed = false;
      set({ mode: "buffering", message: "你这边正在缓冲，TA 那边没有停下。" });
    }
  });
  el.addEventListener("playing", () => {
    if (element === el) {
      hasPlayed = true;
      evaluateSync();
    }
  });
  el.addEventListener("timeupdate", () => {
    if (element === el) set({ localMs: Math.round(el.currentTime * 1000) });
  });
  el.addEventListener("error", () => {
    if (element === el && state.mode !== "left") {
      stopDriftCheck();
      stopHeartbeat();
      set({
        mode: "failed",
        message: "这段素材没能加载（文件不可用或网络中断）。",
      });
    }
  });
  el.addEventListener("ended", () => {
    if (element === el) {
      stopDriftCheck();
      stopHeartbeat();
      set({
        mode: state.mode === "solo" ? "solo" : "left",
        message: "这一段播完了。",
      });
    }
  });
  element = el;
  if (kind === "audio") {
    el.hidden = true;
    el.dataset.petsoulPlayer = "audio";
    document.body.appendChild(el);
  }
  return el;
}

function evaluateSync() {
  if (!element || !activeSession || !joined) return;
  if (!["joining", "synced", "buffering"].includes(state.mode)) return;
  const target = positionAt(
    activeSession.anchor,
    activeSession.state,
    activeSession.media.duration_ms,
    serverNow(),
  );
  const drift = Math.round(element.currentTime * 1000) - target;
  const tolerance = SYNC_TOLERANCE_MS[activeSession.media.kind];
  if (activeSession.state === "paused") {
    set({ driftMs: drift, mode: "synced", message: "和 TA 一起暂停中。" });
    return;
  }
  if (activeSession.state !== "playing") return;
  if (!hasPlayed) return;
  if (!element.paused && Math.abs(drift) <= tolerance) {
    set({ driftMs: drift, mode: "synced", message: null });
  } else if (!element.paused) {
    element.currentTime = target / 1000;
    set({
      driftMs: drift,
      mode: "buffering",
      message: "正在对齐到 TA 的进度…",
    });
  }
}

function loadSource(session: CompanionSession) {
  const el = ensureElement(session.media.kind);
  if (!session.media.src_url) throw new Error("no src");
  const nextKey = `${session.media.kind}:${session.media.edition}:${session.media.src_url}`;
  if (sourceKey !== nextKey || !el.src) {
    el.src = session.media.src_url;
    sourceKey = nextKey;
    el.load();
  }
  return el;
}

/** 必须在用户点击处理函数中同步调用（浏览器有声播放需要用户手势）。 */
export function joinSession(session: CompanionSession): void {
  const attempt = ++generation;
  joined = false;
  hasPlayed = false;
  stopHeartbeat();
  stopDriftCheck();
  if (state.sessionId && state.sessionId !== session.session_id)
    reporter?.leave(state.sessionId, deviceId()).catch(() => undefined);
  element?.pause();
  activeSession = session;
  set({
    sessionId: session.session_id,
    edition: session.media.edition,
    kind: session.media.kind,
    title: session.media.title,
    mode: "joining",
    message: null,
    driftMs: null,
  });
  if (session.state === "ended" || session.state === "interrupted") {
    set({
      mode: "left",
      message:
        session.state === "ended"
          ? "这一段已经播完了。"
          : "到站了，TA 的进度已保存，下一段再一起。",
    });
    return;
  }
  if (session.media.availability !== "in_app_sync" || !session.media.src_url) {
    set({
      mode: "failed",
      message: "这部作品只能在外部平台打开，无法在这里一起同步。",
    });
    return;
  }
  const acknowledgement =
    reporter?.join(session.session_id, deviceId()) ?? Promise.resolve();
  void acknowledgement
    .then(() => {
      if (
        attempt !== generation ||
        state.mode === "left" ||
        state.mode === "failed"
      )
        return;
      joined = true;
      evaluateSync();
      startHeartbeat();
    })
    .catch(() => {
      if (attempt !== generation) return;
      element?.pause();
      stopHeartbeat();
      set({
        mode: "failed",
        message: "没有加入这次会话，请点重试；不会计作同步陪伴。",
      });
    });
  const el = loadSource(session);
  const target = positionAt(
    session.anchor,
    session.state,
    session.media.duration_ms,
    serverNow(),
  );
  const seek = () => {
    if (attempt !== generation || element !== el) return;
    el.currentTime =
      Math.max(0, Math.min(target, session.media.duration_ms - 250)) / 1000;
  };
  if (el.readyState >= 1) seek();
  else el.addEventListener("loadedmetadata", seek, { once: true });
  if (session.state !== "playing") {
    el.pause();
    set({ message: "正在加入暂停中的会话…" });
    return;
  }
  el.play().catch((err: unknown) => {
    if (attempt !== generation) return;
    const name = err instanceof DOMException ? err.name : "";
    if (name === "NotAllowedError")
      set({
        mode: "blocked",
        message: "浏览器拦下了播放，请再点一次“跟着 TA”。",
      });
    else if (name === "NotSupportedError")
      set({
        mode: "failed",
        message: "这段素材没能加载（文件不可用或格式不支持），可以稍后重试。",
      });
    else if (state.mode !== "failed")
      set({ mode: "failed", message: "播放没有开始。" });
  });
  startDriftCheck();
}

export function playSolo(session: CompanionSession): void {
  ++generation;
  joined = false;
  stopDriftCheck();
  activeSession = session;
  set({
    sessionId: session.session_id,
    edition: session.media.edition,
    kind: session.media.kind,
    title: session.media.title,
    mode: "solo",
    message: "你在独立回听，TA 的进度不受影响。",
    driftMs: null,
  });
  startHeartbeat(); // 如实上报 solo：独立回听不计入同步陪伴
  if (!session.media.src_url) {
    set({ mode: "failed", message: "这部作品没有可在这里播放的版本。" });
    return;
  }
  const el = loadSource(session);
  el.currentTime = 0;
  el.play().catch(() =>
    set({ mode: "blocked", message: "浏览器拦下了播放，请再点一次。" }),
  );
}

/** 服务器会话更新（例如共同暂停/恢复、到站中断）后调用，重新对齐。 */
export function onSessionUpdate(session: CompanionSession): void {
  if (
    state.sessionId !== session.session_id ||
    !["joining", "synced", "buffering"].includes(state.mode)
  )
    return;
  activeSession = session;
  if (!element) return;
  if (session.state !== "playing") {
    element.pause();
    if (session.state === "ended" || session.state === "interrupted") {
      stopDriftCheck();
      stopHeartbeat();
      joined = false;
      set({
        mode: "left",
        message:
          session.state === "interrupted"
            ? "到站了，进度已保存。"
            : "这一段播完了。",
      });
      return;
    }
    element.currentTime = session.anchor.position_ms / 1000;
    set({ localMs: session.anchor.position_ms });
    set({ message: "和 TA 一起暂停中。" });
  } else if (
    element.paused &&
    (state.mode === "synced" || state.mode === "buffering")
  ) {
    hasPlayed = false;
    set({ mode: "buffering", message: "正在继续播放，重新对齐到 TA…" });
    element.currentTime =
      positionAt(
        session.anchor,
        session.state,
        session.media.duration_ms,
        serverNow(),
      ) / 1000;
    element
      .play()
      .catch(() =>
        set({
          mode: "blocked",
          message: "浏览器拦下了播放，请再点一次“跟着 TA”。",
        }),
      );
  }
}

export function leaveSession(): void {
  ++generation;
  joined = false;
  element?.pause();
  stopDriftCheck();
  stopHeartbeat();
  if (state.sessionId)
    reporter?.leave(state.sessionId, deviceId()).catch(() => undefined);
  set({ mode: "left", message: "你暂时离开了，TA 还在继续。" });
}

/** 视频面板收起：暂停你的播放并如实提示（不假装仍在一起看）。音频不受影响。 */
export function onSheetCollapsed(): void {
  if (state.kind === "video" && element && !element.paused) {
    leaveSession();
    set({
      mode: "left",
      message: "收起面板后你的视频已暂停，TA 仍在看；点开可重新跟上。",
    });
  }
}

function startDriftCheck() {
  stopDriftCheck();
  driftTimer = window.setInterval(() => {
    if (state.mode === "synced" || state.mode === "buffering") evaluateSync();
  }, 2000);
}

function stopDriftCheck() {
  if (driftTimer !== null) window.clearInterval(driftTimer);
  driftTimer = null;
}

function disposeElement(): void {
  if (element) {
    element.pause();
    element.removeAttribute("src");
    element.load();
    element.remove();
  }
  element = null;
  sourceKey = null;
}

export function teardown(): void {
  ++generation;
  joined = false;
  hasPlayed = false;
  stopDriftCheck();
  if (heartbeatTimer !== null && state.sessionId)
    reporter?.leave(state.sessionId, deviceId()).catch(() => undefined);
  stopHeartbeat();
  disposeElement();
  activeSession = null;
  state = initial;
  listeners.forEach((l) => l());
}

export function deviceId(): string {
  try {
    const existing = localStorage.getItem("petsoul.device_id");
    if (existing) return existing;
    const created = `dev-${Math.random().toString(36).slice(2, 12)}`;
    localStorage.setItem("petsoul.device_id", created);
    return created;
  } catch {
    return "dev-ephemeral";
  }
}
