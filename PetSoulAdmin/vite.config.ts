/// <reference types="vite/client" />
import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// 员工后台与玩家网页是两个独立工程、两个端口、两套 cookie。
// dev 代理同时转发 /api/v1/admin（管理端）与 /api/v1/web（用来当场验证玩家侧真的读到了发布内容）。
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.PETSOUL_ADMIN_API_TARGET || "http://127.0.0.1:18790";
  const proxy = {
    "/api/v1/admin": { target: apiTarget, changeOrigin: false },
    "/api/v1/web": { target: apiTarget, changeOrigin: false },
  };
  return {
    plugins: [react()],
    resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
    server: { host: "127.0.0.1", port: 5299, strictPort: true, proxy },
    preview: { host: "127.0.0.1", port: 4299, strictPort: true, proxy },
    build: { target: "es2022", sourcemap: true },
  };
});
