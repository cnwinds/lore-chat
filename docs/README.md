# docs 地图

写代码先看根目录 [CONTEXT.md](../CONTEXT.md) 与 [ADR](adr/README.md)。**已落地行为以代码为准。** 提示词与发版见 [AGENTS.md](../AGENTS.md)。

## 怎么读

| 你要… | 去哪 |
|------|------|
| 改代码、找模块边界 | [CONTEXT.md](../CONTEXT.md) |
| 某次架构取舍为什么这样 | [adr/](adr/README.md)（已采纳不改写原文） |
| 多角色 / 群聊 / 聊天通道的产品口径 | [product/](product/) |
| Logo / 字标 | [brand/](brand/logo.html) |

不要在本目录再堆实施计划、spike 或 Superpowers 头脑风暴。过期规格以代码与 ADR 为准，不再平行维护第二套「当前设计」。

## 产品规格

拍板时的产品展开，供对照 ADR。实现后不另开规格目录维护现状。

| 文档 | 状态 | 说明 |
|------|------|------|
| [product/multi-role.md](product/multi-role.md) | 已落地 | 多角色产品 / 三栏界面 / 统一时间线（ADR 2026-09-09、09-10） |
| [product/role-rooms.md](product/role-rooms.md) | 已落地 | 角色互通与群聊：房间 + 投递 + 唤醒（ADR 2026-09-12 起） |
| [product/external-chat-api.md](product/external-chat-api.md) | 已落地（脚本通道） | `POST /api/v1/chat`：人设可共享，每 Key 独立隐藏角色 |
| [product/channel-plugins.md](product/channel-plugins.md) | 已落地（P0–P2） | 聊天通道插件超集；公众号仅灰显 |

每角色执行沙箱见 [ADR 2026-09-10](adr/2026-09-10-role-scoped-sandbox.md)，不再另写摘要。

## 品牌

[brand/](brand/logo.html) 为 Logo / 字标资源与生成脚本。
