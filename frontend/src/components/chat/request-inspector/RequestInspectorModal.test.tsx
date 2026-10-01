import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { RequestCallSummary, RequestDetail } from "../../../api";
import {
  getConversationRequest,
  getConversationRequestRaw,
  listConversationRequests,
} from "../../../api";
import { buildCatalogGroups } from "./requestInspectorGroups";
import { RequestInspectorModal } from "./RequestInspectorModal";

const longText = `${"行\n".repeat(50)}末尾`;

const detail: RequestDetail = {
  id: 2,
  turn_id: "t1",
  round: 2,
  ts: "2026-01-01T00:00:00Z",
  status: "error",
  error: "provider down",
  attempts: 1,
  model: "m",
  model_label: "Demo",
  params: {},
  usage: { prompt_tokens: 100, completion_tokens: 5, cache_tokens: null },
  limit_tokens: 8000,
  estimated: false,
  categories: [
    { key: "rules", label: "系统规约", tokens: 40 },
    { key: "history", label: "历史对话", tokens: 20 },
    { key: "turn", label: "本轮消息", tokens: 30 },
    { key: "tool_io", label: "工具往返", tokens: 10 },
  ],
  messages: [
    {
      index: 0,
      role: "system",
      tokens: 40,
      segments: [
        { kind: "rules", category: "rules", label: "系统控制层", text: "规则", tokens: 20 },
        { kind: "role", category: "role", label: "当前角色", text: "人设", tokens: 20 },
      ],
      tool_calls: null,
      tool_call_id: null,
    },
    {
      index: 1,
      role: "user",
      tokens: 20,
      segments: [
        { kind: "history", category: "history", label: "主人", text: "历史主人话", tokens: 20 },
      ],
      tool_calls: null,
      tool_call_id: null,
    },
    {
      index: 2,
      role: "user",
      tokens: 30,
      segments: [
        { kind: "time", category: "context", label: "当前时间", text: "【当前时间】\n周一", tokens: 5 },
        { kind: "user_text", category: "turn", label: "主人", text: longText, tokens: 20 },
        {
          kind: "attachment",
          category: "turn",
          label: "附件「图.png」",
          text: "",
          tokens: 5,
          media: { type: "image", name: "图.png" },
        },
      ],
      tool_calls: null,
      tool_call_id: null,
    },
    {
      index: 3,
      role: "assistant",
      tokens: 5,
      segments: [
        { kind: "tool_call", category: "tool_io", label: "调用 read_doc", text: "", tokens: 5 },
      ],
      tool_calls: [{ id: "1", name: "read_doc", arguments: { path: "a.md" } }],
      tool_call_id: null,
    },
    {
      index: 4,
      role: "tool",
      tokens: 5,
      segments: [
        {
          kind: "tool_result",
          category: "tool_io",
          label: "结果 read_doc",
          text: '{"ok":true}',
          tokens: 5,
        },
      ],
      tool_calls: null,
      tool_call_id: "1",
    },
    {
      index: 5,
      role: "user",
      tokens: 1,
      segments: [
        { kind: "unlabeled", category: "unlabeled", label: "", text: "漏标", tokens: 1 },
      ],
      tool_calls: null,
      tool_call_id: null,
    },
  ],
  tools: [
    {
      name: "read_doc",
      description: "读取文档。第二句。",
      parameters: { type: "object", properties: { path: { type: "string" } } },
      tokens: 12,
    },
  ],
};

const calls: RequestCallSummary[] = [
  {
    id: 2,
    turn_id: "t1",
    round: 2,
    ts: "2026-01-01T00:00:00Z",
    status: "error",
    prompt_tokens: 100,
    model_label: "Demo",
    cache_tokens: null,
    completion_tokens: 5,
    message_count: 6,
    tool_count: 1,
  },
  {
    id: 1,
    turn_id: "t1",
    round: 1,
    ts: "2026-01-01T00:00:00Z",
    status: "ok",
    prompt_tokens: 80,
    model_label: "Demo",
    cache_tokens: null,
    completion_tokens: 3,
    message_count: 4,
    tool_count: 1,
  },
];

vi.mock("../../../api", () => ({
  listConversationRequests: vi.fn(),
  getConversationRequest: vi.fn(),
  getConversationRequestRaw: vi.fn(),
}));

beforeEach(() => {
  vi.mocked(listConversationRequests).mockResolvedValue({ calls });
  vi.mocked(getConversationRequest).mockResolvedValue(detail);
  vi.mocked(getConversationRequestRaw).mockResolvedValue({ messages: [], model: "m" });
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("RequestInspectorModal", () => {
  it("目录分组：system 块、历史默认收起、本轮、工具往返、工具定义", async () => {
    const groups = buildCatalogGroups(detail);
    expect(groups.map((g) => g.title)).toEqual([
      "system",
      "历史 · 1 条",
      "本轮 · 主人",
      "工具往返 · 2 次",
      "工具定义 · 1 个",
    ]);
    expect(groups[0].defaultOpen).toBe(true);
    expect(groups[1].defaultOpen).toBe(false);
    expect(groups[0].lines.map((l) => l.label)).toEqual(["系统控制层", "当前角色"]);
  });

  it("点目录项滚动到分段", async () => {
    const user = userEvent.setup();
    render(
      <RequestInspectorModal
        open
        conversationId="c1"
        initialCategory={null}
        initialCallId="latest"
        onClose={() => {}}
      />,
    );
    await screen.findByText("规则");
    const catalog = document.querySelector(".reqinspector-catalog")!;
    await user.click(within(catalog as HTMLElement).getByText("当前角色"));
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
  });

  it("类别筛选让其它块变淡", async () => {
    const user = userEvent.setup();
    render(
      <RequestInspectorModal
        open
        conversationId="c1"
        initialCategory={null}
        initialCallId={2}
        onClose={() => {}}
      />,
    );
    await screen.findByText("规则");
    const bar = document.querySelector(".reqinspector-bar-seg")!;
    await user.click(bar);
    expect(document.querySelector(".reqinspector-seg--dim")).toBeTruthy();
  });

  it("未标注、超长段展开、tool_calls 显示", async () => {
    const user = userEvent.setup();
    render(
      <RequestInspectorModal
        open
        conversationId="c1"
        initialCategory={null}
        initialCallId={2}
        onClose={() => {}}
      />,
    );
    await screen.findByText("未标注");
    expect(screen.getByText(/read_doc\(/)).toBeInTheDocument();
    expect(screen.queryByText(/末尾/)).toBeNull();
    await user.click(screen.getByRole("button", { name: /展开全部/ }));
    expect(await screen.findByText(/末尾/)).toBeInTheDocument();
  });

  it("搜索高亮与计数、命中收起段自动展开", async () => {
    const user = userEvent.setup();
    render(
      <RequestInspectorModal
        open
        conversationId="c1"
        initialCategory={null}
        initialCallId={2}
        onClose={() => {}}
      />,
    );
    await screen.findByText("规则");
    const input = screen.getByPlaceholderText("在正文中搜索…");
    await user.type(input, "末尾");
    expect(screen.getByText("1 / 1")).toBeInTheDocument();
    expect(document.querySelector("mark.reqinspector-mark")).toBeTruthy();
    expect(screen.getByText("末尾")).toBeInTheDocument();
  });

  it("工具结果只渲染一次，命中数与高亮数一致", async () => {
    const user = userEvent.setup();
    render(
      <RequestInspectorModal
        open
        conversationId="c1"
        initialCategory={null}
        initialCallId={2}
        onClose={() => {}}
      />,
    );
    await screen.findByText("规则");
    await user.type(screen.getByPlaceholderText("在正文中搜索…"), "ok");
    expect(screen.getByText("1 / 1")).toBeInTheDocument();
    expect(document.querySelectorAll("mark.reqinspector-mark")).toHaveLength(1);
  });

  it("命中工具描述后半句时自动展开该工具", async () => {
    const user = userEvent.setup();
    render(
      <RequestInspectorModal
        open
        conversationId="c1"
        initialCategory={null}
        initialCallId={2}
        onClose={() => {}}
      />,
    );
    await screen.findByText("规则");
    await user.type(screen.getByPlaceholderText("在正文中搜索…"), "第二句");
    expect(screen.getByText("1 / 1")).toBeInTheDocument();
    const tools = screen.getByRole("region", { name: /工具定义/ });
    expect(within(tools).getByText("第二句").tagName).toBe("MARK");
  });

  it("切换调用请求对应 id", async () => {
    const user = userEvent.setup();
    render(
      <RequestInspectorModal
        open
        conversationId="c1"
        initialCategory={null}
        initialCallId={2}
        onClose={() => {}}
      />,
    );
    await screen.findByText("规则");
    await user.selectOptions(screen.getByRole("combobox"), "1");
    await waitFor(() =>
      expect(getConversationRequest).toHaveBeenCalledWith("c1", 1),
    );
  });

  it("失败调用显示中文状态与错误", async () => {
    render(
      <RequestInspectorModal
        open
        conversationId="c1"
        initialCategory={null}
        initialCallId={2}
        onClose={() => {}}
      />,
    );
    expect(await screen.findByText(/失败：provider down/)).toBeInTheDocument();
  });

  it("原始视图拉 raw 并显示", async () => {
    const user = userEvent.setup();
    render(
      <RequestInspectorModal
        open
        conversationId="c1"
        initialCategory={null}
        initialCallId={2}
        onClose={() => {}}
      />,
    );
    await screen.findByText("规则");
    await user.click(screen.getByRole("button", { name: "原始" }));
    await waitFor(() =>
      expect(getConversationRequestRaw).toHaveBeenCalledWith("c1", 2),
    );
    expect(screen.getByText(/"model": "m"/)).toBeInTheDocument();
  });

  it("工具定义可展开", async () => {
    const user = userEvent.setup();
    render(
      <RequestInspectorModal
        open
        conversationId="c1"
        initialCategory={null}
        initialCallId={2}
        onClose={() => {}}
      />,
    );
    const tools = await screen.findByRole("region", { name: /工具定义/ });
    await user.click(within(tools).getByRole("button", { name: /read_doc/ }));
    expect(await within(tools).findByText(/第二句/)).toBeInTheDocument();
  });

  it("空状态与 Esc 关闭", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    vi.mocked(listConversationRequests).mockResolvedValue({ calls: [] });
    render(
      <RequestInspectorModal
        open
        conversationId="c1"
        initialCategory={null}
        initialCallId={null}
        onClose={onClose}
      />,
    );
    expect(await screen.findByText("还没有发给模型的请求")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });
});
