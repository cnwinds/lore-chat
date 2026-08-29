# Changelog

本文件遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 风格，版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.2.10] - 2026-08-29

### Fixed

- 沙箱投放/读写不再每次远程探活：过期会话改为调用失败时再建，避免固定多秒延迟

## [0.2.9] - 2026-08-28

### Added

- 沙箱命令统一后台流式执行；默认约每 60 秒检查点交还 Agent，可续等、等到完成或 `sandbox_stop`
- 新增 `sandbox_stop`，可强制停止后台沙箱命令

### Fixed

- 沙箱会话过期后自动探测并重建，减少 `ConnectError`
- Python 长任务日志不再因缓冲整段到达（自动 `PYTHONUNBUFFERED`）

## [0.2.8] - 2026-08-27

### Fixed

- 断线 reconcile 续观测时补全 AbortController，避免 reconcile 死循环导致发行 CI 内存溢出
- 跨会话发送时不再把上一会话的历史气泡拼进新消息

## [0.2.6] - 2026-08-27

### Fixed

- 修复前端测试 lint 导致 `v0.2.5` 发行 CI 未通过（无镜像发布）

## [0.2.5] - 2026-08-27

### Added

- 轻量回合状态 API（`GET /conversations/{id}/turns/active`），断线重连时更快探测服务端是否在跑

### Fixed

- 切换会话时流式 UI 与模型显示不再串台
- 观测断线后以服务端状态 reconcile，减少误报失败并支持续接
- 聊天输入：Enter 发送、Shift+Enter 换行
- 已启用 Skill 时模型可正确收到 Skill 目录（兼容 GLM 等仅识别单条 system 的 API）

## [0.2.4] - 2026-08-26

### Added

- 主应用手机端体验：侧栏抽屉导航、聊天顶栏、提问 FAB 抽屉、文档全屏预览与安全区适配

### Fixed

- 会话与文档公开分享页移动端阅读（FAB + 底部抽屉提问/目录导航）
- 知识库文档重命名或移动后，跟随会话更新的 live 分享链接自动更新路径
- 文档分享页目录抽屉无法滚动

## [0.2.3] - 2026-08-25

### Fixed

- 文档公开分享页：左侧目录与正文独立滚动，滚动时章节高亮同步；整体阅读布局与 Logo 尺寸优化

## [0.2.2] - 2026-08-25

### Added

- 会话与文档公开只读分享：不透明分享链接、快照/定版、有效期（含自定义）、设置页管理、公开 `/share/{id}` 页
- 分享内嵌附件经 media grant 物化；过期链接返回 410
- 分享 Phase 2：会话消息区间快照、访问密码（解锁 token）、访问次数与最近 Referer 统计
- 会话分享可选「跟随会话更新」，访客可查看对话最新内容
- 设置 → 检索页签可配置 `web_search` 默认返回条数（1–20）

### Fixed

- 文档预览 overflow「分享」入口实际可用；分享弹窗与管理页交互与样式完善
- 公开分享页窄栏布局、右侧提问导航与 Logo 尺寸

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

[Unreleased]: https://github.com/cnwinds/lore-chat/compare/v0.2.10...HEAD
[0.2.10]: https://github.com/cnwinds/lore-chat/compare/v0.2.9...v0.2.10
[0.2.9]: https://github.com/cnwinds/lore-chat/compare/v0.2.8...v0.2.9
[0.2.8]: https://github.com/cnwinds/lore-chat/compare/v0.2.6...v0.2.8
[0.2.6]: https://github.com/cnwinds/lore-chat/compare/v0.2.5...v0.2.6
[0.2.5]: https://github.com/cnwinds/lore-chat/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/cnwinds/lore-chat/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/cnwinds/lore-chat/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/cnwinds/lore-chat/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/cnwinds/lore-chat/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/cnwinds/lore-chat/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/cnwinds/lore-chat/releases/tag/v0.1.0
