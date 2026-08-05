export type DocTrayKind = "document" | "skill_root";

export type DocTrayItem = {
  path: string;
  title: string;
  kind: DocTrayKind;
};

export type ComposerDocState = {
  items: DocTrayItem[];
  primaryPath: string | null;
};

export type PendingFile = {
  id: string;
  file: File;
  name: string;
  size: number;
};

export const COMPOSER_TRAY_MAX = 8;
