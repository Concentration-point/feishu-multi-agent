# 智策传媒 · 本地知识库分层架构

本目录是 Agent 的唯一检索源。所有对外知识空间内容都通过 `sync/wiki_sync.py`
从这里异步推送到飞书。本地写入是第一真相源，飞书端只是镜像。

## 分层原则（必读）

- **人工编辑**（01-06, 09）：企业稳态知识，Agent 只读，不自动改
- **流程产物**（07-08）：Orchestrator 自动写入，Agent 既读也写
- **经验回路**（10-11）：自动产出先进 `11_待整理收件箱/`，升格后入 `10_经验沉淀/`
- **references/**：爆款对标素材，独立功能域，`search_reference` 工具专用
- **wiki/ 和 raw/ 已废弃**：历史数据已按语义迁移到 01-10 对应位置

## 顶层目录职责矩阵

| 目录 | 写入者 | 读取 | 同步飞书 | 当前状态 |
|------|--------|------|---------|----------|
| `01_企业底座/` | 人 | Agent L0 + 人 | ✓ | 已填：公司背景、服务边界 |
| `02_服务方法论/` | 人 | Agent L0 + 人 | ✓ | 已填：Brief/人审/流程/审核/质量/SOP/禁用词/调性/核查 |
| `03_行业知识/` | 人 | Agent L0（未来 router） | ✓ | 空占位 |
| `04_平台打法/` | 人 | Agent L0（strategist/copywriter/reviewer） | ✓ | 已填：小红书/抖音/公众号/规范 |
| `05_标准模板/` | 人 | 工具 `read_template` | ✓ | 已填：Brief/策略/文案/审核/客户/项目/复盘/经验卡 |
| `06_客户档案/` | 人 | 人 + 未来 agent | ✗ 私密 | 空占位 |
| `07_项目档案/` | Orchestrator | Agent L1 | ✗ 私密 | 未建代码链路 |
| `08_项目执行记录/` | Orchestrator | 人复盘 | ✗ 私密 | 未建代码链路 |
| `09_项目复盘/` | 人（基于 08） | Agent + 人 | ✗ 私密 | 空占位 |
| `10_经验沉淀/` | 升格机制 / 人 | Agent L1 `load_formal_experiences` | ✓ | 已填：2 份历史全案 |
| `11_待整理收件箱/` | Agent Hook 自省 | 人 review + 升格脚本 | ✗ 缓冲区 | 动态增长 |
| `references/` | 人 | 工具 `search_reference` | ✗ 素材 | 已填：小红书/抖音/公众号 |

## Agent 的三条检索链路

```
┌──────────────────────────────────────────────────────────────┐
│ L0 常驻 system prompt（创建 Agent 时一次性注入）             │
│   01_企业底座 + 02_服务方法论（所有角色通用）                │
│   + 04_平台打法（strategist / copywriter / reviewer 专属）   │
└──────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────┐
│ L1 经验注入（创建 Agent 时按 project_type 查）               │
│   Bitable 经验池表 query_top_k（k=5，按 confidence 排序）    │
│   + 10_经验沉淀/{category}/ 全文                             │
└──────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────┐
│ L2 工具检索（ReAct 中 Agent 主动调）                         │
│   search_knowledge(query, scope)                             │
│     scope=方法论: 01+02+04                                   │
│     scope=模板:   05                                         │
│     scope=正式经验: 10                                       │
│     scope=全部:   除 11 / references 外全局                  │
│   search_reference(query, platform): 仅 references/          │
│   read_knowledge(filepath): 任意路径读全文                   │
│   read_template(name): 05_标准模板/                          │
│   write_wiki(category, title, content): 写入 11_待整理收件箱/│
└──────────────────────────────────────────────────────────────┘
```

## 写入禁令（约束违反 = 架构破坏）

1. **Agent 不得写入 01-09、10**：这些是权威区或 Orchestrator 职责
2. **`write_wiki` 只能落 11_待整理收件箱/**：不许绕过写入任何其他目录
3. **升格到 10_ 必须经飞书多维表格审批**：无审批通过记录不得迁移
4. **references/ 由人工维护**：Agent 可读不可写

## 同步飞书的黑名单

`sync/wiki_sync.py` 默认不对外推送：
`references/` / `11_待整理收件箱/` / `06_客户档案/` / `07_项目档案/` / `08_项目执行记录/` / `09_项目复盘/`

可通过 `WIKI_SYNC_EXCLUDE_DIRS` 环境变量覆盖。

## 经验升格机制（V1：飞书多维表格审批）— 已实现

自动产出累积在 `11_待整理收件箱/{category}/` 后走 3 步闭环：

1. `scripts/submit_inbox_to_review.py`：扫描收件箱，把尚未提交的候选写入飞书「经验升格审批」多维表格，状态=「待审批」。成功后会在 `.sync_state.json` 对应 entry 加 `promotion_submitted: true` + `promotion_record_id`，避免重复提交。
2. 人工在飞书里给每一行勾选「通过」或「驳回」，可补充「审批备注」。
3. `scripts/apply_approved_promotions.py`（定时或手动）：拉审批表，筛状态∈(通过, 驳回) 且「处理时间」为空的记录，逐条处理：
   - 通过 → 把文件从 `11_/{cat}/` 复制到 `10_/{cat}/`（frontmatter 自动追加 `promoted_from` / `promoted_at`），删除 `11_` 源文件；`.sync_state.json` 中旧 entry 删除、新 entry `dirty=true`（下次 `wiki_sync` 会推到飞书）。
   - 驳回 → 删除 `11_` 文件 + state entry。
   - 写回审批表「处理时间」= 当前时间戳。失败不会回滚文件动作，下轮会幂等补写。

### 使用方式

```bash
# 先 dry-run 看看要提交哪些
python scripts/submit_inbox_to_review.py --dry-run
# 实际提交，可用 --limit N 限制一次处理数量
python scripts/submit_inbox_to_review.py --limit 20

# 人工在飞书里审批...

# 再 dry-run 看看要应用哪些决定
python scripts/apply_approved_promotions.py --dry-run
# 实际应用
python scripts/apply_approved_promotions.py
```

### 需要手动在飞书里建的表

**表名**：经验升格审批（PROMOTION_REVIEW_TABLE_ID）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| 候选文件路径 | 文本 | 相对 `knowledge/`，如 `11_待整理收件箱/电商大促/xxx.md` |
| 分类 | 单选 | 电商大促 / 新品发布 / 品牌传播 / 日常运营 / ... |
| 适用角色 | 单选 | account_manager / strategist / copywriter / reviewer / project_manager |
| 经验摘要 | 文本 | 正文前 300 字 |
| 置信度 | 数字 | Agent 蒸馏时的打分 |
| 来源项目 | 文本 | 来源记录 |
| 审批状态 | 单选 | 待审批 / 通过 / 驳回 |
| 审批备注 | 文本 | 审批人填 |
| 提交时间 | 日期 | submit 脚本自动写 |
| 处理时间 | 日期 | apply 脚本回写 |

环境变量 `PROMOTION_REVIEW_TABLE_ID` 必须配到 `.env`，`BITABLE_APP_TOKEN` 与其它表共用。

### 重新提交一个已删除的飞书记录

如果人工误删了飞书审批记录，想让 submit 重发：
- 方案一：手动编辑 `knowledge/.sync_state.json`，把该文件对应 entry 的 `promotion_submitted` 字段改为 false 或删掉。
- 方案二（批量）：`python scripts/reset_dirty_sync.py --all` 会把整张 state 重置，submit 下次会重新扫描所有候选。

### 测试

`python tests/test_promotion_flow.py` — 不依赖真实飞书，用 FakeBitableClient 走完 submit→审批→apply 全链路。
