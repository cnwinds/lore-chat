# 通道插件（外部对接）

> 状态：**草案 / 待确认**（2026-09-14）。尚未实现。实现前须主人确认 §12。
>
> 用户原话：开放接口想开发成类似插件的东西。包括后续的微信、钉钉、飞书、Slack 等外部对接都走插件方式。每个插件可以配置不同的参数。配置完成启用后，就可以和外部聊天。
>
> 配套：[product-external-chat-api.md](product-external-chat-api.md)（**已确认**的脚本 API 口径，本文不改写）、[ADR 草案 2026-09-14 channel-plugins](adr/2026-09-14-channel-plugins.md)、[CONTEXT.md](../CONTEXT.md)（HTTP **不**重编排 Agent）。

## 与已确认文档的关系

| 文档 | 关系 |
|------|------|
| [product-external-chat-api.md](product-external-chat-api.md) | **并列、被包含。** 脚本 Key / `POST /api/v1/chat` / 人设可共享 / 每 Key 一个隐藏工作角色，仍以该文为权威。本文是其**超集**：把那一套收成内置插件类型 `script_api`，并规定微信/钉钉/飞书/Slack 等走同一框架。 |
| 本文 | 通道插件的产品 + 架构草案。确认后实现；**不**替代上一文。 |
| 已确认口径 | 除非 §11 显式提议变更，否则实现须继续遵守对外聊天 API 文。 |

现网对照（以代码为准）：`OpenApiService.complete_chat`（验 Key → 取 hidden `role_id` → `begin_persisted_turn`，`mode=api`，`origin=api`）；设置页「开放接口」= 密钥列表 + 折叠「调用方式」+ 「说话方式」。

## 0. 一句话

插件只做 **外部协议 ↔ lore-chat 内部回合** 的适配。配好参数、启用后，外部消息进来，走现有隐藏工作角色 + 人设 + `ChatSessionRunner`，回复写回外部。对话能力不另造一套 Agent。

脚本 API 是第一种插件；IM 是同一种东西的其它类型。设置里统一管，现有密钥继续能用。

---

## 1. 定位与边界

### 1.1 两层各干什么

| 层 | 负责 | 不负责 |
|----|------|--------|
| **插件 / 通道** | 厂商鉴权与签名、webhook/长连接、配置 schema、把外部事件收成内部用户消息、把助手回复打回外部 | 选模、工具循环、人设注入、沙箱、时间线投影 |
| **现有聊天引擎** | `begin_persisted_turn` → `TurnExecutionHub` → Agent；hidden role、persona 活引用、`mode=api` 工具集 | 解析 Slack/飞书 payload |

HTTP 路由只验签、拆 DTO、交给插件再交给 runner。**禁止**在 webhook handler 里再写一套 Agent 编排（CONTEXT seam）。

### 1.2 脚本 API 与 IM 的关系（拍板建议）

**把脚本 API 做成内置插件类型 `script_api`，与 `feishu` / `slack` / … 并列，统一出现在「插件」设置里。** 不是两套入口。

理由：用户原话就是「开放接口做成插件，外部对接都走插件」；人设已经是跨 Key 共享，IM 也要绑同一套说话方式；工作角色/沙箱隔离规则可以共用。

| 类型 | 外部形态 | 启用后 |
|------|----------|--------|
| `script_api` | Bearer Key + `POST /api/v1/chat` | 行为与现网完全相同 |
| `feishu` / `slack` / `wecom` / `dingtalk` / … | 各厂商协议 | 外部聊天窗口能来回说话 |

**不破坏现网：** `lc_live_…`、v1 路径、Cookie 管 Key、按 Key 看会话、人设 CRUD，P0 只换壳不换语义。旧 `api_keys.json` 启动时投影成 `script_api` 实例（见 §7.4）。

### 1.3 产品对象（对应截图）

当前设置页已有三块，演进后仍在，只是「密钥」变成「插件实例」的一种卡片：

| 现网 | 演进后 |
|------|--------|
| 密钥列表（创建 / 查看会话 / 吊销） | 插件实例列表（添加 / 查看会话或日志 / 停用或吊销） |
| 折叠「调用方式」 | 按类型：`script_api` 仍是 curl；IM 是回调 URL / 长连接状态 / 验证步骤 |
| 折叠「说话方式」 | **保留**；人设可被 Key 与 IM 实例共用 |

---

## 2. 核心模型

五层。前四层与现网「人设 / Key / hidden role / conversation」同构，只是把 Key 泛化成「插件实例」。

```
插件类型 Plugin Type     内置代码，不是用户装的包
    └─ 插件实例 Instance  用户配的一份（名称、参数、启用、persona_id）
           ├─ 工作角色     hidden role：沙箱 + 同时一个 running turn
           ├─ 人设         可共享，活引用
           └─ 会话映射     外部 thread → conversation_id（origin=通道）
```

### 2.1 插件类型（Plugin Type）

内置实现，进程内注册。用户不能从网店安装。

每类声明：

| 字段 | 含义 |
|------|------|
| `type_id` | `script_api` / `feishu` / `slack` / `wecom` / `dingtalk` / （后期）`wechat_mp` |
| `display_name` | 设置里的名字 |
| `config_schema` | 非密钥参数（JSON Schema 或等价表） |
| `secret_schema` | 密钥字段；UI 脱敏；落盘不回传明文 |
| `ingress` | `http_bearer` / `http_webhook` / `outbound_only` / `long_poll` / `websocket` |
| `needs_public_url` | webhook 类为 true；长连接类为 false |
| `ack_deadline_ms` | webhook 必须在此时限内 200；`script_api` 可同步等 |
| `capabilities` | `sync_reply`（脚本）/ `async_reply`（IM）/ `edit_reply` / `thread` / `group` / `media` |

同一 `type_id` 可建**多份实例**（两把脚本 Key、两个飞书应用），参数各配各的。

### 2.2 插件实例（Plugin Instance）

用户配置的一份启用记录。建议字段：

| 字段 | 说明 |
|------|------|
| `id` | 短 id |
| `type_id` | 类型 |
| `name` | 卡片标题（现网密钥名） |
| `enabled` | 关则不收消息、不注册连接；`script_api` 关 ≈ 吊销 |
| `persona_id` | 说话方式；活引用 |
| `role_id` | 绑定的 hidden 工作角色 |
| `config` | 非密参数 |
| `secrets` | 见 §5.6；API 只出 mask |
| `status` | `disabled` / `idle` / `connected` / `error` |
| `status_detail` | 验签失败、长连接断开等 |
| `created_at` / `last_event_at` | 列表「尚未调用 / 上次」 |

`script_api` 实例另有：`key_prefix`、`key_hash`（与现 `api_keys.json` 同语义）；明文 token **只在创建时返回一次**。

### 2.3 工作角色（沿用现网，默认建议）

现网：**每把 API Key = 一个 hidden role**（独立沙箱、独立时间线、同角色同时一个 running turn）。原因见对外聊天 API 文 §1：人设、时间线、沙箱绑在同一个 `role_id` 上，多条接入线不能共用一个角色。

IM 默认建议与 Key **对齐**：

> **每个插件实例一个 hidden 工作角色。** 不要「一个飞书应用里每个群一把沙箱」，也不要「所有插件共用 `__api__`」。

| 策略 | 做法 | 利 | 弊 |
|------|------|----|----|
| **A. 每实例一个角色（默认）** | 启用实例时 `roles.create(visibility=hidden)`，如 `ext_<instance_id>` | 与 Key 同构；沙箱占用可预期；适合「主人自己从 IM 说话」 | 同一实例上多条外部会话**串行**（角色忙则排队）。多人群聊会堵 |
| B. 每个外部线程一个角色 | 新 `chat_id` 懒创建 hidden role | 多线程真并行 | 沙箱槽（`sandbox_max_api_roles` 默认 8）易打满；左栏仍排除但角色表膨胀 |
| C. 全部 IM 共用一个角色 | 一个 `__im__` | 实现少 | **否决**：并发互堵、日志搅在一起，与已确认 Key 模型冲突 |

**P0/P1 用 A。** 自托管是低并发、主人自己聊。群聊高峰是 P2 问题：先排队 + 「正在处理上一条」，再考虑 B 作实例级开关。

`script_api` 继续 `id=api_<key短id>`，不改现网角色。IM 建议前缀 `ext_`，实现时把 `is_api_role_id` 收成「hidden 外部角色」（§11）。

吊销/停用：不能再进线；**历史与工作角色留下**；设置里仍能看会话。删除实例（P1+）是否毁沙箱卷，沿用 Key 的 P1 口径。

### 2.4 人设（说话方式）

不另做一套。继续 `api_personas`（或现网等价表）：

- 多实例（Key 与 IM 混合）可选同一 `persona_id`
- Agent **读人设当前提示词**（活引用）。改完下一轮都生效
- 删人设：仍有任一实例在用则拒绝（现网只查 Key，实现时要查全部实例）
- 「改为独立人设」仍是对外聊天 API 的 P1，插件框架不挡

产品语言：「使用同一个角色」= 选用同一套人设。底下仍是多个工作角色。

### 2.5 会话映射

内部仍是 `conversations` 一行：`role_id` = 该实例的 hidden role；`origin` = 通道；外键指向实例（Key 上现有 `api_key_id`）。

| 外部 | 映射到 `conversation_id` | 多轮 |
|------|--------------------------|------|
| `script_api` | 调用方不传则新建；传入则必须属于这把 Key | 已拍板 |
| IM 私聊 | `type + instance_id + dm + 对方 id` 稳定哈希或查找表 | 同一人连续聊同一段 |
| IM 群（P2） | `type + instance_id + chat_id`；若平台有 thread，再加 `thread_id` | 群与私聊绝不共用一段 |
| Slack `thread_ts` | 建议：有 thread 则一段会话；频道顶栏每条新消息是否开新段 **待确认**（默认：仅 DM + 显式 thread 进同一段，频道裸消息 P2 再定） |

落盘建议：`.kb/channel_threads.json` 或 SQLite 表 `channel_threads(instance_id, external_key, conversation_id)`。禁止把外部 `chat_id` 直接当成内部 id。

**群聊 vs 私聊（产品）：**

- P1 只做私聊/单聊（飞书 `p2p`、Slack IM、企微单聊）。
- P2 群：默认 **被 @ 或被引用才开回合**，避免刷屏。
- 外部群 **不是** 左栏角色群（[product-role-rooms.md](product-role-rooms.md)）。不创建 lore-chat `group` 房间，不进左栏。只是该 hidden 角色下 `origin=feishu` 的一段会话。
- 外部群里的「别人」不要写成主人气泡去抽画像（§7.6）。

左栏：`GET /api/roles` 仍只返回 `visibility=sidebar`。`ensure_active` / tip / 最近活动只看网页主人线。现网用 `origin != api` 排除；实现插件后应排除**全部外部 origin**（§11）。

---

## 3. 生命周期

```
配置参数 → 校验 schema → 启用
    → 注册 ingress（webhook 路由 / 长连接 / 无，视类型）
    → 收消息 → 验签 / 解密 / 幂等
    → 归一化为内部用户文本（+ 可选附件路径）
    → 解析会话 → begin_persisted_turn（mode=api）
    → 回合结束 → outbound 写回外部
停用：断开连接、拒收、Key 视为吊销
删除：停用 + 保留历史；是否毁卷走 Key 的 P1 口径
```

### 3.1 配置与启用

1. 选类型，填该类型表单，选说话方式（默认：与实例同名新建人设，逻辑同创建密钥）。
2. 保存：校验必填、密钥非空、（webhook 类）已知 `public_base_url` 或明确允许先存后连。
3. `enabled=true` 才注册 ingress。长连接失败 → `status=error`，卡片上可见，**不**静默丢消息。
4. `script_api`：创建即「启用」；吊销 = `enabled=false` + `revoked`。

### 3.2 入站：脚本 vs IM

| | `script_api`（保持） | IM webhook | IM 长连接 |
|--|----------------------|------------|-----------|
| 鉴权 | Bearer `lc_live_…` | 厂商签名 / encrypt | 建连时 App Secret；事件仍可能带 id |
| 调用方等待 | 默认同步最多 120s；超时 **202** + `turn_id` | **必须先 ACK**（Slack/飞书约 3s，企微约 5s） | 无 HTTP 时限；仍不要阻塞读循环 |
| 回合 | `complete_chat` 可 `wait` | ACK 后后台 `begin_persisted_turn`，**禁止**在 webhook 协程里等 120s | 同左：入站线程只投递 |
| 回复 | JSON body | 厂商发消息 API | 同左 |

IM **没有**「同步等完整回复」这条产品路径。即使用户在飞书里感觉是一问一答，内部也是异步回合 + 事后 `reply`。

### 3.3 归一化

插件产出统一内部事件，再交给共用 `ChannelTurnService`（名称可改，职责不变）：

```
InboundEvent
  instance_id
  external_user_id / display_name   # 只作会话键与日志，不写进主人画像除非 §7.6 允许
  external_chat_id
  external_thread_id | null
  event_id                          # 幂等
  text
  attachments[]                     # P2；P1 无或降级为「[收到一张图，暂不能读]」
  is_group
  mentioned_bot
```

文本空且无附件：ACK 后丢弃，不空跑回合。

### 3.4 失败、重试、签名、幂等、超时

| 问题 | 建议 |
|------|------|
| 签名失败 / 解密失败 | 401/403，打 `status_detail`，不创建会话 |
| 平台重试同一 `event_id` | 短 TTL 去重表（建议 24h）。已处理：再 ACK，不再开回合。进行中：ACK，不并跑第二条 |
| 同实例角色已有 running turn | 与 Key 相同：角色锁。IM **不要**对平台返回 409（对方会重试风暴）。ACK 后把事件丢进**实例入站队列**（可复用 `role_inbound_queue` 思路，勿在 HTTP 层忙等） |
| 回合失败 / 模型错误 | 向该外部会话发一句失败说明（可关）；内部时间线仍能看 |
| 回合很长 | 内部跑完为止（与网页断开不取消执行同一套 hub）。可选：超过 N 秒先发「还在处理」（**待确认**，P1 默认可关） |
| 出站 API 失败 | 有限次重试（仅 transient）；失败记实例日志；不回滚已落库的助手消息 |
| webhook 超时未 ACK | 平台重试，靠 `event_id` 幂等 |
| 长连接断开 | 自动重连 + `status=error`；积压由厂商侧决定，我们不自造第二套 outbox 给外部协议 |

`script_api` 同 Key 并发仍 **409** `turn_in_progress`（已确认）。不要改成静默排队，除非对外聊天 API 文先改。

### 3.5 `needs_input` / 高风险沙箱

现网：`origin=api` **跳过网页沙箱确认**；`ask_user` 在设置页没有完整闭环（对外聊天 API P1）。

IM 更没有网页。建议：

| 情况 | P1 | P2 |
|------|----|----|
| `ask_user` | 把问题**纯文本**打到 IM；用户下一条当回答（弱）；或告知「请到 Lore Chat 网页确认」 | 结构化选项（飞书卡片 / Slack Block Kit） |
| 高风险 `sandbox_run` | 与 API 一样跳过网页确认（自用假设） | 实例开关「IM 禁用沙箱」或白名单命令 |

**待确认：** P1 是否允许 IM 触发沙箱。建议允许（否则「外部聊天」几乎不能干活），但群聊默认关沙箱直到有发送者白名单。

---

## 4. 配置参数（示例 schema，非最终实现）

字段名按常见官方文档；实现时以厂商当前 API 为准。

### 4.1 `script_api`

无用户填的厂商密钥。创建流程与现网密钥相同。

| 字段 | 来源 |
|------|------|
| `name` | 用户 |
| `persona_id` 或新建人设 | 用户 |
| `token` | 系统签发，`lc_live_` + 哈希落盘 |
| 调用 | `POST /api/v1/chat`，Bearer |

迁移：见 §7.4。v1 契约不变。

### 4.2 微信（先分清再做）

| 形态 | 自托管现实性 | 本草案 |
|------|----------------|--------|
| **企业微信应用**（客户消息 / 智能机器人） | 有企业主体即可；回调要公网 HTTPS，或看当前官方是否提供长连接 | **微信线的首选**（类型 `wecom`） |
| **公众号 / 服务号** | 要备案域名、认证号；主动回复窗口短 | P2+，类型 `wechat_mp`；不与企微混成一个 schema |
| **个人微信 / 协议号 / WeChaty 网页协议** | 非官方，封号 | **明确不做** |

`wecom` 示例：

| 字段 | 密 | 说明 |
|------|----|------|
| `corp_id` | 否 | 企业 ID |
| `agent_id` | 否 | 应用 |
| `corp_secret` | 是 | |
| `token` / `encoding_aes_key` | 是 | 回调验签与解密 |
| `callback_url` | 只读展示 | `{public_base_url}/api/channels/{id}/wecom` |

无 `public_base_url` 时：保存实例但 `status=error`，卡片提示去「分享 / 设置」里配公网根（与分享链同一配置）。

### 4.3 钉钉 `dingtalk`

| 字段 | 密 | 说明 |
|------|----|------|
| `app_key` / `app_secret` | 否 / 是 | 企业内部应用 |
| `robot_code` | 否 | 机器人 |
| `ingress` | 否 | 建议默认 **Stream 长连接**（少依赖公网）；可选 HTTP 回调 |
| `token` / `aes_key` | 是 | 仅 HTTP 回调 |

### 4.4 飞书 `feishu`

| 字段 | 密 | 说明 |
|------|----|------|
| `app_id` / `app_secret` | 否 / 是 | 企业自建应用 |
| `verification_token` | 是 | 事件校验 |
| `encrypt_key` | 是 | 加密事件 |
| `ingress` | 否 | **默认长连接**；可选 webhook |
| `webhook_url` | 只读 | 仅 webhook 模式展示 |

飞书开放平台自建应用支持事件**长连接**，家里 NAS / 无备案域名也能验 P1。这是「第一个 IM」的主因（§8）。

### 4.5 Slack `slack`

| 字段 | 密 | 说明 |
|------|----|------|
| `bot_token` | 是 | `xoxb-…`，出站 `chat.postMessage` |
| `signing_secret` | 是 | Events API 验签 |
| `app_token` | 是 | Socket Mode `xapp-…`；webhook 模式可空 |
| `ingress` | 否 | **默认 Socket Mode**；可选 Events Request URL |
| `request_url` | 只读 | webhook 模式：`{public_base_url}/api/channels/{id}/slack` |

Slack 与飞书同构（都能免公网）。P1 若主人已在用 Slack，可改先做 Slack，框架仍是同一套（§12）。

### 4.6 公网 URL

沿用设置里的 `public_base_url`（分享页已在用）。插件卡片展示拼好的回调 URL，**不要**让用户手填 lore-chat 内部路径。

未配置公网：

- 长连接类型：仍可启用。
- webhook 类型：允许保存草稿，启用时失败并写明原因。

### 4.7 密钥存储

对齐现网两套习惯，不要发明第三套「看起来更安全但没人接」的方案：

| 现网 | 做法 |
|------|------|
| API Key | SHA-256 哈希落盘 `.kb/api_keys.json`；明文只创建时给一次（**不可逆**，适合 Bearer） |
| 模型 / 搜索 Key | `.kb/settings.json` 明文（目录权限）；`public_dict` 脱敏；PATCH 空/掩码则保留旧值 |

IM 的 App Secret / Bot Token **运行时还要拿去调厂商**，不能只存哈希。

**拍板建议：**

- `script_api` token：继续哈希，行为不变。
- IM 密钥：与 settings 相同——落在实例存储里、API 回包脱敏、空/掩码不覆盖。文件权限跟 `.kb/settings.json`。
- **P0 不做**独立信封加密（Fernet 等），除非主人要求；要做就 settings 与插件一起做，不要只加密插件。

---

## 5. UI（设置页演进）

从当前「开放接口」页演进，不新开顶层 IA。

### 5.1 页签

**拍板建议：** 页签文案改为 **「插件」**；`id` 仍可用 `openapi` 以免打掉 localStorage。副标题：「脚本密钥和微信、飞书、Slack 等外部聊天」。

备选（待确认）：「开放接口 / 插件」。

### 5.2 首页

一句说明 + 主按钮 **添加插件**（有 `script_api` 实例时，也可保留「创建密钥」作为该类型的快捷方式，避免老用户找不到）。

列表：**所有插件实例**（含密钥投影），不是只显示 Key。

每张卡：

- 类型图标 + 名称
- 状态：启用开关、`connected` / `error`（IM）
- 说话方式徽章（同名人设）
- `script_api`：`lc_live_Qm4a…` + 上次调用
- IM：上次消息 / 连接状态
- **查看会话**（该实例 hidden role 的只读时间线，现网「查看会话」）
- IM：**日志**（验签失败、出站重试；可与会话同一子页）
- `script_api`：**吊销**；IM：**删除/停用**

空态：还没有插件；主按钮添加。

### 5.3 添加插件

1. 选类型（脚本密钥 / 飞书 / Slack / …；未实现的类型灰显「即将支持」）。
2. 该类型表单 + 选说话方式（控件复用创建密钥：默认同名 / 已有人设 / 新建 / 从左栏复制提示词）。
3. 保存并启用。`script_api` 仍只显示一次明文 Key。
4. IM：成功则展示下一步（飞书后台开长连接权限、把回调 URL 贴回厂商等）。

### 5.4 折叠区

- **说话方式**：现网折叠保留；「N 把密钥在用」改为「N 个插件在用」。
- **调用方式**：仅当存在 `script_api` 实例时展示 curl。有 IM 实例时，另设「接入说明」或把说明放进该实例编辑页，避免首页堆三种厂商文档。

### 5.5 不要做的界面

- 不要把人设、密钥、飞书表单摊成三张并列主表。
- 不要按人设合并时间线（已确认）。
- 不要在左栏出现这些工作角色。
- 不要做插件市场、评分、第三方上传。

---

## 6. 内部 seam 建议

### 6.1 模块路径

建议：`backend/app/engine/plugins/`（产品叫「插件」；代码避免空泛的 `channels` 与角色群「房间」撞名）。

| 单元 | 职责 |
|------|------|
| `PluginRegistry` | 内置 `PluginType` 注册表；进程启动时挂上 |
| `PluginType` / `ChannelAdapter` | `validate_config`、`start/stop`、`parse_inbound`、`send_outbound`、`challenge`（Slack url_verification / 企微 echostr） |
| `PluginInstanceStore` | 实例 CRUD；secret 脱敏；`script_api` 与 Key 投影 |
| `ChannelTurnService` | 验实例启用 → 映射会话 → `begin_persisted_turn`；**不**解析 SSE |
| `plugin_runtime` | 长连接 task 的启停，跟 `Container` / `apply_settings` 生命周期 |

HTTP：

- Cookie：`/api/open-api/*` 保留；其上加 `/api/plugins` 做实例 CRUD（或把 Key API 收成 plugins 的一种资源，对外仍提供旧路径一段时间）。
- 公开：`/api/channels/{instance_id}/{type}` 入站。**无 Cookie、无 Bearer 主人会话**。只信厂商签名。Bearer Key **仍然**不能打设置/KB（已确认）。

出站只走该类型 adapter 的 `send_outbound`，禁止在路由里直接 `httpx` 调 Slack。

### 6.2 复用现网回合

`OpenApiService.complete_chat` 已是正确骨架：验身份 → 取 `role_id` → 断言/创建会话 → `_role_busy` → `begin_persisted_turn(..., mode=MODE_API)` → 可选等待。

建议拆出可同步可异步的一层（P0 哪怕只给脚本用）：

| 调用方 | wait |
|--------|------|
| `POST /api/v1/chat` | 是（现网 timeout / 202） |
| IM adapter | 否；subscribe/finalize 后 `send_outbound` |

观测仍走 `TurnExecutionHub`：断开 webhook 不等于取消执行（与网页 SSE 同一 ADR）。

禁止：为飞书再写 `stream_ephemeral`；禁止 IM 会话 `origin=web`。

### 6.3 `origin` 扩展

现网会话 `origin=api`。建议：

| origin | 谁 |
|--------|-----|
| `web` | 左栏 |
| `api` | `script_api`（**保持字符串**，少迁数据） |
| `feishu` / `slack` / `wecom` / `dingtalk` / `wechat_mp` | 对应 IM |

左栏 tip、记忆 dirty、最近活动：排除 `origin in EXTERNAL_ORIGINS`，不要只判 `!= api`。

### 6.4 `mode=api` 是否用于所有外部插件

现网 `select_tools(mode=api)`：只读 KB、可读 Skill、可沙箱执行；无写库、无 `publish_from_sandbox`、无改角色/例行/记忆写入、无群聊派工工具。不跑记忆抽取。`recall_memory` 可只读。

**拍板建议：所有通道插件默认同一 `mode=api`。**

理由：外部是半信任边界（群里可能是同事）；与「脚本乱写知识库」是同一类风险；实现零分叉。主人要在 IM 里归档，P2 再做实例级「允许写库」（默认关）。

沙箱名额：hidden 角色继续走 `sandbox_max_api_roles`，**不占**左栏 `sandbox_max_roles`。IM 角色与 Key 角色**合计**受该上限；满则该实例本轮失败并通知外部，**绝不借用**左栏或其它实例的盘。

### 6.5 并发与队列

现网：同 Key 第二枪 HTTP 409。IM 改为实例内队列（§3.4）。不要把 IM 事件接到角色群的 `RoomDelivery` 上——那是内部角色互通，外部用户不是 Actor。

---

## 7. 存储（建议）

P0 可继续 JSON 文件，与 Key 一致。

| 现网 | 插件后 |
|------|--------|
| `.kb/api_keys.json` | 启动投影进实例表；P0 可双写以免回滚丢 Key |
| `roles` hidden + `persona_id` | IM 同样 `ext_…` / `api_…` |
| `conversations.origin` + `api_key_id` | 增 `plugin_instance_id`（Key 行可等于实例 id） |
| 无 | `channel_threads` 外部键 → `conversation_id` |
| 无 | 去重 `event_id`（可用 Redis 级内存 + 文件，单进程先 SQLite/JSON TTL） |

### 7.4 `script_api` 迁移（P0 必须无感）

1. 读旧 `api_keys.json` → 每把 Key 一张 `type=script_api` 实例（`id` 可等于 `key_id`，`role_id`/`persona_id`/`hash` 原样）。
2. `POST /api/v1/chat` 仍只认 Bearer，不要求调用方知道插件 id。
3. Cookie：旧 `/api/open-api/keys` 可留作别名。
4. 不迁会话行：`origin=api` 已指向 `api_key_id`。

验收：迁移前后同一把 Key 的 curl 与「查看会话」一致。

---

## 8. 分期

### P0 — 框架 + 密钥变成插件 + UI 骨架

- `PluginRegistry` + `ChannelAdapter` 协议 + `script_api` adapter（内部调现有 `OpenApiService` / 等价拆分）。
- 实例列表 API；旧 Key 投影。
- 设置页：页签名、实例卡（先只有脚本类型）、添加向导骨架、说话方式折叠保留、创建密钥路径仍可用。
- **行为不变：** v1 chat、409、120s/202、人设活引用、左栏不出现 hidden、mode=api。
- 无 IM。

### P1 — 第一个 IM

**建议默认：飞书 + 长连接。** 若主人日常在 Slack，则改为 Slack Socket Mode（工作量同级，见 §12）。

| 候选 | 公网 | 为何排 | P1？ |
|------|------|--------|------|
| **飞书长连接** | 不需要 | 国内知识工作者常用；官方长连接；和 NAS 自托管匹配；事件模型干净 | **默认** |
| Slack Socket Mode | 不需要 | 文档与验签极熟；和飞书同构 | 主人已用 Slack 则换它 |
| 企微回调 | 通常要 | 要 HTTPS 与企业主体；适合已有 `public_base_url` 的办公室 | P2 |
| 钉钉 Stream | 不需要 | 与飞书类似，但第二家再抄 adapter | P2 |
| 公众号 | 要 | 认证与回复窗口差 | 更后 |
| 个微 | — | 非官方 | 不做 |

P1 范围：私聊文本；实例启用/停用；异步回复；幂等；角色忙则排队；查看会话；失败提示。不做群、富媒体、卡片交互。

### P2

- 其余 IM；企微/公众号 webhook。
- 群：@ 才回；发送者白名单。
- 图/文件：先落 KB 媒体路径再进模型（走现有 `attachments`，勿把厂商 URL 当长期身份）。
- `needs_input` 用 IM 卡片；实例级写库开关。
- 删除实例与毁卷；「改为独立人设」。
- 频道顶栏 vs thread 策略定案。

---

## 9. 验收

### P0

1. 旧 `lc_live_` 调用 `POST /api/v1/chat` 与迁移前一致（含 409、202、会话隔离）。
2. 设置里能看见原密钥，人设徽章、查看会话、吊销仍在。
3. 左栏仍无 API/插件工作角色。
4. 两把 Key 同一人设：两套会话、两把沙箱；停一方不影响另一方。
5. 不引入飞书/Slack 代码路径也能通过现网 open-api 测试。

### P1（在选定的第一家 IM 上）

6. 配好官方字段并启用后，私聊发文本能收到 lore-chat 回复（人设为该实例所选）。
7. 改人设，下一轮 IM 与脚本 Key（若共用）都换新提示词。
8. 关实例或填错签名：外部消息进不来；已有时间线仍能在设置里看。
9. 同一人连发两条：第二条不丢（排队），不双开同一 `role_id` 的 turn，不借用其它实例沙箱。
10. 左栏 tip/最近活动不出现这条飞书会话。
11. 写库 / 回写 / 改 Skill / `send_message` 工具不存在（mode=api）。
12. 无 `public_base_url` 时飞书长连接仍能工作。

---

## 10. 明确不做

- 第三方插件商店、侧载 zip、给第三方的 OAuth 门户、多租户计量。
- 请求或 IM 事件里指定左栏 `role_id` 去借沙箱/人设。
- 左栏出现通道工作角色；按人设合并一条大时间线。
- 多实例共用一个 `role_id`；同一实例再开多把沙箱（除非将来显式打开策略 B）。
- 个微 / 非官方协议。
- 把外部群做成 lore-chat 角色群；IM 用户变成内部 Actor。
- 为 IM 另写一套 Agent、ephemeral 不落库对话（脚本已禁止；IM 更要可审计）。
- 在 webhook 路由里解析 Agent SSE 或自建工具循环。
- P0 信封加密只覆盖插件、不覆盖 settings。
- OpenAI 兼容网关（仍是对外聊天 API 的 P2，与通道插件正交）。

---

## 11. 相对已确认文档的变更提议（仅这几条，其余不动）

确认本文后，**实现阶段**才改代码；在此之前 [product-external-chat-api.md](product-external-chat-api.md) 仍全权有效。提议：

| # | 现口径 | 提议 | 为何 |
|---|--------|------|------|
| 1 | 设置入口名叫「开放接口」 | 页签改为「插件」，脚本是其中一类 | 用户原话 |
| 2 | 删人设只拦「仍有密钥」 | 改为「仍有插件实例」 | IM 也绑人设 |
| 3 | 左栏/记忆排除只认 `origin=api` | 排除集合含所有外部 origin | 否则飞书会话会进 tip/抽画像 |
| 4 | `is_api_role_id` 前缀 `api_` | hidden 外部角色含 `ext_` | IM 角色 |
| 5 | 同 Key HTTP 409 | **脚本保持 409**；IM 改为 ACK+排队 | 平台会重试 |
| 6 | 记忆：API 不 dirty | IM 私聊是否抽主人画像 **待确认**（P1 建议仍不抽，与 API 一致，免群聊误伤） | 见 §12 |

不提议改：每 Key 一角色、人设可共享、mode=api 工具集、同步 JSON+120s/202、不做多租户。

---

## 12. 待主人确认

实现前请拍这几项（其它按本文默认建议可开工）：

1. 页签名：「插件」还是「开放接口 / 插件」？
2. P1 第一家 IM：飞书长连接，还是 Slack Socket Mode？
3. 工作角色：确认策略 A（每实例一角色 + IM 排队），还是 P1 就要按外部线程开角色？
4. IM 私聊要不要跑记忆抽取？（建议 P1 否）
5. P1 是否允许 IM 用沙箱（mode=api 已含沙箱工具）？群聊是否默认关沙箱？
6. 回合超过 ~15s 要不要先发「还在处理」？
7. Slack 频道里无 thread 的裸消息：忽略 / 每条新会话 / 整频道一段？
8. webhook 类在未配 `public_base_url` 时：禁止启用，还是允许保存为停用？

---

## 13. 下一阶段实现切片（确认后）

最小可合并 PR 顺序：

1. 协议 + Registry + 实例存储 + Key 投影；测试只覆盖投影与 list。
2. 设置 UI 骨架（仍只创建密钥）。
3. 把 `complete_chat` 的「创建会话 + begin_persisted_turn」抽成通道共用函数；v1 走它；测 open-api 全绿。
4. 飞书（或 Slack）adapter：长连接、幂等、outbound、设置表单。

改提示词不在本范围。Agent 行为差异只通过已有 `mode=api` 与人设，不在 SYSTEM 里写「你在飞书里」。
