"""Orchestrator 流水线子模块。

按职责拆分自原 orchestrator.py，使主编排器保持薄主循环。
所有模块函数以 Orchestrator 实例为首参数，保持外部 API 与原方法语义一致：
  - routing             状态读取、初始化、动态路由、人审门禁、交接校验、收尾
  - stage_runner        单阶段执行、超时、必调工具校验、checkpoint 清理
  - copywriter_fanout   文案 fan-out 分组、并行执行、定向重试、draft 兜底补写
  - review_flow         审核通过率/红线/返工/强制推进/自动 summary
  - delivery            飞书知识空间交付文档生成
  - experience_settlement 经验蒸馏、置信度、Bitable/Chroma/Wiki 落盘、evolution_log
"""
