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
- **Commit/PR**: 5f32c1b
- **Notes**: 已将“禁止悬空进度回复”提升到 AGENTS.md 作为工作规范。

---

## [LRN-20260315-002] best_practice

**Logged**: 2026-03-15T13:00:00+08:00
**Priority**: high
**Status**: promoted
**Area**: docs

### Summary
对于 `cron run` 这类自动投递结果到当前会话的动作，不能再承诺“跑完我会发给你”。

### Details
本次手动触发晨报任务后，系统实际上已将结果投递到当前飞书会话，但我额外回复了“已触发，今天这份晨报现在开始跑。跑完我会把结果发给你。” 这会制造错误预期，好像还需要我人工补发一次，用户看到后自然会觉得我的回复前后矛盾。

### Suggested Action
以后对自动投递型后台任务，统一表述为：已触发，结果会由系统自动发到当前对话；除非明确打算轮询并手动转述，否则不要承诺额外 follow-up。

### Metadata
- Source: conversation
- Related Files: AGENTS.md
- Tags: cron, delivery, reply-flow, expectation-management
- Pattern-Key: cron.auto.delivery.no-extra-promise

### Resolution
- **Resolved**: 2026-03-15T13:00:00+08:00
- **Commit/PR**: pending
- **Notes**: 已补充到 AGENTS.md，明确自动投递型任务的回复规范。

---
## [LRN-20260322-001] correction

**Logged**: 2026-03-22T22:43:00+08:00
**Priority**: high
**Status**: pending
**Area**: docs

### Summary
������/�ձ�/����С��ʱ���ѡ���ʽ�˱���������ݡ���˵�ɡ�����û���˵����������˵�ǰ�Ի�����ȷ�ϵ�δ�����˵���ʵ��

### Details
����Ի�������ȷȷ�������������ѣ����� 11.48 Ԫ��У԰���� 8.50 Ԫ���ܼ� 19.98 Ԫ�����ں��������ռ���С�ᡱ������������֧�� ��0 / ���������˵����������ǿھ��������ѡ���ʽ�˱�Դ������������Ϊ�ա�ֱ��˵�ɡ�����û���˵�������ʧ�˵�ǰ�Ự����ȷ����ʵ��

### Suggested Action
�Ժ��������ڻ���/����С��/�ձ�������������ھ�����ʽд����
1. ��ǰ�Ի���ȷ�ϵ�����
2. ��ʽ�˱�����������
�����߲�һ�£�����˵����ʽ�˱���δ��⣬����ǰ��ȷ�� X �ʣ��ϼ� Y Ԫ����������ֱ��˵��û���˵�����
���⣬���û�Ҫ��̶������ʽʱ���ϸ�ֻ��ָ����ʽ�������׷�ӷ��顢˵�������л���⽨�顣

### Metadata
- Source: user_feedback
- Related Files: MEMORY.md
- Tags: accounting, summary, format-discipline, correction
- Pattern-Key: accounting.summary.must-separate-confirmed-vs-ledger
- Recurrence-Count: 1
- First-Seen: 2026-03-22
- Last-Seen: 2026-03-22

---
## [LRN-20260327-001] correction

**Logged**: 2026-03-27T00:15:44+08:00
**Priority**: high
**Status**: pending
**Area**: docs

### Summary
�û�δ��ȷҪ�󡰼��ˡ�ʱ����Ӧ��֧����ͼֱ���ƽ�Ϊ���ɼ��ˡ����ۡ�

### Details
�� 2026-03-26 �ĶԻ���û�����������֧����Ϣ��ؽ�ͼ����ֱ������ˡ��ɼ��ˡ��Լ�������࣬��Խ�����û����µ���ͼ�߽硣�û������ȷ��ʾ����û���˵����������ˡ�����ȷ����Ӧ�ǣ����û�ֻ��ͼ��δ��ȷ���������/����/���ࡱ���󣬾�ֻ��ʶ����ھ��жϣ����¡��ɼ��ˡ����ۣ����������ƽ������˽��顣

### Suggested Action
�Ժ����˵�/֧����ͼʱ�����ж��û���ͼ��
1. δ��ȷ˵Ҫ���� �� ��ʶ��ͼƬ���ݣ����˵������֧���ɹ�ҳ/����ҳ/�˿�ҳ���ȣ�
2. ��ȷ˵Ҫ���� �� �ٰ����/�̻�/״̬����У�飬��ȫ��Ÿ����ɼ��ˡ����ۣ�
3. ���û�ֻ��˵����������ʲô����ֻ��ͼ �� �����������˽��顣

### Metadata
- Source: user_feedback
- Related Files: MEMORY.md
- Tags: correction, ocr, accounting, intent-boundary

---
## [LRN-20260327-002] best_practice

**Logged**: 2026-03-27T01:58:09+08:00
**Priority**: high
**Status**: pending
**Area**: docs

### Summary
�û��������ͽ�����ͼƬ/��Ϣʱ��Ĭ����Ϊ��ȷ�����ѣ�ֱ�ӽ����������̡�

### Details
�û���ȷǿ�������������Ľ��������ݣ��������Ѿ�ȷ�ϵ����ѡ�������Ӧ�ٴ�׷�ʡ�Ҫ��Ҫ�ǡ���ͣ����ʶ��㣬��Ӧֱ���䵽�˱���������֧���ɹ�ҳ��ҲӦ�Ȱ�������Ŀ���������һ�ʲ��䡣

### Suggested Action
��������ͼƬ/��Ϣ��Ĭ�ϴ�������ͳһΪ��ֱ�������֧���ɹ���Ϊ�Ѽǣ�����ҳ/��֧��/��Ϣ��ȫ��Ϊ���ˡ�

### Metadata
- Source: user_feedback
- Related Files: MEMORY.md
- Tags: correction, accounting, default-intent, ledger

---
## [LRN-20260327-003] correction

**Logged**: 2026-03-27T02:00:14+08:00
**Priority**: high
**Status**: pending
**Area**: docs

### Summary
�û��������͵Ľ��������ݣ�����Ҫ�����ˡ���֧��ͳһ��ȷ������ֱ�Ӽ��ˡ�

### Details
��ǰһ����������ϣ��û���һ�����壺��Ȼ�����������������������ģ��ʹ������Ѿ�ȷ�������ѣ�����Ҫ�ٱ��������ˡ�״̬����ʹ�Ƕ���ҳ�����ʹ�ҳ�ȣ�ֻҪ���������������ڼ��˵Ľ����Ϣ��Ҳ��ȷ������ͳһ���ˡ�

### Suggested Action
���Ը��û��������͵Ľ��ͼ/�����Ϣ��ͳһʹ��ֱ�Ӽ��˿ھ�����ʹ�á����ˡ�״̬��Ҳ��׷��ȷ�ϡ�

### Metadata
- Source: user_feedback
- Related Files: MEMORY.md
- Tags: correction, accounting, direct-booking, no-pending-review

---
## [LRN-20260409-001] correction

**Logged**: 2026-04-09T07:59:00+08:00
**Priority**: high
**Status**: pending
**Area**: docs

### Summary
�û�ָ�������������Ͼ�ʵʱ����������˵��������������ֻ����һԤ��ھ���

### Details
�� 2026-04-09 �糿�����У�����ˡ��Ͼ����Ƶ��硱���������������û����·����Ͼ��������ꡣ���ⲻֻ�Ǵ��ƫ����ǰ�Ԥ��ھ������˵�ǰʵ�����Ժ��ǡ���������/���Ųο����������ݣ��������Ⱥ˶�ʵʱ������������ȷ��Ԥ�����롰ʵ�������������޷�ȷ��ʵʱ������ͱ��Ԥ��д����ǰ��ʵ��

### Suggested Action
��������Ĭ�ϸ�Ϊ��˫У�顱�����Ȳ�ʵʱ����������ٸ��������ƣ���ֻ��Ԥ��Դ����ȷд��Ԥ����ʾ��������ֱ�Ӷ��Ե�ǰ������

### Metadata
- Source: user_feedback
- Related Files: MEMORY.md
- Tags: weather, correction, morning-report, real-time-data

---

## [LRN-20260427-001] best_practice

**Logged**: 2026-04-27T00:32:00+08:00
**Priority**: high
**Status**: pending
**Area**: workflow

### Summary
学习外部文章/案例时，不能照搬其工具链或人设；必须抽象出可复用原则，再按 Clawd 自身定位、现有工具、老大的偏好改造成自己的工作流。

### Details
用户给出 GPT-Image-2 Skill + Hermes 多 Agent 相关文章，并明确要求“学习内化自身能力，要结合自身特点而不是照搬”。核心不是安装或复刻对方 skill，而是吸收：意图翻译、任务拆解、专业 prompt 编译、批量/系列化生成、质量审查、案例库复用、多 agent 协作这些结构性原则。落到 Clawd 自身，应结合现有 OpenClaw 工具、飞书通道、gpt-image-2 生图链路、老大偏好“直接、结果导向、少废话”，形成自己的图像工作流。

### Suggested Action
遇到外部 workflow/skill 文章时固定执行：
1. 提炼原则：解决了什么痛点，关键模块是什么。
2. 过滤边界：不盲装、不照搬、不引入未审计依赖。
3. 本地化改造：映射到当前已有工具和老大偏好。
4. 固化 SOP：写入 AGENTS/TOOLS/相关记忆或生成可执行模板。
5. 下次任务直接调用新 SOP，而不是重新泛泛总结文章。

### Metadata
- Source: user_instruction
- Related Files: AGENTS.md, TOOLS.md
- Tags: image-generation, workflow, self-improvement, adaptation, no-copying
- Pattern-Key: external.workflow.adapt.not.copy

### Resolution
- **Resolved**: pending
- **Commit/PR**: pending
- **Notes**: 需将图像生成工作流沉淀到 AGENTS.md 或专门 SOP。

## [LRN-20260428-001] correction

**Logged**: 2026-04-28T00:35:32+08:00
**Priority**: high
**Status**: promoted
**Area**: workflow

### Summary
老大要求把已学 skill “真正用起来”，不是停留在会背清单和事后评价。

### Details
盘点发现：生图、飞书回复、项目 agent 路由等已经贯彻；但 coding-agent、self-improving-agent、ontology、Agent-Browser、Multi-Search-Engine 等存在“知道但触发不稳定”的问题。后续必须把这些变成条件反射：遇到匹配场景先触发对应工作流，而不是只靠临场想起。

### Suggested Action
在 AGENTS.md 增加 Skill Activation Contract；在 skills-inventory.md 增加日常贯彻矩阵，明确触发条件、必须动作、回报口径和例外。以后复杂 coding 默认转项目/coding agent；失败/纠错必须记 learning；结构化长期关系用 ontology；动态网页/截图用 Agent-Browser；高时效/多源核验用 Multi-Search-Engine。

### Metadata
- Source: user_feedback
- Related Files: AGENTS.md, memory/skills-inventory.md, .learnings/LEARNINGS.md
- Tags: skills, workflow, activation, self-improvement
- Pattern-Key: skills.must-be-operationalized

### Resolution
- **Resolved**: 2026-04-28T00:35:32+08:00
- **Commit/PR**: pending
- **Notes**: 已提升为 AGENTS.md 和 skills-inventory.md 的执行规则。
---

## [LRN-20260428-002] correction

**Logged**: 2026-04-28T01:11:03+08:00
**Priority**: high
**Status**: promoted
**Area**: retrieval

### Summary
网页抓取/摘要链路走不通时，不能等用户提醒“走真实网页”；必须自动切到真实浏览器/页面渲染链路。

### Details
用户指出：我在微信文章抓取失败后，仍需要用户提醒“走真实网页”才切 Agent-Browser。这说明 Retrieval SOP 和 Agent-Browser 的触发还没有形成条件反射。正确行为是：web_fetch/summarize/requests 被拦、验证码、空页面、正文缺失时，主动切到真实浏览器链路，并说明卡点和证据；若浏览器仍卡验证码，再请求用户提供截图/PDF/正文。

### Suggested Action
提升为硬规则：信息检索遇到 blocked/captcha/empty page/JS 渲染/正文缺失，自动按顺序切换：web_fetch → summarize/requests → Agent-Browser 真实页面 → 截图/PDF/用户提供正文；不再反问用户要不要走浏览器。

### Metadata
- Source: user_feedback
- Related Files: AGENTS.md, RETRIEVAL-SOP.md, .learnings/LEARNINGS.md
- Tags: retrieval, browser, agent-browser, fallback, user-correction
- Pattern-Key: retrieval.auto.escalate.real-browser

### Resolution
- **Resolved**: 2026-04-28T01:11:03+08:00
- **Commit/PR**: pending
- **Notes**: 已记录，待提升到检索 SOP / AGENTS。
---

## [LRN-20260428-003] correction

**Logged**: 2026-04-28T01:51:44+08:00
**Priority**: high
**Status**: promoted
**Area**: image-generation

### Summary
当用户已经给出明确生图 prompt 时，不能擅自“重写成我喜欢的 prompt”导致需求漂移；应保留用户原始意图和关键约束，再做结构化增强。

### Details
用户指出：目前有生图 prompt 时，我再次生成的 prompt 并不能满足需求。问题在于我会把用户 prompt 过度翻译、合并、泛化，导致原本的细节、排序、风格词、禁区和判断重点被稀释。高要求生图应以用户 prompt 为源文本，先抽取不可丢失约束，再分层增强，而不是重写。

### Suggested Action
在 IMAGE-GENERATION-SOP 中加入 Prompt Fidelity Protocol：
1. 先保留用户原始 prompt 的核心措辞和所有硬约束。
2. 区分“不可改硬约束 / 可增强软风格 / 需要澄清冲突”。
3. 生成 prompt 时使用“原意保真 + 结构化补强”，不得删掉用户指定字段。
4. 如果用户 prompt 已足够明确，少改，只补模型执行需要的质量、构图、负面限制。
5. 需要再次生成时，应基于上一版失败点定向修，不是完全另写一个 prompt。

### Metadata
- Source: user_feedback
- Related Files: IMAGE-GENERATION-SOP.md, .learnings/LEARNINGS.md
- Tags: image-generation, prompt-fidelity, user-intent, correction
- Pattern-Key: image.prompt.fidelity

### Resolution
- **Resolved**: 2026-04-28T01:51:44+08:00
- **Commit/PR**: pending
- **Notes**: 已记录，待提升到 IMAGE-GENERATION-SOP。
---

## [LRN-20260428-004] best_practice

**Logged**: 2026-04-28T02:11:43+08:00
**Priority**: high
**Status**: promoted
**Area**: image-generation

### Summary
绘图流程必须按 prompt 完整度分档：原 prompt 直出、轻量增强、重构优化。默认目标是命中用户原意，而不是生成“更专业但跑偏”的 prompt。

### Details
用户指出：很多情况下原 prompt 直接生成效果更好；采用流程的本意是效果更好，而不是把 prompt 磨平。现有流程容易把强风格、情绪和明确要求改成模板化高级感。需要将 Raw Prompt Mode / Minimal Compile Mode / Design Rewrite Mode 写入 SOP，并要求生成前判断模式。

### Suggested Action
更新 IMAGE-GENERATION-SOP：
- 原 prompt 完整度 >=80%：Raw Prompt Mode，尽量原文直出，只加模型必要参数/参考图约束。
- 完整度 50%-80%：Minimal Compile Mode，只补少量执行信息，不重排审美。
- 完整度 <50% 或复杂图卡/冲突需求：Design Rewrite Mode，才允许完整 brief 与重构。
- 对强 prompt 可做 A/B：原文直出版 + 轻量增强版。
- 生成前做 prompt mutation lint：检查是否删词、换风格、加结论、改重点。

### Metadata
- Source: user_feedback
- Related Files: IMAGE-GENERATION-SOP.md, .learnings/LEARNINGS.md
- Tags: image-generation, prompt-fidelity, raw-prompt, workflow
- Pattern-Key: image.prompt.mode.routing

### Resolution
- **Resolved**: 2026-04-28T02:11:43+08:00
- **Commit/PR**: pending
- **Notes**: 已提升到 IMAGE-GENERATION-SOP 并添加 smoke test。
---

## [LRN-20260429-001] correction

**Logged**: 2026-04-29T11:01:00+08:00
**Priority**: high
**Status**: pending
**Area**: config

### Summary
Hermes image generation must use the image_gen backend (`gpt-image-2`), not the chat fallback model.

### Details
User corrected that image generation should call `gpt-image-2`; adding `gpt-4o-mini` as fallback only helps the main conversation/tool orchestration model and does not define the image generation model. Hermes image-generation selection reads `image_gen.provider` / `image_gen.model` from config and the OpenAI plugin maps `gpt-image-2-low|medium|high` to API model `gpt-image-2`.

### Suggested Action
When fixing Hermes image failures, separate three layers explicitly: chat/orchestration model, image_gen provider/model, and platform media upload. Configure image_gen separately, e.g. `image_gen.provider: openai`, `image_gen.model: gpt-image-2-medium`.

### Metadata
- Source: user_feedback
- Related Files: C:\Users\25723\.hermes\config.yaml, C:\Users\25723\Hermes agent\plugins\image_gen\openai\__init__.py, C:\Users\25723\Hermes agent\agent\image_gen_registry.py
- Tags: hermes, image-generation, gpt-image-2, config

---

## [LRN-20260429-002] best_practice

**Logged**: 2026-04-29T11:25:00+08:00
**Priority**: high
**Status**: resolved
**Area**: config

### Summary
For Hermes/Feishu image generation, copy OpenClaw's successful chain by bypassing the chat model for direct image requests.

### Details
User pointed out that OpenClaw succeeded because the image request was routed directly to the image tool/model (`gpt-image-2`) instead of asking the chat model to reason first. Hermes was failing before tool invocation: primary chat model got HTTP 403 and the misconfigured OpenAI fallback got HTTP 401. The fix was to remove the bad chat fallback and add a direct image-generation route in `gateway/run.py` for clear image requests, returning `MEDIA:"<local-cache-path>"` after `image_generate_tool` succeeds.

### Suggested Action
When image generation is a first-class intent, don't make the chat LLM a mandatory hop. Route deterministic media intents directly to the image backend when safe, and reserve chat models for ambiguous/meta requests.

### Metadata
- Source: user_feedback
- Related Files: C:\Users\25723\Hermes agent\gateway\run.py, C:\Users\25723\.hermes\config.yaml
- Tags: hermes, image-generation, direct-routing, feishu, gpt-image-2

---

---

## [LRN-20260429-003] correction

**Logged**: 2026-04-29T16:34:00+08:00
**Priority**: high
**Status**: pending
**Area**: ppt-workflow

### Summary
DeckForge/PPT ??????????????? PPT???????????????????????/?????

### Details
??????????? PPT ???????
1. ???????????
2. ???????????????????????????????? PPT ???????

### Suggested Action
?? PPT ???????
- ??????????????? + ??? + ?? 2 ?????/??/?????????????
- ???????????????PPT ???????SVG/PNG ??????????????????????????????? PPT ????
- ??????/??????? Style Bible????????????????????
- ???????????????????????????

### Metadata
- Source: user_feedback
- Related Files: AGENTS.md, build_deckforge_ppt.py
- Tags: ppt, deckforge, formula-rendering, layout-density, visual-consistency
- Pattern-Key: ppt.density.formula.rendering

