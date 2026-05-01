---
created: 2026-04-30
source: Agent 自动蒸馏
category: 日常运营
role: project_manager
---

# project_manager_排期前必须执行“通过状态校验清单”：1）_2869a41e

## 元信息
- 分类：日常运营
- 角色：project_manager

## 正文
## 场景
在项目 record_id=recvicHFQuhatw（客户：烧烤店测试1，项目类型：日常运营，当前状态：排期中）中，需按项目经理流程对“审核通过”内容排期并生成交付摘要。

## 策略
先并行调用 send_message（开始排期广播）、read_project（读取审核总评/通过率/状态等主表字段）、list_content（读取全部内容行）；随后按规则筛选 review_status=通过 的内容并检查 publish_date。核查结果显示主表 review_summary 为空、review_pass_rate=0.0，且全部内容行 review_status 为空，因此未执行 write_content、write_project、update_status，仅输出阻断原因并请求是否进入“无法完成交付”分支。

## 结果
成功完成前置校验与风险拦截，避免了对未通过内容强行排期或错误推进“已完成”；流程停在可控点，等待上游补齐审核结果或用户确认后续动作。

## 经验教训
排期前必须执行“通过状态校验清单”：1）read_project确认 review_pass_rate>0 且 review_summary 非空；2）list_content逐条确认至少1条 review_status=通过；3）仅对“通过且 publish_date 为空”的记录写入日期。任一条件不满足，立即停止写回并发送“无法完成交付”提示，不做状态完结。


> 来源角色: project_manager
