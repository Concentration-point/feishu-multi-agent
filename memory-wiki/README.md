# Memory Wiki

本目录是 OpenClaw 主助理的结构化知识层，不替代 `MEMORY.md`，只用于把长期记忆整理成可审计的知识库。

## 角色分工

- `MEMORY.md`：人工可审计的长期主记忆。
- `memory/*.md`：每日事件流水。
- `memory-wiki/`：结构化知识层，按实体和主题整理。
- `DREAMS.md`：夜间 Dreaming 候选蒸馏结果，人工检查后再决定是否合并。
- Mem0：自动化补充层，不占独占 memory slot。

## 状态

- 部署模式：local file wiki
- Dashboard：`memory-wiki/DASHBOARD.md`
- 自动写入：默认关闭；由 Dreaming 生成候选，不直接改主记忆。
