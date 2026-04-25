# 模块一 ∩ 模块二 协同闭环设计

> 人机协同进化里，文案 Agent 的"对标学习"和审核 Agent 的"规则驱动"
> 不是两条平行线，而是在文案撰写的 ReAct 循环里形成串联闭环。

## 为什么要组合

**并联状态的问题**：
- 模块一单独跑：文案 Agent 会搜到爆款 hook，但爆款里可能有"最有效""第一品牌"这种广告法禁用词，抄过去审核一定驳回
- 模块二单独跑：审核能挑出违规，但文案撰写阶段没有主动预检，驳回→返工→再审核，Demo 现场来回重试很难看
- 结果：两个模块各自"达标"，但整体通过率不升反降

**串联闭环的价值**：
- 文案 Agent 撰写前**同时走双轨**：爆款对标 + 合规自检
- 对标教 "怎么写"、规则教 "不能踩什么"
- 冲突时规则优先（如 hook 里的禁用词用合规替代改写）
- 一次成稿就通过审核，Demo 叙事从"AI 反复返工"升级为"AI 一次过关"

## 闭环架构

```
┌─────────────────────────────────────────────────────────┐
│  文案 Agent ReAct 循环（强制双轨工作流）                │
│                                                          │
│  ① search_reference(query="品类 角度", platform=目标平台) │
│     ↓ 返回 3-5 篇爆款：hook / structure / cta            │
│                                                          │
│  ② search_knowledge(query="禁用词 [品类]")               │
│     ↓ 命中 raw/rules/广告法禁用词.md                     │
│                                                          │
│  ③ search_knowledge(query="[目标平台] 规范")             │
│     ↓ 命中 raw/rules/平台规范.md                         │
│                                                          │
│  ④ 融合创作                                              │
│     - 模仿爆款结构骨架                                    │
│     - 规避规则红线（禁用词做合规替代）                    │
│     - 字数/标签/CTA 达到平台规范下限                      │
│                                                          │
│  ⑤ write_content 写回 draft_content，正文顶部含双标注：  │
│     <!-- [对标参考] ... [合规自检] ... -->               │
│                                                          │
│  ⑥ Hook 自省 → 蒸馏经验                                  │
│     字段：reference_pattern / rule_check /               │
│           conflict_handling / lesson                     │
│                                                          │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│  审核 Agent 审核（模块二独立跑）                        │
│     - 逐条查规则库引用规则文件                            │
│     - 写回 review_feedback 时引用规则依据                │
│                                                          │
│  Hook 蒸馏：applicable_roles=[reviewer, copywriter]     │
│     ↓ 代码级兜底：base.py:505 强制追加 copywriter        │
│                                                          │
│  经验池 → ExperienceManager.query_top_k(copywriter)      │
│     ↓ 下次文案启动时 _load_experiences 注入 system prompt│
│                                                          │
│  下次文案看到：                                          │
│  "上次你因为使用"最"字被驳回，本次撰写 [品类] 时必须..."│
└─────────────────────────────────────────────────────────┘
```

## 代码级落点

| 改动点 | 位置 | 作用 |
|-------|------|------|
| 工具注入 | `agents/copywriter/soul.md` frontmatter | 让 LLM 看到 search_reference + search_knowledge 两个工具的 schema |
| 工作流描述 | `agents/copywriter/soul.md` body | 强制双轨工作流 + 冲突处理原则 + 双标注规范 |
| 硬约束兜底 | `agents/base.py` `_REQUIRED_TOOL_CALLS["copywriter"]` | ReAct 结束后若未调用两个工具，注入合规警告 |
| 反哺 reflect | `agents/base.py` `_COPYWRITER_REFLECT_PROMPT` | 蒸馏时输出 reference_pattern + rule_check + conflict_handling |
| 反哺兜底 | `agents/base.py` `BaseAgent._hook_reflect` 行 505 | 确保 reviewer 经验 applicable_roles 含 copywriter |
| 种子数据 | `knowledge/references/` × 7 篇 | 对标源（方案 C） |
| 种子数据 | `knowledge/raw/rules/` × 4 篇 | 规则源（模块二已建） |

## 答辩叙事

> "我们没有停在'文案学爆款、审核查规则'的孤岛。我们让文案 Agent 在撰写前同时双轨取经：
> 一边拿爆款的结构骨架，一边对照规则的红线清单。爆款里那句"最有效"，文案不会照抄 —
> 它会把规则里的合规替代方案"表现优异"接上来。一次成稿就过审。
>
> 更重要的是：审核每次驳回发现的新违规模式，都会自动蒸馏成经验，applicable_roles
> 标记为文案+审核双角色。下一轮文案 Agent 启动时，这些教训会出现在它的 system prompt 里。
>
> 这不是"训练模型"。这是一个活的组织在自学习 —— 每一次审核发现的坑，变成下一次
> 文案必看的 checklist。模块一教它怎么写得好，模块二教它哪里不能踩，组合起来
> 就是一个越用越懂合规、越用越会抓爆款的虚拟文案团队。"

## 可观测指标（留给模块四）

当前闭环已经为模块四的量化对比打好埋点：

| 指标 | 来源 | 预期趋势 |
|------|------|---------|
| search_reference 命中次数 | ReAct tool_calls 统计 | 稳定 ≥1 / 条 |
| search_knowledge 命中次数 | ReAct tool_calls 统计 | 稳定 ≥2 / 轮 |
| 审核驳回条数 | review_feedback 字段 | 随运行次数递减 |
| 规则违规类型多样性 | reviewer reflect 蒸馏 violations_found | 随运行次数收窄 |
| 文案-审核一次通过率 | 项目主表 review_pass_rate | 随运行次数递增 |

模块四 T4-01 `memory/evolution_metrics.py` 实现后可直接采集上述指标。

## 验证证据

`tests/test_module1_module2_combo.py` 10 项断言全通：

```
[PASS] copywriter soul 含 {search_reference, search_knowledge, read_knowledge}
[PASS] _REQUIRED_TOOL_CALLS[copywriter] = ['search_reference', 'search_knowledge']
[PASS] copywriter reflect prompt 含 [reference_pattern, rule_check, conflict_handling]
[PASS] reviewer reflect prompt 已声明 applicable_roles=[reviewer, copywriter]
[PASS] 轨道 A（search_reference）命中且返回结构化卡片
[PASS] 轨道 B-1（search_knowledge 禁用词）命中广告法禁用词.md
[PASS] 轨道 B-2（search_knowledge 平台规范）命中平台规范.md
[PASS] read_knowledge 可读取广告法禁用词.md（长度=1051）
[PASS] _hook_reflect 代码级兜底：reviewer→copywriter 反哺确保
[PASS] copywriter soul body 含融合工作流关键词
```
