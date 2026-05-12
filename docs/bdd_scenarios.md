# 决赛 Demo BDD 验收场景

本文档以行为驱动开发（BDD）格式定义每个模块的最小原子化验收场景，作为 Demo 前最后一公里的验收抓手。

## 优先级说明

- **P0**：此场景不通过 = Demo 会崩溃（Day 1 必须全部通过）
- **P1**：此场景不通过 = Demo 效果差但不崩溃（Day 2 验证）
- **P2**：锦上添花（时间够就验证）

## 模块清单

- [x] 模块 A：流水线主流程（动态路由 + 五角色串行）
- [x] 模块 B：客户经理（品牌调研 + 主动追问 + Brief 解读）
- [x] 模块 C：策略师（历史经验 + 竞品搜索 + 内容行创建）
- [x] 模块 D：文案（平台指南加载 + 爆款对标 + 逐条撰写）
- [x] 模块 E：审核（预检读取 + 五维审核 + 驳回反馈）
- [x] 模块 F：项目经理（排期 + 交付摘要）
- [x] 模块 G：经验闭环（沉淀 + 检索注入 + 去重合并）
- [ ] 模块 H：异常处理（Agent 失败 + 工具报错 + 状态回退）

---

## 模块 A — 流水线主流程

```gherkin
Feature: 流水线主流程（动态路由 + 五角色串行）

  # ───────── P0 必过 ─────────

  # P0
  Scenario: A-01 完整流水线从 Brief 到「已完成」
    Given 项目主表有一条记录（record_id=recA01，客户="测试客户A"，项目类型="电商大促"，Brief 内容="六一儿童节促销文案"，品牌调性="国潮新锐"）
    And 项目状态="待处理"
    And 内容排期表中该项目无内容行
    When 调用 Orchestrator(record_id=recA01).run()
    Then 项目主表 status 字段最终值="已完成"
    And brief_analysis / strategy / review_summary / delivery 四个字段均非空
    And 内容排期表中关联项目="测试客户A" 的行数 ≥ 3
    And 每行 draft 字段非空
    And review_pass_rate ≥ project_type 对应阈值（0.6）
    And SSE 事件流广播了 pipeline.completed 事件

  # P0
  Scenario: A-02 路由从「待处理」开始正确进入 account_manager
    Given 项目主表 status="待处理"
    When Orchestrator.run() 进入主循环第一步
    Then _resolve_next_role("待处理") 返回 "account_manager"
    And 广播 pipeline.stage_changed 事件，current_role="account_manager"，stage_index=1

  # P0
  Scenario: A-03 状态空字段被兜底初始化为「待处理」
    Given 项目主表 status 字段为空字符串 ""
    When Orchestrator.run() 首次读取项目状态
    Then 调用 _initialize_pending_status() 回写 status="待处理"
    And 主循环继续进入 account_manager 阶段，不直接退出

  # P0
  Scenario: A-04 从中间态恢复 — status=「撰写中」时直接进入 copywriter
    Given 项目主表 status="撰写中"
    And brief_analysis 和 strategy 字段已非空（上游已完成）
    And 内容排期表已有 3 行内容（draft 字段为空）
    When 调用 Orchestrator(record_id=recA04).run()
    Then 第一个 stage_changed 事件 current_role="copywriter"，routed_from_status="撰写中"
    And 不会再调用 account_manager 或 strategist Agent

  # P0
  Scenario: A-05 角色阶段超时不导致流水线崩溃
    Given Orchestrator 正在执行 strategist 阶段
    When strategist 的 BaseAgent.run() 抛出 asyncio.TimeoutError（STAGE_TIMEOUT_SECONDS=600 触发）
    Then StageResult.ok=False，error 字段包含超时信息
    And 广播 "流水线异常" 卡片到飞书群（color=red）
    And 调用 _pm.write_agent_error_log 写回错误到 Bitable
    And 进程不抛出未捕获异常

  # P0
  Scenario: A-06 死循环防护 — 同状态连续 3 次后强制 halt
    Given 项目状态="撰写中"，copywriter 已连续执行 2 次但状态未推进
    And 本轮 result.used_ask_human=False
    When 第 3 次 copywriter 执行结束后状态仍为"撰写中"
    Then no_progress_count 达到 NO_PROGRESS_LIMIT=3
    And 广播 "流水线异常 · 强制中止" 卡片
    And 调用 _finalize_pipeline_halted(reason="no_progress:撰写中")
    And run() 返回，不再进入下一轮循环

  # P0
  Scenario: A-07 路由超过 MAX_ROUTE_STEPS=15 步时强制终止
    Given Orchestrator 主循环已执行 14 轮
    When 第 15 轮完成后状态仍未达到终止态
    Then while 循环退出（step >= MAX_ROUTE_STEPS）
    And 控制台打印 "动态路由超出最大步数 15，强制终止"
    And 流水线进入收尾分支但不会无限循环

  # ───────── P1 效果保障 ─────────

  # P1
  Scenario: A-08 五判据校验全通过时发 pipeline.completed
    Given 流水线运行结束，step=8，ok_count=5
    And 最终 status="已完成"，pass_rate=0.85，_review_threshold=0.7
    When 进入 run() 收尾五判据校验
    Then is_truly_completed=True
    And 发布事件类型为 "pipeline.completed"
    And 不发布 "pipeline.aborted"

  # P1
  Scenario: A-09 通过率低于阈值时发 pipeline.aborted
    Given 流水线运行结束，最终 status="已完成"
    And pass_rate=0.5，_review_threshold=0.7
    When 进入五判据校验
    Then is_truly_completed=False
    And abort_reason="below_threshold:0.50<0.70"
    And 发布事件类型为 "pipeline.aborted"

  # P1
  Scenario: A-10 上游字段缺失时 handoff_validate 阻断后续角色
    Given 项目状态="策略中"，但 brief_analysis 字段为空
    When Orchestrator 路由到 strategist 并执行 _validate_handoff("strategist", ...)
    Then handoff_ok=False，handoff_reason 包含 "brief_analysis"
    And 广播 "流水线异常 · 交接校验失败" 卡片
    And 调用 _finalize_pipeline_halted(reason="handoff_failed:strategist")
    And strategist Agent.run() 不被实际调用

  # P1
  Scenario: A-11 AM 兜底推进 — 阶段成功但 status 未推进时自动推到「待人审」
    Given account_manager 阶段 result.ok=True
    And 阶段结束后从 Bitable 读到 brief_analysis 非空但 status 仍="解读中"
    When Orchestrator 进入 AM 兜底分支
    Then 调用 _pm.update_status("待人审")
    And current_status 更新为 "待人审"
    And 清除 account_manager 的 checkpoint 文件

  # P1
  Scenario: A-12 copywriter fan-out 安全网 — 全部成稿后自动推进状态
    Given copywriter fan-out 已结束，role_id="copywriter"
    And 内容排期表有 4 行，每行 draft 字段都非空
    And 从 Bitable 读到 status="撰写中"
    When 进入文案安全网分支
    Then 调用 _pm.update_status("审核中")
    And 不打印 "文案安全网 FAIL"

  # P1
  Scenario: A-13 copywriter fan-out 安全网 — 仍有空行时回退状态
    Given copywriter fan-out 结束后内容排期表仍有 2/4 行 draft 为空
    And 从 Bitable 读到 status="审核中"（被 LLM 误推）
    When 进入文案安全网分支
    Then 打印 "文案安全网 FAIL"
    And 调用 _pm.update_status("撰写中") 回退状态
    And 不进入 reviewer 阶段

  # ───────── P2 锦上添花 ─────────

  # P2
  Scenario: A-14 状态推进后清除该角色 checkpoint
    Given strategist 阶段执行成功，入口 status="策略中"
    When 执行结束后 _read_current_status() 返回 "撰写中"
    Then no_progress_count 重置为 0
    And 调用 _clear_stage_checkpoint(record_id, "strategist")
    And checkpoints/{record_id}/strategist*.json 文件被删除

  # P2
  Scenario: A-15 SSE 事件总线缺失时不影响主流程
    Given Orchestrator(record_id=recA15, event_bus=None)
    When Orchestrator.run() 执行任意 _publish 调用
    Then _publish 立即 return，不抛异常
    And 流水线主循环正常完成

  # P2
  Scenario: A-16 ask_human 工具调用算有效交互，不计入死循环
    Given account_manager 阶段结束后 status 未推进（仍="解读中"）
    And StageResult.used_ask_human=True
    When 进入死循环防护检查
    Then no_progress_count 被重置为 0（而非自增）
    And 打印 "Agent 调用了 ask_human（人机交互），重置计数"
```

**Module A 摘要**：共 16 个场景，P0=7 / P1=6 / P2=3。锚点覆盖 `orchestrator.run()` 主循环、`ROUTE_TABLE`、五判据校验、`no_progress_count` 防护、`_max_route_steps` 守卫、`_validate_handoff`、AM 兜底、copywriter fan-out 安全网。

---

## 模块 B — 客户经理（品牌调研 + 主动追问 + Brief 解读）

```gherkin
Feature: 客户经理 Agent（account_manager）

  # ───────── P0 必过 ─────────

  # P0
  Scenario: B-01 happy path — 完整产出 Brief 解读且推进到「待人审」
    Given 项目主表 status="待处理"，客户名称="回力"，项目类型="新品发布"，Brief 内容="国潮新锐运动鞋上市"
    And LLM mock 按 soul.md 流程返回 read_project → search_web → search_knowledge → write_project → update_status 的工具调用序列
    When 调用 BaseAgent(role_id="account_manager").run()
    Then 项目主表 brief_analysis 字段非空
    And brief_analysis 文本包含 "品牌调研" 或 "项目摘要" 等报告段落标题
    And 项目主表 status="待人审"
    And AgentResult.output 非空且 ok=True

  # P0
  Scenario: B-02 verify 卡口 — brief_analysis 字段空时触发 Plan-Verify 补充循环
    Given account_manager Agent 第一轮 ReAct 结束但 brief_analysis 字段仍为空
    When BaseAgent._verify_plan 读取 verify.check_fields=["brief_analysis"]
    Then _verify_plan 返回 verified=False
    And Agent 进入补充循环（最多 2 次）
    And 补充循环中 LLM 收到提示要求补齐 brief_analysis 字段

  # P0
  Scenario: B-03 ask_human 单题 — 1 个强阻塞项时使用 ask_human 而非 batch
    Given Brief 仅缺失 1 个 🔴 强阻塞项（预算范围）
    When account_manager 在阶段二决定追问
    Then 调用工具 ask_human（不是 ask_human_batch）
    And ask_human 参数 choices 至少 2 个、至多 6 个
    And 不调用 send_message 当作追问

  # P0
  Scenario: B-04 ask_human_batch 多题 — 2+ 个强阻塞项时一次性发送
    Given Brief 缺失 3 个 🔴 强阻塞项（预算 / 平台 / 优惠机制）
    When account_manager 阶段二追问
    Then 调用工具 ask_human_batch
    And questions 数组长度=3，每题 title 经 ask_human_batch 加上 "追问 i/N" 前缀
    And 每题 choices 数量在 [2, 4] 区间

  # P0
  Scenario: B-05 ask_human 超时降级 — 等待超时后返回提示字符串
    Given account_manager 调用 ask_human，timeout_seconds=120
    And FEISHU_CHAT_ID 已配置且卡片已发出
    When 120 秒内未收到任何按钮点击或文字回复
    Then ask_human.execute 返回字符串以 "等待超时（120 秒）" 开头
    And Agent 后续步骤将该回复视为信息收齐
    And 整个流水线不卡死

  # ───────── P1 效果保障 ─────────

  # P1
  Scenario: B-06 调研工具调用顺序 — 先 search_web 再 web_fetch 深读
    Given account_manager 阶段一调研品牌公开信息
    When LLM 调用 search_web(query="回力 国潮 小红书") 返回若干 URL
    Then 后续工具调用包含 web_fetch 且 url 取自上一步 search_web 的 results
    And 不直接跳过 search_web 凭空给 URL

  # P1
  Scenario: B-07 中文查询走秘塔 — search_web 引擎路由正确
    Given METASO_API_KEY 已配置
    When account_manager 调用 search_web(query="完美日记 小红书 新品推广")
    Then search_web 内部命中 _contains_chinese=True 分支
    And 实际请求秘塔 API（METASO_API_BASE/search）
    And 返回字典 engine="metaso"

  # P1
  Scenario: B-08 CLI 模式自动降级 — ask_human 在无 WebSocket 时返回 choices[0]
    Given 进程以 `python main.py run <record_id>` 启动（CLI 模式，无 WebSocket）
    And card_actions.register 抛出 RuntimeError（"CLI 模式下不支持等待"）
    When account_manager 调用 ask_human(choices=["对", "不对，我补充"])
    Then ask_human 立即返回 "人类已选择：对（CLI 模式自动降级，非人工选择）"
    And Agent 继续推进，不阻塞

  # P1
  Scenario: B-09 ask_human_batch 数量上限 — 超过 5 题被裁剪到 5
    Given account_manager 试图调用 ask_human_batch 提交 7 个问题
    When ask_human_batch.execute 进入参数校验分支
    Then questions 被裁剪为前 5 个
    And 实际发送的卡片只有 5 张

  # P1
  Scenario: B-10 状态推进契约 — 阶段一进入「解读中」、阶段三进入「待人审」
    Given Brief 处于「待处理」状态
    When account_manager Agent 完整执行 ReAct 循环
    Then 工具调用序列中包含 update_status(status="解读中")
    And 工具调用序列中包含 update_status(status="待人审")
    And 不出现 update_status 跳到 "策略中" / "撰写中" / "已完成" 等下游状态

  # P1
  Scenario: B-11 工具白名单约束 — Agent 无法调用 create_content
    Given account_manager 的 soul.md tools 列表不含 create_content
    When LLM 试图返回 tool_call={name: "create_content"}
    Then ToolRegistry 注册给 LLM 的 functions 列表中无 create_content schema
    And LLM 端因 schema 不存在不会真正发起该调用，或 BaseAgent 拒绝执行

  # ───────── P2 锦上添花 ─────────

  # P2
  Scenario: B-12 经验注入 — get_experience 命中后 prompt 包含历史经验
    Given 经验池 Bitable 中有一条 role="account_manager", scene="新品发布", confidence=0.85 的经验
    When account_manager 启动并装配 system prompt
    Then 实际 system prompt 文本包含该条经验的 lesson 字段内容
    And 工具调用记录中可见 get_experience 调用（Top-K=5）

  # P2
  Scenario: B-13 max_iterations=18 — 超过上限后 Agent 安全退出
    Given account_manager 的 soul.md max_iterations=18
    When LLM 连续 18 轮工具调用仍未给出 final answer
    Then ReAct 循环退出
    And AgentResult.output 以 "[TRUNCATED:" 开头
    And 不抛出未捕获异常

  # P2
  Scenario: B-14 修订说明节段 — 收到人审反馈重跑后填写第 9 节
    Given Bitable 项目主表 human_feedback 字段非空（人审驳回回写）
    And 项目状态被 Orchestrator 重置为「解读中」
    When account_manager 第二次执行
    Then 新写入的 brief_analysis 文本包含 "修订说明" 段落标题
    And 该段落引用了 human_feedback 的关键词

  # P2
  Scenario: B-15 send_message 仅用于状态通知 — 不被误用于追问
    Given account_manager 完整执行
    When 复盘所有工具调用记录
    Then send_message 调用次数 ≥ 1（阶段一启动通知 + 阶段三完成通知）
    And 不存在「send_message 的 content 字段是问句且未跟随 ask_human/ask_human_batch」的调用
```

**Module B 摘要**：共 15 个场景，P0=5 / P1=6 / P2=4。锚点覆盖 `agents/account_manager/soul.md` 的三阶段工作流、`tools/ask_human.py` 单题契约、`tools/ask_human_batch.py` 多题裁剪、`tools/search_web.py` 双引擎路由、`BaseAgent._verify_plan` Plan-Verify 卡口、CLI 模式降级路径。

---

## 模块 C — 策略师（历史经验 + 竞品搜索 + 内容行创建）

```gherkin
Feature: 策略师 Agent（strategist）

  # ───────── P0 必过 ─────────

  # P0
  Scenario: C-01 happy path — 内容矩阵创建并推进到「撰写中」
    Given 项目主表 status="策略中"，brief_analysis 字段非空
    And 内容排期表中该项目暂无内容行
    When 调用 BaseAgent(role_id="strategist").run()
    Then 项目主表 strategy 字段非空
    And 内容排期表新增内容行数 ≥ 3
    And 每行的 platform 取自 {小红书, 抖音, 公众号, 微博, 视频号, B站, 知乎} 枚举
    And 每行 title / key_point / target_audience / seq 四字段非空
    And 项目主表 status="撰写中"

  # P0
  Scenario: C-02 verify 卡口 — 内容行少于 3 时触发 Plan-Verify 补充循环
    Given strategist Agent 第一轮 ReAct 结束，strategy 字段已写
    And 内容排期表只创建了 2 行（少于 verify.min_content_rows=3）
    When BaseAgent._verify_plan 校验
    Then 返回 verified=False
    And Agent 进入补充循环（最多 2 次），prompt 中显式要求补足 ≥ 3 行

  # P0
  Scenario: C-03 batch_create_content 入口去重 — 同名 title 跳过不写入 Bitable
    Given 内容排期表中已有一行 title="618 母婴大促种草笔记"
    When strategist 调用 batch_create_content，items 包含 title="618 母婴大促种草笔记"（完全相同）
    Then 返回 JSON 中 skipped 包含该 title，reason="已存在同名内容行"
    And Bitable 不被发起写入请求
    And 内容排期表行数保持不变

  # P0
  Scenario: C-04 batch_create_content 同批次内部去重 — items 自身有重复 title 也合并
    Given 内容排期表为空
    When strategist 提交 items=[{title:"A"}, {title:"A"}, {title:"B"}]
    Then 实际写入 Bitable 的 record_ids 数量=2
    And skipped 列表包含一条 reason="同批次内重复"

  # P0
  Scenario: C-05 全部重复时返回提示但不报错
    Given 内容排期表已有 title=["X","Y","Z"]
    When strategist 提交 items 全为这三条
    Then batch_create_content 返回的 record_ids=[]
    And message 字段包含 "全部 3 条已存在，未创建新内容行"
    And 不抛出异常，不阻断后续 update_status 调用

  # ───────── P1 效果保障 ─────────

  # P1
  Scenario: C-06 工具调用顺序契约 — 先 search_knowledge 再 search_web 再 batch_create_content
    Given strategist 完整执行
    When 复盘 tool_calls 时间序列
    Then search_knowledge 或 read_knowledge 至少调用 1 次（按 soul.md 第二步）
    And search_web 至少调用 1 次（第三步）
    And batch_create_content 调用发生在 search_knowledge 和 search_web 之后

  # P1
  Scenario: C-07 search_knowledge 剥离 frontmatter — 命中正文而非 frontmatter
    Given knowledge/02_服务方法论/x.md frontmatter category="电商大促"，正文无 "电商大促"
    And knowledge/02_服务方法论/y.md 正文包含 "电商大促" 三次
    When strategist 调用 search_knowledge(query="电商大促")
    Then 结果列表中 y.md 排序高于 x.md
    And x.md 完全不命中（frontmatter 不参与匹配）

  # P1
  Scenario: C-08 search_knowledge 默认 scope 剔除 11_待整理收件箱
    Given knowledge/11_待整理收件箱/dirty.md 正文包含 "种草"
    And knowledge/10_经验沉淀/clean.md 正文包含 "种草"
    When strategist 调用 search_knowledge(query="种草")（不指定 scope）
    Then 返回结果只含 clean.md
    And dirty.md 路径不出现在结果中

  # P1
  Scenario: C-09 web_fetch 中文站超时降级到秘塔 Reader
    Given METASO_API_KEY 已配置
    And web_fetch 目标 URL host 命中 _CHINESE_PLATFORM_DOMAINS（如 xiaohongshu.com）
    When 普通 HTTP 请求触发 httpx.TimeoutException
    Then 自动调用 _metaso_reader_fetch
    And 返回字典 extraction_backend="metaso_reader"
    And ok=True，且 content_chars > 0

  # P1
  Scenario: C-10 web_fetch SSRF 拦截 — 内网地址直接返回 ssrf_blocked
    Given strategist 试图 web_fetch(url="http://192.168.1.1/admin")
    When _validate_url_for_request 校验 IP
    Then 返回 ok=False，error_type="ssrf_blocked"
    And retryable=False
    And 不发起任何外网请求

  # P1
  Scenario: C-11 内容行 platform 字段被 schema enum 约束
    Given strategist 试图创建一条 platform="小红书脚本"（带后缀）的内容行
    When OpenAI function calling 校验 batch_create_content 参数
    Then schema 校验失败（不在 enum 列表）
    And BaseAgent 把工具错误反馈给 LLM
    And LLM 在下一轮修正为 platform="小红书"

  # P1
  Scenario: C-12 max_iterations=9 — 策略师在 9 轮内必须完成
    Given strategist soul.md max_iterations=9
    When LLM 在第 9 轮仍未给出 final answer
    Then ReAct 循环退出
    And AgentResult.output 以 "[TRUNCATED:" 开头
    And Orchestrator 广播带 "（输出截断）" 标记的卡片（color=orange）

  # ───────── P2 锦上添花 ─────────

  # P2
  Scenario: C-13 经验注入 — LLM 主动调 get_experience 工具拉取历史经验
    Given 经验池 Bitable 有一条 role=strategist, scene="新品发布", confidence=0.9 的经验
    And strategist 的 soul.md tools 白名单虽未显式列出 get_experience，但 BaseAgent 默认提供（按实际代码注册情况）
    When strategist 执行 ReAct 循环
    Then 工具调用序列中出现 get_experience(role="strategist", scene="新品发布") 调用
    And 该工具返回的经验 lesson 出现在后续 LLM 上下文中，影响 strategy 字段产出
    And 经验注入是 LLM 工具调用驱动，不是 system prompt 启动时静态注入

  # P2
  Scenario: C-14 工具白名单约束 — strategist 不可调用 ask_human
    Given strategist 的 soul.md tools 列表不含 ask_human 或 ask_human_batch
    When LLM 试图返回 tool_call={name:"ask_human"}
    Then ToolRegistry 注册给 LLM 的 functions 列表中无 ask_human schema
    And 实际不会发起人审追问

  # P2
  Scenario: C-15 web_fetch 不可生成式 prompt — 缺少 prompt 字段时返回 missing_prompt
    Given strategist 调用 web_fetch(url="https://x.com/a")，未传 prompt 字段
    When web_fetch.execute 进入参数校验
    Then 返回 ok=False，error_type="missing_prompt"
    And message 提示需要 extraction prompt

  # P2
  Scenario: C-16 web_fetch 速率限制 — 同域名 60 秒内调用超 12 次被限流
    Given strategist 在 60 秒内对 example.com 调用 web_fetch 12 次（均成功）
    When 第 13 次调用同域名 URL
    Then 返回 ok=False，error_type="rate_limited"
    And retryable=True

  # ───────── 质量软约束（输出抽检型）─────────

  # P1
  Scenario: C-17 平台软约束 — 内容矩阵实际产出只落在 {小红书, 抖音}
    Given strategist soul.md 明确规定 "发布平台只限小红书和抖音"
    When strategist 完成 batch_create_content 后从内容排期表读出所有新建行
    Then 每行 platform 字段值 ∈ {"小红书", "抖音"}
    And 小红书行数 ≥ 1 且抖音行数 ≥ 1
    And 总行数 ≥ 3

  # P1
  Scenario: C-18 卖点差异化软约束 — 内容矩阵 key_point 字段两两不同
    Given strategist 完成 batch_create_content
    When 取出该项目所有新建行的 key_point 字段
    Then 两两 key_point 字符串不完全相同（不允许多条打同一角度）
    And 任意两条 key_point 的字符级 Jaccard 相似度 < 0.8（防"换皮重复"）
```

**Module C 摘要**：共 18 个场景，P0=5 / P1=9 / P2=4。锚点覆盖 `agents/strategist/soul.md` 四步流程、`tools/batch_create_content.py` 入口/同批次双重去重、`tools/search_knowledge.py` scope 与 frontmatter 剥离、`tools/web_fetch.py` SSRF/秘塔降级/速率限制/missing_prompt。C-17/C-18 为输出抽检型软约束（代码不强制，靠产出抽样验证）。

---

## 模块 D — 文案（平台指南加载 + 爆款对标 + 逐条撰写）

```gherkin
Feature: 文案 Agent（copywriter）

  # ───────── P0 必过 ─────────

  # P0
  Scenario: D-01 happy path — 全部内容行成稿 + 字数双字段写回
    Given 项目主表 status="撰写中"，strategy 字段非空
    And 内容排期表有 3 行内容（draft 字段为空，title/platform/key_point 非空）
    When 调用 BaseAgent(role_id="copywriter").run()（或 Orchestrator copywriter fan-out 完整跑完）
    Then 内容排期表 3 行的 draft 字段均非空
    And 3 行的 word_count 字段均 > 0
    And 每行 draft 字符长度 ≈ word_count 字段值

  # P0
  Scenario: D-02 verify 卡口 — content 表 draft/word_count 任一字段空则触发补充循环
    Given copywriter Agent 第一轮 ReAct 结束后，某条内容行 word_count 字段仍为空
    When BaseAgent._verify_plan 校验 verify={table:"content", check_fields:["draft","word_count"]}
    Then 返回 verified=False
    And Agent 进入补充循环（最多 2 次），prompt 显式列出未达标的 content_record_id

  # P0
  Scenario: D-03 工具白名单约束 — copywriter 不可调用 update_status
    Given copywriter 的 soul.md tools 列表实际不含 update_status
    When LLM 试图返回 tool_call={name:"update_status", status:"审核中"}
    Then ToolRegistry 注册给 LLM 的 functions 列表中无 update_status schema
    And copywriter 子 Agent 不会自行把状态推到"审核中"
    And 状态推进依赖 orchestrator.py 的 _ensure_copywriter_drafts 安全网兜底

  # P0
  Scenario: D-04 write_content 写 draft_content 自动跑预检并合并备注
    Given 一条内容行 record_id=recCNT01，notes 字段已有 "[预检] 通过（2026-05-10）" 旧记录
    When copywriter 调用 write_content(content_record_id=recCNT01, field_name="draft_content", value="...含'最有效'...")
    Then ContentMemory.write_draft 写入 draft 与字数
    And preflight_lint.scan_forbidden_words 识别出 "最有效" 等禁用词
    And _merge_preflight_into_remark 剔除旧 [预检] 段后 append 新结果
    And notes 字段最终只有 1 段 [预检]，不堆积
    And 工具返回串包含 "命中禁用词 1 个（最有效）" 或类似

  # P0
  Scenario: D-05 write_content field_name 受 enum 限制
    Given LLM 试图调用 write_content(field_name="random_field")
    When OpenAI schema 校验
    Then field_name 不在 enum={draft_content, word_count, review_status, review_feedback, publish_date, notes}
    And schema 校验失败，工具不被执行
    And LLM 在下一轮收到错误反馈并修正

  # ───────── P1 效果保障 ─────────

  # P1
  Scenario: D-06 平台指南加载 — 小红书内容撰写前读「小红书通用规则」
    Given 内容行 platform="小红书"，project_type="电商大促"
    When copywriter 准备撰写该条内容
    Then 工具调用序列包含 search_knowledge(query 包含 "小红书通用规则" 或 "小红书 美妆"/对应品类)
    And 后续 read_knowledge 调用 path 指向 knowledge/05_平台打法/小红书/*.md 之一

  # P1
  Scenario: D-07 爆款对标 — 撰写前必调 search_reference
    Given 内容行 platform="小红书"，key_point="精华液种草"
    When copywriter 完整执行 ReAct 循环写完该条
    Then 工具调用序列包含至少一次 search_reference(query 包含 "精华液" 或 "种草", platform="小红书")
    And search_reference 调用发生在 write_content 之前

  # P1
  Scenario: D-08 search_reference 0 命中降级 — 返回平台 top-3 热度作通用启发
    Given knowledge/references/小红书/ 下没有任何 .md 包含 "扫地机"
    But 小红书目录下有其他 3 篇带 engagement 字段的对标
    When copywriter 调用 search_reference(query="扫地机 双十一", platform="小红书")
    Then 返回文本以 "⚠️ 关键词「扫地机 双十一」未命中精准对标" 开头
    And 文本包含 "同平台热度 top-3" 字样
    And 列表内容卡片按 engagement_score 降序排列

  # P1
  Scenario: D-09 search_reference 库覆盖清单提示 — 完全空库给出 inventory
    Given knowledge/references/ 目录存在但无任何 .md 命中关键词
    And 也没有同平台的卡片可降级
    When copywriter 调用 search_reference(query="完全不相关")
    Then 返回文本以 "对标库完全为空或过滤器过严" 开头
    And 文本包含 "📚 当前覆盖：" 段落
    And copywriter 收到指引后在备注里写明 "对标库无此品类样本"

  # P1
  Scenario: D-10 平台指南复用 — 同平台多条内容只在首条搜指南
    Given 内容排期表有 3 条小红书内容
    When copywriter 完整撰写这 3 条
    Then 全部 ReAct 轮次中，关键词 "小红书通用规则" 的 search_knowledge 调用次数 ≤ 2
    And 不重复 3 次读同一份 knowledge/05_平台打法/小红书/小红书通用规则.md

  # P1
  Scenario: D-11 小红书选题视角复核 — 首条小红书内容前必调"爆款选题逻辑"
    Given 内容排期表至少 1 条 platform="小红书" 的内容
    When copywriter 完整执行
    Then 工具调用序列包含 search_knowledge(query 包含 "小红书爆款选题逻辑" 或 "选题")
    And 该调用发生在第一条小红书内容的 write_content 之前

  # P1
  Scenario: D-12 SEO 关键词复查 — 小红书成稿写回前必调"SEO 关键词策略"
    Given 内容行 platform="小红书"
    When copywriter 撰写该条并准备 write_content
    Then 工具调用序列在 write_content(draft_content) 之前包含 search_knowledge(query 包含 "小红书SEO关键词策略" 或 "SEO")
    And 成稿正文（draft 字段）实际包含至少 1 个话题标签 "#xxx"

  # P1
  Scenario: D-13 max_iterations=14 — 文案在 14 轮内完成或安全截断
    Given copywriter soul.md max_iterations=14
    When LLM 在第 14 轮仍未给出 final answer
    Then ReAct 循环退出
    And AgentResult.output 以 "[TRUNCATED:" 开头
    And 已写入的 draft 字段不被回滚

  # P1
  Scenario: D-14 预检备注幂等性 — 多次写同样 draft 不堆积 [预检] 段
    Given 一条内容行 notes 字段为空
    When copywriter 对同一 record_id 连续 3 次调用 write_content(field_name="draft_content", value="...含'最有效'...")
    Then notes 字段最终只出现 1 段以 "[预检]" 开头的文本
    And _PREFLIGHT_BLOCK_RE 正则成功剔除旧段

  # ───────── P2 锦上添花 ─────────

  # P2
  Scenario: D-15 经验注入 — copywriter 通过 get_experience 工具拉取历史驳回经验
    Given 经验池有一条 role=copywriter, applicable_roles 包含 "copywriter" 的经验
    When copywriter 执行 ReAct 循环
    Then 工具调用序列包含 get_experience(role_id="copywriter", task_context=非空)
    And 返回的 lesson 字段对当条 draft 写作有可见影响（例如修正禁用词、调整 hook）

  # P2
  Scenario: D-16 fan-out 子 Agent 隔离 — 不同平台的 copywriter 子 Agent 各自有 checkpoint
    Given 内容排期表有 2 条小红书 + 2 条抖音内容
    When orchestrator.py 启动 copywriter fan-out
    Then checkpoints/{record_id}/ 下出现 copywriter_小红书.json 和 copywriter_抖音.json
    And 任一平台失败不影响另一平台进度恢复

  # P2
  Scenario: D-17 成稿质量软约束 — 每条 draft 字数达到平台指南最低值
    Given 平台指南 knowledge/05_平台打法/小红书/小红书通用规则.md 规定字数下限 = 500
    When copywriter 完成全部小红书内容
    Then 抽样检查每条 word_count 字段值 ≥ 500
    And 抽样检查 draft 正文实际含 "#" 话题标签 ≥ 1 个

  # P2
  Scenario: D-18 品牌调性优先于爆款风格
    Given 项目主表 brand_tone="高冷克制"，爆款对标多为感叹号密集口语
    When copywriter 写完 draft
    Then draft 中感叹号数量 < 爆款样本平均值
    And draft 不出现明显口播化 "姐妹们冲！" 类调性冲突措辞（抽检型）
```

**Module D 摘要**：共 18 个场景，P0=5 / P1=9 / P2=4。锚点覆盖 `agents/copywriter/soul.md` 工作流、`tools/write_content.py` enum/preflight/幂等备注、`tools/search_reference.py` 精准命中 + 降级 + 空库三分支、`tools/preflight_lint.py` 禁用词扫描、fan-out checkpoint 隔离。

> **关键发现 (代码现状)**：copywriter 的 soul.md tools 白名单**不含** update_status，但 soul.md 第三步描述写要"调 update_status → 审核中"。这是 soul.md 文档与白名单不一致的事实——D-03 把这条事实做成验收点：copywriter **不应该**能推状态，全靠 Orchestrator 的 `_ensure_copywriter_drafts` 安全网兜底（Module A 的 A-12/A-13 已覆盖兜底分支）。决赛 Demo 这条链路通了即可。

---

## 模块 E — 审核（预检读取 + 五维审核 + 驳回反馈）

```gherkin
Feature: 审核 Agent（reviewer）+ Orchestrator 返工分支

  # ───────── P0 必过 ─────────

  # P0
  Scenario: E-01 happy path — 全部内容行通过且推进到「排期中」
    Given 项目主表 status="审核中"，内容排期表有 3 行成稿内容
    And 每行 draft 无禁用词、字数符合平台规范、调性匹配
    When 调用 BaseAgent(role_id="reviewer").run() 完整执行后 Orchestrator._handle_reviewer_retries 介入
    Then 每条内容行都被 submit_review 调用过且 review_status="通过"
    And 项目主表 review_pass_rate ≥ _review_threshold（电商大促=0.6）
    And 项目主表 status="排期中"
    And self.reviewer_retries=0

  # P0
  Scenario: E-02 必调工具契约 — reviewer 缺失 submit_review 则视为违规
    Given reviewer 完整执行 ReAct 循环但全程未调用 submit_review
    When BaseAgent 在退出前校验 _REQUIRED_TOOL_CALLS
    Then AgentResult.missing_required_tools 包含 "submit_review"
    And _detect_required_tool_failure 返回 True
    And StageResult.ok=False，error 包含 "required tool violation: missing submit_review"
    And Orchestrator 触发 _finalize_pipeline_halted 或返工

  # P0
  Scenario: E-03 submit_review 五维一致性硬校验 — 维度不通过禁止整体"通过"
    Given reviewer 试图调用 submit_review(status="通过", dimensions={banned_words:"不通过", brand_tone:"通过", ...})
    When submit_review.execute 进入维度一致性校验
    Then 返回错误字符串 "错误: 存在不通过维度 ['banned_words']，审核结论不能为「通过」"
    And Bitable 不被写入
    And LLM 在下一轮工具反馈中收到该错误并修正 status 为"需修改"或"驳回"

  # P0
  Scenario: E-04 driver 返工 — pass_rate 低于阈值且未达上限，状态回退到「撰写中」
    Given reviewer 阶段完成，pass_rate=0.4，_review_threshold=0.6
    And self.reviewer_retries=0，REVIEW_MAX_RETRIES=2
    And 无红线命中
    When Orchestrator._handle_reviewer_retries 被调用
    Then self.reviewer_retries 自增到 1
    And 调用 _pm.update_status("撰写中")
    And 广播 "触发返工重试 1/2" 卡片到飞书群
    And 流水线主循环继续，状态路由进入 copywriter

  # P0
  Scenario: E-05 红线一票否决 — 命中关键词时硬中止
    Given reviewer 在某条内容上写入 review_red_flag="发现严重合规风险：医疗化表述"
    When Orchestrator._handle_reviewer_retries 调用 _collect_review_red_flag
    Then _is_review_red_flag 判定 True（命中关键词 "严重合规风险" / "医疗化表述"）
    And self._review_red_flag 写入该红线文本
    And 项目状态被推到 "已驳回"，不进入返工
    And 广播红线告警卡片，色彩=red

  # ───────── P1 效果保障 ─────────

  # P1
  Scenario: E-06 verify 卡口 — content 表 review_status/review_feedback 空时触发补充循环
    Given reviewer 第一轮结束后，某条内容行 review_status 字段仍为空
    When BaseAgent._verify_plan 校验 verify={table:"content", check_fields:["review_status","review_feedback"]}
    Then 返回 verified=False
    And Agent 进入补充循环，prompt 列出未填的 content_record_id

  # P1
  Scenario: E-07 重试达上限强制推进 — 第 2 次仍未达标也推到排期
    Given self.reviewer_retries=2，REVIEW_MAX_RETRIES=2
    And pass_rate=0.4，仍低于阈值 0.6
    When _handle_reviewer_retries 被调用
    Then 不再触发返工
    And 调用 _pm.update_status("排期中")
    And 广播 "重试已达上限 2，强制推进到排期阶段" 提示

  # P1
  Scenario: E-08 阈值分型 — 母婴项目阈值=0.8 比电商大促=0.6 更严
    Given 项目类型="母婴"，pass_rate=0.7
    When _get_review_threshold 读取 REVIEW_THRESHOLDS_BY_PROJECT_TYPE["母婴"]
    Then _review_threshold=0.8
    And pass_rate=0.7 < 0.8 → 触发返工
    But 同样 pass_rate=0.7 在电商大促项目下不触发返工（阈值 0.6）

  # P1
  Scenario: E-09 submit_review violated_rules 类型校验 — 必须为字符串数组
    Given reviewer 试图调用 submit_review(violated_rules="广告法违规")（字符串而非数组）
    When submit_review.execute 类型校验
    Then 返回错误 "错误: violated_rules 必须是字符串数组"
    And LLM 在下一轮修正为 violated_rules=["广告法违规"]

  # P1
  Scenario: E-10 submit_review feedback 非空校验 — 需修改/驳回时 feedback 必填
    Given reviewer 试图调用 submit_review(status="需修改", feedback="")
    When submit_review.execute 进入反馈校验
    Then 返回错误 "错误: status 为「需修改」时 feedback 不能为空"
    And Bitable 不被写入

  # P1
  Scenario: E-11 预检结果作为提示而非结论 — 序号"第一"上下文不视为违规
    Given 内容行 notes 字段含 "[预检] 命中禁用词：第一（共1次）"
    And draft 正文中"第一"用于列举（"第一点是...第二点是..."），无任何排名/比较语义
    When reviewer 综合判断 banned_words 维度
    Then submit_review 时 banned_words="通过"
    And feedback 中明确写明 "预检命中'第一'，但上下文为列举序号，不构成违规"

  # P1
  Scenario: E-12 规则检索强制约束 — reviewer 必须先调 search_knowledge 才开审核
    Given reviewer 完整执行
    When 复盘 tool_calls 时间序列
    Then 在第一次 submit_review 之前，至少有一次 search_knowledge(query 含 "广告法"/"禁用词"/平台名)
    And 至少有一次 read_knowledge(path 指向 knowledge/01_审核库/*.md)

  # P1
  Scenario: E-13 逐条独立调用 — N 条成稿对应 N 次 submit_review
    Given 内容排期表有 3 行成稿（无空 draft）
    When reviewer 完整执行
    Then submit_review 调用次数恰好=3
    And 三次调用的 content_record_id 两两不同
    And 不出现单次 submit_review 包含多个 record_id 或批量审核

  # P1
  Scenario: E-14 max_iterations=14 — 审核截断时未提交的内容行被识别
    Given reviewer soul.md max_iterations=14
    And 内容行有 5 条，14 轮内只完成 3 条 submit_review
    When ReAct 循环退出
    Then AgentResult.output 以 "[TRUNCATED:" 开头
    And Plan-Verify 识别出剩余 2 条 review_status 为空
    And 进入补充循环或抛 verify 失败给 Orchestrator

  # ───────── P2 锦上添花 ─────────

  # P2
  Scenario: E-15 经验回写 — reviewer 驳回后将经验通过 write_wiki 落 06 收件箱
    Given reviewer 给出至少一条 status="驳回" 的审核
    When reviewer 阶段结束 + Orchestrator 触发链路 A 经验蒸馏
    Then knowledge/06_待整理收件箱/ 下新增至少一个 .md 文件
    And 该文件 frontmatter 包含 applicable_roles=["reviewer", "copywriter"]
    And 文件正文包含 lesson 字段且来自审核反馈

  # P2
  Scenario: E-16 预检词表 mtime 失效缓存 — 词表文件修改后 reviewer 看到新词
    Given preflight_lint._CACHED_WORDS 已缓存 100 个词
    When knowledge/04_服务方法论/广告法禁用词.md 被修改（mtime 改变）
    Then 下次 scan_forbidden_words 触发 _load_words
    And 缓存被重新解析，新增词条立即生效

  # P2
  Scenario: E-17 红线否定信号识别 — review_red_flag="无" 不触发硬中止
    Given 项目主表 review_red_flag 字段="无"
    When _is_review_red_flag 判断
    Then 返回 False
    And 不进入红线一票否决分支，按 pass_rate 走常规返工逻辑

  # P2
  Scenario: E-18 工具白名单约束 — reviewer 不可调用 batch_create_content
    Given reviewer soul.md tools 列表不含 batch_create_content
    When LLM 试图返回 tool_call={name:"batch_create_content"}
    Then schema 不存在该工具
    And reviewer 不会越级改内容矩阵
```

**Module E 摘要**：共 18 个场景，P0=5 / P1=9 / P2=4。锚点覆盖 `agents/reviewer/soul.md` 五维流程、`tools/submit_review.py` 三层校验（status enum + violated_rules 类型 + 维度一致性 + feedback 非空）、`orchestrator._handle_reviewer_retries` 返工/红线/达上限三分支、`REVIEW_THRESHOLDS_BY_PROJECT_TYPE` 阈值分型、`tools/preflight_lint.py` mtime 缓存。

> **审核是返工链路的源头**，E-02（必调工具契约）+ E-03（维度一致性）+ E-04（返工触发）+ E-05（红线一票否决）+ E-07（达上限强推）形成完整闭环。决赛 Demo 走"驳回 1 次 → 文案修改 → 再审通过"是最常见路径，E-04/E-07 拉通这条主线。

---

## 模块 F — 项目经理（排期 + 交付摘要）

```gherkin
Feature: 项目经理 Agent（project_manager）+ 交付文档生成

  # ───────── P0 必过 ─────────

  # P0
  Scenario: F-01 happy path — 通过内容全部排期 + 交付摘要 + 推到「已完成」
    Given 项目主表 status="排期中"
    And 内容排期表 4 行成稿，其中 3 行 review_status="通过"，1 行 review_status="驳回"
    When 调用 BaseAgent(role_id="project_manager").run()
    Then 3 行通过内容 publish_date 字段非空且各不相同（节奏分布）
    And 1 行驳回内容 publish_date 字段保持为空
    And 项目主表 delivery 字段非空
    And delivery 文本包含 "交付摘要" 标题段落
    And 项目主表 status="已完成"

  # P0
  Scenario: F-02 不可越权 — 不为 review_status="驳回" 的内容强行排期
    Given 一行 review_status="驳回" 的内容
    When project_manager 完整执行
    Then 该行 publish_date 字段保持为空（或为原值不变）
    And 工具调用记录中不存在针对该 record_id 的 write_content(field="publish_date") 调用

  # P0
  Scenario: F-03 verify 卡口 — delivery 字段空时触发补充循环
    Given project_manager 第一轮 ReAct 结束，项目主表 delivery 字段仍为空
    When BaseAgent._verify_plan 校验 verify={table:"project", check_fields:["delivery"]}
    Then 返回 verified=False
    And Agent 进入补充循环（最多 2 次），prompt 显式要求补齐 delivery_summary

  # P0
  Scenario: F-04 完成度护栏 — 可排期内容为 0 时不得推进到「已完成」
    Given 内容排期表全部行 review_status ∈ {"驳回", "需修改"}（无任何"通过"）
    When project_manager 试图调用 update_status("已完成")
    Then 按 soul.md 状态流转规则不应推进
    And 实际推到 "已完成" 时，pipeline 收尾五判据校验仍因 ok_count/pass_rate 失败而落入 pipeline.aborted
    And 不会误发 pipeline.completed 事件

  # P0
  Scenario: F-05 工具白名单约束 — PM 不可调用 submit_review
    Given project_manager soul.md tools 列表不含 submit_review
    When LLM 试图返回 tool_call={name:"submit_review"}
    Then ToolRegistry 中无 submit_review schema
    And PM 不会越权改写审核结论

  # ───────── P1 效果保障 ─────────

  # P1
  Scenario: F-06 write_project delivery_summary 字段映射到 Bitable「交付摘要」列
    Given project_manager 调用 write_project(field_name="delivery_summary", content="# 交付摘要...")
    When write_project.execute 进入 _WRITERS 路由
    Then 实际调用 ProjectMemory.write_delivery
    And Bitable 项目主表「交付摘要」字段（FIELD_MAP_PROJECT["delivery"]）被写入

  # P1
  Scenario: F-07 排期节奏 — 多条内容不全部堆同一天
    Given 4 条审核通过内容
    When project_manager 完成排期
    Then 4 个 publish_date 中不同日期数 ≥ 2
    And 同一平台同一类型下相邻两条内容发布日期间隔 ≥ 1 天（除非项目类型="电商大促"集中爆发）

  # P1
  Scenario: F-08 max_iterations=6 — PM 在 6 轮内完成
    Given project_manager soul.md max_iterations=6
    When LLM 在第 6 轮仍未给出 final answer
    Then ReAct 循环退出
    And AgentResult.output 以 "[TRUNCATED:" 开头
    And 已写入的 publish_date 不被回滚

  # P1
  Scenario: F-09 交付文档生成 — 五判据通过后自动在飞书知识空间建文档
    Given DELIVERY_DOC_ENABLED=true 且 WIKI_SPACE_ID 已配置
    And 流水线收尾 is_truly_completed=True
    When orchestrator.py 1615 行触发 _generate_delivery_document(project_name)
    Then 返回非空 doc_url
    And 广播事件 "delivery_doc.created"，payload 含 url 与 project_name
    And 飞书知识空间「项目交付文档」父节点下新增一个子节点，title 含项目名

  # P1
  Scenario: F-10 交付文档父节点缓存 — 多次运行不重复创建父节点
    Given 同一 Orchestrator 进程已为项目 A 生成过交付文档，Orchestrator._delivery_parent_token 已缓存
    When 项目 B 进入收尾触发 _get_delivery_parent_token
    Then 直接返回缓存的 _delivery_parent_token
    And 不再调用 wiki.create_node 创建父节点
    And 飞书知识空间「项目交付文档」节点不会被重复创建

  # P1
  Scenario: F-11 交付文档开关关闭时跳过 — DELIVERY_DOC_ENABLED=false 不报错
    Given DELIVERY_DOC_ENABLED=false
    And 流水线 is_truly_completed=True
    When 收尾分支检查
    Then _generate_delivery_document 不被调用
    And 不发布 delivery_doc.created 事件
    And 流水线仍正常发 pipeline.completed

  # P1
  Scenario: F-12 WIKI_SPACE_ID 未配置时跳过 — 不阻断流水线 completed
    Given DELIVERY_DOC_ENABLED=true 但 WIKI_SPACE_ID=""
    When 收尾分支检查
    Then _generate_delivery_document 不被调用
    And pipeline.completed 仍正常发布
    And 不抛 AttributeError 或 KeyError

  # P1
  Scenario: F-13 交付文档失败不阻断收尾 — wiki API 报错时降级为日志
    Given DELIVERY_DOC_ENABLED=true，WIKI_SPACE_ID 已配置
    And feishu/wiki.py 在创建子节点时抛 FeishuAPIError
    When orchestrator 1615 行 try/except 捕获
    Then 日志记录错误，但不向上抛
    And pipeline.completed 事件仍正常发布
    And 项目主表 status 仍为 "已完成"

  # ───────── P2 锦上添花 ─────────

  # P2
  Scenario: F-14 交付摘要内容包含 soul.md 规定的 5 段结构
    Given project_manager 完成 write_project(delivery_summary)
    When 从 Bitable 读取 delivery 字段内容
    Then 文本依次包含段落标题 "项目完成情况" / "内容交付概览" / "排期结果" / "风险与说明" / "结论"
    And 文本长度 ≥ 200 字（避免敷衍式摘要）

  # P2
  Scenario: F-15 已有发布日期不被覆盖
    Given 一条内容行 publish_date 已被人工预填 "2026-05-15"
    When project_manager 排期
    Then 该行 publish_date 保持 "2026-05-15"
    And 不出现 write_content(content_record_id=该行, field="publish_date") 调用

  # P2
  Scenario: F-16 平台分布写入交付摘要
    Given 4 条通过内容，platform 分布={"小红书":3, "抖音":1}
    When project_manager 写 delivery_summary
    Then 摘要文本包含 "平台分布" 段落
    And 摘要中明示 "小红书: 3" 和 "抖音: 1" 或等价表述

  # P2
  Scenario: F-17 经验池白名单 — PM 不入 L2 经验池
    Given EXPERIENCE_POOL_ROLE_ALLOWLIST="account_manager,strategist,reviewer"
    When project_manager 阶段结束触发 Hook 自省
    Then ExperienceManager 不向 Bitable 经验池 / Chroma 写入新经验
    And PM 的 _hook_reflect 输出仅留在日志，不持久化
```

**Module F 摘要**：共 17 个场景，P0=5 / P1=8 / P2=4。锚点覆盖 `agents/project_manager/soul.md` 工作流、`tools/write_project.py` enum 与字段映射、`orchestrator._generate_delivery_document` 完整链路（父节点缓存 + 开关 + 失败兜底）、PM 越权护栏（驳回内容不排期、不调 submit_review、不入经验池）。

> **PM 是最薄角色**（max_iterations=6，工具白名单 6 个），但负责"五判据通过 → 交付文档发布"的最后一公里，是 Demo 收口的临门一脚。F-09/F-10/F-11/F-12/F-13 五条专门拉通交付文档生成链路的所有分支，避免决赛现场因 wiki API 失败导致 pipeline.completed 看不到尾。

---

## 模块 G — 经验闭环（沉淀 + 检索注入 + 去重合并）

```gherkin
Feature: L2 经验池（蒸馏 + Bitable/Chroma 双写 + 检索注入 + 桶合并）

  # ───────── P0 必过 ─────────

  # P0
  Scenario: G-01 happy path — 审核驳回触发 Chain A 经验蒸馏并双写
    Given 项目 recG01 有一条 review_status="驳回" 的内容，feedback 含 "广告法禁用词：最有效"
    And EXPERIENCE_POOL_ROLE_ALLOWLIST 包含 reviewer
    When Orchestrator 调用 _distill_experience(chain="A", ...) 后 ExperienceManager.save_experience 执行
    Then Bitable 经验池表新增 record，FE["role"]="reviewer" 和 "copywriter" 各一条（按 applicable_roles 扇出）
    And Chroma 经验集合 "experiences" 新增对应文档，metadata.confidence ≥ EXPERIENCE_CONFIDENCE_THRESHOLD=0.75
    And 同时在 knowledge/06_待整理收件箱/{category}/ 下生成 .md 文件
    And 该文件 frontmatter.applicable_roles 包含 ["reviewer", "copywriter"]

  # P0
  Scenario: G-02 经验注入 — get_experience 命中后 use_count 自增
    Given 经验池 Bitable 有一条 record_id=recE01，role=strategist，confidence=0.9，use_count=3
    And Chroma 集合中存在对应 id 的向量
    When strategist Agent 调用 get_experience(role_id="strategist", task_context="新品发布")
    Then 返回结果包含该条经验
    And Bitable 中 recE01 的 use_count 字段被更新为 4
    And Chroma metadata.use_count 不被更新（只 Bitable 是权威源）

  # P0
  Scenario: G-03 置信度阈值过滤 — 低于 0.75 的经验不进入 query_top_k 结果
    Given 经验池有 5 条 role=reviewer 的记录，confidence 分别 0.9/0.8/0.7/0.6/0.5
    When reviewer 调用 get_experience(role_id="reviewer", task_context="电商大促")
    Then 返回结果只包含 confidence ∈ {0.9, 0.8} 的两条
    And confidence < 0.75 的三条被过滤

  # P0
  Scenario: G-04 经验池白名单 — copywriter / project_manager 不入 L2
    Given EXPERIENCE_POOL_ROLE_ALLOWLIST="account_manager,strategist,reviewer"
    And copywriter 完成阶段触发 Hook 自省
    When orchestrator 经验沉淀分支判断 role_id ∉ ALLOWLIST
    Then ExperienceManager.save_experience 不被调用
    And Bitable 经验池表无新增 copywriter 角色记录
    And Chroma 集合不新增对应文档

  # P0
  Scenario: G-05 语义去重 — 新经验与旧经验相似度 > 0.85 时按置信度仲裁
    Given Chroma 中已有 record_id=recE_old, role=strategist, lesson="先调研竞品再定平台配比"，confidence=0.7
    When 新经验 lesson="调研竞品后再决定平台分配比例"，confidence=0.85 写入
    Then store.query 返回 similarity > 0.85
    And 新经验 confidence > 旧 → 删除 recE_old（Chroma + Bitable 同步删）
    And 写入新经验
    But 若新经验 confidence=0.6 (< 旧 0.7) → 跳过写入，旧经验保留

  # ───────── P1 效果保障 ─────────

  # P1
  Scenario: G-06 卡片质量门 — lesson 字数 < 20 拒绝入库
    Given 蒸馏返回卡片 {situation:"...", action:"...", outcome:"...", lesson:"注意点", category:"电商大促"}
    When ExperienceManager.save_experience 进入 _is_lesson_quality_ok
    Then 返回 False，reason="lesson 字数不足 (3 < 20)"
    And Bitable 与 Chroma 均不写入
    And 日志记录 warning

  # P1
  Scenario: G-07 卡片质量门 — lesson 缺可操作词拒绝入库
    Given 卡片 lesson="审核流程很重要需要仔细注意"（无"先/必须/避免/不要/当…时/应该/禁止/建议"任一）
    When _is_lesson_quality_ok 检查
    Then 返回 False，reason="lesson 缺少可操作词"
    And 不入库

  # P1
  Scenario: G-08 卡片质量门 — lesson 与 situation 重叠率 ≥ 60% 拒绝入库
    Given 卡片 lesson 与 situation 字段 Jaccard 重叠率 = 65%
    When _is_lesson_quality_ok 检查
    Then 返回 False，reason 含 "重叠率过高 (65% >= 60%)"
    And 不入库

  # P1
  Scenario: G-09 桶大小超限自动合并 — 同 role+category 超过 3 条触发 optimize_bucket
    Given 经验池中 role=strategist & category=电商大促 已有 3 条
    When 第 4 条经验写入成功后
    Then _auto_check_and_optimize_bucket 被自动触发（count > EXPERIENCE_MAX_PER_CATEGORY=3）
    And optimize_bucket 先调用 _deduplicate_bucket_records 删重复
    And 仍 > 3 条则调用 _merge_bucket_records 让 LLM 合并为 1-2 条
    And 原 4 条记录被删除，新 1-2 条精炼版被写入
    And source_stage 字段被标记为 "experience_optimizer"

  # P1
  Scenario: G-10 桶去重 — Jaccard > 0.85 时较低置信度版本被删
    Given 桶内 2 条经验：A(conf=0.8, use=3) 和 B(conf=0.6, use=1)
    And A.lesson 与 B.lesson Jaccard 相似度 = 0.9
    When _deduplicate_bucket_records 处理
    Then _choose_duplicate_loser 选 B（confidence 低，use_count 低）
    And B 被从 Bitable + Chroma + 本地 wiki 三处删除
    And A 保留

  # P1
  Scenario: G-11 query_top_k 读时校验架构 — Bitable status="禁用" 的不出现在结果
    Given 经验池 recE_disabled status="禁用"，Chroma 中向量仍存在
    When 调用 query_top_k(role_id, task_brief)
    Then Chroma 召回 20 条候选包含 recE_disabled
    And Bitable batch_get_records 拉到 fields[status]="禁用"
    And 该记录被过滤掉，不出现在返回结果中

  # P1
  Scenario: G-12 Bitable 写失败但 Chroma 写成功 — 两路独立
    Given Bitable 经验池表 API 抛 FeishuAPIError
    When ExperienceManager.save_experience 执行
    Then Bitable 写入分支记录 warning
    And Chroma 写入仍然成功，id 以 "chroma-" 前缀生成（MD5 fallback）
    And 函数不抛异常向上，返回 record_id=None
    And 主流程不被阻断

  # P1
  Scenario: G-13 _distill_experience 解析失败返回 None
    Given LLM 蒸馏返回非 JSON 文本（如 markdown 文字）
    When orchestrator._distill_experience 调用 json.loads
    Then 函数返回 None
    And 上游 try/except 捕获，仅打 warning "经验蒸馏失败"
    And 不触发 save_experience，不阻断收尾

  # P1
  Scenario: G-14 Chain A vs Chain B 路由 — 审核驳回走 A，人审修改走 B
    Given 收尾分支收集到 review_feedback 字段（来自审核驳回）
    When orchestrator 调用 _distill_experience(chain_id="A", ...)
    Then prompt 模板使用 _DISTILL_PROMPT_CHAIN_A
    And 强制 applicable_roles=["reviewer","copywriter"]
    But human_feedback 字段非空（来自人审修改）时
    Then chain_id="B"，模板用 _DISTILL_PROMPT_CHAIN_B
    And 强制 applicable_roles=["account_manager"]

  # P1
  Scenario: G-15 经验 wiki 双写 — save_to_wiki 落 06 收件箱并 mark_dirty
    Given 卡片质量校验通过，confidence=0.8
    When ExperienceManager.save_to_wiki 执行
    Then knowledge/06_待整理收件箱/{sanitize(category)}/{sanitize(title)}.md 文件被创建
    And 文件 frontmatter 含 category / role / confidence
    And 文件正文含 "## 溯源 / ## 场景 / ## 策略 / ## 结果 / ## 经验教训" 五段
    And mark_dirty 在 base_path 中标记该 rel_path 为待同步

  # P1
  Scenario: G-16 query_top_k 降级 — Bitable 批量查失败时回落到 Chroma metadata
    Given Chroma 召回 5 条候选
    And BitableClient.batch_get_records 抛 FeishuAPIError
    When query_top_k 进入合并逻辑
    Then 批量查空字典 → confidence 从 Chroma metadata 读取
    And 仍按 confidence 过滤 + 排序
    And 不抛异常，returns 非空 list

  # P1
  Scenario: G-17 EXPERIENCE_TOP_K=5 默认 — 不传 k 时返回 5 条
    Given 经验池有 10 条 confidence ≥ 0.75 的 strategist 经验
    When get_experience 不传 k 参数
    Then 实际返回结果长度=5（EXPERIENCE_TOP_K 默认）
    And 按 Bitable.confidence 降序排列

  # ───────── P2 锦上添花 ─────────

  # P2
  Scenario: G-18 lesson 压缩 — 合并后 lesson > 200 字时压缩到 ≤ 100 字
    Given 桶合并 LLM 返回 lesson=350 字
    When _compress_lesson 处理
    Then 触发压缩（长度 > MERGED_LESSON_COMPRESS_TRIGGER=200）
    And 优先保留含动作词（先/优先/必须/避免/检查...）的句子
    And 输出长度 ≤ MERGED_LESSON_MAX_LEN=100

  # P2
  Scenario: G-19 applicable_roles 扇出 — 一张卡同时写入两个角色行
    Given 卡片 applicable_roles=["reviewer", "copywriter"]
    When save_experience 执行
    Then Bitable 经验池表新增恰好 2 条 record
    And 两条记录 FE["role"] 分别为 "reviewer" 和 "copywriter"
    And Chroma 也新增 2 条文档（不同 id 但同样的 lesson）

  # P2
  Scenario: G-20 Chroma fallback id — Bitable 表未配置时用 MD5 兜底
    Given EXPERIENCE_TABLE_ID="" 或 "tblxxx..."（未配置）
    When save_experience 执行
    Then Bitable 写入跳过（_table_configured=False）
    And Chroma 仍写入，id="chroma-{md5(role::category::lesson)[:16]}"
    And 后续 query_top_k 能召回（chroma- 前缀的记录用 metadata 降级）

  # P2
  Scenario: G-21 cosine 距离与相似度换算正确
    Given Chroma 集合 metadata={hnsw:space: cosine}
    When store.query 返回 distance=0.12
    Then similarity = 1 - 0.12 = 0.88
    And similarity > EXPERIENCE_SIMILARITY_DEDUP_THRESHOLD=0.85
    And 触发去重分支
```

**Module G 摘要**：共 21 个场景，P0=5 / P1=12 / P2=4。锚点覆盖 `memory/experience.py` 全部主路径（双写、质量门两层、桶合并、读时校验架构、扇出、降级）、`memory/experience_store.py` Chroma cosine 距离换算、`orchestrator._distill_experience` Chain A/B 双链路、`EXPERIENCE_POOL_ROLE_ALLOWLIST` 角色过滤、`EXPERIENCE_MAX_PER_CATEGORY=3` 自动合并触发。

> **经验闭环是项目最有"AI 自进化"含量的部分**。G-01/G-02/G-05 是 Demo 最容易出彩的路径："驳回 → 蒸馏 → 入池 → 下个项目检索复用 → 真去重"。决赛现场如果能复演这条链路，比喊"多 Agent 协作"更有说服力。G-09/G-10/G-11 验证桶合并和读时校验，这是项目敢宣称"自进化"的底层逻辑。

---

---
