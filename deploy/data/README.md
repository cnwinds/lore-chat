# 运行时数据（本地）

独立安装（curl 下来的单文件启动器）会在**脚本所在目录**创建 `data/`。

在本仓库的 `deploy/` 下运行启动器时，**不会**用这里，而是挂 `../docker/data`（可用 `LORECHAT_DATA_DIR` 覆盖）。

| 路径 | 用途 |
|------|------|
| `knowledge/` | 知识库（Markdown + `.kb/` 索引与设置） |
| `backups/` | 导入 / 还原前的自动备份 |

请勿将个人笔记或 API Key 提交到 git。
