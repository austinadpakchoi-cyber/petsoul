/// <reference types="vitest/config" />
import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.PETSOUL_DEV_API_TARGET || "http://127.0.0.1:18761";
  const proxy = {
    "/api/v1/web": { target: apiTarget, changeOrigin: false },
    "/media": { target: apiTarget, changeOrigin: false },
    // 高德 JS API 安全代理（CR-6C2B-MAP W0）。**必须是站点根一级路由**——高德的 serviceHost
    // 指到 /api/v1/web 下面会被 JS API 拒绝（6c2b 实测）。后端实现在 app/routers/amap_service.py：
    // 只放行三条渲染类路径并补安全密钥，服务类一律 403。开发期靠这条转给后端，生产由反向代理转发。
    "/_AMapService": { target: apiTarget, changeOrigin: false },
  };
  return {
    plugins: [react()],
    resolve: {
      alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
    },
    server: { host: "127.0.0.1", port: 5287, strictPort: true, proxy },
    preview: { host: "127.0.0.1", port: 4287, strictPort: true, proxy },
    build: { target: "es2022", sourcemap: true, chunkSizeWarningLimit: 700 },
    test: {
      environment: "jsdom",
      include: ["tests/**/*.test.{ts,tsx}"],
      setupFiles: ["tests/setup.ts"],
    },
  };
});
