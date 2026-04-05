# Finance Ledger Repair SOP v1

## 目标
修历史坏账，但不拿原账本当实验田。

## 原则
- **先审计，后修复**
- **先出计划，后落改**
- **默认非破坏式**
- **拿不到原始依据，就不要硬猜**

## 当前工具
- 审计：`python agents/finance/ledger_doctor.py --ledger expense`
- 修复预案：`python agents/finance/ledger_repair_plan.py`

## 修复顺序
1. 先锁定可疑行
2. 优先用 `raw_ref` 回查原图/原消息
3. 回查不到，再看 `id` 里的 hint
4. 能确定的，写出修复候选
5. 不能确定的，标为待人工确认
6. 正式修复前，先产出 preview，不直接覆盖原账本

## 当前发现
- expense 账本存在一批历史乱码行
- 目前更像历史编码事故，不是当前执行器继续写坏
- 新执行器链路已通过 UTF-8 追加 + 回读验证

## 结论
旧账修复该做，但必须慢刀子，不准上电锯。
