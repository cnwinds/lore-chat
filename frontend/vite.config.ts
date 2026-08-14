import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/**
 * 经 Caddy / 公网域名反代到 Vite 时需放行 Host。
 * - Docker 开发（设了 VITE_PROXY_TARGET）默认放行全部
 * - 或设 VITE_ALLOWED_HOSTS=all / true / 逗号分隔域名（如 lore.ai-news.top,.ai-news.top）
 */
function resolveAllowedHosts(): true | string[] {
  const raw = (process.env.VITE_ALLOWED_HOSTS || "").trim();
  if (raw === "all" || raw === "true" || raw === "*") {
    return true;
  }
  if (raw) {
    return raw.split(",").map((s) => s.trim()).filter(Boolean);
  }
  // Docker compose.dev 会注入 VITE_PROXY_TARGET
  if (process.env.VITE_PROXY_TARGET) {
    return true;
  }
  return ["localhost", ".localhost"];
}

export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: resolveAllowedHosts(),
    // Docker 开发叠加里设 VITE_PROXY_TARGET=http://backend:8000
    proxy: {
      "/api": {
        target: process.env.VITE_PROXY_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
    },
    watch: {
      usePolling: process.env.CHOKIDAR_USEPOLLING === "true",
    },
  },
});
