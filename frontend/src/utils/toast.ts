/** 轻量全局 toast：无 Provider，任意处调用 showToast。 */

const TOAST_HOST_ID = "lorechat-toast-host";
const TOAST_DURATION_MS = 2200;

function ensureHost(): HTMLElement {
  let host = document.getElementById(TOAST_HOST_ID);
  if (!host) {
    host = document.createElement("div");
    host.id = TOAST_HOST_ID;
    host.className = "app-toast-host";
    host.setAttribute("aria-live", "polite");
    document.body.appendChild(host);
  }
  return host;
}

export function showToast(message: string, durationMs = TOAST_DURATION_MS): void {
  if (typeof document === "undefined") return;
  const host = ensureHost();
  const el = document.createElement("div");
  el.className = "app-toast";
  el.textContent = message;
  host.appendChild(el);
  // trigger enter transition
  requestAnimationFrame(() => {
    el.classList.add("app-toast--visible");
  });
  window.setTimeout(() => {
    el.classList.remove("app-toast--visible");
    window.setTimeout(() => {
      el.remove();
      if (host.childElementCount === 0) host.remove();
    }, 200);
  }, durationMs);
}
