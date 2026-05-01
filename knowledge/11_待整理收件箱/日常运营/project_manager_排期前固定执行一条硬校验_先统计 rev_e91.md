---
created: 2026-04-29
source: Agent 自动蒸馏
category: 日常运营
role: project_manager
---

# project_manager_排期前固定执行一条硬校验：先统计 rev_e9132b9a

## 元信息
- 分类：日常运营
- 角色：project_manager

## 正文
## 场景
在“日常运营”项目中，项目状态已是“排期中”，需要项目经理基于审核结果为通过内容写入计划发布日期并生成交付摘要；但读取主表后发现 review_summary 为空、review_pass_rate=0，读取全部 5 条内容行后发现 review_status 全为空，无法识别任何“审核通过”内容。

## 策略
先按流程并行调用 read_project 与 list_content完成前置校验，并发送“开始排期”广播；随后执行“通过状态校验清单”，仅以 review_status=通过 作为排期准入条件，因通过数为 0 而停止 write_content；改为 write_project 写回结构化交付摘要（未排期原因点名 record_id + 后续补充项），最后发送“无法完成交付”广播且不推进到“已完成”。

## 结果
流程合规收口：未对未审核内容误排期，成功写回交付摘要并完成异常广播；项目保持未完成状态，明确阻塞点为审核字段未回填，避免了错误状态流转和合规风险。

## 经验教训
排期前固定执行一条硬校验：先统计 review_status=“通过” 且 publish_date 为空的记录数；若计数为 0，立即停止写排期与完成态更新，改为写回交付摘要中的“未排期原因（含具体 record_id）+ 需审核补齐字段清单（review_status/review_feedback/review_summary/review_pass_rate）”，并发送“无法完成交付”广播。


> 来源角色: project_manager
