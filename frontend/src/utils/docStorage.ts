import type { EditMode } from "../types/doc";

export const EDIT_MODE_KEY = "docEditMode";

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
