---
created: 2026-04-29
source: Agent 自动蒸馏
category: 日常运营
role: project_manager
---

# project_manager_进入排期前固定执行“通过状态校验清单”：_d514f3d1

## 元信息
- 分类：日常运营
- 角色：project_manager

## 正文
## 场景
在“日常运营”项目（record_id: recvicHHWMBtJO）中，用户要求项目经理按流程完成排期与交付收口；我先并行调用 send_message（开始排期广播）、read_project（读取审核总评/通过率/状态等）和 list_content（拉取全部内容行）。返回结果显示项目主表 review_summary 为空、review_pass_rate=0.0，且5条内容行的 review_status 均为空、publish_date 均未填写。

## 策略
先做审核前置校验：以 read_project 的审核字段和 list_content 的逐条 review_status 作为排期准入门槛；在确认“无任何通过内容”后，严格停止 write_content、write_project、update_status（不推进到已完成），并输出阻断原因与所需补充字段。

## 结果
成功避免了对未审核内容的违规排期和错误完结；流程停在可控点并向上游明确了缺失项，但本轮未能产出排期写回、交付摘要写回和完成态流转。

## 经验教训
进入排期前固定执行“通过状态校验清单”：1) 先看项目级 review_summary 非空且 review_pass_rate>0；2) 再逐条筛选 review_status=="通过"；3) 仅对通过且 publish_date 为空的记录写入日期；若通过数=0，立即中止写操作并先发“无法完成交付”说明，避免后续状态更新卡死或违规完结。


> 来源角色: project_manager
