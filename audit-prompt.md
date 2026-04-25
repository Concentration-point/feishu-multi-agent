你是项目评估者。你的任务是：逐项对比 CLAUDE.md 中的设计规范和 TODO.md / todo.json 中的规划，与项目中的实际代码实现，找出一切偏差、遗漏和不一致。

## 工作流程

### 第一步：建立基准

1. 通读 CLAUDE.md 全文，提取所有"应该存在的东西"——每个文件、每个类、每个方法、每个字段映射、每个工具、每个配置项
2. 读取 TODO.md 和 todo.json（如果存在），了解规划的任务和标注的状态
3. 扫描项目目录结构，列出实际存在的所有文件

### 第二步：逐模块审计

对以下每个模块，做三件事：
- **存在性检查**：CLAUDE.md 说应该有的文件/类/方法，实际有没有
- **一致性检查**：实际实现的逻辑是否和 CLAUDE.md 描述的一致
- **质量检查**：实现是否完整，还是 stub/placeholder/半成品

---

#### 2.1 项目结构

对照 CLAUDE.md 中的项目结构树，逐行检查：
- [ ] 每个目录是否存在
- [ ] 每个文件是否存在
- [ ] 有没有 CLAUDE.md 中没提到的多余文件（不一定是问题，但标注出来）
- [ ] 有没有 CLAUDE.md 中提到但不存在的文件

#### 2.2 feishu/ 层

**feishu/auth.py**
- [ ] TokenManager 类是否存在
- [ ] 是否单例模式
- [ ] get_token() 是否 async
- [ ] 是否有过期前自动刷新逻辑
- [ ] 缓存机制是否和 CLAUDE.md 描述一致（过期前 60s 刷新）

**feishu/bitable.py**
- [ ] BitableClient 类是否存在
- [ ] table_id 是否作为参数传入（不是写死的，因为有多张表）
- [ ] 以下方法是否都存在且签名正确：
  - get_record(table_id, record_id) -> dict
  - update_record(table_id, record_id, fields)
  - list_records(table_id, filter_expr=None) -> list
  - create_record(table_id, fields) -> str
  - batch_create_records（CLAUDE.md 提到策略师批量创建）
- [ ] 富文本字段是否统一转纯字符串
- [ ] 是否有 delete_record 方法（经验池合并时需要，CLAUDE.md 可能没明确提但逻辑需要）
- [ ] 错误处理：是否抛 FeishuAPIError
- [ ] 日志：关键操作是否打 info

**feishu/im.py**
- [ ] FeishuIMClient 类是否存在
- [ ] send_text 方法是否存在且能发纯文本
- [ ] send_card 方法是否存在且支持 color 参数
- [ ] 是否复用 TokenManager 鉴权
- [ ] 是否是真实实现还是 stub

**feishu/wiki.py**
- [ ] 是否存在
- [ ] CLAUDE.md 说"仅供 sync 模块使用"，检查是否有 Agent 直接调用它
- [ ] create_node / update_doc / list_nodes 方法是否存在
- [ ] 是否是真实实现还是 stub

#### 2.3 config.py

对照 CLAUDE.md 的配置要求检查：
- [ ] FEISHU_APP_ID / FEISHU_APP_SECRET
- [ ] BITABLE_APP_TOKEN
- [ ] PROJECT_TABLE_ID / CONTENT_TABLE_ID / EXPERIENCE_TABLE_ID
- [ ] FEISHU_CHAT_ID
- [ ] WIKI_SPACE_ID
- [ ] LLM_API_KEY / LLM_BASE_URL / LLM_MODEL
- [ ] KNOWLEDGE_BASE_PATH
- [ ] SYNC_INTERVAL
- [ ] EXPERIENCE_CONFIDENCE_THRESHOLD / EXPERIENCE_MAX_PER_CATEGORY / EXPERIENCE_TOP_K
- [ ] FIELD_MAP_PROJECT 字段映射是否和 CLAUDE.md 多维表格设计一致
- [ ] FIELD_MAP_CONTENT 字段映射是否一致
- [ ] .env.example 是否包含所有配置项且有中文注释

#### 2.4 memory/ 层

**memory/project.py**
- [ ] ProjectMemory 类是否存在
- [ ] ContentMemory 类是否存在（或等效实现）
- [ ] CLAUDE.md 中列出的语义化方法是否都存在：
  - load / get_brief / get_brand_tone / get_dept_style / get_project_type
  - update_status / write_brief_analysis / write_strategy
  - write_review_summary / write_delivery / write_knowledge_ref
- [ ] ContentMemory 的方法是否都存在：
  - create_content_item / batch_create / list_by_project
  - write_draft / write_review / write_publish_date
- [ ] 是否通过 feishu/bitable.py 操作，而不是直接写 HTTP

**memory/experience.py**
- [ ] ExperienceManager 类是否存在
- [ ] save_experience 方法
- [ ] save_to_wiki 方法
- [ ] query_top_k 方法（排序逻辑是否正确：置信度 × log(使用次数)）
- [ ] check_dedup 方法
- [ ] merge_experiences 方法
- [ ] 是否是真实实现还是 stub

#### 2.5 tools/ 层

**tools/__init__.py**
- [ ] ToolRegistry 类是否存在
- [ ] 是否自动扫描 tools/ 目录
- [ ] get_tools(tool_names) 方法是否返回 OpenAI function calling 格式
- [ ] call_tool(name, params, context) 方法是否存在
- [ ] AgentContext dataclass 是否存在且包含 record_id / project_name / role_id

**逐个工具检查**（对每个工具检查三项：文件存在 / SCHEMA 格式正确 / execute 是真实实现还是 stub）：
- [ ] read_project.py
- [ ] write_project.py
- [ ] update_status.py（是否有状态机校验）
- [ ] list_content.py
- [ ] create_content.py
- [ ] batch_create_content.py
- [ ] write_content.py
- [ ] search_knowledge.py（是否是 grep 实现还是 stub）
- [ ] read_knowledge.py
- [ ] write_wiki.py
- [ ] send_message.py（是否是真实 IM 发送还是 stub）
- [ ] get_experience.py（是否是真实查询还是 stub）

#### 2.6 agents/ 层

**agents/base.py**
- [ ] BaseAgent 类是否存在
- [ ] __init__ 是否接收 role_id 和 record_id
- [ ] 是否加载 _shared/*.md
- [ ] 是否解析 soul.md 的 YAML frontmatter（提取 tools / max_iterations）
- [ ] 是否从 ToolRegistry 按 soul.md 声明过滤工具
- [ ] prompt 装配是否包含五层：shared → soul → 项目上下文 → 知识 → 经验
- [ ] ReAct 循环是否完整：LLM 调用 → tool_calls 处理 → 结果追加 → 循环
- [ ] max_iterations 保护是否存在
- [ ] Hook 自省是否嵌入（ReAct 结束后、return 之前）
- [ ] _pending_experience 属性是否存在
- [ ] 日志是否打印每轮的工具调用信息

**agents/_shared/**
- [ ] company.md 是否存在且内容非空
- [ ] sop.md 是否存在且内容非空
- [ ] quality_standards.md 是否存在且内容非空
- [ ] 内容是否贴合「智策传媒」内容营销公司的设定

**五个 soul.md**（每个检查）：
- [ ] 文件是否存在：account_manager / strategist / copywriter / reviewer / project_manager
- [ ] frontmatter 是否包含 name / role_id / tools / max_iterations
- [ ] tools 列表中的工具是否都在 ToolRegistry 中注册
- [ ] body（soul prompt）是否足够详细：身份、工作流程、输出格式、约束
- [ ] soul prompt 是否引导 Agent 主动使用工具（而不是一次性输出）

#### 2.7 知识库

- [ ] knowledge/raw/ 目录是否存在
- [ ] 是否有 1-2 篇种子历史方案 .md
- [ ] 种子文档内容是否足够详实（>500 字，可供 Agent 真实引用）
- [ ] knowledge/wiki/ 目录是否存在
- [ ] knowledge/wiki/_index.md 是否存在
- [ ] knowledge/.sync_state.json 是否存在

#### 2.8 sync/ 层

- [ ] sync/wiki_sync.py 是否存在
- [ ] WikiSyncService 类是否存在
- [ ] start() / sync_once() / trigger() 方法
- [ ] 是否通过 .sync_state.json 做增量同步
- [ ] 是否是真实实现还是 stub

#### 2.9 orchestrator.py

- [ ] Orchestrator 类是否存在
- [ ] pipeline 顺序是否正确：account_manager → strategist → copywriter → reviewer → project_manager
- [ ] 是否依次实例化 BaseAgent 并调 run()
- [ ] 驳回重试逻辑：审核通过率 < 60% → 重跑 copywriter + reviewer → 最多 2 次
- [ ] 经验沉淀逻辑：是否收集 _pending_experience → 统一打分 → 双写
- [ ] 错误处理：单个 Agent 失败是否不崩全流水线
- [ ] 关键节点是否调 IM 广播

#### 2.10 main.py

- [ ] CLI 入口：python main.py run <record_id> 是否可用
- [ ] webhook 服务是否存在（可以是 stub）
- [ ] 后台 sync task 是否在启动时创建

#### 2.11 测试

- [ ] tests/test_bitable.py 是否存在
- [ ] tests/test_agent.py 或 test_framework.py 是否存在
- [ ] tests/test_pipeline.py 是否存在
- [ ] tests/test_knowledge.py 是否存在
- [ ] tests/test_im.py 是否存在
- [ ] tests/test_experience.py 是否存在

### 第三步：交叉一致性检查

这一步不是看单个文件，而是看模块之间是否对得上：

- [ ] **字段名一致性**：config.py 的 FIELD_MAP 中的字段名，和 tools 里工具传的字段名，和 soul.md 里描述的字段名，三者是否一致
- [ ] **工具名一致性**：soul.md 声明的 tools 列表里的名字，和 tools/ 目录下实际注册的名字，是否完全匹配（大小写、下划线）
- [ ] **状态机一致性**：CLAUDE.md 定义的状态流转，update_status 工具中的校验逻辑，orchestrator 中的状态判断，三者是否一致
- [ ] **表结构一致性**：CLAUDE.md 的多维表格字段设计，和 config.py 的 FIELD_MAP，和 memory/project.py 的方法，三者是否对得上
- [ ] **知识库路径一致性**：search_knowledge / read_knowledge / write_wiki 三个工具中使用的路径，和 knowledge/ 实际目录结构，是否一致
- [ ] **经验池一致性**：Hook 蒸馏的 JSON 字段，ExperienceManager 存储的字段，get_experience 查询返回的字段，三者是否对得上

### 第四步：TODO 状态校准

对照 TODO.md / todo.json 中标注的状态，和实际代码对比：
- 标注为 ✅已完成 但实际是 stub 或有明显 bug → 标记为误判
- 标注为 ⬜待开始 但实际已经有完整实现 → 标记为漏更新
- 更新 todo.json 中每个任务的实际状态

## 输出格式

生成 AUDIT_REPORT.md 到项目根目录，包含：

```markdown
# 项目审计报告
> 生成时间: xxxx-xx-xx
> 对照基准: CLAUDE.md + TODO.md

## 总览
- 检查项总数: XX
- ✅ 一致: XX 项
- ❌ 偏差: XX 项（必须修复）
- ⚠️ 缺失: XX 项（功能缺失）
- 💡 建议: XX 项（可以改进）

## 偏差清单（必须修复）

### ❌ D-01: config.py 缺少 EXPERIENCE_TABLE_ID
- CLAUDE.md 要求: config.py 应包含 EXPERIENCE_TABLE_ID 配置
- 实际情况: config.py 中不存在该配置项
- 影响: memory/experience.py 无法定位经验池表
- 修复建议: 在 config.py 中添加，在 .env.example 中同步

### ❌ D-02: ...

## 缺失清单（功能缺失）

### ⚠️ M-01: sync/wiki_sync.py 不存在
- CLAUDE.md 要求: 后台异步线程将本地知识库同步到飞书知识空间
- 实际情况: sync/ 目录不存在
- 影响: 企业人员无法在飞书中查看 Agent 沉淀的知识
- 优先级: 中（不影响核心流水线，但影响演示效果）

### ⚠️ M-02: ...

## 仍为 Stub 的组件

| 文件 | 状态 | 说明 |
|------|------|------|
| tools/search_knowledge.py | stub | 返回固定文本，未实现 grep 搜索 |
| tools/get_experience.py | stub | 返回固定文本，未实现真实查询 |
| ... | ... | ... |

## 一致性问题

### 字段名不一致
| 位置 A | 使用的名称 | 位置 B | 使用的名称 | 应统一为 |
|--------|-----------|--------|-----------|---------|
| config.py FIELD_MAP | "brief_content" | soul.md | "Brief内容" | ... |

### 工具名不一致
（如有）

### 状态机不一致
（如有）

## 建议改进

### 💡 S-01: ...

## TODO 状态校准

| 任务 ID | TODO 标注 | 实际状态 | 需要更新 |
|---------|----------|---------|---------|
| P1-T01 | ✅ | ✅ | 否 |
| P2-T03 | ✅ | stub | 是 → 🔨 |
| P4-T01 | ⬜ | ✅ | 是 → ✅ |

## 下一步行动

按优先级排序的待办事项（从审计中提炼）：
1. [紧急] ...
2. [重要] ...
3. [一般] ...
```

## 执行

1. 读 CLAUDE.md 全文
2. 读 TODO.md / todo.json（如果存在）
3. 扫描完整项目目录结构
4. 对每个模块：读文件内容 → 对照 CLAUDE.md 检查 → 记录偏差
5. 做交叉一致性检查
6. 做 TODO 状态校准
7. 生成 AUDIT_REPORT.md
8. 打印汇总到终端
