---
created: 2026-04-29
source: Agent 自动蒸馏
category: 日常运营
role: project_manager
---

# project_manager_排期前固定执行一条门禁规则：只有当“至少_39575ac8

## 元信息
- 分类：日常运营
- 角色：project_manager

## 正文
## 场景
在“日常运营”项目（record_id: recvicHFQuhatw）中，项目状态已是“排期中”，我需要按流程为审核通过内容安排发布日期并生成交付摘要。我先调用 read_project 读取主表字段（含 review_summary、review_pass_rate），再调用 list_content 拉取全部5条内容行并检查 review_status。

## 策略
先做“审核可排期前置校验”：1）确认项目主表是否存在审核总评与通过率；2）逐条筛选 review_status=通过 的内容；3）若通过条数为0或审核字段缺失，则立即停止 write_content/write_project/update_status，仅输出阻塞原因与下一步要求，避免违规排期或错误收口。

## 结果
read_project 返回 review_summary 为空、review_pass_rate=0.0；list_content 显示5条内容的 review_status 全为空，导致可排期内容为0。我未执行写回与状态推进，成功避免了对未通过内容排期和错误标记“已完成”的风险。

## 经验教训
排期前固定执行一条门禁规则：只有当“至少1条 review_status=通过”且“review_summary 非空、review_pass_rate 有效”同时满足时，才进入写入 publish_date；否则立即中止并回传缺失字段清单（含具体 record_id）。


> 来源角色: project_manager
