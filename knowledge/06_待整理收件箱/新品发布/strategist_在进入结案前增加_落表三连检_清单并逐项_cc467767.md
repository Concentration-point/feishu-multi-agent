---
created: 2026-05-04
source: Agent 自动蒸馏
category: 新品发布
role: strategist
---

# strategist_在进入结案前增加“落表三连检”清单并逐项_cc467767

## 元信息
- 分类：新品发布
- 角色：strategist

## 正文
## 场景
在“回力-新品发布”项目中，需要按流程完成策略制定：先读上游Brief并核验缺失项，再检索内部经验与外部竞品情报，最后产出小红书+抖音内容矩阵并写入项目主表；过程中外部检索首轮出现大量聚合站噪音，且部分目标页面被robots拦截。

## 策略
先用 read_project 获取brief_analysis并识别“默认推断”项（KPI数值缺失）；同步 send_message 报备启动；用 search_knowledge+read_knowledge提取内部新品发布可复用框架（预热-爆发-长尾）；外部先 search_web 再 web_fetch 定向深读，遇到robots拦截立即二次检索替换来源，只采纳页面明确陈述并标注口径；随后根据预算5万与平台约束设计最小可执行矩阵（双平台、总数>=3、卖点去重、错峰发布），并需补写 strategy 字段。

## 结果
完成了上游核验、内部经验提炼与至少1篇外部深读，识别了外部数据可信度风险和抓取限制；但出现主表 strategy 字段未写入的缺口，需要继续执行 write_project 完成落表后再结束。

## 经验教训
在进入结案前增加“落表三连检”清单并逐项执行：1) 先 read_project 检查 strategy 是否为空；2) 若为空立即 write_project 写入完整策略；3) 再次 read_project 复核字段已落库后，才做状态更新与收尾通知，避免流程完成但主表缺失。


> 来源角色: strategist
