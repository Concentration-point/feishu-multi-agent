# 模块三验收标准：客户经理 Agent 的「人类指导进化」

## 一、工具注册验收（T3-01）

| # | 验收项 | 验证方式 | 期望结果 |
|---|--------|---------|---------|
| 1.1 | `request_human_review` 出现在 ToolRegistry | `python -c "from tools import ToolRegistry; r=ToolRegistry(); assert 'request_human_review' in r.tool_names"` | 断言通过 |
| 1.2 | SCHEMA 符合 OpenAI function calling 格式 | 检查 `SCHEMA["function"]["parameters"]["required"]` 包含 `brief_analysis` | `required: ["brief_analysis"]` |
| 1.3 | soul.md 解析后 tools 列表包含新工具 | `parse_soul()` 返回的 `tools` 含 `request_human_review` | 已验证通过 |

## 二、AUTO_APPROVE 模式验收（T3-01 降级路径）

| # | 验收项 | 验证方式 | 期望结果 |
|---|--------|---------|---------|
| 2.1 | `AUTO_APPROVE_HUMAN_REVIEW=true` 时跳过真人审核 | 设置环境变量，调用 `execute()`，不发 IM | 返回含 `[AUTO_APPROVE]` 的通过结果 |
| 2.2 | `FEISHU_CHAT_ID` 为空时降级通过 | 清空 CHAT_ID，调用 `execute()` | 返回含 `[未配置群聊]` 的通过结果 |
| 2.3 | 卡片发送失败时降级通过 | mock `send_card_return_id` 抛异常 | 返回含 `[发送失败]` 的通过结果，不抛异常 |
| 2.4 | 超时时降级通过 | `timeout_seconds=1`，无人回复 | 返回含 `[超时]` 的通过结果 |
| 2.5 | `brief_analysis` 为空时拒绝执行 | 传空字符串 | 返回错误提示，不发 IM |

**核心原则**：任何配置缺失或外部故障，流程都不能卡死。

## 三、正常人机交互验收（T3-01 主路径）

| # | 验收项 | 验证方式 | 期望结果 |
|---|--------|---------|---------|
| 3.1 | 审核卡片成功发送到群聊 | 真实飞书环境运行，观察群聊 | 出现橙色卡片，标题含「Brief 解读等待审核」 |
| 3.2 | 卡片正文包含完整 Brief 解读 | 查看卡片内容 | 含解读全文 + 回复指引 |
| 3.3 | 人类回复「通过」正确解析 | 群聊回复"通过" | 工具返回 `状态：通过` |
| 3.4 | 人类回复「修改：xxx」正确解析 | 群聊回复"修改：目标人群需要调整" | 工具返回 `状态：需要修改`，`修改意见` 含原文 |
| 3.5 | 人类直接回复自由文本作为修改意见 | 群聊回复"客户的预算其实是10万不是5万" | 解析为修改意见（兜底逻辑） |
| 3.6 | 只解析人类消息，忽略机器人消息 | poll 过程中有其他 bot 消息 | 跳过 bot 消息，只处理 `sender_type=user` |

## 四、soul.md 工作流验收（T3-02）

| # | 验收项 | 验证方式 | 期望结果 |
|---|--------|---------|---------|
| 4.1 | 客户经理 ReAct 日志中出现 `request_human_review` 调用 | 跑完整 pipeline，检查日志 | 日志含 `调用工具 request_human_review` |
| 4.2 | 不跳过人类审核直接输出 | 检查 Agent 行为 | Brief 解读写入主表**前**必有 `request_human_review` 调用 |
| 4.3 | 修改后二次提交审核 | 第一轮回复"修改"，观察 Agent | Agent 重新生成解读并再次调用 `request_human_review` |
| 4.4 | 最终解读标注人类审核状态 | 检查写入主表的 `brief_analysis` 字段 | 含「已通过人类审核」字样 |
| 4.5 | max_iterations 足够支撑 2 轮审核 | 检查 soul.md | `max_iterations: 12`（原 8 不够 2 轮审核来回） |

## 五、Hook 自省分化验收（T3-03）

| # | 验收项 | 验证方式 | 期望结果 |
|---|--------|---------|---------|
| 5.1 | 客户经理蒸馏经验含 `human_correction` 字段 | 跑 pipeline 后检查 `_pending_experience` | JSON 含 `human_correction`, `reasoning` |
| 5.2 | 人类直接通过时，`human_correction` 为「无修改」 | AUTO_APPROVE 模式跑一次 | `human_correction` 不为空 |
| 5.3 | `lesson` 具体到客户类型的解读模式 | 检查蒸馏输出 | 不是"注意沟通"这种废话，是"当客户说X时通常意思是Y" |
| 5.4 | 其他角色不受影响，用默认 prompt | 检查 strategist 的蒸馏输出 | 无 `human_correction` 字段，结构与原来一致 |
| 5.5 | 经验写入本地 wiki | 检查 `knowledge/wiki/` 目录 | 有 `account_manager_` 开头的 .md 文件 |

## 六、Demo 端到端验收（T3-04 + 集成）

| # | 验收项 | 验证方式 | 期望结果 |
|---|--------|---------|---------|
| 6.1 | AUTO_APPROVE 模式全链路跑通 | `AUTO_APPROVE_HUMAN_REVIEW=true python demo/run_demo.py --scene 电商大促` | 客户经理阶段完成，日志含「模拟人类批准」 |
| 6.2 | 手动审核模式全链路跑通 | 关闭 AUTO_APPROVE，队友在群聊配合回复 | 客户经理阶段含 2 轮审核交互 |
| 6.3 | 客户经理阶段耗时合理 | 观察日志时间戳 | AUTO_APPROVE < 60s，手动审核 < 120s（含人类反应时间） |
| 6.4 | playbook 覆盖所有 Demo Brief | 检查 `demo/human_review_playbook.md` | 三个 Brief 均有预设回复话术 |

## 七、不可回归项

| # | 验收项 | 说明 |
|---|--------|------|
| 7.1 | 其他 4 个 Agent 行为不变 | strategist / copywriter / reviewer / project_manager 不受本次改动影响 |
| 7.2 | 现有工具全部正常注册 | ToolRegistry 扫描结果数量 = 原有数 + 1 |
| 7.3 | Orchestrator 流程不变 | 五阶段串行 + 审核驳回重试逻辑不受影响 |
