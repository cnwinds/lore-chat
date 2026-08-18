# 演示内容

演示站的知识库、会话与记忆事实，由内容线生产与固化。

设计与实现计划见：

- [`docs/superpowers/specs/2026-08-18-demo-mode-design.md`](../docs/superpowers/specs/2026-08-18-demo-mode-design.md) §10-11
- [`docs/superpowers/plans/2026-08-18-demo-content.md`](../docs/superpowers/plans/2026-08-18-demo-content.md)

## 进 git 的是什么

| 路径 | 内容 |
|------|------|
| `knowledge/` | 全部 Markdown 与附件，原样即定稿 |
| `conversations/*.json` | 每会话一个，`tools/dump.py` 产出 |
| `memory.json` | 记忆事实 |
| `manifest.json` | `reference_date` 等构建元数据 |

**SQLite 一律不进 git**：`*.db` 是构建产物，不是源。

## 生产流程

1. 准备一台普通实例（`DEMO_MODE=0`、空 KB、配好模型链与搜索 provider）
2. `cd demo && python -m seed.run --base-url http://localhost:8080 --password <管理员密码>`
3. 人工定稿：Markdown 直接改；会话与记忆用 `tools/dump.py` 导出改完再 `tools/load.py` 导回
4. `cd demo && python -m tools.dump --kb <实例 KB 路径> --out .`
5. 提交 `demo/`

`tools/` 与 `seed/` 内部按包互相引用，命令行请用 `cd demo && python -m tools.xxx`
的形式运行，不要直接 `python demo/tools/dump.py`。

## 构建（部署即重置）

```bash
python demo/build.py --kb /data/knowledge
```

会清空运行时 KB、从 `knowledge/` 物化、灌入会话与记忆、按「距今多少天」平移时间戳、重建索引。
演示站容器每次启动执行一次，任何运行期漂移自动消失。
