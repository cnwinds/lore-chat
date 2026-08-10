# 运行时数据（本地）

单文件启动器（`lorechat.sh` / `lorechat.ps1`）会在**脚本所在目录**创建 `data/`：

| 路径 | 用途 |
|------|------|
| `knowledge/` | 知识库（Markdown + `.kb/` 索引与设置） |
| `backups/` | 导入 / 还原前的自动备份 |

仓库内若保留 `deploy/data/`，仅作开发时占位；请勿将个人笔记或 API Key 提交到 git。
