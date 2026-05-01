---
created: 2026-04-30
source: Agent 自动蒸馏
category: 日常运营
role: project_manager
---

# project_manager_在任何排期任务中，先执行“3项硬校验”再_f3a2e36c

## 元信息
- 分类：日常运营
- 角色：project_manager

## 正文
## 场景
在“日常运营”项目（客户：烧烤店测试1，record_id: recvicHFQuhatw）中，项目状态已是“排期中”，需要按流程为审核通过内容写入发布日期并生成交付摘要。我先后调用了 send_message（发送开始排期广播）、read_project（读取到 review_summary 为空、review_pass_rate=0.0）、list_content（5条内容的 review_status 均为空、publish_date 均为空）。

## 策略
严格按前置校验执行：先读项目审核字段，再读全部内容行并仅筛选 review_status=“通过”。当发现项目级与内容级审核结果均缺失时，立即停止 write_content/write_project/update_status，不做任何排期写回或状态推进，并按“无法完成交付”逻辑输出阻塞原因与补充数据清单。

## 结果
避免了对未审核内容误排期和错误完结项目；成功识别流程阻塞点并给出可继续执行的明确前提（补齐 review_status、review_summary、review_pass_rate）。本轮未进入“已完成”。

## 经验教训
在任何排期任务中，先执行“3项硬校验”再动笔写回：1) read_project 中 review_summary 非空；2) review_pass_rate > 0；3) list_content 至少1条 review_status=“通过”。任一不满足时，禁止调用 write_content/update_status，直接输出缺失字段与责任环节。


> 来源角色: project_manager
