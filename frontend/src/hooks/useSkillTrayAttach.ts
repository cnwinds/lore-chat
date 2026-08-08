/**
 * Skill 包发现 → 确认层 → 写入文档托盘。
 */

import { useCallback, useState } from "react";
import { discoverSkills } from "../api";
import { COMPOSER_TRAY_MAX } from "../types/composer";

type ComposerSkillApi = {
  trayRemaining: number;
  addSkillRoots: (paths: string[]) => void;
};

export function useSkillTrayAttach(composer: ComposerSkillApi) {
  const [skillPick, setSkillPick] = useState<{
    folder: string;
    candidates: string[];
  } | null>(null);

  const addSkillsToTray = useCallback(
    (selected: string[]) => {
      const room = composer.trayRemaining;
      if (room <= 0) {
        window.alert(`托盘已满（最多 ${COMPOSER_TRAY_MAX} 项）。`);
        return;
      }
      const toAdd = selected.slice(0, room);
      if (toAdd.length < selected.length) {
        window.alert(
          `托盘最多 ${COMPOSER_TRAY_MAX} 项，已加入前 ${toAdd.length} 个 Skill。`,
        );
      }
      composer.addSkillRoots(toAdd);
    },
    [composer],
  );

  const openSkillPickForFolder = useCallback(
    (folderPath: string) => {
      void (async () => {
        try {
          const { roots } = await discoverSkills(folderPath);
          if (roots.length === 0) {
            window.alert(
              "该目录及子目录下未发现 Skill 包（每个包须为直接包含 SKILL.md 的文件夹）。",
            );
            return;
          }
          if (roots.length === 1) {
            addSkillsToTray(roots);
            return;
          }
          setSkillPick({ folder: folderPath, candidates: roots });
        } catch (err) {
          window.alert(err instanceof Error ? err.message : "发现 Skill 失败");
        }
      })();
    },
    [addSkillsToTray],
  );

  const handleSkillPickConfirm = useCallback(
    (selected: string[]) => {
      addSkillsToTray(selected);
      setSkillPick(null);
    },
    [addSkillsToTray],
  );

  const cancelSkillPick = useCallback(() => setSkillPick(null), []);

  return {
    skillPick,
    openSkillPickForFolder,
    handleSkillPickConfirm,
    cancelSkillPick,
  };
}
