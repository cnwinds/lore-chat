# 聊天通道插件

> 状态：**草案 / 待确认**（2026-09-14）。尚未实现。实现前须主人确认 §12。
>
> 用户原话：开放接口想开发成类似插件的东西。包括后续的微信、钉钉、飞书、Slack 等外部对接都走插件方式。每个插件可以配置不同的参数。配置完成启用后，就可以和外部聊天。
>
> 主人补充（命名）：统一叫 **「聊天通道插件」（Channel Plugin）**。不要泛泛叫「插件」，也不要把脚本和 IM 当成完全无关的两类。平台差异只是适配层；共有能力见 §2。
>
> 配套：[product-external-chat-api.md](product-external-chat-api.md)（**已确认**的脚本通道口径，本文不改写）、[ADR 草案 2026-09-14 channel-plugins](adr/2026-09-14-channel-plugins.md)、[CONTEXT.md](../CONTEXT.md)（HTTP **不**重编排 Agent）。

文件名保持 `product-channel-plugins.md`。文内标题与设置文案用「聊天通道插件 / 聊天通道」。

## 与已确认文档的关系

| 文档 | 关系 |
|------|------|
| [product-external-chat-api.md](product-external-chat-api.md) | **并列、被包含。** 脚本 Key / `POST /api/v1/chat` / 人设可共享 / 每 Key 一个隐藏工作角色，仍以该文为权威。本文是其**超集**：把那一套收成第一种聊天通道（`script_api` / HTTP），并规定微信/钉钉/飞书/Slack 走**同一公共模型**。 |
| 本文 | 聊天通道插件的产品 + 架构草案。确认后实现；**不**替代上一文。 |
| 已确认口径 | 除非 §11 显式提议变更，否则实现须继续遵守对外聊天 API 文。 |

现网对照（以代码为准）：`OpenApiService.complete_chat`（验 Key → 取 hidden `role_id` → `begin_persisted_turn`，`mode=api`，`origin=api`）；设置页「开放接口」= 密钥列表 + 折叠「调用方式」+ 「说话方式」。演进后，这一页变成**聊天通道**列表，现有密钥是列表里的第一种卡片。

## 0. 一句话

**聊天通道插件**把外部聊天（脚本 HTTP、微信、钉钉、飞书、Slack…）接到 lore-chat 的同一条内部回合上。配好参数、启用后，外部消息进来，走隐藏工作角色 + 人设 + `ChatSessionRunner`，回复写回外部。各类型只换适配层，不另造 Agent，也不另开一套设置。

现有「开放接口 / API Key」= **第一种聊天通道**（script / HTTP）。不是并列的第二套产品。

---

## 1. 定位与边界

### 1.1 命名（已拍板建议）

| 说法 | 用不用 |
|------|--------|
| **聊天通道插件** / **聊天通道** | 产品名、页签、文档标题。英文 Channel Plugin |
| 通道类型 / 通道实例 | 模型层：`feishu` 是类型，用户配的那一份是实例 |
| 「插件」单字 | **不要**当产品名。易与 Skill、浏览器插件、应用商店混在一起 |
| 「脚本」vs「IM」当两个产品 | **不要。** 只是两种 `type_id`；列表同级、共有能力同一套 |

### 1.2 两层各干什么

| 层 | 负责 | 不负责 |
|----|------|--------|
| **聊天通道（适配层）** | 厂商鉴权与签名、webhook/长连接/Bearer、类型特有 config、把外部事件收成内部用户消息、把助手回复打回外部 | 选模、工具循环、人设注入、沙箱、时间线投影 |
| **现有聊天引擎（共有）** | `begin_persisted_turn` → `TurnExecutionHub` → Agent；hidden role、persona 活引用、`mode=api` 工具集 | 解析 Slack/飞书 payload |

HTTP 路由只验签、拆 DTO、交给通道再交给 runner。**禁止**在 webhook handler 里再写一套 Agent 编排（CONTEXT seam）。

### 1.3 开放接口是第一种聊天通道

**`script_api`（脚本 / HTTP）与 `feishu` / `slack` / `wecom` / `dingtalk` 同级。** 设置里一张列表，不是「开放接口」一页再加「IM 插件」另一页。

| 类型 `type_id` | 外部形态 | 启用后 |
|----------------|----------|--------|
| `script_api` | Bearer Key + `POST /api/v1/chat` | 行为与现网完全相同 |
| `feishu` / `slack` / `wecom` / `dingtalk` / … | 各厂商协议 | 外部聊天窗口能来回说话 |

共有：选说话方式、查看会话、启停与状态、会话映射、（建议）日志/用量。特有：Bearer vs 签名 vs 长连接、厂商字段、同步 JSON vs 异步 reply。

**不破坏现网：** `lc_live_…`、v1 路径、Cookie 管 Key、按 Key 看会话、人设 CRUD，P0 只换壳不换语义。旧 `api_keys.json` 启动时投影成 `script_api` 通道实例（见 §7.4）。

### 1.4 产品对象（对应截图）

当前设置页三块，演进后仍在：密钥卡变成通道实例卡的一种。

| 现网 | 演进后 |
|------|--------|
| 页签「开放接口」 | **聊天通道**（待确认文案见 §12） |
| 密钥列表（创建 / 查看会话 / 吊销） | **通道实例列表**（脚本 / 飞书 / Slack 同级；添加 / 查看会话 / 启停） |
| 折叠「调用方式」 | 类型特有接入说明：`script_api` 仍是 curl；IM 是回调 URL / 长连接 / 验证步骤 |
| 折叠「说话方式」 | **共有**；人设可被任意通道实例共用 |

---

## 2. 核心模型

一层类型、一层实例。实例上挂共有字段；类型只贡献适配器与特有 schema。

```
通道类型 Channel Type     内置适配器（script_api / feishu / …），不是网店包
    └─ 通道实例 Instance  用户配的一份（共有字段 + 该类型 config/secrets）
           ├─ 人设         可共享，活引用（说话方式）
           ├─ 工作角色     hidden role：沙箱 + 同时一个 running turn
           └─ 会话映射     外部 thread → conversation_id（origin=该通道）
```

### 2.1 公共模型 vs 类型特有 schema

所有聊天通道插件**共用左列**；右列才随类型变化。实现时：公共字段进实例表；特有字段进 `config` / `secrets`，用该类型的 schema 校验。

| | **公共模型（所有通道）** | **类型特有（适配层）** |
|--|--------------------------|------------------------|
| 身份 | `id`、`name`、`type_id` | 展示名、图标 |
| 说话方式 | `persona_id`（见 §2.5） | 无。禁止类型私自再存一份提示词 |
| 工作角色 | `role_id`（hidden，默认每实例一个） | 角色 id 前缀可不同（`api_` / `ext_`），规则相同 |
| 启停 | `enabled` | 启用时注册何种 ingress |
| 状态 | `disabled` / `enabled` / `error`（校验失败、断线）；`status_detail` | 错误文案可含厂商细节 |
| 会话 | `channel_threads`：外部线程键 → `conversation_id` | 怎么拼外部键（Key 的 `conversation_id` / 飞书 `open_id` / Slack `thread_ts`） |
| 看记录 | 按**本实例**打开只读时间线 / 会话列表（现网「查看会话」） | 无。禁止按类型合并、按人设合并 |
| 日志 / 用量 | **建议共有**：入站失败、出站重试、回合耗时；用量页可按通道实例过滤 | 厂商原始 payload 只进该实例日志，不上公共时间线 |
| 回合 | `begin_persisted_turn` + `mode=api` | `script_api` 可同步 wait；IM 先 ACK 再异步 reply |
| 配置 | — | 见 §4 各类型表：`token` 哈希、`app_id`、Signing Secret、长连接开关… |
| 接入 | — | `http_bearer` / `http_webhook` / `websocket` / …；是否要 `public_base_url` |

同一 `type_id` 可建**多份实例**（两把脚本 Key、两个飞书应用），公共字段各填各的，特有参数也各配各的。

### 2.2 共有能力（产品必须有）

每一张通道卡片，无论 script 还是飞书，都要能做这些事：

| 能力 | 行为 |
|------|------|
| **选择说话方式** | 绑定人设 `persona_id`。与左栏「角色」的关系见 §2.5（建议绑人设，不绑左栏 `role_id`） |
| **查看聊天记录** | 进入该实例的只读时间线 / 会话列表，对齐现网「查看会话」。只看这一实例，不按人设合并 |
| **配置参数** | 先填公共项（名称、人设），再填该类型表单 |
| **启停** | 关：不收消息、断开长连接；`script_api` 关 ≈ 吊销 Key。开：校验通过才进 `enabled` |
| **状态** | 未启用 / 已启用 / 校验失败（含签名错、缺公网、长连接断开）。失败原因写在卡片上 |
| **会话映射** | 外部线程标识 ↔ 内部 `conversation_id`，多轮连续 |
| **日志 / 用量（建议）** | 实例内日志入口；用量页可按通道实例看调用。P0 脚本可先沿用「上次调用」；P1 IM 补失败日志 |

类型特有能力（同步 JSON、Socket Mode、群 @）挂在适配器上，**不要**复制一套「说话方式 / 查看会话」。

### 2.3 通道类型（Channel Type）

内置实现，进程内注册。用户不能从网店安装。

每类声明：

| 字段 | 含义 |
|------|------|
| `type_id` | `script_api` / `feishu` / `slack` / `wecom` / `dingtalk` / （后期）`wechat_mp` |
| `display_name` | 列表里的类型名（脚本 / HTTP、飞书、…） |
| `config_schema` | 非密钥参数 |
| `secret_schema` | 密钥字段；UI 脱敏；落盘不回传明文 |
| `ingress` | `http_bearer` / `http_webhook` / `websocket` / … |
| `needs_public_url` | webhook 类为 true；长连接与 Bearer 为 false |
| `ack_deadline_ms` | webhook 必须在此时限内 200；`script_api` 可同步等 |
| `capabilities` | `sync_reply` / `async_reply` / `edit_reply` / `thread` / `group` / `media` |

### 2.4 通道实例（Channel Instance）

用户配置的一份启用记录。公共字段：

| 字段 | 说明 |
|------|------|
| `id` | 短 id |
| `type_id` | 通道类型 |
| `name` | 卡片标题（现网密钥名） |
| `enabled` | 关则不收消息、不注册连接 |
| `persona_id` | 说话方式；活引用 |
| `role_id` | 绑定的 hidden 工作角色 |
| `config` / `secrets` | **仅类型特有**；API 对 secret 只出 mask |
| `status` | `disabled` / `enabled` / `error` |
| `status_detail` | 校验失败原因 |
| `created_at` / `last_event_at` | 列表「尚未调用 / 上次」 |

`script_api` 的特有部分：`key_prefix`、`key_hash`（与现 `api_keys.json` 同语义）；明文 token **只在创建时返回一次**。这些进 `secrets`/`config`，不要另做「密钥对象」与实例并列。

### 2.5 说话方式 vs 左栏「角色」（建议 + 待确认）

现网拆过两层（对外聊天 API 文 §1），聊天通道沿用：

| 层 | 是什么 | 通道能不能共享 | 进不进左栏 |
|----|--------|----------------|------------|
| **人设 persona** | 名称、头像、提示词（「说话方式」） | **能**。多条通道可选用同一套 | 否 |
| **工作角色** | `roles` 一行：`role_id`、沙箱、会话 | **不能。** 每通道实例恰好一个 hidden role | 否 |
| **左栏角色** | 人设 + 工作角色 + 网页时间线，给主人在三栏里聊 | 见下，**默认不绑 `role_id`** | 是 |

产品上「选择角色 / 说话方式」指的是选 **人设**，不是把左栏那个人拖来共用沙箱。

**拍板建议（P0/P1）：**

1. 通道实例只存 `persona_id`。Agent 读人设**当前**提示词（活引用）。改人设，所有选用它的通道下一轮生效。
2. 创建时的选项与现网创建密钥对齐：默认与实例同名新建人设 / 选用已有人设 / 新建一套 / **从左栏角色复制**（只拷名称、头像、提示词）。
3. 复制出来的是**独立人设**。改左栏「通用」的提示词，**不影响**任何通道（对外聊天 API 验收第 5 条）。通道的 hidden role **不**等于左栏那个 `role_id`。
4. 禁止请求或 IM 事件里带一个左栏 `role_id` 去借沙箱（已确认）。

**待确认（若主人希望「飞书上就是通用助手」）：**

| 方案 | 含义 | 建议 |
|------|------|------|
| A. 只绑人设（默认） | 与现网 Key 相同；从左栏复制也是副本 | **P0 用这个** |
| B. 跟随左栏角色的人设 | 通道 `persona` 活引用某左栏角色的 `system_prompt`，工作角色仍是 hidden | 和已确认「改左栏不影响 Key」冲突。若要做，须在对外聊天 API 文里改口径，且 UI 写清「跟随 / 已复制」 |
| C. 直接绑左栏 `role_id` | 外部消息进左栏时间线、共用那把沙箱 | **否决**。左栏会被脚本/群消息打乱，并发互堵 |

删人设：仍有任一通道实例在用则拒绝（现网只查 Key，实现时查全部实例）。「改为独立人设」仍是对外聊天 API 的 P1。

### 2.6 工作角色（每实例一个 hidden role）

现网：**每把 API Key = 一个 hidden role**。聊天通道对齐为：**每个通道实例一个 hidden 工作角色。** 不要「一个飞书应用里每个群一把沙箱」，也不要「所有通道共用 `__api__`」。

| 策略 | 做法 | 利 | 弊 |
|------|------|----|----|
| **A. 每实例一个角色（默认）** | 启用时 `roles.create(visibility=hidden)`，如 `ext_<instance_id>` | 与 Key 同构；沙箱占用可预期 | 同一实例上多条外部会话**串行**（忙则排队） |
| B. 每个外部线程一个角色 | 新 `chat_id` 懒创建 hidden role | 多线程真并行 | `sandbox_max_api_roles`（默认 8）易满 |
| C. 全部通道共用一个角色 | 一个 `__im__` | 实现少 | **否决**：与已确认 Key 模型冲突 |

**P0/P1 用 A。** `script_api` 继续 `id=api_<key短id>`。其它类型建议前缀 `ext_`，实现时把 `is_api_role_id` 收成「hidden 通道工作角色」（§11）。

停用：不能再进线；**历史与工作角色留下**；设置里仍能查看会话。删除实例（P1+）是否毁沙箱卷，沿用 Key 的 P1 口径。

### 2.7 会话映射

内部仍是 `conversations` 一行：`role_id` = 该实例的 hidden role；`origin` = 通道类型；外键指向实例（Key 上现有 `api_key_id`）。

| 外部 | 映射到 `conversation_id` | 多轮 |
|------|--------------------------|------|
| `script_api` | 调用方不传则新建；传入则必须属于这把 Key | 已拍板 |
| IM 私聊 | `type + instance_id + dm + 对方 id` 稳定哈希或查找表 | 同一人连续聊同一段 |
| IM 群（P2） | `type + instance_id + chat_id`；有 thread 再加 `thread_id` | 群与私聊绝不共用一段 |
| Slack `thread_ts` | 建议：有 thread 则一段会话；频道顶栏裸消息 **待确认**（默认 P1 只做 DM + 显式 thread） | |

落盘：`.kb/channel_threads.json` 或表 `channel_threads(instance_id, external_key, conversation_id)`。禁止把外部 `chat_id` 直接当内部 id。这是**公共模型**，各类型只负责怎么从 payload 抽出 `external_key`。

**群聊 vs 私聊：**

- P1 只做私聊/单聊。
- P2 群：默认 **被 @ 或被引用才开回合**。
- 外部群 **不是** 左栏角色群（[product-role-rooms.md](product-role-rooms.md)）。不创建 lore-chat `group` 房间，不进左栏。
- 外部群里的「别人」不要写成主人气泡去抽画像（记忆策略见 §12）。

左栏：`GET /api/roles` 仍只返回 `visibility=sidebar`。`ensure_active` / tip / 最近活动只看网页主人线。现网用 `origin != api` 排除；实现后应排除**全部通道 origin**（§11）。

---

## 3. 生命周期

共有流程。类型只替换「注册 ingress / 验签 / 写回」这几步。

```
配置公共项 + 类型参数 → 校验 → 启用
    → 注册 ingress（Bearer 无需常驻；webhook / 长连接视类型）
    → 收消息 → 验签 / 解密 / 幂等
    → 归一化为 InboundEvent
    → 会话映射 → begin_persisted_turn（mode=api）
    → 回合结束 → 该类型 outbound
停用：断开、拒收（script_api ≈ 吊销）
删除：停用 + 保留历史；毁卷走 Key 的 P1 口径
```

### 3.1 配置与启用

1. 选通道类型，填名称 + 说话方式（§2.5），再填该类型表单。
2. 保存：公共必填 + 类型 schema；webhook 类还要 `public_base_url`（或允许先存后连，§12）。
3. `enabled=true` 才注册 ingress。校验失败 → `status=error`，卡片可见，**不**静默丢消息。
4. `script_api`：创建即启用；吊销 = `enabled=false`。

### 3.2 入站时序（共有回合，特有等待策略）

| | `script_api`（保持） | IM webhook | IM 长连接 |
|--|----------------------|------------|-----------|
| 鉴权 | Bearer `lc_live_…` | 厂商签名 / encrypt | 建连时 App Secret；事件仍可能带 id |
| 调用方等待 | 默认同步最多 120s；超时 **202** + `turn_id` | **必须先 ACK**（约 3–5s） | 不要阻塞读循环 |
| 回合 | 共用 `ChannelTurnService`，可 `wait` | 同一服务，ACK 后后台跑；**禁止**在 webhook 里等 120s | 入站线程只投递 |
| 回复 | JSON body | 厂商发消息 API | 同左 |

IM 没有「同步等完整回复」这条产品路径。内部都是同一套回合；差别只在适配层是否 wait。

### 3.3 归一化（共有事件）

各适配器产出同一 `InboundEvent`，再交给 `ChannelTurnService`：

```
InboundEvent
  instance_id
  external_user_id / display_name
  external_chat_id
  external_thread_id | null
  event_id                          # 幂等
  text
  attachments[]                     # P2
  is_group
  mentioned_bot
```

文本空且无附件：ACK 后丢弃，不空跑回合。

### 3.4 失败、重试、签名、幂等、超时

| 问题 | 建议 |
|------|------|
| 签名 / 解密失败 | 401/403，打 `status=error`，不创建会话 |
| 平台重试同一 `event_id` | 短 TTL 去重（建议 24h）。已处理：再 ACK，不再开回合 |
| 同实例角色已有 running turn | 角色锁。IM **不要**对平台 409；ACK 后进**实例入站队列**。`script_api` 仍 HTTP 409（已确认） |
| 回合失败 | 可向该外部会话发一句失败说明；内部时间线仍能看 |
| 回合很长 | 内部跑完为止。可选：超过 N 秒先发「还在处理」（**待确认**，P1 默认可关） |
| 出站失败 | 有限次重试（仅 transient）；记实例日志；不回滚已落库助手消息 |
| 长连接断开 | 自动重连 + `status=error` |

### 3.5 `needs_input` / 高风险沙箱

现网：`origin=api` **跳过网页沙箱确认**；`ask_user` 在设置页没有完整闭环。

| 情况 | P1 | P2 |
|------|----|----|
| `ask_user` | 纯文本打到该通道；或「请到 Lore Chat 网页确认」 | 结构化卡片（仍是适配层，问题本身是共有 Pending） |
| 高风险 `sandbox_run` | 与脚本通道一样跳过网页确认（自用假设） | 实例开关「本通道禁用沙箱」 |

**待确认：** P1 是否允许非脚本通道触发沙箱。建议允许；群聊默认关沙箱直到有发送者白名单。

---

## 4. 类型特有配置（示例 schema，非最终实现）

以下字段**不属于**公共模型。公共项（名称、人设、启停）见 §2.1。字段名按常见官方文档，实现以厂商当前 API 为准。

### 4.1 `script_api`（第一种通道：脚本 / HTTP）

| 字段 | 密 | 说明 |
|------|----|------|
| `token` | 签发后只哈希 | 系统生成 `lc_live_…`，明文只创建时给一次 |
| 调用 | — | `POST /api/v1/chat`，Bearer（现网契约不变） |

无厂商 AppId。迁移见 §7.4。

### 4.2 微信（先分清再做）

| 形态 | 自托管现实性 | 本草案 |
|------|----------------|--------|
| **企业微信应用** | 有企业主体即可；回调常要公网 HTTPS | **微信线首选**，类型 `wecom` |
| **公众号 / 服务号** | 备案域名、认证号；回复窗口短 | P2+，`wechat_mp`；不要和企微混一个 schema |
| **个人微信 / 协议号 / WeChaty** | 非官方 | **明确不做** |

`wecom` 特有：

| 字段 | 密 | 说明 |
|------|----|------|
| `corp_id` / `agent_id` | 否 | |
| `corp_secret` | 是 | |
| `token` / `encoding_aes_key` | 是 | 回调验签与解密 |
| `callback_url` | 只读展示 | `{public_base_url}/api/channels/{id}/wecom` |

无 `public_base_url`：可保存，启用则 `status=error`，提示去配公网根（与分享链同一配置）。

### 4.3 钉钉 `dingtalk`

| 字段 | 密 | 说明 |
|------|----|------|
| `app_key` / `app_secret` | 否 / 是 | 企业内部应用 |
| `robot_code` | 否 | |
| `ingress` | 否 | 建议默认 **Stream 长连接**；可选 HTTP 回调 |
| `token` / `aes_key` | 是 | 仅 HTTP 回调 |

### 4.4 飞书 `feishu`

| 字段 | 密 | 说明 |
|------|----|------|
| `app_id` / `app_secret` | 否 / 是 | 企业自建应用 |
| `verification_token` / `encrypt_key` | 是 | |
| `ingress` | 否 | **默认长连接**；可选 webhook |
| `webhook_url` | 只读 | 仅 webhook 模式 |

长连接不依赖备案域名，是 P1 默认第一家 IM 的主因（§8）。

### 4.5 Slack `slack`

| 字段 | 密 | 说明 |
|------|----|------|
| `bot_token` | 是 | `xoxb-…` |
| `signing_secret` | 是 | Events API |
| `app_token` | 是 | Socket Mode `xapp-…`；webhook 模式可空 |
| `ingress` | 否 | **默认 Socket Mode** |
| `request_url` | 只读 | webhook：`{public_base_url}/api/channels/{id}/slack` |

与飞书同构（都能免公网）。P1 若主人已用 Slack，可改先做它，**公共模型不变**。

### 4.6 公网 URL（webhook 类特有依赖）

沿用设置里的 `public_base_url`。卡片展示拼好的回调 URL，不要让用户手填内部路径。

- 长连接与 `script_api`：无公网也可启用。
- webhook 类型：未配置则启用失败（或允许存成未启用，§12）。

### 4.7 密钥存储

| 现网 | 做法 |
|------|------|
| API Key | SHA-256 落盘 `.kb/api_keys.json`；明文只创建时给一次 |
| 模型 / 搜索 Key | `.kb/settings.json`；API 脱敏；PATCH 空/掩码保留旧值 |

IM 的 App Secret **运行时还要拿去调厂商**，不能只存哈希。

**拍板建议：** `script_api` token 继续哈希。其它通道 secret 对齐 settings：实例存储里落盘、回包脱敏、空/掩码不覆盖。**P0 不做**单独信封加密；要做就和 settings 一起做。

---

## 5. UI（设置页演进）

从当前「开放接口」页演进成 **聊天通道** 首页。不新开「IM」顶层页签。

### 5.1 页签

**拍板建议：** 文案 **「聊天通道」**；`id` 仍可用 `openapi` 以免打掉 localStorage。副标题：「脚本、微信、飞书、Slack 等，都是聊天通道。」

备选（待确认）：「开放接口」保留作副名，如「聊天通道（原开放接口）」。不要只写「插件」。

### 5.2 首页：同级实例列表

一句说明 + 主按钮 **添加通道**。

列表：**所有通道实例**。`script_api` 与飞书、Slack **同一列表、同一卡片结构**，用类型图标区分，不要「密钥区 + IM 区」两截。

每张卡（共有槽位）：

- 类型图标 + 名称
- 状态：启用开关；已启用 / 未启用 / 校验失败
- 说话方式徽章
- 上次活动（脚本：Key 前缀 + 尚未调用；IM：连接或上次消息）
- **查看会话**（该实例只读时间线）
- **日志**（建议；P0 脚本可弱化）
- 停用 / 吊销 / 删除（脚本吊销 = 停用）

空态：还没有聊天通道；主按钮添加。有旧密钥时，投影进列表，不要空态。

快捷方式：可保留「创建脚本通道」以免老用户找「创建密钥」；仍是向导里选 `script_api`，不是第二入口。

### 5.3 添加通道

1. **选类型**（脚本 / HTTP、飞书、Slack…；未实现的灰显「即将支持」）。类型是适配器，不是另一套产品。
2. **共有表单**：名称、说话方式（默认同名 / 已有人设 / 新建 / 从左栏复制提示词）。
3. **特有表单**：该类型 schema。
4. 保存并启用。`script_api` 仍只显示一次明文 Key。
5. IM：成功则展示该类型的下一步（开长连接权限、粘贴回调 URL）。

### 5.4 折叠区

- **说话方式**：现网折叠保留，作为**通道共用**人设库；「N 把密钥在用」改为「N 个通道在用」。
- **接入说明**：不要只在首页堆 curl。`script_api` 的 curl 放进该实例或类型说明；IM 的回调步骤同理。

### 5.5 查看会话（共有）

点实例进入只读记录页（现网 Key 的「查看会话」）。数据：该 hidden 角色的 timeline / 会话列表。两实例选同一人设：徽章同名，点进去是**两份互不相干的聊天**。

### 5.6 不要做的界面

- 不要把脚本和 IM 做成两个页签或两张主表。
- 不要按人设合并时间线（已确认）。
- 不要在左栏出现通道工作角色。
- 不要做插件市场、评分、第三方上传。
- 不要用「插件」当页签名。

---

## 6. 内部 seam 建议

### 6.1 模块路径

建议：`backend/app/engine/channel_plugins/`（产品名聊天通道插件；避免泛 `plugins/`，也避免和 Slack「channel」、角色群房间撞名）。

| 单元 | 职责 |
|------|------|
| `ChannelPluginRegistry` | 内置通道类型；进程启动时挂上 |
| `ChannelAdapter` | `validate_config`、`start/stop`、`parse_inbound`、`send_outbound`、`challenge` |
| `ChannelInstanceStore` | 实例 CRUD；secret 脱敏；`script_api` 与 Key 投影 |
| `ChannelTurnService` | **共有**：验实例启用 → 映射会话 → `begin_persisted_turn`；不解析 SSE |
| `channel_runtime` | 长连接 task，跟 `Container` / `apply_settings` |

HTTP：

- Cookie：`/api/open-api/*` 可留作别名；主资源 `/api/channel-plugins`（或 `/api/channels`）做实例 CRUD。
- 公开入站：`/api/channels/{instance_id}/{type}`。无 Cookie、无主人 Bearer。只信厂商签名。脚本 Bearer **仍然**不能打设置/KB。

出站只走该类型 `send_outbound`。

### 6.2 复用现网回合（共有）

`OpenApiService.complete_chat` 已是正确骨架。抽成 `ChannelTurnService` 后：

| 调用方 | wait |
|--------|------|
| `POST /api/v1/chat` | 是（现网 timeout / 202） |
| IM adapter | 否；finalize 后 `send_outbound` |

观测仍走 `TurnExecutionHub`。禁止为飞书再写 `stream_ephemeral`；禁止通道会话 `origin=web`。

### 6.3 `origin` 扩展

| origin | 谁 |
|--------|-----|
| `web` | 左栏 |
| `api` | `script_api`（**保持字符串**） |
| `feishu` / `slack` / `wecom` / `dingtalk` / `wechat_mp` | 对应类型 |

左栏 tip、记忆 dirty、最近活动：排除 `origin in CHANNEL_ORIGINS`，不要只判 `!= api`。

### 6.4 `mode=api` 用于所有聊天通道

现网 `select_tools(mode=api)`：只读 KB、可读 Skill、可沙箱；无写库、无回写、无改角色/例行/记忆写入、无群聊派工。不跑记忆抽取。

**拍板建议：所有聊天通道默认同一 `mode=api`。** 外部是半信任边界；与「脚本乱写知识库」同一类风险。P2 再做实例级「允许写库」（默认关）。

沙箱：hidden 角色走 `sandbox_max_api_roles`，不占左栏名额。脚本与 IM 实例**合计**受该上限；满则本轮失败，**绝不借用**左栏或其它实例的盘。

### 6.5 并发与队列

同实例第二枪：脚本仍 409；IM ACK + 排队。不要把外部事件接到 `RoomDelivery` 上——内部角色互通与聊天通道不是同一条总线。

---

## 7. 存储（建议）

| 现网 | 聊天通道之后 |
|------|------------|
| `.kb/api_keys.json` | 投影为 `script_api` 实例；P0 可双写 |
| `roles` hidden + `persona_id` | 所有通道类型同样 |
| `conversations.origin` + `api_key_id` | 增 `channel_instance_id`（脚本行可等于原 key id） |
| 无 | **公共** `channel_threads` |
| 无 | 去重 `event_id`；实例日志 |

### 7.4 `script_api` 迁移（P0 必须无感）

1. 读旧 `api_keys.json` → 每把 Key 一张 `type=script_api` 实例（`id` 可等于 `key_id`）。
2. `POST /api/v1/chat` 仍只认 Bearer。
3. Cookie 旧 `/api/open-api/keys` 可留作别名。
4. 不迁会话行：`origin=api` 已指向 `api_key_id`。

验收：同一把 Key 的 curl 与「查看会话」与迁移前一致。

---

## 8. 分期

### P0 — 公共模型 + 第一种通道（脚本 / HTTP）+ UI 骨架

- Registry + Adapter 协议 + `script_api` adapter（内部调现有 `OpenApiService` / 拆出的 `ChannelTurnService`）。
- 实例列表；旧 Key 投影成通道卡片。
- 设置页：页签名「聊天通道」、**同级列表**（先只有脚本类型）、共有槽位（人设、查看会话、启停）、添加向导骨架。
- **行为不变：** v1 chat、409、120s/202、人设活引用、左栏不出现 hidden、mode=api。
- 尚无第二家类型，但 UI/数据模型按「还会有飞书」来，避免以后把脚本再拆出去。

### P1 — 第二个类型（第一家 IM）

**建议默认：飞书 + 长连接。** 主人已用 Slack 则改 Socket Mode。公共模型不改，只加 adapter + 特有表单。

| 候选 | 公网 | P1？ |
|------|------|------|
| **飞书长连接** | 不需要 | **默认** |
| Slack Socket Mode | 不需要 | 主人已用 Slack 则换它 |
| 企微回调 | 通常要 | P2 |
| 钉钉 Stream | 不需要 | P2 |
| 公众号 | 要 | 更后 |
| 个微 | — | 不做 |

P1 范围：私聊文本；共有启停/状态/查看会话；异步回复；幂等；忙则排队。不做群、富媒体、卡片交互。

### P2

- 其余类型；企微/公众号 webhook。
- 群：@ 才回；发送者白名单。
- 富媒体走现有 `attachments`。
- `needs_input` 的类型特有卡片；实例级写库开关。
- 统一日志/用量按通道实例过滤。
- 删除实例与毁卷；「改为独立人设」。

---

## 9. 验收

### P0

1. 旧 `lc_live_` 调用 `POST /api/v1/chat` 与迁移前一致（含 409、202、会话隔离）。
2. 设置「聊天通道」列表能看见原密钥，与飞书等**同一卡片结构**（即使当时只有脚本类型）；人设徽章、查看会话、吊销仍在。
3. 左栏仍无通道工作角色。
4. 两把脚本通道同一人设：两套会话、两把沙箱。
5. 不引入飞书/Slack 代码路径也能通过现网 open-api 测试。
6. 文档与 UI 文案不把脚本描述成「另一套开放接口产品」。

### P1（在选定的第一家 IM 上）

7. 配好特有字段并启用后，私聊文本能收到回复（人设为该实例所选）。
8. 改共用人员设，下一轮脚本通道与 IM 通道都换新提示词。
9. 关实例或校验失败：外部消息进不来；已有时间线仍能「查看会话」。
10. 同一人连发两条：第二条不丢（排队），不双开同一 `role_id` 的 turn。
11. 左栏 tip 不出现该通道会话。
12. 写库 / 回写 / 改 Skill / `send_message` 不存在（mode=api）。
13. 无 `public_base_url` 时长连接类型仍能工作。
14. 脚本通道与 IM 通道在列表里同级，共有「说话方式 / 查看会话 / 启停 / 状态」。

---

## 10. 明确不做

- 泛「插件」平台、第三方商店、侧载 zip、多租户 OAuth。
- 把脚本 HTTP 与 IM 做成两套产品、两个页签、两套人设/会话模型。
- 请求或外部事件里指定左栏 `role_id` 去借沙箱。
- 左栏出现通道工作角色；按人设合并一条大时间线。
- 多实例共用一个 `role_id`；默认按外部线程再开多把沙箱（策略 B 须另开开关）。
- 个微 / 非官方协议。
- 把外部群做成 lore-chat 角色群。
- 为某个类型另写一套 Agent 或 ephemeral 不落库对话。
- 在 webhook 路由里解析 Agent SSE。
- OpenAI 兼容网关（仍是对外聊天 API 的 P2，与聊天通道正交）。

---

## 11. 相对已确认文档的变更提议（仅这几条，其余不动）

确认本文后，**实现阶段**才改代码；在此之前 [product-external-chat-api.md](product-external-chat-api.md) 仍全权有效。提议：

| # | 现口径 | 提议 | 为何 |
|---|--------|------|------|
| 1 | 设置入口叫「开放接口」，首页只管密钥 | 页签改为「聊天通道」；密钥是第一种通道实例，与 IM **同级列表** | 主人命名 |
| 2 | 删人设只拦「仍有密钥」 | 改为「仍有通道实例」 | 共有人设 |
| 3 | 左栏/记忆排除只认 `origin=api` | 排除全部通道 origin | 飞书会话不能进 tip |
| 4 | `is_api_role_id` 前缀 `api_` | hidden 通道工作角色含 `ext_` | 非脚本类型 |
| 5 | 同 Key HTTP 409 | **脚本保持 409**；其它类型 ACK+排队 | 平台会重试 |
| 6 | 记忆：API 不 dirty | 其它通道 P1 建议仍不抽；是否对「主人自己的 IM 私聊」开抽取 **待确认** | §12 |
| 7 | 人设与左栏：只复制、不跟随 | 保持方案 A（§2.5）；若要「跟随左栏角色人设」须另改已确认口径 | 待确认 |

不提议改：每 Key（现为每通道实例）一角色、人设可共享、mode=api 工具集、脚本同步 JSON+120s/202、不做多租户、不绑左栏 `role_id`。

---

## 12. 待主人确认

实现前请拍（其它按本文默认建议可开工）：

1. 页签名：建议 **「聊天通道」**。是否保留「开放接口」作副名？
2. 说话方式：确认方案 A（只绑人设；从左栏只复制副本），还是要做方案 B（跟随左栏角色提示词）？
3. P1 第二家类型：飞书长连接，还是 Slack Socket Mode？
4. 工作角色：确认每实例一角色 + IM 排队，还是 P1 就要按外部线程开角色？
5. 非脚本通道的私聊要不要跑记忆抽取？（建议 P1 否）
6. P1 是否允许非脚本通道用沙箱？群聊是否默认关沙箱？
7. 回合超过 ~15s 要不要先发「还在处理」？
8. Slack 频道无 thread 的裸消息：忽略 / 每条新会话 / 整频道一段？
9. webhook 类未配 `public_base_url`：禁止启用，还是允许保存为未启用？
10. 日志/用量：P0 是否就要按通道实例进用量页，还是 P1 再做？

---

## 13. 下一阶段实现切片（确认后）

1. 公共模型：Registry + 实例存储 + Key 投影为 `script_api`；测试投影与 list。
2. 设置 UI：同级列表 + 共有槽位（人设、查看会话、启停、状态）；先只创建脚本通道。
3. 抽出 `ChannelTurnService`；v1 走它；open-api 测试全绿。
4. 第二家类型（飞书或 Slack）只加 adapter 与特有表单，不改公共模型。

改提示词不在本范围。Agent 行为差异只通过已有 `mode=api` 与人设，不在 SYSTEM 里写「你在飞书里」。
