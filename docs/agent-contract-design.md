# multi-agent-feishu Agent Contract 设计稿

> 目标：把当前“会聊天的流程”升级成“有结构化交付契约的多智能体组织”。

## 结论先行
当前项目最该补的，不是更多 soul prompt，而是 **Agent Contract（交付契约）**。

原因很简单：
- 现在每个角色的职责定义是清楚的
- 但上游给下游的交付物还偏自然语言
- 自然语言可以展示，但不适合做阶段推进、状态校验、返工判断、经验沉淀

所以建议：

> **每个 Agent 都必须同时产出两份结果：**
> 1. 给人看的自然语言结果（飞书文档 / 多维表格展示）
> 2. 给系统看的结构化 contract（供 orchestrator / guard / 下游 agent 使用）

---

# 一、总体设计原则

## 1. contract 是正式交付，不是附属备注
每个 agent 执行完成后，真正驱动后续流程的应该是 contract，而不是一段总结。

## 2. supervisor / orchestrator 只认 contract
- 是否允许进入下一阶段
- 是否允许更新状态
- 是否允许对外发送“已完成/已通过/已排期”

都应该以 contract 字段为准，而不是靠 LLM 自己判断“差不多可以了”。

## 3. 自然语言结果只负责展示
- 飞书主表文本字段
- 飞书文档
- 群聊广播

这些都可以继续保留，但它们属于“可读层”，不是“控制层”。

## 4. contract 要能沉淀经验
L2 经验池不应该从整段大作文里硬抽，而应该优先基于 contract + outcome 生成经验卡。

---

# 二、推荐的统一 contract 外壳

建议所有角色共用一层统一 envelope：

```json
{
  "role_id": "strategist",
  "record_id": "rec_xxx",
  "status": "success",
  "version": "v1",
  "output": {},
  "handoff": {
    "next_role": "copywriter",
    "ready": true,
    "blocking_issues": []
  },
  "meta": {
    "started_at": "2026-04-15T23:00:00+08:00",
    "finished_at": "2026-04-15T23:02:10+08:00",
    "tool_calls": 4,
    "notes": []
  }
}
```

## 字段说明
- `role_id`: 当前角色
- `record_id`: 项目主表记录 ID
- `status`: `success` / `partial` / `failed`
- `version`: contract 版本号，后续方便演进
- `output`: 当前角色的核心结构化产物
- `handoff.next_role`: 交接给谁
- `handoff.ready`: 是否满足进入下一阶段
- `handoff.blocking_issues`: 阻塞原因
- `meta`: 运行元信息

---

# 三、各角色 contract 设计

---

## 1. 客户经理（account_manager）contract

### 角色目标
把原始 Brief 变成结构化可执行需求，不让后续角色直接啃原始文本。

### 推荐 contract

```json
{
  "role_id": "account_manager",
  "status": "success",
  "output": {
    "client_name": "某美妆品牌",
    "project_type": "双十一电商营销",
    "brief_summary": "客户希望围绕双十一做一轮站内外联动内容营销。",
    "campaign_goal": "提升大促转化与预热声量",
    "target_audience": ["18-30岁女性消费者", "关注护肤和彩妆人群"],
    "core_requirements": ["突出双十一促销节奏", "强调品牌专业感"],
    "constraints": ["避免过度低价叫卖", "避免绝对化表达"],
    "risks": ["Brief 中促销机制描述不完整"]
  },
  "handoff": {
    "next_role": "strategist",
    "ready": true,
    "blocking_issues": []
  }
}
```

### 必填最小集
- `brief_summary`
- `campaign_goal`
- `target_audience`
- `core_requirements`
- `constraints`

### 不满足则不得进入下一阶段
如果缺少目标、受众、限制条件，就不能让 strategist 开工。

---

## 2. 策略师（strategist）contract

### 角色目标
把结构化 brief 变成内容策略和内容矩阵。

### 推荐 contract

```json
{
  "role_id": "strategist",
  "status": "success",
  "output": {
    "strategy_summary": "采用预热-爆发-返场三阶段内容节奏，围绕成分力、功效力、价格利益点组织内容。",
    "content_pillars": ["产品卖点", "场景种草", "大促转化"],
    "platform_plan": [
      {"platform": "小红书", "count": 4},
      {"platform": "公众号", "count": 2},
      {"platform": "短视频", "count": 4}
    ],
    "content_items": [
      {
        "seq": 1,
        "title": "双十一预热主张",
        "platform": "小红书",
        "content_type": "种草图文",
        "key_point": "成分党安心感",
        "target_audience": "年轻女性"
      }
    ],
    "knowledge_refs": ["历史双十一案例A", "品牌大促 SOP"]
  },
  "handoff": {
    "next_role": "copywriter",
    "ready": true,
    "blocking_issues": []
  }
}
```

### 必填最小集
- `strategy_summary`
- `content_pillars`
- `content_items`

### 阶段门槛
- `content_items.length >= 1`
- 每条 item 必须有：`title/platform/content_type/key_point/target_audience`

没有内容矩阵，就不能让文案开工。

---

## 3. 文案（copywriter）contract

### 角色目标
基于内容矩阵逐条产出可审核成稿。

### 推荐 contract

```json
{
  "role_id": "copywriter",
  "status": "success",
  "output": {
    "drafted_items": [
      {
        "content_record_id": "rec_content_1",
        "title": "双十一预热主张",
        "draft_ready": true,
        "word_count": 312,
        "platform": "小红书"
      }
    ],
    "draft_count": 10,
    "missing_items": []
  },
  "handoff": {
    "next_role": "reviewer",
    "ready": true,
    "blocking_issues": []
  }
}
```

### 必填最小集
- `drafted_items`
- `draft_count`
- `missing_items`

### 阶段门槛
- 所有策略师创建的 content item 都必须被覆盖
- 若有缺稿，`handoff.ready = false`

---

## 4. 审核（reviewer）contract

### 角色目标
把“看起来像成稿”的东西变成“是否允许进入排期”的明确判断。

### 推荐 contract

```json
{
  "role_id": "reviewer",
  "status": "success",
  "output": {
    "total_items": 10,
    "passed_items": 7,
    "failed_items": 3,
    "pass_rate": 0.7,
    "review_results": [
      {
        "content_record_id": "rec_content_1",
        "review_status": "通过",
        "feedback": "可直接排期"
      },
      {
        "content_record_id": "rec_content_2",
        "review_status": "驳回",
        "feedback": "促销口径过猛，需重写 CTA"
      }
    ],
    "blocking_issues": ["3 条内容存在平台字数与措辞问题"]
  },
  "handoff": {
    "next_role": "project_manager",
    "ready": true,
    "blocking_issues": []
  }
}
```

### 必填最小集
- `total_items`
- `passed_items`
- `failed_items`
- `pass_rate`
- `review_results`

### 阶段门槛
- `pass_rate >= 阈值` 才允许进入 project_manager
- 若 `< 阈值`，应该交回 copywriter，而不是继续往下走

这里建议把“返工”也结构化：

```json
"handoff": {
  "next_role": "copywriter",
  "ready": false,
  "blocking_issues": ["pass_rate_below_threshold"]
}
```

---

## 5. 项目经理（project_manager）contract

### 角色目标
对审核通过内容完成排期与交付汇总。

### 推荐 contract

```json
{
  "role_id": "project_manager",
  "status": "success",
  "output": {
    "scheduled_items": 7,
    "unscheduled_items": 3,
    "delivery_summary": "本项目共完成 10 条内容，其中 7 条通过审核并完成排期。",
    "publish_plan": [
      {
        "content_record_id": "rec_content_1",
        "publish_date": "2026-11-01"
      }
    ]
  },
  "handoff": {
    "next_role": null,
    "ready": true,
    "blocking_issues": []
  }
}
```

### 必填最小集
- `scheduled_items`
- `unscheduled_items`
- `delivery_summary`
- `publish_plan`

### 阶段门槛
- 至少要有 1 条通过审核的内容被排期
- 否则不应直接宣告“已完成”

---

# 四、建议新增一个组织治理 contract（manager / guard）

当前项目里最缺的不是业务角色，而是治理角色。

## 推荐新增角色：workflow_guard / manager

### 职责
- 检查当前阶段 contract 是否完整
- 检查状态是否允许推进
- 检查是否满足下一阶段前置条件
- 拦截不完整交付

### 推荐 contract

```json
{
  "role_id": "workflow_guard",
  "status": "success",
  "output": {
    "stage": "review_to_pm",
    "all_checks_passed": true,
    "checks": [
      {"name": "review_contract_exists", "passed": true},
      {"name": "pass_rate_above_threshold", "passed": true},
      {"name": "approved_items_nonzero", "passed": true}
    ]
  },
  "handoff": {
    "next_role": "project_manager",
    "ready": true,
    "blocking_issues": []
  }
}
```

## 为什么值得单独做
因为：
- 业务角色会偏向“完成自己的活”
- guard 才负责“流程到底能不能过”

**组织治理不应该散落在文档里。**

---

# 五、contract 如何落地到你当前仓库

## 推荐新增目录
```text
agents/contracts/
```

里面放：
- `base_contract.md` / `base_contract.json`
- `account_manager.contract.json`
- `strategist.contract.json`
- `copywriter.contract.json`
- `reviewer.contract.json`
- `project_manager.contract.json`
- `workflow_guard.contract.json`

## 推荐代码层改动

### 1. BaseAgent 增加结构化输出约束
建议加一个方法：
- `async def run_contract() -> dict`

然后 `run()` 可以返回自然语言，`run_contract()` 返回结构化 contract。

更稳一点的做法：
- 让 LLM 最后一轮**强制输出 JSON contract**
- BaseAgent 负责校验 JSON 结构
- 校验不过就重试或标失败

### 2. orchestrator 只吃 contract
不要直接看自然语言字段推进流程。
应该：
- `contract.ready == true` 才能进入下一阶段
- `contract.output` 决定状态更新和下游输入

### 3. 项目主表 / 内容表可继续存展示结果
但 contract 最好单独存：
- 可以先存在 memory/working
- 或者单独一张 Bitable 表：`Agent Contract Log`

如果比赛时间紧，先本地落 JSON 文件也行。

---

# 六、推荐的最小落地顺序

如果你现在正在赶 agent 部分，不要一口气全重构。按这个顺序最划算：

## Phase 1
先给 **account_manager** 和 **strategist** 补 contract。

原因：
- 这两个是上游
- 一旦它们结构化，下游质量会立刻稳很多

## Phase 2
给 **reviewer** 补 contract。

原因：
- reviewer 是全流程里最关键的 gatekeeper
- `pass_rate`、`failed_items`、`blocking_issues` 一旦结构化，返工和排期都会顺

## Phase 3
再补 copywriter / project_manager / workflow_guard。

---

# 七、我对你这个项目的最终建议

一句话版：

> **别再给 agent 加更多“人格”，先给它们加“交付契约”。**

人格决定气质，
contract 决定系统会不会翻车。

你这个项目已经有很好的：
- 飞书载体
- 多角色分工
- 共享记忆
- 工具分层

现在最值钱的一步，就是把“谁给谁交什么”钉死。

这样它就不再只是一个会演公司的 demo，
而是一个开始像“组织操作系统”的东西。

---

# 八、建议上传位置

最推荐放到仓库：

```text
/docs/agent-contract-design.md
```

如果你暂时还没建 `docs/`，那第二选择是：

```text
/agents/contracts/README.md
```

## 我的建议
- **如果你把它当设计文档/方案稿** → 放 `docs/agent-contract-design.md`
- **如果你准备马上按这个落 contract 文件** → 放 `agents/contracts/README.md`

就你现在这个阶段，我更推荐：

> **先传到 `docs/agent-contract-design.md`**

因为它现在是“架构设计稿”，不是实现文件。
