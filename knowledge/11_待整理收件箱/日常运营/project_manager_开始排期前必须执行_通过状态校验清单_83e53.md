---
created: 2026-04-29
source: Agent 自动蒸馏
category: 日常运营
role: project_manager
---

# project_manager_开始排期前必须执行“通过状态校验清单”：_83e5365d

## 元信息
- 分类：日常运营
- 角色：project_manager

## 正文
## 场景
在“日常运营”项目（客户：烧烤店测试1，record_id: recvicHFQuhatw）中，项目状态已是“排期中”，需要按流程为审核通过内容写入计划发布日期并生成交付摘要，但需先确认审核结果是否完整可用。

## 策略
先发送开始排期广播（send_message），再读取项目主表关键字段（read_project：review_summary、review_pass_rate、status等），随后拉取全部内容行（list_content）并逐条筛查review_status；仅当存在“通过”内容时才进入write_content排期与write_project交付摘要写回，否则立即停止后续写回与完成态推进。

## 结果
成功完成流程前置检查并识别到不可排期：项目review_summary为空、review_pass_rate=0.0、5条内容的review_status均为空，因此未执行write_content/write_project/update_status，避免了违规放行与错误结项。

## 经验教训
开始排期前必须执行“通过状态校验清单”：1) read_project确认review_pass_rate与review_summary非空；2) list_content统计review_status=“通过”条数；3) 若通过数=0，立即发送“无法完成交付”广播并停止所有写回动作，等待审核补全后再重试。


> 来源角色: project_manager
