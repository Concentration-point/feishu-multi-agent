"""BaseAgent — 配置驱动的 Agent 引擎。

加载 soul.md + 共享知识 → 装配 system prompt → ReAct 工具调用循环。
所有角色复用同一个 Python 类，行为差异全部由 soul.md 配置决定。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncio

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)

from config import (
    LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_MAX_RETRIES, LLM_APP_MAX_RETRIES,
    LLM_TIMEOUT_SECONDS, EXPERIENCE_TOP_K,
    L0_MESSAGE_WINDOW_MAX_TOKENS, L0_MESSAGE_WINDOW_RESERVE_TOKENS,
)
from memory.project import ProjectMemory
from memory.experience import ExperienceManager
from memory.working import MessageWindow
from tools import ToolRegistry, AgentContext

logger = logging.getLogger(__name__)

# 项目根目录 / agents 目录
_AGENTS_DIR = Path(__file__).parent

# ── 角色专用自省 prompt（按 role_id 分化）──

_DEFAULT_REFLECT_PROMPT = (
    "你刚完成了一项工作。回顾你的整个执行过程（包括你调用了哪些工具、"
    "得到了什么结果、遇到了什么问题），用以下 JSON 格式总结一条可复用的经验：\n\n"
    "{\n"
    '  "situation": "你面对的具体任务场景",\n'
    '  "action": "你采取的关键策略或方法",\n'
    '  "outcome": "结果如何",\n'
    '  "lesson": "下次遇到类似场景，最重要的一条具体可执行的建议",\n'
    '  "category": "电商大促|新品发布|品牌传播|日常运营",\n'
    '  "applicable_roles": ["当前角色ID"]\n'
    "}\n\n"
    "要求：\n"
    "- lesson 必须具体可执行，不要空泛建议\n"
    "- situation 要足够具体\n"
    "- 只输出 JSON，不要任何其他文字"
)

_ACCOUNT_MANAGER_REFLECT_PROMPT = (
    "你刚完成了一轮 Brief 解读，并接受了人类专家的审核。回顾这次经历：\n\n"
    "1. 你初版 Brief 解读漏掉了什么或误解了什么？\n"
    "2. 人类审核给了什么修改意见？背后的判断依据是什么？\n"
    "3. 归纳出一条「下次遇到类似客户时的 Brief 解读模式」\n\n"
    "输出 JSON（只输出 JSON，不要任何其他文字）:\n"
    "{\n"
    '  "situation": "某客户类型的 Brief 解读",\n'
    '  "human_correction": "人类指出的关键修正点",\n'
    '  "reasoning": "为什么人类会这样修正",\n'
    '  "action": "你的解读策略",\n'
    '  "outcome": "是否被人类采纳",\n'
    '  "lesson": "当客户说 [X] 时，通常意思是 [Y]，需要追问 [Z]",\n'
    '  "category": "电商大促|新品发布|品牌传播|日常运营",\n'
    '  "applicable_roles": ["account_manager"]\n'
    "}\n\n"
    "要求：\n"
    "- human_correction 必须具体记录人类的修改点，如果人类直接通过则写「无修改」\n"
    "- reasoning 要分析人类修正背后的思维方式\n"
    "- lesson 必须是具体可复用的解读模式，不是「注意沟通」这种废话\n"
    "- 如果人类未给出修改，也要总结你这次解读中做得好的策略"
)

_REVIEWER_REFLECT_PROMPT = (
    "你刚完成了一轮审核工作。回顾这次审核过程，输出一条可复用的审核经验。\n\n"
    "输出 JSON：\n"
    "{\n"
    '  "situation": "某品类/某平台的内容审核场景",\n'
    '  "violations_found": ["发现的违规类型1", "违规类型2"],\n'
    '  "action": "你如何基于规则库进行审核",\n'
    '  "outcome": "审核通过率和整体结果",\n'
    '  "lesson": "下次文案在撰写这类内容前必须预先检查什么",\n'
    '  "category": "电商大促|新品发布|品牌传播|日常运营",\n'
    '  "applicable_roles": ["reviewer", "copywriter"]  // 必须保持此固定值，不要修改\n'
    "}\n\n"
    "要求：\n"
    "- lesson 必须具体到可执行检查项，不要空泛\n"
    "- violations_found 必须尽量落到具体违规模式\n"
    "- applicable_roles 固定为 [\"reviewer\", \"copywriter\"]，不允许输出其他值\n"
    "- 只输出 JSON，不要其他文字"
)

_COPYWRITER_REFLECT_PROMPT = (
    "你刚完成了一轮文案撰写。回顾你这次的【对标 + 规则】双轨学习过程：\n\n"
    "1. 轨道A：你调 search_reference 搜了哪些爆款？共性是什么？你复用了哪些元素？\n"
    "2. 轨道B：你调 search_knowledge 查了哪些规则？本轮规避了哪些禁用词/平台红线？\n"
    "3. 对标与规则是否有冲突？你如何化解？\n"
    "4. 归纳一条「对标 + 规则」融合的可复用套路\n\n"
    "输出 JSON（只输出 JSON，不要任何其他文字）:\n"
    "{\n"
    '  "situation": "某平台某品类的文案撰写场景",\n'
    '  "reference_pattern": "爆款共性规律（hook/structure/cta 具体模式）",\n'
    '  "rule_check": "本轮查到的规则红线 + 已规避的禁用词/平台限制",\n'
    '  "conflict_handling": "对标元素与规则冲突的化解方式（如 hook 里的违规措辞如何合法替代）",\n'
    '  "action": "你如何融合对标与规则进行创作",\n'
    '  "outcome": "成稿质量 + 合规自检结果",\n'
    '  "lesson": "下次撰写同类内容时，先搜 [爆款关键词] 再查 [规则关键词]，套用 [结构]，避免 [具体红线]",\n'
    '  "category": "电商大促|新品发布|品牌传播|日常运营",\n'
    '  "applicable_roles": ["copywriter"]\n'
    "}\n\n"
    "要求：\n"
    "- reference_pattern 具体到可模仿的结构骨架，不是空话\n"
    "- rule_check 必须列出实际命中的规则文件名 + 至少 1 条已规避的违规模式\n"
    "- conflict_handling 如果本轮无冲突写「无冲突」，但要说明如何确认无冲突\n"
    "- lesson 必须可操作，覆盖「搜什么 → 查什么 → 怎么写 → 避什么」完整闭环\n"
    "- 如果本轮未调 search_reference 或 search_knowledge（违规），lesson 必须自我检讨"
)

_ROLE_REFLECT_PROMPTS: dict[str, str] = {
    "account_manager": _ACCOUNT_MANAGER_REFLECT_PROMPT,
    "reviewer": _REVIEWER_REFLECT_PROMPT,
    "copywriter": _COPYWRITER_REFLECT_PROMPT,
}

# ── 角色必调工具（代码级硬约束，prompt 偏航时兜底）──
# 如果 ReAct 结束后这些工具未被调用，post-validation 会注入指令要求 LLM 补全
_REQUIRED_TOOL_CALLS: dict[str, list[str]] = {
    # account_manager 的人审已改由 Orchestrator 门禁驱动，不再依赖 Agent 自调工具
    # 文案走「对标 + 规则」双轨：search_reference 拿爆款套路，
    # search_knowledge 查禁用词/平台规范，二者缺一不可
    "copywriter": ["search_reference", "search_knowledge"],
    # reviewer 必须用 submit_review 写回审核结论（结构化五维校验），
    # 同时必须调 search_knowledge 驱动语义层规则检索
    "reviewer": ["search_knowledge", "submit_review"],
}

# post-validation 每轮最多注入此轮次；超过后打 warning 不阻塞
_POST_VALIDATION_ROUNDS = 2
_POST_VALIDATION_MINI_ITERS = 3

# 空 turn 检测：LLM 产出无 tool_use 且无 text 时，最多重试注入此轮次
_MAX_EMPTY_TURN_RETRIES = 2


@dataclass
class SoulConfig:
    """从 soul.md YAML frontmatter 解析出的配置。"""
    name: str
    role_id: str
    description: str
    tools: list[str]
    max_iterations: int
    body: str  # Markdown 正文


@dataclass
class AgentResult:
    """Result object for isolated single-agent unit execution."""
    role_id: str
    output: str
    messages: list[dict]
    tool_calls: list[dict]
    missing_required_tools: list[str]
    meta: dict[str, Any]


def parse_soul(text: str) -> SoulConfig:
    """解析 soul.md：--- YAML frontmatter --- + Markdown body。"""
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("soul.md 格式错误：缺少 --- 分隔的 frontmatter")

    frontmatter_raw = parts[1].strip()
    body = parts[2].strip()

    # 简单的 YAML 解析（不依赖 PyYAML）
    fm: dict[str, Any] = {}
    current_key = ""
    current_list: list[str] | None = None

    for line in frontmatter_raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # 列表项: "  - value"
        if stripped.startswith("- ") and current_key:
            if current_list is None:
                current_list = []
            current_list.append(stripped[2:].strip())
            fm[current_key] = current_list
            continue

        # key: value
        if ":" in stripped:
            # 先保存之前的列表
            current_list = None
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            current_key = key
            if val:
                # 尝试转数字
                try:
                    fm[key] = int(val)
                except ValueError:
                    fm[key] = val
            else:
                fm[key] = None

    return SoulConfig(
        name=fm.get("name", ""),
        role_id=fm.get("role_id", ""),
        description=fm.get("description", ""),
        tools=fm.get("tools", []) if isinstance(fm.get("tools"), list) else [],
        max_iterations=fm.get("max_iterations", 10),
        body=body,
    )


def load_soul_snippet(role_id: str, max_chars: int = 500) -> str:
    """加载角色 soul.md 核心描述片段（跳过 frontmatter，返回正文前 max_chars 字）。

    轻量版本，供外部模块注入角色人格上下文。
    """
    soul_path = _AGENTS_DIR / role_id / "soul.md"
    if not soul_path.exists():
        return ""
    try:
        text = soul_path.read_text(encoding="utf-8")
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                text = parts[2]
        return text.strip()[:max_chars]
    except Exception:
        return ""


# ── 平台专属 soul 追加式合成（扫描式发现，零硬编码白名单）──
#
# 任何角色只要在 agents/{role_id}/platforms/ 下有 {platform}.md 就会触发补丁。
# 零硬编码：新增 role 的平台分化，只需建目录放 md，无需改 Python 代码。


def _role_has_platform_patches(role_id: str) -> bool:
    """检查 agents/{role_id}/platforms/ 是否存在（有补丁目录即视为支持分化）。"""
    return (_AGENTS_DIR / role_id / "platforms").is_dir()


def load_soul_with_platform_patch(
    role_id: str,
    platform: str | None,
) -> tuple[SoulConfig, bool]:
    """加载基础 soul 并按 platform 追加平台补丁。

    合成规则（扫描式发现，无硬编码白名单）：
      - 仅当 role 下存在 platforms/ 目录且 platform 非空时走补丁逻辑
      - 补丁文件路径：agents/{role_id}/platforms/{platform}.md（纯 Markdown，无 frontmatter）
      - 存在 → 基础 body + 显式分隔符 + 补丁内容；返回 (patched_soul, True)
      - 不存在 → 打 WARNING 日志；返回 (base_soul, False) —— 软兜底
      - platforms/ 目录不存在 or platform 为空 → 直接返回 (base_soul, False)

    工具清单（frontmatter.tools）完全沿用基础 soul，平台补丁不改工具权限。
    """
    soul_path = _AGENTS_DIR / role_id / "soul.md"
    if not soul_path.exists():
        raise FileNotFoundError(f"找不到 {soul_path}")
    base_soul = parse_soul(soul_path.read_text(encoding="utf-8"))

    # 无 platform 或角色无 platforms/ 目录 → 直接返回基础 soul
    if not platform or not _role_has_platform_patches(role_id):
        return base_soul, False

    patch_path = _AGENTS_DIR / role_id / "platforms" / f"{platform}.md"
    if not patch_path.exists():
        logger.warning(
            "[%s] 平台 %s 无专属补丁（未找到 %s），使用基础 %s soul 软兜底",
            role_id, platform, patch_path.name, role_id,
        )
        return base_soul, False

    try:
        patch_body = patch_path.read_text(encoding="utf-8").strip()
    except Exception as e:
        logger.warning(
            "[%s] 读取平台补丁失败 platform=%s err=%s，软兜底",
            role_id, platform, e,
        )
        return base_soul, False

    if not patch_body:
        logger.warning(
            "[%s] 平台补丁为空文件 platform=%s，软兜底",
            role_id, platform,
        )
        return base_soul, False

    separator = "\n\n---\n\n# 🎯 平台专属补充：{}\n\n".format(platform)
    merged_body = base_soul.body + separator + patch_body

    patched_soul = SoulConfig(
        name=base_soul.name,
        role_id=base_soul.role_id,
        description=base_soul.description,
        tools=list(base_soul.tools),
        max_iterations=base_soul.max_iterations,
        body=merged_body,
    )
    logger.info(
        "[%s] 平台专属 soul 合成完成 platform=%s base=%d+patch=%d chars",
        role_id, platform, len(base_soul.body), len(patch_body),
    )
    return patched_soul, True


# ── 共享知识分层加载（方案B：语义角色映射）──

# 所有 Agent 都需要的公司级底座（02_服务方法论 按角色细分，不再全量灌入）
_COMMON_KNOWLEDGE_DIRS: tuple[str, ...] = (
    "01_企业底座",
)

# 02_服务方法论 中所有角色共需的文件
_COMMON_METHOD_FILES: tuple[str, ...] = (
    "内容生产主流程.md",
    "项目类型SOP补充.md",
)

# 02_服务方法论 中按 role_id 细分的文件（不在此列的角色只拿 _COMMON_METHOD_FILES）
_ROLE_METHOD_FILES: dict[str, tuple[str, ...]] = {
    "account_manager": ("Brief 解读规则.md",),
    "copywriter":      ("事实核查要点.md", "品牌调性检查清单.md", "广告法禁用词.md"),
    "reviewer":        ("事实核查要点.md", "品牌调性检查清单.md", "广告法禁用词.md",
                        "审核规则与风险边界.md", "质量红线标准.md"),
}

# 按 role_id 额外附加的知识目录
_ROLE_KNOWLEDGE_DIRS: dict[str, tuple[str, ...]] = {
    "strategist": ("04_平台打法",),
    "copywriter": ("04_平台打法",),
    "reviewer":   ("04_平台打法",),
}


def _load_dir_markdown(kb_root: Path, rel_dir: str) -> list[str]:
    """读取 kb_root/rel_dir 下所有 .md 文件（跳过 README/_index）。"""
    target = kb_root / rel_dir
    if not target.exists() or not target.is_dir():
        return []
    parts: list[str] = []
    for md in sorted(target.rglob("*.md")):
        name = md.name
        if name.lower() == "readme.md" or name.startswith("_"):
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except Exception:
            continue
        rel = md.relative_to(kb_root).as_posix()
        parts.append(f"<!-- source: {rel} -->\n{text}")
    return parts


def _load_method_files(kb_root: Path, filenames: tuple[str, ...]) -> list[str]:
    """精确加载 02_服务方法论/ 下的指定文件。"""
    method_dir = kb_root / "02_服务方法论"
    if not method_dir.exists():
        return []
    parts: list[str] = []
    for name in filenames:
        md = method_dir / name
        if not md.exists():
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except Exception:
            continue
        rel = md.relative_to(kb_root).as_posix()
        parts.append(f"<!-- source: {rel} -->\n{text}")
    return parts


def load_shared_knowledge(role_id: str | None = None) -> str:
    """加载分层知识：公共底座（01）+ 02方法论按角色精确选取 + 角色专属目录。

    - 01_企业底座：全量加载（所有角色共享）
    - 02_服务方法论：公共文件（内容生产主流程 + 项目类型SOP）+ 角色专属文件
    - 04_平台打法等：按 _ROLE_KNOWLEDGE_DIRS 追加
    - 兜底：若新分层空则回读旧 agents/_shared/*.md
    """
    from config import KNOWLEDGE_BASE_PATH
    kb_root = Path(KNOWLEDGE_BASE_PATH).resolve()

    parts: list[str] = []

    # 1) 公共目录（01_企业底座）
    for d in _COMMON_KNOWLEDGE_DIRS:
        parts.extend(_load_dir_markdown(kb_root, d))

    # 2) 02_服务方法论：公共文件 + 角色专属文件
    method_files = list(_COMMON_METHOD_FILES)
    if role_id and role_id in _ROLE_METHOD_FILES:
        method_files.extend(_ROLE_METHOD_FILES[role_id])
    parts.extend(_load_method_files(kb_root, tuple(method_files)))

    # 3) 角色专属目录（04_平台打法 等）
    if role_id and role_id in _ROLE_KNOWLEDGE_DIRS:
        for d in _ROLE_KNOWLEDGE_DIRS[role_id]:
            parts.extend(_load_dir_markdown(kb_root, d))

    # 兜底：新分层为空时回退到旧 _shared/
    if not parts:
        legacy_dir = _AGENTS_DIR / "_shared"
        if legacy_dir.exists():
            for md in sorted(legacy_dir.glob("*.md")):
                if md.name.lower() == "readme.md":
                    continue
                parts.append(md.read_text(encoding="utf-8"))

    return "\n\n---\n\n".join(parts)


def load_formal_experiences(category: str | None = None) -> str:
    """加载 knowledge/10_经验沉淀/ 下的正式经验全文。

    - category=None：加载全部正式经验
    - category="电商大促"：只加载 10_经验沉淀/电商大促/ 下的文件
    - 11_待整理收件箱/ 的脏经验**不**在此读取（收件箱是缓冲区）
    """
    from config import KNOWLEDGE_BASE_PATH
    kb_root = Path(KNOWLEDGE_BASE_PATH).resolve()
    formal_dir = kb_root / "10_经验沉淀"
    if not formal_dir.exists():
        return ""
    target = formal_dir / category if category else formal_dir
    if not target.exists():
        return ""
    parts: list[str] = []
    for md in sorted(target.rglob("*.md")):
        if md.name.lower() == "readme.md" or md.name.startswith("_"):
            continue
        try:
            parts.append(md.read_text(encoding="utf-8"))
        except Exception:
            continue
    return "\n\n---\n\n".join(parts)


class BaseAgent:
    """通用 Agent 引擎。

    用法:
        agent = BaseAgent(role_id="account_manager", record_id="recXXX")
        result = await agent.run()
    """

    # 角色 ID → 中文名映射
    _ROLE_NAMES: dict[str, str] = {
        "account_manager": "客户经理",
        "strategist": "策略师",
        "copywriter": "文案",
        "reviewer": "审核",
        "project_manager": "项目经理",
        "data_analyst": "数据分析师",
    }

    def __init__(
        self,
        role_id: str,
        record_id: str,
        event_bus=None,
        task_filter: dict | None = None,
        *,
        tool_registry: ToolRegistry | None = None,
        llm_client: Any | None = None,
        shared_knowledge: str | None = None,
        project_memory_factory: Any | None = None,
    ):
        self.role_id = role_id
        self.record_id = record_id
        self._event_bus = event_bus
        # task_filter: fan-out 子任务过滤器，如 {"platform": "小红书"}
        # 用于 copywriter 按 platform 并行分组 — 注入 user_msg 引导 LLM 只处理子集
        # 目前仅识别 platform 键，未来可扩展 category 等
        self._task_filter: dict = task_filter or {}

        # 加载 soul.md（支持按 task_filter.platform 追加平台专属补丁）
        platform_for_patch = (task_filter or {}).get("platform")
        self.soul, self._platform_patch_used = load_soul_with_platform_patch(
            role_id, platform_for_patch,
        )

        # 加载共享知识（按角色分层装配）
        self.shared_knowledge = (
            load_shared_knowledge(role_id)
            if shared_knowledge is None
            else shared_knowledge
        )

        # 工具注册
        self._registry = tool_registry or ToolRegistry()
        self._tools_config = self._registry.get_tools(self.soul.tools)
        self._project_memory_factory = project_memory_factory or ProjectMemory

        # LLM 客户端
        self._llm = llm_client or AsyncOpenAI(
            base_url=LLM_BASE_URL,
            api_key=LLM_API_KEY,
            timeout=LLM_TIMEOUT_SECONDS,
            max_retries=LLM_MAX_RETRIES,
            default_headers={"User-Agent": "Mozilla/5.0"},
        )

        # 经验暂存（Hook 蒸馏后自主写入 wiki，也供 Orchestrator 写 Bitable）
        self._pending_experience: dict | None = None
        # 标记 Agent 是否已自主完成 wiki 写入
        self._wiki_written: bool = False
        # 空 turn 计数（防 LLM reasoning 后不产出 tool_use 也不产出 text）
        self._empty_turn_count: int = 0
        # 标记 Agent 是否调用了人机交互工具（ask_human / ask_human_batch）
        self._used_ask_human: bool = False
        # ReAct 对话历史（供 Hook 回顾）
        self._messages: list[dict] = []
        logger.info(
            "[%s] LLM client ready model=%s base_url=%s timeout=%ss retries=%s",
            self.soul.name,
            LLM_MODEL,
            LLM_BASE_URL,
            LLM_TIMEOUT_SECONDS,
            LLM_MAX_RETRIES,
        )

    def _publish(self, event_type: str, payload: dict | None = None, *, round_num: int = 0) -> None:
        """安全发布事件到 EventBus，失败不影响主流程。

        若当前 Agent 有 task_filter（fan-out 子 agent），自动将 filter 注入 payload，
        前端可据此将 swim lane 细分到 agent_role + task_filter.platform 粒度。
        """
        if self._event_bus is None:
            return
        try:
            merged_payload = dict(payload or {})
            if self._task_filter:
                # 不覆盖已有字段，避免上游误传
                merged_payload.setdefault("task_filter", dict(self._task_filter))
                # 平台补丁元信息（dashboard 展示平台标签 / 兜底告警）
                # 仅当 task_filter 里有 platform 才注入，避免污染其他 role 事件
                patch_platform = self._task_filter.get("platform")
                if patch_platform:
                    # 用 getattr 防御：现有 mock 测试用 object.__new__ 绕过 __init__
                    # 不会设 _platform_patch_used，此时视为未用补丁（兜底）
                    patch_used = getattr(self, "_platform_patch_used", False)
                    if patch_used:
                        merged_payload.setdefault("platform_patch", patch_platform)
                    else:
                        merged_payload.setdefault("fallback_used", True)
            self._event_bus.publish(
                self.record_id,
                event_type,
                merged_payload,
                agent_role=self.role_id,
                agent_name=self._ROLE_NAMES.get(self.role_id, self.role_id),
                round_num=round_num,
            )
        except Exception:
            pass

    def _build_unit_system_prompt(
        self,
        strategy: dict[str, Any],
        context: dict[str, Any],
    ) -> str:
        """Build a prompt for isolated single-agent tests without pipeline state."""
        sections: list[str] = []
        if self.shared_knowledge:
            sections.append("# Shared knowledge\n\n" + self.shared_knowledge)
        sections.append(
            f"# Role soul\n\n"
            f"- name: {self.soul.name}\n"
            f"- role_id: {self.soul.role_id}\n"
            f"- description: {self.soul.description}\n\n"
            f"{self.soul.body}"
        )
        if strategy:
            sections.append(
                "# Explicit strategy\n\n"
                + json.dumps(strategy, ensure_ascii=False, indent=2)
            )
        if context:
            sections.append(
                "# Explicit context\n\n"
                + json.dumps(context, ensure_ascii=False, indent=2, default=str)
            )

        # 输出规则（强制）—— 与 _build_system_prompt 对齐
        sections.append(
            "# 输出规则（强制）\n\n"
            "你的每一次响应必须包含以下至少一项：\n"
            "1. 至少一个工具调用（tool_use）—— 执行一个具体动作\n"
            "2. 一段面向用户的文本回复 —— 汇报进展或说明情况\n\n"
            "严格禁止：\n"
            "- 在思考中完成分析后，不产出任何 tool_use 或文本就结束\n"
            '- 认为"已经想清楚了"就等于"已经做了"\n\n'
            "如果你不确定下一步该做什么，也必须输出一段文本说明你的困惑，而不是静默结束。"
        )

        return "\n\n---\n\n".join(sections)

    @staticmethod
    def _build_unit_user_prompt(input_data: str) -> str:
        return "# Input\n\n" + (input_data or "")

    async def run_unit(
        self,
        input_data: str,
        strategy: dict | None = None,
        context: dict | None = None,
    ) -> AgentResult:
        """Run one soul-driven agent with explicit input/context/strategy only.

        This path is intended for unit tests. It does not load ProjectMemory,
        does not enter the pipeline, and does not run reflection/wiki hooks.
        """
        strategy = strategy or {}
        context = context or {}
        tool_context = AgentContext(
            record_id=str(context.get("record_id") or self.record_id),
            project_name=str(
                context.get("project_name")
                or context.get("client_name")
                or self.role_id
            ),
            role_id=self.role_id,
        )
        messages: list[dict] = [
            {
                "role": "system",
                "content": self._build_unit_system_prompt(strategy, context),
            },
            {"role": "user", "content": self._build_unit_user_prompt(input_data)},
        ]
        tool_calls: list[dict] = []
        final_output = ""

        for iteration in range(1, self.soul.max_iterations + 1):
            response = await self._llm_call(
                messages,
                stage="unit_react_loop",
                iteration=iteration,
            )
            message = response.choices[0].message
            messages.append(message.model_dump())

            if not message.tool_calls:
                content = message.content or ""
                if not content.strip():
                    # 空 turn 检测（unit 路径）
                    self._empty_turn_count += 1
                    logger.warning(
                        "[%s] unit 第%d轮 → 空 turn，第 %d/%d 次重试",
                        self.soul.name, iteration,
                        self._empty_turn_count, _MAX_EMPTY_TURN_RETRIES,
                    )
                    if self._empty_turn_count <= _MAX_EMPTY_TURN_RETRIES:
                        messages.append({
                            "role": "user",
                            "content": (
                                "⚠️ [系统检测] 你的上一次响应没有产出任何工具调用或文本回复。"
                                "请重新审视当前状态，并明确执行一个动作（调用工具）"
                                "或输出一段文本（汇报当前进展/说明困惑）。"
                            ),
                        })
                        continue
                    final_output = (
                        f"[WARNING:empty_turn_retries_exceeded="
                        f"{self._empty_turn_count}/{_MAX_EMPTY_TURN_RETRIES}]"
                    )
                    break
                final_output = content
                break

            for tc in message.tool_calls:
                fn_name = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    fn_args = {}
                result = await self._registry.call_tool(fn_name, fn_args, tool_context)
                from memory.cost_tracker import cost_tracker as _ct
                _ct.record_tool_call(self.record_id, self.role_id, fn_name, iteration)
                tool_calls.append(
                    {
                        "tool_name": fn_name,
                        "arguments": fn_args,
                        "result": result,
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    }
                )
        else:
            final_output = messages[-1].get("content", "") if messages else ""

        missing = self._check_required_tools(messages)
        self._messages = messages
        return AgentResult(
            role_id=self.role_id,
            output=final_output,
            messages=messages,
            tool_calls=tool_calls,
            missing_required_tools=missing,
            meta={
                "mode": "unit",
                "soul_name": self.soul.name,
                "record_id": tool_context.record_id,
                "project_name": tool_context.project_name,
            },
        )

    async def run(
        self,
        input_data: str | None = None,
        strategy: dict | None = None,
        context: dict | None = None,
    ) -> str | AgentResult:
        """执行 Agent 的完整 ReAct 循环。"""
        if input_data is not None or strategy is not None or context is not None:
            return await self.run_unit(input_data or "", strategy, context)

        # 1. 加载项目上下文（独立 Agent 如数据分析师无对应记录时兜底）
        try:
            pm = self._project_memory_factory(self.record_id)
            proj = await pm.load()
        except Exception:
            logger.info("[%s] 无对应项目记录，使用空上下文", self.soul.name)
            proj = BriefProject(record_id=self.record_id)

        context = AgentContext(
            record_id=self.record_id,
            project_name=proj.client_name or self.role_id,
            role_id=self.role_id,
        )

        # 2. 加载历史经验
        experience_text = await self._load_experiences(proj.project_type)

        # 3. 装配 system prompt
        system_prompt = self._build_system_prompt(proj, experience_text)

        # 4. 构造初始消息
        if proj.client_name:
            user_msg_parts = [
                "请开始处理以下项目:",
                f"- 客户名称: {proj.client_name}",
                f"- 项目类型: {proj.project_type}",
                f"- 当前状态: {proj.status}",
                f"- record_id: {self.record_id}",
            ]
        else:
            user_msg_parts = [
                "请开始执行你的工作任务。",
                f"- record_id: {self.record_id}",
            ]
        # fan-out 子 agent 注入 platform 约束 — 强制 LLM 只处理自己负责的 platform 子集
        platform_filter = (self._task_filter or {}).get("platform")
        if platform_filter:
            user_msg_parts.append("")
            user_msg_parts.append(
                f"【并行分组约束】本次你只负责 platform=「{platform_filter}」的内容，"
                f"其他平台由其他子 Agent 并行处理，不要越权处理其他平台的行。"
            )
            user_msg_parts.append(
                f'- 调 list_content 时必须传入 platform="{platform_filter}" 只拉取自己的 rows'
            )
            user_msg_parts.append(
                "- 处理完 platform 子集后即可结束，不要等待/影响其他平台"
            )
        # fan-out 子 agent 注入 content_rows — 精确限定负责的内容行，避免全表读
        content_rows = (self._task_filter or {}).get("content_rows")
        if content_rows:
            user_msg_parts.append("")
            user_msg_parts.append(
                f"【内容行分配】你只负责以下 {len(content_rows)} 条内容行，"
                f"不要处理其他行（其他行由其他子 Agent 并行处理）："
            )
            for cr in content_rows:
                user_msg_parts.append(
                    f"  - record_id={cr['record_id']} | 平台={cr.get('platform', '?')}"
                    f" | 类型={cr.get('content_type', '?')}"
                    f" | 标题={cr.get('title', '?')}"
                    f" | 卖点={cr.get('key_point', '?')}"
                    f" | 人群={cr.get('target_audience', '?')}"
                )
            user_msg_parts.append(
                "- 如果 list_content 返回了其他行，忽略它们，只写上述 record_id 对应的行"
            )
        # 数据分析师注入报告类型约束
        report_type = (self._task_filter or {}).get("report_type")
        if report_type:
            _REPORT_TYPE_NAMES = {
                "weekly": "运营周报",
                "insight": "数据洞察",
                "decision": "决策建议",
            }
            user_msg_parts.append("")
            user_msg_parts.append(
                f"【报告类型】请生成一份「{_REPORT_TYPE_NAMES.get(report_type, report_type)}」"
                f"（report_type={report_type}）。"
            )
        user_msg_parts.append("")
        user_msg_parts.append("请按照你的工作流程逐步执行。")
        user_msg = "\n".join(user_msg_parts)

        # L0 工作记忆：用 MessageWindow 做对话窗口保护
        # 每轮 LLM 调用前 trim，避免长对话/大工具返回撑爆上下文
        window = MessageWindow(
            max_tokens=L0_MESSAGE_WINDOW_MAX_TOKENS,
            reserve_tokens=L0_MESSAGE_WINDOW_RESERVE_TOKENS,
        )
        window.append({"role": "system", "content": system_prompt})
        window.append({"role": "user", "content": user_msg})

        self._publish("agent.started", {
            "project_name": proj.client_name,
            "project_type": proj.project_type,
            "max_iterations": self.soul.max_iterations,
        })

        # 5. ReAct 循环
        final_output = ""
        for iteration in range(1, self.soul.max_iterations + 1):
            # 每轮 LLM 调用前 trim：按 assistant+tool 组整体丢弃最早对话
            pre_trim = window.total_tokens()
            window.trim()
            post_trim = window.total_tokens()
            if post_trim < pre_trim:
                logger.info(
                    "[%s] 第%d轮 → 窗口裁剪 %d→%d tokens（保留 %d 条消息）",
                    self.soul.name, iteration, pre_trim, post_trim, len(window.messages),
                )

            response = await self._llm_call(window.messages, stage="react_loop", iteration=iteration)
            message = response.choices[0].message

            # 有工具调用
            if message.tool_calls:
                # 将 assistant message（含 tool_calls）加入历史
                window.append(message.model_dump())

                # 如果 LLM 同时返回了文本思考内容，发布 thinking 事件
                if message.content:
                    self._publish("agent.thinking", {
                        "content": message.content,
                    }, round_num=iteration)

                for tc in message.tool_calls:
                    fn_name = tc.function.name
                    try:
                        fn_args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        fn_args = {}

                    logger.info(
                        "[%s] 第%d轮 → 调用工具 %s(%s)",
                        self.soul.name, iteration, fn_name,
                        ", ".join(f"{k}={v!r}" for k, v in fn_args.items()),
                    )

                    self._publish("tool.called", {
                        "tool_name": fn_name,
                        "arguments": fn_args,
                    }, round_num=iteration)

                    result = await self._registry.call_tool(
                        fn_name, fn_args, context
                    )

                    from memory.cost_tracker import cost_tracker as _ct
                    _ct.record_tool_call(self.record_id, self.role_id, fn_name, iteration)

                    if fn_name in ("ask_human", "ask_human_batch"):
                        self._used_ask_human = True

                    self._publish("tool.returned", {
                        "tool_name": fn_name,
                        "result": result[:300] if result else "",
                    }, round_num=iteration)

                    window.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })
            else:
                # 无工具调用 → 检查是否为空 turn
                content = message.content or ""
                window.append(message.model_dump())
                if not content.strip():
                    # 空 turn: 模型在 reasoning 中完成了思考但没有产出
                    self._empty_turn_count += 1
                    logger.warning(
                        "[%s] 第%d轮 → 空 turn（无 tool_use 且无文本），"
                        "第 %d/%d 次重试",
                        self.soul.name, iteration,
                        self._empty_turn_count, _MAX_EMPTY_TURN_RETRIES,
                    )
                    self._publish("agent.empty_turn", {
                        "iteration": iteration,
                        "empty_turn_count": self._empty_turn_count,
                    }, round_num=iteration)
                    if self._empty_turn_count <= _MAX_EMPTY_TURN_RETRIES:
                        window.append({
                            "role": "user",
                            "content": (
                                "⚠️ [系统检测] 你的上一次响应没有产出任何工具调用或文本回复。"
                                "请重新审视当前状态，并明确执行一个动作（调用工具）"
                                "或输出一段文本（汇报当前进展/说明困惑）。"
                                "你在思考中的分析用户和系统都看不到——必须显式输出。"
                            ),
                        })
                        continue
                    # 超过重试上限，强制截断
                    final_output = (
                        f"[WARNING:empty_turn_retries_exceeded="
                        f"{self._empty_turn_count}/{_MAX_EMPTY_TURN_RETRIES}]"
                    )
                    break

                # 有文本 → 正常最终输出
                final_output = content

                self._publish("agent.thinking", {
                    "content": final_output[:500],
                }, round_num=iteration)

                logger.info(
                    "[%s] 第%d轮 → 输出最终结果，循环结束",
                    self.soul.name, iteration,
                )
                break
        else:
            # 达到最大迭代次数，截断输出并加标记，让 Orchestrator 可感知
            logger.warning(
                "[%s] 达到最大迭代次数 %d，强制结束，输出可能不完整",
                self.soul.name, self.soul.max_iterations,
            )
            raw = window.messages[-1].get("content", "") if window.messages else ""
            final_output = f"[TRUNCATED:max_iterations={self.soul.max_iterations}] {raw}"

        messages = window.messages

        # 6. 必调工具 post-validation（代码级硬约束）
        # ReAct 循环结束后检查必调工具；缺失则注入补全指令并继续 LLM 对话，
        # 每轮注入一次，最多 _POST_VALIDATION_ROUNDS 轮；达上限后打 warning 不阻塞。
        missing = self._check_required_tools(messages)
        for _pv in range(_POST_VALIDATION_ROUNDS):
            if not missing:
                break
            logger.info(
                "[%s] post-validation 第%d/%d轮：缺少必调工具 %s，注入补全指令",
                self.soul.name, _pv + 1, _POST_VALIDATION_ROUNDS, missing,
            )
            self._publish("agent.post_validation", {"missing_tools": missing, "round": _pv + 1})
            # reviewer 场景补充逐行提示，避免只调一次就结束
            if self.role_id == "reviewer" and "submit_review" in missing:
                extra = "\n对每一条内容行必须独立调用一次 submit_review（不能合并处理），调用时须填写全部 dimensions 五个字段。"
            else:
                extra = ""
            window.append({
                "role": "user",
                "content": (
                    f"⚠️ 工具合规校验：你在本次工作中还未调用必须工具 {missing}。\n"
                    f"请立即调用这些工具完成必要操作，然后输出最终结论。{extra}"
                ),
            })
            # mini-loop：tool call → tool result → final text（最多 _POST_VALIDATION_MINI_ITERS 步）
            for _pv_iter in range(_POST_VALIDATION_MINI_ITERS):
                try:
                    resp = await self._llm_call(
                        window.messages, stage="post_validation", iteration=_pv_iter + 1,
                    )
                    pv_msg = resp.choices[0].message
                    window.append(pv_msg.model_dump())
                    if pv_msg.tool_calls:
                        for tc in pv_msg.tool_calls:
                            fn_name = tc.function.name
                            try:
                                fn_args = json.loads(tc.function.arguments)
                            except json.JSONDecodeError:
                                fn_args = {}
                            result = await self._registry.call_tool(fn_name, fn_args, context)
                            from memory.cost_tracker import cost_tracker as _ct
                            _ct.record_tool_call(self.record_id, self.role_id, fn_name, 0)
                            window.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                    else:
                        final_output = pv_msg.content or final_output
                        break  # LLM 已给出最终文本，mini-loop 结束
                except Exception as _pv_exc:
                    logger.warning(
                        "[%s] post-validation 第%d轮 mini-iter %d 失败: %s",
                        self.soul.name, _pv + 1, _pv_iter + 1, _pv_exc,
                    )
                    break
            messages = window.messages
            missing = self._check_required_tools(messages)

        if missing:
            logger.warning("[%s] post-validation 后仍缺少必调工具: %s", self.soul.name, missing)
            final_output += (
                f"\n\n⚠️ 合规警告：本次执行未调用必需工具 {missing}，输出可能未经必要审核流程。"
            )

        # 7. 保存对话历史供 Hook 使用
        self._messages = messages

        # 8. Hook: 自省蒸馏 + 自主写入 wiki（不影响主流程）
        try:
            experience_card = await self._hook_reflect(messages)
            if experience_card:
                self._pending_experience = experience_card
                logger.info(
                    "[%s] Hook 蒸馏完成: %s",
                    self.soul.name, experience_card.get("lesson", "")[:80],
                )
                self._publish("experience.distilled", {
                    "role_id": self.role_id,
                    "category": experience_card.get("category", "未分类"),
                    "lesson": str(experience_card.get("lesson", ""))[:80],
                    "applicable_roles": experience_card.get("applicable_roles", []),
                })
                # 自主写入本地 wiki
                await self._self_write_wiki(experience_card, context)
            else:
                logger.warning("[%s] Hook 蒸馏失败或解析错误", self.soul.name)
        except Exception as e:
            logger.warning("[%s] Hook 异常: %s", self.soul.name, e)

        self._publish("agent.completed", {
            "output_length": len(final_output),
        })

        return final_output

    def _check_required_tools(self, messages: list[dict]) -> list[str]:
        """检查 ReAct 历史中是否调用了当前角色的必需工具，且调用未以错误结束。

        局限：只检查工具是否被调用过至少一次（不检查 per-row 覆盖率，
        那需要在 Orchestrator 层读取内容行数后做额外校验）。

        Returns:
            缺失或全部结果为错误的工具名列表，空列表表示全部满足。
        """
        required = _REQUIRED_TOOL_CALLS.get(self.role_id, [])
        if not required:
            return []

        # 第一遍：收集所有 assistant 工具调用，建立 call_id→tool_name 映射
        called: set[str] = set()
        tc_id_to_name: dict[str, str] = {}
        for msg in messages:
            if not isinstance(msg, dict) or msg.get("role") != "assistant":
                continue
            for tc in msg.get("tool_calls") or []:
                if isinstance(tc, dict):
                    fn_name = tc.get("function", {}).get("name", "")
                    tc_id = tc.get("id", "")
                    called.add(fn_name)
                    if tc_id and fn_name:
                        tc_id_to_name[tc_id] = fn_name

        # 第二遍：检查工具结果 — 如果某必调工具的全部结果都以"错误:"开头，
        # 视为未有效调用（等同于没调用）
        # 注：仅当某工具 100% 结果为错误时才认为"缺失"，部分成功则放行
        tool_error_counts: dict[str, int] = {}
        tool_total_counts: dict[str, int] = {}
        for msg in messages:
            if not isinstance(msg, dict) or msg.get("role") != "tool":
                continue
            tc_id = msg.get("tool_call_id", "")
            tool_name = tc_id_to_name.get(tc_id, "")
            if not tool_name or tool_name not in required:
                continue
            content = msg.get("content", "")
            tool_total_counts[tool_name] = tool_total_counts.get(tool_name, 0) + 1
            if isinstance(content, str) and content.startswith("错误:"):
                tool_error_counts[tool_name] = tool_error_counts.get(tool_name, 0) + 1

        # 全部结果均为错误的工具，等同于未有效调用
        all_failed: set[str] = {
            t for t in required
            if tool_total_counts.get(t, 0) > 0
            and tool_error_counts.get(t, 0) == tool_total_counts.get(t, 0)
        }

        return [t for t in required if t not in called or t in all_failed]

    async def _load_experiences(self, project_type: str) -> str:
        """从两源加载历史经验拼为 prompt 段落：
        - L1a：Bitable 经验池 top-K（排序 + 使用次数累计）
        - L1b：knowledge/10_经验沉淀/{category}/ 正式区全文（升格后的高质经验）
        - 11_待整理收件箱/ 的脏经验**不**进 prompt，避免污染
        """
        lines: list[str] = []
        bitable_count = 0

        # L1a：Bitable top-K
        try:
            em = ExperienceManager()
            experiences = await em.query_top_k(
                self.role_id, category=project_type, k=EXPERIENCE_TOP_K
            )
            if experiences:
                bitable_count = len(experiences)
                lines.append("## 过往高分经验（基于 Bitable 经验池 top-K）")
                lines.append("以下是你在类似场景中积累的经验，请参考但不要机械照搬：")
                for i, exp in enumerate(experiences, 1):
                    cat = exp.get("category", "")
                    lesson = exp.get("lesson", "")
                    lines.append(f"{i}. [{cat}] {lesson}")
        except Exception as e:
            logger.warning("[%s] 加载 Bitable 经验失败: %s", self.soul.name, e)

        # L1b：10_经验沉淀/ 正式经验全文
        formal_loaded = False
        try:
            formal = load_formal_experiences(category=project_type) if project_type else ""
            if formal:
                if lines:
                    lines.append("")
                lines.append("## 正式沉淀经验（knowledge/10_经验沉淀/）")
                lines.append(formal)
                formal_loaded = True
        except Exception as e:
            logger.warning("[%s] 加载正式经验失败: %s", self.soul.name, e)

        # 发布经验加载事件供 Dashboard 可视化
        if lines:
            self._publish("experience.loaded", {
                "role_id": self.role_id,
                "bitable_count": bitable_count,
                "formal_loaded": formal_loaded,
                "category": project_type or "未分类",
            })

        return "\n".join(lines)

    async def _hook_reflect(self, messages: list[dict]) -> dict | None:
        """Hook 自省：回顾 ReAct 过程，蒸馏一条可复用经验。

        按 role_id 使用不同的自省 prompt，让每个角色聚焦自己最有价值的经验维度。
        """
        reflect_prompt = _ROLE_REFLECT_PROMPTS.get(self.role_id, _DEFAULT_REFLECT_PROMPT)

        # 构造自省对话：复用 ReAct 历史 + 追加自省指令
        reflect_messages = messages.copy()
        reflect_messages.append({"role": "user", "content": reflect_prompt})

        try:
            resp = await self._llm_call(
                reflect_messages,
                with_tools=False,
                stage="reflect",
            )
            raw = resp.choices[0].message.content or ""
            # 清理可能的 markdown 代码块包裹
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
            cleaned = cleaned.strip()

            card = json.loads(cleaned)
            # 字段规范化 + 兜底
            _VALID_CATEGORIES = {"电商大促", "新品发布", "品牌传播", "日常运营"}
            card.setdefault("situation", "")
            card.setdefault("action", "")
            card.setdefault("outcome", "")
            card.setdefault("lesson", "")
            if card.get("category") not in _VALID_CATEGORIES:
                card["category"] = "未分类"
            # 确保 applicable_roles 包含当前角色；审核经验还必须反哺文案
            if not isinstance(card.get("applicable_roles"), list):
                card["applicable_roles"] = [self.role_id]
            elif self.role_id not in card["applicable_roles"]:
                card["applicable_roles"].insert(0, self.role_id)
            if self.role_id == "reviewer" and "copywriter" not in card["applicable_roles"]:
                card["applicable_roles"].append("copywriter")
            logger.info(
                "[%s] Hook 经验适用角色: %s",
                self.soul.name, card.get("applicable_roles"),
            )
            return card
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("[%s] Hook JSON 解析失败: %s", self.soul.name, e)
            return None

    def _build_wiki_title(self, lesson: str) -> str:
        """基于规整化 lesson 生成去重友好的 wiki 文件名。

        规整化：移除所有空白 + 非字母数字中文字符，并转小写。
        - 前 20 字作为人眼可读前缀（保留原始 lesson 里的可见字符，不做规整化）
        - 规整化全文的 md5 前 8 位作为短指纹，决定唯一性
        同语义仅标点不同的 lesson 会落到同一 fingerprint → 同文件名 → 覆盖写入。
        """
        normalized = re.sub(r"[\s\W_]+", "", lesson).lower()
        if not normalized:
            normalized = lesson
        fingerprint = hashlib.md5(normalized.encode("utf-8")).hexdigest()[:8]
        human_prefix = lesson[:20].strip() or "经验"
        return f"{self.role_id}_{human_prefix}_{fingerprint}"

    async def _self_write_wiki(self, card: dict, context: AgentContext) -> None:
        """Agent 自主将经验卡片写入本地 wiki，实现自检闭环。

        文件命名策略（修复隐患2）：
          {role_id}_{规整化前20字}_{规整化全文md5前8位}
        规整化会去掉所有标点/空白并小写，使得"仅标点或空白差异"的同语义 lesson
        命中同一文件名 → write_wiki 覆盖写入 → 自动去重，不再堆积近重复文件。
        """
        category = card.get("category", "未分类")
        lesson = card.get("lesson", "")
        if not lesson:
            return

        # 构造 wiki 内容：SAOL 格式
        content_parts = []
        if card.get("situation"):
            content_parts.append(f"## 场景\n{card['situation']}")
        if card.get("action"):
            content_parts.append(f"## 策略\n{card['action']}")
        if card.get("outcome"):
            content_parts.append(f"## 结果\n{card['outcome']}")
        if lesson:
            content_parts.append(f"## 经验教训\n{lesson}")
        content_parts.append(f"\n> 来源角色: {self.role_id}")

        title = self._build_wiki_title(lesson)

        try:
            result = await self._registry.call_tool(
                "write_wiki",
                {"category": category, "title": title, "content": "\n\n".join(content_parts)},
                context,
            )
            self._wiki_written = True
            logger.info("[%s] 自主写入 wiki 完成: %s", self.soul.name, result)
        except Exception as e:
            logger.warning("[%s] 自主写入 wiki 失败: %s", self.soul.name, e)

    def _build_system_prompt(self, proj, experience_text: str = "") -> str:
        """装配完整的 system prompt。"""
        sections = []

        # 共享知识
        if self.shared_knowledge:
            sections.append(
                "# 公司共享知识\n\n" + self.shared_knowledge
            )

        # Soul prompt
        sections.append(
            f"# 你的角色配置\n\n"
            f"- 角色: {self.soul.name}\n"
            f"- 职责: {self.soul.description}\n\n"
            f"{self.soul.body}"
        )

        # 项目上下文
        ctx_parts = [
            "# 当前项目上下文",
            f"- 品牌调性: {proj.brand_tone}" if proj.brand_tone else None,
            f"- 部门风格注入: {proj.dept_style}" if proj.dept_style else None,
            f"- 项目类型: {proj.project_type}" if proj.project_type else None,
        ]
        sections.append("\n".join(p for p in ctx_parts if p))

        # 上一轮人类审核反馈注入（AM 恢复重跑时专用，其他角色一般为空）
        human_feedback = (getattr(proj, "human_feedback", "") or "").strip()
        if human_feedback and self.role_id == "account_manager":
            sections.append(
                "# 上一轮人类审核反馈（必须在本轮解读中采纳）\n\n"
                f"> {human_feedback}\n\n"
                "请基于原 Brief 和上面这段反馈重新生成《Brief 解读报告》，"
                "并在最终输出中明确说明你采纳了哪些建议、做了哪些修订。"
            )

        # 历史经验注入
        if experience_text:
            sections.append(
                "# 历史经验（基于过往项目积累）\n\n" + experience_text
            )

        # 输出规则（强制）—— 防静默 turn + thinking 边界
        sections.append(
            "# 输出规则（强制）\n\n"
            "你的每一次响应必须包含以下至少一项：\n"
            "1. 至少一个工具调用（tool_use）—— 执行一个具体动作\n"
            "2. 一段面向用户的文本回复 —— 汇报进展或说明情况\n\n"
            "严格禁止：\n"
            "- 在思考中完成分析后，不产出任何 tool_use 或文本就结束\n"
            "- 在思考中想好了要问的问题，但没有实际输出给用户\n"
            '- 认为"已经想清楚了"就等于"已经做了"\n\n'
            "如果你不确定下一步该做什么，也必须输出一段文本说明你的困惑，而不是静默结束。\n\n"
            "【Thinking 边界说明】你的思考/推理过程用户完全看不到。"
            "你需要用户知道的任何信息，必须明确写在文本回复中。"
            "思考中「想到要追问」不等于已经追问了，思考中「决定调工具」不等于已经调用了。"
            "思考是草稿纸——观众只看舞台上发生的事。"
        )

        return "\n\n---\n\n".join(sections)

    @staticmethod
    def _approx_message_chars(messages: list[dict]) -> int:
        total = 0
        for message in messages:
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if isinstance(content, str):
                total += len(content)
            elif content is not None:
                total += len(json.dumps(content, ensure_ascii=False))
        return total

    async def _llm_call(
        self,
        messages: list[dict],
        *,
        with_tools: bool = True,
        stage: str = "chat",
        iteration: int | None = None,
    ) -> Any:
        """调用 LLM，叠加应用层指数退避重试以吸收网络抖动。

        SDK 内置 `max_retries` 只覆盖极短抖动；这里再加一层抓手，
        把 `APIConnectionError` / `APITimeoutError` 做最多 3 次指数退避重试，
        且把代理环境变量打进日志，便于定位是否为本地 proxy 抽风。
        """
        kwargs: dict[str, Any] = {
            "model": LLM_MODEL,
            "messages": messages,
        }
        if with_tools and self._tools_config:
            kwargs["tools"] = self._tools_config

        max_attempts = LLM_APP_MAX_RETRIES
        # RateLimitError 需要更长等待；连接/超时/5xx 用较短退避
        backoff_seconds = [2, 4, 8]
        rate_limit_backoff = [5, 15, 30]

        for attempt in range(1, max_attempts + 1):
            try:
                response = await self._llm.chat.completions.create(**kwargs)
                if response.usage:
                    from memory.cost_tracker import cost_tracker
                    cost_tracker.record(
                        record_id=self.record_id,
                        role_id=self.role_id,
                        stage=stage,
                        model=LLM_MODEL,
                        prompt_tokens=response.usage.prompt_tokens or 0,
                        completion_tokens=response.usage.completion_tokens or 0,
                        iteration=iteration,
                    )
                return response
            except (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError) as exc:
                is_last = attempt == max_attempts
                is_rate_limit = isinstance(exc, RateLimitError)
                proxy_env = {
                    "http_proxy": os.getenv("http_proxy") or os.getenv("HTTP_PROXY") or "",
                    "https_proxy": os.getenv("https_proxy") or os.getenv("HTTPS_PROXY") or "",
                    "no_proxy": os.getenv("no_proxy") or os.getenv("NO_PROXY") or "",
                }
                level = logger.error if is_last else logger.warning
                level(
                    "[%s] LLM %s stage=%s iteration=%s attempt=%d/%d model=%s base_url=%s "
                    "timeout=%ss sdk_retries=%s proxy=%s messages=%d approx_chars=%d err=%s",
                    self.soul.name,
                    type(exc).__name__,
                    stage,
                    iteration,
                    attempt,
                    max_attempts,
                    LLM_MODEL,
                    LLM_BASE_URL,
                    LLM_TIMEOUT_SECONDS,
                    LLM_MAX_RETRIES,
                    proxy_env,
                    len(messages),
                    self._approx_message_chars(messages),
                    exc,
                )
                if is_last:
                    raise
                backoff = rate_limit_backoff if is_rate_limit else backoff_seconds
                delay = backoff[attempt - 1]
                logger.info(
                    "[%s] LLM 重试前等待 %ds（应用层第 %d/%d 次，%s）",
                    self.soul.name, delay, attempt, max_attempts - 1, type(exc).__name__,
                )
                await asyncio.sleep(delay)

    @property
    def system_prompt_preview(self) -> dict:
        """返回 system prompt 的结构预览（用于调试）。"""
        # 需要一个 proj 对象来构建，用空值代替
        from memory.project import BriefProject
        dummy = BriefProject(record_id="preview")
        full = self._build_system_prompt(dummy)
        sections = full.split("\n\n---\n\n")
        return {
            "total_chars": len(full),
            "sections": [
                {
                    "title": s.split("\n")[0][:60],
                    "chars": len(s),
                }
                for s in sections
            ],
        }
