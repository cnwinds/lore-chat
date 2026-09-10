import { useState, useCallback } from "react";
import { createRole } from "../../api";

export function useRoleShell() {
  const [activeRoleId, setActiveRoleId] = useState<string | null>(null);
  const [roleRefreshKey, setRoleRefreshKey] = useState(0);
  const [configPanelCollapsed, setConfigPanelCollapsed] = useState(false);

  const refreshRoles = useCallback(() => {
    setRoleRefreshKey((k) => k + 1);
  }, []);

  const handleNewRole = useCallback(async () => {
    try {
      const newRole = await createRole({
        name: `新角色 ${Date.now()}`,
      });
      setActiveRoleId(newRole.id);
      refreshRoles();
    } catch (err) {
      console.error("Failed to create role:", err);
      alert("创建角色失败");
    }
  }, [refreshRoles]);

  const handleSelectRole = useCallback((roleId: string) => {
    setActiveRoleId(roleId);
  }, []);

  const toggleConfigPanel = useCallback(() => {
    setConfigPanelCollapsed((c) => !c);
  }, []);

  return {
    activeRoleId,
    setActiveRoleId,
    roleRefreshKey,
    refreshRoles,
    configPanelCollapsed,
    toggleConfigPanel,
    handleNewRole,
    handleSelectRole,
  };
}
