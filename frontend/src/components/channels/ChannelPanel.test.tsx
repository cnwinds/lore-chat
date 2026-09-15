import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../../api";
import * as channelPlugins from "../../api/channelPlugins";
import * as openApi from "../../api/openApi";
import * as clipboard from "../../utils/clipboard";
import { ChannelPanel } from "./ChannelPanel";

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
  patchChannelInstance: vi.fn(),
  revokeChannelInstance: vi.fn(),
  getChannelTimeline: vi.fn(),
  getChannelLogs: vi.fn(),
  getChannelUsage: vi.fn(),
  getChannelCredential: vi.fn(),
}));

vi.mock("../../utils/toast", () => ({
  showToast: vi.fn(),
}));

vi.mock("../../utils/clipboard", () => ({
  copyTextToClipboard: vi.fn(),
}));

const listRoles = vi.mocked(api.listRoles);
const listApiPersonas = vi.mocked(openApi.listApiPersonas);
const createApiPersona = vi.mocked(openApi.createApiPersona);
const listChannelTypes = vi.mocked(channelPlugins.listChannelTypes);
const listChannelInstances = vi.mocked(channelPlugins.listChannelInstances);
const createChannelInstance = vi.mocked(channelPlugins.createChannelInstance);
const patchChannelInstance = vi.mocked(channelPlugins.patchChannelInstance);
const getChannelTimeline = vi.mocked(channelPlugins.getChannelTimeline);
const getChannelLogs = vi.mocked(channelPlugins.getChannelLogs);
const getChannelUsage = vi.mocked(channelPlugins.getChannelUsage);
const getChannelCredential = vi.mocked(channelPlugins.getChannelCredential);
const copyTextToClipboard = vi.mocked(clipboard.copyTextToClipboard);

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
    available: true,
  },
  {
    type_id: "slack",
    display_name: "Slack",
    ingress: "websocket",
    needs_public_url: false,
    available: true,
  },
  {
    type_id: "wecom",
    display_name: "企业微信",
    ingress: "http_webhook",
    needs_public_url: true,
    available: true,
  },
  {
    type_id: "dingtalk",
    display_name: "钉钉",
    ingress: "websocket",
    needs_public_url: false,
    available: true,
  },
  {
    type_id: "wechat_mp",
    display_name: "微信公众号",
    ingress: "http_webhook",
    needs_public_url: true,
    available: false,
  },
];

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

function seedEmpty() {
  listApiPersonas.mockResolvedValue({ personas: [] });
  listChannelInstances.mockResolvedValue({ instances: [] });
  listChannelTypes.mockResolvedValue({ types: sampleTypes });
  listRoles.mockResolvedValue({ roles: [] });
  getChannelLogs.mockResolvedValue({ items: [] });
  getChannelUsage.mockResolvedValue({ totals: {} });
  patchChannelInstance.mockResolvedValue(sampleInstance);
  getChannelCredential.mockResolvedValue({
    kind: "token",
    token: "lc_live_secret",
    prefix: "lc_live_abcd",
    display: "lc_live_secret…",
    copy_text: "lc_live_secret",
    can_copy_full: true,
  });
  copyTextToClipboard.mockResolvedValue(true);
}

afterEach(() => {
  cleanup();
});

beforeEach(() => {
  vi.clearAllMocks();
  seedEmpty();
});

function renderPanel() {
  return render(<ChannelPanel open onRequestClose={() => undefined} />);
}

async function goCreateScript(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "添加通道" }));
  await user.click(await screen.findByRole("button", { name: /脚本 \/ HTTP/ }));
}

describe("ChannelPanel", () => {
  it("keeps the empty home to a single create action", async () => {
    renderPanel();
    expect(await screen.findByText("还没有聊天通道")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "添加通道" })).toBeInTheDocument();
    expect(screen.getByText("聊天通道")).toBeInTheDocument();
    expect(screen.queryByText("开放接口")).toBeNull();
  });

  it("creates a script channel with only a name on the default path", async () => {
    const user = userEvent.setup();
    createChannelInstance.mockResolvedValue({
      ...sampleInstance,
      token: "lc_live_secret",
    });
    renderPanel();
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
    expect(await screen.findByText("悬浮窗 · 密钥可复制 · Tab 直接点开")).toBeInTheDocument();
    expect(screen.queryByText("只显示这一次，请立刻复制保存。")).toBeNull();
  });

  it("lists cards with copyable credentials, a role picker, and collapsed tabs", async () => {
    listApiPersonas.mockResolvedValue({
      personas: [sampleInstance.persona!],
    });
    listChannelInstances.mockResolvedValue({ instances: [sampleInstance] });
    renderPanel();
    expect(await screen.findByText("周报脚本")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "复制" })).toBeInTheDocument();
    expect(screen.getByLabelText("周报脚本 角色")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "停用通道" })).toBeChecked();
    expect(screen.getByRole("tab", { name: "接入说明" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "会话" })).toBeInTheDocument();
    expect(screen.queryByText(/POST \/api\/v1\/chat/)).toBeNull();
    expect(screen.queryByText("详情")).toBeNull();
    expect(screen.queryByText("新建共用角色")).toBeNull();
    expect(screen.queryByRole("button", { name: "查看会话" })).toBeNull();
  });

  it("copies the stored key without regenerating", async () => {
    const user = userEvent.setup();
    listApiPersonas.mockResolvedValue({
      personas: [sampleInstance.persona!],
    });
    listChannelInstances.mockResolvedValue({ instances: [sampleInstance] });
    renderPanel();
    await user.click(await screen.findByRole("button", { name: "复制" }));
    await waitFor(() => {
      expect(getChannelCredential).toHaveBeenCalledWith("k1");
      expect(copyTextToClipboard).toHaveBeenCalledWith("lc_live_secret");
    });
  });

  it("opens a tab pane on the card and folds it when the same tab is clicked again", async () => {
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
    renderPanel();
    await user.click(await screen.findByRole("tab", { name: "接入说明" }));
    expect(await screen.findByText(/POST \/api\/v1\/chat/)).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "接入说明" }));
    expect(screen.queryByText(/POST \/api\/v1\/chat/)).toBeNull();
    await user.click(screen.getByRole("tab", { name: "会话" }));
    expect(await screen.findByText("写一份周报")).toBeInTheDocument();
    expect(screen.getByText("好的")).toBeInTheDocument();
  });

  it("opens per-instance logs from the details tabs", async () => {
    const user = userEvent.setup();
    listApiPersonas.mockResolvedValue({
      personas: [sampleInstance.persona!],
    });
    listChannelInstances.mockResolvedValue({ instances: [sampleInstance] });
    getChannelLogs.mockResolvedValue({
      items: [
        {
          id: "l1",
          ts: "2026-09-14T00:00:00Z",
          level: "info",
          kind: "turn_done",
          message: "回合完成",
          duration_ms: 12,
        },
      ],
    });
    getChannelUsage.mockResolvedValue({
      totals: { calls: 2, total_tokens: 40 },
    });
    renderPanel();
    await user.click(await screen.findByRole("tab", { name: "日志" }));
    expect(await screen.findByText("回合完成")).toBeInTheDocument();
    expect(screen.getByText("调用 2 次 · 40 tokens")).toBeInTheDocument();
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
    renderPanel();
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

  it("lets the user add a Feishu channel while greying out later types", async () => {
    const user = userEvent.setup();
    renderPanel();
    await user.click(await screen.findByRole("button", { name: "添加通道" }));
    expect(screen.getByRole("button", { name: /飞书/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Slack/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /企业微信/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /钉钉/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /微信公众号/ })).toBeDisabled();
    expect(screen.getByText("即将支持")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /飞书/ }));
    expect(
      screen.getByText("填名称和飞书应用凭证。默认走长连接，不需要公网地址。"),
    ).toBeInTheDocument();
    createChannelInstance.mockResolvedValue({
      id: "f1",
      type_id: "feishu",
      name: "飞书助手",
      enabled: true,
      status: "enabled",
      role_id: "ext_f1",
      created_at: "2026-09-14T00:00:00Z",
      config: { app_id: "cli_x", ingress: "websocket" },
      secrets: { app_secret: "pl***cret" },
      persona: sampleInstance.persona,
    });
    await user.type(screen.getByPlaceholderText("例如：飞书助手"), "飞书助手");
    await user.type(screen.getByLabelText("App ID"), "cli_x");
    await user.type(screen.getByLabelText("App Secret"), "secret-value");
    await user.click(screen.getByRole("button", { name: "创建并启用" }));
    await waitFor(() => {
      expect(createChannelInstance).toHaveBeenCalledWith({
        type_id: "feishu",
        name: "飞书助手",
        config: { app_id: "cli_x", ingress: "websocket" },
        secrets: { app_secret: "secret-value" },
      });
    });
    expect(
      await screen.findByText(/请在飞书开放平台开启「长连接」/),
    ).toBeInTheDocument();
  });

  it("toggles a channel instance without leaving the list", async () => {
    const user = userEvent.setup();
    listApiPersonas.mockResolvedValue({
      personas: [sampleInstance.persona!],
    });
    listChannelInstances.mockResolvedValue({ instances: [sampleInstance] });
    patchChannelInstance.mockResolvedValue({
      ...sampleInstance,
      enabled: false,
      status: "disabled",
    });
    renderPanel();
    await user.click(await screen.findByRole("checkbox", { name: "停用通道" }));
    await waitFor(() => {
      expect(patchChannelInstance).toHaveBeenCalledWith("k1", { enabled: false });
    });
  });

  it("binds a channel-specific persona from the card picker", async () => {
    const user = userEvent.setup();
    const shared = sampleInstance.persona!;
    const other = {
      ...sampleInstance,
      id: "k2",
      name: "另一路",
      role_id: "api_k2",
    };
    listApiPersonas.mockResolvedValue({
      personas: [shared],
    });
    listChannelInstances.mockResolvedValue({ instances: [sampleInstance, other] });
    createApiPersona.mockResolvedValue({
      id: "p2",
      name: "周报脚本",
      system_prompt: "",
      created_at: "2026-09-14T00:00:00Z",
      updated_at: "2026-09-14T00:00:00Z",
    });
    patchChannelInstance.mockResolvedValue({
      ...sampleInstance,
      persona_id: "p2",
    });
    renderPanel();
    await user.selectOptions(
      await screen.findByLabelText("周报脚本 角色"),
      "__new_exclusive__",
    );
    await waitFor(() => {
      expect(createApiPersona).toHaveBeenCalledWith({
        name: "周报脚本",
        system_prompt: "",
      });
      expect(patchChannelInstance).toHaveBeenCalledWith("k1", { persona_id: "p2" });
    });
  });

  it("renders as a floating dialog and closes via X, Escape, or click-outside", async () => {
    const user = userEvent.setup();
    const onRequestClose = vi.fn();
    render(
      <div>
        <button type="button">outside</button>
        <ChannelPanel open onRequestClose={onRequestClose} />
      </div>,
    );
    expect(await screen.findByRole("dialog", { name: "聊天通道" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭聊天通道" }));
    expect(onRequestClose).toHaveBeenCalledTimes(1);

    onRequestClose.mockClear();
    await user.keyboard("{Escape}");
    expect(onRequestClose).toHaveBeenCalledTimes(1);

    onRequestClose.mockClear();
    await user.click(screen.getByRole("button", { name: "outside" }));
    expect(onRequestClose).toHaveBeenCalledTimes(1);
  });

  it("keeps shared personas collapsed until opened", async () => {
    const user = userEvent.setup();
    listApiPersonas.mockResolvedValue({
      personas: [sampleInstance.persona!],
    });
    listChannelInstances.mockResolvedValue({ instances: [sampleInstance] });
    renderPanel();
    expect(await screen.findByText("共用角色")).toBeInTheDocument();
    expect(screen.queryByText("新建共用角色")).toBeNull();
    await user.click(screen.getByRole("button", { name: /共用角色/ }));
    expect(await screen.findByRole("button", { name: "新建共用角色" })).toBeInTheDocument();
    expect(screen.getByText("1 个通道在用")).toBeInTheDocument();
  });
});
