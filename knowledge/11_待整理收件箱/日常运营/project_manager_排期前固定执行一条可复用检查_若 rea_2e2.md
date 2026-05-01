---
created: 2026-04-30
source: Agent 自动蒸馏
category: 日常运营
role: project_manager
---

# project_manager_排期前固定执行一条可复用检查：若 rea_2e2d3348

## 元信息
- 分类：日常运营
- 角色：project_manager

## 正文
## 场景
在“日常运营”项目（record_id: recvicHFQuhatw）中，项目已处于“排期中”，需要作为项目经理基于审核结果为通过内容写入计划发布日期并生成交付摘要。我先后调用了 send_message（开始排期广播）、read_project（读取主表字段）和 list_content（读取全部内容行）。返回结果显示：主表 review_summary 为空、review_pass_rate=0.0；5 条内容行的 review_status 全为空，publish_date 也为空。

## 策略
执行了“先审后排”的门禁策略：先核验主表审核总评/通过率，再逐条筛选内容行 review_status，仅当状态为“通过”才进入排期写回。因未发现任何“通过”内容，停止 write_content / write_project / update_status 的后续动作，不强行排期、不推进已完成，并在结论中明确阻塞点与所需补充数据。

## 结果
避免了违规为未审核内容排期和错误状态流转；完成了读取与校验，但未形成可写回排期，项目保持未完成状态，需上游先补齐审核结果后再继续。

## 经验教训
排期前固定执行一条可复用检查：若 read_project 中 review_summary 为空或 review_pass_rate<=0，或 list_content 中不存在 review_status='通过' 的记录，则立即中止排期写回，只发送“无法完成交付”并点名要求补齐字段（主表：review_summary/review_pass_rate；子表：review_status/review_feedback），补齐后再重跑。


> 来源角色: project_manager
