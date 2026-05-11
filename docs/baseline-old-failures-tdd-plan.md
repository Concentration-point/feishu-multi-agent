# 基线旧失败下一轮 TDD 计划

> 分支：`codex/tdd-baseline-old-failures`
> 范围：仅处理全量测试中已在 `codex-tdd-audit-baseline` 复现的 7 个旧失败。
> 原则：不和本轮安全修复混合；先补/校准测试，再修实现。

## 当前基线

本轮安全修复已合回 `main`，目标安全测试通过：

```bash
python -m pytest tests/test_pipeline_red_flag_tdd.py tests/test_agent_required_tools_tdd.py tests/test_webhook_auth_tdd.py tests/test_webhook_dedup_tdd.py tests/test_status_authority_tdd.py tests/test_fail_closed_gates_tdd.py -q --tb=short
```

结果：`31 passed`。

全量测试剩余 7 个旧失败：

```bash
python -m pytest tests -q --tb=short --basetemp=.pytest_tmp
```

结果：`199 passed, 5 skipped, 7 failed`。

## 待处理失败

### F1 account_manager unit 模式 required tool 预期不一致

失败用例：

1. `tests/agents/test_account_manager_agent.py::test_account_manager_soul_runs_with_explicit_input_context_strategy`
2. `tests/agents/test_account_manager_agent.py::test_account_manager_can_call_ask_human_for_blocking_info`

当前现象：
- 测试预期 `missing_required_tools == ["write_project"]`。
- 实际结果为 `[]`，因为脚本里 mock LLM 已经声明过 `write_project` 工具调用。

下一步 TDD 判断：
- 明确 unit 模式到底只统计真实 registry 调用，还是统计 LLM 声明的 tool call。
- 若应统计真实调用，则修 `BaseAgent` unit 模式工具执行路径或测试 fake registry 断言。
- 若应统计 LLM 声明，则更新测试预期。

建议边界：
- 测试：`tests/agents/test_account_manager_agent.py`
- 实现：`agents/base.py`

### F2 experience optimization 语义去重与桶合并冲突

失败用例：

`tests/test_experience_optimization.py::test_optimize_bucket_merges_bucket_and_resets_use_count`

当前现象：
- 期望合并后写入 1 条经验。
- 实际被语义去重拦截，`client.records == []`。

下一步 TDD 判断：
- 桶合并产生的新经验是否应绕过“同置信度重复跳过”逻辑。
- 或者测试应构造真正需要合并的新经验输入。

建议边界：
- 测试：`tests/test_experience_optimization.py`
- 实现：`memory/experience.py`

### F3 wiki title 指纹方法缺失

失败用例：

`tests/test_pipeline_diagnosis_fixes.py::test_hidden_2_title_dedup_by_fingerprint`

当前现象：
- 测试引用 `BaseAgent._build_wiki_title`。
- 当前 `BaseAgent` 没有该方法。

下一步 TDD 判断：
- 若该能力仍需要，恢复/实现稳定标题指纹方法。
- 若该能力已迁移，测试应改到新的 owner。

建议边界：
- 测试：`tests/test_pipeline_diagnosis_fixes.py`
- 实现：`agents/base.py` 或经验/知识沉淀实际 owner 模块

### F4 soul audit 知识注入为空

失败用例：

1. `tests/test_soul_audit_improvements.py::test_reviewer_still_gets_full_rules`
2. `tests/test_soul_audit_improvements.py::test_all_roles_get_common_method_files`

当前现象：
- `load_shared_knowledge("reviewer")` 返回空字符串或缺公共方法论内容。

下一步 TDD 判断：
- 明确本地 knowledge 目录缺文件、路径配置错误，还是 `load_shared_knowledge` 筛选逻辑错误。
- 若测试依赖知识文件，应补 fixture 或 mock，而不是依赖真实本地知识库状态。

建议边界：
- 测试：`tests/test_soul_audit_improvements.py`
- 实现：`agents/base.py`
- 数据/fixture：仅在确认必要时补最小测试知识文件

### F5 soul max_iterations 审计期望未落地

失败用例：

`tests/test_soul_audit_improvements.py::test_max_iterations_reduced`

当前现象：
- 测试期望 strategist/project_manager/data_analyst 的 `max_iterations` 降低。
- 当前 strategist 仍为 `14`。

下一步 TDD 判断：
- 这些阈值是否仍是目标行为。
- 若是，修改对应 `agents/*/soul.md`。
- 若否，更新测试说明和期望。

建议边界：
- 测试：`tests/test_soul_audit_improvements.py`
- 配置：`agents/strategist/soul.md`、`agents/project_manager/soul.md`、`agents/data_analyst/soul.md`

## 建议拆分

1. Agent A：处理 F1 account_manager unit 模式语义。
2. Agent B：处理 F2 experience optimization。
3. Agent C：处理 F3 wiki title 指纹 owner。
4. Agent D：处理 F4/F5 soul audit 改善。

## 验收命令

先跑 7 个旧失败目标：

```bash
python -m pytest tests/agents/test_account_manager_agent.py::test_account_manager_soul_runs_with_explicit_input_context_strategy tests/agents/test_account_manager_agent.py::test_account_manager_can_call_ask_human_for_blocking_info tests/test_experience_optimization.py::test_optimize_bucket_merges_bucket_and_resets_use_count tests/test_pipeline_diagnosis_fixes.py::test_hidden_2_title_dedup_by_fingerprint tests/test_soul_audit_improvements.py::test_reviewer_still_gets_full_rules tests/test_soul_audit_improvements.py::test_all_roles_get_common_method_files tests/test_soul_audit_improvements.py::test_max_iterations_reduced -q --tb=short --basetemp=.pytest_tmp
```

再跑全量：

```bash
python -m pytest tests -q --tb=short --basetemp=.pytest_tmp
```
