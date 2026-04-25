---
type: reference_index
purpose: 文案 Agent 的爆款对标参考库
---

# 爆款对标参考库

本目录收录各平台的真实风格爆款内容，供文案 Agent 在撰写前通过 `search_reference` 检索对标。

## 目录结构

```
references/
├── 小红书/       # 种草笔记、测评、教程
├── 抖音/         # 口播脚本、剧情脚本
└── 公众号/       # 长文、深度稿
```

## 每篇参考的 frontmatter 规范

```yaml
platform: 小红书 | 抖音 | 公众号
category: 电商大促 | 新品发布 | 品牌传播 | 日常运营
tags: [精华液, 美妆, 成分党]
engagement: 1.2w赞 / 3.5w播放 / 8k阅读
hook: 开头抓手方式（问题/故事/数据/反差）
structure: 内容结构骨架（如：问题 → 个人故事 → 成分解析 → 对比 → CTA）
cta: 结尾引导动作的方式
---

正文...
```

## Agent 如何使用

1. `search_reference(query="小红书 精华液 种草", platform="小红书")` → 搜出 3-5 篇
2. 分析共性：hook 类型、structure、cta 方式
3. 基于共性创作，明确"参考了哪些爆款的哪些元素"

## 维护建议

- 每个品类 + 平台组合至少保留 2-3 篇
- 避免放违规/过时内容
- 定期从真实爆款中补充更新
