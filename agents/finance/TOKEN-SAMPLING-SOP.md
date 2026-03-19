# Finance Agent - Token 采样 SOP v1

## 目标
把 OpenClaw token / usage 记录变成稳定采样、统一格式、可做趋势分析的流水。

## 数据源优先级
### 一级
- session_status
- 系统返回的 usage / token / cost 信息

### 二级
- 运行结果里的会话 usage
- 已知结构化状态卡片

### 三级
- 手工估算
- 模糊推断

规则：三级数据只允许做备注，不允许当正式 token 记录。

## 每次采样最少记录字段
- 日期
- 时间
- session_key
- agent_type
- model
- input_tokens
- output_tokens
- total_tokens
- estimated_cost（若无则留空）
- source_type
- confidence

## 采样步骤
### Step 1：拉取当前状态
优先用 session_status

### Step 2：抽字段
把 token 和 cost 拆成结构化字段，不直接散文式描述

### Step 3：判断置信度
#### 高置信
- 数据直接来自系统状态

#### 中置信
- 字段部分缺失，但来源靠谱

#### 低置信
- 需要估算或转述
- 不作为正式流水

### Step 4：输出采样结果
先标准化回显，后续再沉账本

## 单次采样回显模板
```md
已记录一条 OpenClaw token 使用数据：

- 时间：2026-03-19 10:30
- 会话：main
- 模型：custom-api/gpt-5.4
- input：189
- output：1900
- total：2089
- cost：0
- 置信度：高
```

## 异常提醒模板
```md
今天 token 消耗明显偏高。

- 总 tokens 比近几天均值高
- 主要消耗集中在：主会话
- 建议：回头看一下是不是长轮对话或重复调试吃掉了预算
```

## 硬规则
- 没拿到 cost，就写“暂无精确 cost”
- 不要自己脑补美元金额
- 不要把 context usage 混成 token 消耗本体
- token 采样和消费账本必须分开存
