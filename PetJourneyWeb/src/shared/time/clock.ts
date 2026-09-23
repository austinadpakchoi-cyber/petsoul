import { useEffect, useState } from "react";

/**
 * 服务器时间校准：收到任何带 server_time 的快照时调用 calibrate，页面用 useNow() 取得校准后的“现在”。
 * 客户端时间只用于呈现插值；结算、到达、金币永远以服务端为准。
 */
let offsetMs = 0;

export function calibrate(serverTimeIso: string, receivedAtMs: number = Date.now()): void {
  const server = Date.parse(serverTimeIso);
  if (!Number.isNaN(server)) offsetMs = server - receivedAtMs;
}

export function serverNow(): number {
  return Date.now() + offsetMs;
}

/** 每 intervalMs 刷新一次的服务器校准时间；标签页回到前台时立即刷新。 */
export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(serverNow);
  useEffect(() => {
    const tick = () => setNow(serverNow());
    const timer = window.setInterval(tick, intervalMs);
    const onVisible = () => {
      if (document.visibilityState === "visible") tick();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [intervalMs]);
  return now;
}

export function formatDuration(ms: number): string {
  const total = Math.max(0, Math.round(ms / 60_000));
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (h === 0) return `${m} 分钟`;
  return m === 0 ? `${h} 小时` : `${h} 小时 ${m} 分`;
}

export function formatClock(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** 按 IANA 时区显示当地时刻（例如出发地/目的地当地时间）。 */
export function formatLocalTime(iso: string, timeZone: string): string {
  try {
    return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone }).format(new Date(iso));
  } catch {
    return new Date(iso).toISOString().slice(11, 16);
  }
}
