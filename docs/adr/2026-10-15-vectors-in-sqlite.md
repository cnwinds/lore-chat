# ADR 2026-10-15：向量存进 partitioned.db，去掉 Chroma

## 状态

已采纳（2026-10-15）。取代 [ADR 2026-09-29 分区检索底座](2026-09-29-partitioned-retrieval.md) 中「向量在 `vec/` 目录下另开集合」「嵌入按模型分集合」的存储部分，以及 [ADR 2026-09-29 文档库与会话迁入](2026-09-29-kb-conversation-retrieval-migration.md) 第 5、7 条中与 Chroma 相关的部分。分区、对账、降级、按模型重嵌等语义不变。

## 背景

分区检索底座把向量放在 Chroma 0.5（`.kb/index/vec/`），每 (族, 模型) 一个集合。线上实例（约 3400 条、1024 维）实测：

- **内存**：导入 chromadb 约 66 MB，打开客户端并查询三个集合再加约 48 MB；嵌入走外部 API，chromadb 带进来的 onnxruntime、tokenizers 等用不上。
- **镜像**：只被 chromadb 依赖的包 56 个、约 260 MB（kubernetes 111 MB、onnxruntime 64 MB、grpcio 17 MB 等），占后端镜像 884 MB 的近三成。
- **磁盘与备份**：`chroma.sqlite3` 89 MB，真正的向量约 14 MB；其余是 Chroma 自存的正文、元数据、自带全文索引与写入队列，与 `partitioned.db` 重复，且随备份一起打包。
- **两套存储的一致性**：清单在 `partitioned.db`、向量在 Chroma，写入分两步，失败要靠回表、重试兜底；删除要先收集「待删向量」再跨库删。
- **绕路代码**：`chroma_repair.py`（修 0.5 的 `max_seq_id` 类型）、每线程一个客户端的 `ThreadLocalChroma`、导入备份前释放 Chroma 文件锁、`posthog` 版本钉。
- **过滤不精确**：范围条件与组前缀 Chroma 做不了，只能多取 8 倍候选再在内存里过滤，仍可能取不够。
- **升级成本**：Chroma 1.x 换了存储格式，继续用也要再迁一次。

同规模基准：向量以 BLOB 存进 SQLite，按 SQL 过滤后分批读出、numpy 精确计算余弦，约 12 ms/次，峰值多占约 5 MB；Chroma 首次查询 30–180 ms。

## 决策

1. **向量存进 `partitioned.db`。** 新表 `vectors(partition, item_id, family, model, vec)`，主键 `(partition, item_id)`，每个条目只存当前一份向量。`vec` 是 L2 归一化后的 float32 小端字节串，余弦即点积。与 `items` 同库同事务：标记嵌入完成与写入向量一起提交，删除、改文本时在同一事务里删掉向量，不再有跨库不一致。
2. **查询先过滤后精算。** 分区、族、当前模型、元数据过滤（eq / ne / in / gte / lt）、组前缀全部在 SQL 里过滤，再分批读出向量，用 numpy 精确计算并保留前 k 个。结果是精确最近邻，不再多取候选，也不常驻向量矩阵。
3. **换模型就地覆盖。** 只有 `model` 等于当前活动模型的向量参与查询；后台重嵌时直接覆盖该条目的向量，不再有「旧集合清空即删」。
4. **存量迁移靠重嵌，不读 Chroma。** Chroma 0.5 的向量在 HNSW 二进制文件里，不装 chromadb 读不出。启动时把「标记已嵌入、但 `vectors` 里没有对应向量」的条目改回待补，由后台限流重嵌；重嵌完成前该部分只走全文（ADR 2026-09-29 既有降级）。旧版迁移（`legacy_migration`）只保留从真相重建全文，不再沿用旧向量。
5. **旧向量目录直接删除。** 构建索引子图时删除 `.kb/index/vec/`。索引是派生投影（ADR 2026-09-29 第 2 条），删除不丢真相。导入旧备份后同样删除并重嵌。
6. **依赖。** 移除 `chromadb` 与为它加的 `posthog` 版本钉，显式依赖 `numpy`。`pysqlite3-binary` 保留：FTS5 / fts5vocab 仍需较新的 SQLite。

## 规模上限与退路

线性扫描的耗时与参与查询的条数成正比：约 3400 条 12 ms，估计 1 万条约 35 ms、5 万条约 180 ms。查询在线程里执行，有向量截止时间，超时降级为只用全文，所以变慢表现为向量通道超时、召回变差，不会卡住回合。

现在约 3400 条，10 月以来每两周新增约 300 条。出现以下任一情况时再评估：

- 向量通道 `timeout` 明显增多；
- 单族参与查询的条数超过约 5 万。

退路依次是：向量量化（float16 / int8，读取量减半或更少）；SQLite 内的近似最近邻扩展（如 sqlite-vec）。两者都不改变本 ADR 的接口与存储位置。

## 后果

- 依赖体积减少约 280 MB（site-packages 695 MB → 416 MB）；导入后内存 140 MB → 104 MB，另省去 Chroma 客户端与集合缓存的运行时内存（约 48 MB）；`.kb/index/` 与备份体积减少约 75 MB。
- 升级后一次性重嵌全部条目，费用与首次建索引相同；重嵌期间向量召回逐步恢复。
- 删除 `chroma_client.py`、`chroma_repair.py`、`adopt_vectors` 与旧 Chroma 迁移测试。
- 没迁移过旧栈的实例升级后同样从真相重建全文、后台重嵌，不再沿用旧向量。
