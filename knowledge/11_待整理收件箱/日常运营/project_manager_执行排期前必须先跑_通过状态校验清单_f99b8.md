---
created: 2026-04-30
source: Agent 自动蒸馏
category: 日常运营
role: project_manager
---

# project_manager_执行排期前必须先跑“通过状态校验清单”：_f99b8aa9

## 元信息
- 分类：日常运营
- 角色：project_manager

## 正文
## 场景
在“日常运营”项目（客户：烧烤店测试1，record_id: recvicHFQuhatw）中，项目状态已是“排期中”，但需要按流程先核验审核结果后再给通过内容安排发布日期并生成交付摘要。

## 策略
先发送“开始排期”广播；并行调用 read_project 与 list_content 做只读校验：检查项目主表的 review_summary、review_pass_rate、status，以及内容表逐条 review_status 与 publish_date；按“仅审核通过可排期”规则筛选可排期集合，再决定是否进入写回与状态收口。

## 结果
读取结果显示 review_summary 为空、review_pass_rate=0.0，且5条内容 review_status 全为空，因此可排期内容为0；按规则停止 write_content/write_project/update_status，不推进“已完成”，并向用户明确阻塞点与下一步选项。

## 经验教训
执行排期前必须先跑“通过状态校验清单”：若项目级审核字段缺失或所有内容 review_status 非“通过”，立即中止写回，仅输出阻塞原因与所需补齐字段（review_summary、review_pass_rate、各行review_status），避免产生无效排期和错误完结状态。


> 来源角色: project_manager
