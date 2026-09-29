# ADR 2026-09-29：沙箱观测保真（忠实输出 / 结构化探针 / 缺席分型 / 产出跨回合可见）

## 状态

已采纳（2026-09-29）；P0、P1 均已落地。

`run()` 只有启动 job 这一步可在会话失效时重建重试；job 启动后轮询失败直接抛出，不重跑命令（非幂等命令如 `rm -rf` 不得执行两次）。超时中断后再取一次日志尾。

P0 落地时顺带修正：`_is_recoverable_sandbox_error` 曾把任何 `SandboxApiException`（含 `FILE_NOT_FOUND`、非目录）当作会话失效，读一个不存在的文件就会清掉持久化的 `sandbox_id` 并新建容器。现只认连接类错误与 `SANDBOX_NOT_FOUND`；文件级错误在适配器内先分型为 `SandboxFsError`，不进入重建判断。

## 背景

### 事故

会话「帮我拉取最近一个月的游戏类型」（`5721a98688b9`，角色 `b2f18dfd3f61`）：上一轮用 `sandbox_run` 把数据写到 `/workspace/steam_result.json`；下一轮主人回复「可以」，助手称「目录已被清理，上一轮数据没了」，重拉数据时撞上 Steam 限流。

文件**从未被清理**，一直在该角色卷里。实际链路：

1. `sandbox_list_dir /workspace` 返回「共 1 项」（实有 12 项）。
2. `sandbox_list_dir /workspace/conversations` 返回 1 项，名字是 `5721a98688b9/a76572da7195/db33d98c1bc7/ed8109bbbba5`——其实是四个并列目录名首尾相接。
3. 列这个「路径」得到 `No such file or directory`，模型断言「被清理」；随后 `mkdir -p` 把这条幽灵路径真建了出来，错误观测变成了磁盘状态。

直接原因：`OpenSandboxRuntime.run()` 走同步 `commands.run` + 流式回调，execd 按行回调且**去掉换行**；`run()` 只给进度日志补了换行（`ensure_line_chunk`），拼 `CommandResult.stdout` 用的是原始分片；`list_dir` 再对 `ls -1Ap` 的输出按行拆分。线上复现：`run("ls -1Ap -- /workspace/conversations").stdout == '5721a98688b9/a76572da7195/db33d98c1bc7/ed8109bbbba5/'`。

### 同类前科

2026-09-03 提交 `035f57b` 已遇到「模型把相邻文件名粘成一个路径」，当时归因为模型从多行 summary 里拼路径，改成 summary 只写条数并在工具描述里加「不要从 summary 拼路径」。症状被压住，传输层根因未动，三周后以更坏的形态复发（直接给出错误事实）。单测没拦住，因为 `FakeSandboxRuntime.list_dir` 在内存里直接构造条目，不经过 `run()` 的文本解析。

### 次要原因

即使 `list_dir` 正确，下一轮也只能**猜**文件在哪：下一轮 history 只带上一轮正文、征询与【本轮产出】脚注，脚注只收知识库写入类工具（`_TURN_OUTPUT_TOOLS`），`sandbox_run` 在工作区写的文件从不跨回合可见。本例上一轮用绝对路径写在 `/workspace` 根，下一轮按默认 cwd 去会话目录找。

### 实测（现网 execd，SDK `opensandbox==0.1.16`）

| 通道 | 输出保真 | 短命令耗时 | 备注 |
|---|---|---|---|
| 同步 `commands.run` + 回调 | **有损**：每行去换行；`printf 'a\n\nb'; printf 'c\n'` 回调为 `['a', '\n', 'bc']`；末行有无换行不可辨 | ~1000 ms（固定开销） | stdout / stderr 分开 |
| 后台 job + `get_background_command_logs` 游标 | **逐字节一致**（空行、无尾换行、70 KB 长行、20 万行三页分页均完整） | ~8 ms | stdout / stderr 合流；退出码正确 |
| `files.get_file_info` / `read_bytes` / `write_files` | 结构化 | ~1 ms | 缺失返回 `FILE_NOT_FOUND` 类错误码；`entry_type` 为空 |
| `files.list_directory` | — | — | 现网不可用（服务端响应非 JSON → `INVALID_ARGUMENT`） |

## 根因（类别）

**不可信的文本通道被当成了结构化事实的来源，且失败被报告成确定的事实。** 具体三层：

1. 端口 `SandboxRuntime.run()` 的输出不忠实——传输分帧泄漏到调用方。
2. 结构化信息（目录条目）靠解析人读格式（`ls`）得到，任何分帧 / 特殊文件名都会静默改变结果。
3. 「任意非零退出」一律映射成 `FileNotFoundError`，工具再把它呈现为「不存在」；模型把「此刻此路径不存在」外推成「被清理」。

## 决策

### 1. 输出忠实是端口契约

- `SandboxRuntime.run()` 返回的输出必须是命令实际写出的文本，**逐字节**；适配器负责屏蔽传输分帧，调用方不得做换行修补。
- OpenSandbox 适配器的**所有**命令（含 bootstrap `mkdir`、镜像脚本、KB 投放的 `rm` / `mkdir`、探针）统一走**后台 job + 游标日志**通道；**不再使用**同步 `commands.run` 回调通道。
- `run()` 与 `SandboxExecutionEngine` 共用同一个「启动 job → 按游标取尽日志 → 取退出码」原语；取消时 `interrupt`，超时 `interrupt` 并标 `timed_out`。
- `CommandResult` 改为 `output`（stdout / stderr 合流、逐字节）+ `exit_code` + `timed_out`，去掉现有 stdout / stderr 分离字段——后台通道本就合流，保留两个字段只会制造「stderr 为空 = 没出错」的假象。
- 内部操作（探针、bootstrap、投放）**默认不向界面发进度**；只有 `sandbox_run` 经引擎流式展示。

### 2. 结构化事实走结构化来源，不解析人读格式

来源优先级：

1. SDK 结构化文件 API 中**经实测可用**者（`read_bytes`、`write_files`、`get_file_info`）；
2. **探针命令**：只输出一个机器文档（单个 JSON），自带错误分型；
3. 禁止解析 `ls` / `stat` / `find` 等人读输出来得出条目、类型或存在性。

`list_dir` 改为探针：`os.scandir` 后只输出一行 `@@lorechat-probe@@` 前缀的 JSON（成功 `{"ok": true, "entries": [{"name", "is_dir"}]}`，失败 `{"ok": false, "errno", "detail"}`，宿主按 errno 分型）。文件名含空格、换行、中文均安全。`files.list_directory` 在 execd 修好后可替换探针实现，端口与工具契约不变。

### 3. 缺席与失败分型

- 端口文件类操作（`list_dir`、`read_file`、存在性查询）的失败分为 `not_found` / `not_a_directory` / `permission_denied` / `runtime_error`（传输失败、探针自身失败、不可解析）。
- 映射依据是 SDK 错误码或探针 errno，**禁止**「非零退出即不存在」；`runtime_error` 不得呈现为不存在。execd 对非目录 / 无权限只给 `RUNTIME_ERROR` 加 Go syscall 文本，此时才退而匹配该文本。
- 工具结果对模型只陈述观测：`{"error": "not_found", "checked_path": "..."}`，summary 写「此刻不存在：<path>」，不附任何原因推测。

### 4. 工作区产出跨回合可见（确定性）

- `sandbox_run` 完成后，引擎以本次执行的开始时间为界，用探针列出工作区中新增 / 修改的文件，写入该工具块的 `workspace_outputs`（只含路径与大小，不含内容，限条数）。
- 排除隐藏目录与缓存（`.cache`、`.venvs`、`.local`、`node_modules`、`__pycache__` 等）以及**其他**会话 / 定时任务的子目录（`/workspace/conversations/<其他 id>`、`/workspace/schedules/<其他 id>`），避免同角色跨会话串味。
- `ConversationTranscript` 的【本轮产出】脚注增加「沙箱文件（未入库）」一栏，列出上述路径。下一轮凭确定性记录找文件，不靠模型记忆或猜 cwd。

P1 落地细节：

- 以沙箱自身时钟回溯（执行已耗时 + 5 s 余量），不传宿主时间戳，规避容器时钟偏差；`sandbox_stop` 与 `if_exceeded=stop` 同样探测，检查点（仍在运行）不探测。
- 按修改时间取最新 20 条，单次最多扫描 20000 个文件，超出即标 `truncated`；遍历先进 `conversations` / `schedules`（已收窄到本会话 / 本定时任务），大构建目录不会先耗尽扫描上限。实测 3.6 万文件的工作区约 0.4 s。
- 探针失败只记日志，不影响命令结果；没有新文件时结果里不带该字段。
- 批准后由后端直接执行的命令没有工具块，同一清单附在续跑提示里。

### 5. 契约测试：Fake 不得绕开解码层

- 探针 JSON 解码、错误分型、日志拼接做成纯函数模块，FakeRuntime 与 OpenSandboxRuntime **共用**；Fake 只模拟「命令产出的原始文本 / 错误码」，不得在内存里直接构造 `DirEntry`。
- 一套端口契约用例同时跑两种 runtime：Fake 常驻 CI；OpenSandbox 以 opt-in 集成标记在有沙箱的环境运行。
- 用例须覆盖：多行保真（空行、无尾换行、>64 KB 长行、分段写入）、特殊文件名、`not_found` / `not_a_directory` / `permission_denied` / `runtime_error` 各自分型、大输出分页完整。

### 6. 提示词层不加规则

《戒律》已有「先取证后动手」「检索无果时如实说未找到可靠依据，不猜测」。本次主因是工具交出了错误事实，不是缺原则；按 [AGENTS.md](../../AGENTS.md) §0 不针对个案加句。撤回 `035f57b` 中基于错误归因的注释与描述（「避免 JSON 转义换行导致模型粘连文件名」「不要从 summary 拼路径」）；「路径以 `entries[].path` 为准、summary 单行计数」本身是好契约，保留。

## 备选方案

- **在同步回调里补换行**（`out_chunks.append(ensure_line_chunk(text))`）：改一行即可止血，但同步通道本身有损（无尾换行的片段与下一行合并、末行换行不可知、空行编码为 `'\n'`），依赖未文档化的分帧，且每次固定约 1 s。不采纳为方案，仅可作 P0 前的临时热修。
- **立即改用 `files.list_directory`**：现网 execd 不可用、`entry_type` 为空。等上游修复后再替换探针实现。
- **只修 `list_dir`，不动 `run()`**：`run()` 仍有损，下一个读输出的调用方（base64 读回退、镜像脚本诊断、投放错误详情）会再踩。
- **把上一轮工具原文整段回灌 history**：成本高，与「工具原文不回灌、按需 `read_last_tool_results`」的既有取舍冲突，且后者只覆盖最近一轮。决策 4 只回灌确定性的路径清单。

## 后果

- 修订 [ADR 2026-08-06](2026-08-06-opensandbox-runtime.md) §3「短任务同步 `commands.run`」：所有命令走 job 通道；延续 [ADR 2026-08-28](2026-08-28-sandbox-execution-wait-budget.md) 对 `sandbox_run` 的统一。
- 内部操作延迟从约 1 s 降到约 10 ms（KB 投放的 `rm` / `mkdir`、镜像探测、`list_dir`）。`_call_sandbox` 注释「OpenSandbox 跑一条 `true` 约 1s」应更正为同步端点开销。
- 调用方拿不到单独的 stderr；需要干净数据的必须用探针或文件 API。
- 每次 `sandbox_run` 完成多一次产出探测（小工作区约 10 ms，扫满上限约 0.4 s）。
- 已被错误观测写出的幽灵目录（本例 `/workspace/conversations/5721a98688b9/a76572da7195/db33d98c1bc7/ed8109bbbba5`）不自动清理。
- [CONTEXT.md](../../CONTEXT.md) 沙箱一行在落地后同步：端口输出契约、探针模块、`workspace_outputs`。

## 分期

| 期 | 内容 |
|---|---|
| P0 | 决策 1、2、3、5；撤回 `035f57b` 的错误归因（决策 6）。修复本事故 |
| P1 | 决策 4（`workspace_outputs` + 【本轮产出】沙箱栏） |

## 验收意图

- 列一个含 N 个子项的目录，`entries` 恰为 N 条，名字与 `ls -A` 一致；含空格 / 换行 / 中文的文件名不被拆分或合并。
- `run()` 对 `printf 'a\n\nb'; sleep 0.3; printf 'c\n'` 返回 `'a\n\nbc\n'`；对无尾换行输出不追加换行。
- 列不存在路径 → `not_found`；列普通文件 → `not_a_directory`；探针不可解析 / 连接失败 → `runtime_error`，且工具 summary 不出现「不存在」。
- 上一轮 `sandbox_run` 用绝对路径写到 `/workspace/x.json`，下一轮 history 的【本轮产出】含该路径；同角色另一会话目录中的文件不出现。
- FakeRuntime 与 OpenSandboxRuntime 跑同一套契约用例全部通过。
