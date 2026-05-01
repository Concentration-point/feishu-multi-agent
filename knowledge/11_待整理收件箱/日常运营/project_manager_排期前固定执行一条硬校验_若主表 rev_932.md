---
created: 2026-04-30
source: Agent 自动蒸馏
category: 日常运营
role: project_manager
---

# project_manager_排期前固定执行一条硬校验：若主表 rev_932df9da

## 元信息
- 分类：日常运营
- 角色：project_manager

## 正文
## 场景
在“日常运营”项目（record_id: recvicHFQuhatw）中，项目状态已是“排期中”，但需要按SOP先读取审核结果并仅对审核通过内容排期。我调用了 send_message 发送开始排期广播、read_project 读取主表字段、list_content 拉取全部内容行后发现：主表 review_summary 为空、review_pass_rate=0.0，且5条内容的 review_status 全为空。

## 策略
先执行“审核可排期性校验”再做任何写回：1) 读取主表审核总评/通过率/状态；2) 拉取全部内容并逐条筛查 review_status 是否为“通过”；3) 在未命中“通过”记录时，停止 write_content/write_project/update_status，避免违规排期与错误状态流转；4) 向用户明确缺失字段与下一步补录要求。

## 结果
成功完成前置核查并避免了对未审核内容的错误排期；已发送开始广播并给出阻塞原因与补救路径，但未执行发布日期写回、交付摘要写回和完成态推进，因为不满足流程准入条件。

## 经验教训
排期前固定执行一条硬校验：若主表 review_summary 为空或 review_pass_rate<=0，或内容表中 review_status=“通过”的记录数为0，则立即中止所有写操作（write_content/write_project/update_status），仅输出“缺失审核结果清单+需补字段（review_status、review_summary、review_pass_rate）”，待补齐后再继续。


> 来源角色: project_manager
