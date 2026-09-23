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
