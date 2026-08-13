# ADR 2026-08-06：Agent 执行 Runtime 采用 OpenSandbox

## 状态

已采纳（2026-08-06）

## 背景

Lore Chat 的 Agent 工具面是服务器内白名单语义工具（KB / 网页 / 记忆 / `ask_user` 等），**不能**在回合中执行本机命令。视频类 skill（如 `hn-video-report`）需要 `edge-tts`、`hyperframes`、`ffmpeg` 等工具链。

经决策梳理（单操作者、强信任）：

- v1 **主路径是服务器侧执行**，本机客户端 / companion 延后；Runtime 接口预留可插拔
- 不在 `lorechat-backend` 容器内直接开放 shell（与聊天争资源、重建丢环境、爆炸半径过大）
- 需要**与 API 隔离、可持久的沙箱**；短命令同步、长任务异步 job；前端要关键节点事件，不能盲等
- 产物默认留在沙箱，**显式发布**才入库；KB 不整库可写挂进任意 shell

自研 execd / job / 流式日志会重复造轮子。成熟候选中：E2B 自托管过重；Daytona 不完全适合自托管底座；Den 有 AGPL 顾虑。**OpenSandbox**（Apache-2.0）提供 Docker/K8s 运行时、命令前后台、文件 API、SSE 流式，与现有 Compose 部署可并存。

## 决策

### 1. 底座

- v1 Server Runtime **采用 OpenSandbox**（Compose 旁挂 `opensandbox-server`）。
- `lorechat-backend` **只**经 OpenSandbox HTTP/SDK 下发命令与文件操作；**不**挂载 `docker.sock`。
- OpenSandbox **控制面**按上游设计挂载 `docker.sock` 以创建/管理沙箱容器；这是编排特权，不授予 Agent 工具面。

### 2. 生命周期与隔离

- 单操作者维护 **一个**长驻沙箱（sandbox id 持久化在 lore-chat 配置/状态中）。
- 持久层：Docker named volume（OpenSandbox `pvc`）挂到沙箱内 `/workspace`（及可选 home/工具目录）；重建沙箱时 **工具环境可清空，`/workspace` 默认保留**。
- 沙箱可出网、可装软件；**不**向沙箱暴露宿主机根盘、**不**向沙箱挂载 `docker.sock`、**不**把整个知识库可写挂进沙箱。
- 知识库写入仅经受控工具（如 `publish_from_sandbox` / 现有 `write_doc` 管线），从沙箱指定路径导入。

### 3. 与 Agent 循环的耦合

- **短任务**：同步 `commands.run`（或等价），stdout/stderr/退出码回写 tool result。
- **长任务**：后台 command / job；回合可挂起等待，但必须把 OpenSandbox 的 SSE / 日志轮询 **映射为 lore-chat Agent SSE 关键节点**（阶段、日志片段、退出码、产物路径）。
- 确认策略：v1 **默认信任模式开启**（全局 `sandbox_trust_mode=true`）；关闭后对装包/删改等高风险 `sandbox_run` 征询，批准后由后端直接执行。会话级信任延后。

### 4. 工具面厚度

- v1 对模型先暴露 **薄封装**：sandbox 短跑 / job、工作区文件列举与读日志、显式发布入库。
- 视频高频步骤后续再加少数类型化工具（如 TTS）；不在 v1 做成厚视频平台。
- 镜像策略：**先极简镜像验证**，把反复成功的依赖固化进自定义镜像（Dockerfile/脚本为真理来源，不靠聊天里一次性 `apt`）。

### 5. 明确非目标（v1）

- 本机 Runtime / 桌面客户端
- 在 `lorechat-backend` 内直接 `subprocess` 跑用户命令
- 以 E2B / Daytona 为自托管底座
- 多租户强隔离（产品仍是单操作者）

### 6. 可选部署

- **默认**（仅 `docker/docker-compose.yml`）：`SANDBOX_ENABLED=false`，无 OpenSandbox 服务，无命令执行能力。
- **带执行能力**：叠加 `docker/docker-compose.sandbox.yml`（启动 `opensandbox-server`，并向 backend 注入 `SANDBOX_ENABLED=true` 与连接参数）。
- `GET /api/health` → `capabilities.sandbox` 反映本实例是否启用；沙箱相关部署 Settings **不可**经 UI 热改（与 Compose 编排绑定）。
- **确认策略**：默认 `sandbox_trust_mode=true`，沙箱命令直接执行；关闭后对高风险 `sandbox_run` 征询（执行/取消），**批准后由后端直接执行**（不依赖模型再调 `sandbox_run`）。
- **软件源**：`sandbox_mirror_region=cn|global`（默认 `cn`），可经设置热改；影响沙箱内 apt / pip / npm（国内=阿里云/npmmirror，国外=官方源）。切换后下次 `ensure_ready` 会重配。
- **执行与观测解耦**：有 `conversation_id` 的回合在进程内 `asyncio.Task`（`TurnExecutionHub`）中执行；前端 SSE 仅为观测通道，连接断开**不**取消回合、**不** interrupt 沙箱。仅 **显式 stop**（`POST /api/chat/stop`）会 cancel Task 并 interrupt 沙箱；进程重启时将 DB 中无对应 Task 的 `running` 孤儿 **finalize 为 interrupted**（不保证能 interrupt 已失联的沙箱进程）。
- **跨回合**：`sandbox_job_status(execution_id)` 查询未完成的后台任务。

## 后果

- 新增运维面：`opensandbox-server`、execd 镜像拉取、named volume、API key；与 lore-chat Compose 同机编排。
- Agent / SSE / timeline 需扩展「执行中关键节点」事件模型；长任务与单 worker uvicorn 的交互必须按 job 设计，避免堵死事件循环。
- 控制面持有 `docker.sock`：须限制谁能访问 OpenSandbox API（本机网络 / API key），避免变成「远程任意起容器」。
- 后续若插 Local Runtime，只要实现同一 Runtime 端口，Agent 工具契约可保持稳定。

## Spike

见 `docs/spikes/2026-08-06-opensandbox/`：验证旁挂服务、短命令、流式/后台长命令、named volume 持久、以及与「backend 无 sock」边界是否成立。

**Spike 结果（2026-08-06）：PASS。** 详见同目录 `NOTES.md`（含 `host_ip=127.0.0.1`、端口 `18090`、execd 预拉等运维要点）。
