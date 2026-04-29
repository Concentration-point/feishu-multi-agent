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

## [ERR-20260429-002] hermes_image_tool_ignored_openai_plugin

**Logged**: 2026-04-29T11:18:00+08:00
**Priority**: high
**Status**: resolved
**Area**: config

### Summary
Hermes `image_generate_tool` still used the legacy FAL path even after `image_gen.provider: openai` was configured.

### Error
```
Unknown FAL model 'gpt-image-2-medium' in config; falling back to fal-ai/flux-2/klein/9b
FAL_KEY environment variable not set
```

### Context
- Direct test of `tools.image_generation_tool.image_generate_tool(...)` showed it ignored the OpenAI/gpt-image-2 plugin and tried FAL.
- Fixed tool dispatch so configured plugin providers are used before the legacy FAL path.
- OpenAI-compatible endpoint also needed a raw minimal `/images/generations` request via `requests`; the official SDK path or Python urllib hit provider-side block/incomplete read in this local setup.
- Verified successful output saved under `C:\Users\25723\.hermes\cache\images\openai_gpt-image-2-medium_20260429_111633_e6bae612.png`.

### Suggested Fix
When a Hermes tool has both legacy implementation and plugin registry, test the direct tool function after config changes. Do not assume config selection is wired into the tool entry point.

### Metadata
- Reproducible: yes
- Related Files: C:\Users\25723\Hermes agent\tools\image_generation_tool.py, C:\Users\25723\Hermes agent\plugins\image_gen\openai\__init__.py
- Tags: hermes, image-generation, plugin-dispatch, gpt-image-2, fal

---

## [ERR-20260429-003] hermes_luhengcheng_chat_sdk_block

**Logged**: 2026-04-29T12:10:00+08:00
**Priority**: high
**Status**: resolved
**Area**: provider-transport

### Summary
Hermes ordinary chat via `custom-api / gpt-5.5` was blocked when using the OpenAI SDK request path, while plain HTTP requests to the same `/chat/completions` endpoint worked.

### Error
```
Your request was blocked.
Timeout value connect was Timeout(...), but it must be an int, float or None.
API call failed after 3 retries. Expecting value: line 1 column 1 (char 0)
```

### Fix
Added a `RequestsOpenAICompatibleClient` for `api.luhengcheng.top` that mimics the small OpenAI Chat Completions response surface Hermes needs, including streaming SSE chunks. `run_agent._create_openai_client()` now uses this requests-backed client for `api.luhengcheng.top`, avoiding the SDK request shape that triggers provider blocking.

### Verification
- Direct sync + async requests-backed calls returned OK.
- Streaming path worked.
- Feishu end-to-end text test `只回复 OK` returned response length 2 with no 401/403/block in logs.
- Regression command passed: `python -m pytest -o addopts= tests/tools/test_image_generation.py tests/tools/test_image_generation_plugin_dispatch.py tests/agent/test_error_classifier.py -q` → 178 passed.

### Metadata
- Reproducible: yes
- Related Files: C:\Users\25723\Hermes agent\agent\auxiliary_client.py, C:\Users\25723\Hermes agent\run_agent.py
- Tags: hermes, luhengcheng, custom-api, openai-compatible, streaming, requests-transport

---

## [ERR-20260429-004] hermes_requests_stream_mojibake

**Logged**: 2026-04-29T12:20:00+08:00
**Priority**: high
**Status**: resolved
**Area**: provider-transport

### Summary
After switching Hermes `api.luhengcheng.top` chat transport to `requests`, streamed replies could become mojibake because SSE lines were decoded using requests' guessed encoding.

### Error
```
Latest Hermes reply was pure garbled text. Direct stream output showed mojibake like `â` for UTF-8 punctuation.
```

### Fix
Changed `_RequestsChatCompletionsAdapter._stream_chunks()` to iterate raw bytes with `decode_unicode=False` and explicitly decode each SSE line as UTF-8 with replacement fallback. This prevents ISO-8859-1 fallback mojibake from `requests` when the provider omits charset.

### Verification
- Fake UTF-8 SSE test with Chinese + em dash passed via assertion.
- Regression command passed: `python -m pytest -o addopts= tests/tools/test_image_generation.py tests/tools/test_image_generation_plugin_dispatch.py tests/agent/test_error_classifier.py -q` → 178 passed.
- Gateway restarted.
- Live endpoint test could not be repeated at this moment because `api.luhengcheng.top` returned Cloudflare 530 tunnel_error / retry_after=120.

### Metadata
- Reproducible: yes
- Related Files: C:\Users\25723\Hermes agent\agent\auxiliary_client.py
- Tags: hermes, mojibake, utf8, requests, sse, streaming

---

## [ERR-20260429-005] hermes_feishu_mojibake_outbound_guard

**Logged**: 2026-04-29T12:35:00+08:00
**Priority**: high
**Status**: resolved
**Area**: feishu-output

### Summary
Hermes sent a reply to Feishu as mojibake (`ææ¯...`) at 12:12. The requests streaming decoder was fixed earlier, but an outbound Feishu guard was added so already-mojibaked provider text is repaired before send.

### Fix
Added `_repair_utf8_mojibake()` in `gateway/platforms/feishu.py` and applied it in `FeishuPlatformAdapter.format_message()`. The repair tries Latin-1 bytes -> UTF-8 only when mojibake marker score clearly decreases, leaving normal text untouched.

### Verification
- Unit-style direct assertion repaired UTF-8-as-Latin-1 sample for `我是 Clawd，你的 Hermes 助理。`.
- Regression command passed earlier in this session: 178 passed.
- Gateway restarted.
- Live text endpoint is currently unavailable due Cloudflare 530 tunnel_error, so end-to-end model reply retest must wait until api.luhengcheng.top recovers.

### Metadata
- Reproducible: yes
- Related Files: C:\Users\25723\Hermes agent\gateway\platforms\feishu.py
- Tags: hermes, feishu, mojibake, utf8, outbound-guard

---
