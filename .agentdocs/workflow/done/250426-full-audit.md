# 全模块审计报告

> 状态: 进行中  
> 创建: 2025-04-26

---

## TODO

- [x] a1: Orchestrator 动态路由 + 状态机
- [x] a2: BaseAgent 引擎 + ReAct 循环 + Hook
- [x] a3: 三层记忆系统 (L0/L1/L2) 一致性
- [x] a4: 工具层注册/执行/上下文传递
- [x] a5: Dashboard 事件链路 (EventBus→SSE→前端聚合)
- [x] a6: 协商机制 + 经验进化链路完整性
- [x] a7: 配置常量一致性 + 知识同步
- [x] a8: 测试覆盖度 + 已知失败分析

---

## a1: Orchestrator 动态路由 + 状态机

### 正面
- `ROUTE_TABLE` 覆盖全部 `VALID_STATUSES`，测试已验证完备性
- `_max_route_steps=15` 防死循环，有对应的单元测试
- 支持中途恢复（如 status=撰写中 → 直接从 copywriter 接续）
- 人审门禁特殊路由 `__human_review_gate__` 设计清晰

### 问题

**P1 — ProjectMemory 高频重复实例化**  
`_get_review_threshold`, `_get_review_summary`, `_get_review_red_flag`, `_get_project_review_status`, `_get_review_pass_rate`, `_get_project_name`, `_reconcile_review_pass_rate` 每个方法都 `ProjectMemory(self.record_id)` 单独 new 一次再 `load()`。在 `_handle_reviewer_retries` 循环中，一次 retry 可调 5+ 个 helper，导致大量重复 Bitable API 调用。  
**建议**: 在 `run()` 入口缓存一个 `self._pm`，helper 方法共用；或在需要最新数据时显式 `reload()`。

**P2 — `_get_review_pass_rate` 绕过语义层**  
直接调 `pm._client.get_record(pm._table_id, ...)`，绕过 `ProjectMemory.load()` 的封装。  
**建议**: 通过 `proj.review_pass_rate` 读取，保持数据访问路径一致。

**P3 — `_get_review_threshold` 隐含写入副作用**  
一个 getter 方法内部调 `pm.write_review_summary()`。语义不自洽，调用者无法预期"读阈值"会写数据。  
**建议**: 拆分为纯读 + 独立写入两步。

**P4 — `_handle_reviewer_retries` 绕过动态路由**  
返工时硬编码 `update_status("撰写中")` → `_run_copywriter_fanout()` → `_run_stage_with_agent("reviewer")`，不走 while 循环的路由决策。正常路径和返工路径是两套逻辑。  
**影响**: 如果未来路由表新增状态或角色插入 reviewer 前后，返工路径不会自动适配。  
**建议**: 返工只修改状态 → `continue` 回到 while 循环让路由表决策。

**P5 — `_contains_red_flag()` 为 Dead Code**  
模块级定义了 `_contains_red_flag(text)` 函数（匹配 `REVIEW_RED_FLAG_KEYWORDS`），但实际红线检测用的是 `_get_review_red_flag()` 读结构化字段。该函数未被任何地方调用。  
**建议**: 删除或标注废弃。

---

## a2: BaseAgent 引擎 + ReAct 循环 + Hook

### 正面
- 手写 ReAct 循环 + OpenAI function calling，简洁有效
- `max_iterations` 由 soul.md frontmatter 声明，可配置
- `_hook_reflect` 蒸馏经验 + `_self_write_wiki` 自主沉淀，双路径完整
- 平台补丁 `load_soul_with_platform_patch` 设计巧妙
- `MessageWindow` 保证 system msg 不被裁剪，assistant+tool 成组裁剪

### 问题

**P6 — `_ROLE_NAMES` 三处重复定义**  
`orchestrator.py:44`, `agents/base.py`, `tools/negotiate.py:13` 各自定义了 `_ROLE_NAMES` 字典，内容相同。  
**建议**: 统一到 `config.py` 导出。

---

## a3: 三层记忆系统 (L0/L1/L2)

### 正面
- L0 `MessageWindow`: token 估算 + 滑动窗口裁剪，边界处理好（system msg 保护、tool msg 成组）
- L1 `ProjectMemory`/`ContentMemory`: 字段映射集中在 `config.py`，修改飞书字段不影响业务代码
- L2 `ExperienceManager`: 完整的 save → dedup → merge → wiki write 链路

### 问题

**P7 — ExperienceManager 和 ProjectMemory 中各有 `_safe_float`/`_safe_int` 副本**  
`memory/experience.py:379-390` 和 `memory/project.py` 各自定义了相同的 helper。  
**建议**: 抽到公共 utils。

---

## a4: 工具层注册/执行/上下文传递

### 正面
- `ToolRegistry` 自动扫描 + `SCHEMA`/`execute` 约定，零配置注册
- `AgentContext` 透传 `record_id / project_name / role_id`
- 工具执行异常转字符串返回 LLM，让 ReAct 能自纠
- soul.md `tools:` 白名单过滤注册

### 问题

**P8 — negotiate 工具和 Orchestrator 检查点协商是两套独立链路**  
- `tools/negotiate.py` 是 Agent 主动调用的工具，不走 `NegotiationManager`，也不影响检查点协商
- `orchestrator._run_negotiation_checkpoint` 是 Orchestrator 自动驱动的，走 `NegotiationManager`
- 两者的 `_load_soul_snippet` 和 `_generate_response` / `_broadcast` 逻辑各自实现
- **影响**: Agent 工具级协商的记录不会被 Orchestrator 看到，检查点协商的记录也不会注入 Agent 上下文
- **建议**: 如果需要统一协商语义，应让 negotiate 工具也写入 `NegotiationManager`；如果两者故意独立，应在文档中明确说明。

---

## a5: Dashboard 事件链路

### 正面
- EventBus 进程内发布 → SSE 实时推送，磁盘持久化到 `events.jsonl`
- `fromEvents.ts` 聚合器覆盖全部事件类型，包括 experience.* 7 种事件
- `useEventProcessor.ts` 按事件类型驱动 Zustand store 更新
- 经验进化面板 (`ExperienceEvolution.tsx`) 实时展示漏斗和卡片

### 问题

**P9 — negotiation.* 事件未被前端消费**  
Orchestrator 发布了 `negotiation.started`, `negotiation.message`, `negotiation.response`, `negotiation.completed`, `negotiation.skipped` 5 种事件，但 `fromEvents.ts` 和 `useEventProcessor.ts` 均未处理这些事件。前端看不到协商过程。  
**建议**: 在 `fromEvents.ts` 的 aggregate 函数中添加协商事件聚合，或至少记录到 auditLog。

---

## a6: 协商机制 + 经验进化链路完整性

### 正面
- 协商检查点配置化 (`NEGOTIATION_CHECKPOINTS`)，可通过环境变量关闭
- 经验进化链路完整: Agent 蒸馏 → Orchestrator 打分 → 去重 → 合并 → 双写 (Bitable + Wiki)
- 置信度计算 `_calc_confidence` 四因子（通过率 0.4 + 任务完成 0.3 + 无返工 0.2 + 知识引用 0.1）
- Wiki 写入走 dirty 缓冲 + 升格审批流程

### 问题

**P10 — `_load_soul_snippet` 重复实现**  
`orchestrator.py:565-580` 和 `tools/negotiate.py:178-194` 各自实现了相同逻辑。  
**建议**: 提取到 `agents/base.py` 的 `parse_soul` 附近作为公共静态方法。

**P11 — `_settle_experiences` dedup 按 `role_id` 去重可能丢经验**  
`deduped[item["role_id"]] = item` 只保留每个 role 最后一条。copywriter fan-out 可能产出多条（每平台一条），但 `pending_experiences` 中 role_id 都是 "copywriter"，最终只保留最后一条。  
**建议**: 用 `(role_id, task_filter)` 作为去重 key，或改为只对 card 内容去重。

---

## a7: 配置常量一致性 + 知识同步

### 正面
- 全部字段映射集中在 `config.py`
- 审核阈值按项目类型分型，可扩展
- 知识库 11 层目录 + 双向同步白名单设计严谨

### 问题

**P12 — 无显著配置不一致问题**  
配置层设计良好。唯一值得注意的是 `_ROLE_NAMES` 应该放入 config（见 P6）。

---

## a8: 测试覆盖度 + 已知失败分析

### 覆盖情况

| 模块 | 测试文件 | 类型 | 可 pytest 收集 |
|---|---|---|---|
| 动态路由 | `test_dynamic_routing.py` | pytest+asyncio | ✅ |
| 红线检测 | `test_orchestrator_red_flag.py` | pytest | ✅ |
| 审核策略 | `test_review_policy.py` | pytest | ✅ |
| 协商机制 | `test_negotiation.py` | pytest+asyncio | ✅ |
| Fan-out | `test_copywriter_fanout.py` | 脚本式 | ❌ (conftest 排除) |
| 经验进化 | `test_experience_evolution.py` | ? | ? |
| 人审门禁 | `test_human_review_gate.py` | ? | ? |
| 平台补丁 | `test_platform_patches.py` | ? | ? |
| 升格流程 | `test_promotion_flow.py` | ? | ? |
| Wiki 同步 | `test_wiki_sync_harness.py` | 脚本式 | ❌ (需真实环境) |

### 问题

**P13 — conftest.py 排除了 8 个测试文件**  
`collect_ignore` 排除了 `test_agent.py`, `test_bitable.py`, `test_knowledge.py` 等核心模块的测试。这些都是脚本式测试（`if __name__`），无法被 pytest 收集。  
**影响**: CI 中 `pytest` 命令跑不到这些测试，只能手动运行。  
**建议**: 逐步将脚本式测试迁移为标准 pytest 用例。

**P14 — `test_copywriter_fanout.py` 也是脚本式**  
含 8 个验证，但都不是 `test_` 前缀的标准 pytest 函数（函数虽然叫 `test_xxx` 但是 async 且有自定义 runner），被 conftest 排除。  
**建议**: 添加 `@pytest.mark.asyncio` 装饰器使其可被 pytest 收集。

---

## 总结：按优先级排序的问题清单

| 优先级 | ID | 问题 | 影响 |
|---|---|---|---|
| **HIGH** | P11 | `_settle_experiences` 按 role_id 去重丢 fan-out 经验 | 数据丢失 |
| **HIGH** | P4 | `_handle_reviewer_retries` 绕过动态路由 | 逻辑分叉 |
| **HIGH** | P9 | negotiation.* 事件未被前端消费 | 功能缺失 |
| **MED** | P1 | ProjectMemory 高频重复实例化 | 性能浪费 |
| **MED** | P2 | `_get_review_pass_rate` 绕过语义层 | 封装泄漏 |
| **MED** | P3 | `_get_review_threshold` 隐含写入副作用 | 语义混乱 |
| **MED** | P8 | 工具级与检查点级协商两套独立链路 | 设计模糊 |
| **LOW** | P5 | `_contains_red_flag` Dead Code | 代码杂乱 |
| **LOW** | P6 | `_ROLE_NAMES` 三处重复 | DRY 违反 |
| **LOW** | P7 | `_safe_float/_safe_int` 重复 | DRY 违反 |
| **LOW** | P10 | `_load_soul_snippet` 重复实现 | DRY 违反 |
| **LOW** | P13-14 | 脚本式测试无法被 pytest 收集 | CI 覆盖不足 |
