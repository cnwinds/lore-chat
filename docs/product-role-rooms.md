# 角色互通与群聊（提案）

> 状态：**待拍板**。本文不是已采纳 ADR。拍板后再拆 ADR + 实现。
>
> 配套现状：[ADR 2026-09-09 多角色底座](adr/2026-09-09-multi-role-shell.md)、[ADR 2026-09-10 统一时间线](adr/2026-09-10-role-timeline.md)、[ADR 2026-09-10 每角色沙箱](adr/2026-09-10-role-scoped-sandbox.md)、[product-multi-role.md](product-multi-role.md)。
>
> 目标：主人可以对角色说「你去喊游戏开发助手做 X」；对方像接到一条入站消息一样开回合干活，做完能回话。底层必须能直接长出群聊，而不是先做点对点再推翻。

## 0. 一句话

**不要做「角色 A 调用角色 B」的点对点特判。** 做成四件东西：

| 概念 | 含义 |
|------|------|
| Actor | 谁在说话：主人 / 某个角色 / 系统 |
| Room | 一间共享房间：同一份时间线，多个参与者 |
| Delivery | 往房间里贴一条带说话人身份的消息 |
| Wake | 按策略唤醒 0～N 个角色，各自用自己的人设、history、沙箱跑一轮 |

现有「主人 ↔ 某角色」是房间的第一种。一对一委托是两人房间。群聊是多人房间。机制相同，策略不同。

## 1. 用户体验

### 1.1 主人仍跟一个人说话

主人继续待在「通用助手大师」的时间线里，像现在这样聊天。不必先建群、不必先切到对方。

> 「你去喊游戏开发助手，把登录页的演示数据换成真实接口。」

通用助手理解后**投递**一条消息给游戏开发助手，并在当前对话里落下一张**协作卡**（不是假装自己变成了对方）：

- 发给谁、说了什么（可展开）
- 状态：排队中 / 工作中 / 等你确认 / 已回执 / 失败
- 「查看协作」：跳到双方共享的那间房间

主人可以继续跟通用助手说话。对方在自己的沙箱里干活，不打断这边。

### 1.2 被喊到的角色：入站消息，不是主人冒充

游戏开发助手**不是**在主人跟他的日常 tip 里被插入一句假「用户说」。而是：

1. 进入（或复用）一间 **peer 房间**：参与者 = 通用助手 + 游戏开发助手，主人是观察者，可插话。
2. 看到一条**来自「通用助手大师」**的气泡（头像 + 名字），不是主人气泡。
3. 系统按这条入站刺激开一轮：工具、沙箱、检索，能力与主人直接说话相同。
4. 工作过程留在这间房间。主人切到游戏开发助手时，时间线上能看到这段协作（特殊分隔：「与「通用助手大师」协作」）。

对模型：像接到一条要办事的消息。对系统：说话人是同伴，不是主人。

### 1.3 回话怎么回到主人眼前

游戏开发助手做完后，应**显式回执**（工具投递，而不是把整段工作独白自动转发给对方）：

- 回执贴进同一间 peer 房间。
- 若这次委托源自「主人 ↔ 通用助手」那条线，再**唤醒通用助手的 tip**：入站刺激 = 同伴回执。通用助手向主人转述：「同学做完了，登录页已接上真实接口。」
- 协作卡同步成「已回执」。

主人也可以不管通用助手，直接打开协作房间或切到游戏开发助手，自己看过程、自己插话。

### 1.4 群聊（P2，但现在就要能长出来）

主人建一间群，圈几个角色。入口在左栏角色列表下的 **「群聊」**，不挂在某一个角色头上。

- 中栏是**一份**共享时间线。
- 主人在群里说话；`@游戏开发助手` 才唤醒对方。没 @ 就不自动全员抢麦。
- 角色也可以往群里发；默认只唤醒被 @ 的人。
- 高风险沙箱确认、`ask_user` 仍然只问**主人**，协作卡 / 群消息上露出「某角色在等你确认」。

一对一委托 = 两人房间 + 「另一方默认唤醒」。群 = 多人房间 + 「只有被点名的才唤醒」。没有第二套引擎。

### 1.5 明确不要的体验

- 通用助手在自己的气泡里**扮演**游戏开发助手（「我已经是游戏开发助手了」）。
- 把同伴的话画成主人气泡，或写进主人画像。
- 为了委托把主人当前 tip 和对方 tip 揉成一段 history。
- 对方正在跟主人聊天时，硬打断他的回合去接委托（排队，卡上写「对方正忙」）。
- 第一期就做「全员群里自由吵」——没有点名策略会变成死循环抢麦。

## 2. 现有底座拦得住什么

现在会话是「一角房间」：

| 现状 | 卡点 |
|------|------|
| `conversations.role_id` 单归属 | 时间线 = `WHERE role_id=?`，两人共享房间无处挂 |
| `messages.role` 只有 `user` / `assistant` | 同伴入站只能假扮主人，记忆抽取会当成主人自述 |
| `begin_turn` 固定插入 `role='user'` | 定时任务、引导开场已经在假扮用户；再加一条假扮会更脏 |
| `turns` = 一条 user → 一条 assistant | 没记录「这一轮是谁在应」 |
| 每角色一把沙箱、`role_has_running_turn` | 对：角色串行。委托必须排队，不能借别人的沙箱 |
| Agent `history` 仅当前会话段 | 对。协作必须自己有一段，不要拼进主人 tip |
| 定时任务把 `prompt` 当 `user_text` 打进 tip | 可复用「非主人触发回合」，但**不要**再扩这种假扮 |

结论：第一期就要把「谁在说话 / 这轮谁应 / 房间有谁」变成一等事实。否则群聊还得翻一次存储和 transcript。

## 3. 底层模型

### 3.1 Actor

```text
Actor = { kind: user | role | system, id }
```

- `user`：知识库主人，id 固定（单用户产品，不必先做多主人）。
- `role`：`roles.id`。
- `system`：投递失败、回路熔断、排队说明。不进记忆抽取。

### 3.2 Room = 广义 conversation

**不另做一套消息库。** 给现有 `conversations` 加上种类与参与者。现有行回填为 `owner_dm`。

```text
conversations.kind:
  owner_dm   主人 ↔ 单角色（今天的全部会话）
  peer_dm    两角色协作；主人默认 observer
  group      群聊；主人默认 member

conversation_participants
  conversation_id
  actor_kind          user | role
  actor_id
  membership          member | observer
  last_read_at
```

规则：

- `owner_dm`：`role_id` 仍是「主场角色」；参与者回填 `{user, member}` + `{role, member}`。tip / 连续窗口 / 「新话题」**只在这个 kind 上算**。
- `peer_dm`：恰好两个 role member；`role_id` 不再当唯一归属。按 `{role_a, role_b}` 去重复用，不每次委托新开一间。
- `group`：N 个 role member + user member。独立标题。
- 角色时间线改为：**我是 participant 的房间**（含 observer）。`owner_dm` 与协作段都出现；可写 tip 仍只来自自己的 `owner_dm`。
- 群聊主入口是左栏「群聊」，不依赖先选中某个角色。角色时间线上可再挂一条「参与了某群」的投影/链接。

### 3.3 Message：LLM 线角色 ≠ 说话人

```text
messages.role            仍是 user | assistant（给现有 UI / transcript 一条兼容线）
messages.speaker_kind    user | role | system
messages.speaker_id
messages.causation_id    这次委托链的根（通常是主人那句）
messages.hop             从根算起的跳数
```

写入约定：

| 事件 | `role` | `speaker_*` |
|------|--------|-------------|
| 主人说话 | `user` | `user` |
| 同伴入站（唤醒刺激） | `user` | `role` + 对方 id |
| 本角色回应当轮 | `assistant` | `role` + 自己 id |
| 本角色主动投递的正文 | 见实现：以 speaker 为准，transcript 按「应者」重映射 | `role` + 自己 id |

**禁止**再出现「定时 / 引导 / 同伴」三种假用户却没有 speaker。定时与引导应迁到同一套 `InboundStimulus`（可稍后，但接口现在就要留）。

### 3.4 Turn：刺激 → 一个应者

```text
turns.responding_role_id
turns.inbound_message_id     取代「只能是 user_message」的语义
```

一间房间**同时只准一个角色在说**（房间锁）。一个角色**同时只准一个 running turn**（已有角色锁 + 沙箱槽）。不同角色、不同房间可以并行——这正是每角色沙箱的用途。

对方正忙：入站进**服务端** `role_inbound_queue`，不借用前端出站队列，不 `interrupt`。协作卡：「排队中（对方正忙）」。

### 3.5 唯一投递 seam：Delivery + Wake

所有非 HTTP 直打的发言（工具委托、回执、群里角色发言、以及未来定时）只走：

```text
RoomDelivery.post(room_id, speaker, text, *,
                  reply_to=None, mentions=[], expect_reply=True,
                  causation_id=None, hop=0) -> Message

WakePolicy.targets(room, message) -> [role_id...]
# 对每个 target：有角色锁则入队，否则 begin_persisted_turn(stimulus)
```

`TurnExecutionHub` / `begin_persisted_turn` 继续跑 Agent。HTTP `/api/chat` 仍然只负责主人在当前 tip 里打字。路由**不**解析房间策略。

默认唤醒：

| 房间 | 说话人 | 唤醒谁 |
|------|--------|--------|
| `owner_dm` | 主人 | 主场角色 |
| `peer_dm` | 角色 A | 角色 B（若 hop 未超限） |
| `peer_dm` | 主人插话 | 被 @ 的人；没 @ 则唤醒「上一轮应者」 |
| `group` | 任何人 | **仅** `mentions`；没点名则不唤醒角色 |
| 任意 | 自己 | 永不唤醒自己 |

委托回执额外一步（不是第二条总线）：若 `causation` 来自某角色的 `owner_dm`，且 `expect_reply`，则在该 tip **再投一条刺激**（inject 或排队 `begin_turn`），让发起方转述给主人。刺激正文带同伴身份包装，不是主人原话。

### 3.6 回路

| 规则 | 作用 |
|------|------|
| `hop` 上限（建议 4） | A→B→A→B 不会无限派工 |
| 回执轮 system 提示 | 「这是协作回执，向主人交代结果；没有新指令不要再派工」 |
| 同房间冷却 | 短时间同一对来回超过阈值，停并问主人 |
| 不唤醒说话者本人 | 避免自言自语开回合 |
| 高风险仍走 `SandboxCommandGate` | 同伴不能替主人点「批准」 |
| `ask_user` 只问主人 | 同伴的话不能当征询答案 |

### 3.7 主路径时序

```text
主人 ──说──► owner_dm(通用助手)
                │
                │ send_message(to=游戏开发助手, text=…)
                ▼
         find_or_create peer_dm(通用, 游戏)
         post(speaker=通用, hop=1, causation=主人那句)
         通用 tip 上落协作卡
                │
                ▼
         Wake(游戏开发助手) ──► peer_dm 上开回合
                │                 （对方忙则入队）
                │ 干活：检索 / 沙箱 / 写库…
                │ send_message 回执
                ▼
         post(speaker=游戏, hop=2)
         Wake(通用助手) 于 owner_dm tip
                │
                ▼
         通用助手向主人转述
```

群聊把中间的 `peer_dm` 换成 `group`，把「唤醒另一方」换成「唤醒 mentions」。

## 4. 对模型：像用户消息，但不是主人

`ConversationTranscript` 按**本轮 `responding_role_id`** 重映射，不要按存储的 `messages.role` 死译：

- 应者自己先前的发言 → `assistant`
- 其它人 → `user`，正文包一层身份，例如：

```text
<peer_message from="通用助手大师" role_id="…">
请把登录页的演示数据换成真实接口。
</peer_message>
```

能力与主人回合相同（同一套 tool catalog / 沙箱槽 / 检索）。身份不同。

注入原则（写原则，不写个案黑名单）：

1. **发言者是事实。** 只有 `speaker_kind=user` 才是主人；同伴 / 系统 / 定时都不是。
2. **你只能当当前角色。** 派工是投递，不是换皮。
3. **回执先交代结果。** 不要把对方的话改写成主人自述，也不要无新指令再派工。
4. ≥2 个角色时注入**角色名录**（id、名称、一句职责、是否忙碌），并开放 `send_message`。

记忆（AGENTS.md 三道门槛仍然够用，差的是输入层）：

- 抽取输入不得把 `speaker_kind!=user` 写成主人行。
- 纯同伴房间（主人从未插话）不打记忆 dirty / 不抽取。
- 「去喊同学做 X」落在主人 tip 里，通常是任务不是画像，耐久性门槛会挡；不要为此加关键词黑名单。

定时任务今天把 prompt 当作用户消息；迁到 `InboundStimulus(source=schedule, speaker=system)` 后，抽取也不会再误伤。可与本需求同一接口、分 commit。

## 5. Agent 工具

角色配置已经以工具为主要接口（见 product-multi-role §3.3）。互通同样走工具，不另开一套 HTTP 编排。

| 工具 | 职责 |
|------|------|
| `list_roles` | 名称 / id / 职责摘要 / 是否忙碌。派工前用来对齐名字。 |
| `send_message` | `to_role_id` 或 `to_role_name` 或 `room_id` + `text` + `expect_reply` + 可选 `mentions`。无 `room_id` 则 find_or_create `peer_dm`。 |
| `list_rooms` | P2：当前角色参与的协作 / 群。 |
| `create_room` | P2：建群（标题 + 角色列表）。也可由 UI 调 HTTP。 |

`send_message` 的工具结果必须带 `room_id`、`message_id`、目标状态（已唤醒 / 已排队），前端才能画协作卡。不要让模型编会话 id 当导航；沿用 `conversation://` 链接约定。

HTTP 只保留 shell：房间列表、时间线包含协作段、群聊 CRUD、跳转。创建与投递的权威路径仍是 Delivery，UI 与工具共用，禁止在 `role_routes` 里再写一套唤醒。

## 6. 前端怎么长

### 6.1 第一期（能用）

- 协作卡：特殊渲染 `send_message` 工具块（状态可轮询或挂该房间 turn 的 SSE）。
- 同伴气泡：`speaker_kind=role` 且不是「当前选中角色的应声」时，用对方头像 + 名字，不用主人气泡。
- 「查看协作」：切到对方角色时间线并滚到该 `peer_dm` 段，或直接打开该 conversation。第一期跳转即可，不必做实时分屏。
- 角色列表忙碌角标复用现有 `GET /api/roles/busy`；排队中的委托不算 running，卡上自己写排队。

### 6.2 紧接着（P1）

- 双方时间线都出现协作段，分隔文案与「超时新话题」区分开。
- 协作段可「插话」（点名或默认上一应者）。**不**把协作段变成该角色的 tip。
- 协作卡实时更新最后一行预览。

### 6.3 群聊（P2）

- 左栏角色列表与 KB 之间加「群聊」。
- 选中群：中栏只显示该房间；composer 是主人在对房间说话，`@` 出角色。
- 不出现 VM / 桌面屏（沿用多角色 ADR）。

## 7. 和现有 seam 怎么接

| 层 | 做法 |
|----|------|
| HTTP `/api/chat` | 主人 tip 照旧；不解析委托 |
| `TurnExecutionHub` | `begin_and_ensure` 接受 `InboundStimulus`，不只接受 `user_text` |
| `TurnLifecycle.begin_turn` | 按 stimulus 写 speaker；定时 / 引导日后同一入口 |
| `RoomDelivery` | **新** deep module：贴消息 + 调 Wake；Container 持一份 |
| `role_inbound_queue` | 角色锁满时入队；可挂在现有 schedule worker 旁，或同 loop 轻扫 |
| 沙箱 | 仍 `conversation` → 应者 `role_id` → `RoleSandboxPool.get`；禁止借用 |
| 时间线 API | `GET /api/roles/{id}/timeline` 改为 participant 并集；tip 算法仍只看 `owner_dm` |
| 记忆 | `session_observe` / `dialogue_timeline_pack` 只把主人 speaker 当用户行 |
| 检索 | `search_kb(scope=conversations)` 可按 `room_id` / kind 过滤；跨房间回忆仍须检索，不自动拼 history |

## 8. 分期

**P0 — 两人委托能跑通（建议第一刀就做完抽象列，避免假用户再扩散）**

- 表：`kind`、`participants`、`speaker_*`、`causation/hop`、`responding_role_id`、入站队列。
- 旧会话回填 `owner_dm` + 参与者。
- `InboundStimulus` + transcript 按应者重映射。
- `list_roles` / `send_message`；find_or_create `peer_dm`；Wake + 排队 + hop。
- 发起方 tip 协作卡；回执唤醒发起方 tip。
- 记忆不抽同伴行；角色名录注入。
- 单角色时不暴露 `send_message`。

**P1 — 时间线与插话**

- 协作段出现在双方时间线；跳转与插话。
- 卡状态实时；「等你确认」从对方 `ask_user` / 沙箱门透出。

**P2 — 群聊**

- `group` + 左栏入口 + `@` 唤醒。
- `create_room` / UI 建群。
- 房间锁：群内串行发言；跨房间跨角色仍并行。

## 9. 验收意图（根因同类，不写死原句）

- 主人对 A 说「让 B 做一件具体事」→ A 调用 `send_message`，B 的 peer 房间出现**同伴**入站并开回合，B 的 owner_dm tip 不被塞假用户句。
- B 做完回执 → A 的 tip 被唤醒并转述；hop 再往下派工会被上限 / 回执提示拦住。
- B 正忙 → 卡显示排队，不打断 B 当前回合，不借用 B 的沙箱给别人。
- 记忆：同伴说「主人喜欢 X」不进画像；主人自己在 tip 里说的稳定偏好仍可抽。
- B 调 `ask_user` 或高风险沙箱 → 问的是主人，不是 A。
- 换一种措辞的委托（「转告 / 请同学 / @B」）只要模型调用同一工具，路径相同——不靠句式补丁。
- P2：群里不 @ 则无人自动应；@ 谁谁应。与 peer 默认唤醒另一方是同一 Wake，不同策略。

## 10. 明确不采用

- **收件箱各写一份**：A、B 各存副本。群聊会分叉，主人没有唯一现场。
- **同一回合里嵌套 subagent**：A 的工具循环里同步跑完 B。B 没有自己的时间线 / 人设 / 沙箱槽，也做不出异步与群聊。
- **只把 B 的结果当 A 的 tool_result**：B 不能多轮、不能征询、主人不能中途跟 B 说话。
- **新建平行 Room 消息表却继续用旧 messages 跑 Agent**：两套 transcript 必漂。
- **同伴入站继续 `role='user'` 且不记 speaker**：记忆与 UI 会把同学当成主人。

## 11. 请拍板的三点

1. **委托后对方是否自动开干？** 建议：**自动**。高风险与征询仍走现有主人确认。若改成「每次委托先问主人」，协作卡多一步批准，适合更谨慎，但不如你描述的「喊他去做」。
2. **协作房间要不要上双方时间线？** 建议：P0 跳转能看即可，**P1 必须上**，否则「切到游戏开发助手看不到被喊了什么」。
3. **群聊入口？** 建议：左栏独立「群聊」。群不属于某一个角色；只挂在角色时间线上，主人会找不到房间。

拍板后下一步：按本文落 ADR（只写已定决策），再开 P0 实现，不在本提案里直接改引擎。
