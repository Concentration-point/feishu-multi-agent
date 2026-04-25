# BaseAgent Contract Integration 设计稿

> 目标：让 `BaseAgent` 不只会输出自然语言，还能稳定产出结构化 contract，并让 orchestrator 基于 contract 推动流程。

---

# 一、当前问题

当前 `BaseAgent.run()` 的能力是：
- 加载 soul.md
- 装配 prompt
- 注册工具
- 跑 ReAct 循环
- 返回一段自然语言结果

这对 Demo 展示够用，但对多 Agent 协作不够硬。

## 核心问题
1. **最终产物偏自然语言**
   - 下游流程不好消费
   - orchestrator 难以做严格判断

2. **没有正式交接单**
   - 上游 agent 做完后，下游还得自己去猜哪些结果是关键

3. **状态推进缺少硬门槛**
   - 现在更像“看上去做完了”
   - 不是“结构化结果满足条件，才允许推进”

所以需要给 `BaseAgent` 增加 contract 能力。

---

# 二、设计目标

## 1. BaseAgent 同时支持两类输出
- **自然语言输出**：给人看
- **contract 输出**：给系统看

## 2. contract 是第一公民
- orchestrator 优先看 contract
- 状态机优先看 contract
- workflow guard 优先看 contract

## 3. 尽量不推翻当前结构
不重写整个 agent 引擎，只做可控增量：
- 保留现有 `run()`
- 新增 `run_contract()`
- 再增加一个组合方法 `run_full()`

---

# 三、推荐接口设计

## 方案一：最稳妥版本

### 1. `run()`
继续保留现状：
```python
async def run(self) -> str:
    ...
```
返回自然语言结果。

### 2. `run_contract()`
新增：
```python
async def run_contract(self) -> dict:
    ...
```
职责：
- 基于当前角色 prompt + 工具结果
- 强制 LLM 输出 JSON contract
- 本地校验 JSON 是否符合 contract 结构
- 校验失败可重试 1~2 次
- 最终返回 `dict`

### 3. `run_full()`
新增：
```python
async def run_full(self) -> dict:
    return {
        "text": "...",
        "contract": {...}
    }
```
职责：
- 一次完整执行同时拿到：
  - 展示文本
  - 结构化 contract

## 为什么推荐这个方案
因为它改动最小，最适合你当前阶段。

---

# 四、推荐的执行顺序

## Step 1：先让 Agent 完成工具调用和业务动作
也就是当前的 ReAct 循环照旧。

## Step 2：结束后增加一轮“contract 生成调用”
不是让主循环直接输出 contract，
而是在业务动作完成后，再额外补一轮：

```text
你已经完成本角色工作。
现在请不要继续调用工具。
请基于本轮执行结果，严格输出 JSON contract。
必须符合 agents/contracts/{role_id}.contract.json 的结构。
不得输出 Markdown，不得解释，只输出 JSON。
```

这一步最稳。因为：
- 主循环专注“做事”
- 最后一轮专注“交接”

不要一开始就把“做事 + 输出 contract”混在一起，很容易两头都乱。

---

# 五、contract 生成方式建议

## 推荐方式：模板驱动 + JSON 校验

### 输入给 LLM 的额外上下文
- `base_contract.json`
- 当前角色的 `*.contract.json` 示例
- 当前 agent 本轮最终自然语言总结
- 当前工具调用结果摘要（如需要）

### 输出要求
必须：
- 只输出 JSON
- 顶层字段完整
- `role_id` 与当前角色一致
- `handoff.next_role` 与流程定义一致

### 本地校验
BaseAgent 侧至少做这些校验：
- JSON 解析成功
- `role_id == self.role_id`
- `record_id == self.record_id`
- `status in {success, partial, failed}`
- `output` 存在
- `handoff.ready` 为 bool
- `handoff.blocking_issues` 为 list

如果失败：
- 第一次：让 LLM 重试修正
- 第二次还失败：返回系统级失败 contract

---

# 六、推荐的数据结构

## BaseAgentResult
建议引入 dataclass：

```python
@dataclass
class BaseAgentResult:
    role_id: str
    record_id: str
    text: str
    contract: dict
```
```

这样 orchestrator 不用再分别拼。

---

# 七、orchestrator 怎么改

当前 orchestrator 大概率是：
- 顺序跑各角色
- 看文本结果/状态字段
- 决定下一步

## 推荐改法
改成：
- `result = await agent.run_full()`
- `contract = result["contract"]`
- 只看 `contract` 推流程

### 示例
```python
result = await strategist.run_full()
contract = result["contract"]

if not contract["handoff"]["ready"]:
    raise WorkflowBlocked(contract["handoff"]["blocking_issues"])

next_role = contract["handoff"]["next_role"]
```

这样你的流程推进就不是“我觉得差不多”，而是“contract 明确允许”。

---

# 八、状态机怎么接 contract

## 原则
状态更新不要只依赖 agent 自己想改什么，
而应该由 orchestrator / workflow guard 根据 contract 判断。

### 例子
#### account_manager 完成后
只有当 contract 中至少包含：
- `brief_summary`
- `campaign_goal`
- `target_audience`
- `constraints`

才允许项目状态从：
- `待处理` → `解读中完成 / 进入策略中`

#### reviewer 完成后
只有当 contract 中：
- `total_items > 0`
- `pass_rate` 已给出

才允许：
- `审核中` → `排期中`
- 或回退 `撰写中`

---

# 九、推荐先落地的最小版本

## Phase 1：只接 1 个角色
先给 `account_manager` 接 `run_contract()`。

原因：
- 上游角色最适合做 contract 试点
- 一旦成功，strategist 就能马上吃结构化输入

## Phase 2：接 `strategist`
让内容矩阵真正结构化。

## Phase 3：接 `reviewer`
让 pass_rate / blocking_issues 成为真正 gate。

这三个接完，系统质量会明显上一个台阶。

---

# 十、建议新增文件

推荐在仓库继续新增：

```text
agents/contracts/loader.py
agents/contracts/validator.py
```

## `loader.py`
职责：
- 读取 `base_contract.json`
- 读取角色 contract 示例
- 给 BaseAgent contract 生成阶段提供模板上下文

## `validator.py`
职责：
- 校验 contract JSON 基本结构
- 校验 role_id / record_id / handoff 字段
- 返回错误信息供重试使用

这样 BaseAgent 本体不会太肥。

---

# 十一、推荐伪代码

```python
class BaseAgent:
    async def run(self) -> str:
        text = await self._run_react_loop()
        return text

    async def run_contract(self, final_text: str | None = None) -> dict:
        if final_text is None:
            final_text = await self.run()

        contract_prompt = self._build_contract_prompt(final_text)
        raw = await self._llm_no_tools(contract_prompt)
        contract = json.loads(raw)
        validate_contract(contract, role_id=self.role_id, record_id=self.record_id)
        return contract

    async def run_full(self) -> dict:
        text = await self.run()
        contract = await self.run_contract(final_text=text)
        return {
            "text": text,
            "contract": contract,
        }
```

---

# 十二、最终建议

一句话：

> **先别急着让整个系统都懂 contract，先让 BaseAgent 学会交接单。**

你现在这项目最好的做法不是大改，
而是：
- 保留现有 agent 引擎
- 在末尾补一层 contract 生成与校验
- 让 orchestrator 慢慢切到“只认 contract”

这条路最稳，比赛里也最好讲。

---

# 十三、建议提交位置

推荐直接放仓库：

```text
/docs/baseagent-contract-integration.md
```

因为这仍然属于：
- 实现设计稿
- 代码改造前文档

不是最终 Python 实现文件。
