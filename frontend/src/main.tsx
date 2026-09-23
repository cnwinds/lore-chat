import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import "./styles/grok-layout.css";
import "./styles/lore-theme.css";
import { initTheme } from "./theme";
import { initOverlayScrollbar } from "./utils/overlayScrollbar";
import App from "./App.tsx";

initTheme();
initOverlayScrollbar();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
