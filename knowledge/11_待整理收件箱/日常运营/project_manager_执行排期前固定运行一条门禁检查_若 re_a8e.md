---
created: 2026-04-29
source: Agent 自动蒸馏
category: 日常运营
role: project_manager
---

# project_manager_执行排期前固定运行一条门禁检查：若 re_a8e8929a

## 元信息
- 分类：日常运营
- 角色：project_manager

## 正文
## 场景
在日常运营项目（record_id: recvicHFQuhatw）中，项目状态已是“排期中”，需要我作为 project_manager 基于审核结果为通过内容安排发布日期并生成交付摘要。我先调用 read_project 读取到 review_summary 为空、review_pass_rate=0.0；再调用 list_content 读取到 5 条内容行的 review_status 均为空、publish_date 均为空。

## 策略
严格按流程先做“可排期资格校验”：先读主表审核字段，再全量读取内容行并筛选 review_status=通过。发现通过集合为空后，停止 write_content / write_project / update_status 操作，不越权改审核结论，并输出阻塞原因与上游所需补充项（先完成审核字段写回）。

## 结果
避免了对未审核内容违规排期，也避免了无效状态流转；任务在合规前提下被正确中止，并形成了明确的恢复路径（审核补齐后再排期）。

## 经验教训
执行排期前固定运行一条门禁检查：若 review_summary 为空或 review_pass_rate<=0，或内容表中 review_status=“通过”的记录数为 0，则立即中止后续写操作（write_content/write_project/update_status），仅返回“需先补齐审核结果”的明确清单。


> 来源角色: project_manager
