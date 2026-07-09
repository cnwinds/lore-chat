# 对话式知识管家

对话式知识库：你说内容，系统自动组织并保存为 Markdown；提问时混合检索并带来源回答。数据落在 `knowledge/` 目录，可直接浏览、编辑，并由 git 记录历史。

## 后端启动

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
copy .env.example .env          # 编辑 .env，填入 OPENAI_API_KEY 等
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

默认 API 地址：`http://localhost:8000`。

## 前端启动

```bash
cd frontend
npm install
npm run dev
```

前端默认通过 `VITE_API_BASE=http://localhost:8000` 访问后端（见 `frontend/.env`）。

## 数据目录说明

知识库根目录由环境变量 `KB_PATH` 指定（默认 `./knowledge`）：

```
knowledge/                 ← git 仓库，可直接打开浏览/编辑
├── 技术/
│   └── docker/
│       └── 常用命令.md
├── attachments/           ← 附件原件
└── .kb/
    ├── index/             ← 向量/全文索引（可删除后重建）
    ├── pending.json       ← 待用户确认的归置问题
    └── changelog.md       ← AI 整理操作记录
```

- **Markdown 文件**是唯一事实来源；索引仅为加速缓存。
- **git 历史**记录每次写入与整理，可随时回滚。
- **`.kb/changelog.md`** 汇总 AI 的归置与变更说明，便于审计。
