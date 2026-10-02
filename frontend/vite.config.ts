import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

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
    return raw.split(",").map((s: string) => s.trim()).filter(Boolean);
  }
  // Docker compose.dev 会注入 VITE_PROXY_TARGET
  if (process.env.VITE_PROXY_TARGET) {
    return true;
  }
  return ["localhost", ".localhost"];
}

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "prompt",
      injectRegister: false,
      includeAssets: ["lore.svg", "pwa-icon-192.png", "pwa-icon-512.png", "pwa-icon-180.png"],
      manifest: {
        name: "Lore Chat",
        short_name: "Lore",
        description: "与角色对话、管理知识库与记忆的 Lore Chat",
        lang: "zh-CN",
        dir: "ltr",
        start_url: "/",
        scope: "/",
        display: "standalone",
        orientation: "any",
        theme_color: "#f5f8f4",
        background_color: "#f5f8f4",
        icons: [
          {
            src: "pwa-icon-192.png",
            sizes: "192x192",
            type: "image/png",
            purpose: "any",
          },
          {
            src: "pwa-icon-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "any",
          },
          {
            src: "pwa-icon-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,ico,svg,png,woff2,woff,ttf}"],
        maximumFileSizeToCacheInBytes: 3 * 1024 * 1024,
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//],
        runtimeCaching: [],
        cleanupOutdatedCaches: true,
      },
      devOptions: {
        enabled: false,
      },
    }),
  ],
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
