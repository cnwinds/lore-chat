# docs 地图

写代码先看根目录 [CONTEXT.md](../CONTEXT.md) 与 [ADR](adr/README.md)。本目录只放**仍有效**的设计与未完成工作；已落地的逐任务实施计划已删除（以代码与 ADR 为准）。

| 目录 | 用途 |
|------|------|
| [adr/](adr/README.md) | 架构决策（已采纳，不删不改写原文） |
| [brand/](brand/logo.html) | Logo / 字标资源与生成脚本 |
| [superpowers/specs/](superpowers/README.md) | 仍被引用或尚未落地的产品规格 |
| [superpowers/plans/](superpowers/README.md) | **仅**公开演示站（未实施）的实现计划 |

## 还在用的规格

| 文档 | 说明 |
|------|------|
| [记忆抽取重设计](superpowers/specs/2026-08-07-memory-extraction-redesign.md) | 抽取/合并权威；提示词门槛见根目录 `AGENTS.md` |
| [记忆层](superpowers/specs/2026-07-13-memory-layer-design.md) | 召回、tombstone、衰减；与上文一起读 |
| [Agent 工具](superpowers/specs/2026-07-10-agent-tools-design.md) | 工具面设计；清单以 `tool_catalog.py` 为准 |
| [ingest / ask](superpowers/specs/2026-07-12-ingest-ask-api-design.md) | 同步机器 API（测试/脚本，不是产品主入口） |
| [局部编辑 edit_doc](superpowers/specs/2026-07-12-partial-doc-edit-design.md) | Agent 补丁式改文档 |
| [多文档合并](superpowers/specs/2026-07-11-multi-doc-merge-design.md) | HTTP 合并审阅；边界见 [ADR 08-05](adr/2026-08-05-merge-ui-only.md) |
| [系统层与会话总结](superpowers/specs/2026-07-11-system-layer-and-conversation-summary-design.md) | 戒律 / 心法 / 归档成文 |
| [登录、备份、热配置](superpowers/specs/2026-07-16-deploy-auth-backup-settings-design.md) | 单机门禁与导入导出 |
| [演示站](superpowers/specs/2026-08-18-demo-mode-design.md) | **未落地**；实施计划见同主题 plans |

## 未完成

公开演示站：规格 + [运行时计划](superpowers/plans/2026-08-18-demo-runtime.md) + [内容计划](superpowers/plans/2026-08-18-demo-content.md)。
