# Finance Ledger Guardrail

## 正式真相源
- finance 唯一正式账本：飞书多维表格（见 `SOURCE-OF-TRUTH.md`）
- 本地 JSONL 仅作辅助，不得单独作为正式对外依据

## 目标
把“识别消费”与“正式落账”绑成一个不可拆开的事务，防止再出现“嘴上说已记，账本里没有”的假落账。

## 强制事务规则
只要主脑或 finance 专岗对外使用以下任一确定性表述：
- 可直接记
- 已确认消费
- 已记
- 已入账
- 这笔没问题
- 可以直接入账

就必须在**同一流程内**完成下面 4 步，缺一不可：

1. 生成结构化账目字段
2. 追加写入 `agents/finance/finance-ledger-expense.jsonl`
3. 立即回读或核对写入结果，确认记录真实存在
4. 只有在第 3 步成功后，才能对外说“已记 / 已入账 / 已记录”

## 失败回退规则
若任一步失败：
- 禁止对外说“已记 / 已入账 / 已记录”
- 必须明确改口为：
  - 未落账
  - 待补记
  - 识别完成但写入失败
- 必须优先报错，不允许沉默吞掉

## 编码规则
- 正式账本统一按 UTF-8 写入
- 追加写入后若回读发现乱码、截断、JSON 非法，视为写入失败
- 不允许继续向污染账本追加“看起来像成功”的记录

## 汇总联动规则
- 日报 / 周报 / 月报 / 年报只认正式账本
- 若聊天里已出现“可直接记 / 已确认消费”，但账本缺失对应记录，完整性检查必须告警
- 汇总任务禁止把“漏记”误写成“今日无新增”

## 执行入口
正式落账默认走：
- `python agents/finance/ledger_append.py --ledger expense --record-file <record.json>`
- `python agents/finance/ledger_append.py --ledger token --record-file <record.json>`

发送前核账默认分两类：
- 本地 JSONL 守卫：`python agents/finance/verify_report_guard.py --date <YYYY-MM-DD>`
- 飞书主账本守卫准备器：`python agents/finance/verify_bitable_guard.py --date <YYYY-MM-DD>`
- 若要校验草稿文案（本地账本场景）：`python agents/finance/verify_report_guard.py --date <YYYY-MM-DD> --report-file <draft.md> --must-include-counts`

执行器职责：
- 校验字段完整性
- 按 UTF-8 追加 JSONL
- 立即回读核对 `id`
- 任一步失败即返回失败，不得嘴上算成功

核账守卫职责：
- 从正式账本计算记录数 / 已入账数 / 待确认数 / 异常数 / 总金额
- 若传入草稿文案，检查是否缺少核心数字
- 拦截“账本空白 / 漏记 / 明天补账 / 未落实”等与账本现状冲突的陈旧状态词
- 若无正式记录，拦截“已记 / 已入账 / 已落实 / 已补完”等确定性表述

## 一句话
**先落盘，再说话。**
