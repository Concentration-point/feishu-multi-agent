---
created: 2026-04-29
source: Agent 自动蒸馏
category: 日常运营
role: project_manager
---

# project_manager_进入排期前先执行“通过状态校验清单”：逐_a621e7ff

## 元信息
- 分类：日常运营
- 角色：project_manager

## 正文
## 场景
在“日常运营”项目（record_id: recvicHFQuhatw）中，项目状态已是“排期中”，但需要按流程只对审核通过内容写入计划发布日期并生成交付摘要。

## 策略
先并行调用 read_project 与 list_content 做前置校验：读取到 review_summary 为空、review_pass_rate=0，且5条内容的 review_status 全为空；据此停止 write_content/write_project/update_status，仅发送“无法完成交付”广播并明确缺失项。

## 结果
避免了违规排期和错误完结；项目未被误更新为“已完成”，并向上游清晰暴露了审核结果缺失这一阻塞点。

## 经验教训
进入排期前先执行“通过状态校验清单”：逐条确认 review_status=通过 且项目级 review_summary/review_pass_rate 已写入；任一项缺失就不要写 publish_date，也不要推进状态，直接回传缺失字段清单让审核环节补齐。


> 来源角色: project_manager
