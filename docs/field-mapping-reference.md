# 字段映射参考

这份文档给联调时对字段名，不讲抽象，直接看字面。

## 项目主表（FIELD_MAP_PROJECT）

| 代码键 | 飞书字段名 |
| --- | --- |
| client_name | 客户名称 |
| brief | Brief 内容 |
| project_type | 项目类型 |
| brand_tone | 品牌调性 |
| dept_style | 部门风格注入 |
| status | 状态 |
| brief_analysis | Brief 解读 |
| strategy | 策略方案 |
| review_summary | 审核总评 |
| review_pass_rate | 审核通过率 |
| review_threshold | 审核阈值 |
| review_red_flag | 审核红线风险 |
| delivery | 交付摘要 |
| knowledge_ref | 知识引用 |

## 内容排期表（FIELD_MAP_CONTENT）

| 代码键 | 飞书字段名 |
| --- | --- |
| project_name | 关联项目 |
| seq | 内容序号 |
| title | 内容标题 |
| platform | 目标平台 |
| content_type | 内容类型 |
| key_point | 核心卖点 |
| target_audience | 目标人群 |
| draft | 成稿内容 |
| word_count | 字数 |
| review_status | 审核状态 |
| review_feedback | 审核反馈 |
| publish_date | 计划发布日期 |
| remark | 备注 |

## 使用建议

联调时，把飞书表头和这张表逐项比。

**一字不差最好。**

如果你非要改代码，也行，但别嘴上说“差不多”。字段名这种东西，差一个字就不是一个东西。 
