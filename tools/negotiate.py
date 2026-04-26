"""Tool: record an inter-agent clarification or negotiation request.

This tool is intentionally local-only. It gives soul.md files a registered
function for role-to-role clarification without writing to Feishu, databases,
or pipeline state.
"""

from __future__ import annotations

from tools import AgentContext


SCHEMA = {
    "type": "function",
    "function": {
        "name": "negotiate",
        "description": "Record a clarification, coordination, or negotiation message for another role. This does not write external state.",
        "parameters": {
            "type": "object",
            "properties": {
                "target_role": {
                    "type": "string",
                    "description": "Role that should receive the clarification or coordination request.",
                },
                "topic": {
                    "type": "string",
                    "description": "Short topic of the negotiation.",
                },
                "message": {
                    "type": "string",
                    "description": "Concrete question, clarification, or coordination note.",
                },
                "blocking": {
                    "type": "boolean",
                    "description": "Whether this issue blocks the current agent from continuing.",
                },
            },
            "required": ["target_role", "message"],
        },
    },
}


async def execute(params: dict, context: AgentContext) -> str:
    target_role = str(params.get("target_role") or "unknown")
    topic = str(params.get("topic") or "clarification")
    message = str(params.get("message") or "").strip()
    blocking = bool(params.get("blocking", False))

    return (
        "协商记录\n"
        f"- from_role: {context.role_id}\n"
        f"- to_role: {target_role}\n"
        f"- project: {context.project_name}\n"
        f"- topic: {topic}\n"
        f"- blocking: {blocking}\n"
        f"- message: {message}"
    )
