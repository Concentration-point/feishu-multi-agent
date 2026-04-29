# Memory Architecture Deployment Status

Time: 2026-04-29 20:50 Asia/Shanghai

## Step 1: Active Memory

Status: degraded / safe fallback

- `active-memory` plugin name: not found in current OpenClaw installation.
- Current memory slot: `memory-core`.
- `memory-lancedb`: available but disabled.
- Reason: `memory-lancedb` requires embedding API; current `http://127.0.0.1:8317/v1/embeddings` returns 404.
- `openclaw memory status` shows:
  - main: `0/23 files · 0 chunks`
  - Vector: disabled
  - FTS: ready

## Step 2: Active Memory Recall Test

Status: not fully testable through CLI index

- Current `memory_search` tool can still be called in-agent.
- CLI index remains empty (`0 chunks`), so active indexed recall is not healthy.

## Step 3: memory-wiki

Status: active-local

Migrated pages:

- `entities/people.md`
- `entities/projects.md`
- `entities/tools.md`
- `topics/memory-architecture.md`
- `topics/ppt-workflow.md`
- `tasks/open-items.md`
- `MIGRATION-REPORT.md`

Rules added to `AGENTS.md`:

- Prefer `memory-wiki/` for structured long-term facts, preferences, decisions, project relations, tool states, and todos.
- No dedicated wiki tools exist; use `read` / `write` / `edit` as local wiki operations.
- Keep evidence/source chains.
- Dreaming only writes to `DREAMS.md`; no automatic merge into `MEMORY.md`.
- Mem0 must remain non-exclusive; do not set `plugins.slots.memory = "openclaw-mem0"`.

## Step 4: Validation

Gateway: ok

Memory status summary:

```text
Memory Search (main)
Provider: openai
Sources: memory
Indexed: 0/23 files · 0 chunks
Vector: disabled
FTS: ready
```

Plugin status summary:

```text
memory-core: loaded
memory-lancedb: disabled
openclaw-mem0: disabled
```

Dreaming cron:

```text
jobId: 70332101-bf1e-4a64-bd60-cff10194a3c1
schedule: 0 3 * * * Asia/Shanghai
mode: candidate / review-only
output: DREAMS.md
```

## Warnings

- QMD blocked on Windows native install.
- Active memory index remains empty.
- Mem0 official plugin wants exclusive memory slot; kept disabled to satisfy hard boundary.
- Config warnings remain for disabled `feishu` and disabled `openclaw-mem0` entries.
