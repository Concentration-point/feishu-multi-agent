# Finance Summary Builder Spec

## 目标
把 finance 正式复盘前的“飞书查询 + 数字汇总 + 可发性判断”收成一个统一 builder。

builder 不是聊天人格，它是**汇总执行器**。
它的职责不是写漂亮话，而是先把数字和状态产出来。

## 输入
最小输入：
```json
{
  "date": "YYYY-MM-DD"
}
```

可扩展输入：
```json
{
  "date": "YYYY-MM-DD",
  "range_type": "day",
  "source_of_truth": "feishu_bitable",
  "strict": true,
  "need_renderable_summary": true
}
```

## 数据源
固定为飞书多维表格：
- app_token: `DTBKbMBRcaO9jHsY99ycAc3unid`
- table_id: `tblX8Jop5niKoOK9`

## 处理流程
1. 校验日期输入
2. 查询飞书主账本对应日期记录
3. 计算以下核心数字：
   - `record_count`
   - `booked_count`
   - `pending_count`
   - `abnormal_count`
   - `total_amount`
4. 生成状态判断：
   - `sendable`: 是否允许直接发送正式复盘/小结
   - `status`: `ok` / `empty` / `needs_attention`
5. 若 `need_renderable_summary=true`，顺手产出一版可直接贴给人的短摘要草稿

## 输出契约
```json
{
  "ok": true,
  "source_of_truth": "feishu_bitable",
  "date": "2026-04-14",
  "summary": {
    "record_count": 37,
    "booked_count": 37,
    "pending_count": 0,
    "abnormal_count": 0,
    "total_amount": 584.19
  },
  "sendable": true,
  "status": "ok",
  "reason": "formal_ledger_has_records_and_core_counts_are_ready",
  "renderable_summary": "昨日已记录 37 笔｜已入账 37｜待确认 0｜异常 0｜总支出 ¥584.19。"
}
```

## sendable 判定规则
### sendable = true
满足以下条件：
- 成功查到飞书主账本
- 核心 5 数齐全
- 若 `record_count > 0`，则允许发正式复盘/小结

### sendable = false
以下任一命中：
- 飞书查询失败
- 核心数字不完整
- 想发正式复盘，但结果仍是未核验状态
- 文案里出现正式状态词，但还没拿到主账本数字

## renderable_summary 规则
如果生成给人看的短摘要，必须：
- 先给数字
- 不先写感想
- 不预设“漏记 / 空白 / 已补完”等结论，除非 builder 已确认

## 与主管 prompt 的关系
- builder 先出结构化结果
- supervisor 再决定如何表达
- supervisor 不得跳过 builder 直接拍脑袋写正式复盘

## 当前实现状态
- 本地已提供脚手架执行器：`finance_summary_builder.py`
- 当前脚手架负责：日期校验、summary JSON 契约校验、sendable 判断、可渲染摘要生成、草稿数字校验
- 飞书实际查询仍由 assistant/tool 层完成；builder 脚本当前不直接请求飞书 API

## 一句话
**builder 先算账，supervisor 再开口。**
