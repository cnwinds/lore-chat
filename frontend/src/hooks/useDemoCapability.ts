import { createContext, useContext } from "react";
import type { AuthStatus } from "../api";

export type DemoCapability = {
  isDemo: boolean;
  role: AuthStatus["role"];
  canWrite: boolean;
  canPersistChat: boolean;
};

export const DEFAULT_CAPABILITY: DemoCapability = {
  isDemo: false,
  role: "admin",
  canWrite: true,
  canPersistChat: true,
};

export function resolveDemoCapability(status: AuthStatus): DemoCapability {
  const isGuest = status.demo && status.role === "guest";
  return {
    isDemo: status.demo,
    role: status.role,
    canWrite: !isGuest,
    canPersistChat: !isGuest,
  };
}

export const DemoCapabilityContext =
  createContext<DemoCapability>(DEFAULT_CAPABILITY);

export function useDemoCapability(): DemoCapability {
  return useContext(DemoCapabilityContext);
}
