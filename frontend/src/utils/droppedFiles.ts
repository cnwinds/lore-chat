/** 从拖放事件收集本地文件，保留文件夹相对路径（用于知识库导入）。 */

export type DroppedFile = { file: File; relativePath: string };

type FileSystemEntry = {
  isFile: boolean;
  isDirectory: boolean;
  name: string;
};

type FileSystemFileEntry = FileSystemEntry & {
  file: (
    success: (file: File) => void,
    failure?: (err: DOMException) => void,
  ) => void;
};

type FileSystemDirectoryReader = {
  readEntries: (
    success: (entries: FileSystemEntry[]) => void,
    failure?: (err: DOMException) => void,
  ) => void;
};

type FileSystemDirectoryEntry = FileSystemEntry & {
  createReader: () => FileSystemDirectoryReader;
};

export function joinKbDirectory(base: string, sub: string): string {
  const b = base.replace(/\\/g, "/").replace(/\/+$/, "");
  const s = sub.replace(/\\/g, "/").replace(/^\/+/, "");
  if (!b) return s;
  if (!s) return b;
  return `${b}/${s}`;
}

/** 将拖放相对路径映射到知识库 directory + filename。 */
export function targetDirectoryForDrop(
  baseDirectory: string,
  relativePath: string,
): { directory: string; filename: string } {
  const norm = relativePath.replace(/\\/g, "/");
  const slash = norm.lastIndexOf("/");
  const filename = slash === -1 ? norm : norm.slice(slash + 1);
  const subdir = slash === -1 ? "" : norm.slice(0, slash);
  return {
    directory: joinKbDirectory(baseDirectory, subdir),
    filename,
  };
}

function entryToFile(entry: FileSystemFileEntry): Promise<File> {
  return new Promise((resolve, reject) => {
    entry.file(resolve, reject);
  });
}

async function readAllDirectoryEntries(
  reader: FileSystemDirectoryReader,
): Promise<FileSystemEntry[]> {
  const all: FileSystemEntry[] = [];
  for (;;) {
    const batch = await new Promise<FileSystemEntry[]>((resolve, reject) => {
      reader.readEntries(resolve, reject);
    });
    if (batch.length === 0) break;
    all.push(...batch);
  }
  return all;
}

async function traverseEntry(
  entry: FileSystemEntry,
  prefix: string,
): Promise<DroppedFile[]> {
  if (entry.isFile) {
    const file = await entryToFile(entry as FileSystemFileEntry);
    const relativePath = prefix ? `${prefix}/${entry.name}` : entry.name;
    return [{ file, relativePath }];
  }
  if (entry.isDirectory) {
    const dir = entry as FileSystemDirectoryEntry;
    const nestedPrefix = prefix ? `${prefix}/${entry.name}` : entry.name;
    const children = await readAllDirectoryEntries(dir.createReader());
    const nested = await Promise.all(
      children.map((child) => traverseEntry(child, nestedPrefix)),
    );
    return nested.flat();
  }
  return [];
}

export async function collectDroppedFiles(
  dt: DataTransfer,
): Promise<DroppedFile[]> {
  const items = dt.items;
  if (items?.length) {
    const fromItems: DroppedFile[] = [];
    const tasks: Promise<void>[] = [];
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.kind !== "file") continue;
      const webkitItem = item as DataTransferItem & {
        webkitGetAsEntry?: () => FileSystemEntry | null;
      };
      const entry = webkitItem.webkitGetAsEntry?.() ?? null;
      if (entry) {
        tasks.push(
          traverseEntry(entry, "").then((found) => {
            fromItems.push(...found);
          }),
        );
      } else {
        const f = item.getAsFile();
        if (f) fromItems.push({ file: f, relativePath: f.name });
      }
    }
    await Promise.all(tasks);
    if (fromItems.length) return fromItems;
  }

  const out: DroppedFile[] = [];
  for (const file of Array.from(dt.files)) {
    const rp = (file as File & { webkitRelativePath?: string }).webkitRelativePath;
    out.push({
      file,
      relativePath: rp && rp.length > 0 ? rp : file.name,
    });
  }
  return out;
}

export function dropEffectForTransfer(dt: DataTransfer): "copy" | "move" {
  if (dt.types.includes("Files")) return "copy";
  return "move";
}
