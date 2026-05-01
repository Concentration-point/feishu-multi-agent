---
created: 2026-04-29
source: Agent 自动蒸馏
category: 日常运营
role: project_manager
---

# project_manager_执行排期前必须先跑“通过状态校验清单”：_55fb1f31

## 元信息
- 分类：日常运营
- 角色：project_manager

## 正文
## 场景
在“日常运营”项目（客户：烧烤店测试1，record_id: recvicHFQuhatw）中，项目已处于“排期中”，需要按SOP执行项目经理收口：读取审核结果、筛选通过内容、写入发布日期、生成交付摘要并推进状态。

## 策略
先发送“开始排期”广播（send_message），再并行读取项目主表与内容表（read_project + list_content）做准入校验：重点检查 review_summary、review_pass_rate 以及每条内容的 review_status；发现审核字段缺失后，立即停止 write_content/write_project/update_status，改为输出阻塞说明并请求补齐审核数据。

## 结果
成功完成了流程前置校验与进度同步，避免了对未审核内容误排期；识别到项目主表 review_summary 为空、review_pass_rate=0.0，且全部内容行 review_status 为空，因无可排期内容未执行写回与状态完结。

## 经验教训
执行排期前必须先跑“通过状态校验清单”：若项目 review_summary 为空或 review_pass_rate<=0，或内容表中不存在 review_status=“通过”的记录，则只发送阻塞通知并暂停，不得写 publish_date、不得写交付摘要完结版、不得更新为“已完成”。


> 来源角色: project_manager
