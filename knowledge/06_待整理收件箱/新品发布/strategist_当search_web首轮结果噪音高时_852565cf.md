---
created: 2026-05-04
source: Agent 自动蒸馏
category: 新品发布
role: strategist
---

# strategist_当search_web首轮结果噪音高时，_852565cf

## 元信息
- 分类：新品发布
- 角色：strategist

## 正文
## 场景
在“回力-新品发布（record_id: recviAgYuV3I2A）”项目中，需要按流程完成策略制定与内容矩阵创建；上游Brief已给出关键约束（小红书重点、抖音承接、5万仅内容制作费、7月中旬首发），但KPI数值缺失，且外部首轮检索出现大量聚合站/旧闻噪音。

## 策略
先调用read_project核对Brief并用send_message同步启动；再用search_knowledge+read_knowledge提取内部三段式节奏经验；外部情报先search_web，发现噪音后立即二次定向检索，并用web_fetch深读2篇可读来源，仅抽取“页面明确提及的方法论”且标注不采信其效果数据；最后基于“设计证据链+场景证据+抖音单品收束”逻辑，用batch_create_content一次创建4条差异化内容行，并write_project写入完整策略。

## 结果
完成了内部经验检索、外部深读、策略落地与排期创建：成功批量创建4条内容行（小红书2条+抖音2条，卖点互斥、节奏分期），并写入策略方案；方案中对缺失KPI明确标注为风险项并给出48小时复盘口径。

## 经验教训
当search_web首轮结果噪音高时，必须在同一轮执行“二次检索+web_fetch深读2篇”：检索词改成“平台+类目+动作词（如上新/首发/挑战赛）”，提取时只保留可验证原文信息，并在策略里明确“采纳方法论，不采信无审计数据”，再进入batch_create_content，避免凭低可信信息拍板配比。


> 来源角色: strategist
