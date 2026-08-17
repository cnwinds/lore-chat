import {
  MEDIA_GENERATED,
  MEDIA_ROOT,
  MEDIA_UPLOADS,
  isMediaPath,
} from "./kbMediaPaths";
import { isLikelyImagePath } from "./kbImageUrls";
import { isMarkdownPath } from "./kbPath";

/** 系统控制层目录名，与 backend `system_layer_dir` 保持一致 */
export const SYSTEM_LAYER_DIR = "系统";

/** Skill 固定目录，与 backend `skills_dir` 保持一致 */
export const SKILLS_DIR = "技能";

/** 聊天媒体根目录，与 backend `kb_media_paths.MEDIA_ROOT` 对齐 */
export const MEDIA_DIR = MEDIA_ROOT;

/** 系统层文件显示顺序：心法在上，戒律在下（与 backend SystemLayer.compose 一致） */
const SYSTEM_LAYER_FILE_ORDER = ["心法.md", "戒律.md"];

/** 根级固定目录排序：系统 → 技能 → 媒体 → 其余 */
const ROOT_FIXED_FOLDER_ORDER = [SYSTEM_LAYER_DIR, SKILLS_DIR, MEDIA_DIR];

export function isSystemLayerPath(path: string): boolean {
  return path === SYSTEM_LAYER_DIR || path.startsWith(`${SYSTEM_LAYER_DIR}/`);
}

export function isSkillsDirPath(path: string): boolean {
  return path === SKILLS_DIR || path.startsWith(`${SKILLS_DIR}/`);
}

export function isMediaDirPath(path: string): boolean {
  return isMediaPath(path);
}

/** 知识库特殊目录「系统 / 技能 / 媒体」及其下所有路径（含子目录与文件） */
export function isSpecialKbPath(path: string): boolean {
  return (
    isSystemLayerPath(path) || isSkillsDirPath(path) || isMediaDirPath(path)
  );
}

/** 侧栏文件行图标：图片专用，其它非 md 为附件，md 为文档。 */
export function fileTreeFileIcon(path: string): "🖼" | "📎" | "📄" {
  if (isLikelyImagePath(path)) return "🖼";
  if (!isMarkdownPath(path)) return "📎";
  return "📄";
}

export type FileNode = { type: "file"; name: string; path: string };
export type FolderNode = {
  type: "folder";
  name: string;
  path: string;
  children: TreeNode[];
};
export type TreeNode = FileNode | FolderNode;

function ensureFolder(parent: FolderNode, name: string): FolderNode {
  let folder = parent.children.find(
    (c): c is FolderNode => c.type === "folder" && c.name === name,
  );
  if (!folder) {
    const path = parent.path ? `${parent.path}/${name}` : name;
    folder = { type: "folder", name, path, children: [] };
    parent.children.push(folder);
  }
  return folder;
}

function ensureRootFolder(root: FolderNode, name: string): FolderNode {
  return ensureFolder(root, name);
}

export function buildFileTree(paths: string[]): TreeNode[] {
  const root: FolderNode = { type: "folder", name: "", path: "", children: [] };

  for (const rel of [...paths].sort()) {
    const parts = rel.split("/");
    let current = root;
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const isFile = i === parts.length - 1;
      const nodePath = parts.slice(0, i + 1).join("/");

      if (isFile) {
        // 媒体树只保留目录结构，文件改由左侧图库浏览
        if (isMediaPath(rel)) continue;
        current.children.push({ type: "file", name: part, path: rel });
      } else {
        let folder = current.children.find(
          (c): c is FolderNode => c.type === "folder" && c.name === part,
        );
        if (!folder) {
          folder = { type: "folder", name: part, path: nodePath, children: [] };
          current.children.push(folder);
        }
        current = folder;
      }
    }
  }

  ensureRootFolder(root, SYSTEM_LAYER_DIR);
  ensureRootFolder(root, SKILLS_DIR);
  const media = ensureRootFolder(root, MEDIA_DIR);
  ensureFolder(media, MEDIA_UPLOADS);
  ensureFolder(media, MEDIA_GENERATED);

  const sortNodes = (nodes: TreeNode[], parentPath = ""): TreeNode[] =>
    [...nodes]
      .sort((a, b) => {
        if (parentPath === "") {
          const aRank = ROOT_FIXED_FOLDER_ORDER.indexOf(a.name);
          const bRank = ROOT_FIXED_FOLDER_ORDER.indexOf(b.name);
          const aFixed = a.type === "folder" && aRank !== -1;
          const bFixed = b.type === "folder" && bRank !== -1;
          if (aFixed && bFixed) return aRank - bRank;
          if (aFixed !== bFixed) return aFixed ? -1 : 1;
        }
        if (parentPath === SYSTEM_LAYER_DIR) {
          const orderA = SYSTEM_LAYER_FILE_ORDER.indexOf(a.name);
          const orderB = SYSTEM_LAYER_FILE_ORDER.indexOf(b.name);
          const rankA = orderA === -1 ? SYSTEM_LAYER_FILE_ORDER.length : orderA;
          const rankB = orderB === -1 ? SYSTEM_LAYER_FILE_ORDER.length : orderB;
          if (rankA !== rankB) return rankA - rankB;
        }
        if (a.type !== b.type) return a.type === "folder" ? -1 : 1;
        return a.name.localeCompare(b.name, "zh-CN");
      })
      .map((n) =>
        n.type === "folder" ? { ...n, children: sortNodes(n.children, n.path) } : n,
      );

  return sortNodes(root.children);
}

export function collectFolderPaths(nodes: TreeNode[]): string[] {
  const paths: string[] = [];
  for (const n of nodes) {
    if (n.type === "folder") {
      paths.push(n.path);
      paths.push(...collectFolderPaths(n.children));
    }
  }
  return paths;
}

/** 默认展开的文件夹：前 2 层展开，第 3 层及以下折叠；系统/媒体目录保持折叠 */
export function collectDefaultExpandedFolderPaths(nodes: TreeNode[]): string[] {
  return collectFolderPaths(nodes).filter((p) => {
    if (p === SYSTEM_LAYER_DIR || isMediaDirPath(p)) return false;
    const depth = p.split("/").filter(Boolean).length;
    return depth <= 2;
  });
}

/**
 * 首次无持久化记录时用默认规则；否则恢复已存路径并剔除已不存在的目录。
 */
export function resolveExpandedFolderPaths(
  nodes: TreeNode[],
  storedPaths: string[] | null | undefined,
): string[] {
  if (storedPaths == null) {
    return collectDefaultExpandedFolderPaths(nodes);
  }
  const valid = new Set(collectFolderPaths(nodes));
  return storedPaths.filter((p) => valid.has(p));
}

/**
 * 树变更后的用户展开态：尚未持久化则按默认规则重算；已持久化则只剪枝。
 */
export function nextUserExpandedAfterTreeChange(
  nodes: TreeNode[],
  prevUserExpanded: Iterable<string>,
  hasPersistedUserExpanded: boolean,
): string[] {
  if (!hasPersistedUserExpanded) {
    return collectDefaultExpandedFolderPaths(nodes);
  }
  return resolveExpandedFolderPaths(nodes, [...prevUserExpanded]);
}

/** 打开文件时用于临时露出的祖先目录（不应当作用户展开态持久化）。 */
export function collectAncestorFolderPaths(filePaths: string[]): string[] {
  const folders = new Set<string>();
  for (const filePath of filePaths) {
    const parts = filePath.split("/").filter(Boolean);
    for (let i = 0; i < parts.length - 1; i++) {
      folders.add(parts.slice(0, i + 1).join("/"));
    }
  }
  return [...folders];
}
