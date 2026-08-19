# Lore Chat — Agent 约定

本文件约束在本仓库工作的 AI。**改提示词**或**做版本发布**前先读对应章节；日常写代码仍以 [CONTEXT.md](CONTEXT.md) 与 [docs/adr/](docs/adr/) 为准。

- [一、提示词编写](#一提示词编写)
- [二、版本发布](#二版本发布)

# 一、提示词编写

本文件约束 **lore-chat 开发时如何编写与修改提示词**（system prompt、抽取器 prompt、工具描述中的行为说明等）。改代码里的提示词前先读本节；评审提示词改动时对照本节。

适用范围示例：

- `backend/app/engine/agent/prompts.py`、`system_layer.py` 内置段
- `backend/app/engine/memory/*extractor*.py` 记忆抽取 prompt
- 其它 LLM 调用的 system / developer 指令
- 不宜用提示词堆砌的细节，应下沉到 Tool description 或代码契约时，也按本节取舍

---

## 0. 核心原则：根因治理，禁止孤例补丁

**当出现问题需要修改提示词时：**

1. **先定位本质层面的根因**——问：失败属于哪一类判断错误？（例如「把与主人无关的常识当成画像」，而不是「误记了 660 分」。）
2. **针对该类根因调整原则性表述**——让同一类输入以后都被正确处理。
3. **禁止针对具体案例加补丁**——例如「禁止记满分」「遇到某某句式则忽略」。补丁只能解决孤例，不能解决这类问题，还会让提示词膨胀、互相打架。

个案可以留作**正反例**帮助模型理解原则，但**绝不能代替原则本身**。

自检一句：

> 若再出现措辞不同、但根因相同的新例子，当前改动是否仍然有效？若否，说明仍在打补丁。

---

## 1. 总则

1. **写原则，不写个案黑名单。**（见 §0）
2. **一层一个职责。** 行为策略（《戒律》）、处世准则（《心法》）、工具契约（SYSTEM_PROMPT / Tool schema）、领域抽取（记忆抽取器）分开写，避免同一规则在多处漂移复述。
3. **能确定性做的不要交给模型。** 密钥扫描、路径校验、敏感硬拒等用代码；提示词只表达模型必须做的语义判断。
4. **改提示词要可验收。** 附最小用例或测试意图（什么输入应产出 / 不应产出什么），禁止「感觉更严」的无证据改动；用例应覆盖**根因同类**，不只有原报错句。

---

## 2. 记忆类提示词：稳定跨会话画像（§0 的应用）

编写或修改**任何**写入长期记忆 / 用户画像的抽取提示词时，必须包含下列门槛（表述可润色，语义不可削弱）。三道门槛正交，缺一不可。

### 2.1 关于主人（归属）

**根因层：** 记忆对象是主人稳定画像，不是对话里出现的世界知识。错抽「上海卷 660 分制」的本质不是「分数」，而是**与主人无关的常识被当成了画像**。

**判定口诀（应写进抽取 prompt）**

> 删掉这句话，主人的长期画像是否变少？若不变，就不要记。

### 2.2 耐久性（任务/短期活动 ≠ 画像）

**根因层：** 记忆对象是**跨会话仍成立**的画像，不是当前项目/会话的任务上下文或短期活动排期。错抽「我计划重写 skill，去掉里面的 pi.dev」的本质不是某个专名，而是**阶段性实现意图被当成稳定画像**。

**判定口诀**

> 删掉该句后，跨会话仍成立的「主人是谁 / 怎么协作 / 长期方向」是否变少？若只影响本会话交付或某短期活动阶段，则不要记。

### 2.3 语境保全（禁止去语境泛化）

**根因层：** 若事实只在特定活动/课程/项目/方案下成立，抽成无限定通项会过度概括。错抽「我每周可支配时间不多」而丢掉「相对某学习计划排期」的本质，是**剥掉了使命题为真的限定**。

**判定口诀**

> 删掉限定语境后，这句话是否变成对主人的过度概括？若是，不得以通项形式输出；若补全后仍只绑定短期活动，整条不记。

### 应抽取

- 主人明确自述或可稳定归属的：身份、偏好、跨会话长期方向、工作方式、硬约束
- 主人主动纳入画像的家庭/环境关系（例如「我的孩子有上海户口」）——须是**主人侧关系**，不是百科条目
- 稳定生活/协作节奏（例如「我工作日晚上通常只有约 1 小时可支配」）

### 不应抽取

- 与主人无关的制度、常识、规格、考试规则、新闻、文档摘要等
- 用户提到了数字或专名，但句子未建立「与我 / 我家的稳定关系」
- 把常识改写成第一人称伪自述
- 本会话交付、具体实现步骤、针对某仓库/依赖/文件的阶段性改动计划
- 仅在某课程/活动/项目阶段内成立的时间精力安排；对助手方案的一次性改期/改范围
- 剥掉限定后的通项（例如把「学某课期间时间紧」写成「我每周都没空」）

### 实现要求（输入层）

会话级抽取输入须以用户消息为主，并保留截断后的助手轮次作指代与限定消歧；助手内容不得写成主人自述。

### 正反例（仅作说明，不可当成唯一规则）

| 用户原话 / 情境 | 是否抽取 | 根因归类 |
|---|---|---|
| 是上海卷 660 分制下的 | 否 | 与主人无关的常识 |
| 我孩子高考考了 500 分 | 是 | 关于主人家庭的具体事实 |
| 我计划重写某模块并去掉某依赖 | 否 | 阶段性任务 ≠ 稳定画像 |
| 相对某学习计划说每周时间紧并要求拉长路线图 | 否 | 短期排期 + 禁止去语境通项 |
| 我工作日晚上通常只有约 1 小时可支配 | 是 | 稳定节奏 |
| 我长期做教育科技方向的产品 | 是 | 跨会话长期方向 |

### 开发禁止事项

- **禁止**用关键词黑名单代替上述原则（如禁止记某课程名、某依赖名）
- **禁止**只修某一个错例的 prompt 句子，而不提升到根因原则（见 §0）
- 修改记忆抽取 prompt 后，验收意图须覆盖「常识提及 ≠ 画像事实」「任务提及 ≠ 画像事实」「去语境泛化 ≠ 完整画像事实」这类，而非单句回归

---

## 3. 提示词改动检查清单

提交涉及提示词的改动前自检：

- [ ] 已写明本质根因；改动针对该类问题，不是孤例补丁（§0）
- [ ] 再换一种措辞的同类失败，当前原则仍应挡住
- [ ] 职责落在正确层（戒律 / 心法 / 内置 SYSTEM / 抽取器 / Tool）
- [ ] 与代码硬约束无重复、无矛盾
- [ ] 若动记忆抽取：已体现关于主人 / 耐久性 / 语境保全门槛与口诀
- [ ] 有正反例或测试意图，覆盖根因同类而非仅原句

---

# 二、版本发布

用户说「发布」「打版本」「出 0.x.y」时，**必须按本节执行**，不要另发明流程。版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)；`CHANGELOG.md` 遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## 2.1 产物与标签

发行版来自 **`master` 上的 annotated tag `vX.Y.Z`**（例如 `v0.1.0`）。推送 tag 后，[publish-images.yml](.github/workflows/publish-images.yml) 先跑与 PR 相同的检查，再推送三张 GHCR 镜像：

| 镜像 | 用途 |
|------|------|
| `ghcr.io/cnwinds/lore-chat-backend` | API |
| `ghcr.io/cnwinds/lore-chat-web` | 前端 Nginx |
| `ghcr.io/cnwinds/lore-chat-sandbox-agent` | Work 模式沙箱 Agent |

每个发行版打出：

- **`X.Y.Z`**（如 `0.1.0`）— 用户应锁定的版本
- **`X.Y`**（如 `0.1`）— 同 minor 最新 patch
- **`latest`** — 最新发行版；推送到 `master`/`main` 也会更新 `latest`（滚动预览）

Git 标签带 `v`（`v0.1.0`）；**镜像标签不带 `v`**（`0.1.0`）。这是 Docker 通用约定：git/GitHub Release 用 `v*`，镜像用裸 SemVer。

用户侧锁定方式（预构建启动器 `.env`）：

```bash
LORECHAT_IMAGE_TAG=0.1.0
```

留空或 `latest` 则跟随最新发行 / master 滚动。完整镜像名仍可用 `LORECHAT_BACKEND_IMAGE` / `LORECHAT_WEB_IMAGE` / `SANDBOX_IMAGE` 覆盖。

源码仓库根目录 [`VERSION`](VERSION) 是产品版本的唯一手写来源，必须与即将打的 tag 去掉 `v` 后一致。

## 2.2 何时发、怎么定版本

- **patch**（`0.1.0` → `0.1.1`）：缺陷修复、安全补丁、文档/流程且用户可感知
- **minor**（`0.1.1` → `0.2.0`）：向后兼容的功能
- **major**（`1.0.0` 起）：破坏性变更。`0.x` 期间允许不兼容，但仍用 minor 表达「一批能力」，不要无必要跳 major
- 工作区有未提交改动、不在 `master`、或 `CHANGELOG.md` 的 `[Unreleased]` 为空时，**停止发布**，先问用户

## 2.3 发布清单（按顺序，不可跳）

在仓库根目录操作。**不要** `--no-verify`、**不要** `push --force`、**不要** 改写已推送的 tag、**不要** 把 `knowledge/` / `.env` / 密钥打进提交。

1. **对齐主干**
   ```bash
   git checkout master
   git pull --ff-only origin master
   git status   # 必须干净
   ```
2. **确认版本** `X.Y.Z`（用户指定；未指定则根据 Unreleased 与上次 tag 建议，并征得同意）。
3. **写 `VERSION`**：文件内容一行，仅为 `X.Y.Z`。
4. **写 `CHANGELOG.md`**
   - 把 `[Unreleased]` 下已交付项移到 `## [X.Y.Z] - YYYY-MM-DD`
   - 保留空的 `## [Unreleased]`
   - 文风写用户能感知的变化，不堆文件名
   - 文末 compare / tag 链接改到新版本（见现有格式）
5. **不要**为发版去改 `frontend/package.json` 的 `0.0.0`（那是前端包占位，不是产品版本）。
6. **提交**（仅 VERSION + CHANGELOG；若本次发版还包含流程/CI 改动，可同 commit，但与发版无关的功能必须已经在先前 commit）
   ```bash
   git add VERSION CHANGELOG.md
   git commit -m "$(cat <<'EOF'
   chore(release): X.Y.Z

   EOF
   )"
   ```
7. **打 annotated tag**
   ```bash
   git tag -a "vX.Y.Z" -m "Lore Chat X.Y.Z"
   ```
8. **推送分支与 tag**（tag 推上去才会出版本镜像与 GitHub Release）
   ```bash
   git push origin master
   git push origin "vX.Y.Z"
   ```
9. **等待 CI**：GitHub Actions 工作流 `Publish images`。检查失败则**不要**删 tag 凑合；修代码后发 **patch**。
10. **验收**
    - GitHub Release `vX.Y.Z` 已创建，说明来自 CHANGELOG 该节（工作流自动 `gh release create`；已存在则更新 notes）
    - 三张镜像均可拉：`:X.Y.Z` 与 `:latest`
      ```bash
      docker pull ghcr.io/cnwinds/lore-chat-backend:X.Y.Z
      docker pull ghcr.io/cnwinds/lore-chat-web:X.Y.Z
      docker pull ghcr.io/cnwinds/lore-chat-sandbox-agent:X.Y.Z
      ```
11. **首次把 GHCR 包设为 Public**（否则未登录用户拉不下来）。每个包一次：
    ```bash
    gh api --method PUT -H "Accept: application/vnd.github+json" \
      /user/packages/container/lore-chat-backend/visibility \
      -f visibility=public
    # 对 lore-chat-web、lore-chat-sandbox-agent 各做一次
    ```
    若 API 不可用，让用户在 GitHub → Packages 里把三个容器包 Visibility 改为 Public。

**禁止**：agent 本地 `docker build` 冒充发版；禁止只推 `master` 不打 tag（那样没有 `X.Y.Z` 镜像）；禁止把 git 的 `vX.Y.Z` 原样写成镜像 tag。

## 2.4 发版后用户怎么用

默认一键脚本拉 **`latest`**。锁定发行版：

```bash
# 安装目录下的 .env
LORECHAT_IMAGE_TAG=0.1.0
```

然后 `./lorechat.sh update`（或 `start`）。详见 README「使用发布镜像」。

## 2.5 失败与更正

| 情况 | 做法 |
|------|------|
| 检查没过、tag 已推 | 修 bug，按清单发 **patch**（新 commit + 新 tag），不要 force 改旧 tag |
| CHANGELOG 写错但镜像已出 | patch 更正文档，或 `gh release edit` 只改说明；镜像内容不变则不必重打镜像 tag |
| 发错 major/minor | 发正确的新版本；不要删除已公开的 tag / 镜像 |

## 2.6 发布检查清单（提交 tag 前）

- [ ] 在 `master` 且工作区干净
- [ ] `VERSION` 与 tag `vX.Y.Z`、CHANGELOG 标题 `[X.Y.Z]` 三者一致
- [ ] `[Unreleased]` 已腾空，新节有日期与用户可读条目
- [ ] 未把运行时数据、密钥写入提交
- [ ] 将推送 `master` **和** `vX.Y.Z`
- [ ] 已提醒：镜像 tag 是 `X.Y.Z`，git tag 是 `vX.Y.Z`
