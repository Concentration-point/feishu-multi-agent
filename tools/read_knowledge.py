"""工具: 读取知识库文档全文"""

from pathlib import Path
from tools import AgentContext
from config import KNOWLEDGE_BASE_PATH

SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_knowledge",
        "description": "读取知识库中指定文档的完整内容。路径从 search_knowledge 的搜索结果中获取。",
        "parameters": {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "相对于 knowledge/ 的文件路径，如 'raw/某美妆品牌618电商营销全案.md'",
                },
            },
            "required": ["filepath"],
        },
    },
}


async def execute(params: dict, context: AgentContext) -> str:
    filepath = params.get("filepath", "").strip()
    if not filepath:
        return "错误: filepath 不能为空"

    # 安全校验：拒绝路径穿越
    if ".." in filepath or filepath.startswith("/") or filepath.startswith("\\"):
        return "错误: 非法路径，不允许包含 '..' 或使用绝对路径"

    base = Path(KNOWLEDGE_BASE_PATH).resolve()
    full_path = (base / filepath).resolve()

    # 确保解析后的路径仍在知识库目录内（基于路径结构判断，非字符串前缀）
    if not full_path.is_relative_to(base):
        return "错误: 路径越界，只能读取知识库内的文件"

    if not full_path.exists():
        return f"错误: 文件不存在 — {filepath}"

    if not full_path.is_file():
        return f"错误: 路径不是文件 — {filepath}"

    try:
        content = full_path.read_text(encoding="utf-8")
    except Exception as e:
        return f"错误: 读取文件失败 — {e}"

    if len(content) > 3000:
        return content[:3000] + "\n\n...（内容过长，已截取前 3000 字）"

    return content
