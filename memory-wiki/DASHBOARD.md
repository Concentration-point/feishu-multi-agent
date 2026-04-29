# Memory Dashboard

更新时间：2026-04-29 19:25 Asia/Shanghai

## Components

| Component | Role | Status | Notes |
|---|---|---|---|
| MEMORY.md | 主长期记忆 | active | 人工可审计，最终权威层 |
| memory/*.md | 日志/短期流水 | active | 每日上下文 |
| memory-wiki | 结构化知识层 | active-local | 本地文件 wiki，非插件包 |
| Dreaming | 夜间候选蒸馏 | pending | 输出到 DREAMS.md，不直接合并 |
| Mem0 | 自动捕获/召回补充层 | pending | 不设置 plugins.slots.memory |
| QMD | 精准搜索后端 | blocked | Windows 原生安装失败，建议 WSL2 |
| Active Memory | 回复前召回 | degraded | 配置已开，memory-core CLI chunks=0 |

## Wiki Index

- `entities/people.md`
- `entities/projects.md`
- `entities/tools.md`
- `topics/ppt-workflow.md`
- `topics/memory-architecture.md`
- `tasks/open-items.md`

## Review Rules

1. 自动捕获的信息不能直接覆盖 `MEMORY.md`。
2. Dreaming 只写候选到 `DREAMS.md`。
3. 重要晋升需人工 review 或至少被主助理明确确认。
4. Mem0 只作为补充层，不独占 memory slot。
