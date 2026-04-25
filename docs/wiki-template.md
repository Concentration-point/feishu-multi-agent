# Wiki 内容模板（P4 收口版）

统一结构：

```md
---
created: 2026-04-17
source: Agent 自动蒸馏
category: 电商大促
role: copywriter
confidence: 0.84
---

# 标题

## 元信息
- 分类：电商大促
- 角色：copywriter
- 置信度：0.84

## 正文
这里放正文内容。
```

## 约束
- Frontmatter 只保留扁平字段，避免复杂嵌套
- 正文从 `## 正文` 开始，避免 docx 写入时解析歧义
- 不使用 HTML 注释、复杂表格、嵌套代码块作为主内容
- 空行最多连续 2 个

## 经验卡片正文推荐结构

```md
## 场景
...

## 策略
...

## 结果
...

## 经验教训
...
```

## 质量门槛
- category 不能为空
- situation >= 8 字
- action >= 8 字
- outcome >= 4 字
- lesson >= 12 字

## 去重策略
- 第一层：role + category + lesson 指纹精确去重
- 第二层：同 role + category 数量超阈值后，走 LLM merge_experiences 合并
- 第三层：confidence 低于阈值不入库
