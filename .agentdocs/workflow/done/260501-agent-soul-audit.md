# Agent 灵魂审计（策略师 / 项目经理 / 数据分析师）

> 创建日期: 2026-05-01
> 范围: 仅审计 strategist / project_manager / data_analyst 三个角色

## 一、审计发现

### 1. Context 膨胀（所有 Agent 无差别注入 ~32KB 共享知识）

`load_shared_knowledge()` 把 `01_企业底座` + `02_服务方法论` **全量灌给每个 Agent**。

| 知识文件 | 大小 | 实际需要角色 |
|---------|------|------------|
| 企业定位与服务边界.md | 0.6KB | 所有 |
| 智策传媒公司背景.md | 10KB | 所有 |
| Brief 解读规则.md | 0.7KB | account_manager |
| 事实核查要点.md | 2KB | reviewer, copywriter |
| 人审规则与超时策略.md | 0.7KB | orchestrator |
| 内容生产主流程.md | 0.7KB | 所有 |
| 品牌调性检查清单.md | 1.8KB | reviewer, copywriter |
| 审核规则与风险边界.md | 0.8KB | reviewer |
| 广告法禁用词.md | 2.5KB | reviewer, copywriter |
| 质量红线标准.md | 1.3KB | reviewer |
| 项目类型SOP补充.md | **12KB** | 通用（但过大） |

**问题**：策略师/PM/数据分析师每轮都被注入审核规则、广告法禁用词、品牌调性清单等**完全无关的知识**，白白多吃 ~8KB token。

### 2. 工具白名单冗余

| 角色 | 当前工具数 | 冗余工具 | 理由 |
|------|----------|---------|------|
| strategist | 12 | `get_experience`, `write_wiki` | 经验已由 base.py `_load_experiences()` 注入 system prompt；策略师不写 wiki |
| project_manager | **13** | `search_knowledge`, `read_knowledge`, `read_template`, `write_wiki`, `create_content`, `get_experience`, `negotiate` | PM 只做排期+交付摘要，不搜知识、不建内容、不写wiki、不用模板 |
| data_analyst | 6 | `search_knowledge`, `read_knowledge`, `get_experience` | 数据分析师只用 stats 工具，不查知识文章 |

**每多一个工具 SCHEMA，每轮 LLM 调用多付 ~200-500 token**。PM 有 7 个冗余工具 ≈ 每轮多 ~2K token × 9 轮 = **~18K token 浪费**。

### 3. Soul.md 冗余

- **策略师 (113 行)**: 结构清晰，问题不大。`max_iterations: 15` 偏高（实测用 9）。
- **项目经理 (253 行)**: **严重冗余**。"排期原则"和"排期规则"说了两遍同一件事；"输入优先级"和"工具使用要求"重叠；"输出风格要求"是常识废话。可压缩到 ~130 行。
- **数据分析师 (124 行)**: 合理。工作流步骤 2"调 search_knowledge"多余。

### 4. 日志异常："飞书审核全过又全重写"

**根因**：orchestrator `_handle_reviewer_retries()` 的判定逻辑。
- Reviewer 对每条内容发 send_message "通过" → 群里看起来全过
- 但 Orchestrator 算的是**聚合 pass_rate**，如果低于阈值（默认 60%）→ 状态回退到"撰写中" → 文案全部重写
- 这不是 bug，是**信息展示不一致**：per-item 消息 vs aggregate 判定

### 5. Token 成本估算

| 角色 | 迭代次数 | prompt 总量 | completion 总量 | 合计 |
|------|---------|------------|----------------|------|
| strategist | 9 | ~60K | ~5K | **~65K** |
| project_manager | 9 | ~42K | ~4K | **~46K** |
| data_analyst | 4 | ~15K | ~4K | **~19K** |

加上 reflect hook（每个角色额外 ~8-12K），**单次流水线三角色合计 ~145K+ token**。

主要浪费源：
1. 无差别知识注入（每角色 ~8KB 冗余知识 × 迭代数）
2. 冗余工具 SCHEMA（PM 每轮 ~2K 浪费）
3. `get_experience` 工具与 `_load_experiences()` 双重加载
4. web_fetch 内部额外调一次 LLM 做内容提取（策略师特有）

## 二、改动方案

### Phase 1: 知识分层 + 工具瘦身（最高 ROI）

1. `base.py` `_ROLE_KNOWLEDGE_DIRS` 按角色细分 02_服务方法论中的文件
2. 策略师/PM/数据分析师的 soul.md 删除冗余 allowed_tools
3. 降 max_iterations

### Phase 2: Soul.md 精简

4. PM soul.md 合并重复段落，删除废话

## 三、TODO

- [x] 审计分析
- [x] Phase 1: 知识分层（02_服务方法论 按角色精确选取文件）
- [x] Phase 1: 工具瘦身（strategist -2 / PM -7 / data_analyst -3）
- [x] Phase 1: 降 max_iterations（strategist 15→9 / PM 10→6 / data_analyst 8→5）
- [x] Phase 2: PM soul.md 精简（253→142 行）
- [x] 验证：全量 135 测试通过
