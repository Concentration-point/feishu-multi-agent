---
created: 2026-04-29
source: Agent 自动蒸馏
category: 电商大促
role: strategist
---

# strategist_先做“两层检索”再定矩阵：第1层用 se_f1cae59b

## 元信息
- 分类：电商大促
- 角色：strategist

## 正文
## 场景
在 record_id=recvi8QQXuRcrI 的电商大促项目中，Brief 已给出平台范围（公众号/小红书/抖音）与预算（5万），但品牌主体与量化KPI缺失；需要在“策略中”阶段完成内外部调研并产出可执行内容矩阵。

## 策略
先用 read_project 锁定约束与缺口并 send_message 同步启动；再用 search_knowledge+read_knowledge 提取同类618项目的内容配比与复盘结论；随后用 search_web 做外部趋势检索，并对返回URL执行 web_fetch 深读（遇到 PDF 被拒后立即切换到 HTML 来源）；最后按“平台全覆盖+卖点差异化+分阶段节奏”生成策略方案并落表（write_project）、批量建行（batch_create_content）、更新状态到撰写中（update_status）并广播完成（send_message）。

## 结果
完成了全链路工具调用与交付动作，策略方案具备内外部依据和可执行排期；在外部抓取阶段识别并规避了 PDF 抓取限制，没有中断流程，项目顺利推进到“撰写中”。

## 经验教训
先做“两层检索”再定矩阵：第1层用 search_knowledge 固化历史高效配比，第2层用 search_web 后至少 web_fetch 1个HTML权威页；若首个链接为PDF/登录墙，30秒内改抓下一条HTML，不等待同源修复，避免策略阶段卡住。


> 来源角色: strategist
