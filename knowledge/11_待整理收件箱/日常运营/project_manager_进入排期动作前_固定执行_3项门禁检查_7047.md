---
created: 2026-04-30
source: Agent 自动蒸馏
category: 日常运营
role: project_manager
---

# project_manager_进入排期动作前，固定执行“3项门禁检查”_70472ca9

## 元信息
- 分类：日常运营
- 角色：project_manager

## 正文
## 场景
在“日常运营”项目（record_id: recvicHFQuhatw）中，项目状态已是“排期中”，但需要按SOP仅对审核通过内容写入计划发布日期并生成交付摘要。我先后调用了 send_message（开始排期广播）、read_project（读取到 review_summary 为空、review_pass_rate=0.0、status=排期中）、list_content（5条内容均 review_status 为空、publish_date 为空）。

## 策略
先执行前置校验再排期：1）先读项目主表审核字段；2）全量拉取内容行并逐条筛查 review_status；3）发现无“通过”记录后立即停止 write_content/write_project/update_status，避免违规排期与错误完结；4）向用户明确阻塞字段与可继续执行的最小前提（补齐审核状态）。

## 结果
成功避免了对未通过/未判定内容的错误排期，未发生越权写回或错误状态流转；但本轮未能完成排期、交付摘要写回和项目完结，流程阻塞在审核结果缺失。

## 经验教训
进入排期动作前，固定执行“3项门禁检查”：`review_summary`非空、`review_pass_rate`可用、内容行中至少1条`review_status=通过`；任一不满足时，立即中止所有写操作（不调用write_content/write_project/update_status），仅输出缺失字段清单并要求审核环节补齐后再继续。


> 来源角色: project_manager
