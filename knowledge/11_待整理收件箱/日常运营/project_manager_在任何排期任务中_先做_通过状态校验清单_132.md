---
created: 2026-04-30
source: Agent 自动蒸馏
category: 日常运营
role: project_manager
---

# project_manager_在任何排期任务中，先做“通过状态校验清单_132b1b28

## 元信息
- 分类：日常运营
- 角色：project_manager

## 正文
## 场景
在“日常运营”项目（客户：烧烤店测试1，record_id: recvicHFQuhatw）中，项目状态已是“排期中”，但需要按SOP仅为审核通过内容写入发布日期并生成交付摘要。

## 策略
先发送开始排期广播（send_message），再并行读取项目主表关键字段（read_project: client_name/project_type/brand_tone/status/strategy/review_summary/review_pass_rate）与全部内容行（list_content），逐条核对review_status与publish_date，仅在存在“通过”记录时才执行write_content排期、write_project写摘要和状态收口。

## 结果
读取结果显示review_summary为空、review_pass_rate=0.0，且5条内容的review_status均为空；判定可排期内容为0，未执行write_content/write_project/update_status，避免了违规放行和错误完结。

## 经验教训
在任何排期任务中，先做“通过状态校验清单”：若review_summary为空或review_pass_rate<=0或不存在review_status=“通过”的记录，则立即停止写回动作，仅保留进度广播并触发上游补齐审核结果；不要先写发布日期再回头校验。


> 来源角色: project_manager
