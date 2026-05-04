---
created: 2026-05-04
source: Agent 自动蒸馏
category: 新品发布
role: reviewer
---

# reviewer_文案提交前必须执行4项预检：1) 禁用词_d46fa6c1

## 元信息
- 分类：新品发布
- 角色：reviewer

## 正文
## 场景
新品发布期的鞋服类内容审核场景（小红书图文 + 抖音口播）

## 策略
先按平台与合规关键词检索并读取规则库（广告法禁用词、平台规则），再按五维（banned_words/brand_tone/platform_spec/dept_style/fact_check）逐条核查；对每条内容独立调用 submit_review，强制填写完整 dimensions，并确保 review_status 与 review_feedback 均落库。

## 结果
本轮内容在合规与调性维度整体可通过，主要问题集中在审核写回完整性；补齐缺失字段后，审核记录可追溯且可进入后续排期流转。

## 经验教训
文案提交前必须执行4项预检：1) 禁用词扫描（最好/第一/100%/必买/无副作用等）；2) 对比句加证据锚点（材料、工艺、结构、测试口径，缺一则改为“更强调/更适合”）；3) 价格与价值表述去绝对化（用“可按需求选择/侧重设计升级”替代“最划算”）；4) 发布前流程检查清单确认 review_status、review_feedback、五维字段齐全。


> 来源角色: reviewer
