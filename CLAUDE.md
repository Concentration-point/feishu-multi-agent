# CLAUDE.md


## 项目定位

飞书·智组织 —— 多 Agent 内容生产流水线。客户在飞书多维表格新建一行 Brief，Orchestrator 串起「客户经理 → 策略师 → 文案 → 审核 → 项目经理」五个角色，以 Bitable 为事实源完成 Brief 解读、人审门禁、内容矩阵策略、平台化文案、结构化审核、排期交付、经验蒸馏、知识空间沉淀。

## 常用命令

```bash
# 安装依赖（Python 3.11+）
pip install -r requirements.txt

# 跑单个项目（给定 Bitable record_id）
python main.py run <record_id>

# Webhook + Dashboard（默认端口 8000，含 SSE 实时面板）
python main.py serve

# 手动同步（上行白名单 07-10，下行白名单 01-06）
python main.py sync --direction up
python main.py sync --direction down
python main.py sync --direction both

# 首次初始化知识库 11 层目录
python scripts/init_wiki_tree.py

# 前端开发（Dashboard）
cd dashboard/react-app && npm install && npm run dev     # 开发
cd dashboard/react-app && npm run build                  # 产物输出到 dashboard/static/

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

事件订阅 `bitable.record.created_v1` 打到 `POST /webhook/event`；CLI `run` 和 Webhook 共用 `Orchestrator.run()`。`_processed_record_ids` 去重避免飞书重发，`_running_record_ids` 做运行中锁。

### 编排器状态机（`orchestrator.py`）

```
待处理 → 解读中 ─┬─► 待人审 ─┬─► 策略中 → 撰写中 → 审核中 ─┬─► 排期中 → 已完成
                │           │                              │
                │           └─► (修改反馈) → 解读中         ├─► (驳回 × N) → 撰写中
                │                                          │
                │                                          └─► (命中红线) → 中止并标记风险
                │
                └─► (超时) → 保持"待人审"，本次 return，下次触发恢复门禁
```

关键分支逻辑：
- **人审门禁**：AM 产出后由 `_enter_human_review_gate` 发飞书卡片 + 轮询群消息，识别「通过」/「修改：xxx」/ 超时。`AUTO_APPROVE_HUMAN_REVIEW=true` 时 Demo 模式跳过。
- **审核返工**：reviewer 输出 `review_pass_rate / review_red_flag / review_status / review_summary` 四字段；`_handle_reviewer_retries` 依据这些字段决定进入 PM、回退 copywriter（上限 `REVIEW_MAX_RETRIES=2`）还是中止并写「风险标记」。
- **阈值分型**：`REVIEW_THRESHOLDS_BY_PROJECT_TYPE` 按项目类型细分通过率（母婴 0.8 / 医疗健康 0.9）。
- **红线关键词**：`REVIEW_RED_FLAG_KEYWORDS` 命中即硬中止，不走返工。

### BaseAgent 单引擎（`agents/base.py`）

**没有 Agent 框架**，手写 ReAct 循环 + OpenAI function calling。新增角色 = 建 `agents/{role_id}/soul.md` + frontmatter 声明 `tools:` 白名单，零代码改动。

prompt 装配顺序（从外到内）：
1. `agents/_shared/*.md` — 公司级共享知识
2. `agents/{role_id}/soul.md` body — 角色人格
3. （copywriter 专属）`agents/copywriter/platforms/{公众号|小红书|抖音}.md` — 平台补丁，按内容行目标平台动态拼接
4. Bitable 项目主表的品牌调性 + 部门风格注入 — 项目级上下文
5. `get_experience` 从 L2 经验池查 top-5 — 跨项目经验

### 工具层（`tools/`）

所有工具都导出 `SCHEMA`（OpenAI function calling JSON schema）+ `execute(params, context)`。`context: AgentContext` 携带 `record_id / project_name / role_id`。`ToolRegistry` 根据 soul.md 声明的白名单过滤注册给 LLM。

当前 18 个工具（以文件名为准，含策略师联网 + 文案双轨）：

| 类别 | 工具 | 说明 |
|---|---|---|
| 项目主表 | `read_project` / `write_project` / `update_status` | 读写项目行，状态更新带状态机校验 |
| 内容排期 | `list_content` / `create_content` / `batch_create_content` / `write_content` | 内容行 CRUD，策略师批量建行，文案逐条成稿 |
| 知识检索 | `search_knowledge` / `read_knowledge` / `read_template` | 多关键词 grep → 排序 → 读全文，不走飞书 API |
| 知识沉淀 | `write_wiki` | Hook 自省蒸馏写入 `knowledge/11_待整理收件箱/`（脏缓冲，升格后才进 10） |
| 对标 | `search_reference` | grep `knowledge/references/` 专用爆款对标库（不出站） |
| 联网 | `search_web` / `web_fetch` | 策略师联网调研（Tavily + trafilatura 抓全文） |
| IM | `send_message` | 飞书群广播 |
| 经验 | `get_experience` | 查 L2 经验池 top-5 |
| 人审 | `request_human_review` | Orchestrator 内部 helper，不暴露给 Agent |

### 三层记忆

| 层 | 存储 | 读写路径 |
|---|---|---|
| **L0 工作记忆** | `memory/working.py` | 单次会话 prompt + messages + tool calls，按 token 整组裁剪，任务结束销毁 |
| **L1 项目记忆** | Bitable「项目主表」+「内容排期表」 | `memory/project.py` 封装行映射；五角色通过读写同一行记录协作 |
| **L2 经验池** | Bitable「经验池表」+ 本地 `knowledge/10_经验沉淀/` | `memory/experience.py`：Hook 蒸馏 → 置信度 ≥ 0.7 → 双写；可溯源 `project/run/stage/review` |

### 知识库分层（`knowledge/`）

11 层数字前缀目录 + `references/`，按「谁维护」+「同步方向」划分：

```
01_企业底座 ~ 06_客户档案  → 人类维护，源真值在飞书，只下行（wiki_download）
07_项目档案 ~ 10_经验沉淀  → Agent 产出，源真值在本地，只上行白名单（wiki_sync）
11_待整理收件箱            → Agent 脏缓冲，不出站
references/                → 爆款对标，仅 search_reference 使用，不出站
```

**核心约束**：01–06 不被 Agent 覆盖，10 必须通过飞书「升格审批表」（`scripts/submit_inbox_to_review.py` → 过审 → `scripts/apply_approved_promotions.py`）从 11 迁移而来。白名单由 `WIKI_SYNC_UPLOAD_DIRS` 强制。

### 同步链路（`sync/`）

- `wiki_sync.py` — 后台异步线程，默认 `SYNC_INTERVAL`（1h），扫描 07–10 计算 hash 对 `.sync_state.json` 做 diff，推送到飞书知识空间。失败不抛异常，保持 dirty 等下次。
- `wiki_download.py` — 后台下行线程，拉取飞书 01–06 节点覆盖本地（人类在飞书修改后 Agent 能看到）。由 `WIKI_DOWNLOAD_ENABLED` 控制。
- 目录层级 → 飞书节点层级一一映射。

### Dashboard（`dashboard/`）

- `event_bus.py` —— 进程内 SSE 事件总线，`Orchestrator._publish` 在每个 stage 开始/结束时广播。
- `react-app/` —— React 19 + Vite 8 + Tailwind 4 + Zustand，消费 SSE 流渲染实时管道、Markdown 产物预览。
- 构建产物输出到 `dashboard/static/` 由 FastAPI `StaticFiles` 挂载到 `/static/`。

## 编码规范要点

- **全异步**：所有 I/O 路径 async/await。Bitable client 有全局并发闸门（防飞书限频）。
- **飞书 API 只走 `feishu/`**：`auth.py` token 单例 + `bitable.py` / `im.py` / `wiki.py` 封装；工具层不直接 httpx 请求。
- **知识工具走文件系统**：不经过 `feishu/`，grep 毫秒级。
- **富文本统一转纯字符串**：在 `feishu/bitable.py` 层做，不让上层处理飞书富文本结构。
- **配置集中**：所有字段名映射在 `config.py:FIELD_MAP_PROJECT / FIELD_MAP_CONTENT`，改飞书表字段 = 改常量，不改业务代码。
- **错误分类**：飞书层抛 `FeishuAPIError`；工具层把异常转成字符串返回给 LLM（让 ReAct 循环能看见并自纠）。

## 新手接手阅读顺序

1. `README.md` — 全景视图与 mermaid 图
2. `orchestrator.py` — 编排主循环、人审门禁、返工分支
3. `agents/base.py` — Agent 引擎、prompt 装配、ReAct 循环、Hook 自省
4. 任一 `agents/*/soul.md` — 体会角色人格 + 工具白名单声明
5. `memory/project.py` + `memory/experience.py` — L1/L2 如何落到 Bitable
6. `sync/wiki_sync.py` + `sync/wiki_download.py` — 双向同步白名单
7. `config.py` — 所有字段映射、阈值、开关
8. `docs/knowledge-architecture.md` — 知识分层完整设计
9. `docs/module1_module2_combo.md` — 文案双轨（爆款对标 + 合规自检）
10. `docs/02_执行流程文档.md` — 全链路细节

## 运维脚本（`scripts/`）

常用：`init_wiki_tree.py`（初始化 11 层）、`preview_wiki_sync.py`（dry-run 同步）、`audit_wiki_local.py`（frontmatter/NUL 字符审计）、`reset_dirty_sync.py`（重置脏标记）、`submit_inbox_to_review.py` + `apply_approved_promotions.py`（升格流程）、`check_demo_ready.py`（Demo 环境就绪检查）、`selfcheck_orchestrator_red_flag.py`（红线拦截链路诊断）。

## Windows 执行环境提示（本项目实测）

- 仓库文件存在历史中文乱码残留，编辑时留意保持 UTF-8。
- 本地开发用 Windows 原生 Python 3.12（`python` 命令），不要切到 WSL（pip/SSL 受限）。
- Git Bash 下需补 PATH：`PATH="/usr/bin:/bin:/mingw64/bin:/c/Program Files/Git/cmd:/c/Program Files/Git/mingw64/bin:/c/Program Files/Git/usr/bin:$PATH"`
