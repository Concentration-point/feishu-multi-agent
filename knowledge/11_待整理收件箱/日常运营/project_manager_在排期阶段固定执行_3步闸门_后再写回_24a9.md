---
created: 2026-04-30
source: Agent 自动蒸馏
category: 日常运营
role: project_manager
---

# project_manager_在排期阶段固定执行“3步闸门”后再写回：_24a9caa7

## 元信息
- 分类：日常运营
- 角色：project_manager

## 正文
## 场景
在“日常运营”项目（客户：烧烤店测试1，record_id: recvicHFQuhatw）中，项目状态已是“排期中”，需要按流程为“审核通过”的内容写入计划发布日期并生成交付摘要；我先后调用了 send_message（开始排期广播）、read_project（读取审核总评/通过率/状态等）、list_content（拉取全部内容行及审核状态）。

## 策略
先发开始广播，再进行“审核前置校验”：核对项目级 review_summary 与 review_pass_rate，并逐条筛查内容行 review_status，仅允许对状态为“通过”的记录排期；当发现项目级审核字段为空且全部内容行 review_status 为空时，立即停止 write_content/write_project/update_status，转为输出阻塞说明与上游补数要求。

## 结果
成功避免了对未审核内容误排期和违规状态流转；未执行任何写回操作（未写 publish_date、未写交付摘要、未变更状态），并明确给出无法继续的具体原因与下一步依赖项。

## 经验教训
在排期阶段固定执行“3步闸门”后再写回：1）read_project 必须读到非空 review_summary；2）review_pass_rate > 0 且与内容通过情况一致；3）list_content 中至少1条 review_status=“通过”。任一步不满足，禁止调用 write_content/write_project/update_status，并立刻通知审核环节补齐字段。


> 来源角色: project_manager
