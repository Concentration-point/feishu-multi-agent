# 知识沉淀链路诊断报告

> 诊断日期：2026-04-17
> 诊断范围：`Agent 自省 → 本地 wiki → .sync_state.json → 后台同步 → 飞书知识空间 → 下次项目复用` 全链路 10 环节
> 方法：纯静态代码核对 + 物证对账，不改代码、不跑流水线

## 链路状态总览

| 环节 | 状态 | 说明 |
|------|------|------|
| 1. Hook 自省 | ✅ | `agents/base.py:405` ReAct 结束后调 `_hook_reflect`；按 role_id 分化 prompt（默认 + account_manager/reviewer/copywriter 3 个专用）；LLM 调用 `with_tools=False`（line 479）；JSON 解析外包 try/except（line 512-514）；成功时暂存 `self._pending_experience`（line 407） |
| 2. 写入本地 wiki | ✅ | `tools/write_wiki.py` 真实实现；落盘 `knowledge/wiki/{category}/{title}.md`（line 153-155）；`cat_dir.mkdir(parents=True, exist_ok=True)`（line 161）；统一 frontmatter（created/source/category/role/confidence）；写完更新 `_index.md`（line 172） |
| 3. 写入触发点 | ✅ | **三重保险**：① Agent 在 ReAct 中自己调 write_wiki（5 个 soul.md 均声明了该工具）；② `base.py:413` Hook 后 `_self_write_wiki` 兜底；③ `orchestrator.py:428-429` Agent 未写时由 `em.save_to_wiki` 再兜底 |
| 4. search_knowledge 搜 wiki | ✅ | `tools/search_knowledge.py:75` 从 `KNOWLEDGE_BASE_PATH` 根起 `rglob("*.md")`（line 34），自动覆盖 `raw/` + `wiki/` + `references/` |
| 5. read_knowledge 读 wiki | ✅ | `tools/read_knowledge.py:35-36` 以 `KNOWLEDGE_BASE_PATH` 为基 resolve 任意相对路径；路径穿越校验齐全；不限定子目录 |
| 6. dirty 标记 | ✅ | `write_wiki.py:62-89` mark_dirty 统一 schema `{hash, dirty, updated_at}`；文件写入后对 md 本体 + `_index.md` 各标记一次（line 175-177） |
| 7. 异步同步线程 | ✅ | `sync/wiki_sync.py` 完整实现；`start()` 无限循环（line 36）、`sync_once()`、`trigger()` 手动触发、`_find_dirty_files` 同时识别 dirty/新文件/hash 变更；成功后追写 `synced_at` 并清 dirty（line 78） |
| 8. 同步线程启动 | ✅ | `main.py:137-139` FastAPI startup 自动拉起；CLI `run` 前 `_start_background_sync()`、流水线结束 `_trigger_sync_once()`（line 114/119）；webhook 触发后同样 `_trigger_sync_once`（line 457） |
| 9. feishu/wiki.py | ✅ | `list_nodes` / `find_node_by_title` / `create_node` / `update_doc_content` 全部真实；带 5 分钟节点缓存；`update_doc_content` 走「清空→重写」覆盖策略 |
| 10. 下次项目复用 | ✅ | `base.py:291` `_load_experiences` → Bitable 查 top-K 注入 system prompt（line 576-580）；5 个 soul.md 的 tools 列表均含 `search_knowledge`，ReAct 中可主动搜 wiki |

---

## 链路断裂点

**没有硬断裂（❌）。** 10 个环节全部有代码落点和真实实现，端到端链路跑得通。

---

## 已通过但有隐患的环节（⚠️）

### ⚠️ 隐患 1：wiki 文件命名策略粗糙 → 近重复文件泛滥

- **证据**：`base.py:535` 用 `f"{self.role_id}_{lesson[:20]}"` 作为文件名。`knowledge/wiki/电商大促/` 下出现高度相似的条目堆积：
  - `reviewer_下次文案在撰写这类内容前必须先检查：1)` / `reviewer_下次文案在撰写这类内容前必须先检查：1）` / `reviewer_下次文案在撰写这类内容前，必须先检查：1` — 三条仅标点差异
  - `copywriter_...` 前缀相似的条目 7 条、`strategist_...` 相似条目 5 条
- **影响**：wiki 体积虚胖，search_knowledge 命中含糊，Agent 读到的经验高度冗余。闭环跑得通但颗粒度失控。
- **建议**：`ExperienceManager.check_dedup` 和 `merge_experiences` 已具备合并能力（`experience.py:230-299`），但合并阈值 `EXPERIENCE_MAX_PER_CATEGORY` 看上去未有效触发。排查合并入口是否在 Orchestrator 的 `_settle_experiences` 真的被走到，或降低阈值。

### ⚠️ 隐患 2：5 条早期 dirty 记录卡在未同步状态

- **证据**：`.sync_state.json` 第 2-26 行 5 条记录 `dirty: true`，`updated_at` 停留在 `2026-04-15T19:39:49`；而 `2026-04-16` 之后写的记录 `synced_at` 均已回填。
- **影响**：这 5 条经验只在本地、飞书知识空间看不到；答辩时如果演示「本地 wiki → 飞书」一致性，会被戳穿。
- **可能原因**：写入时 `WIKI_SPACE_ID` 未配置 / 飞书 API 那一瞬间故障 / 文件名含特殊字符被飞书拒绝。建议启动一次 `python main.py sync` 看日志哪几条抛 FeishuAPIError。

### ⚠️ 隐患 3：sync 扫描范围吞掉 `raw/` 和 `references/`

- **证据**：`wiki_sync.py:110` 全仓扫描 `self._base_path.rglob("*.md")`；`_map_node_path` 对 `raw/*` 映射到「历史方案」节点、`references/*` 会落到「其他」节点（line 181-183）。
- **影响**：如果 `references/` 目录是后加的对标素材（ls 显示有 小红书/公众号/抖音/ 子目录 + README），这些也会被推到飞书「其他」节点下，可能超出你对飞书知识空间的设计预期。
- **建议**：确认 references/ 是否要对外同步；不要的话在 `_find_dirty_files` 加目录黑名单。

### ⚠️ 隐患 4：wiki 已收录分类只有「电商大促」一个

- **证据**：`ls knowledge/wiki/` 只有「电商大促」子目录。
- **影响**：Hook 蒸馏的 category 强制落在「电商大促/新品发布/品牌传播/日常运营」四选一（base.py:493），但只跑过电商大促 Brief；「新品发布」等类型 Agent 当前零经验。不是 bug，是 Demo 覆盖面问题。
- **建议**：Demo 演示前至少跑一次「新品发布」Brief 产生第二个分类，让飞书知识空间看起来是持续扩张的「活的企业大脑」。

### ⚠️ 隐患 5：frontmatter 的 `category` 字段会被 search 命中

- **证据**：`write_wiki.py:125-135` 写入的 frontmatter 含 `category: 电商大促`；`search_knowledge.py` 对整个文件内容做不区分 frontmatter 的子串匹配。
- **影响**：搜「电商大促」会命中全部 wiki 文件的 frontmatter（而不是真正讨论电商大促的内容），排序失真。
- **建议**：search 时跳过 frontmatter，或搜正文前剥离。

---

## 端到端验证结果

**未执行跨项目运行级验证**（需要 LLM key + 飞书凭证真实触发流水线，不适合本次诊断范围）。

仅做了静态物证核对：
- `ls knowledge/wiki/电商大促/` 列出 28 个 wiki .md，`.sync_state.json` 有 34 条记录（含 `_index.md` + 5 条上述未同步项），数量对应；
- `_index.md` 头部和实际文件列表一致，更新链路通；
- 5 个 soul.md 均含 `search_knowledge` + `read_knowledge` + `write_wiki` 工具声明，下次项目复用通路闭环；
- `.env` 中 `WIKI_SPACE_ID=7629425490247289814` 已配置，同步线程不会被 `if not self.space_id: return`（wiki_sync.py:52）短路掉。

---

## 修复优先级

1. **[一般-可上 Demo] 清一下 5 条卡死的 dirty 记录**
   - 跑 `python main.py sync` 看具体报错；无法同步的话手动把 `.sync_state.json` 中对应 entry 的 hash 改成当前文件真实 hash，让下次扫描作为「hash 变了」重推一次，或删掉 entry 当新文件处理。

2. **[一般] wiki 文件重名合并**
   - 验证 `_settle_experiences` 里 `check_dedup` 的 `EXPERIENCE_MAX_PER_CATEGORY` 阈值是否真的触发到 `merge_experiences`；或补一个「同 role + 同 category + 前 10 字相同」的文件级合并钩子。

3. **[一般] Demo 前种一条非电商大促 wiki**
   - 让知识空间出现「新品发布」/「品牌传播」等第二分类，讲「持续增厚的企业大脑」才立得住。

4. **[可延后] references 目录同步策略**
   - 决定是否推到飞书；不推就在 `_find_dirty_files` 加目录过滤。

---

## 结论

底层逻辑通了，10 环节零硬断裂，闭环跑得顺。颗粒度上有 5 个⚠️，均为"能上 Demo 但不 owner"的优化项，不影响链路可用性。
