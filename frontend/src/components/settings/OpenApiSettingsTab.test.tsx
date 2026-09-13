import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../../api";
import * as openApi from "../../api/openApi";
import { OpenApiSettingsTab } from "./OpenApiSettingsTab";

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return { ...actual, listRoles: vi.fn() };
});

vi.mock("../../api/openApi", () => ({
  listApiPersonas: vi.fn(),
  listOpenApiKeys: vi.fn(),
  createApiPersona: vi.fn(),
  createOpenApiKey: vi.fn(),
  deleteApiPersona: vi.fn(),
  updateApiPersona: vi.fn(),
  revokeOpenApiKey: vi.fn(),
  getOpenApiKeyTimeline: vi.fn(),
}));

vi.mock("../../utils/toast", () => ({
  showToast: vi.fn(),
}));

const listRoles = vi.mocked(api.listRoles);
const listApiPersonas = vi.mocked(openApi.listApiPersonas);
const listOpenApiKeys = vi.mocked(openApi.listOpenApiKeys);
const createOpenApiKey = vi.mocked(openApi.createOpenApiKey);
const getOpenApiKeyTimeline = vi.mocked(openApi.getOpenApiKeyTimeline);

function seedEmpty() {
  listApiPersonas.mockResolvedValue({ personas: [] });
  listOpenApiKeys.mockResolvedValue({ keys: [] });
  listRoles.mockResolvedValue({ roles: [] });
}

const sampleKey = {
  id: "k1",
  name: "周报脚本",
  prefix: "lc_live_abcd",
  persona_id: "p1",
  role_id: "api_k1",
  revoked: false,
  created_at: "2026-09-12T00:00:00Z",
  last_used_at: null,
  persona: {
    id: "p1",
    name: "通用助手",
    system_prompt: "",
    created_at: "2026-09-12T00:00:00Z",
    updated_at: "2026-09-12T00:00:00Z",
  },
};

afterEach(() => {
  cleanup();
});

beforeEach(() => {
  vi.clearAllMocks();
  seedEmpty();
});

describe("OpenApiSettingsTab", () => {
  it("keeps the empty home to a single create action", async () => {
    render(<OpenApiSettingsTab />);
    expect(await screen.findByText("还没有密钥")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "创建密钥" })).toBeInTheDocument();
    expect(screen.queryByText("新建人设")).toBeNull();
    expect(screen.queryByPlaceholderText("这个角色怎么说话、做什么")).toBeNull();
    expect(screen.queryByText(/隐藏工作角色/)).toBeNull();
    expect(screen.queryByText(/不进左栏/)).toBeNull();
  });

  it("creates a key with only a name on the default path", async () => {
    const user = userEvent.setup();
    createOpenApiKey.mockResolvedValue({
      ...sampleKey,
      token: "lc_live_secret",
    });
    render(<OpenApiSettingsTab />);
    await user.click(await screen.findByRole("button", { name: "创建密钥" }));
    expect(screen.getByText("填个名字就行。说话方式可先不改。")).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText("例如：周报脚本"), "周报脚本");
    await user.click(screen.getByRole("button", { name: "创建" }));
    await waitFor(() => {
      expect(createOpenApiKey).toHaveBeenCalledWith({ name: "周报脚本" });
    });
    expect(await screen.findByText("只显示这一次，请立刻复制保存。")).toBeInTheDocument();
    expect(screen.getByText("lc_live_secret")).toBeInTheDocument();
  });

  it("lists keys as cards without the old dual forms", async () => {
    listApiPersonas.mockResolvedValue({
      personas: [sampleKey.persona!],
    });
    listOpenApiKeys.mockResolvedValue({ keys: [sampleKey] });
    render(<OpenApiSettingsTab />);
    expect(await screen.findByText("周报脚本")).toBeInTheDocument();
    expect(document.querySelector(".openapi-voice")).toHaveTextContent("通用助手");
    expect(screen.getByRole("button", { name: "查看会话" })).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("例如：周报脚本")).toBeNull();
    expect(screen.queryByPlaceholderText("例如：周报助手")).toBeNull();
  });

  it("can reuse an existing persona when creating a key", async () => {
    const user = userEvent.setup();
    listApiPersonas.mockResolvedValue({
      personas: [sampleKey.persona!],
    });
    createOpenApiKey.mockResolvedValue({
      ...sampleKey,
      token: "lc_live_secret",
    });
    render(<OpenApiSettingsTab />);
    await user.click(await screen.findByRole("button", { name: "创建密钥" }));
    await user.type(screen.getByPlaceholderText("例如：周报脚本"), "另一把");
    await user.selectOptions(screen.getByLabelText("说话方式"), "persona:p1");
    await user.click(screen.getByRole("button", { name: "创建" }));
    await waitFor(() => {
      expect(createOpenApiKey).toHaveBeenCalledWith({
        name: "另一把",
        persona_id: "p1",
      });
    });
  });

  it("opens a dedicated session view", async () => {
    const user = userEvent.setup();
    listApiPersonas.mockResolvedValue({
      personas: [sampleKey.persona!],
    });
    listOpenApiKeys.mockResolvedValue({ keys: [sampleKey] });
    getOpenApiKeyTimeline.mockResolvedValue({
      role_id: "api_k1",
      segments: [
        {
          title: "周报",
          messages: [
            { id: "m1", role: "user", text: "写一份周报" },
            { id: "m2", role: "assistant", text: "好的" },
          ],
        },
      ],
    } as never);
    render(<OpenApiSettingsTab />);
    await user.click(await screen.findByRole("button", { name: "查看会话" }));
    expect(await screen.findByText("只看这一把密钥的调用记录。")).toBeInTheDocument();
    expect(screen.getByText("写一份周报")).toBeInTheDocument();
    expect(screen.getByText("好的")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "← 返回" }));
    expect(screen.getByText("周报脚本")).toBeInTheDocument();
    expect(screen.queryByText("写一份周报")).toBeNull();
  });
});
