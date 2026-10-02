import { showToast } from "../utils/toast";

/** 生产构建注册 Service Worker；开发模式不启用（见 vite.config）。 */
export function registerPwa(): void {
  if (!import.meta.env.PROD) return;

  void import("virtual:pwa-register")
    .then(({ registerSW }) => {
      registerSW({
        immediate: true,
        onRegisteredSW(_url, registration) {
          if (registration) {
            document.documentElement.dataset.pwa = "registered";
          }
        },
        onRegisterError(error) {
          console.warn("[pwa] register failed", error);
        },
        onNeedRefresh() {
          showToast("有新版本，刷新页面即可更新", 4000);
        },
        onOfflineReady() {
          showToast("离线可打开界面（对话仍需联网）", 3500);
        },
      });
    })
    .catch((err) => {
      console.warn("[pwa] load register module failed", err);
    });
}
