# 全链路 API 测试诊断报告

**测试时间**: 2026-05-02 21:48 ~ 22:15 (约 27 分钟)
**场景**: 电商大促（某护肤品牌·玻尿酸精华液）
**record_id**: `recviteEZuMgCB`
**LLM**: gpt-5.4-mini (api.luhengcheng.top)
**模式**: AUTO_APPROVE_HUMAN_REVIEW=true

---

## 一、流水线执行摘要

| # | 阶段 | 角色 | 结果 | 耗时 | 备注 |
|---|------|------|------|------|------|
| 1 | Brief 解读 | account_manager | ✅ OK | ~2m | 5 轮 ReAct |
| 2 | 人审门禁 | __human_review_gate__ | ✅ 跳过 | <1s | AUTO_APPROVE |
| 3 | 内容策略 | strategist | ✅ OK | ~2m | 7 轮，创建 6 条排期行 |
| 4 | 文案撰写 | copywriter (fan-out×3) | ⚠️ 截断 | ~15m | 达 max_iterations=14 |
| 5 | 审核 | reviewer | ⚠️ 缺工具 | ~3m | submit_review 不可用 |
| 6 | 排期交付 | project_manager | ❌ 失败 | <1s | 交接校验失败: review_summary 为空 |

**最终项目状态**: 排期中（但 PM 交接校验失败，未真正完成排期）

---

## 二、项目产出数据

- **Brief 解读**: 1575 字 ✅
- **策略方案**: 1480 字 ✅
- **审核总评**: 0 字 ❌（submit_review 未被调用导致）
- **交付摘要**: 0 字 ❌
- **审核通过率**: 63.6% (7/11)
- **内容行**: 11 条（含历史重名项目残留 5 条），全部有成稿
  - 公众号长文 × 4（稿长 2312~2973 字）
  - 小红书种草 × 4（稿长 1143~1184 字）
  - 抖音口播 × 3（稿长 664~674 字）

---

## 三、工具调用统计

| 工具 | 总数 | 成功 | 失败 | 成功率 | 平均耗时 | 最大耗时 |
|------|------|------|------|--------|----------|----------|
| write_content | 72 | 72 | 0 | 100% | 10.9s | 30.1s |
| send_message | 12 | 12 | 0 | 100% | 3.6s | 6.1s |
| search_reference | 10 | 10 | 0 | 100% | 10ms | 12ms |
| read_project | 7 | 7 | 0 | 100% | 5.5s | 11.7s |
| search_knowledge | 7 | 7 | 0 | 100% | 3ms | 5ms |
| list_content | 5 | 5 | 0 | 100% | 4.9s | 6.6s |
| read_knowledge | 4 | 4 | 0 | 100% | 2ms | 2ms |
| update_status | 3 | 3 | 0 | 100% | 6.6s | 7.8s |
| write_project | 2 | 2 | 0 | 100% | 4.2s | 4.3s |
| search_web | 2 | 2 | 0 | 100% | <1ms | <1ms |
| write_wiki | 6 | 6 | 0 | 100% | 44ms | 61ms |
| batch_create_content | 1 | 1 | 0 | 100% | 4.1s | 4.1s |
| ask_human_batch | 1 | 1 | 0 | 100% | 16.4s | 16.4s |
| **unknown** | **190** | **0** | **190** | **0%** | 0ms | 0ms |

**LLM Token 总消耗**: ~1,523,064 tokens

---

## 四、发现的关键问题 (按优先级排序)

### 🔴 P0: reviewer 白名单缺少 submit_review

**现象**: 审核 Agent 在 post-validation 反复提示缺少 `submit_review`，Agent 回复"当前会话可用工具列表中没有这个工具"。

**根因**: `agents/reviewer/soul.md` 的 `tools:` 白名单中**没有** `submit_review`，但 `agents/base.py:_REQUIRED_TOOL_CALLS` 要求 reviewer 必须调用它。矛盾导致：
1. LLM 看不到该工具的 schema，无法调用
2. post-validation 注入补全指令后 LLM 仍无法调用（工具不存在）
3. `review_summary` 为空 → PM 交接校验失败

**修复**: 在 `agents/reviewer/soul.md` 的 `tools:` 列表添加 `submit_review`。

---

### 🔴 P1: 项目名称碰撞导致内容行混淆

**现象**: 策略师创建了 6 条内容行，但诊断报告显示 11 条。`list_records filter=CurrentValue.[关联项目]="某护肤品牌" count=11`。

**根因**: 多次测试使用相同的 `client_name="某护肤品牌"`，Bitable 按项目名关联内容行，导致历史残留数据混入当前项目。

**修复建议**:
1. demo 脚本自动追加时间戳到 client_name（如 `某护肤品牌_0502`）
2. 或 ContentMemory 增加 record_id 维度过滤

---

### 🟡 P2: 文案 Agent 迭代效率低，写回过多

**现象**: write_content 被调用 72 次（平均 11s/次），3 个平台子 Agent 均达到 max_iterations=14 被截断。

**根因分析**:
1. 文案 Agent 对同一 record_id 重复写 `draft_content` 和 `word_count`（每条内容至少 4~6 次写回）
2. 因混入了历史残留行（P1），Agent 在处理超出分配范围的行
3. post-validation 要求补调 `search_reference` / `search_knowledge`，额外消耗迭代轮数

**优化建议**:
1. `write_content` 支持批量字段更新（draft + word_count 一次写完）
2. 在 user prompt 中更明确地限制只处理分配的 record_id
3. 考虑将 search_reference/search_knowledge 提前到 fan-out 调度层预执行

---

### 🟡 P3: ask_human_batch 在非 server 模式下不可用

**现象**: 客户经理调用 `ask_human_batch` 时返回"card_actions 未初始化，请在 lifespan 中调用 set_main_loop()"。

**根因**: `ask_human_batch` 依赖 FastAPI webhook 回调机制，CLI 模式下无 HTTP 服务。

**影响**: 客户经理无法向客户追问澄清问题（5 个问题全部失败）。Brief 解读可能缺少关键信息。

**修复建议**: ask_human_batch 降级处理 — 非 server 模式下自动跳过，写入日志标记"客户澄清不可用"。

---

### 🟡 P4: search_web 返回空结果

**现象**: 策略师调用 2 次 `search_web`，但日志显示"外部竞品网页检索受 API 限制，未获取到最新网页情报"。

**根因**: Tavily API 可能未配置或配额耗尽（`search_web` 耗时 <1ms 说明可能直接返回了空）。

---

### 🟢 P5: 190 条 "unknown" 工具调用记录

**现象**: `tool_calls.jsonl` 中 190 条 `tool="unknown"` 且全部失败。

**根因**: 这些是历史运行残留的异常记录（可能来自 cost_tracker 而非 ToolRegistry），record_id 恰好匹配。

**修复**: 诊断脚本在统计时排除 `tool="unknown"` 的记录。

---

## 五、优化升级建议

### 立即修复（本次可做）

1. **`agents/reviewer/soul.md` 添加 `submit_review` 到工具白名单** — 根因修复
2. **demo 脚本 client_name 去重** — 追加时间戳或随机后缀

### 短期优化

3. **write_content 批量字段更新** — 减少 API 调用次数（72→~20）
4. **ask_human_batch 非 server 模式降级** — 明确返回"跳过"而非报错
5. **文案 fan-out 预加载知识** — search_reference/search_knowledge 移到调度层执行一次，结果注入子 Agent prompt

### 中期优化

6. **Token 预算管控** — 单次流水线 152 万 token 偏高，可对文案子 Agent 设更严格的 max_iterations (8~10)
7. **内容行关联加固** — ContentMemory 增加 project_record_id 字段，替代按项目名匹配
8. **Orchestrator 交接校验增加降级策略** — review_summary 为空时从 write_content 的 review_feedback 中聚合生成

---

## TODO

- [x] 运行全链路诊断测试
- [x] 记录分析日志和 Agent 回复
- [ ] 修复 P0: reviewer soul.md 添加 submit_review
- [ ] 修复 P1: demo client_name 去重
- [ ] 评估并实施短期优化
