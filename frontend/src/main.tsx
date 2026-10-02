import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import "./styles/grok-layout.css";
import "./styles/lore-theme.css";
import "./styles/background-flow.css";
import { initTheme } from "./theme";
import { initOverlayScrollbar } from "./utils/overlayScrollbar";
import App from "./App.tsx";
import { registerPwa } from "./pwa/registerPwa";

initTheme();
initOverlayScrollbar();
registerPwa();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
