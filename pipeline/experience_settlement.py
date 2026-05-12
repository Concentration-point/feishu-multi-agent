"""经验蒸馏与沉淀：流水线收尾后从外部反馈中蒸馏 L2 经验并写入 Bitable/Chroma/Wiki。"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from config import (
    EXPERIENCE_CONFIDENCE_THRESHOLD,
    EXPERIENCE_POOL_ROLE_ALLOWLIST,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    LLM_TIMEOUT_SECONDS,
)
from memory.experience import ExperienceManager as _DefaultExperienceManager
from memory.project import ContentMemory as _DefaultContentMemory

if TYPE_CHECKING:
    from memory.experience import ExperienceManager
    from memory.project import ContentMemory
    from orchestrator import Orchestrator


logger = logging.getLogger(__name__)


def _resolve_ContentMemory():
    """通过 orchestrator 模块属性获取 ContentMemory，让测试 monkey-patch 生效。"""
    import sys
    orch_mod = sys.modules.get("orchestrator")
    if orch_mod is not None:
        return getattr(orch_mod, "ContentMemory", _DefaultContentMemory)
    return _DefaultContentMemory


def _resolve_ExperienceManager():
    """通过 orchestrator 模块属性获取 ExperienceManager，让测试 monkey-patch 生效。"""
    import sys
    orch_mod = sys.modules.get("orchestrator")
    if orch_mod is not None:
        return getattr(orch_mod, "ExperienceManager", _DefaultExperienceManager)
    return _DefaultExperienceManager


# ── 经验蒸馏 prompt（链路A：审核驳回反馈 → 文案/审核经验）──
_DISTILL_PROMPT_CHAIN_A = (
    "你是一名飞书多 Agent 系统的经验蒸馏员。\n\n"
    "以下是一个内容营销项目的审核驳回记录：\n"
    "任务摘要：{task_summary}\n\n"
    "审核驳回意见：\n{feedback_text}\n\n"
    "请基于以上审核反馈（不要推测其他信息），输出一条供文案和审核角色复用的经验卡片 JSON：\n"
    "{\n"
    '  "situation": "某平台某品类内容在撰写/审核时遇到的具体场景",\n'
    '  "violations_found": ["从驳回意见提炼出的违规类型1", "违规类型2"],\n'
    '  "action": "文案应该怎么写才能提前规避这类问题",\n'
    '  "outcome": "该类问题被驳回的后果",\n'
    '  "lesson": "下次撰写此类内容时必须预先检查的具体事项（可操作）",\n'
    '  "category": "电商大促|新品发布|品牌传播|日常运营",\n'
    '  "applicable_roles": ["reviewer", "copywriter"]\n'
    "}\n\n"
    "要求：\n"
    "- lesson 必须具体到可执行的检查项，不要空泛\n"
    "- violations_found 落到具体违规类型，不要写「表达问题」这种\n"
    '- applicable_roles 固定为 ["reviewer", "copywriter"]，不允许修改\n'
    "- 只输出 JSON，不要任何其他文字"
)

# ── 经验蒸馏 prompt（链路B：人类修改意见 → 客户经理经验）──
_DISTILL_PROMPT_CHAIN_B = (
    "你是一名飞书多 Agent 系统的经验蒸馏员。\n\n"
    "以下是一个内容营销项目的人类审核修改记录：\n"
    "任务摘要：{task_summary}\n\n"
    "人类审核意见：\n{feedback_text}\n\n"
    "请基于以上人类修改意见（不要推测其他信息），输出一条供客户经理角色复用的 Brief 解读经验卡片 JSON：\n"
    "{\n"
    '  "situation": "某类客户或某类项目的 Brief 解读场景",\n'
    '  "human_correction": "人类指出的关键修正点（具体记录，若无修改写「无修改」）",\n'
    '  "reasoning": "人类修正背后的思维方式或业务逻辑",\n'
    '  "action": "正确的 Brief 解读策略",\n'
    '  "outcome": "采纳修正后的结果",\n'
    '  "lesson": "当客户说[X]时，通常意思是[Y]，下次需要关注[Z]（具体可操作）",\n'
    '  "category": "电商大促|新品发布|品牌传播|日常运营",\n'
    '  "applicable_roles": ["account_manager"]\n'
    "}\n\n"
    "要求：\n"
    "- human_correction 必须具体记录人类的修改点\n"
    "- lesson 必须是具体可复用的解读模式，不是「注意沟通」这种废话\n"
    '- applicable_roles 固定为 ["account_manager"]，不允许修改\n'
    "- 只输出 JSON，不要任何其他文字"
)


def calc_confidence(
    pass_rate: float | None,
    task_completed: bool,
    no_rework: bool,
    knowledge_cited: bool,
) -> float:
    """加权置信度计算（legacy，外部反馈链路固定 0.85，此函数保留兼容旧调用）。"""
    score = 0.0
    score += 0.4 * (pass_rate if pass_rate is not None else 0.5)
    score += 0.3 * (1.0 if task_completed else 0.0)
    score += 0.2 * (1.0 if no_rework else 0.0)
    score += 0.1 * (1.0 if knowledge_cited else 0.0)
    return round(score, 2)


async def distill_experience(
    orch: "Orchestrator",
    task_summary: str,
    feedback_text: str,
    applicable_roles: list[str],
) -> dict | None:
    """新开干净 LLM 调用从外部反馈中蒸馏经验，不复用 ReAct 历史。

    根据 applicable_roles 选择链路A（含 reviewer）或链路B（account_manager）prompt。
    """
    if "reviewer" in applicable_roles:
        prompt_tpl = _DISTILL_PROMPT_CHAIN_A
    else:
        prompt_tpl = _DISTILL_PROMPT_CHAIN_B

    prompt = prompt_tpl.format(
        task_summary=task_summary,
        feedback_text=feedback_text,
    )

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            base_url=LLM_BASE_URL,
            api_key=LLM_API_KEY,
            timeout=LLM_TIMEOUT_SECONDS,
        )
        resp = await client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

        card = json.loads(raw)

        _VALID_CATEGORIES = {"电商大促", "新品发布", "品牌传播", "日常运营"}
        card.setdefault("situation", "")
        card.setdefault("action", "")
        card.setdefault("outcome", "")
        card.setdefault("lesson", "")
        if card.get("category") not in _VALID_CATEGORIES:
            card["category"] = "未分类"
        # 强制覆盖 applicable_roles，不允许 LLM 自行修改
        card["applicable_roles"] = applicable_roles

        return card
    except Exception as exc:
        logger.warning("[经验蒸馏] _distill_experience 失败: %s", exc)
        return None


async def distill_from_feedback(orch: "Orchestrator", project_name: str) -> list[dict]:
    """检查外部反馈信号，按需蒸馏经验，返回 experience card list。

    链路A：内容排期表中有审核驳回行 → 蒸馏文案/审核经验
    链路B：项目主表有人类修改意见 → 蒸馏客户经理经验
    两条链路独立执行，各自异常不影响另一条，无反馈时返回空列表。
    """
    results: list[dict] = []

    # ── 链路A：审核驳回反馈 → reviewer / copywriter 经验 ──
    try:
        rows = await _resolve_ContentMemory()().list_by_project(project_name)
        rejected_rows = [
            r for r in rows
            if r.review_status in ("需修改", "驳回") and (r.review_feedback or "").strip()
        ]
        if rejected_rows:
            feedback_text = "\n\n".join(r.review_feedback.strip() for r in rejected_rows)
            task_summary = (
                f"项目「{project_name}」内容审核，{len(rejected_rows)} 条被驳回"
            )
            card = await orch._distill_experience(
                task_summary, feedback_text, ["reviewer", "copywriter"]
            )
            if card:
                results.append({"role_id": "reviewer", "card": card})
                logger.info("[经验蒸馏] 链路A完成: %s", card.get("lesson", "")[:60])
    except Exception as exc:
        logger.warning("[经验蒸馏] 链路A失败，跳过: %s", exc)

    # ── 链路B：人类修改意见 → account_manager 经验 ──
    try:
        proj = await orch._pm.load()
        human_feedback = (proj.human_feedback or "").strip()
        if human_feedback:
            task_summary = f"项目「{project_name}」Brief 解读，人类审核给出修改意见"
            card = await orch._distill_experience(
                task_summary, human_feedback, ["account_manager"]
            )
            if card:
                results.append({"role_id": "account_manager", "card": card})
                logger.info("[经验蒸馏] 链路B完成: %s", card.get("lesson", "")[:60])
    except Exception as exc:
        logger.warning("[经验蒸馏] 链路B失败，跳过: %s", exc)

    return results


async def settle_experiences(
    orch: "Orchestrator",
    project_name: str,
    pass_rate: float | None,
) -> None:
    pending = await orch._distill_from_feedback(project_name)
    if not pending:
        print("[Orchestrator] 无外部反馈信号，跳过经验蒸馏")
        return

    orch._publish("experience.settle_started", {
        "total": len(pending),
        "project_name": project_name,
    })

    deduped: dict[str, dict] = {}
    for item in pending:
        deduped[item["role_id"]] = item
    unique_pending = list(deduped.values())

    em = _resolve_ExperienceManager()()
    total = len(unique_pending)
    passed = 0
    merged_count = 0
    settled = 0

    for item in unique_pending:
        role_id = item["role_id"]
        card = item["card"]

        # 角色白名单过滤：只有外部验证来源的角色经验才进入 L2 经验池。
        if role_id not in EXPERIENCE_POOL_ROLE_ALLOWLIST:
            logger.info(
                "[经验沉淀] 跳过 %s，该角色不在 L2 经验池白名单 %s",
                role_id, sorted(EXPERIENCE_POOL_ROLE_ALLOWLIST),
            )
            continue

        # 外部反馈驱动的蒸馏已经过验证，固定置信度 0.85
        confidence = 0.85

        orch._publish("experience.scored", {
            "role_id": role_id,
            "confidence": confidence,
            "threshold": EXPERIENCE_CONFIDENCE_THRESHOLD,
            "passed": confidence >= EXPERIENCE_CONFIDENCE_THRESHOLD,
            "factors": {
                "external_feedback": True,
            },
            "lesson": str(card.get("lesson", "") or "")[:80],
            "category": card.get("category", "未分类"),
        }, agent_role=role_id)

        if confidence < EXPERIENCE_CONFIDENCE_THRESHOLD:
            logger.info(
                "[经验沉淀] 跳过 %s，置信度 %.2f < %.2f",
                role_id,
                confidence,
                EXPERIENCE_CONFIDENCE_THRESHOLD,
            )
            continue

        passed += 1
        try:
            category = card.get("category", "未分类")
            lesson = str(card.get("lesson", "") or "")
            card.setdefault("title", f"{category} - {role_id} - {lesson[:18]}")
            card["source_project"] = project_name
            card["source_run"] = orch.record_id
            card["source_stage"] = role_id
            card["review_status"] = await orch._get_project_review_status()
            saved = await em.save_experience(card, confidence, project_name)
            wiki_saved = await em.save_to_wiki(card, confidence)
            if saved or wiki_saved:
                settled += 1
                orch._publish("experience.saved", {
                    "role_id": role_id,
                    "category": category,
                    "confidence": confidence,
                    "lesson": lesson[:80],
                    "bitable_saved": bool(saved),
                    "wiki_saved": bool(wiki_saved),
                }, agent_role=role_id)

                optimize_roles = card.get("applicable_roles") or [role_id]
                seen_roles: set[str] = set()
                for optimize_role in optimize_roles:
                    optimize_role = str(optimize_role or role_id)
                    if optimize_role in seen_roles:
                        continue
                    seen_roles.add(optimize_role)
                    optimize_call = em.optimize_bucket(
                        optimize_role, category, project_name=project_name
                    )
                    optimize_summary = {}
                    if hasattr(optimize_call, "__await__"):
                        optimize_summary = await optimize_call
                    if optimize_summary:
                        if optimize_summary.get("merged_created", 0) > 0:
                            merged_count += 1
                            orch._publish("experience.merging", {
                                "role_id": optimize_role,
                                "category": category,
                                "existing_count": optimize_summary.get("after_dedup", 0),
                            }, agent_role=optimize_role)
                            orch._publish("experience.merged", {
                                "role_id": optimize_role,
                                "category": category,
                                "merged_from": optimize_summary.get("merged_deleted", 0),
                                "new_count": optimize_summary.get("merged_created", 0),
                            }, agent_role=optimize_role)
                        if (
                            optimize_summary.get("dedup_deleted", 0) > 0
                            or optimize_summary.get("merged_created", 0) > 0
                        ):
                            orch._publish("experience.optimized", {
                                **optimize_summary,
                            }, agent_role=optimize_role)
            else:
                logger.info("[经验沉淀] %s 被质量门槛或去重策略拦截，未落盘", role_id)
        except Exception as exc:
            logger.warning("[经验沉淀] %s 沉淀失败: %s", role_id, exc)

    # ── 经验进化统计输出 ──
    print("\n" + "-" * 60)
    print("  经验进化统计（自进化闭环）")
    print("-" * 60)
    print(f"  外部反馈蒸馏产出: {total} 条")
    print(f"  置信度阈值:     ≥ {EXPERIENCE_CONFIDENCE_THRESHOLD:.2f}")
    print(f"  打分通过:       {passed} 条")
    print(f"  去重合并:       {merged_count} 组")
    print(f"  最终沉淀:       {settled} 条（Bitable + Wiki 双写）")

    # 按角色统计沉淀来源
    role_stats: dict[str, int] = {}
    for item in unique_pending:
        rid = item["role_id"]
        role_stats[rid] = role_stats.get(rid, 0) + 1
    if role_stats:
        roles_line = " | ".join(f"{r}: {c}" for r, c in role_stats.items())
        print(f"  来源角色分布:   {roles_line}")

    # 展示沉淀样例（最多 2 条）
    sample_count = 0
    for item in unique_pending:
        card = item.get("card") or {}
        lesson = str(card.get("lesson", "") or "")[:60]
        if lesson and sample_count < 2:
            cat = card.get("category", "未分类")
            print(f"  样例 [{item['role_id']}][{cat}]: {lesson}...")
            sample_count += 1

    print("-" * 60)

    orch._publish("experience.settle_completed", {
        "total_distilled": total,
        "passed_scoring": passed,
        "merged_groups": merged_count,
        "final_settled": settled,
        "project_name": project_name,
    })


async def append_evolution_log(
    orch: "Orchestrator",
    project_name: str,
    project_type: str,
    pass_rate: float | None,
) -> None:
    """将本次运行关键指标追加写入 evolution_log.json。写入失败只打日志不阻塞。"""
    import json as _json
    from datetime import datetime, timezone
    from pathlib import Path

    log_path = Path("evolution_log.json")

    # 经验注入条数由 BaseAgent 内部统计，蒸馏重构后不再从 pending 汇总
    experiences_injected = 0

    # 统计内容行数
    content_count = 0
    try:
        rows = await _resolve_ContentMemory()().list_by_project(project_name)
        content_count = len(rows)
    except Exception:
        pass

    entry = {
        "run_id": orch.record_id,
        "project_type": project_type or "未知",
        "experiences_injected": int(experiences_injected),
        "review_pass_rate": round(float(pass_rate), 4) if pass_rate is not None else 0.0,
        "rework_count": int(orch.reviewer_retries),
        "content_count": int(content_count),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        if log_path.exists():
            existing = _json.loads(log_path.read_text(encoding="utf-8"))
            if not isinstance(existing, list):
                existing = []
        else:
            existing = []
        existing.append(entry)
        log_path.write_text(
            _json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("evolution_log.json 已追加: run_id=%s entries=%d", orch.record_id, len(existing))
    except Exception as exc:
        logger.warning("evolution_log.json 写入失败（不阻塞主流程）: %s", exc)
