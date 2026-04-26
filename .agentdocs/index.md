# .agentdocs 索引

## 架构文档
- （暂无独立架构文档，参见 `CLAUDE.md`）

## 工作流文档
- `workflow/done/250426-full-audit.md` — 全模块审计（已完成）

## 决策记录
- `ROLE_NAMES` / `safe_float` / `safe_int` / `load_soul_snippet` 统一定义在 `config.py` 和 `agents/base.py`，各模块通过 import 复用
- `ProjectMemory` 在 Orchestrator 中缓存为 `self._pm`，所有 helper 方法复用同一实例
- **飞书交付文档自动生成**：流水线完成后自动创建结构化云文档
  - `feishu/delivery_charts.py` — matplotlib 图表生成（柱状图 + 饼图），面向客户
  - `feishu/wiki.py` — `write_delivery_doc` 支持 heading/callout/table/image/divider 等 block type
  - 表格用 descendant API 一次性创建；图片用 3 步流程（创建空 Block → 上传 → 绑定）
  - 文档面向客户：不暴露审核通过率、返工次数、内部审核意见等企业内部数据
  - 开关：`DELIVERY_DOC_ENABLED` 环境变量，默认开启
  - 飞书 Docx BlockType 正确映射：table=31, table_cell=32, image=27（注意 wiki_markdown.py 中有已知偏移）
