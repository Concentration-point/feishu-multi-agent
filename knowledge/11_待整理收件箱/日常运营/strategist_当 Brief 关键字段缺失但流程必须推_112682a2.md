---
created: 2026-04-30
source: Agent 自动蒸馏
category: 日常运营
role: strategist
---

# strategist_当 Brief 关键字段缺失但流程必须推_112682a2

## 元信息
- 分类：日常运营
- 角色：strategist

## 正文
## 场景
在“日常运营”项目中，作为 strategist 需要基于 record_id=recvicO5Ayt02j 为本地餐饮客户（烧烤店）制定可执行内容策略；上游 Brief 已明确品牌调性与核心卖点（鲜货现烤、食材丰富），但缺失预算、商圈、账号基础、优惠机制等关键经营信息，且项目已处于“策略中”需尽快推进到“撰写中”。

## 策略
按四步流程执行并保留可追溯证据：1) 用 read_project 读取 brief_analysis/brand_tone/dept_style/project_type，并 send_message 宣布启动；2) 用 search_knowledge 检索“日常运营 内容矩阵/策略/内容配比”，发现同品类直接经验不足，采用“3-6条小规模验证”内部方法；3) 先用 search_web 做外部检索，再对返回 URL 执行 web_fetch 深读（1个页面抽取失败后立即更换 URL 重试），提取可引用的趋势数字与链路信息；4) 在信息缺失前提下输出最小可执行三平台矩阵（抖音/小红书/视频号，一条一卖点、错峰节奏），并依次调用 batch_create_content、write_project、update_status(撰写中)、send_message 完成闭环。

## 结果
成功创建 3 条差异化内容排期并写入策略方案，状态从“策略中”推进到“撰写中”，团队收到完成通知；外部调研完成且满足“search_web + web_fetch”要求；过程中出现 1 次 web_fetch 空抽取（疑似 JS/反爬）但通过更换来源解决，未阻塞交付。

## 经验教训
当 Brief 关键字段缺失但流程必须推进时，先固定执行“最小验证矩阵”规则：仅做 3 条内容、覆盖 Brief 提及平台、每条只打 1 个不同卖点、发布必须错峰；同时在策略风险提示中明确缺失信息清单（商圈/客单/优惠/账号数据），并在完成消息里同步“先跑首轮数据再扩量”——这样既不空转也不越界。


> 来源角色: strategist
