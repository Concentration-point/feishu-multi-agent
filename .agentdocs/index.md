# .agentdocs 索引

## 架构文档
- （暂无独立架构文档，参见 `CLAUDE.md`）

## 工作流文档
- `workflow/done/250426-full-audit.md` — 全模块审计（已完成）

## 决策记录
- `ROLE_NAMES` / `safe_float` / `safe_int` / `load_soul_snippet` 统一定义在 `config.py` 和 `agents/base.py`，各模块通过 import 复用
- `ProjectMemory` 在 Orchestrator 中缓存为 `self._pm`，所有 helper 方法复用同一实例
