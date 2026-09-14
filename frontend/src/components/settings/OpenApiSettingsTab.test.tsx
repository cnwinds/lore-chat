import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../../api";
import * as channelPlugins from "../../api/channelPlugins";
import * as openApi from "../../api/openApi";
import { OpenApiSettingsTab } from "./OpenApiSettingsTab";

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return { ...actual, listRoles: vi.fn() };
});

vi.mock("../../api/openApi", () => ({
  listApiPersonas: vi.fn(),
  createApiPersona: vi.fn(),
  deleteApiPersona: vi.fn(),
  updateApiPersona: vi.fn(),
}));

vi.mock("../../api/channelPlugins", () => ({
  listChannelTypes: vi.fn(),
  listChannelInstances: vi.fn(),
  createChannelInstance: vi.fn(),
  revokeChannelInstance: vi.fn(),
  getChannelTimeline: vi.fn(),
}));

vi.mock("../../utils/toast", () => ({
  showToast: vi.fn(),
}));

const listRoles = vi.mocked(api.listRoles);
const listApiPersonas = vi.mocked(openApi.listApiPersonas);
const listChannelTypes = vi.mocked(channelPlugins.listChannelTypes);
const listChannelInstances = vi.mocked(channelPlugins.listChannelInstances);
const createChannelInstance = vi.mocked(channelPlugins.createChannelInstance);
const getChannelTimeline = vi.mocked(channelPlugins.getChannelTimeline);

const sampleTypes = [
  {
    type_id: "script_api",
    display_name: "脚本 / HTTP",
    ingress: "http_bearer",
    needs_public_url: false,
    available: true,
  },
  {
    type_id: "feishu",
    display_name: "飞书",
    ingress: "websocket",
    needs_public_url: false,
    available: false,
  },
];

function seedEmpty() {
  listApiPersonas.mockResolvedValue({ personas: [] });
  listChannelInstances.mockResolvedValue({ instances: [] });
  listChannelTypes.mockResolvedValue({ types: sampleTypes });
  listRoles.mockResolvedValue({ roles: [] });
}

const sampleInstance = {
  id: "k1",
  type_id: "script_api",
  name: "周报脚本",
  enabled: true,
  status: "enabled",
  persona_id: "p1",
  role_id: "api_k1",
  created_at: "2026-09-12T00:00:00Z",
  last_event_at: null,
  config: { key_prefix: "lc_live_abcd" },
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

async function goCreateScript(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "添加通道" }));
  await user.click(await screen.findByRole("button", { name: /脚本 \/ HTTP/ }));
}

describe("OpenApiSettingsTab", () => {
  it("keeps the empty home to a single create action", async () => {
    render(<OpenApiSettingsTab />);
    expect(await screen.findByText("还没有聊天通道")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "添加通道" })).toBeInTheDocument();
    expect(screen.getByText("聊天通道")).toBeInTheDocument();
    expect(screen.queryByText("开放接口")).toBeNull();
    expect(screen.queryByText("新建人设")).toBeNull();
    expect(screen.queryByPlaceholderText("这个角色怎么说话、做什么")).toBeNull();
    expect(screen.queryByText(/隐藏工作角色/)).toBeNull();
    expect(screen.queryByText(/不进左栏/)).toBeNull();
  });

  it("creates a script channel with only a name on the default path", async () => {
    const user = userEvent.setup();
    createChannelInstance.mockResolvedValue({
      ...sampleInstance,
      token: "lc_live_secret",
    });
    render(<OpenApiSettingsTab />);
    await goCreateScript(user);
    expect(screen.getByText("填个名字就行。说话方式可先不改。")).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText("例如：周报脚本"), "周报脚本");
    await user.click(screen.getByRole("button", { name: "创建并启用" }));
    await waitFor(() => {
      expect(createChannelInstance).toHaveBeenCalledWith({
        type_id: "script_api",
        name: "周报脚本",
      });
    });
    expect(await screen.findByText("只显示这一次，请立刻复制保存。")).toBeInTheDocument();
    expect(screen.getByText("lc_live_secret")).toBeInTheDocument();
  });

  it("lists instances as shared cards and keeps projected keys out of empty state", async () => {
    listApiPersonas.mockResolvedValue({
      personas: [sampleInstance.persona!],
    });
    listChannelInstances.mockResolvedValue({ instances: [sampleInstance] });
    render(<OpenApiSettingsTab />);
    expect(await screen.findByText("周报脚本")).toBeInTheDocument();
    expect(document.querySelector(".openapi-voice")).toHaveTextContent("通用助手");
    expect(screen.getByText("已启用")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "查看会话" })).toBeInTheDocument();
    expect(screen.queryByText("还没有聊天通道")).toBeNull();
    expect(screen.queryByPlaceholderText("例如：周报脚本")).toBeNull();
    expect(screen.queryByPlaceholderText("例如：周报助手")).toBeNull();
  });

  it("can reuse an existing persona when creating a channel", async () => {
    const user = userEvent.setup();
    listApiPersonas.mockResolvedValue({
      personas: [sampleInstance.persona!],
    });
    createChannelInstance.mockResolvedValue({
      ...sampleInstance,
      token: "lc_live_secret",
    });
    render(<OpenApiSettingsTab />);
    await goCreateScript(user);
    await user.type(screen.getByPlaceholderText("例如：周报脚本"), "另一把");
    await user.selectOptions(screen.getByLabelText("说话方式"), "persona:p1");
    await user.click(screen.getByRole("button", { name: "创建并启用" }));
    await waitFor(() => {
      expect(createChannelInstance).toHaveBeenCalledWith({
        type_id: "script_api",
        name: "另一把",
        persona_id: "p1",
      });
    });
  });

  it("opens a dedicated session view", async () => {
    const user = userEvent.setup();
    listApiPersonas.mockResolvedValue({
      personas: [sampleInstance.persona!],
    });
    listChannelInstances.mockResolvedValue({ instances: [sampleInstance] });
    getChannelTimeline.mockResolvedValue({
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
    expect(await screen.findByText("只看这一路通道的聊天记录。")).toBeInTheDocument();
    expect(screen.getByText("写一份周报")).toBeInTheDocument();
    expect(screen.getByText("好的")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "← 返回" }));
    expect(screen.getByText("周报脚本")).toBeInTheDocument();
    expect(screen.queryByText("写一份周报")).toBeNull();
  });

  it("greys out upcoming types in the add wizard", async () => {
    const user = userEvent.setup();
    render(<OpenApiSettingsTab />);
    await user.click(await screen.findByRole("button", { name: "添加通道" }));
    expect(screen.getByRole("button", { name: /飞书/ })).toBeDisabled();
    expect(screen.getByText("即将支持")).toBeInTheDocument();
  });
});
