# Runtime data (local)

Docker Compose mounts this directory for persistent data.

在 **git clone** 里，根目录 `./lorechat.sh` 与 `deploy/lorechat.sh` 都挂这里（`knowledge/` + `backups/`）。
curl 安装的独立目录才用启动器旁的 `./data/`。

可用 `LORECHAT_DATA_DIR` 覆盖。这些路径是 **private** 且 gitignored（`backups/.gitkeep` 除外），不要提交 API Key 或个人笔记。
