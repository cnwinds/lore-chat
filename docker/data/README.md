# Runtime data (local)

Docker Compose mounts this directory for persistent data:

| Path | Purpose |
|------|---------|
| `knowledge/` | Knowledge base (Markdown + `.kb/` index). Created on first run. |
| `backups/` | Automatic backups before import / restore. |

These paths are **private** and gitignored (except `backups/.gitkeep`). Do not commit API keys or personal notes from here.
