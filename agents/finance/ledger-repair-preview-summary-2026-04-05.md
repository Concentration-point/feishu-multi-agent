# Ledger Repair Preview Summary · 2026-04-05

## 结果
- 仅生成 preview，**未回写原账本**
- 共生成 21 条修复候选
- unresolved = 0

## 高置信可修
这批基本可以直接进入正式修复候选：
- `expense-2026-03-21-1203-njupt-1250`
- `expense-2026-03-21-1820-xiangcunji-1330`
- `expense-2026-03-21-1856-tastien-2240`
- `expense-2026-03-25-taobao-domino-coupon-4565`
- `expense-2026-03-25-domino-nanjing-1030`
- `expense-2026-03-23-1200-njupt-1500`
- `expense-2026-03-23-1800-njupt-1600`
- `expense-2026-03-24-1133-junfei-1680`
- `expense-2026-03-24-1912-laoxiangji-4400`
- `expense-2026-03-25-0021-orientalleaf-1790`
- `expense-2026-03-26-1228-njupt-1480`
- `expense-2026-03-26-1808-hulailong-2681`
- `expense-2026-03-28-1345-qieguonow-4059`
- `expense-2026-03-28-mcd-coupon-3761`
- `expense-2026-03-28-hotel-16500`
- `exp_2026-04-03_121506_junfei_gaijiaofan_3525`

## 中置信，建议保守处理
- `expense-2026-03-21-1401-xianyu-100`
- `expense-2026-03-21-1437-kefu-2990`
- `expense-2026-03-27-pdd-yogurt-2490`
- `expense-2026-03-28-1223-anqingxiaochidian-814`
- `expense-2026-03-28-1223-anqingxiaochidian-1700`

## 下一步建议
1. 先只正式修复高置信 16 条
2. 中置信 5 条继续保留 preview，不直接覆盖
3. 正式修复仍应采用**非破坏式生成 patched ledger preview**，而不是直接改原始文件
