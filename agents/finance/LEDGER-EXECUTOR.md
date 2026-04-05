# Finance Ledger Executor v1

## 这是什么
这是 finance 的**唯一最小落账入口**。

文件：
- 执行器：`agents/finance/ledger_append.py`
- 消费账本：`agents/finance/finance-ledger-expense.jsonl`
- token 账本：`agents/finance/finance-ledger-token.jsonl`

## 目标
把下面三件事绑成一个事务：
1. 结构化生成记录
2. UTF-8 追加写入 JSONL
3. 立即回读校验记录真实存在

没通过第 3 步，就不算记上。

## 用法
### 消费账
```bash
python agents/finance/ledger_append.py --ledger expense --record-file agents/finance/sample-expense-record.json
```

### token 账
```bash
python agents/finance/ledger_append.py --ledger token --record-file path/to/token-record.json
```

## 输入要求
`--record-file` 必须是一个 UTF-8 JSON 文件，字段必须完整。

### expense 必填字段
- `id`
- `date`
- `time`
- `merchant`
- `amount`
- `direction`
- `category`
- `channel`
- `note`
- `source_type`
- `confidence`
- `confirmed`
- `raw_ref`
- `created_at`

## 成功输出
```json
{"ok": true, "ledger": "...", "id": "...", "verified": true}
```

## 失败输出
```json
{"ok": false, "error": "..."}
```
并返回非 0 退出码。

## 当前保证
- UTF-8 读写
- 禁止重复 `id`
- 追加后立即回读
- 若回读找不到 / 内容不一致 / JSON 损坏，直接判失败

## 当前限制
- 只做最小执行，不负责 OCR、分类推断、截图解析
- 不自动修复历史乱码记录
- 记录构造仍需上游先完成

## 规则
以后凡是要说：
- 已记
- 已入账
- 可直接记
- 已确认消费

就应该先走这个入口，再说话。
