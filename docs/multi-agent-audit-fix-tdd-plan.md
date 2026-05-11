# 多 Agent 审计待修复清单与 TDD 计划

> 状态：待开发前评审
> 范围：本文件只定义待修复问题、期望结果、测试脚本和验收标准，不包含生产代码改动。
> 原则：先写测试，确认测试失败且失败原因符合预期，再实现修复，最后跑测试到通过。

## 目标结果

本轮修复的目标不是增加新功能，而是把现有多 Agent 流水线从“提示约束 + 事后警告”提升为“关键风险强门禁”：

1. 红线风险必须硬中止，不能进入排期和交付。
2. Agent 必调工具缺失必须让阶段失败，不能只追加警告文本。
3. 状态流转权必须收敛到编排层，尤其是 copywriter fan-out 子 Agent 不能提前推进状态。
4. webhook 配置了 token 时必须强制鉴权，缺 token 也不能放行。
5. 人审门禁、Plan-Verify、handoff 等关键校验读取失败时应 fail closed。
6. webhook 去重不能永久阻断同 record_id 后续断点续跑。

## 修复任务清单

### P0-1 红线风险必须硬中止

当前风险：

- reviewer 后置逻辑检测到 `review_red_flag` 后只打印警告。
- 达到最大返工次数后仍可能强制进入“排期中”。
- 最终 `pipeline.completed` 判定没有纳入红线字段。

期望行为：

- 只要项目级 `review_red_flag` 非空且不等于“无”，流水线必须中止。
- 中止时不得进入“排期中”或“已完成”。
- 应发布明确的 aborted/rejected 事件，并保留红线原因。

建议测试文件：

- `tests/test_pipeline_red_flag_tdd.py`

建议测试用例：

- `test_red_flag_blocks_scheduling_even_when_pass_rate_is_high`
- `test_red_flag_blocks_force_advance_after_max_retries`
- `test_red_flag_marks_pipeline_aborted_not_completed`

验收标准：

- 红线存在时不会调用 `ProjectMemory.update_status("排期中")`。
- 红线存在时最终 verdict 不是 completed。
- 红线原因能从事件或项目字段中追溯。

### P0-2 reviewer 红线写入路径必须结构化

当前风险：

- `submit_review` 只写内容行审核状态和反馈。
- reviewer 没有 `write_project` 白名单，无法稳定写入项目级 `review_red_flag`。
- Orchestrator 依赖项目级红线字段，但该字段缺少可靠来源。

期望行为：

- 行级审核命中严重规则后，系统能汇总生成项目级 `review_red_flag`。
- 项目级红线来源应来自结构化数据，而不是 reviewer 自由文本总结。

建议测试文件：

- `tests/test_pipeline_red_flag_tdd.py`

建议测试用例：

- `test_submit_review_rejected_rule_can_be_reconciled_to_project_red_flag`
- `test_project_red_flag_does_not_depend_on_review_summary_keywords`

验收标准：

- reviewer 逐行提交严重违规后，项目级红线字段可被 Orchestrator 读到。
- 旧的 `review_summary` 关键词不再作为唯一红线来源。

### P1-1 必调工具缺失必须导致阶段失败

当前风险：

- BaseAgent 的 post-validation 最终仍缺工具时，只在输出中追加警告。
- Orchestrator 只要 `agent.run()` 正常返回，就把阶段标记为成功。

期望行为：

- 必调工具缺失或必调工具全部失败时，Agent 结果必须结构化暴露失败。
- Orchestrator 接收到缺工具结果时，阶段 `ok=False`。
- reviewer 未逐行覆盖 `submit_review` 时必须失败。

建议测试文件：

- `tests/test_agent_required_tools_tdd.py`

建议测试用例：

- `test_base_agent_returns_failure_when_required_tools_still_missing`
- `test_orchestrator_marks_stage_failed_when_required_tools_missing`
- `test_reviewer_missing_submit_review_for_any_row_fails_stage`
- `test_required_tool_all_business_errors_counts_as_missing`

验收标准：

- 缺少必调工具不再只是 warning 文本。
- 阶段失败会阻止下游角色启动。
- reviewer 的每条内容行都必须被有效 `submit_review` 覆盖。

### P1-2 copywriter fan-out 子 Agent 不得拥有状态推进权

当前风险：

- copywriter soul 白名单包含 `update_status`。
- fan-out 注释要求状态由 Orchestrator 控制，但工具权限没有收窄。
- 任一平台子 Agent 可能提前把状态推进到“审核中”。

期望行为：

- fan-out 子 Agent 的工具白名单不包含 `update_status`。
- “撰写中”到“审核中”只能由 Orchestrator 在所有 draft 非空后推进。
- 子 Agent 尝试提前推进状态时应无效或被拒绝。

建议测试文件：

- `tests/test_status_authority_tdd.py`

建议测试用例：

- `test_copywriter_fanout_agent_tools_do_not_include_update_status`
- `test_orchestrator_advances_to_review_only_after_all_drafts_filled`
- `test_partial_drafts_keep_status_writing`

验收标准：

- fan-out 子 Agent 无法调用 `update_status`。
- 草稿不完整时不会进入 reviewer。

### P1-3 webhook token 缺失必须拒绝

当前风险：

- 配置 `WEBHOOK_VERIFICATION_TOKEN` 后，请求缺 token 时仍可能放行。
- challenge 分支也存在缺 token 放行风险。

期望行为：

- 配置了 token 时，请求 token 缺失或不匹配都返回 401。
- 只有 token 匹配才允许 challenge 或事件处理继续。

建议测试文件：

- `tests/test_webhook_auth_tdd.py`

建议测试用例：

- `test_webhook_event_missing_token_rejected_when_token_configured`
- `test_webhook_event_invalid_token_rejected`
- `test_webhook_challenge_missing_token_rejected_when_token_configured`
- `test_webhook_valid_token_accepted`

验收标准：

- 缺 token、错 token 均为 401。
- 合法 token 才触发 `_launch_pipeline`。

### P1-4 关键门禁读取失败必须 fail closed

当前风险：

- 人审门禁加载项目失败时返回 approved。
- Plan-Verify 读取内容行失败时返回空 gaps。
- handoff 读取项目失败时跳过校验。

期望行为：

- 人审门禁读失败应中止或挂起，不得自动放行。
- Plan-Verify 读失败应返回校验不可用的 gap。
- handoff 关键读失败应阻止下游启动。

建议测试文件：

- `tests/test_fail_closed_gates_tdd.py`

建议测试用例：

- `test_human_review_gate_load_failure_does_not_approve`
- `test_plan_verify_content_read_failure_returns_gap`
- `test_handoff_project_read_failure_blocks_critical_stage`

验收标准：

- 外部事实源不可读时，流程进入 blocked/aborted，而不是继续生产。

### P2-1 webhook 去重应支持断点续跑

当前风险：

- `_processed_record_ids` 是进程内永久集合。
- 同一个 record_id 处理过后，即使需要恢复，也会被 webhook duplicate 逻辑挡住。

期望行为：

- 正在运行时返回 `already_running`。
- 运行结束后允许同 record_id 再次触发，以便断点续跑。
- 若仍需去重，应按 event_id 或短 TTL 去重，而不是永久按 record_id。

建议测试文件：

- `tests/test_webhook_dedup_tdd.py`

建议测试用例：

- `test_running_record_returns_already_running`
- `test_finished_record_can_be_triggered_again_for_resume`
- `test_duplicate_event_id_within_ttl_is_ignored`

验收标准：

- record 级恢复不被永久去重挡住。
- 重复事件仍能在短窗口内被抑制。

### P2-2 事件发布失败应可观测

当前风险：

- `_publish` 捕获异常后静默忽略。
- Dashboard 或事件持久化失败时，流水线仍继续但审计侧无法定位丢事件原因。

期望行为：

- 事件发布失败至少记录 warning。
- 日志包含 `record_id`、`event_type`、异常类型。

建议测试文件：

- `tests/test_event_publish_observability_tdd.py`

建议测试用例：

- `test_orchestrator_publish_failure_logs_warning`
- `test_base_agent_publish_failure_logs_warning`

验收标准：

- EventBus 失败不会打断主流程。
- 日志中能看到失败事件的定位信息。

## TDD 开发顺序

第一批红灯测试：

1. `tests/test_pipeline_red_flag_tdd.py`
2. `tests/test_agent_required_tools_tdd.py`
3. `tests/test_webhook_auth_tdd.py`

第一批实现：

1. 红线硬中止。
2. reviewer 红线结构化汇总。
3. 必调工具缺失结构化失败。
4. webhook 强制 token 校验。

第二批红灯测试：

1. `tests/test_status_authority_tdd.py`
2. `tests/test_fail_closed_gates_tdd.py`

第二批实现：

1. fan-out 子 Agent 工具权限收窄。
2. Plan-Verify、handoff、人审门禁 fail closed。

第三批红灯测试：

1. `tests/test_webhook_dedup_tdd.py`
2. `tests/test_event_publish_observability_tdd.py`

第三批实现：

1. webhook 去重改为 TTL/event_id 或运行锁语义。
2. 事件发布异常记录 warning。

## 审计检查点

后续每批实现完成后，审计人员应至少检查：

1. 是否存在新增的 fail-open 分支。
2. 是否仍有“警告但继续成功”的关键风险路径。
3. 是否把 LLM 自报结果当作事实源。
4. 是否绕过 `feishu/` 封装直接访问飞书 API。
5. 是否让 Agent 拥有不属于它的状态推进或跨表写入权限。
6. 是否有测试覆盖异常路径，而不仅是 happy path。

## 当前已知本地验证

本次审计前已跑过以下离线测试：

```bash
python -m pytest tests/test_orchestrator_red_flag.py tests/test_reviewer_rules.py tests/test_dynamic_routing.py -q --tb=short
```

结果：

- `12 passed`
- 有 `.pytest_cache` 写入权限 warning，不影响本轮审计结论。

## 非目标

本轮不处理：

1. Dashboard UI 改版。
2. 飞书真实环境联调。
3. 新增业务角色。
4. 改动知识库目录结构。
5. 大规模重构 Orchestrator 或 BaseAgent。

