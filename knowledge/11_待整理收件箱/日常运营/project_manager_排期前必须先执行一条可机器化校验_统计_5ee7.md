---
created: 2026-04-29
source: Agent 自动蒸馏
category: 日常运营
role: project_manager
---

# project_manager_排期前必须先执行一条可机器化校验：统计_5ee75815

## 元信息
- 分类：日常运营
- 角色：project_manager

## 正文
## 场景
在“日常运营”项目（record_id: recvicHHWMBtJO）中，项目状态已是“排期中”，需要按SOP完成排期与交付收口；我先调用 read_project 读取到审核总评为空、审核通过率为0.0，再调用 list_content 读取5条内容后发现全部 review_status 为空（无“通过”记录）。

## 策略
严格按流程先发开始广播（send_message），再做“通过状态校验清单”：仅筛选 review_status=通过 且 publish_date 为空的记录；因可排期数为0，停止 write_content 与完成态推进，改为仅 write_project 写入结构化交付摘要（明确未排期原因并点名 record_id），最后发送“无法完成交付”广播。

## 结果
完成了项目上下文读取、内容全量核查、风险拦截、交付摘要写回和异常广播；避免了对未审核通过内容强行排期，也未违规将状态推进到“已完成”。

## 经验教训
排期前必须先执行一条可机器化校验：统计 `review_status==通过` 的内容数；若为0，则禁止写 `publish_date`、禁止推进“已完成”，仅写回交付摘要中的“未排期原因+具体record_id”，并发送“无法完成交付”消息。


> 来源角色: project_manager
