"""经验进化可视化单元测试。

验证点：
1. orchestrator _settle_experiences 发布 experience.* 事件
2. 外部反馈驱动的固定置信度（0.85）
3. 事件 payload 结构完整
4. 各阶段事件顺序（scored → merging → merged → saved → settle_completed）
5. 白名单过滤与置信度门控
6. settle_completed 汇总数据一致性
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── 置信度计算（_calc_confidence 仍存在，保留验证）──

class TestCalcConfidence:
    """_calc_confidence 静态方法测试。"""

    def setup_method(self):
        from orchestrator import Orchestrator
        self.calc = Orchestrator._calc_confidence

    def test_perfect_score(self):
        score = self.calc(pass_rate=1.0, task_completed=True, no_rework=True, knowledge_cited=True)
        assert score == 1.0

    def test_zero_score(self):
        score = self.calc(pass_rate=0.0, task_completed=False, no_rework=False, knowledge_cited=False)
        assert score == 0.0

    def test_pass_rate_none(self):
        score = self.calc(pass_rate=None, task_completed=True, no_rework=True, knowledge_cited=True)
        # 0.4*0.5 + 0.3*1 + 0.2*1 + 0.1*1 = 0.2+0.3+0.2+0.1 = 0.8
        assert score == 0.8

    def test_below_threshold(self):
        score = self.calc(pass_rate=0.3, task_completed=False, no_rework=True, knowledge_cited=False)
        # 0.4*0.3 + 0.3*0 + 0.2*1 + 0.1*0 = 0.12+0+0.2+0 = 0.32
        assert score == 0.32

    def test_threshold_boundary(self):
        from config import EXPERIENCE_CONFIDENCE_THRESHOLD
        score = self.calc(pass_rate=0.75, task_completed=True, no_rework=False, knowledge_cited=True)
        # 0.4*0.75 + 0.3*1 + 0.2*0 + 0.1*1 = 0.3+0.3+0+0.1 = 0.7
        assert score < EXPERIENCE_CONFIDENCE_THRESHOLD


# ── 经验事件发布 ──

class TestSettleExperienceEvents:
    """_settle_experiences 中的事件发布测试。"""

    @pytest.fixture
    def orch(self):
        from dashboard.event_bus import EventBus
        from orchestrator import Orchestrator
        bus = EventBus()
        o = Orchestrator(record_id="recTEST001", event_bus=bus)
        o.stage_results = []
        o.reviewer_retries = 0
        return o, bus

    def _make_pending(self, role_id: str, category: str = "电商大促", lesson: str = "测试经验教训") -> dict:
        return {
            "role_id": role_id,
            "card": {
                "situation": "测试场景",
                "action": "测试策略行动",
                "outcome": "测试结果输出",
                "lesson": lesson,
                "category": category,
                "applicable_roles": [role_id],
            },
        }

    @pytest.mark.asyncio
    async def test_settle_started_event(self, orch):
        o, bus = orch
        pending = [self._make_pending("account_manager")]
        with patch.object(o, '_distill_from_feedback', AsyncMock(return_value=pending)):
            with patch.object(type(o), "_get_project_review_status", new_callable=AsyncMock, return_value="approved"):
                with patch("orchestrator.ExperienceManager") as MockEM:
                    em = MockEM.return_value
                    em.check_dedup = AsyncMock(return_value=[])
                    em.save_experience = AsyncMock(return_value="recEXP001")
                    em.save_to_wiki = AsyncMock(return_value="wiki/path.md")
                    await o._settle_experiences("测试项目", 0.8)

        events = bus.get_history("recTEST001")
        started = [e for e in events if e["event_type"] == "experience.settle_started"]
        assert len(started) == 1
        assert started[0]["payload"]["total"] == 1
        assert started[0]["payload"]["project_name"] == "测试项目"

    @pytest.mark.asyncio
    async def test_scored_event_payload(self, orch):
        o, bus = orch
        pending = [self._make_pending("account_manager")]

        with patch.object(o, '_distill_from_feedback', AsyncMock(return_value=pending)):
            with patch.object(type(o), "_get_project_review_status", new_callable=AsyncMock, return_value="approved"):
                with patch("orchestrator.ExperienceManager") as MockEM:
                    em = MockEM.return_value
                    em.check_dedup = AsyncMock(return_value=[])
                    em.save_experience = AsyncMock(return_value="recEXP001")
                    em.save_to_wiki = AsyncMock(return_value="wiki/path.md")
                    await o._settle_experiences("测试项目", 0.8)

        events = bus.get_history("recTEST001")
        scored = [e for e in events if e["event_type"] == "experience.scored"]
        assert len(scored) == 1
        p = scored[0]["payload"]
        assert p["role_id"] == "account_manager"
        assert isinstance(p["confidence"], float)
        assert isinstance(p["threshold"], float)
        assert "factors" in p
        assert "external_feedback" in p["factors"]
        assert "category" in p

    @pytest.mark.asyncio
    async def test_saved_event_on_success(self, orch):
        o, bus = orch
        pending = [self._make_pending("account_manager")]

        with patch.object(o, '_distill_from_feedback', AsyncMock(return_value=pending)):
            with patch.object(type(o), "_get_project_review_status", new_callable=AsyncMock, return_value="approved"):
                with patch("orchestrator.ExperienceManager") as MockEM:
                    em = MockEM.return_value
                    em.check_dedup = AsyncMock(return_value=[])
                    em.save_experience = AsyncMock(return_value="recEXP001")
                    em.save_to_wiki = AsyncMock(return_value="wiki/path.md")
                    await o._settle_experiences("测试项目", 0.8)

        events = bus.get_history("recTEST001")
        saved = [e for e in events if e["event_type"] == "experience.saved"]
        assert len(saved) == 1
        p = saved[0]["payload"]
        assert p["role_id"] == "account_manager"
        assert p["bitable_saved"] is True
        assert p["wiki_saved"] is True

    @pytest.mark.asyncio
    async def test_whitelist_role_always_confident(self, orch):
        """外部反馈驱动的经验置信度固定 0.85，始终高于阈值，白名单角色始终落盘。"""
        o, bus = orch
        pending = [self._make_pending("account_manager")]

        with patch.object(o, '_distill_from_feedback', AsyncMock(return_value=pending)):
            with patch.object(type(o), "_get_project_review_status", new_callable=AsyncMock, return_value="approved"):
                with patch("orchestrator.ExperienceManager") as MockEM:
                    em = MockEM.return_value
                    em.check_dedup = AsyncMock(return_value=[])
                    em.save_experience = AsyncMock(return_value="recEXP001")
                    em.save_to_wiki = AsyncMock(return_value="wiki/path.md")
                    await o._settle_experiences("测试项目", 0.0)

        events = bus.get_history("recTEST001")
        scored = [e for e in events if e["event_type"] == "experience.scored"]
        saved = [e for e in events if e["event_type"] == "experience.saved"]
        assert len(scored) == 1
        assert scored[0]["payload"]["passed"] is True
        assert len(saved) == 1

    @pytest.mark.asyncio
    async def test_settle_completed_summary(self, orch):
        o, bus = orch
        pending = [
            self._make_pending("account_manager"),
            self._make_pending("reviewer"),
        ]

        with patch.object(o, '_distill_from_feedback', AsyncMock(return_value=pending)):
            with patch.object(type(o), "_get_project_review_status", new_callable=AsyncMock, return_value="approved"):
                with patch("orchestrator.ExperienceManager") as MockEM:
                    em = MockEM.return_value
                    em.check_dedup = AsyncMock(return_value=[])
                    em.save_experience = AsyncMock(return_value="recEXP001")
                    em.save_to_wiki = AsyncMock(return_value="wiki/path.md")
                    await o._settle_experiences("测试项目", 0.8)

        events = bus.get_history("recTEST001")
        completed = [e for e in events if e["event_type"] == "experience.settle_completed"]
        assert len(completed) == 1
        p = completed[0]["payload"]
        assert p["total_distilled"] == 2
        assert p["passed_scoring"] == 2
        assert p["final_settled"] == 2
        assert p["project_name"] == "测试项目"

    @pytest.mark.asyncio
    async def test_merge_events(self, orch):
        """当触发合并时，应发 merging + merged 事件。"""
        o, bus = orch
        pending = [self._make_pending("account_manager")]

        with patch.object(o, '_distill_from_feedback', AsyncMock(return_value=pending)):
            with patch.object(type(o), "_get_project_review_status", new_callable=AsyncMock, return_value="approved"):
                with patch("orchestrator.ExperienceManager") as MockEM:
                    em = MockEM.return_value
                    em.save_experience = AsyncMock(return_value="recEXPMerged")
                    em.save_to_wiki = AsyncMock(return_value="wiki/merged.md")
                    em.optimize_bucket = AsyncMock(return_value={
                        "role_id": "account_manager",
                        "category": "电商大促",
                        "before": 4,
                        "after_dedup": 4,
                        "duplicate_pairs": 0,
                        "dedup_deleted": 0,
                        "merged_deleted": 4,
                        "merged_created": 1,
                    })
                    await o._settle_experiences("测试项目", 0.8)

        events = bus.get_history("recTEST001")
        merging = [e for e in events if e["event_type"] == "experience.merging"]
        merged = [e for e in events if e["event_type"] == "experience.merged"]
        assert len(merging) == 1
        assert merging[0]["payload"]["existing_count"] == 4
        assert len(merged) == 1
        assert merged[0]["payload"]["merged_from"] == 4
        assert merged[0]["payload"]["new_count"] == 1

    @pytest.mark.asyncio
    async def test_empty_pending_no_events(self, orch):
        o, bus = orch
        with patch.object(o, '_distill_from_feedback', AsyncMock(return_value=[])):
            await o._settle_experiences("测试项目", 0.8)
        events = bus.get_history("recTEST001")
        assert len(events) == 0


# ── 事件顺序 ──

class TestEventOrdering:
    """验证事件发布顺序。"""

    @pytest.fixture
    def orch(self):
        from dashboard.event_bus import EventBus
        from orchestrator import Orchestrator
        bus = EventBus()
        o = Orchestrator(record_id="recORDER001", event_bus=bus)
        o.stage_results = []
        o.reviewer_retries = 0
        return o, bus

    @pytest.mark.asyncio
    async def test_event_order(self, orch):
        o, bus = orch
        pending = [{
            "role_id": "account_manager",
            "card": {
                "situation": "场景", "action": "行动行动行动",
                "outcome": "结果结果",
                "lesson": "经验教训描述需要足够长度", "category": "电商大促",
                "applicable_roles": ["account_manager"],
            },
        }]
        with patch.object(o, '_distill_from_feedback', AsyncMock(return_value=pending)):
            with patch.object(type(o), "_get_project_review_status", new_callable=AsyncMock, return_value="approved"):
                with patch("orchestrator.ExperienceManager") as MockEM:
                    em = MockEM.return_value
                    em.check_dedup = AsyncMock(return_value=[])
                    em.save_experience = AsyncMock(return_value="recEXP")
                    em.save_to_wiki = AsyncMock(return_value="wiki/path.md")
                    await o._settle_experiences("测试项目", 0.8)

        events = bus.get_history("recORDER001")
        types = [e["event_type"] for e in events]
        assert types[0] == "experience.settle_started"
        assert "experience.scored" in types
        assert "experience.saved" in types
        assert types[-1] == "experience.settle_completed"
        scored_idx = types.index("experience.scored")
        saved_idx = types.index("experience.saved")
        assert scored_idx < saved_idx


# ── role_id 去重逻辑 ──

class TestFanoutExperienceDedup:
    """验证 _settle_experiences 的 role_id 去重逻辑（重构后从 (role_id, platform) 改为 role_id）。"""

    @pytest.fixture
    def orch(self):
        from dashboard.event_bus import EventBus
        from orchestrator import Orchestrator
        bus = EventBus()
        o = Orchestrator(record_id="recFANOUT001", event_bus=bus)
        o.stage_results = []
        o.reviewer_retries = 0
        return o, bus

    def _make_fanout_pending(self, platform: str) -> dict:
        return {
            "role_id": "reviewer",
            "card": {
                "situation": f"{platform}场景",
                "action": f"{platform}行动行动",
                "outcome": f"{platform}结果结果",
                "lesson": f"{platform}经验教训足够长",
                "category": "电商大促",
                "applicable_roles": ["reviewer", "copywriter"],
            },
        }

    @pytest.mark.asyncio
    async def test_same_role_deduped_to_one(self, orch):
        """同一 role_id 的多条经验去重为 1 条（保留最后一条）。"""
        o, bus = orch
        pending = [
            self._make_fanout_pending("小红书"),
            self._make_fanout_pending("抖音"),
            self._make_fanout_pending("公众号"),
        ]

        with patch.object(o, '_distill_from_feedback', AsyncMock(return_value=pending)):
            with patch.object(type(o), "_get_project_review_status", new_callable=AsyncMock, return_value="approved"):
                with patch("orchestrator.ExperienceManager") as MockEM:
                    em = MockEM.return_value
                    em.check_dedup = AsyncMock(return_value=[])
                    em.save_experience = AsyncMock(return_value="recEXP")
                    em.save_to_wiki = AsyncMock(return_value="wiki/path.md")
                    await o._settle_experiences("测试项目", 0.8)

        events = bus.get_history("recFANOUT001")
        scored = [e for e in events if e["event_type"] == "experience.scored"]
        saved = [e for e in events if e["event_type"] == "experience.saved"]
        completed = [e for e in events if e["event_type"] == "experience.settle_completed"]

        assert len(scored) == 1, f"同 role_id 应去重为 1 条，实际 {len(scored)}"
        assert len(saved) == 1, f"同 role_id 应去重为 1 条，实际 {len(saved)}"
        assert completed[0]["payload"]["total_distilled"] == 1

    @pytest.mark.asyncio
    async def test_fanout_same_platform_deduped(self, orch):
        """同一角色重复出现应去重为 1 条。"""
        o, bus = orch
        pending = [
            self._make_fanout_pending("小红书"),
            self._make_fanout_pending("小红书"),  # 重复
        ]

        with patch.object(o, '_distill_from_feedback', AsyncMock(return_value=pending)):
            with patch.object(type(o), "_get_project_review_status", new_callable=AsyncMock, return_value="approved"):
                with patch("orchestrator.ExperienceManager") as MockEM:
                    em = MockEM.return_value
                    em.check_dedup = AsyncMock(return_value=[])
                    em.save_experience = AsyncMock(return_value="recEXP")
                    em.save_to_wiki = AsyncMock(return_value="wiki/path.md")
                    await o._settle_experiences("测试项目", 0.8)

        events = bus.get_history("recFANOUT001")
        scored = [e for e in events if e["event_type"] == "experience.scored"]
        assert len(scored) == 1, f"同角色应去重为 1 条，实际 {len(scored)}"
