export type DocTrayItem = { path: string; title: string };

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
