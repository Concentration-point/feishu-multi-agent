# 阶段六代码审查报告

审查范围仅包含以下阶段六新增或修改文件：

- `agents/base.py`
- `memory/experience.py`
- `orchestrator.py`
- `tools/get_experience.py`
- `tests/test_experience.py`
- `config.py`

说明：

- 本次为静态代码审查，不跑测试。
- 结论按模块组织。
- 所有必须修复项均给出修复建议，但不直接改代码。

## agents/base.py

- `Hook` 方法存在且为 `async`
- `_pending_experience` 已在 `__init__` 初始化为 `None`
- `Hook` 调用位置正确，在 ReAct 循环结束后、`return` 之前
- `Hook` 失败不会影响 `run()` 正常返回，外层有兜底
- `Hook` 的 LLM 调用没有带 `tools` 参数
- JSON 解析有 `try/except`，失败返回 `None`
- 原有 ReAct 主循环整体还在，没有被意外大改

问题：最终没有工具调用的那条 `assistant` 消息没有 append 回 `messages`，所以 `_hook_reflect()` 拿到的不是完整 ReAct 历史，会漏掉最终回答。
建议：在 `final_output = message.content or ""` 前先追加 `messages.append(message.model_dump())`。

注意：`_hook_reflect()` 只对 `applicable_roles` 做了补丁，没有对 `category/situation/action/outcome/lesson` 做 schema 校验或默认值收口。
建议：补一层字段规范化，`category` 非法时回退 `"未分类"`，其余字段缺失时回退空串。

## memory/experience.py

- `ExperienceManager` 类存在
- `save_experience()` 使用了 `FIELD_MAP_EXPERIENCE`，字段映射方向正确
- `save_to_wiki()` 写入路径是 `knowledge/wiki/{category}/`
- 不存在的目录会自动创建
- `_index.md` 会更新
- `query_top_k()` 排序公式正确：`confidence * (1 + log(use_count + 1))`
- `use_count = 0` 的情况不会报错
- 命中后会更新使用次数 `+1`
- `check_dedup()` 的过滤条件是“同角色 AND 同分类”
- `merge_experiences()` 确实调了 LLM
- 经验池表未配置时，`query_top_k()` 会返回空列表，不会崩

问题：`save_to_wiki()` 的文件名和目录名清洗不够，只替换了 `/`、`\` 和空格，没处理 `: * ? " < > |`、`..`、末尾点号等非法字符，也没防 `category` 路径穿越。
建议：对 `category` 和 `filename` 用 allowlist 清洗，只允许字母、数字、下划线、短横线和有限中文。

问题：`save_to_wiki()` 没有更新 `.sync_state.json` 的 `dirty` 标记，不符合设计预期。
建议：在 `knowledge/.sync_state.json` 中写入 `dirty=true` 和更新时间。

问题：`merge_experiences()` 没有删除旧条目，只是把旧记录 `confidence` 置 `0` 并改内容，属于软删除伪装。
建议：补真删除；如果要保留归档，也至少单独做归档字段，不要伪装成删除。

问题：`check_dedup()` 不会排除这些“已合并但未删除”的旧记录，后续去重会不断把 `[已合并]` 垃圾记录卷进去。
建议：真删除旧记录；在没补删除前，至少过滤掉 `confidence <= 0` 的条目。

注意：`query_top_k()` 的使用次数更新是逐条 `update_record()`，不是批量更新。
建议：如果后续量会上来，补批量更新接口。

注意：`merge_experiences()` 对 LLM 返回值没有做 markdown code fence 清洗，也没有 JSON fallback。
建议：和 `_hook_reflect()` 一样，先清洗再解析。

注意：`save_to_wiki()` 每次全量重写 `_index.md`，没有锁；并发跑两条流水线时存在覆盖风险。
建议：至少在本地文件层加锁，或者接受该风险并写进注释或文档。

## orchestrator.py

- 在流水线循环中有收集 `agent._pending_experience`
- `_settle_experiences()` 是在整条流水线跑完后统一调用，不是每个 Agent 跑完就沉淀
- `_calc_confidence()` 公式写对了
- 审核通过率是从 Bitable 读取的，不是硬编码
- 阈值过滤和去重阈值都走了 `config.py`
- 双写都有调，`save_experience + save_to_wiki` 都在
- 沉淀报告日志有打印

问题：最终广播直接格式化 `pass_rate:.0%`，如果 `_get_review_pass_rate()` 返回 `None`，整个 orchestrator 会在全部阶段跑完后崩掉。
建议：广播前先把 `None` 兜底成 `0.5` 或 `"未知"`。

问题：审核通过率字段为空时，现在给的是 `0.0`，不是更合理的中性兜底 `0.5`；这样会把 reviewer 失败或字段缺失场景误判成“极差经验”。
建议：区分“字段缺失”和“字段真实为 0”。

问题：`task_completed` 被硬编码成 `True`，没有真实判断依据。
建议：至少结合 `StageResult.ok`、`agent.run()` 是否有最终输出，或必填字段是否已写回主表来判断。

问题：`knowledge_cited` 被硬编码成 `False`，这条评分分支现在是死的。
建议：基于 `agent._messages` 检查是否实际调用过 `search_knowledge` 或 `get_experience`。

问题：驳回重试场景下，会把初版和返工后的 `copywriter/reviewer` 经验全部追加到 `pending_experiences`，最后统一沉淀时可能沉淀多份重复经验。
建议：明确策略，只保留最终有效版本，或者给每次尝试打 `attempt_no/final_effective` 标记后再沉淀。

注意：`no_rework` 现在是按全局 `self.reviewer_retries` 粗算的，只要有过返工，所有 `copywriter` 经验都算“有返工”，粒度偏粗。
建议：按单次 card 对应的 attempt 判断，而不是全局布尔。

注意：`_settle_experiences()` 对单条经验的双写没有独立兜底，`save_to_wiki()` 一次异常就会打断后续沉淀。
建议：每条经验单独 `try/except`，失败写日志继续。

## tools/get_experience.py

- `SCHEMA` 符合 OpenAI function calling 规范
- 参数里有 `role_id` 必填、`category` 可选
- `execute()` 调用了 `ExperienceManager.query_top_k()`
- 返回是人类可读文本，不是原始 JSON
- 无结果时有友好提示，不是空字符串或异常

## BaseAgent prompt 装配 / 经验注入

- `run()` 在 prompt 装配阶段已经通过 `ExperienceManager.query_top_k()` 取历史经验，不需要额外走工具调用
- 注入顺序正确：`shared -> soul -> 项目上下文 -> 历史经验`
- 经验池为空时返回空串，prompt 装配不会报错
- 注入格式清晰，按序号和分类输出

## tests/test_experience.py

- 文件有直接运行入口，`python tests/test_experience.py` 可作为脚本入口
- 第一层本地测试存在，理论上不依赖飞书凭证
- `LLM_API_KEY` 和 `EXPERIENCE_TABLE_ID` 都有跳过逻辑
- 模块导入路径处理正确

问题：文档里写了“三层测试”，但这个文件根本没有第三层“两次流水线对比”的实现，`main()` 只跑了四个测试函数。
建议：补真实第三层，至少包含“两次运行前后 get_experience/提示词注入差异”的对比报告。

问题：第二层跳过逻辑只检查 `EXPERIENCE_TABLE_ID`，没有检查 `FEISHU_APP_ID/FEISHU_APP_SECRET/BITABLE_APP_TOKEN`，半配置状态会误入真实调用。
建议：统一做前置配置检查，缺任一关键项都 `skip + exit 0`。

问题：`get_experience` 工具验证分支写坏了，成功和失败两边都 `report.ok()`，这个断言永远不会失败。
建议：失败分支改成 `report.fail()`。

问题：`test_wiki_write()` 直接写真实 `KNOWLEDGE_BASE_PATH`，清理时还 `rmtree()` 整个 `knowledge/wiki/电商大促/` 目录，这会误删真实知识库内容。
建议：改到临时目录跑，或至少给测试用专属 category 前缀，不要删真实分类目录。

问题：Bitable 测试会创建真实经验记录，但没有清理逻辑，也没有“已保留可手动删除”的提示。
建议：要么补删除，要么在报告里打印 `record_id` 并明确保留策略。

## 配置与基础设施

- `config.py` 已新增 `EXPERIENCE_TABLE_ID / EXPERIENCE_CONFIDENCE_THRESHOLD / EXPERIENCE_MAX_PER_CATEGORY / EXPERIENCE_TOP_K`
- `FIELD_MAP_EXPERIENCE` 已补上
- `requirements.txt` 看下来不需要新增依赖，现有 `httpx/python-dotenv/openai` 足够

问题：`.env.example` 只加了 `EXPERIENCE_TABLE_ID`，漏了 `EXPERIENCE_CONFIDENCE_THRESHOLD / EXPERIENCE_MAX_PER_CATEGORY / EXPERIENCE_TOP_K`。
建议：把三个配置项和默认值一起补进示例文件。

问题：`memory/__init__.py` 没有导出 `ExperienceManager`。
建议：显式导出，保持 `memory` 包 API 一致。

问题：`feishu/bitable.py` 目前只有 `create/batch_create/update`，没有 `delete_record` / `batch_delete_records`。
建议：补删除接口；否则经验合并、测试清理都会继续写旁路代码或做软删除假动作。

## 汇总

- 必须修复的问题：16 个
- 建议改进的问题：5 个
- 检查通过的项目：31 个

## 优先级建议

建议先修这四类，再考虑跑阶段六测试：

1. `Hook` 历史不完整
2. 经验合并不真删
3. `orchestrator` 评分依赖硬编码或兜底不稳
4. `tests/test_experience.py` 会误删真实 wiki 内容

这些不收口，阶段六的“经验沉淀 / 自进化”会越跑越脏。
