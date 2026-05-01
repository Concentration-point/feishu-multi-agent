---
created: 2026-04-30
source: Agent 自动蒸馏
category: 日常运营
role: project_manager
---

# project_manager_执行排期前固定先跑一条检查清单：1) r_35b4c597

## 元信息
- 分类：日常运营
- 角色：project_manager

## 正文
## 场景
在“日常运营”项目（record_id: recvicHFQuhatw）中，项目状态已是“排期中”，我作为 project_manager 接手后需基于审核结果为通过内容安排发布日期并写交付摘要。我依次调用了 send_message（开始排期广播）、read_project（读取主表关键字段）、list_content（读取全部内容行）。读取结果显示：project 的 review_summary 为空、review_pass_rate=0.0，且5条内容的 review_status 均为空、publish_date 均为空。

## 策略
先按流程做“审核可用性闸门检查”：在任何 write_content / write_project / update_status 前，先验证项目级审核字段与内容级 review_status 是否可用于筛选“通过”内容。确认无“通过”记录后，立即停止排期写回与状态推进，仅输出阻塞原因和上游补充要求，避免违规为未审核内容排期。

## 结果
成功避免了越权排期和错误状态流转；完成了开始广播与数据核验，但未执行发布日期写回、交付摘要写回和“已完成”推进。项目保持在“排期中”，并明确告知需先补齐审核结果。

## 经验教训
执行排期前固定先跑一条检查清单：1) read_project 确认 review_summary 非空且 review_pass_rate>0；2) list_content 统计 review_status='通过' 的记录数；3) 仅当通过数>=1时才调用 write_content 写 publish_date。任一条件不满足时，立刻停止写操作并反馈“缺少审核结果字段/通过记录”。


> 来源角色: project_manager
