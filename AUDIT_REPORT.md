# 项目审计报告

> 生成时间: 2026-04-16
> 对照基准: `claude.md` + `TODO.md` + `todo.json`
> 审计方式: 按模块核对实现，辅以一次 `python -m pytest tests -q --tb=short` 实测

## 总览

- 已核对模块: `config / feishu / memory / tools / agents / sync / orchestrator / main / tests / knowledge / TODO`
- 结论: 当前仓库的主体功能大多已落地，阶段七的主链路代码也已存在；主要问题不在“文件缺失”，而在安全边界、Wiki 同步语义、测试体系失真，以及文档/TODO 状态不同步
- 实测结果: `python -m pytest tests -q --tb=short` 返回 `25 failed, 4 passed, 8 errors`

## 偏差清单（必须修复）

### ❌ D-01: `read_knowledge` 存在目录穿越，可读取 `knowledge/` 之外的任意文件
- CLAUDE.md 要求: `read_knowledge` 只能读取 `knowledge/{filepath}` 下的知识文档
- 实际情况: [tools/read_knowledge.py](/D:/feishus/tools/read_knowledge.py:31) 直接拼接 `Path(KNOWLEDGE_BASE_PATH) / filepath`，随后就执行 `exists()`、`is_file()` 和 `read_text()`，没有做 `resolve()` 和“必须留在知识库根目录内”的校验
- 影响: Agent 或错误调用可借由 `../` 读取 `.env`、配置文件或仓库内任意文本文件，突破知识工具的访问边界
- 修复建议: 对目标路径执行 `resolve()`，并校验其父路径必须位于 `KNOWLEDGE_BASE_PATH` 之下；拒绝绝对路径和带 `..` 的相对路径

### ❌ D-02: `write_wiki` 同样缺少路径约束，可越权写出 `knowledge/wiki/`
- CLAUDE.md 要求: `write_wiki` 仅写入 `knowledge/wiki/{category}/{title}.md`
- 实际情况: [tools/write_wiki.py](/D:/feishus/tools/write_wiki.py:94) 和 [tools/write_wiki.py](/D:/feishus/tools/write_wiki.py:107) 直接将 `category`、`title` 拼进目录和文件名；未做合法字符过滤，也未校验最终路径仍位于 `knowledge/wiki/` 内
- 影响: 恶意或异常输入可借由 `../` 覆盖知识库外部文件；`.sync_state.json` 也会被写入错误的相对路径，污染同步状态
- 修复建议: 复用 `memory/experience.py` 的 `_sanitize_name()` 思路，或对最终路径 `resolve()` 后做目录边界校验

### ❌ D-03: Wiki“更新”实际是追加 block，重复同步会不断堆叠内容
- CLAUDE.md 要求: `sync/wiki_sync.py` 对脏文件执行“创建或更新文档”
- 实际情况: [feishu/wiki.py](/D:/feishus/feishu/wiki.py:120) 的 `update_doc_content()` 先查根 block，然后用 [feishu/wiki.py](/D:/feishus/feishu/wiki.py:159) 的 children 创建接口继续插入内容；[sync/wiki_sync.py](/D:/feishus/sync/wiki_sync.py:149) 和 [sync/wiki_sync.py](/D:/feishus/sync/wiki_sync.py:157) 在每次同步时都会调用这个方法
- 影响: 同一文档每次重新同步都会把全文再插入一遍，飞书知识空间内容会越来越长，并且与本地文件不再一致
- 修复建议: 更新前先清空旧内容，或改成真正的“覆盖式”更新流程；否则当前同步语义不满足“镜像”

### ❌ D-04: 测试体系与“阶段已完成”的说法不一致，当前不能按 `pytest` 正常执行
- CLAUDE.md / TODO 预期: 多个阶段测试已完成，阶段七 `tests/test_webhook.py` 已补齐
- 实测情况: `python -m pytest tests -q --tb=short` 返回 `25 failed, 4 passed, 8 errors`
- 直接原因:
  - [requirements.txt](/D:/feishus/requirements.txt:1) 只列了运行依赖，没有 `pytest`、`pytest-asyncio` 等测试依赖
  - [tests/test_agent.py](/D:/feishus/tests/test_agent.py:62) 和 [tests/test_bitable.py](/D:/feishus/tests/test_bitable.py:67) 把脚本式 `async def test_*` 暴露给 pytest，导致收集后直接报 “async def functions are not natively supported”
  - [tests/test_bitable.py](/D:/feishus/tests/test_bitable.py:186) 把 `record_id` 写成 pytest fixture 形态，但仓库没有对应 fixture
  - [tests/test_framework.py](/D:/feishus/tests/test_framework.py:84) 起的一组测试把 `report` 当 fixture 使用，同样不存在
- 影响: TODO 中“测试已完成”的标注无法支撑，CI 或本地回归都不可靠
- 修复建议: 明确二选一
  - 要么把这些文件保留为“脚本式验收工具”，统一改名避免 pytest 收集
  - 要么补齐 pytest 依赖和 fixture，并把测试改造成真正可收集、可断言的 pytest 用例

### ❌ D-05: `tests/test_framework.py` 仍把真实工具当 stub 校验，测试语义已过时
- TODO / 实际代码预期: `search_knowledge`、`send_message`、`get_experience` 均已是真实实现
- 实际情况: [tests/test_framework.py](/D:/feishus/tests/test_framework.py:329) 的 `test_stub_tools()` 仍要求返回值中出现 `stub`、“阶段五”或“阶段六”
- 影响: 即使把 pytest 依赖补齐，这组测试仍会因为验收标准过时而失败
- 修复建议: 删除这组 stub 断言，改成真实行为校验

### ❌ D-06: 经验池字段设计与实现不一致，缺少“创建时间”映射与写入
- CLAUDE.md 要求: 经验池表包含 `适用角色 / 场景分类 / 经验内容 / 置信度 / 使用次数 / 来源项目 / 创建时间`
- 实际情况:
  - [config.py](/D:/feishus/config.py:75) 的 `FIELD_MAP_EXPERIENCE` 缺少 `创建时间`
  - [memory/experience.py](/D:/feishus/memory/experience.py:113) 写入经验时也没有写 `创建时间`
- 影响: 表结构与设计稿不一致；后续无法按沉淀时间审计、排序或回溯经验来源
- 修复建议: 在 `FIELD_MAP_EXPERIENCE` 中补 `created_time`，并在 `save_experience()` 中写入对应时间字段

## 缺失清单（功能缺失）

- 本轮未发现新的“大块功能缺失”。当前问题主要是“功能已写出，但语义、安全性或可验证性不达标”。

## 一致性问题

### 节点路径与设计不一致
- CLAUDE.md 设计: `knowledge/wiki/电商大促/策略模板.md` 应映射到飞书知识空间“电商大促”节点下的“策略模板”文档
- 实际情况: [sync/wiki_sync.py](/D:/feishus/sync/wiki_sync.py:171) 会把 `wiki/<category>/...` 映射成父节点 `Wiki-<category>`
- 影响: 飞书知识空间层级与本地知识库结构不再一一对应，和设计稿不一致

### Wiki 客户端方法名与审计基准不一致
- 审计基准检查项期望 `create_node / update_doc / list_nodes`
- 实际情况: [feishu/wiki.py](/D:/feishus/feishu/wiki.py:120) 提供的是 `update_doc_content()`，不是 `update_doc()`
- 影响: 虽不阻塞当前调用，但接口名称与设计稿不一致，增加了后续维护成本

### 项目主表“创建时间”仍未接入
- CLAUDE.md 主表设计包含 `创建时间`
- 实际情况: [config.py](/D:/feishus/config.py:42) 的 `FIELD_MAP_PROJECT` 未包含该字段，`ProjectMemory` 也未暴露
- 影响: account_manager 的 soul 中要求优先读取“创建时间”，但当前工具链并不支持这件事

## TODO 状态校准

### 需要更新的状态

| 任务 ID | 当前标注 | 实际状态 | 说明 |
|---------|----------|---------|------|
| P2-T22 | `completed` | `需要返工` | 当前测试文件并不能被 pytest 正常执行，且框架测试仍保留 stub 断言 |
| P5-T03 | `completed` | `需要返工` | IM 测试文件同样属于 async 脚本式写法，未形成可运行的 pytest 保障 |
| P6-T03 | `completed` | `需要返工` | 经验池测试同样受 pytest/fixture 问题影响 |
| P7-T09 | `completed` | `部分完成` | `tests/test_webhook.py` 文件存在，但 `todo.json` 备注自己也写了“当前环境缺 pytest，未实际执行” |
| P7-T10 | `pending` | `已完成` | [todo.json](/D:/feishus/todo.json:110) 仍标 pending，但 [claude.md](/D:/feishus/claude.md:379) 已把阶段七标成“当前阶段”，并列出对应已完成项 |

### 需要保留的状态

| 任务 ID | 当前标注 | 结论 |
|---------|----------|------|
| P7-T01 | `completed` | `main.py` 已具备 `serve`、`/webhook/event`、challenge 处理和异步触发主流程 |
| P7-T02 | `completed` | `requirements.txt` 已补 `fastapi` 与 `uvicorn[standard]` |
| P7-T03 | `completed` | `memory/working.py` 已从 stub 演进为轻量工作记忆工具 |
| P7-T04 | `completed` | `.env.example` 已补 webhook 配置说明 |
| P7-T05 | `completed` | `demo/run_demo.py` 已存在 |
| P7-T06 | `completed` | `demo/briefs/` 三份预设数据已存在 |
| P7-T08 | `completed` | `README.md` 已存在并覆盖基础说明 |

## 验证记录

### 命令

```powershell
python -m pytest tests -q --tb=short
```

### 结果摘要

- `25 failed, 4 passed, 8 errors`
- 主要失败类型:
  - 缺少 async 测试插件
  - fixture 不存在
  - 脚本式测试被 pytest 错误收集
  - 过时的 stub 断言

## 建议改进

### 💡 S-01: 把 webhook 幂等键从 `record_id` 提升为 `event_id`
- [main.py](/D:/feishus/main.py:161) 当前只基于内存里的 `_processed_record_ids` 去重
- 更稳妥的做法是优先使用飞书事件头中的 `event_id`，并加 TTL 或持久化去重

### 💡 S-02: 把 FastAPI `on_event` 换成 lifespan
- 本次 pytest 输出已经出现 `DeprecationWarning`
- [main.py](/D:/feishus/main.py:96) 和 [main.py](/D:/feishus/main.py:101) 后续建议改为 lifespan handler

### 💡 S-03: 为知识工具补统一的路径安全辅助函数
- `read_knowledge`、`write_wiki`、`ExperienceManager.save_to_wiki()` 当前各自处理路径
- 建议抽一个统一的 `safe_resolve_under(base, *parts)`，避免后续再出类似问题

## 下一步行动

1. 先修复知识工具的路径边界和 Wiki 同步“覆盖式更新”问题。这两项是实质 bug，不是文档问题。
2. 重新定义测试策略：要么全部转成可收集的 pytest 用例，要么显式保留为脚本并从 pytest 收集中排除。
3. 校准 `todo.json`：至少更新 `P2-T22 / P5-T03 / P6-T03 / P7-T09 / P7-T10`。
