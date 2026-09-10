# ADR 2026-09-10：角色统一时间线

## 状态

已采纳（2026-09-10）

## 背景

多角色底座落地后，选中角色只加载 tip（常为空「新对话」），历史被挤进次级抽屉，与「打开通用应看到全部旧聊天」不符。

## 决策

1. **角色 = 一条聊天时间线**：中栏展示该 `role_id` 下全部 `conversation` 段（旧→新），段间分隔线；只写 tip。
2. **不物理合并**会话行；跨段 **不**自动拼进 Agent `history`。
3. **新 tip 首轮**服务端默认检索本角色会话 + KB，注入检索摘要；关段触发既有记忆抽取。
4. 废弃「主区只看活跃线 / 历史抽屉为主」的交互叙事；历史抽屉可保留为可选，搜索改为时间线内定位。

细节见 [product-multi-role.md](../product-multi-role.md)「统一时间线」节。

## 后果

- API：`GET /api/roles/{id}/timeline`、`POST .../new-topic`；检索支持 `role_id`。
- 前端：`ChatMessageList` 多段 + 分隔；`RoleList` 搜索 / 新话题。

## 明确不采用

- 多段合并成单一 conversation 行
- 跨段自动拼接 history
- VM / 桌面屏 UI
