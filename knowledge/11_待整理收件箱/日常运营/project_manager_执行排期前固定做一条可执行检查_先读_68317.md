---
created: 2026-04-29
source: Agent 自动蒸馏
category: 日常运营
role: project_manager
---

# project_manager_执行排期前固定做一条可执行检查：`先读_6831771d

## 元信息
- 分类：日常运营
- 角色：project_manager

## 正文
## 场景
在项目 recvicHHWMBtJO（客户：烧烤店测试2，项目类型：日常运营，当前状态：排期中）中，项目经理需要基于审核结果为通过内容排期并生成交付摘要。我先后调用 send_message（开始排期广播）、read_project（读取 client_name/project_type/brand_tone/status/strategy/review_summary/review_pass_rate）和 list_content（读取全部内容行）。结果显示 review_summary 为空、review_pass_rate=0.0，且 5 条内容的 review_status 全为空、publish_date 全为空。

## 策略
采用“先校验再写回”的门禁策略：先并行完成开始广播与主表/内容表只读检查；再按规则逐条筛选 review_status=通过 的记录。发现可排期数为 0 后，立即停止 write_content/write_project/update_status，不做任何排期写回或完结状态推进，仅输出阻塞原因与后续选项。

## 结果
避免了对未通过或未审核内容的违规排期，保持状态机与审核边界一致；但本轮未能进入交付写回阶段，项目无法推进到已完成。

## 经验教训
执行排期前固定做一条可执行检查：`先读 review_pass_rate + 全量 review_status；若“通过”条数=0，则禁止调用 write_content/write_project/update_status`，只发送阻塞说明并要求审核环节先补齐状态。


> 来源角色: project_manager
