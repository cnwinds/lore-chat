import type { DocWidth, EditMode } from "../types/doc";

export const EDIT_MODE_KEY = "docEditMode";
export const DOC_FLOAT_WIDTH_KEY = "lorechat.docFloatWidth";
export const DOC_PANEL_WIDTH_KEY = "lorechat.docPanelWidth";
const LEGACY_DOC_WIDTH_KEY = "lorechat.docWidth";

export function getStoredEditMode(): EditMode {
  try {
    return sessionStorage.getItem(EDIT_MODE_KEY) === "markdown"
      ? "markdown"
      : "preview";
  } catch {
    return "preview";
  }
}

export function setStoredEditMode(mode: EditMode) {
  try {
    sessionStorage.setItem(EDIT_MODE_KEY, mode);
  } catch {
    /* ignore */
  }
}

function readWidth(key: string): DocWidth {
  // 存量显式值只有 narrow / wide；未显式存过 narrow 的一律视为 wide
  return localStorage.getItem(key) === "narrow" ? "narrow" : "wide";
}

export function getStoredFloatWidth(): DocWidth {
  try {
    if (localStorage.getItem(DOC_FLOAT_WIDTH_KEY) != null) {
      return readWidth(DOC_FLOAT_WIDTH_KEY);
    }
    if (localStorage.getItem(LEGACY_DOC_WIDTH_KEY) != null) {
      return readWidth(LEGACY_DOC_WIDTH_KEY);
    }
  } catch {
    /* ignore */
  }
  return "wide";
}

export function setStoredFloatWidth(width: DocWidth) {
  try {
    localStorage.setItem(DOC_FLOAT_WIDTH_KEY, width);
  } catch {
    /* ignore */
  }
}

export function getStoredPanelWidth(): DocWidth {
  try {
    if (localStorage.getItem(DOC_PANEL_WIDTH_KEY) != null) {
      return readWidth(DOC_PANEL_WIDTH_KEY);
    }
  } catch {
    /* ignore */
  }
  return "wide";
}

export function setStoredPanelWidth(width: DocWidth) {
  try {
    localStorage.setItem(DOC_PANEL_WIDTH_KEY, width);
  } catch {
    /* ignore */
  }
}
