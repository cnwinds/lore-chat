import { SKILLS_DIR } from "./fileTree";

const SKILL_ENTRY = "/SKILL.md";

export function skillPackageRootFromSkillMd(relPath: string): string | null {
  const rel = relPath.replace(/\\/g, "/");
  // 禁止知识库根目录作为 Skill 包
  if (rel === "SKILL.md") return null;
  if (rel.endsWith(SKILL_ENTRY)) {
    const root = rel.slice(0, -SKILL_ENTRY.length);
    return root || null;
  }
  return null;
}

function normDir(path: string): string {
  return path.replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
}

export function isUnderDir(path: string, base: string): boolean {
  const b = normDir(base);
  const p = normDir(path);
  if (!b) return true;
  return p === b || p.startsWith(`${b}/`);
}

/** 与后端 `discover_skill_roots` 同算法；单测用。产品 UI 请调 `discoverSkills` API。 */
export function discoverSkillRoots(
  allPaths: string[],
  fromDir: string,
  skillsDir: string = SKILLS_DIR,
): string[] {
  const from = normDir(fromDir);
  const skills = normDir(skillsDir);
  const roots = new Set<string>();
  for (const rel of allPaths) {
    const root = skillPackageRootFromSkillMd(rel);
    if (root === null) continue;
    if (!isUnderDir(root, from)) continue;
    if (!isUnderDir(root, skills)) continue;
    roots.add(root);
  }
  return [...roots].sort((a, b) => a.localeCompare(b, "zh-CN"));
}

/** 若 path 位于「技能」目录下某 Skill 包内，返回该包根。 */
export function enclosingSkillRoot(
  filePath: string,
  allPaths: Set<string> | string[],
  skillsDir: string = SKILLS_DIR,
): string | null {
  const pathSet = allPaths instanceof Set ? allPaths : new Set(allPaths);
  const norm = normDir(filePath);
  const parts = norm.split("/").filter(Boolean);
  for (let i = parts.length; i >= 0; i--) {
    const dir = parts.slice(0, i).join("/");
    if (!dir || !isUnderDir(dir, skillsDir)) continue;
    const skillMd = `${dir}/SKILL.md`;
    if (pathSet.has(skillMd)) return dir;
  }
  return null;
}

export function isInsideSkillPackage(
  filePath: string,
  allPaths: Set<string> | string[],
  skillsDir: string = SKILLS_DIR,
): boolean {
  return enclosingSkillRoot(filePath, allPaths, skillsDir) !== null;
}

export function skillRootLabel(root: string): string {
  if (!root) return "Skill";
  const name = root.split("/").pop() ?? root;
  return `Skill · ${name}`;
}
