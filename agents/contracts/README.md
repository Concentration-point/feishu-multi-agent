# Agent Contracts

本目录定义多智能体角色的**结构化交付契约（contract）**。

## 目标
让每个 Agent 不只产出给人看的自然语言结果，还产出给系统消费的结构化结果。

也就是说：
- 飞书文档 / 多维表格文本 / 群聊消息 = 展示层
- contract JSON = 控制层

后续 orchestrator、workflow guard、状态机推进，应优先基于 contract 判断，而不是基于一段自然语言总结拍脑袋。

## 设计原则
1. 所有角色共用统一外壳（见 `base_contract.json`）
2. 每个角色在 `output` 中定义自己的专属交付结构
3. 每个角色都必须明确：
   - 是否执行成功
   - 是否允许进入下一阶段
   - 阻塞问题是什么
4. 自然语言结果可继续写入 Bitable / 文档，但不作为流程推进唯一依据

## 当前文件
- `base_contract.json`：统一 contract 外壳示例
- `account_manager.contract.json`
- `strategist.contract.json`
- `copywriter.contract.json`
- `reviewer.contract.json`
- `project_manager.contract.json`

## 推荐后续动作
1. 让 BaseAgent 在最终轮支持输出 contract JSON
2. 让 orchestrator 读取 contract 而不是只看文本字段
3. 让 reviewer / workflow guard 基于 contract 做阶段拦截

一句话：

**多 Agent 要像组织，不像群聊；contract 就是组织里的交接单。**
