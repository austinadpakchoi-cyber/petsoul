#!/usr/bin/env node
/**
 * 运营后台演示后端（仅本地）：隔离数据库、供应商全部 mock 且总开关关闭、调度器与世界任务都不启动。
 *
 *   node scripts/dev-backend.mjs          # 127.0.0.1:18790，数据 PetJourneyBackend/data/web-admin-demo/
 *   PETSOUL_ADMIN_BACKEND_PORT=18791 node scripts/dev-backend.mjs
 *   PETSOUL_ADMIN_WORLD=on node scripts/dev-backend.mjs   # 想看世界真的在推进时才打开
 *
 * 注意：
 * - 世界任务默认 **off**：后台的查询页面本来就不该推进世界，关掉能让"读接口纯读"这件事一眼可查；
 * - 供应商密钥变量显式置空，即使 PetJourneyBackend/.env 里有真实密钥也读不到（不会产生任何付费调用）；
 * - 演示库由 `python scripts/seed_admin_demo.py` 生成；这个脚本不会自己造数据。
 */
import { spawn } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const backendDir = resolve(here, "..", "..", "PetJourneyBackend");
const port = process.env.PETSOUL_ADMIN_BACKEND_PORT ?? "18790";
const dataDir = resolve(process.env.PETSOUL_ADMIN_DATA_DIR ?? join(backendDir, "data", "web-admin-demo"));
const dbPath = join(dataDir, "petjourney.sqlite3");

if (!existsSync(dbPath)) {
  console.error(`[admin-backend] 找不到演示库：${dbPath}`);
  console.error("[admin-backend] 先在仓库根目录跑：python scripts/seed_admin_demo.py");
  process.exit(1);
}
mkdirSync(join(dataDir, "uploads"), { recursive: true });

const world = process.env.PETSOUL_ADMIN_WORLD === "on";
// 批量补偿的额度必须显式配置才开放（方案 §4 P1）。默认不配 —— 后台会如实显示"这项能力关闭"。
// 想演示批量闭环时：PETSOUL_ADMIN_BATCH=on node scripts/dev-backend.mjs
const batch = process.env.PETSOUL_ADMIN_BATCH === "on"
  ? { PETSOUL_ADMIN_BATCH_MAX_RECIPIENTS: "10", PETSOUL_ADMIN_BATCH_MAX_COINS_PER_PET: "50",
      PETSOUL_ADMIN_BATCH_MAX_TOTAL_COINS: "300" }
  : {};
// 员工前端的来源白名单：默认只放行 5299（dev）与 4299（preview）。另起一套前端（例如指向演示库副本）时
// 用 PETSOUL_ADMIN_ORIGINS 显式放行它的端口——不放行的话，那套前端上的写操作会被来源校验挡下（403）。
const adminOrigins = process.env.PETSOUL_ADMIN_ORIGINS ?? "http://127.0.0.1:5299,http://127.0.0.1:4299";
const env = {
  ...process.env,
  TZ: "UTC",
  PETJOURNEY_DB_PATH: dbPath,
  PETJOURNEY_UPLOAD_DIR: join(dataDir, "uploads"),
  PETJOURNEY_WEB_PRIVATE_MEDIA_DIR: join(dataDir, "web-private-media"),
  PETJOURNEY_PUBLIC_BASE_URL: `http://127.0.0.1:${port}`,
  PETJOURNEY_CORS_ORIGINS: adminOrigins,
  // 演示库是 seed 脚本用这把密钥建的会话表；换密钥只会让旧会话失效，不影响数据。
  PETJOURNEY_AUTH_SECRET: process.env.PETJOURNEY_AUTH_SECRET ?? "petsoul-admin-demo-secret-0123456789abcdef",
  PETJOURNEY_WEB_COOKIE_SECURE: "false",
  PETJOURNEY_APPLE_AUTH_MODE: "mock",
  PETJOURNEY_SCHEDULER_ENABLED: "false",
  PETJOURNEY_WEB_DEMO_CATALOG: "1",
  PETJOURNEY_WEB_WORLD_RUNNER: world ? "embedded" : "off",
  PETJOURNEY_WEB_BRAIN_MODE: "off",
  PETJOURNEY_WEB_HEARTBEAT_MODE: "shadow",
  PETJOURNEY_PROVIDER_MODE: "mock",
  PETJOURNEY_MAP_PROVIDER: "mock",
  PETJOURNEY_LLM_PROVIDER: "mock",
  PETJOURNEY_IMAGE_PROVIDER: "mock",
  PETJOURNEY_TRANSPORT_SCHEDULE_PROVIDER: "mock",
  PETJOURNEY_TRAVEL_GUIDE_RESEARCH_PROVIDER: "mock",
  PETJOURNEY_MEMORY_PROVIDER: "sqlite",
  PETJOURNEY_LEGACY_API_POLICY: "open",
  PETSOUL_ADMIN_ORIGINS: adminOrigins,
  PETSOUL_ADMIN_COOKIE_SECURE: "false",
  ...batch,
  // 密钥一律置空：本地演示不产生任何真实付费调用。
  PETJOURNEY_WEB_PROVIDERS: "",
  OPENAI_API_KEY: "",
  AMAP_API_KEY: "",
  GOOGLE_MAPS_API_KEY: "",
  DOUBAO_API_KEY: "",
  PETJOURNEY_IMAGE_API_KEY: "",
  IMAGE_API_KEY: "",
  OPENAI_IMAGE_API_KEY: "",
};

const python = process.env.PETSOUL_PYTHON ?? "python";
const child = spawn(python, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", port],
                    { cwd: backendDir, env, stdio: "inherit" });
console.log(`[admin-backend] pid=${child.pid} port=${port} data=${dataDir} world=${world ? "embedded" : "off"} providers=off batch=${process.env.PETSOUL_ADMIN_BATCH === "on" ? "limits-configured" : "off(未配额度)"}`);
child.on("exit", (code) => process.exit(code ?? 0));
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => child.kill(sig));
