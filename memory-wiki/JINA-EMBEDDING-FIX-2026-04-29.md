# Jina Embedding Fix

Time: 2026-04-29 21:50 Asia/Shanghai

## Change

Configured OpenClaw memory search embedding to use Jina OpenAI-compatible endpoint.

Actual config path used:

```text
agents.defaults.memorySearch.provider = openai
agents.defaults.memorySearch.model = jina-embeddings-v3
agents.defaults.memorySearch.remote.baseUrl = https://api.jina.ai/v1
agents.defaults.memorySearch.remote.apiKey = <redacted>
agents.defaults.memorySearch.store.vector.enabled = true
```

## Verification

Direct smoke test:

```text
POST https://api.jina.ai/v1/embeddings
status: 200
model: jina-embeddings-v3
dim: 1024
```

OpenClaw memory status after explicit main reindex:

```text
Memory Search (main)
Indexed: 23/23 files · 59 chunks
Vector: ready
Vector dims: 1024
FTS: ready
Embedding cache: 59 entries
```

Search test:

```text
openclaw memory search --query "老大 偏好 PPT 生图 记忆系统" --max-results 5 --json
```

Returned results from `MEMORY.md`, `memory/skills-inventory.md`, and `memory/2026-04-28.md`.

## Notes

Initial reindex failed while Gateway held `main.sqlite` lock. Running explicit `openclaw memory index --agent main --force --verbose` succeeded afterward.

## Remaining Warnings

- `plugins.entries.feishu`: disabled config remains.
- `plugins.entries.openclaw-mem0`: disabled config remains by design to keep Mem0 non-exclusive.
- `feishu-project` warns that `workspace-feishu-project/memory` directory is missing, but its single `MEMORY.md` indexed successfully.
