---
created: 2026-04-29
source: Agent 自动蒸馏
category: 日常运营
role: project_manager
---

# project_manager_在任何排期动作前先执行一份“通过状态校验_cf414ca8

## 元信息
- 分类：日常运营
- 角色：project_manager

## 正文
## 场景
在“日常运营”项目（record_id: recvicHHWMBtJO）中，项目状态已是“排期中”，需要按流程读取审核结果后，仅对审核通过内容安排发布日期并生成交付摘要。

## 策略
先用 send_message 发送“开始排期”广播；并行调用 read_project（读取 client_name/project_type/brand_tone/status/strategy/review_summary/review_pass_rate）与 list_content（拉取全部内容行）；逐条校验 review_status，仅将“通过”作为可排期候选，同时核对 publish_date 是否已有值。

## 结果
read_project 返回 review_summary 为空、review_pass_rate=0.0；list_content 返回 5 条内容且 review_status 全为空，导致可排期内容数为 0。依据规则未执行 write_content、未推进到“已完成”，并判定应进入“无法完成交付”说明路径。

## 经验教训
在任何排期动作前先执行一份“通过状态校验清单”：统计全部内容行中 review_status='通过' 的数量；若数量为 0，立即停止 write_content 与状态完结操作，只输出未完成说明并触发“无法完成交付”广播，避免违规强行排期。


> 来源角色: project_manager
