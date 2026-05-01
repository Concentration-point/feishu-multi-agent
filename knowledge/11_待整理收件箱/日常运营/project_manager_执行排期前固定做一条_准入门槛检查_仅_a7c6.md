---
created: 2026-04-30
source: Agent 自动蒸馏
category: 日常运营
role: project_manager
---

# project_manager_执行排期前固定做一条“准入门槛检查”：仅_a7c69a57

## 元信息
- 分类：日常运营
- 角色：project_manager

## 正文
## 场景
在日常运营项目中，项目状态已是“排期中”，但读取到审核总评显示通过率为0%，内容排期表3条内容的review_status均为“需修改”，且审核反馈明确存在禁用词命中与平台字数超限风险。

## 策略
先发送“开始排期”进度广播；随后按顺序调用read_project核验review_summary/review_pass_rate/status，再调用list_content全量读取并筛选“通过”内容；因可排期数为0，严格不调用write_content写发布日期、不推进“已完成”；改为调用write_project写入结构化交付摘要，逐条记录未排期record_id与原因，并保留当前状态。

## 结果
未发生违规排期，未误触发完结状态；项目主表已沉淀可交付说明（未排期原因、后续返工与复审要求），流程合规且可追溯。

## 经验教训
执行排期前固定做一条“准入门槛检查”：仅当`review_status=通过`的内容数>=1时才写`publish_date`并考虑完结；若为0，立即改写交付摘要（逐条列record_id+未排期原因）并停止状态推进到“已完成”。


> 来源角色: project_manager
