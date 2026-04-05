#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate a non-destructive repair preview for historically corrupted expense rows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / "finance-ledger-expense.jsonl"
OUT = ROOT / "ledger-repair-preview-2026-04-05.json"

REPAIRS: dict[str, dict[str, Any]] = {
    "expense-2026-03-21-1203-njupt-1250": {
        "merchant": "南京邮电大学",
        "category": "餐饮/校园消费",
        "channel": "零钱/校园支付",
        "note": "原金额13.00，优惠0.50，实付12.50；历史记录文本发生编码损坏，按 id 与上下文恢复。",
        "confidence": "high",
    },
    "expense-2026-03-21-1401-xianyu-100": {
        "merchant": "闲鱼客服介入/服务单",
        "category": "售后/服务费",
        "channel": "闲鱼",
        "note": "金额1.00；原文本编码损坏，依据 id 中 xianyu 与当时上下文作修复预览，正式修复前建议再回查原消息。",
        "confidence": "medium",
    },
    "expense-2026-03-21-1437-kefu-2990": {
        "merchant": "客服补差/服务单",
        "category": "购物/补差价",
        "channel": "平台支付",
        "note": "金额29.90；备注中可见与两件商品及补差相关，但原文本已坏，先给修复预览。",
        "confidence": "medium",
    },
    "expense-2026-03-21-1820-xiangcunji-1330": {
        "merchant": "乡村基",
        "category": "餐饮/快餐",
        "channel": "微信支付",
        "note": "用户确认口径的餐饮消费，金额13.30；历史文本编码损坏，按 id 与记录上下文恢复。",
        "confidence": "high",
    },
    "expense-2026-03-21-1856-tastien-2240": {
        "merchant": "塔斯汀中国汉堡",
        "category": "餐饮/快餐",
        "channel": "微信支付",
        "note": "原价45.80，使用12元券后实付22.40；历史文本编码损坏，按 id 与残余数字信息恢复。",
        "confidence": "high",
    },
    "expense-2026-03-25-taobao-domino-coupon-4565": {
        "merchant": "淘宝卡券｜达美乐优惠券",
        "category": "餐饮/预付卡券",
        "channel": "淘宝订单页（用户确认记账）",
        "note": "根据用户明确指令“都记上”补录；截图口径为订单页，记为达美乐优惠券购入。关联后续达美乐门店补差支付记录。",
        "confidence": "high",
    },
    "expense-2026-03-25-domino-nanjing-1030": {
        "merchant": "达美乐南京新模范马路店",
        "category": "餐饮/外卖",
        "channel": "微信支付",
        "note": "支付成功页可见支付金额、支付方式、付款时间；与前序达美乐优惠券购入相关，属本次下单补差支付。",
        "confidence": "high",
    },
    "expense-2026-03-23-1200-njupt-1500": {
        "merchant": "南京邮电大学",
        "category": "餐饮/食堂",
        "channel": "校园支付",
        "note": "用户后续明确确认：这是食堂吃饭消费；历史文本编码损坏，按确认口径恢复。",
        "confidence": "high",
    },
    "expense-2026-03-23-1800-njupt-1600": {
        "merchant": "南京邮电大学",
        "category": "餐饮/食堂",
        "channel": "校园支付",
        "note": "用户后续明确确认：晚间这笔也是食堂消费，金额16.00。",
        "confidence": "high",
    },
    "expense-2026-03-24-1133-junfei-1680": {
        "merchant": "俊飞盖浇饭",
        "category": "餐饮/午饭",
        "channel": "微信支付",
        "note": "支付成功页可见，属午饭消费；历史文本编码损坏后按 id 与旧上下文恢复。",
        "confidence": "high",
    },
    "expense-2026-03-24-1912-laoxiangji-4400": {
        "merchant": "老乡鸡",
        "category": "餐饮/晚餐",
        "channel": "微信支付余额",
        "note": "用户确认：老乡鸡44元，按晚餐口径恢复。",
        "confidence": "high",
    },
    "expense-2026-03-25-0021-orientalleaf-1790": {
        "merchant": "农夫山泉东方树叶 500ml×8",
        "category": "餐饮/饮料",
        "channel": "微信支付余额",
        "note": "深夜下单饮料，原价信息在旧备注中残留；修复为可读版。",
        "confidence": "high",
    },
    "expense-2026-03-26-1228-njupt-1480": {
        "merchant": "南京邮电大学",
        "category": "餐饮/校园消费",
        "channel": "零钱+储蓄卡补足",
        "note": "支付成功页；用户明确要求直接记账，历史文本编码损坏后恢复为可读版。",
        "confidence": "high",
    },
    "expense-2026-03-26-1808-hulailong-2681": {
        "merchant": "南京鼓楼·沪来隆黄焖鸡",
        "category": "餐饮",
        "channel": "农业银行储蓄卡(1271)",
        "note": "原价29.00，优惠2.19，实付26.81。",
        "confidence": "high",
    },
    "expense-2026-03-27-pdd-yogurt-2490": {
        "merchant": "拼多多｜简醇酸奶整箱直达/同类商品",
        "category": "食品/饮品",
        "channel": "拼多多订单页",
        "note": "用户主动确认这类金额图默认直接记账；原文本损坏，先按可读预览恢复。",
        "confidence": "medium",
    },
    "expense-2026-03-28-1345-qieguonow-4059": {
        "merchant": "切果NOW（鼓楼门店）",
        "category": "餐饮/水果",
        "channel": "微信支付商户订单",
        "note": "水果类消费，金额40.59；历史记录文本发生编码损坏，按 id 与残余信息恢复。",
        "confidence": "high",
    },
    "expense-2026-03-28-1223-anqingxiaochidian-814": {
        "merchant": "安庆小吃店",
        "category": "餐饮",
        "channel": "支付成功页",
        "note": "同图中的一笔小额餐饮消费，金额8.14。",
        "confidence": "medium",
    },
    "expense-2026-03-28-1223-anqingxiaochidian-1700": {
        "merchant": "安庆小吃店",
        "category": "餐饮",
        "channel": "支付成功页",
        "note": "同图中的另一笔餐饮消费，金额17.00。",
        "confidence": "medium",
    },
    "expense-2026-03-28-mcd-coupon-3761": {
        "merchant": "麦当劳优惠点单券",
        "category": "餐饮/优惠券",
        "channel": "淘宝订单页",
        "note": "订单页实付37.61，按优惠券购入处理。",
        "confidence": "high",
    },
    "expense-2026-03-28-hotel-16500": {
        "merchant": "酒店房费",
        "category": "住宿/酒店",
        "channel": "微信支付",
        "note": "酒店预订成功，入住日期2026-03-29；原价362，优惠合计197，实付165。",
        "confidence": "high",
    },
    "exp_2026-04-03_121506_junfei_gaijiaofan_3525": {
        "merchant": "俊飞盖浇饭",
        "category": "餐饮",
        "channel": "微信支付",
        "note": "订单金额36.00，优惠0.75，实付35.25。",
        "confidence": "high",
    }
}


def main() -> int:
    rows = LEDGER.read_text(encoding="utf-8", errors="replace").splitlines()
    preview = []
    unresolved = []

    for idx, raw in enumerate(rows, start=1):
        if not raw.strip():
            continue
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            continue
        rec_id = obj.get("id")
        if rec_id not in REPAIRS:
            continue
        repaired = dict(obj)
        repaired.update(REPAIRS[rec_id])
        repaired["repair_meta"] = {
            "mode": "preview_only",
            "source": "manual_mapping_2026-04-05",
            "original_line": idx,
        }
        preview.append(
            {
                "line": idx,
                "id": rec_id,
                "original": obj,
                "repaired_preview": repaired,
            }
        )

    present_ids = {item["id"] for item in preview}
    for rec_id in REPAIRS:
        if rec_id not in present_ids:
            unresolved.append(rec_id)

    out = {
        "generated_at": "2026-04-05T11:02:00+08:00",
        "mode": "preview_only_no_writeback",
        "preview_count": len(preview),
        "unresolved_mappings": unresolved,
        "preview": preview,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(OUT), "preview_count": len(preview), "unresolved": len(unresolved)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
