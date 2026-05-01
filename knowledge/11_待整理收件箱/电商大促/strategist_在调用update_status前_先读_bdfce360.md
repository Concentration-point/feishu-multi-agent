---
created: 2026-04-28
source: Agent 自动蒸馏
category: 电商大促
role: strategist
---

# strategist_在调用update_status前，先读_bdfce360

## 元信息
- 分类：电商大促
- 角色：strategist

## 正文
## 场景
在“某护肤品牌-电商大促”项目中，需基于不完整Brief（品牌主体与KPI缺失）完成策略制定与排期创建，且必须覆盖指定平台（公众号/小红书/抖音）、完成内外部调研并写回系统。

## 策略
先用read_project读取Brief解读与约束并send_message启动同步；随后用search_knowledge+read_knowledge提炼同预算同赛道历史配比与复盘教训；再用search_web抓取外部趋势并对2条可读HTML页面执行web_fetch深读（跳过PDF不可读源）；据此输出“预热-升温-爆发-长尾”节奏的6条差异化内容矩阵，并通过batch_create_content与write_project一次性落表，最后send_message广播完成。

## 结果
策略方案成功写入，6条内容行成功创建并完成团队通知；外部与内部依据齐全，平台与卖点配比可执行。唯一问题是update_status尝试写入“策略中”时被状态机拦截（当前已是策略中，仅允许流转到撰写中）。

## 经验教训
在调用update_status前，先读取并校验当前状态与允许流转列表；若当前已是目标状态，则跳过更新并在完成通知中明确“状态无需变更”，避免无效调用和流程噪音。


> 来源角色: strategist
