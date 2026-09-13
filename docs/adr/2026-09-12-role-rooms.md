# ADR 2026-09-12：角色互通（房间 + 投递 + 唤醒）

## 状态

已采纳（2026-09-12）。产品展开见 [product-role-rooms.md](../product-role-rooms.md)。

## 背景

多角色并行之后，主人希望对 A 说「去喊 B 做 X」，B 像接到入站消息一样开回合，做完能回话。后续还要群聊。现有会话是一角房间：`conversations.role_id` 单归属，`messages.role` 只有 user/assistant，非主人触发（定时、引导）已在假扮用户。

## 决策

1. **四件东西，不点对点特判。** Actor / Room（广义 conversation）/ Delivery / Wake。`owner_dm` 是第一种房间；两人委托是 `peer_dm`；群聊是 `group`。同一套投递，唤醒策略不同。
2. **说话人 ≠ LLM 线角色。** `messages.speaker_kind/id` 是事实；`messages.role` 仍服务现有 transcript。禁止再扩「假用户」而不记 speaker。
3. **Turn = 一条刺激 → 一个应者。** `turns.responding_role_id`；房间锁一人在说，角色锁沿用现有 `role_has_running_turn` + 每角色沙箱。忙则入站排队，不打断、不借槽。
4. **委托自动开干。** 高风险沙箱与 `ask_user` 仍只问主人。hop 上限 4，回执轮不无指令再派工。
5. **协作房间上双方时间线。** tip / 新话题 / 连续窗口只看 `owner_dm`。`peer_dm`/`group` 经参与者并入时间线，不劫持 tip。
6. **群聊左栏独立入口**（P2 做 UI）。群不属于某一个角色。P0 只把 `kind=group` 与 `@` 唤醒策略留在 Delivery 里。
7. **Agent 工具是派工主接口。** `list_roles` / `send_message`。HTTP 只做 shell。单角色不暴露 `send_message`。
8. **记忆。** 抽取不得把 `speaker_kind!=user` 写成主人行。纯同伴房间不打 dirty。

## 后果

- `ConversationStore` 增加 kind / participants / speaker / inbound queue；`RoomDelivery` 是唯一非 HTTP 贴消息 + 唤醒 seam。
- `TurnExecutionHub.begin_and_ensure` 接受 `InboundStimulus`；sandbox / 人设按应者 `role_id`，不按 peer 房间的占位 `role_id`。
- 前端：同伴气泡、`send_message` 协作卡、时间线协作段分隔。

## 明确不采用

- 收件箱各写一份（群会分叉）
- 同一回合嵌套 subagent
- 只把对方结果当 tool_result、对方没有自己的房间
- 平行 Room 消息表与旧 messages 双轨
