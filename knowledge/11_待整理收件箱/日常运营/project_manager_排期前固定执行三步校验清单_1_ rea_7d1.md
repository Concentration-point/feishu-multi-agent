---
created: 2026-04-29
source: Agent 自动蒸馏
category: 日常运营
role: project_manager
---

# project_manager_排期前固定执行三步校验清单：1) rea_7d19939d

## 元信息
- 分类：日常运营
- 角色：project_manager

## 正文
## 场景
在“日常运营”项目（record_id: recvicHFQuhatw）中，项目已处于“排期中”，需要按流程为审核通过内容写入发布日期并生成交付摘要。我先调用 send_message 发送“开始排期”广播，再调用 read_project 读取主表字段（client_name、project_type、brand_tone、status、strategy、review_summary、review_pass_rate），随后调用 list_content 拉取全部内容行并检查 review_status 与 publish_date。

## 策略
执行了“先审后排”的硬校验：先核对主表审核结果是否完整（review_summary 非空、review_pass_rate 可用），再逐条筛选内容行是否为“审核通过”。发现主表 review_summary 为空、review_pass_rate=0.0，且全部内容行 review_status 为空后，立即停止 write_content、write_project、update_status 操作，避免违规排期与错误完结，仅输出阻塞原因并请求上游补齐审核写回。

## 结果
成功避免了对未审核内容进行排期、避免错误推进到“已完成”；流程在“审核结果缺失”处被安全拦截，状态保持合规，但本轮未产生发布日期写回和交付摘要写回。

## 经验教训
排期前固定执行三步校验清单：1) read_project 检查 review_summary 非空且 review_pass_rate>0；2) list_content 统计 review_status=“通过”的记录数；3) 仅当“通过数>=1”时才执行 write_content/write_project/update_status，否则立刻发送“无法完成交付”并列出缺失字段（主表+内容行）供上游补齐。


> 来源角色: project_manager
