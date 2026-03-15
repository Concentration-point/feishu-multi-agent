# LEARNINGS

记录已确认的学习、纠错、最佳实践。

---

## [LRN-20260315-001] correction

**Logged**: 2026-03-15T12:50:00+08:00
**Priority**: high
**Status**: promoted
**Area**: docs

### Summary
当用户要求“现在跑一遍给我看”时，不能只发送口头确认消息而没有后续结果。

### Details
本次在飞书私聊中，先回复了“我现在手动跑今天这份晨报，用新规则出一版给你看。”，但没有在后续同一流程内继续给出结果，形成悬空回复，用户明确指出这是个问题。对聊天产品来说，这种体验比直接报错更差，因为看起来像失联或遗忘。

### Suggested Action
默认规则改为：此类请求优先直接执行并返回结果；只有在明确进入后台执行时，才允许先发进度消息，并且完成后必须主动补发。若工具失败或中断，必须显式告知失败点和下一步。

### Metadata
- Source: user_feedback
- Related Files: AGENTS.md
- Tags: feishu, reply-flow, progress-update, reliability
- Pattern-Key: no.dangling.progress.replies

### Resolution
- **Resolved**: 2026-03-15T12:50:00+08:00
- **Commit/PR**: pending
- **Notes**: 已将“禁止悬空进度回复”提升到 AGENTS.md 作为工作规范。

---
