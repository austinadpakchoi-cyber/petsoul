#!/usr/bin/env node
/**
 * 本地隔离后端（仅开发/联调）：独立 SQLite 与上传目录、全部供应商 mock、调度器关闭、不读取任何真实密钥。
 *
 *   node scripts/dev-backend.mjs            # 127.0.0.1:18761，数据在 PetJourneyBackend/data/web-dev/
 *   PETSOUL_DEV_BACKEND_PORT=18762 PETSOUL_DEV_DATA_DIR=... node scripts/dev-backend.mjs
 *
 * 注意：
 * - PETJOURNEY_APPLE_AUTH_MODE=mock 只用于本地拿 Bearer 调试（沿用 iOS 开发约定），绝不能用于任何部署；
 * - 供应商密钥变量被显式置空，因此即使 PetJourneyBackend/.env 存在真实密钥也不会被读取（config.load_env_file 不覆盖已存在的变量）；
 * - 不要指向默认的 PetJourneyBackend/data/petjourney.sqlite3，也不要与其他窗口共用正在写入的数据库。
 */
import { spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const backendDir = resolve(here, "..", "..", "PetJourneyBackend");
const port = process.env.PETSOUL_DEV_BACKEND_PORT ?? "18761";
const dataDir = resolve(process.env.PETSOUL_DEV_DATA_DIR ?? join(backendDir, "data", "web-dev"));
mkdirSync(join(dataDir, "uploads"), { recursive: true });

const env = {
  ...process.env,
  TZ: "UTC",
  PETJOURNEY_DB_PATH: join(dataDir, "petjourney.sqlite3"),
  PETJOURNEY_UPLOAD_DIR: join(dataDir, "uploads"),
  PETJOURNEY_WEB_PRIVATE_MEDIA_DIR: join(dataDir, "web-private-media"),
  PETJOURNEY_PUBLIC_BASE_URL: `http://127.0.0.1:${port}`,
  PETJOURNEY_CORS_ORIGINS: "http://127.0.0.1:5287,http://127.0.0.1:4287",
  PETJOURNEY_PROVIDER_MODE: "mock",
  PETJOURNEY_MAP_PROVIDER: "mock",
  PETJOURNEY_LLM_PROVIDER: "mock",
  PETJOURNEY_IMAGE_PROVIDER: "mock",
  PETJOURNEY_TRANSPORT_SCHEDULE_PROVIDER: "mock",
  PETJOURNEY_TRAVEL_GUIDE_RESEARCH_PROVIDER: "mock",
  PETJOURNEY_SCHEDULER_ENABLED: "false",
  PETJOURNEY_MEMORY_PROVIDER: "sqlite",
  PETJOURNEY_APPLE_AUTH_MODE: "mock",
  PETJOURNEY_AUTH_SECRET: process.env.PETJOURNEY_AUTH_SECRET ?? randomBytes(32).toString("hex"),
  PETJOURNEY_WEB_COOKIE_SECURE: "false",
  PETJOURNEY_LEGACY_API_POLICY: process.env.PETJOURNEY_LEGACY_API_POLICY ?? "open",
  OPENAI_API_KEY: "",
  AMAP_API_KEY: "",
  AMAP_JS_KEY: "",
  AMAP_JS_SECURITY_CODE: "",
  GOOGLE_MAPS_API_KEY: "",
  DOUBAO_API_KEY: "",
  PETJOURNEY_IMAGE_API_KEY: "",
  IMAGE_API_KEY: "",
  OPENAI_IMAGE_API_KEY: "",
};

// 真实供应商（显式开启）：PETSOUL_DEV_PROVIDERS=1 读取 PetJourneyBackend/data/secrets/web-providers.env（git 忽略），
// 或给出其他密钥文件路径。只取白名单变量；不打印任何值；总开关 PETJOURNEY_WEB_PROVIDERS 只在这里打开。
const PROVIDER_KEYS = [
  "OPENAI_API_KEY", "PETJOURNEY_LLM_PROVIDER", "PETJOURNEY_OPENAI_BASE_URL", "PETJOURNEY_AGENT_MODEL",
  "AMAP_API_KEY", "GOOGLE_MAPS_API_KEY", "PETJOURNEY_MAP_TIMEOUT_SECONDS",
  // 高德 Web 端（JS API）两把：JS Key 按设计公开下发给浏览器，安全密钥**只在后端**、只由 /_AMapService 代理使用。
  "AMAP_JS_KEY", "AMAP_JS_SECURITY_CODE",
  "DOUBAO_API_KEY", "PETJOURNEY_DOUBAO_BASE_URL", "PETJOURNEY_IMAGE_PROVIDER", "PETJOURNEY_VOLCENGINE_IMAGE_MODEL", "PETJOURNEY_IMAGE_TIMEOUT_SECONDS",
];
const providersOpt = process.env.PETSOUL_DEV_PROVIDERS;
if (providersOpt && providersOpt !== "0") {
  const file = providersOpt === "1" ? join(backendDir, "data", "secrets", "web-providers.env") : resolve(providersOpt);
  if (!existsSync(file)) {
    console.error(`[dev-backend] 找不到供应商配置文件：${file}`);
    process.exit(1);
  }
  const loaded = [];
  for (const line of readFileSync(file, "utf8").split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
    if (m && PROVIDER_KEYS.includes(m[1]) && m[2]) {
      env[m[1]] = m[2];
      loaded.push(m[1]);
    }
  }
  env.PETJOURNEY_WEB_PROVIDERS = "1";
  // 哪些算「密钥」只报个数、不报名字：**不能只看 KEY**——`AMAP_JS_SECURITY_CODE` 名字里没有 KEY，
  // 只按 /KEY/ 分会把它列进「普通配置」那一半。现在打印的都只是**变量名**（值一直没打印），
  // 所以分错类不会泄露；但哪天有人改这段去打印值，分类就成了那道闸，所以现在就把它分对。
  const SECRETISH = /KEY|SECRET|CODE|TOKEN|PASSWORD/;
  console.log(`[dev-backend] 真实供应商已开启（仅服务端）：${loaded.filter((k) => !SECRETISH.test(k)).join(", ")}；密钥 ${loaded.filter((k) => SECRETISH.test(k)).length} 个（不显示）`);
}

const python = process.env.PETSOUL_PYTHON ?? "python";
const child = spawn(python, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", port], { cwd: backendDir, env, stdio: "inherit" });
console.log(`[dev-backend] pid=${child.pid} port=${port} data=${dataDir}`);
child.on("exit", (code) => process.exit(code ?? 0));
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => child.kill(sig));
