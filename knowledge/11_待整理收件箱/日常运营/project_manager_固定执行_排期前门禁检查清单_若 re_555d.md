---
created: 2026-04-30
source: Agent 自动蒸馏
category: 日常运营
role: project_manager
---

# project_manager_固定执行“排期前门禁检查清单”：若 re_555df941

## 元信息
- 分类：日常运营
- 角色：project_manager

## 正文
## 场景
在“日常运营”项目中（客户：烧烤店测试1，状态：排期中），需要作为项目经理基于审核结果为通过内容排期并写交付摘要。我先后调用 read_project、list_content、send_message。read_project 返回 review_summary 为空、review_pass_rate=0.0；list_content 返回 5 条内容且 review_status 全为空、publish_date 全为空。

## 策略
先执行只读校验再决定是否写回：1）用 read_project 核对审核总评/通过率/当前状态；2）用 list_content 逐条筛选 review_status=通过 的记录；3）在可排期数为 0 时，不调用 write_content、write_project、update_status，避免违规推进；4）仅发送进度广播说明“已接收审核结果、当前无法完成交付”。

## 结果
成功完成流程合规检查并避免误排期；未产生任何越权写回或错误状态流转。项目未被推进到“已完成”，风险被显式暴露为“审核结果缺失导致无可排期内容”。

## 经验教训
固定执行“排期前门禁检查清单”：若 review_summary 为空或 review_pass_rate<=0，或 list_content 中无任何 review_status=通过 记录，则立即停止所有写操作（write_content/write_project/update_status），只发送“无法完成交付”消息并等待审核补录后再继续。


> 来源角色: project_manager
