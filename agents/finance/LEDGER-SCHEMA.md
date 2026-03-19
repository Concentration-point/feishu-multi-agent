# Finance Agent - 账本结构说明 v1

## 目标
为 finance 专岗提供统一、可追加、可回溯的账本结构，支撑：
- 消费记账
- OpenClaw token 自动记录
- 每日 / 每周 / 每月 / 每年度汇总

## 存储策略
v1 先采用 **JSONL**：
- 一行一条记录
- 便于追加
- 人能看，程序也能读
- 后续容易转 CSV / 表格

账本分两份，不混：
1. `finance-ledger-expense.jsonl`
2. `finance-ledger-token.jsonl`

---

## 一、消费流水账本
文件：`finance-ledger-expense.jsonl`

### 每条记录字段
```json
{
  "id": "",
  "date": "",
  "time": "",
  "merchant": "",
  "amount": 0,
  "direction": "expense",
  "category": "",
  "channel": "",
  "note": "",
  "source_type": "screenshot",
  "confidence": "medium",
  "confirmed": false,
  "raw_ref": "",
  "created_at": ""
}
```

### 字段说明
- `id`：唯一 ID
- `date`：消费日期，格式 `YYYY-MM-DD`
- `time`：消费时间，可空，格式 `HH:mm`
- `merchant`：商户/项目名
- `amount`：金额，数值型，不带货币符号
- `direction`：`expense` / `income`
- `category`：消费分类
- `channel`：微信 / 支付宝 / 银行卡 / 现金等，可空
- `note`：备注，可空
- `source_type`：`screenshot` / `csv` / `text` / `manual`
- `confidence`：`high` / `medium` / `low`
- `confirmed`：是否已确认
- `raw_ref`：原始截图/文件引用，可空
- `created_at`：记录生成时间，ISO 8601

### 推荐分类
- 餐饮
- 交通
- 日用消费
- 数码/工具
- 订阅服务
- 学习/课程
- 娱乐/社交
- 医疗
- 其他

---

## 二、Token 流水账本
文件：`finance-ledger-token.jsonl`

### 每条记录字段
```json
{
  "id": "",
  "date": "",
  "time": "",
  "session_key": "",
  "agent_type": "",
  "model": "",
  "input_tokens": 0,
  "output_tokens": 0,
  "total_tokens": 0,
  "estimated_cost": null,
  "task_type": "",
  "source_type": "session_status",
  "confidence": "high",
  "created_at": ""
}
```

### 字段说明
- `id`：唯一 ID
- `date`：采样日期，格式 `YYYY-MM-DD`
- `time`：采样时间，格式 `HH:mm`
- `session_key`：会话 key
- `agent_type`：`main` / `coding` / `editor` / `finance` / `other`
- `model`：模型名
- `input_tokens`：输入 token
- `output_tokens`：输出 token
- `total_tokens`：总 token
- `estimated_cost`：若系统未提供则为 `null`
- `task_type`：任务类型，可空
- `source_type`：`session_status` / `runtime_usage` / `manual`
- `confidence`：`high` / `medium` / `low`
- `created_at`：记录生成时间，ISO 8601

---

## 三、汇总层
汇总层可以后续从两份 JSONL 动态生成，不一定先建实体账本。

### 每日小结
- 今日总支出
- 今日笔数
- 今日各类别简表
- 未确认账目数
- 今日 token 快照 / 简要总结

### 每周日总结
- 本周总支出
- 分类占比
- 最大几笔支出
- 未确认账目数
- 本周 token / 使用趋势
- 异常点

### 每月总结
- 本月总支出
- 各类别支出排行
- 订阅类支出汇总
- 异常大额支出
- OpenClaw 本月 token / 成本趋势

### 每年度总结
- 年度总支出
- 年度类别占比
- 工具/订阅年度成本
- OpenClaw 年度 token / 成本总览
- 高峰月份

---

## 四、硬规则
- 消费账本和 token 账本必须分开
- 模糊截图不得直接形成 `confirmed=true` 的正式账目
- 若无精确 cost，不得自行估算成本并写入正式 token 流水
- 所有汇总默认只基于已记录数据，不得伪造“完整账期”

## 一句话总结
v1 先把流水记干净，再谈高级分析。