/**
 * Skill 启用集：仅 Ctrl+点击顶层「技能」目录 → 勾选 → 跨会话 PUT。
 * 与文档托盘无关。
 */

import { useCallback, useState } from "react";
import {
  discoverSkills,
  getEnabledSkills,
  putEnabledSkills,
} from "../api";
import { SKILLS_DIR } from "../utils/fileTree";

/** 首次无启用 → 全选候选；否则预勾选「候选 ∩ 已启用」（可为空）。 */
export function initialSkillSelection(
  candidates: string[],
  enabled: string[],
): string[] {
  if (enabled.length === 0) return [...candidates];
  const enabledSet = new Set(enabled);
  return candidates.filter((r) => enabledSet.has(r));
}

export function useEnabledSkillsAttach() {
  const [skillPick, setSkillPick] = useState<{
    candidates: string[];
    initiallySelected: string[];
  } | null>(null);
  const [saving, setSaving] = useState(false);

  const openEnabledSkillsModal = useCallback(() => {
    void (async () => {
      try {
        const [{ roots }, { roots: enabled }] = await Promise.all([
          discoverSkills(SKILLS_DIR),
          getEnabledSkills(),
        ]);
        if (roots.length === 0) {
          window.alert(
            `「${SKILLS_DIR}」下未发现 Skill 包（每个包须为直接包含 SKILL.md 的文件夹）。`,
          );
          return;
        }
        setSkillPick({
          candidates: roots,
          initiallySelected: initialSkillSelection(roots, enabled),
        });
      } catch (err) {
        window.alert(err instanceof Error ? err.message : "加载 Skill 列表失败");
      }
    })();
  }, []);

  const handleSkillPickConfirm = useCallback(
    (selected: string[]) => {
      if (!skillPick) return;
      void (async () => {
        setSaving(true);
        try {
          // 从技能根管理全集：整表重写启用集
          await putEnabledSkills(selected);
          setSkillPick(null);
        } catch (err) {
          window.alert(
            err instanceof Error
              ? err.message
              : "保存启用技能失败，请检查各 SKILL.md 是否含 name / description 头",
          );
        } finally {
          setSaving(false);
        }
      })();
    },
    [skillPick],
  );

  const cancelSkillPick = useCallback(() => setSkillPick(null), []);

  return {
    skillPick,
    saving,
    openEnabledSkillsModal,
    handleSkillPickConfirm,
    cancelSkillPick,
  };
}
