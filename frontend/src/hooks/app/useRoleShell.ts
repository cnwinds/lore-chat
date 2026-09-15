import { useState, useCallback, useEffect } from "react";
import { createRole, ensureActiveConversation, listRoles } from "../../api";

const STORAGE_KEY = "lorechat.lastRoleId";
const CONFIG_COLLAPSED_KEY = "lorechat.roleConfigCollapsed";

export function useRoleShell() {
  const [activeRoleId, setActiveRoleId] = useState<string | null>(null);
  const [roleRefreshKey, setRoleRefreshKey] = useState(0);
  const [configPanelCollapsed, setConfigPanelCollapsed] = useState(() => {
    try {
      return localStorage.getItem(CONFIG_COLLAPSED_KEY) === "1";
    } catch {
      return false;
    }
  });
  const [onRoleSwitch, setOnRoleSwitch] = useState<
    ((roleId: string, conversationId: string) => void) | null
  >(null);

  // Load last role or default on mount
  useEffect(() => {
    async function init() {
      try {
        const { roles } = await listRoles();
        if (roles.length === 0) return;

        // Try last used role
        const lastRoleId = localStorage.getItem(STORAGE_KEY);
        const targetRole =
          roles.find((r) => r.id === lastRoleId) || roles[0];

        setActiveRoleId(targetRole.id);

        // Ensure active conversation for initial role
        if (onRoleSwitch) {
          const { conversation_id } = await ensureActiveConversation(targetRole.id);
          onRoleSwitch(targetRole.id, conversation_id);
        }
      } catch (err) {
        console.error("Failed to initialize role:", err);
      }
    }
    void init();
  }, []);

  const refreshRoles = useCallback(() => {
    setRoleRefreshKey((k) => k + 1);
  }, []);

  const handleNewRole = useCallback(async () => {
    try {
      const newRole = await createRole({
        name: `新角色 ${Date.now()}`,
      });
      setActiveRoleId(newRole.id);
      localStorage.setItem(STORAGE_KEY, newRole.id);
      refreshRoles();

      // Switch to new role's active conversation
      if (onRoleSwitch) {
        const { conversation_id } = await ensureActiveConversation(newRole.id);
        onRoleSwitch(newRole.id, conversation_id);
      }
    } catch (err) {
      console.error("Failed to create role:", err);
      alert("创建角色失败");
    }
  }, [refreshRoles, onRoleSwitch]);

  const handleSelectRole = useCallback(
    async (roleId: string) => {
      try {
        setActiveRoleId(roleId);
        localStorage.setItem(STORAGE_KEY, roleId);

        // Resolve and switch to role's active conversation
        if (onRoleSwitch) {
          const { conversation_id } = await ensureActiveConversation(roleId);
          onRoleSwitch(roleId, conversation_id);
        }
      } catch (err) {
        console.error("Failed to switch role:", err);
        alert("切换角色失败");
      }
    },
    [onRoleSwitch],
  );

  const persistCollapsed = useCallback((next: boolean) => {
    try {
      localStorage.setItem(CONFIG_COLLAPSED_KEY, next ? "1" : "0");
    } catch {
      /* ignore */
    }
    return next;
  }, []);

  const toggleConfigPanel = useCallback(() => {
    setConfigPanelCollapsed((c) => persistCollapsed(!c));
  }, [persistCollapsed]);

  const expandConfigPanel = useCallback(() => {
    setConfigPanelCollapsed((c) => (c ? persistCollapsed(false) : c));
  }, [persistCollapsed]);

  const registerRoleSwitchHandler = useCallback(
    (handler: (roleId: string, conversationId: string) => void) => {
      setOnRoleSwitch(() => handler);
    },
    [],
  );

  return {
    activeRoleId,
    setActiveRoleId,
    roleRefreshKey,
    refreshRoles,
    configPanelCollapsed,
    toggleConfigPanel,
    expandConfigPanel,
    handleNewRole,
    handleSelectRole,
    registerRoleSwitchHandler,
  };
}
