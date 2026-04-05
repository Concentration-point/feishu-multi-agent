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

## 配套工具
### 1) record 生成器
```bash
python agents/finance/ledger_make_record.py \
  --output agents/finance/tmp-record.json \
  --date 2026-04-05 \
  --time 18:36 \
  --merchant "乡村基（南京宜悦里店）" \
  --amount 19.50 \
  --category "餐饮/外卖" \
  --channel "外卖订单页" \
  --note "用户主动发送金额图，按已确认消费入账。" \
  --source-type "screenshot+user_confirmation" \
  --confidence high \
  --confirmed true \
  --raw-ref "feishu:om_xxx"
```

### 2) ledger 体检器
```bash
python agents/finance/ledger_doctor.py --ledger expense
```
作用：
- 扫坏行
- 扫重复 id
- 扫历史乱码/可疑文本行
- 只审计，不改账

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
