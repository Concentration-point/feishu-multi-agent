# Demo 翻车风险审查报告

> **审查时间**：2026-05-06  
> **剩余时间**：约 15 小时  
> **审查方式**：静态代码审查 + Python 运行时验证  
> **审查范围**：主流水线 + 工具系统 + soul.md + 经验链路

---

## 必修清单（按优先级，总计约 13 分钟）

| # | 级别 | 修复动作 | 预估 |
|---|------|----------|------|
| 1 | **P0** | `.env` 加 `AUTO_APPROVE_HUMAN_REVIEW=true` | 1 min |
| 2 | **P0** | 运行 LLM 连通测试，确认 `gpt-5.1` 可用 | 5 min |
| 3 | **P0** | `agents/project_manager/soul.md`: `max_iterations: 6` → `12` | 1 min |
| 4 | **P1** | `agents/strategist/soul.md`: `max_iterations: 9` → `14` | 1 min |
| 5 | **P1** | Demo Brief 去掉「公众号」需求，或删 strategist soul 平台硬限 | 2 min |
| 6 | **P1** | 在 Bitable 手动设 1 条内容行 `review_status=需修改`，触发经验面板动画 | 3 min |

---

## 第一轮：流水线能不能跑通

### P0-01：`AUTO_APPROVE_HUMAN_REVIEW=false` → Demo 卡死在人审门禁

- **现象**：AM 完成后，Orchestrator 进入 `_enter_human_review_gate`，调 `poll_for_human_reply` 向飞书群发卡片等待人工审批。Demo 现场无人实时操作飞书，则等待 `HUMAN_REVIEW_TIMEOUT=300s` 后返回 `timeout`，pipeline 标记为 `aborted`，评委看到流水线中止。
- **根因**：`.env` 当前值 `AUTO_APPROVE_HUMAN_REVIEW=false`，未开启跳过逻辑。`poll_for_human_reply` 第 36 行判断：`if AUTO_APPROVE_HUMAN_REVIEW: return skipped_auto_approve`，当前条件不满足，进入真实等待。
- **影响**：100% 必现，流水线第二阶段（AM→策略师）必然卡死。
- **修复**：
  ```bash
  # .env 中加入
  AUTO_APPROVE_HUMAN_REVIEW=true
  ```
- **预估**：1 分钟

---

### P0-02：`LLM_MODEL=gpt-5.1` 非标准模型名，需确认第三方中转实际支持

- **现象**：当前配置 `LLM_MODEL=gpt-5.1`，`LLM_BASE_URL=https://api-xai.ainaibahub.com/v1`。`gpt-5.1` 不是 OpenAI 官方任何已知模型 ID。若第三方中转站不识别该 alias 或服务不稳定，所有 LLM 调用全部报 `404 model_not_found`，整条流水线崩溃。
- **根因**：模型名依赖第三方中转私有 alias，无法在不发请求的情况下验证。
- **修复**：立即运行以下命令验证连通性：
  ```bash
  python -c "
  import asyncio
  from openai import AsyncOpenAI
  import os; from dotenv import load_dotenv; load_dotenv()
  async def t():
      c = AsyncOpenAI(base_url=os.getenv('LLM_BASE_URL'), api_key=os.getenv('LLM_API_KEY'))
      r = await c.chat.completions.create(
          model=os.getenv('LLM_MODEL'),
          messages=[{'role':'user','content':'hi'}],
          max_tokens=5
      )
      print('OK:', r.choices[0].message.content)
  asyncio.run(t())
  "
  ```
  如果报错，换回中转站支持的模型名（如 `gpt-4o`）。
- **预估**：5 分钟

---

### P1-01：`project_manager max_iterations=6` → PM 必然被截断，"已完成"到不了

- **验证数据**：
  - N=3 条通过内容：最少 9 步 + Plan-Verify 2 轮 = **11 步 vs max=6，SHORT by 5**
  - N=5 条通过内容：**13 步 vs max=6，SHORT by 7**
  - N=9 条通过内容：**17 步 vs max=6，SHORT by 11**
- **现象**：PM 被截断后无法写交付摘要、推进状态到「已完成」。Orchestrator 读到 `status=排期中 ≠ 已完成`，触发 `pipeline.aborted`，5 判据全部失败。
- **修复**：`agents/project_manager/soul.md` 第 12 行：
  ```yaml
  max_iterations: 12
  ```
- **预估**：1 分钟

---

### P1-02：`strategist max_iterations=9` → 最少需要 10+ 步，截断风险极高

- **验证数据**：最少必要步骤 10 步 + Plan-Verify 2 轮 = **12 步 vs max=9，SHORT by 3**
- **现象**：策略师被截断时，内容行可能已建但 `write_project`（策略方案）或 `update_status`（撰写中）没执行。Orchestrator 读 `status=策略中`，死循环防护在 3 次后 halt。
- **修复**：`agents/strategist/soul.md` 第 16 行：
  ```yaml
  max_iterations: 14
  ```
- **预估**：1 分钟

---

### P1-03：Demo 演示依赖路线未确认

- **现象**：`python demo/run_demo.py --scene 电商大促` 依赖真实飞书凭证且需要 Bitable 中预先建好记录。`POST /api/demo/start` 是纯 mock，无需凭证，评委看到的管道效果相同。两条路线都 OK，但必须提前确认用哪条。
- **修复**：确认演示路线（0 分钟代码改动）。

---

## 第二轮：工具系统有没有坑

**整体结论：工具层干净，无 P0。**

- 25 个工具全部通过：SCHEMA 格式合规（`type: function`，`function.name/description/parameters` 层级正确）、`execute` 全异步、签名全为 `(params, context)`
- `preflight_lint` 无 SCHEMA/execute 是设计如此（仅被 `write_content` 内部调用，不暴露给 LLM），ToolRegistry 自动跳过，正确
- `search_web` 返回 `dict`，ToolRegistry.`call_tool` 用 `json.dumps` 序列化后送给 LLM，无问题
- 6 个角色 soul.md 工具白名单与 ToolRegistry 完全匹配，无幽灵工具
- 熔断机制（circuit breaker）对所有工具生效，连续失败 5 次后自动熔断 60s
- 状态转移表 `_TRANSITIONS` 覆盖 Demo 完整链路（待处理→解读中→待人审→策略中→撰写中→审核中→排期中→已完成）全部 OK
- `list_content` 支持 `platform` 过滤参数，fan-out 子 Agent 正常使用
- `METASO_API_KEY` 已设置，中文搜索走秘塔，Tavily 处理英文，双引擎健康

### P2-01：`submit_review.dimensions` 5 个子字段全部 required，LLM 易遗漏

- **现象**：reviewer LLM 如漏填任意一个 `dimensions` 子字段，工具返回错误字符串，reviewer 需补调一次，浪费 1 轮迭代。
- **建议**：`agents/reviewer/soul.md` 第 76 行处补充 5 个维度名：`banned_words / brand_tone / platform_spec / dept_style / fact_check`（已有 SCHEMA 约束，soul 加一行提醒即可）。

---

## 第三轮：五个 Agent 的 soul.md 有没有硬伤

### P0-01（同第一轮 P1-01）：project_manager max_iterations=6

（见第一轮 P1-01，此处不赘述）

---

### P1-01（同第一轮 P1-02）：strategist max_iterations=9

（见第一轮 P1-02，此处不赘述）

---

### P1-02：strategist soul 硬限「只限小红书和抖音」，Demo Brief 要求公众号 — 评委会注意到

- **现象**：strategist soul 写死：
  > **发布平台只限小红书和抖音**，不考虑其他平台（公众号、微博、视频号等）

  Demo Brief：「需要公众号科普文+小红书种草+抖音开箱脚本」。策略师直接忽略公众号，只建小红书+抖音内容行。评委对比 Brief 和内容矩阵，一眼看出缺口，认为 Agent 读 Brief 不认真。

- **修复**（二选一）：
  - **选项 A（推荐）**：修改 Demo Brief，去掉公众号，改为「小红书种草+抖音开箱脚本，各 2 条」——0 分钟代码改动
  - **选项 B**：修改 `agents/strategist/soul.md` 第 58 行，删除平台硬限，改为「优先小红书和抖音，客户明确要求时可加其他平台」
- **预估**：2 分钟

---

### 其他 soul.md 检查结论

| 角色 | frontmatter 解析 | 工具白名单 | verify.check_fields | 工作流逻辑 |
|------|----------------|-----------|---------------------|-----------|
| account_manager | OK | OK（12个，无幽灵） | `brief_analysis` ✓ BriefProject | OK，追问限 2 轮 |
| strategist | OK | OK（10个，无幽灵） | `strategy` ✓ BriefProject | **max_iter 不足** |
| copywriter | OK | OK（9个，无幽灵） | `draft/word_count` ✓ ContentRecord | OK |
| reviewer | OK | OK（11个，无幽灵） | `review_status/review_feedback` ✓ ContentRecord | 与 Orchestrator 阈值逻辑语义轻微不一致（P2） |
| project_manager | OK | OK（6个，无幽灵） | `delivery` ✓ BriefProject | **max_iter 严重不足** |
| data_analyst | OK | OK（3个，无幽灵） | 无 verify | OK |

### P2-01：Demo Brief 品类（儿童益智玩具）无精确品类文件，copywriter 触发兜底

- **现象**：`knowledge/04_平台打法/` 下有美妆/餐饮/服饰/家居/教育/本地生活，无「玩具」品类文件。copywriter soul 写了「若无精确品类文件，搜最近似的品类名」兜底，LLM 会搜「教育」命中。不崩溃，但指南精确度略低。
- **建议**：可不修。若有时间，各加一个轻量 `小红书-玩具.md` / `抖音-玩具.md`。

### P2-02：reviewer soul「全部通过才推排期中」与 Orchestrator 60% 阈值不一致

- **现象**：soul 说「仅当全部通过时」推 `排期中`，但 Orchestrator `_handle_reviewer_retries` 用 60% 阈值覆盖。功能上 Orchestrator 会救场，无崩溃风险，仅语义不统一。
- **建议**：改 reviewer soul 第四步描述，删掉「仅当全部通过时」的条件，改为「调 update_status → 排期中，具体由系统阈值决定」。

---

## 第四轮：经验沉淀链路能不能走通

**整体结论：经验链路代码健全，Chroma 有 11 条历史经验，端到端可用。**

### 端到端验证结果

| 环节 | 验证结果 |
|------|---------|
| Chroma 实例化 | OK（chromadb 1.5.8）|
| `store.query()` 返回格式 | OK（`id/document/metadata/distance`）|
| 手动插入后立即查询命中 | OK（100%）|
| `save_experience` 双写独立 | OK（任一失败仅 warning，不阻断另一方）|
| `query_top_k` → `_load_experiences` → system prompt | OK（experience_text 注入 `# 历史经验` 章节）|
| Chroma 现有经验数量 | AM:1 / strategist:3 / copywriter:6 / reviewer:1 / PM:0 |

### P1-01：Demo 首次运行时「经验沉淀」链路不触发，Dashboard 经验面板漏斗全为 0

- **根因**：`_settle_experiences` 调 `_distill_from_feedback`，后者依赖：
  - **链路A**：内容排期表有 `review_status=需修改/驳回` 的行
  - **链路B**：主表 `human_feedback` 字段非空（来自人审修改意见）
  
  Demo 设 `AUTO_APPROVE_HUMAN_REVIEW=true` → 人审跳过 → 链路B 必然为空。
  若审核全部通过 → 链路A 也为空。
  `pending=[]` → `_settle_experiences` 直接 return，Dashboard 经验面板整个漏斗不动。

- **影响**：CLAUDE.md 特别提及的「经验进化·L2 沉淀」面板是 Demo 视觉亮点之一，若面板静止，评委会追问「这个功能有没有实现」。

- **修复（选项 A，推荐，0 代码改动）**：
  Demo 跑完后（或 Demo 前预热时）在 Bitable 内容排期表里手动对 1 条内容行设置：
  ```
  审核状态 = 需修改
  审核反馈 = 小红书笔记使用了「最有效」等绝对化用语，需修改
  ```
  然后再触发一次流水线，`_distill_from_feedback` 链路A 会命中，经验面板漏斗完整走通。

- **预估**：3 分钟

[预检] 命中禁用词：最（共2次）、第一（共1次）
---

## 综合修复路线图

### 第一优先级（P0，合计 7 分钟）

```bash
# 1. .env 加一行（1 分钟）
echo "AUTO_APPROVE_HUMAN_REVIEW=true" >> .env

# 2. 验证 LLM 连通（5 分钟）
python -c "
import asyncio
from openai import AsyncOpenAI
import os; from dotenv import load_dotenv; load_dotenv()
async def t():
    c = AsyncOpenAI(base_url=os.getenv('LLM_BASE_URL'), api_key=os.getenv('LLM_API_KEY'))
    r = await c.chat.completions.create(
        model=os.getenv('LLM_MODEL'),
        messages=[{'role':'user','content':'hi'}],
        max_tokens=5
    )
    print('LLM OK:', r.choices[0].message.content)
asyncio.run(t())
"

# 3. PM max_iterations（1 分钟）
# 修改 agents/project_manager/soul.md 第 12 行：
#   max_iterations: 6  →  max_iterations: 12
```

### 第二优先级（P1，合计 6 分钟）

```bash
# 4. strategist max_iterations（1 分钟）
# 修改 agents/strategist/soul.md 第 16 行：
#   max_iterations: 9  →  max_iterations: 14

# 5. Demo Brief 平台对齐（2 分钟）
# 方案A：修改 demo/briefs/ 下的 Brief 文件，删掉「公众号」需求
# 方案B：修改 agents/strategist/soul.md，删掉「只限小红书和抖音」硬约束

# 6. 触发经验面板动画（3 分钟）
# 登录飞书 → 内容排期表 → 任选 1 条内容行
# 将「审核状态」设为「需修改」
# 将「审核反馈」填入「小红书笔记使用了最有效等绝对化用语，需修改」
```

---

## 环境配置速查

| 配置项 | 当前值 | 正确值 | 状态 |
|--------|--------|--------|------|
| `AUTO_APPROVE_HUMAN_REVIEW` | `false` | `true` | ❌ 需改 |
| `LLM_MODEL` | `gpt-5.1` | 需验证中转支持 | ⚠️ 需验证 |
| `LLM_BASE_URL` | `https://api-xai.ainaibahub.com/v1` | 第三方中转 | ⚠️ 需验证 |
| `FEISHU_APP_ID` | 已设置 | — | ✅ |
| `BITABLE_APP_TOKEN` | 已设置 | — | ✅ |
| `PROJECT_TABLE_ID` | 已设置 | — | ✅ |
| `CONTENT_TABLE_ID` | 已设置 | — | ✅ |
| `FEISHU_CHAT_ID` | 已设置 | — | ✅ |
| `TAVILY_API_KEY` | dev key 已设置 | — | ✅（dev key，速率有限） |
| `METASO_API_KEY` | 已设置 | — | ✅ |
| `WIKI_SPACE_ID` | 已设置 | — | ✅ |
| `EXPERIENCE_TABLE_ID` | 已设置 | — | ✅ |
| `PM max_iterations` | 6 | 12 | ❌ 需改 |
| `Strategist max_iterations` | 9 | 14 | ❌ 需改 |

---

*报告生成：2026-05-06 | 审查方法：静态代码分析 + Python 运行时验证 | 覆盖：main.py / orchestrator.py / agents/base.py / tools/ (25个) / agents/*/soul.md (6个) / memory/experience.py*
