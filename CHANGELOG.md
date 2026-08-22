# Changelog

本文件遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 风格，版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Fixed

- 带图对话不再改走同步补全，与无图共用真流式，思考与正文可实时输出
- 切换正在输出的会话时，旧观测的收尾不再清掉新会话的流所有权，也不再误驱动另一会话的发送队列
- 切换会话时立即清空上一会话气泡，避免在历史加载完成前把新消息追加到错误会话上
- 兼容 OpenRouter（如 ox）流式思考字段 `reasoning`，避免长时间有 chunk 但界面无思考输出

## [0.1.0] - 2026-08-19

首个对外发行版：本地优先的 AI 工作系统，对话可沉淀为知识、记忆与可复用 Skill。

### Added

- 对话、知识库、记忆与 Skill 主路径；网页设置配置模型与 API Key
- 首次配置「免费起步套餐」引导（Agnes Flash / 硅基流动嵌入 / 可选 Tavily）
- 厂家预设：OpenAI、智谱 / 智谱 Plan、百炼、DeepSeek、MiniMax / MiniMax Plan、Agnes、OpenRouter、硅基流动（嵌入）
- 预构建一键启动：`deploy/lorechat.sh` / `deploy/lorechat.ps1`，以及 `get-lorechat.sh` / `get-lorechat.ps1`
- GHCR 镜像：`latest`（master 与发行 tag）以及 `X.Y.Z` / `X.Y`（不带 `v`；git tag 为 `vX.Y.Z`）；可用 `LORECHAT_IMAGE_TAG=0.1.0` 锁定版本
- 源码 Docker：`./lorechat.sh start --chat|--work`，可选开发热重载
- Work 模式 OpenSandbox 沙箱执行
- MIT 许可证与开源社区文件（SECURITY、CONTRIBUTING、CODE_OF_CONDUCT）
- GitHub Issue / PR 模板与 CI（backend pytest、frontend lint/test/build）

[Unreleased]: https://github.com/cnwinds/lore-chat/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/cnwinds/lore-chat/releases/tag/v0.1.0
