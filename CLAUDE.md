# CLAUDE.md


## 项目定位

飞书·智组织 —— 多 Agent 内容生产流水线。客户在飞书多维表格新建一行 Brief，Orchestrator 串起「客户经理 → 策略师 → 文案 → 审核 → 项目经理」五个角色，以 Bitable 为事实源完成 Brief 解读、人审门禁、内容矩阵策略、平台化文案、结构化审核、排期交付、经验蒸馏、知识空间沉淀。此外，「数据分析师」作为独立 Agent 负责跨项目数据分析，自动生成运营周报、数据洞察和决策建议并推送至飞书群聊。

## 常用命令

```bash
# 安装依赖（Python 3.11+）
pip install -r requirements.txt

# 跑单个项目（给定 Bitable record_id）
python main.py run <record_id>

# Webhook + Dashboard（默认端口 8000，含 SSE 实时面板）
python main.py serve

# 手动同步（上行白名单 03_经验沉淀，下行全部 01-06）
python main.py sync --direction up
python main.py sync --direction down
python main.py sync --direction both

# 首次初始化知识库 6 层目录
python scripts/init_wiki_tree.py

# 前端开发（Dashboard）
cd dashboard/react-app && npm install && npm run dev     # 开发
cd dashboard/react-app && npm run build                  # 产物输出到 dashboard/static/

# 数据分析报告（独立于项目流水线）
python main.py report                     # 默认生成运营周报
python main.py report --type insight       # 数据洞察
python main.py report --type decision      # 决策建议

# Demo 跑通整条链路
python demo/run_demo.py --scene 电商大促
python demo/run_demo.py --record-id <record_id>
```

### 测试

```bash
pytest                                      # 全量
pytest tests/test_orchestrator_red_flag.py  # 单文件
pytest tests/test_agent.py -k copywriter    # 关键字过滤
pytest tests/test_agent_live.py             # 需要真实 LLM / 飞书环境
```

`tests/conftest.py` 提供 Bitable / IM / LLM 的 fixture mock，多数测试可离线跑；文件名含 `_live` 或 `_harness` 的需要 `.env` 中的真实凭证。

## 高层架构

### 触发路径

`main.py`（CLI + FastAPI Webhook）→ `Orchestrator`（五角色串行）→ `BaseAgent`（单引擎跑 ReAct 循环）→ `tools/*`（工具分发到 `memory/` 或直接操作 `knowledge/`）→ 飞书 Bitable / IM / Wiki。

独立 Agent 触发路径：`main.py report` / `POST /api/report` → `BaseAgent(role_id="data_analyst")` → `query_project_stats` 拉取全量数据 → LLM 分析生成报告 → `send_report` / `generate_report_doc` 推送飞书群聊。

事件订阅 `bitable.record.created_v1` 打到 `POST /webhook/event`；CLI `run` 和 Webhook 共用 `Orchestrator.run()`。`_processed_record_ids` 去重避免飞书重发，`_running_record_ids` 做运行中锁。

### 编排器状态机（`orchestrator.py`）— 动态路由

编排器使用**状态驱动的动态路由**（非固定序列）。每个 Agent 完成后，Orchestrator 从 Bitable 读取项目当前状态，通过 `ROUTE_TABLE`（定义在 `config.py`）决定下一个角色：

```
路由表（config.ROUTE_TABLE）:
  待处理 / 解读中  → account_manager
  待人审          → __human_review_gate__（特殊路由）
  策略中          → strategist
  撰写中          → copywriter
  审核中          → reviewer
  排期中          → project_manager
  已完成 / 已驳回  → None（终止）

典型流转：
待处理 → 解读中 ─┬─► 待人审 ─┬─► 策略中 → 撰写中 → 审核中 ─┬─► 排期中 → 已完成
                │           │                              │
                │           └─► (修改反馈) → 解读中         ├─► (驳回 × N) → 撰写中
                │                                          │
                │                                          └─► (命中红线) → 中止并标记风险
                │
                └─► (超时) → 保持"待人审"，本次 return，下次触发恢复门禁

动态路由优势：
  - 从任意中间状态恢复（如掉线后 status=撰写中，自动从 copywriter 接续）
  - 路由表可配置，新增状态/角色只需修改 config.ROUTE_TABLE
  - MAX_ROUTE_STEPS=15 防死循环
```

关键分支逻辑：
- **动态路由**：`_resolve_next_role(status)` 查 `ROUTE_TABLE` 返回下一角色；`_read_current_status()` 每步从 Bitable 读取最新状态，实现状态驱动的 while 循环。
- **人审门禁**：AM 产出后由 `_enter_human_review_gate` 发飞书卡片 + 轮询群消息，识别「通过」/「修改：xxx」/ 超时。`AUTO_APPROVE_HUMAN_REVIEW=true` 时 Demo 模式跳过。
- **审核返工**：reviewer 通过 `submit_review` 工具写回审核结论（五维结构化校验）；`review_pass_rate / review_red_flag / review_status / review_summary` 四字段驱动 `_handle_reviewer_retries` 决定进入 PM、回退 copywriter（上限 `REVIEW_MAX_RETRIES=2`）还是中止并写「风险标记」。
- **阈值分型**：`REVIEW_THRESHOLDS_BY_PROJECT_TYPE` 按项目类型细分通过率（电商大促/日常运营 0.6 / 新品发布/品牌传播 0.7 / 母婴 0.8 / 医疗健康 0.9）。
- **红线关键词**：`REVIEW_RED_FLAG_KEYWORDS` 命中即硬中止，不走返工。
- **交付文档生成**：项目进入「已完成」时，若 `DELIVERY_DOC_ENABLED=true` 且 `WIKI_SPACE_ID` 已配置，Orchestrator 自动调用 `_generate_delivery_document` 在飞书知识空间生成交付文档并发布 `delivery_doc.created` 事件。
- **死循环防护**：同角色连续 3 次执行后状态未推进触发 halt；`used_ask_human=true`（Agent 调用了 ask_human 工具）时重置计数，不误判人机交互为死循环。

### BaseAgent 单引擎（`agents/base.py`）

**没有 Agent 框架**，手写 ReAct 循环 + OpenAI function calling。新增角色 = 建 `agents/{role_id}/soul.md` + frontmatter 声明 `tools:` 白名单，零代码改动。

prompt 装配顺序（从外到内）：
1. `agents/{role_id}/soul.md` body — 角色人格
2. Bitable 项目主表的品牌调性 + 部门风格注入 — 项目级上下文
3. `get_experience` 从 L2 经验池（Chroma）查 top-K — 跨项目经验注入

**Plan-Verify 机制**（`agents/base.py`）：每个角色的 soul.md frontmatter 包含 `verify` 字段配置（`table` + `check_fields` + 可选 `min_content_rows`）。Agent 进入循环前调用 `_make_plan` 生成完成计划；想退出前调用 `_verify_plan` 校验产出是否达标；最多触发 2 次补充循环。`verify` 字段缺失的角色整段跳过，行为与无 Plan-Verify 一致。

**reviewer 强制工具约束**：reviewer 必须对每条内容行独立调用一次 `submit_review`（结构化五维字段），不可合并处理；`_REQUIRED_TOOL_CALLS` 在启动时校验 soul.md 白名单。

### 工具层（`tools/`）

所有工具都导出 `SCHEMA`（OpenAI function calling JSON schema）+ `execute(params, context)`。`context: AgentContext` 携带 `record_id / project_name / role_id`。`ToolRegistry` 根据 soul.md 声明的白名单过滤注册给 LLM。

当前 26 个工具（以 `tools/` 目录文件为准）：

| 类别 | 工具 | 说明 |
|---|---|---|
| 项目主表 | `read_project` / `write_project` / `update_status` | 读写项目行，状态更新带状态机校验 |
| 内容排期 | `list_content` / `create_content` / `batch_create_content` / `write_content` | 内容行 CRUD，策略师批量建行，文案逐条成稿 |
| 知识检索 | `search_knowledge` / `read_knowledge` / `read_template` | 多关键词 grep → 排序 → 读全文，不走飞书 API |
| 知识沉淀 | `write_wiki` | 蒸馏写入 `knowledge/06_待整理收件箱/`（脏缓冲，升格后才进 03） |
| 对标 | `search_reference` | grep `knowledge/references/` 专用爆款对标库（不出站） |
| 联网 | `search_web` / `web_fetch` | 策略师联网调研（Tavily 英文 + 秘塔中文，trafilatura 抓全文） |
| IM | `send_message` | 飞书群广播 |
| 经验 | `get_experience` | 查 L2 经验池（Chroma）top-K |
| 审核 | `submit_review` | reviewer 专用：结构化五维写回审核结论（每行独立调用） |
| 人机交互 | `ask_human` / `ask_human_batch` / `ask_human_free` | 客户经理向飞书群发起单问 / 批量问题 / 自由式追问 |
| 数据分析 | `query_project_stats` / `send_report` / `generate_report_doc` | 跨项目统计，IM 推送，生成飞书文档报告 |
| 预检 | `preflight_lint` | 工具调用前合规预检（tools/ 注册，角色白名单控制） |
| 人审（内部） | `request_human_review` | Orchestrator 内部 helper，不暴露给 Agent |

**各角色工具白名单**（以 soul.md frontmatter 为准）：

| 角色 | tools |
|---|---|
| account_manager | read_project, write_project, update_status, search_knowledge, read_knowledge, search_web, web_fetch, write_wiki, get_experience, send_message, ask_human, ask_human_batch |
| strategist | read_project, write_project, update_status, create_content, batch_create_content, search_knowledge, read_knowledge, search_web, web_fetch, send_message |
| copywriter | read_project, list_content, write_content, update_status, search_knowledge, read_knowledge, search_reference, get_experience, send_message |
| reviewer | read_project, list_content, write_content, update_status, search_knowledge, read_knowledge, search_reference, write_wiki, get_experience, send_message, submit_review |
| project_manager | read_project, list_content, write_content, write_project, update_status, send_message |
| data_analyst | query_project_stats, send_report, generate_report_doc |

### 三层记忆

| 层 | 存储 | 读写路径 |
|---|---|---|
| **L0 工作记忆** | `memory/working.py:MessageWindow` | 单次会话 prompt + messages + tool calls，按 token 整组裁剪（`L0_MESSAGE_WINDOW_MAX_TOKENS`），任务结束销毁 |
| **L1 项目记忆** | Bitable「项目主表」+「内容排期表」 | `memory/project.py:ProjectMemory / ContentMemory` 封装行映射；五角色通过读写同一行记录协作 |
| **L2 经验池** | Bitable「经验池表」+ Chroma 向量库（`.chroma/`） | `memory/experience.py:ExperienceManager` + `memory/experience_store.py:ExperienceVectorStore`：Hook 蒸馏 → 置信度 ≥ `EXPERIENCE_CONFIDENCE_THRESHOLD`（默认 0.75）→ 双写 Bitable + Chroma；可溯源 project/run/stage/review |

**经验池角色白名单**（`EXPERIENCE_POOL_ROLE_ALLOWLIST`，默认 `account_manager,strategist,reviewer`）：仅白名单内角色的经验写入 L2 Bitable + Chroma；copywriter / project_manager 不入池（无外部验证来源）。

**成本追踪**：`memory/cost_tracker.py:CostTracker` 按项目 + 角色维度记录 LLM token 用量，`GET /api/costs` 接口提供查询。

### 知识库分层（`knowledge/`）

6 层数字前缀目录 + `references/`，按「谁维护」+「同步方向」划分：

```
01_审核库          → 人类维护，源真值在飞书，只下行（wiki_download）
02_客户档案        → 人类维护，源真值在飞书，只下行
03_经验沉淀        → Agent 产出（升格审批后），源真值在本地，默认上行白名单
04_服务方法论      → 人类维护，源真值在飞书，只下行
05_平台打法        → 人类维护，源真值在飞书，只下行
06_待整理收件箱    → Agent 脏缓冲（write_wiki 写入），不出站，升格流程后迁入 03
references/        → 爆款对标，仅 search_reference 使用，不出站
```

**核心约束**：01-05 不被 Agent 覆盖；06 内容必须通过飞书「升格审批表」（`scripts/submit_inbox_to_review.py` → 过审 → `scripts/apply_approved_promotions.py`）才能迁入 03_经验沉淀。上行白名单由 `WIKI_SYNC_UPLOAD_DIRS` 环境变量控制（默认 `03_经验沉淀`）。

### 同步链路（`sync/`）

- `wiki_sync.py:WikiSyncService` — 后台异步线程，默认 `SYNC_INTERVAL`（3600s），扫描上行白名单目录计算 hash 对 `.sync_state.json` 做 diff，推送到飞书知识空间。失败不抛异常，保持 dirty 等下次。
- `wiki_download.py` — 后台下行线程，拉取飞书 01-06 节点覆盖本地（人类在飞书修改后 Agent 能感知）。由 `WIKI_DOWNLOAD_ENABLED` 控制，默认间隔 `WIKI_DOWNLOAD_INTERVAL`（1800s）。
- 目录层级 → 飞书节点层级一一映射。

### Dashboard（`dashboard/`）

- `event_bus.py:EventBus` — 进程内 SSE 事件总线，`Orchestrator._publish` 在每个 stage 开始/结束时广播。
- `react-app/` — React + Vite + Tailwind + Zustand，消费 SSE 流渲染实时管道、Markdown 产物预览。组件：`StagesPipeline.tsx` / `EventStream.tsx` / `InfoPanel.tsx` / `Controls.tsx` / `RecordPicker.tsx` / `TopBar.tsx`。
- 构建产物输出到 `dashboard/static/` 由 FastAPI `StaticFiles` 挂载到 `/static/`。
- SSE 端点：`GET /stream`（全局）/ `GET /stream/{record_id}`（项目级）。

### 飞书层（`feishu/`）

| 模块 | 说明 |
|---|---|
| `auth.py:TokenManager` | tenant_access_token 单例 + 自动刷新 |
| `bitable.py:BitableClient` | 项目主表 / 内容排期 / 经验池 CRUD，富文本统一转纯字符串 |
| `im.py:FeishuIMClient` | 发文字/卡片/选择卡，读群消息，支持卡片回调 |
| `wiki.py:FeishuWikiClient` | 节点增删查，文档块读写，交付文档自动生成 |
| `wiki_markdown.py` | Markdown → 飞书文档块转换 |
| `card_actions.py` | 飞书卡片回调路由（ask_human 选择确认） |
| `delivery_charts.py` / `report_charts.py` | Matplotlib 生成审核通过率/项目状态图表，嵌入飞书文档 |
| `ws_client.py` | WebSocket 长连接（飞书事件订阅备用通道） |

## 编码规范要点

- **全异步**：所有 I/O 路径 async/await。Bitable client 有全局并发闸门（防飞书限频）。
- **飞书 API 只走 `feishu/`**：`auth.py` token 单例 + `bitable.py` / `im.py` / `wiki.py` 封装；工具层不直接 httpx 请求。
- **知识工具走文件系统**：不经过 `feishu/`，grep 毫秒级。
- **富文本统一转纯字符串**：在 `feishu/bitable.py` 层做，不让上层处理飞书富文本结构。
- **配置集中**：字段映射分四张表：`config.py:FIELD_MAP_PROJECT / FIELD_MAP_CONTENT / FIELD_MAP_EXPERIENCE / FIELD_MAP_PROMOTION`，改飞书表字段 = 改常量，不改业务代码。
- **错误分类**：飞书层抛 `FeishuAPIError`；工具层把异常转成字符串返回给 LLM（让 ReAct 循环能看见并自纠）。

## 新手接手阅读顺序

1. `README.md` — 全景视图与 mermaid 图
2. `orchestrator.py` — 编排主循环、人审门禁、返工分支
3. `agents/base.py` — Agent 引擎、prompt 装配、ReAct 循环、Plan-Verify、Hook 自省
4. 任一 `agents/*/soul.md` — 体会角色人格 + 工具白名单 + verify 配置
5. `memory/project.py` + `memory/experience.py` + `memory/experience_store.py` — L1/L2 如何落到 Bitable + Chroma
6. `sync/wiki_sync.py` + `sync/wiki_download.py` — 双向同步白名单
7. `config.py` — 所有字段映射、阈值、开关
8. `docs/knowledge-architecture.md` — 知识分层完整设计
9. `docs/module1_module2_combo.md` — 文案双轨（爆款对标 + 合规自检）
10. `docs/02_执行流程文档.md` — 全链路细节

## 运维脚本（`scripts/`）

常用：`init_wiki_tree.py`（初始化 6 层）、`preview_wiki_sync.py`（dry-run 同步）、`audit_wiki_local.py`（frontmatter/NUL 字符审计）、`reset_dirty_sync.py`（重置脏标记）、`submit_inbox_to_review.py` + `apply_approved_promotions.py`（升格流程）、`check_demo_ready.py`（Demo 环境就绪检查）、`selfcheck_orchestrator_red_flag.py`（红线拦截链路诊断）、`inspect_chroma.py`（Chroma 向量库内容查看）、`diagnose_route.py`（动态路由链路诊断）、`analyze_tool_stats.py`（工具调用统计分析）。

# 工作规范
- 所有注释用中文，变量函数用英文。
- 改动前先说明你打算改什么，确认后再动手。
- 新功能先写实现，不主动加测试，除非我明确要求。
- 数据库表名用下划线分隔，比如 user_profile。

# 禁止项
- 不要主动重构我没提到的文件。
- 不要删除任何文件，除非我明确说删掉。
- 不要在没确认前直接执行 npm install 装新依赖。

# 压缩时保留
长对话被自动压缩时，按优先级保留：
1. 架构决策和它背后的理由
2. 改过哪些文件、改了什么
3. 当前进展状态
4. 还没做完的 TODO
