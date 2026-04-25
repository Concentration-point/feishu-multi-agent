# 飞书·智组织 — 项目待办清单

> 生成时间: 2026-04-16
> 基于 CLAUDE.md 全案架构 + 实际代码审查

---

## 阶段一：Bitable 共享记忆层 ✅

### P1-T01: 实现 TokenManager 单例 + 自动刷新
- **描述**: 在 `feishu/auth.py` 中实现 `TokenManager` 类，使用 `__new__` 实现单例模式，缓存 `tenant_access_token`，有效期内复用，过期前 60s 自动刷新
- **文件**: `feishu/auth.py`
- **依赖**: 无
- **验收**:
  - `TokenManager()` 多次调用返回同一实例
  - `get_token()` 返回有效 token
  - 第二次调用命中缓存不发网络请求
  - 过期前 60s 触发刷新
  - 飞书返回非 0 code 时抛出 `FeishuAuthError`
- **耗时**: 1h
- **状态**: ✅

### P1-T02: 实现 BitableClient CRUD 封装
- **描述**: 在 `feishu/bitable.py` 中实现 `BitableClient` 类，封装多维表格的 `get_record` / `list_records` / `create_record` / `batch_create_records` / `update_record` / `delete_record` 六个方法，统一错误处理和 `rich_text_to_str` 富文本转换
- **文件**: `feishu/bitable.py`
- **依赖**: P1-T01
- **验收**:
  - 单条读取返回 fields 字典且富文本已转纯字符串
  - 列表查询支持 filter + 自动分页
  - 创建返回 record_id
  - 批量创建返回 record_id 列表
  - 更新/删除操作正常
  - HTTP 非 200 或 code != 0 时抛出 `FeishuAPIError`
- **耗时**: 2h
- **状态**: ✅

### P1-T03: 配置模块 config.py
- **描述**: 实现 `config.py`，从 `.env` 加载环境变量，定义飞书凭证、多维表格 ID、LLM 配置、字段映射 (`FIELD_MAP_PROJECT` / `FIELD_MAP_CONTENT` / `FIELD_MAP_EXPERIENCE`)、状态机常量 (`STATUS_*` / `VALID_STATUSES`)
- **文件**: `config.py`
- **依赖**: 无
- **验收**:
  - 所有常量可正常 import
  - 字段映射覆盖 CLAUDE.md 中三张表的全部字段
  - 状态机 7+1 个状态定义完整
  - `.env` 不存在时有默认空值不报错
- **耗时**: 0.5h
- **状态**: ✅

### P1-T04: .env.example 配置模板
- **描述**: 创建 `.env.example` 文件，包含所有环境变量的占位说明
- **文件**: `.env.example`
- **依赖**: P1-T03
- **验收**:
  - 包含 FEISHU_APP_ID / FEISHU_APP_SECRET / BITABLE_APP_TOKEN / 三个 TABLE_ID / LLM 配置 / CHAT_ID / WIKI_SPACE_ID
  - 每个变量有注释说明获取方式
- **耗时**: 0.5h
- **状态**: ✅

### P1-T05: ProjectMemory 项目主表语义化封装
- **描述**: 在 `memory/project.py` 中实现 `ProjectMemory` 类和 `BriefProject` 数据类，提供 `load()` 全量加载、单字段读取 (`get_brief` / `get_brand_tone` 等)、语义化写入 (`write_brief_analysis` / `write_strategy` / `write_review_summary` / `write_delivery` / `write_knowledge_ref`)、`update_status()` 状态更新
- **文件**: `memory/project.py`
- **依赖**: P1-T02
- **验收**:
  - `load()` 返回完整 `BriefProject` dataclass
  - 各语义化方法正确映射字段名
  - `write_review_summary` 同时写通过率
  - 日期字段毫秒时间戳转换正确
- **耗时**: 1.5h
- **状态**: ✅

### P1-T06: ContentMemory 内容排期表语义化封装
- **描述**: 在 `memory/project.py` 中实现 `ContentMemory` 类和 `ContentItem` / `ContentRecord` 数据类，提供 `create_content_item` / `batch_create_content_items` / `list_by_project` / `write_draft` / `write_review` / `write_publish_date` 方法
- **文件**: `memory/project.py`
- **依赖**: P1-T02
- **验收**:
  - 单条/批量创建返回 record_id
  - `list_by_project` 按项目名过滤
  - 写成稿同时写字数
  - 写审核同时写状态和反馈
  - 发布日期 YYYY-MM-DD 转毫秒时间戳
- **耗时**: 1.5h
- **状态**: ✅

### P1-T07: 阶段一集成测试
- **描述**: 编写 `tests/test_bitable.py`，覆盖鉴权、项目主表 CRUD、内容排期表 CRUD、ProjectMemory 语义化读写、ContentMemory 语义化读写
- **文件**: `tests/test_bitable.py`
- **依赖**: P1-T01 ~ P1-T06
- **验收**:
  - 所有测试用例通过
  - 测试报告输出通过/失败统计
- **耗时**: 1h
- **状态**: ✅

---

## 阶段二：Agent 框架 + 工具系统 ✅

### P2-T01: ToolRegistry 自动发现 + AgentContext
- **描述**: 在 `tools/__init__.py` 中实现 `ToolRegistry` 类（自动扫描 `tools/` 下所有 `.py` 文件的 `SCHEMA` 和 `execute`）和 `AgentContext` 数据类 (`record_id` / `project_name` / `role_id`)
- **文件**: `tools/__init__.py`
- **依赖**: 无
- **验收**:
  - `ToolRegistry()` 初始化时自动发现所有工具
  - `tool_names` 属性返回完整列表
  - `get_tools(names)` 返回过滤后的 OpenAI function calling 格式 schema
  - `call_tool(name, params, ctx)` 调用工具返回字符串
  - 不存在的工具返回友好错误消息
- **耗时**: 1h
- **状态**: ✅

### P2-T02: read_project 工具
- **描述**: 实现项目主表读取工具，支持一次读取多个字段，返回 JSON
- **文件**: `tools/read_project.py`
- **依赖**: P1-T05, P2-T01
- **验收**:
  - SCHEMA 定义 fields 数组参数
  - 支持 brief_content / brand_tone / status 等字段别名
  - 未知字段返回错误提示而非崩溃
- **耗时**: 0.5h
- **状态**: ✅

### P2-T03: write_project 工具
- **描述**: 实现项目主表写入工具，支持 brief_analysis / strategy / review_summary / review_pass_rate / delivery_summary / knowledge_ref 六个字段
- **文件**: `tools/write_project.py`
- **依赖**: P1-T05, P2-T01
- **验收**:
  - review_summary 自动解析通过率
  - review_pass_rate 支持 "75%" 和 "0.75" 两种格式
  - knowledge_ref 按换行拆分为列表
  - 不支持的字段返回错误
- **耗时**: 1h
- **状态**: ✅

### P2-T04: update_status 工具（带状态机校验）
- **描述**: 实现项目状态更新工具，内置状态流转合法性校验
- **文件**: `tools/update_status.py`
- **依赖**: P1-T05, P2-T01
- **验收**:
  - 合法流转（如待处理→解读中）成功
  - 非法流转（如待处理→审核中）返回错误
  - 审核中可回退到撰写中
- **耗时**: 0.5h
- **状态**: ✅

### P2-T05: list_content 工具
- **描述**: 列出当前项目的所有内容排期行
- **文件**: `tools/list_content.py`
- **依赖**: P1-T06, P2-T01
- **验收**:
  - 自动按 project_name 过滤
  - 返回完整 ContentRecord JSON 数组
- **耗时**: 0.5h
- **状态**: ✅

### P2-T06: create_content 工具
- **描述**: 创建单条内容排期行
- **文件**: `tools/create_content.py`
- **依赖**: P1-T06, P2-T01
- **验收**:
  - SCHEMA 包含 title / platform / content_type / key_message / target_audience / sequence 六个必填参数
  - 自动关联当前项目名
  - 返回 record_id
- **耗时**: 0.5h
- **状态**: ✅

### P2-T07: batch_create_content 工具
- **描述**: 批量创建多条内容排期行
- **文件**: `tools/batch_create_content.py`
- **依赖**: P1-T06, P2-T01
- **验收**:
  - 接受 items 数组
  - 返回 record_ids 列表
  - 空数组返回错误
- **耗时**: 0.5h
- **状态**: ✅

### P2-T08: write_content 工具
- **描述**: 更新内容排期表的指定字段（draft_content / word_count / review_status / review_feedback / publish_date / notes）
- **文件**: `tools/write_content.py`
- **依赖**: P1-T06, P2-T01
- **验收**:
  - draft_content 写入同时自动计算字数
  - review_status 和 review_feedback 分别写入不覆盖另一字段
  - publish_date 接受 YYYY-MM-DD 格式
- **耗时**: 1h
- **状态**: ✅

### P2-T09: soul.md 解析器
- **描述**: 在 `agents/base.py` 中实现 `parse_soul()` 函数，解析 YAML frontmatter（不依赖 PyYAML，手动解析 key:value 和列表项）+ Markdown body
- **文件**: `agents/base.py`
- **依赖**: 无
- **验收**:
  - 正确解析 name / role_id / description / tools 列表 / max_iterations / body
  - tools 返回列表类型
  - max_iterations 返回整数
  - body 保留完整 Markdown 正文
- **耗时**: 1h
- **状态**: ✅

### P2-T10: 共享知识加载
- **描述**: 在 `agents/base.py` 中实现 `load_shared_knowledge()` 函数，扫描 `agents/_shared/*.md` 并拼接
- **文件**: `agents/base.py`
- **依赖**: P2-T14 ~ P2-T16（共享知识文件）
- **验收**:
  - 返回拼接后的字符串
  - 包含公司背景、SOP、质量标准
  - 文件不存在时返回空字符串
- **耗时**: 0.5h
- **状态**: ✅

### P2-T11: BaseAgent ReAct 循环引擎
- **描述**: 在 `agents/base.py` 中实现 `BaseAgent` 类核心：初始化（加载 soul.md + 共享知识 + 注册工具 + 创建 LLM 客户端）、`run()` 方法（加载项目上下文 → 装配 system prompt → ReAct 循环 → Hook 自省）
- **文件**: `agents/base.py`
- **依赖**: P2-T01, P2-T09, P2-T10
- **验收**:
  - `_build_system_prompt()` 拼接共享知识 + Soul + 项目上下文 + 经验
  - ReAct 循环正确处理 tool_calls 和纯文本输出
  - 达到 max_iterations 时强制结束
  - tool_call 的参数 JSON 解析失败不崩溃
  - 最终输出保存到 `_messages` 供 Hook 使用
- **耗时**: 3h
- **状态**: ✅

### P2-T12: Hook 自省蒸馏
- **描述**: 在 `BaseAgent` 中实现 `_hook_reflect()` 方法，复用 ReAct 历史上下文追加自省 prompt，要求 LLM 输出 SAOL 格式 JSON 经验卡片
- **文件**: `agents/base.py`
- **依赖**: P2-T11
- **验收**:
  - 返回包含 situation / action / outcome / lesson / category / applicable_roles 的字典
  - 清理 markdown 代码块包裹
  - 无效 category 兜底为 "未分类"
  - 当前角色 ID 加入 applicable_roles
  - JSON 解析失败返回 None 不影响主流程
- **耗时**: 1h
- **状态**: ✅

### P2-T13: 经验注入加载
- **描述**: 在 `BaseAgent` 中实现 `_load_experiences()` 方法，从经验池查询 top-K 经验拼为 prompt 段落
- **文件**: `agents/base.py`
- **依赖**: P6-T01（ExperienceManager）
- **验收**:
  - 查询 top-K 经验并格式化
  - 经验池无数据时返回空字符串
  - 异常不影响 Agent 启动
- **耗时**: 0.5h
- **状态**: ✅

### P2-T14: 共享知识 — company.md
- **描述**: 撰写 `agents/_shared/company.md`，包含公司定位、服务对象、核心业务、盈利方向、公司风格、通用规则、智能体角色介绍
- **文件**: `agents/_shared/company.md`
- **依赖**: 无
- **验收**:
  - 内容覆盖智策传媒完整背景
  - 包含五个角色的介绍和协作机制
  - 字数 > 500
- **耗时**: 1h
- **状态**: ✅

### P2-T15: 共享知识 — sop.md
- **描述**: 撰写 `agents/_shared/sop.md`，定义通用流程框架和各项目类型专用流程（电商大促、新品发布、品牌传播、日常运营等）
- **文件**: `agents/_shared/sop.md`
- **依赖**: 无
- **验收**:
  - 包含通用流程框架
  - 覆盖 10 个专用流程
  - 每个流程有完整的 Agent 协作链路
- **耗时**: 1.5h
- **状态**: ✅

### P2-T16: 共享知识 — quality_standards.md
- **描述**: 撰写 `agents/_shared/quality_standards.md`，定义绝对禁止项、各平台字数规范、内容质量要求、审核评分维度
- **文件**: `agents/_shared/quality_standards.md`
- **依赖**: 无
- **验收**:
  - 绝对禁止项列表完整
  - 5 个平台的字数规范表格
  - 6 项内容质量要求
  - 5 维审核评分及权重
- **耗时**: 0.5h
- **状态**: ✅

### P2-T17: 客户经理 soul.md
- **描述**: 撰写 `agents/account_manager/soul.md`，定义角色人格、核心职责、工作边界、Brief 解读报告格式、准入规则、状态流转规则、消息广播规则、工具使用要求
- **文件**: `agents/account_manager/soul.md`
- **依赖**: 无
- **验收**:
  - frontmatter 包含 name / role_id / description / tools / max_iterations
  - tools 列表只包含 read_project / write_project / update_status / send_message
  - body 定义完整的 7 节结构化 Brief 解读报告格式
  - 准入规则 6 项条件明确
- **耗时**: 1h
- **状态**: ✅

### P2-T18: 策略师 soul.md
- **描述**: 撰写 `agents/strategist/soul.md`，定义策略方案格式、内容任务拆解规则、策略制定原则
- **文件**: `agents/strategist/soul.md`
- **依赖**: 无
- **验收**:
  - tools 包含 read_project / write_project / update_status / batch_create_content / search_knowledge / send_message
  - 策略方案 7 节结构化格式
  - 内容任务拆解规则明确
- **耗时**: 1h
- **状态**: ✅

### P2-T19: 文案 soul.md
- **描述**: 撰写 `agents/copywriter/soul.md`，定义核心写作原则、单条成稿标准、各内容类型写作要求
- **文件**: `agents/copywriter/soul.md`
- **依赖**: 无
- **验收**:
  - tools 包含 read_project / list_content / write_content / update_status / search_knowledge / send_message
  - 文章类 / 短视频脚本类 / 社媒短文案类三种写作要求
  - 6 项核心写作原则
- **耗时**: 1h
- **状态**: ✅

### P2-T20: 审核 soul.md
- **描述**: 撰写 `agents/reviewer/soul.md`，定义 5 维审核维度、单条审核标准、审核总评格式、判定规则
- **文件**: `agents/reviewer/soul.md`
- **依赖**: 无
- **验收**:
  - tools 包含 read_project / list_content / write_content / write_project / update_status / send_message
  - 审核总评 4 节结构化格式
  - 通过 / 需修改 / 驳回三级判定标准
  - 60% 通过率阈值规则
- **耗时**: 1h
- **状态**: ✅

### P2-T21: 项目经理 soul.md
- **描述**: 撰写 `agents/project_manager/soul.md`，定义排期原则、交付摘要格式、完成条件
- **文件**: `agents/project_manager/soul.md`
- **依赖**: 无
- **验收**:
  - tools 包含 read_project / list_content / write_content / write_project / update_status / send_message
  - 交付摘要 5 节结构化格式
  - 5 项排期规则
  - 状态流转明确（排期中 → 已完成的条件）
- **耗时**: 1h
- **状态**: ✅

### P2-T22: 阶段二集成测试
- **描述**: 编写 `tests/test_agent.py`，覆盖 ToolRegistry 自动发现、soul.md 解析、共享知识加载、system prompt 装配、工具实际调用、ReAct 循环完整运行
- **文件**: `tests/test_agent.py`
- **依赖**: P2-T01 ~ P2-T21
- **验收**:
  - 6 组测试全部通过
  - ToolRegistry 发现 >= 10 个工具
  - soul.md 解析字段完整
  - system prompt >= 500 字
- **耗时**: 1h
- **状态**: ✅
- **备注**: 已完成 D-04 / D-05 审计修复验证：`requirements.txt` 已补 `pytest` 与 `pytest-asyncio`，`tests/test_framework.py` 的过时 stub 断言已改为真实工具行为校验；阶段二脚本式验收测试现通过 `tests/conftest.py` 显式排除，不再误被 pytest 收集

---

## 阶段三：Orchestrator 全流程编排 ✅

### P3-T01: Orchestrator 流水线核心
- **描述**: 在 `orchestrator.py` 中实现 `Orchestrator` 类，按 account_manager → strategist → copywriter → reviewer → project_manager 顺序执行五个 Agent，每个 Agent 的 pending_experience 暂存
- **文件**: `orchestrator.py`
- **依赖**: P2-T11
- **验收**:
  - 五个 Agent 按顺序执行
  - 每个阶段记录 `StageResult`（ok/fail/duration/output）
  - 异常不中断流水线
  - 返回 `list[StageResult]`
- **耗时**: 2h
- **状态**: ✅

### P3-T02: 审核驳回重试机制
- **描述**: 在 Orchestrator 中实现 reviewer 阶段的返工重试逻辑：审核通过率 < 60% 时回退到撰写中，重新跑 copywriter + reviewer，最多重试 2 次
- **文件**: `orchestrator.py`
- **依赖**: P3-T01
- **验收**:
  - 通过率 >= 60% 直接继续
  - 通过率 < 60% 状态改回 "撰写中" 并重跑 copywriter + reviewer
  - 最多 2 次重试后即使未达标也继续 project_manager
  - 重试期间的 pending_experience 也被收集
- **耗时**: 1.5h
- **状态**: ✅

### P3-T03: 经验统一沉淀逻辑
- **描述**: 在 Orchestrator 中实现 `_settle_experiences()` 方法：流水线结束后统一处理所有 Agent 的 pending_experience，置信度打分 → 阈值过滤 → 去重合并 → 双写（Bitable + Wiki）
- **文件**: `orchestrator.py`
- **依赖**: P3-T01, P6-T01
- **验收**:
  - `_calc_confidence()` 公式正确（pass_rate×0.4 + task_completed×0.3 + no_rework×0.2 + knowledge_cited×0.1）
  - 置信度 < 阈值的跳过
  - 同角色同分类超 3 条时触发 LLM 合并
  - 最终 print 沉淀统计
- **耗时**: 2h
- **状态**: ✅

### P3-T04: IM 广播集成
- **描述**: 在 Orchestrator 中实现 `_broadcast()` 方法，关键节点发送飞书卡片消息（新项目启动、各阶段完成/失败、审核驳回、项目交付）
- **文件**: `orchestrator.py`
- **依赖**: P5-T01
- **验收**:
  - FEISHU_CHAT_ID 未配置时 fallback 到 print
  - 配置了则调用 FeishuIMClient.send_card
  - 发送失败不影响流水线
- **耗时**: 1h
- **状态**: ✅

### P3-T05: CLI 入口 — run 命令
- **描述**: 在 `main.py` 中实现 CLI `run` 子命令，接受 record_id 参数，启动 Orchestrator + 后台 sync task
- **文件**: `main.py`
- **依赖**: P3-T01, P4-T06
- **验收**:
  - `python main.py run recXXX` 正常执行
  - 配置了 WIKI_SPACE_ID 时启动后台 sync
  - 流水线结束后手动 trigger 一次同步
  - 退出时 cancel 后台任务
- **耗时**: 1h
- **状态**: ✅

### P3-T06: CLI 入口 — sync 命令
- **描述**: 在 `main.py` 中实现 CLI `sync` 子命令，手动触发一次知识库同步
- **文件**: `main.py`
- **依赖**: P4-T06
- **验收**:
  - `python main.py sync` 执行一次同步
  - 未配置 WIKI_SPACE_ID 时给出提示
- **耗时**: 0.5h
- **状态**: ✅

### P3-T07: 全流程集成测试
- **描述**: 编写 `tests/test_pipeline.py`，创建测试 Brief → 跑 account_manager + strategist → 注入占位 draft → 跑 reviewer + project_manager → 验证所有字段填写完整
- **文件**: `tests/test_pipeline.py`
- **依赖**: P3-T01 ~ P3-T06
- **验收**:
  - 测试 Brief 成功创建
  - 五个阶段输出非空
  - Brief解读 / 策略方案 / 审核总评 / 交付摘要 全部填写
  - 内容行 >= 4 条
  - 通过内容有发布日期
  - 项目状态为 "已完成"
- **耗时**: 1.5h
- **状态**: ✅

---

## 阶段四：知识库系统 + 后台同步 ✅

### P4-T01: knowledge/ 种子文档
- **描述**: 在 `knowledge/raw/` 下撰写至少 2 篇完整的历史营销方案文档（如 618 电商全案、新品发布方案），每篇 > 500 字，包含目标、策略、内容矩阵、执行计划等完整结构
- **文件**: `knowledge/raw/某美妆品牌618电商营销全案.md`, `knowledge/raw/某母婴品牌新品发布传播方案.md`
- **依赖**: 无
- **验收**:
  - 每篇 > 500 字
  - 包含可被 search_knowledge 搜索的关键词（电商/种草/小红书等）
  - 结构完整可作为策略师参考
- **耗时**: 1.5h
- **状态**: ✅

### P4-T02: search_knowledge 工具
- **描述**: 实现本地知识库搜索工具，多关键词交集排序，返回 top-5 匹配文件的路径 + 命中数 + 上下文片段
- **文件**: `tools/search_knowledge.py`
- **依赖**: P4-T01
- **验收**:
  - 多关键词空格分隔
  - 按命中数降序
  - 每个结果包含 200 字上下文片段
  - 最多返回 5 个
  - 无结果返回友好提示
- **耗时**: 1h
- **状态**: ✅

### P4-T03: read_knowledge 工具
- **描述**: 实现读取指定知识文档全文的工具，超 3000 字截断
- **文件**: `tools/read_knowledge.py`
- **依赖**: P4-T01
- **验收**:
  - 正确读取 knowledge/{filepath}
  - 超 3000 字截断并提示
  - 文件不存在返回错误
- **耗时**: 0.5h
- **状态**: ✅
- **备注**: 已完成 D-01 审计修复，新增路径穿越防护（`resolve()` + `is_relative_to()`），当前只允许读取 knowledge/ 目录内文件

### P4-T04: write_wiki 工具
- **描述**: 实现 Wiki 写入工具：写入 knowledge/wiki/{category}/{title}.md，自动更新 _index.md，标记 .sync_state.json dirty
- **文件**: `tools/write_wiki.py`
- **依赖**: 无
- **验收**:
  - 自动创建目录
  - 文件包含 frontmatter（created / source / category）
  - _index.md 包含新条目
  - .sync_state.json 中 dirty=true
- **耗时**: 1h
- **状态**: ✅
- **备注**: 已完成 D-02 审计修复，新增非法字符拦截与 `resolve()` + `is_relative_to()` 路径边界校验，当前只允许写入 knowledge/wiki/ 目录内文件

### P4-T05: 飞书知识空间 API 封装
- **描述**: 在 `feishu/wiki.py` 中实现 `FeishuWikiClient`：`list_nodes`（带 5 分钟缓存）、`find_node_by_title`、`create_node`、`update_doc_content`（创建子 block 写入内容）
- **文件**: `feishu/wiki.py`
- **依赖**: P1-T01
- **验收**:
  - list_nodes 自动分页 + 缓存
  - find_node_by_title 支持按 parent_token 过滤
  - create_node 创建后清除缓存
  - update_doc_content 支持多段落写入
- **耗时**: 2h
- **状态**: ✅
- **备注**: 已完成 D-03 审计修复，`update_doc_content` 已改为覆盖式写入：同步前清空旧 children，再写入新内容，避免重复同步时内容堆叠

### P4-T06: WikiSyncService 后台同步
- **描述**: 在 `sync/wiki_sync.py` 中实现 `WikiSyncService`：定时扫描 dirty 文件 → 映射飞书节点路径 → 创建或更新文档 → 更新 sync_state
- **文件**: `sync/wiki_sync.py`
- **依赖**: P4-T05
- **验收**:
  - `start()` 无限循环定时扫描
  - `trigger()` 手动触发
  - `sync_once()` 只处理 dirty 文件
  - 本地目录映射到飞书节点层级
  - 单文件失败不影响其他文件
  - 失败文件保持 dirty 状态
- **耗时**: 2h
- **状态**: ✅
- **备注**: 已完成 D-03 审计修复验证，sync 侧继续调用 `update_doc_content`，现有更新路径已切换为覆盖模式，不再是纯追加写入

### P4-T07: 阶段四集成测试
- **描述**: 编写 `tests/test_knowledge.py`，覆盖种子文档验证、search/read/write_wiki 三个工具、WikiSync 同步
- **文件**: `tests/test_knowledge.py`
- **依赖**: P4-T01 ~ P4-T06
- **验收**:
  - 第一层（本地）不需飞书凭证
  - 第二层（同步）需要 WIKI_SPACE_ID
  - 测试后清理测试数据
- **耗时**: 1h
- **状态**: ✅

---

## 阶段五：IM 群聊 ✅

### P5-T01: FeishuIMClient 实现
- **描述**: 在 `feishu/im.py` 中实现 `FeishuIMClient`：`send_text`（纯文本）和 `send_card`（卡片消息，支持 title / content / color）
- **文件**: `feishu/im.py`
- **依赖**: P1-T01
- **验收**:
  - send_text 发送纯文本到 chat_id
  - send_card 发送带标题和颜色的卡片
  - API 错误时抛出 RuntimeError
  - 日志记录发送结果
- **耗时**: 1h
- **状态**: ✅

### P5-T02: send_message 工具完整实现
- **描述**: 在 `tools/send_message.py` 中实现完整的消息发送工具，支持 text/card 两种模式，自动添加角色名前缀，FEISHU_CHAT_ID 未配置时走 fallback
- **文件**: `tools/send_message.py`
- **依赖**: P5-T01
- **验收**:
  - SCHEMA 包含 message / message_type / title / color 四个参数
  - 只有 message 是 required（向后兼容）
  - 未配置 CHAT_ID 时 fallback 到日志记录
  - 发送失败返回错误信息不崩溃
- **耗时**: 0.5h
- **状态**: ✅

### P5-T03: 阶段五集成测试
- **描述**: 编写 `tests/test_im.py`，覆盖客户端实例化、SCHEMA 格式、向后兼容、真实发送消息
- **文件**: `tests/test_im.py`
- **依赖**: P5-T01, P5-T02
- **验收**:
  - 第一层不需飞书凭证
  - 第二层需要 FEISHU_CHAT_ID
  - 真实发送 3 种类型消息
- **耗时**: 0.5h
- **状态**: ✅
- **备注**: 已完成 D-04 审计修复验证：阶段五测试保留为脚本式验收测试，并通过 `tests/conftest.py` 显式排除，避免 pytest 误收集导致假失败

---

## 阶段六：L2 经验池 + 自进化 ✅

### P6-T01: ExperienceManager 实现
- **描述**: 在 `memory/experience.py` 中实现 `ExperienceManager`：`save_experience`（写 Bitable）、`save_to_wiki`（写本地 Wiki + dirty 标记 + 索引更新）、`query_top_k`（按 confidence×log 排序 + 使用次数 +1）、`check_dedup` + `merge_experiences`（LLM 合并同类经验）
- **文件**: `memory/experience.py`
- **依赖**: P1-T02, P4-T04
- **验收**:
  - save_experience 正确写入 Bitable（表未配置时跳过）
  - save_to_wiki 生成 frontmatter + SAOL 结构 + dirty 标记
  - query_top_k 按 confidence×(1+log(use_count+1)) 排序
  - 使用后 use_count +1
  - merge_experiences 调用 LLM 合并 + 真删除旧记录
  - 文件名安全字符清洗
- **耗时**: 3h
- **状态**: ✅

### P6-T02: get_experience 工具
- **描述**: 实现经验池查询工具，按 role_id + 可选 category 查询 top-K 经验
- **文件**: `tools/get_experience.py`
- **依赖**: P6-T01
- **验收**:
  - SCHEMA 包含 role_id（必填）和 category（可选）
  - 返回格式化的经验列表（置信度 + 场景 + 经验教训）
  - 无经验返回友好提示
- **耗时**: 0.5h
- **状态**: ✅

### P6-T03: 阶段六集成测试
- **描述**: 编写 `tests/test_experience.py`，三层测试：置信度打分 + Wiki 双写 + Hook 自省（本地）、Bitable 经验 CRUD + get_experience 工具（联调）、两次 Agent 运行的闭环对比（第一次沉淀 → 第二次注入）
- **文件**: `tests/test_experience.py`
- **依赖**: P6-T01, P6-T02
- **验收**:
  - 5 组置信度打分用例通过
  - Wiki 写入 + dirty 标记 + 索引更新
  - Bitable CRUD 后清理测试数据
  - 闭环对比：第二次运行前 _load_experiences 有内容
- **耗时**: 2h
- **状态**: ✅
- **备注**: 已完成 D-04 审计修复验证：阶段六测试保留为脚本式验收测试，并通过 `tests/conftest.py` 显式排除，避免 pytest 误收集导致假失败

---

## 阶段七：Webhook + Demo 打磨

### P7-T01: FastAPI Webhook 服务
- **描述**: 在 `main.py` 中添加 FastAPI 应用，实现 `/webhook/event` 端点接收飞书事件回调。处理 URL 验证 challenge、多维表格新增记录事件，提取 record_id 后异步触发 Orchestrator
- **文件**: `main.py`
- **依赖**: P3-T01
- **验收**:
  - `python main.py serve` 启动 uvicorn 服务
  - `/webhook/event` POST 端点正确处理 URL verification challenge
  - 接收到多维表格新增记录事件后异步启动流水线
  - 重复事件幂等处理（相同 record_id 不重复触发）
  - 启动时同时启动后台 sync task
- **耗时**: 2h
- **状态**: ⬜

### P7-T02: requirements.txt 补充 FastAPI 依赖
- **描述**: 在 `requirements.txt` 中添加 `fastapi` 和 `uvicorn[standard]` 依赖
- **文件**: `requirements.txt`
- **依赖**: 无
- **验收**:
  - `pip install -r requirements.txt` 后可以 `import fastapi`
  - `uvicorn` 命令可用
- **耗时**: 0.1h
- **状态**: ⬜

### P7-T03: L0 工作记忆 working.py 实现
- **描述**: 在 `memory/working.py` 中实现 L0 工作记忆管理。当前文件只有占位注释。需要实现 system prompt 组装辅助、ReAct 对话历史管理（可选：如果 BaseAgent 已在 run() 中内联管理了 messages，则此模块可作为可选的上下文窗口管理工具，例如长对话截断、token 统计等）
- **文件**: `memory/working.py`
- **依赖**: P2-T11
- **验收**:
  - 提供 prompt 段落拼接辅助函数
  - 或提供对话历史 token 统计和截断功能
  - 或明确标注此模块不需要（如果 BaseAgent 已完全内联处理）
- **耗时**: 1h
- **状态**: 🔨（当前为 stub）

### P7-T04: 飞书事件订阅配置文档
- **描述**: 补充飞书开放平台事件订阅的配置说明：如何在飞书开发者控制台设置事件订阅 URL、需要开通的权限、需要订阅的事件类型（bitable.record.created_v1）
- **文件**: 在 `.env.example` 中补充 WEBHOOK_* 相关配置说明
- **依赖**: P7-T01
- **验收**:
  - `.env.example` 包含 WEBHOOK_PORT / WEBHOOK_VERIFICATION_TOKEN 等
  - 有清晰的配置步骤说明
- **耗时**: 0.5h
- **状态**: ⬜

### P7-T05: Demo 演示脚本
- **描述**: 创建 `demo/run_demo.py` 脚本，自动化执行完整演示流程：创建测试 Brief → 等待/触发全流程 → 实时打印进度 → 最终汇总输出。支持 CLI 参数选择预设 Brief（电商大促/新品发布）
- **文件**: `demo/run_demo.py`
- **依赖**: P3-T01
- **验收**:
  - `python demo/run_demo.py --scene 电商大促` 运行完整 Demo
  - 实时输出每个 Agent 的进度和耗时
  - 最终输出完整的项目字段填充情况
  - 支持 `--record-id` 参数使用已有记录
- **耗时**: 1.5h
- **状态**: ⬜

### P7-T06: 演示用 Brief 测试数据
- **描述**: 在 `demo/briefs/` 下准备 2-3 份预设 Brief 数据（JSON 格式），覆盖电商大促、新品发布、品牌传播等场景，数据质量足以支撑 5-10 分钟的完整演示
- **文件**: `demo/briefs/电商大促.json`, `demo/briefs/新品发布.json`
- **依赖**: 无
- **验收**:
  - 每份 Brief 包含客户名称 / Brief 内容 / 项目类型 / 品牌调性 / 部门风格注入
  - Brief 内容足够丰富，能激发多条内容任务
  - 品牌调性明确，审核环节有东西可审
- **耗时**: 0.5h
- **状态**: ⬜

### P7-T07: 答辩 PPT 素材准备
- **描述**: 准备答辩所需的架构图、流程图和关键数据：系统架构全景图（Agent → Tools → Memory → Feishu）、流水线时序图、记忆三层架构图、自进化闭环图、Demo 截图（多维表格 + 知识空间 + IM 群聊）
- **文件**: `docs/presentation/`
- **依赖**: P7-T05
- **验收**:
  - 架构全景图清晰展示组件关系
  - 流水线时序图展示 5 个 Agent 的串行流程
  - 自进化闭环图展示 Hook → 打分 → 双写 → 注入
  - 有 Demo 运行后的实际截图
- **耗时**: 2h
- **状态**: ⬜

### P7-T08: README.md
- **描述**: 撰写项目 README，包含项目简介、快速开始（环境准备 / 安装依赖 / 配置 .env / 创建飞书多维表格 / 运行 Demo）、架构说明、目录结构说明、开发指南
- **文件**: `README.md`
- **依赖**: 无
- **验收**:
  - 快速开始步骤完整可执行
  - 包含飞书多维表格建表说明
  - 架构图内嵌或引用
  - 开发指南说明如何新增角色
- **耗时**: 1.5h
- **状态**: ⬜

### P7-T09: 阶段七 Webhook 测试
- **描述**: 编写 Webhook 端点的测试：模拟飞书事件回调、URL verification challenge 响应、事件重复过滤
- **文件**: `tests/test_webhook.py`
- **依赖**: P7-T01
- **验收**:
  - challenge 验证返回正确
  - 合法事件触发流水线
  - 重复 event_id 被过滤
  - 非法 payload 返回 400
- **耗时**: 1h
- **状态**: ✅
- **备注**: 已完成 D-04 审计修复验证：`python -m pytest tests -q --tb=short` 当前可正常执行，`tests/test_webhook.py` 4 个 pytest 用例实跑通过

### P7-T10: CLAUDE.md 更新阶段标注
- **描述**: 更新 CLAUDE.md 中的开发阶段标注，将已完成的阶段标记为 ✅，将阶段七标为当前阶段
- **文件**: `CLAUDE.md`
- **依赖**: 无
- **验收**:
  - 阶段一到六标记为 ✅
  - 阶段七标记为 ← 当前
- **耗时**: 0.1h
- **状态**: ⬜

---

## 汇总

| 指标 | 数量 |
|------|------|
| 总任务数 | 44 |
| ✅ 已完成 | 34 |
| 🔨 进行中 | 1 |
| ⬜ 待开始 | 9 |
| 总预估工时 | ~57.8h |
| 已完成工时 | ~42.5h |
| 剩余工时 | ~10.2h |

### 剩余任务优先级排序

1. **P7-T02** requirements.txt 补依赖 (0.1h) — 阻塞 P7-T01
2. **P7-T01** FastAPI Webhook 服务 (2h) — 核心接入层
3. **P7-T03** working.py 实现或标注 (1h) — 补齐架构完整性
4. **P7-T04** 事件订阅配置文档 (0.5h) — 补齐配置
5. **P7-T05** Demo 演示脚本 (1.5h) — 答辩核心
6. **P7-T06** 演示用 Brief 数据 (0.5h) — 配合 Demo
7. **P7-T09** Webhook 测试 (1h) — 质量保障
8. **P7-T08** README.md (1.5h) — 交付物
9. **P7-T07** 答辩 PPT 素材 (2h) — 最后准备
10. **P7-T10** CLAUDE.md 更新 (0.1h) — 收尾

