"""环境变量、字段映射与全局常量。"""

from __future__ import annotations

import logging
import os

# 进程级 asyncio 运行时修复（Windows: ProactorEventLoop -> SelectorEventLoop）。
# 必须在任何 asyncio.run() 之前发生；放在 config.py 顶部是因为所有入口都 import config。
import _runtime  # noqa: F401 — side-effect only

from dotenv import load_dotenv

load_dotenv()

# ── 飞书应用凭证 ──
FEISHU_APP_ID: str = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET: str = os.getenv("FEISHU_APP_SECRET", "")
FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"

# ── 多维表格配置 ──
BITABLE_APP_TOKEN: str = os.getenv("BITABLE_APP_TOKEN", "")
PROJECT_TABLE_ID: str = os.getenv("PROJECT_TABLE_ID", "")
CONTENT_TABLE_ID: str = os.getenv("CONTENT_TABLE_ID", "")
EXPERIENCE_TABLE_ID: str = os.getenv("EXPERIENCE_TABLE_ID", "")
PROMOTION_REVIEW_TABLE_ID: str = os.getenv("PROMOTION_REVIEW_TABLE_ID", "")

EXPERIENCE_CONFIDENCE_THRESHOLD: float = float(os.getenv("EXPERIENCE_CONFIDENCE_THRESHOLD", "0.75"))
EXPERIENCE_MAX_PER_CATEGORY: int = int(os.getenv("EXPERIENCE_MAX_PER_CATEGORY", "3"))
EXPERIENCE_TOP_K: int = int(os.getenv("EXPERIENCE_TOP_K", "5"))

# 只有白名单内角色的经验才进入 L2 经验池（Bitable + Chroma）。
# copywriter 自评无外部验证；project_manager 产出为 LLM 通识，均不入池。
# 白名单角色的 _hook_reflect 和 _self_write_wiki 仍正常执行，只是不写到 L2。
EXPERIENCE_POOL_ROLE_ALLOWLIST: frozenset[str] = frozenset(
    s.strip() for s in os.getenv(
        "EXPERIENCE_POOL_ROLE_ALLOWLIST",
        "account_manager,strategist,reviewer",
    ).split(",") if s.strip()
)

# ── 审核流转策略 ──
REVIEW_PASS_THRESHOLD_DEFAULT: float = float(os.getenv("REVIEW_PASS_THRESHOLD_DEFAULT", "0.6"))
REVIEW_MAX_RETRIES: int = int(os.getenv("REVIEW_MAX_RETRIES", "2"))
REVIEW_RED_FLAG_KEYWORDS: list[str] = [
    item.strip() for item in os.getenv(
        "REVIEW_RED_FLAG_KEYWORDS",
        "严重合规风险,虚假宣传,绝对化用语,医疗化表述,编造数据,事实错误,严重不适配"
    ).split(",") if item.strip()
]

REVIEW_THRESHOLDS_BY_PROJECT_TYPE: dict[str, float] = {
    "电商大促": 0.6,
    "日常运营": 0.6,
    "新品发布": 0.7,
    "品牌传播": 0.7,
    "母婴": 0.8,
    "医疗健康": 0.9,
}

# ── IM / Wiki / Webhook ──
FEISHU_CHAT_ID: str = os.getenv("FEISHU_CHAT_ID", "")
WIKI_SPACE_ID: str = os.getenv("WIKI_SPACE_ID", "")
WEBHOOK_PORT: int = int(os.getenv("WEBHOOK_PORT", "8000"))
WEBHOOK_VERIFICATION_TOKEN: str = os.getenv("WEBHOOK_VERIFICATION_TOKEN", "")

# ── 交付文档自动生成 ──
DELIVERY_DOC_ENABLED: bool = os.getenv("DELIVERY_DOC_ENABLED", "true").lower() in ("true", "1", "yes")

# ── 人类审核配置 ──
AUTO_APPROVE_HUMAN_REVIEW: bool = os.getenv("AUTO_APPROVE_HUMAN_REVIEW", "false").lower() in ("true", "1", "yes")
HUMAN_REVIEW_TIMEOUT: int = int(os.getenv("HUMAN_REVIEW_TIMEOUT", "300"))
HUMAN_REVIEW_POLL_INTERVAL: int = int(os.getenv("HUMAN_REVIEW_POLL_INTERVAL", "5"))
ASK_HUMAN_TIMEOUT: int = int(os.getenv("ASK_HUMAN_TIMEOUT", "120"))

# ── 知识库配置 ──
KNOWLEDGE_BASE_PATH: str = os.getenv("KNOWLEDGE_BASE_PATH", "knowledge")

# ── Chroma 向量数据库 ──
CHROMA_DB_PATH: str = os.getenv("CHROMA_DB_PATH", ".chroma")
EXPERIENCE_SIMILARITY_DEDUP_THRESHOLD: float = float(
    os.getenv("EXPERIENCE_SIMILARITY_DEDUP_THRESHOLD", "0.85")
)

# 上行同步（本地 → 飞书）间隔，默认 1 小时
SYNC_INTERVAL: int = int(os.getenv("SYNC_INTERVAL", "3600"))

# 下行同步（飞书 → 本地）间隔，默认 30 分钟
# 01-06 是人类维护的知识，改动频率低，30min 延迟 Agent 感知不到
WIKI_DOWNLOAD_INTERVAL: int = int(os.getenv("WIKI_DOWNLOAD_INTERVAL", "1800"))

# 是否启用下行同步（默认 true；设为 false 可完全禁用拉取）
WIKI_DOWNLOAD_ENABLED: bool = os.getenv("WIKI_DOWNLOAD_ENABLED", "true").lower() in ("true", "1", "yes")

# ── LLM 配置 ──
LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o")
LLM_TIMEOUT_SECONDS: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "180"))
LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "2"))       # SDK 层内置重试数（极短抖动）
LLM_APP_MAX_RETRIES: int = int(os.getenv("LLM_APP_MAX_RETRIES", "3"))  # 应用层指数退避重试数
MAX_ROUTE_STEPS: int = int(os.getenv("MAX_ROUTE_STEPS", "15"))  # 防路由死循环安全上限
STAGE_TIMEOUT_SECONDS: float = float(os.getenv("STAGE_TIMEOUT_SECONDS", "600"))  # 单 Agent 阶段超时（秒）
IM_TIMEOUT_SECONDS: float = float(os.getenv("IM_TIMEOUT_SECONDS", "15"))  # 飞书 IM API 超时（秒）
TOOL_CB_THRESHOLD: int = int(os.getenv("TOOL_CB_THRESHOLD", "5"))      # 工具连续失败熔断阈值
TOOL_CB_RESET_SECONDS: float = float(os.getenv("TOOL_CB_RESET_SECONDS", "60"))  # 熔断自动恢复间隔（秒）

# ── L0 工作记忆（对话窗口保护）──
# max: 对话总 token 上限（按 estimate_tokens 估算）
# reserve: 给 LLM 输出留出的 token 预算（策略师批量输出时需要更大余量）
L0_MESSAGE_WINDOW_MAX_TOKENS: int = int(os.getenv("L0_MESSAGE_WINDOW_MAX_TOKENS", "40000"))
L0_MESSAGE_WINDOW_RESERVE_TOKENS: int = int(os.getenv("L0_MESSAGE_WINDOW_RESERVE_TOKENS", "4000"))

# ── 联网搜索 / 网页抓取配置（策略师专用）──
TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")
if not TAVILY_API_KEY:
    logging.getLogger(__name__).warning(
        "TAVILY_API_KEY 未配置，search_web 工具英文搜索将不可用（策略师无法搜索英文公网信息）"
    )
TAVILY_API_URL: str = os.getenv("TAVILY_API_URL", "https://api.tavily.com/search")
TAVILY_DEFAULT_MAX_RESULTS: int = int(os.getenv("TAVILY_DEFAULT_MAX_RESULTS", "5"))
TAVILY_TIMEOUT_SECONDS: float = float(os.getenv("TAVILY_TIMEOUT_SECONDS", "15"))

# ── 秘塔 AI 搜索（中文搜索引擎，覆盖小红书/美团/大众点评等中文站）──
METASO_API_KEY: str = os.getenv("METASO_API_KEY", "")
# 官方接口：https://metaso.cn/api/v1/search（注意不是 api.metaso.cn）
METASO_API_BASE: str = os.getenv("METASO_API_BASE", "https://metaso.cn/api/v1")

WEB_FETCH_MAX_CHARS_DEFAULT: int = int(os.getenv("WEB_FETCH_MAX_CHARS_DEFAULT", "10000"))
WEB_FETCH_MAX_CHARS_LIMIT: int = int(os.getenv("WEB_FETCH_MAX_CHARS_LIMIT", "50000"))
WEB_FETCH_MAX_BYTES: int = int(os.getenv("WEB_FETCH_MAX_BYTES", str(5 * 1024 * 1024)))
WEB_FETCH_TIMEOUT_SECONDS: float = float(os.getenv("WEB_FETCH_TIMEOUT_SECONDS", "10"))
WEB_FETCH_USER_AGENT: str = os.getenv(
    "WEB_FETCH_USER_AGENT",
    "FeishuSmartOrg/1.0 (+strategy-research-agent)",
)

# ── 项目主表字段映射 ──
FIELD_MAP_PROJECT = {
    "client_name": "客户名称",
    "brief": "Brief 内容",
    "project_type": "项目类型",
    "brand_tone": "品牌调性",
    "dept_style": "部门风格注入",
    "status": "状态",
    "brief_analysis": "Brief 解读",
    "strategy": "策略方案",
    "review_summary": "审核总评",
    "review_pass_rate": "审核通过率",
    "review_threshold": "审核阈值",
    "review_red_flag": "审核红线风险",
    "delivery": "交付摘要",
    "knowledge_ref": "知识引用",
    "review_status": "人审状态",
    "pending_meta": "人审元数据",
    "human_feedback": "人类修改意见",
}

# ── 内容排期表字段映射 ──
FIELD_MAP_CONTENT = {
    "project_name": "关联项目",
    "seq": "内容序号",
    "title": "内容标题",
    "platform": "目标平台",
    "content_type": "内容类型",
    "key_point": "核心卖点",
    "target_audience": "目标人群",
    "draft": "成稿内容",
    "word_count": "字数",
    "review_status": "审核状态",
    "review_feedback": "审核反馈",
    "publish_date": "计划发布日期",
    "remark": "备注",
}

# ── 经验池表字段映射 ──
FIELD_MAP_EXPERIENCE = {
    "role": "适用角色",
    "scene": "场景分类",
    "content": "经验内容",
    "confidence": "置信度",
    "use_count": "使用次数",
    "source_project": "来源项目",
    "status": "状态",
}

# ── 经验升格审批表字段映射 ──
# 对应多维表格「经验升格审批」（PROMOTION_REVIEW_TABLE_ID）
# 飞书表格需由人工手动建好，字段定义如下：
#   候选文件路径 - 文本（相对 knowledge/，如 11_待整理收件箱/电商大促/xxx.md）
#   分类         - 单选（电商大促/新品发布/品牌传播/日常运营/...）
#   适用角色     - 单选（account_manager/strategist/copywriter/reviewer/project_manager）
#   经验摘要     - 文本（正文前 300 字）
#   置信度       - 数字
#   来源项目     - 文本
#   审批状态     - 单选（待审批/通过/驳回）
#   审批备注     - 文本（审批人填写）
#   提交时间     - 日期（submit 脚本写入时自动填）
#   处理时间     - 日期（apply 脚本处理后回写）
FIELD_MAP_PROMOTION = {
    "file_path": "候选文件路径",
    "category": "分类",
    "role": "适用角色",
    "summary": "经验摘要",
    "confidence": "置信度",
    "source_project": "来源项目",
    "approval_status": "审批状态",
    "approval_note": "审批备注",
    "submitted_at": "提交时间",
    "processed_at": "处理时间",
}

# 升格审批状态枚举（单选项值必须与飞书表一致）
PROMOTION_STATUS_PENDING = "待审批"
PROMOTION_STATUS_APPROVED = "通过"
PROMOTION_STATUS_REJECTED = "驳回"

# ── 状态机常量 ──
STATUS_PENDING = "待处理"
STATUS_ANALYZING = "解读中"
STATUS_STRATEGY = "策略中"
STATUS_WRITING = "撰写中"
STATUS_REVIEWING = "审核中"
STATUS_SCHEDULING = "排期中"
STATUS_DONE = "已完成"
STATUS_REJECTED = "已驳回"
STATUS_PENDING_REVIEW = "待人审"

VALID_STATUSES = [
    STATUS_PENDING,
    STATUS_ANALYZING,
    STATUS_STRATEGY,
    STATUS_WRITING,
    STATUS_REVIEWING,
    STATUS_SCHEDULING,
    STATUS_DONE,
    STATUS_REJECTED,
    STATUS_PENDING_REVIEW,
]

# ── 人审状态字段枚举 ──
REVIEW_STATUS_PENDING = "待人审"
REVIEW_STATUS_APPROVED = "通过"
REVIEW_STATUS_NEED_REVISE = "需修改"
REVIEW_STATUS_TIMEOUT = "超时"

# ── 动态路由表（状态 → 下一角色）──
# Orchestrator 每完成一个阶段后读取项目状态，据此决定下一个 Agent
# None 表示路由终止（流水线结束或挂起）
ROUTE_TABLE: dict[str, str | None] = {
    STATUS_PENDING: "account_manager",
    STATUS_ANALYZING: "account_manager",
    STATUS_PENDING_REVIEW: "__human_review_gate__",  # 特殊标记：进入人审门禁
    STATUS_STRATEGY: "strategist",
    STATUS_WRITING: "copywriter",
    STATUS_REVIEWING: "reviewer",
    STATUS_SCHEDULING: "project_manager",
    STATUS_DONE: None,
    STATUS_REJECTED: None,
}

# 路由终止状态集合（命中即结束流水线主循环）
ROUTE_TERMINAL_STATUSES: set[str] = {STATUS_DONE, STATUS_REJECTED}

# ── 角色名称映射（Agent role_id → 中文展示名）──
ROLE_NAMES: dict[str, str] = {
    "account_manager": "客户经理",
    "strategist": "策略师",
    "copywriter": "文案",
    "reviewer": "审核",
    "project_manager": "项目经理",
    "data_analyst": "数据分析师",
}


# ── 通用安全类型转换 ──
def safe_float(val) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def safe_int(val) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0
