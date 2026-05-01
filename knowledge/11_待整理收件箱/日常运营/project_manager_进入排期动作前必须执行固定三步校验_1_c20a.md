---
created: 2026-04-30
source: Agent 自动蒸馏
category: 日常运营
role: project_manager
---

# project_manager_进入排期动作前必须执行固定三步校验：1)_c20a8bfd

## 元信息
- 分类：日常运营
- 角色：project_manager

## 正文
## 场景
在“日常运营”项目（record_id: recvicHFQuhatw）中，项目已处于“排期中”，我先后调用 send_message（开始排期广播）、read_project（读取到 review_summary 为空、review_pass_rate=0.0）、list_content（5条内容的 review_status 全为空），需要判断是否可执行发布日期写回与项目收口。

## 策略
按“先审后排”门禁执行：先读主表审核字段，再全量拉取内容行并逐条筛选 review_status=通过；当可排期内容=0时，停止 write_content/write_project/update_status，不强行排期或完结，仅保留进度说明并等待上游补齐审核结果。

## 结果
避免了对未审核内容误排期和错误状态收口；成功识别阻塞点为审核结果缺失（主表与内容行双缺），流程在合规边界内安全暂停。

## 经验教训
进入排期动作前必须执行固定三步校验：1) read_project确认 review_summary 非空且 review_pass_rate>0；2) list_content统计 review_status=通过 的记录数；3) 仅当“通过数>=1”时才执行 write_content 与 write_project，否则立即发送“无法完成交付”广播并挂起等待审核补录。


> 来源角色: project_manager
