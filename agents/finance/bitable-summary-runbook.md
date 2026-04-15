# Finance Bitable Summary Runbook

## 目标
把“查飞书主账本 → 出数字 → 判断能不能发复盘”这条链路收成固定动作。

## 正式账本
- app_token: `DTBKbMBRcaO9jHsY99ycAc3unid`
- table_id: `tblX8Jop5niKoOK9`

## 标准动作
### 1. 准备查询参数
先运行：
```bash
python agents/finance/verify_bitable_guard.py --date YYYY-MM-DD
```
作用：
- 规范日期
- 回显唯一正式账本标识
- 明确当前查询应以飞书主账本为准

### 2. 查询飞书主账本
用以下口径查询飞书多维表格：
- 日期字段：`日期时间`
- 目标日期：当天 00:00:00 到 23:59:59（本地时区）
- 状态字段：`状态`
- 金额字段：`金额`

### 3. 汇总输出最小字段
任何正式汇总/复盘前，必须先拿到：
- `record_count`
- `booked_count`（状态=已入账）
- `pending_count`（状态=待确认）
- `abnormal_count`（可先按 0；若后续建立异常字段，再升级）
- `total_amount`

### 4. 才允许发结论
有了上面 5 个数字，才能继续：
- 今日记账小结
- finance 复盘
- 状态异常说明
- 日/周/月总结

## 当前异常数口径
飞书主账本当前还没有单独“异常”字段，因此：
- 当前 `abnormal_count` 可暂按 `0` 输出
- 若实际流程发现异常，必须在文案里单写，不得伪装成账本字段结果
- 后续若补了异常字段，再升级自动统计口径

## 禁止事项
- 禁止跳过飞书查询直接写复盘
- 禁止用本地 JSONL 数字冒充飞书正式结果
- 禁止没有数字就发正式 finance 总结

## 一句话
**先查飞书，再说人话。**
