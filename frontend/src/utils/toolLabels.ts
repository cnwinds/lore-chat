export const TOOL_LABELS: Record<string, string> = {
  search: "检索知识与会话",
  read: "读取内容",
  list: "浏览目录",
  search_kb: "检索本地知识库",
  read_doc: "读取文档",
  read_doc_meta: "读取文档元数据",
  list_kb_structure: "查看知识库目录结构",
  read_conversation_context: "读取会话上下文",
  recall_memory: "回忆已确认的用户画像",
  recall_cards: "查阅角色知识卡",
  fetch_url: "打开链接",
  web_search: "搜索网页",
  generate_image: "生成图片",
  write_doc: "写入文档",
  write_kb_file: "写入知识库代码/文本文件",
  summarize_conversation: "归档整段会话",
  delete_kb: "删除知识库内容",
  ask_user: "征询用户",
  list_roles: "列出角色",
  create_role: "创建角色",
  send_message: "发给其他角色",
  list_rooms: "列出协作房间",
  list_groups: "列出群聊",
  create_room: "创建群聊",
  create_group: "创建群聊",
  update_group: "更新群聊",
  delete_group: "删除群聊",
  edit_doc: "局部编辑文档",
  update_doc_meta: "更新文档元数据",
  move_entry: "移动或重命名路径",
  move_doc: "移动或重命名路径",
  sandbox_run: "在沙箱执行命令",
  sandbox_list_dir: "列出沙箱目录",
  sandbox_read_file: "读取沙箱文件",
  publish_from_sandbox: "从沙箱发布到知识库",
  stage_to_sandbox: "将知识库文件批量投放到沙箱",
  sandbox_job_status: "查询沙箱后台任务",
};

/** 与后端 resolve_tool_label 对齐：SVG 按矢量图展示，而非代码/文本。 */
export function resolveToolLabel(
  tool: string,
  input?: Record<string, unknown> | null,
): string {
  if (tool === "write_kb_file" && input && typeof input === "object") {
    const fn = String(input.filename ?? "").trim().toLowerCase();
    if (fn.endsWith(".svg")) return "写入知识库矢量图";
  }
  return TOOL_LABELS[tool] || tool;
}
