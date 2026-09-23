/**
 * 运行模式与 API 基址（唯一读取 import.meta.env 的地方）。
 * VITE_* 会进入客户端 bundle：这里只允许公开配置，禁止密钥。
 */

export type DataMode = "fixture" | "live";

function readMode(): DataMode {
  const raw = String(import.meta.env.VITE_PETSOUL_DATA_MODE ?? "fixture").trim().toLowerCase();
  if (raw === "live" || raw === "fixture") return raw;
  // 未知值按 fixture 处理并在控制台说明，绝不静默当作 live 连接后端。
  console.warn(`[petsoul] 未知的 VITE_PETSOUL_DATA_MODE=${raw}，已使用 fixture`);
  return "fixture";
}

export const env = {
  dataMode: readMode(),
  apiBase: String(import.meta.env.VITE_PETSOUL_API_BASE ?? "/api/v1/web").replace(/\/$/, ""),
  isDev: import.meta.env.DEV,
} as const;
