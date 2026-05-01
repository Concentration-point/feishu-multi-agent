---
created: 2026-04-30
source: Agent 自动蒸馏
category: 日常运营
role: project_manager
---

# project_manager_进入排期前先执行硬性门槛检查：若 rea_79815077

## 元信息
- 分类：日常运营
- 角色：project_manager

## 正文
## 场景
在“日常运营”项目（record_id: recvicHFQuhatw）中，项目状态已是“排期中”，我作为 project_manager 需要基于审核结果为通过内容安排发布日期并生成交付摘要。我先调用 read_project 读取到 review_summary 为空、review_pass_rate=0.0；再调用 list_content 读取5条内容，发现全部 review_status 为空且 publish_date 为空。

## 策略
按流程先做审核可排期校验：仅筛选 review_status=“通过”的内容；结果为0条后，停止 write_content/write_project/update_status，避免违规推进；随后调用 send_message 先发“开始排期”广播，再发“无法完成交付（无可排期内容）”广播，并在结果中明确卡点为审核结果未回填。

## 结果
成功完成了上下文读取与全量内容检查，避免了对未通过内容强行排期，也未错误推进到“已完成”；任务在规则边界内安全收口，但本轮未产生排期写回与交付摘要写回。

## 经验教训
进入排期前先执行硬性门槛检查：若 read_project 的 review_pass_rate<=0 或 list_content 中不存在任何 review_status=“通过”记录，则立即中止写操作（不调用 write_content/write_project/update_status），仅发送“无法完成交付”广播并点名需上游补齐审核字段后再继续。


> 来源角色: project_manager
