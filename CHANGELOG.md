# Changelog

本文件遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 风格，版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added

- 会话与文档公开只读分享：不透明分享链接、快照/定版、有效期（含自定义）、设置页管理、公开 `/share/{id}` 页
- 分享内嵌附件经 media grant 物化；过期链接返回 410

### Fixed

- 文档预览 overflow「分享」入口实际可用；分享弹窗与管理页交互与样式完善

## [0.2.1] - 2026-08-22

### Added

- 聊天框支持粘贴本机复制的文件（图片、视频及其他文件进入 Composer 托盘）

### Fixed

- 媒体图库视频瓦片预览与全屏播放（不再仅落在「其他文件」下载列表）
- Composer 多模态提示补全：视频条数上限、50MB、大文件 signed URL、识图 max_images 校验
- 统一视频缩略/播放组件（附件列表、托盘与图库共用 VideoLightbox）

## [0.2.0] - 2026-08-22

### Added

- 聊天视频附件：按模型链 catalog 能力路由与物化 wire；Composer 校验上传并提示（单视频 50MB；大文件在配置 `public_base_url` 时优先 signed URL）
- 设置页候选链编辑器展示 video / max_videos / max_images 等多模态能力
- models.dev 与 catalog 补充视频模型能力元数据

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

[Unreleased]: https://github.com/cnwinds/lore-chat/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/cnwinds/lore-chat/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/cnwinds/lore-chat/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/cnwinds/lore-chat/releases/tag/v0.1.0
