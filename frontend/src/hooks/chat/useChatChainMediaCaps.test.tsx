import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SETTINGS_CHANGED_EVENT } from "../../utils/settingsChangedEvent";

vi.mock("../../api", () => ({
  getSettings: vi.fn(),
}));

vi.mock("../../utils/chatChainMedia", () => ({
  resolveChainMediaCapsFromSettings: vi.fn(),
}));

import { getSettings } from "../../api";
import { resolveChainMediaCapsFromSettings } from "../../utils/chatChainMedia";
import { useChatChainMediaCaps } from "./useChatChainMediaCaps";

const getSettingsMock = vi.mocked(getSettings);
const resolveMock = vi.mocked(resolveChainMediaCapsFromSettings);

describe("useChatChainMediaCaps", () => {
  beforeEach(() => {
    getSettingsMock.mockReset();
    resolveMock.mockReset();
    getSettingsMock.mockResolvedValue({ chat_models: [] } as never);
    resolveMock.mockResolvedValue({
      videoSupported: true,
      maxVideos: 2,
      imageSupported: true,
      maxImages: 3,
      videoWireData: true,
    });
  });

  it("loads caps on mount", async () => {
    const { result } = renderHook(() => useChatChainMediaCaps());
    await waitFor(() => {
      expect(result.current.videoSupported).toBe(true);
      expect(result.current.maxVideos).toBe(2);
      expect(result.current.imageSupported).toBe(true);
      expect(result.current.maxImages).toBe(3);
      expect(result.current.videoWireData).toBe(true);
    });
    expect(resolveMock).toHaveBeenCalled();
  });

  it("refreshes when settings change event fires", async () => {
    let calls = 0;
    resolveMock.mockImplementation(async () => {
      calls += 1;
      if (calls === 1) {
        return {
          videoSupported: false,
          maxVideos: 1,
          imageSupported: false,
          maxImages: null,
          videoWireData: false,
        };
      }
      return {
        videoSupported: true,
        maxVideos: 3,
        imageSupported: true,
        maxImages: 5,
        videoWireData: true,
      };
    });

    const { result } = renderHook(() => useChatChainMediaCaps());
    await waitFor(() => expect(result.current.videoSupported).toBe(false));

    await act(async () => {
      window.dispatchEvent(new CustomEvent(SETTINGS_CHANGED_EVENT));
    });

    await waitFor(() => expect(result.current.maxVideos).toBe(3));
    expect(result.current.videoSupported).toBe(true);
    expect(result.current.maxImages).toBe(5);
    expect(resolveMock.mock.calls.length).toBeGreaterThanOrEqual(2);
  });
});
