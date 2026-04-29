# ERRORS

记录命令失败、外部工具异常、环境问题。

---

## [ERR-20260425-001] git-commit-missing-user-identity

**Logged**: 2026-04-25T16:15:00+08:00
**Priority**: low
**Status**: resolved
**Area**: config

### Summary
New isolated OpenClaw agent workspaces may initialize as Git repos without local user.name/user.email, causing the first commit to fail.

### Error
```text
Author identity unknown
fatal: unable to auto-detect email address
```

### Context
- Operation: committing initial files for `workspace-feishu-project`
- Fix applied: set local repo identity only:
  - `git config user.name "Clawd"`
  - `git config user.email "clawd@local.openclaw"`

### Suggested Fix
For future new agent workspaces, set local Git identity before the first commit instead of changing global Git identity.

### Metadata
- Reproducible: yes
- Related Files: C:\Users\25723\.openclaw\workspace-feishu-project\.git\config
---

## [ERR-20260426-001] openclaw_config_edit_probe_script

**Logged**: 2026-04-26T18:12:00+08:00
**Priority**: medium
**Status**: pending
**Area**: config

### Summary
While diagnosing OpenClaw API image generation, the first Node probe script parsed its own script path instead of the config path because it used `process.argv[1]` instead of `process.argv[2]`.

### Error
```text
SyntaxError: Unexpected token 'const'
```

### Context
- Command attempted: temporary Node script to parse `~/.openclaw/openclaw.json` and probe `/v1/images/generations`.
- Cause: in Node, `process.argv[1]` is the script file; the first user argument is `process.argv[2]`.

### Suggested Fix
For temporary Node scripts launched as `node script.js arg`, always read the first external argument from `process.argv[2]`.

### Metadata
- Reproducible: yes
- Related Files: C:\Users\25723\.openclaw\openclaw.json

---

## [ERR-20260426-002] openclaw_image_config_provider_models

**Logged**: 2026-04-26T18:12:00+08:00
**Priority**: high
**Status**: resolved
**Area**: config

### Summary
Adding `models.providers.openai` without a `models` array made OpenClaw config invalid; then using `api: openai-chat` was also invalid for this OpenClaw schema.

### Error
```text
models.providers.openai.models: Invalid input: expected array, received undefined
models.providers.openai.models.0.api: Invalid option: expected one of "openai-completions"|"openai-responses"|...
```

### Context
- Goal: route image generation to the local OpenAI-compatible `/v1/images/generations` endpoint.
- Fix applied: add `models.providers.openai.models` with `api: 'openai-responses'`, then set `agents.defaults.imageGenerationModel.primary = 'openai/gpt-image-2'`.

### Suggested Fix
When adding an OpenClaw model provider manually, include a valid `models` array and use schema-supported `api` values only.

### Metadata
- Reproducible: yes
- Related Files: C:\Users\25723\.openclaw\openclaw.json

---

## [ERR-20260426-003] openclaw_image_provider_aspectratio_cached_module

**Logged**: 2026-04-26T18:36:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: config

### Summary
After patching OpenClaw's OpenAI image-generation provider chunk to support `aspectRatio`, the current agent session's `image_generate` tool still returned the old error because the provider module was already cached in the running tool process.

### Error
```text
openai generate does not support aspectRatio overrides.
```

### Context
- Patched file: `C:\Users\25723\AppData\Roaming\npm\node_modules\openclaw\dist\image-generation-provider-fiOkT1Zi.js`
- Added aspect-ratio-to-size mapping for OpenAI-compatible image generation.
- External fresh Node import verified `supportsAspectRatio: true` and successfully generated an image with `aspectRatio: '16:9'`.

### Suggested Fix
After patching runtime chunks, restart Gateway and validate from a fresh process/import. Do not trust the current already-loaded tool module as the final verdict.

### Metadata
- Reproducible: yes
- Related Files: C:\Users\25723\AppData\Roaming\npm\node_modules\openclaw\dist\image-generation-provider-fiOkT1Zi.js

---

## [ERR-20260429-001] hermes_image_generation_delivery_403

**Logged**: 2026-04-29T10:57:00+08:00
**Priority**: high
**Status**: pending
**Area**: config

### Summary
Initial Hermes image-generation fix targeted only remote generated-image caching, but user reported the same error again.

### Error
```
Hermes still returned the same visible error after restart. Latest logs showed the failing request was a main-model provider block (`Your request was blocked`, HTTP 403-ish), not only Feishu fetching a generated image URL.
```

### Context
- User asked to fix Hermes image generation delivery after a 403 screenshot.
- First fix cached provider image URLs locally before Feishu upload and passed image-generation tests.
- Follow-up showed the actual remaining failure path was the primary `custom-api` model (`gpt-5.5` via `https://api.luhengcheng.top/v1`) being blocked before the tool/follow-up completed.
- Hermes config had no fallback providers despite `OPENAI_API_KEY` being available.
- Added `openai-direct` custom provider and configured it as fallback (`gpt-4o-mini`) so provider-side request blocks can fail over.

### Suggested Fix
For Hermes image/tool delivery errors, verify whether the error happens in: (1) image provider URL fetch, (2) platform media upload, or (3) main LLM follow-up. Do not assume all 403s are media-download 403s.

### Metadata
- Reproducible: yes
- Related Files: C:\Users\25723\.hermes\config.yaml, C:\Users\25723\Hermes agent\tools\image_generation_tool.py, C:\Users\25723\Hermes agent\run_agent.py
- Tags: hermes, image-generation, feishu, fallback-provider, 403

---
