"""工具: 读取 knowledge/05_标准模板/ 下的结构化模板。

供 Agent 按统一模板产出 Brief 解读 / 策略 / 文案 / 审核 / 复盘 等，
避免每次自由发挥导致上下游字段对不上。

设计考量：
- name 参数支持中文短名（如「策略」），内部映射到 "策略模板.md"
- 也支持直接传文件名（如「项目复盘模板」），去掉 .md 后缀
- 文件不存在时返回错误提示 + 可用列表，便于 Agent 自纠正
"""

from pathlib import Path

from tools import AgentContext
from config import KNOWLEDGE_BASE_PATH

_TEMPLATE_DIR = "05_标准模板"

# 短名 → 模板文件名（含扩展名）
_ALIASES: dict[str, str] = {
    "brief": "Brief 解读模板.md",
    "brief解读": "Brief 解读模板.md",
    "brief 解读": "Brief 解读模板.md",
    "策略": "策略模板.md",
    "文案": "文案模板.md",
    "审核": "审核模板.md",
    "客户档案": "客户档案模板.md",
    "项目档案": "项目档案模板.md",
    "项目复盘": "项目复盘模板.md",
    "经验卡": "经验卡模板.md",
}


SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_template",
        "description": (
            "读取标准模板文档，按统一结构产出 Brief 解读 / 策略 / 文案 / 审核 / 复盘 等。"
            "name 支持短名（策略、文案、审核、brief、项目复盘、经验卡、客户档案、项目档案）"
            "或完整文件名。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "模板短名或文件名，如 '策略' / '文案' / 'Brief 解读模板'",
                },
            },
            "required": ["name"],
        },
    },
}


def _list_available(template_dir: Path) -> list[str]:
    return sorted(p.stem for p in template_dir.glob("*.md") if not p.name.startswith("_"))


def _resolve_filename(name: str, template_dir: Path) -> Path | None:
    """把用户传入的 name 解析为一个确切的模板文件路径。"""
    key = name.strip()
    if not key:
        return None

    # 1) 别名精确匹配（小写）
    aliased = _ALIASES.get(key.lower())
    if aliased:
        p = template_dir / aliased
        if p.exists():
            return p

    # 2) 直接当文件名（补 .md）
    if not key.lower().endswith(".md"):
        p = template_dir / f"{key}.md"
        if p.exists():
            return p

    # 3) 作为完整文件名
    p = template_dir / key
    if p.exists() and p.suffix == ".md":
        return p

    # 4) 模糊匹配：stem 包含子串
    for md in template_dir.glob("*.md"):
        if key in md.stem:
            return md
    return None


async def execute(params: dict, context: AgentContext) -> str:
    name = (params.get("name") or "").strip()
    if not name:
        return "错误: name 不能为空，请传模板短名如 '策略'"

    base = Path(KNOWLEDGE_BASE_PATH) / _TEMPLATE_DIR
    if not base.exists():
        return f"错误: 模板目录不存在 — {_TEMPLATE_DIR}/"

    target = _resolve_filename(name, base)
    if not target:
        available = _list_available(base)
        alias_hint = "、".join(sorted(_ALIASES.keys())[:6])
        return (
            f"未找到模板「{name}」。可用文件：\n"
            + "\n".join(f"- {t}" for t in available)
            + f"\n\n也可用别名：{alias_hint}"
        )

    try:
        content = target.read_text(encoding="utf-8")
    except Exception as e:
        return f"错误: 读取模板失败 — {e}"

    rel = target.relative_to(Path(KNOWLEDGE_BASE_PATH)).as_posix()
    return f"[来源: {rel}]\n\n{content}"
