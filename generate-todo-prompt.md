读取项目根目录的 CLAUDE.md，基于其中的完整架构设计，生成一份详细的项目待办清单。

## 你的角色

你同时扮演三个角色完成这个任务：

### 第一轮：规划者 (Planner)
通读 CLAUDE.md 全文，把整个项目拆解为可执行的原子任务。
拆解粒度：每个任务应该是一个人在一次工作会话（30分钟-2小时）内可以完成的单元。
不要遗漏任何细节——每个文件、每个类、每个方法、每个配置项、每个测试用例都应该有对应的任务。

### 第二轮：执行者视角审查 (Executor Review)
以实际写代码的人的视角重新审查任务列表：
- 任务描述是否足够清晰，拿到就能干，不需要再问？
- 有没有遗漏的隐性依赖（比如任务 B 依赖任务 A 的产出，但没标注）？
- 有没有看起来简单但实际很复杂的任务需要拆得更细？
- 每个任务的验收标准是否明确？

### 第三轮：评估者补全 (Evaluator)
检查规划者和执行者是否遗漏了：
- 错误处理和边界情况
- 测试覆盖（每个模块是否有对应测试任务）
- 文档和配置（.env.example、README、注释）
- 演示准备（Demo 脚本、演示数据、答辩材料）
- 部署和运维（启动脚本、日志、监控）

## 输出格式

生成两个文件：

### 1. TODO.md — 人类可读的待办清单

按开发阶段组织，每个任务包含：
- 任务编号（如 P1-T03）
- 任务标题
- 详细描述（做什么、怎么做、产出物是什么）
- 涉及文件
- 依赖任务（哪些任务必须先完成）
- 验收标准（怎么判断这个任务做完了）
- 预估耗时
- 当前状态（根据项目目录中已有的文件判断：✅已完成 / 🔨进行中 / ⬜待开始）

格式示例：
```markdown
## 阶段二：Agent 框架 + 工具系统

### P2-T01: 实现 ToolRegistry 自动发现机制
- **描述**: 在 tools/__init__.py 中实现 ToolRegistry 类，启动时自动扫描 tools/ 目录下所有 .py 文件，加载每个文件的 SCHEMA 和 execute 函数，构建注册表
- **文件**: tools/__init__.py
- **依赖**: 无
- **验收**: 
  - import ToolRegistry 不报错
  - registry.list_tools() 返回所有已注册工具名
  - registry.get_tools(["read_project"]) 返回符合 OpenAI function calling 格式的 schema
  - registry.call_tool("send_message", {...}, ctx) 能执行并返回字符串
- **耗时**: 1h
- **状态**: ⬜
```

### 2. todo.json — 机器可读的结构化数据

```json
{
  "project": "飞书·智组织",
  "generated_at": "2025-xx-xx",
  "phases": [
    {
      "id": "P1",
      "name": "Bitable 共享记忆层",
      "status": "completed",
      "tasks": [
        {
          "id": "P1-T01",
          "title": "实现 TokenManager 单例",
          "description": "...",
          "files": ["feishu/auth.py"],
          "depends_on": [],
          "acceptance": ["..."],
          "estimated_hours": 1,
          "status": "completed",
          "assignee": null,
          "notes": ""
        }
      ]
    }
  ],
  "summary": {
    "total_tasks": 0,
    "completed": 0,
    "in_progress": 0,
    "pending": 0,
    "total_estimated_hours": 0
  }
}
```

## 任务拆解要求

### 必须覆盖的维度（对照 CLAUDE.md 逐项拆解）

**基础设施层**
- feishu/auth.py 的每个方法
- feishu/bitable.py 的每个方法
- feishu/im.py 的每个方法
- feishu/wiki.py 的每个方法
- config.py 的每个配置项
- .env.example

**记忆层**
- memory/project.py 的 ProjectMemory 和 ContentMemory
- memory/experience.py 的 ExperienceManager
- memory/working.py

**工具层**
- tools/__init__.py 的 ToolRegistry 和 AgentContext
- 每个工具文件（read_project / write_project / update_status / list_content / create_content / batch_create_content / write_content / search_knowledge / read_knowledge / write_wiki / send_message / get_experience）
- 每个工具的 SCHEMA 定义
- 每个工具的 execute 实现

**Agent 层**
- agents/base.py 的 BaseAgent 引擎
  - soul.md 解析（frontmatter + body）
  - _shared/ 加载
  - prompt 装配（5 层拼接）
  - ReAct 循环核心逻辑
  - Hook 自省机制
  - 经验注入
- agents/_shared/ 三个共享知识文件的内容撰写
- 五个角色的 soul.md 撰写（每个单独一个任务）

**知识库层**
- knowledge/raw/ 种子文档撰写
- knowledge/wiki/ 目录结构和初始索引
- knowledge/.sync_state.json
- sync/wiki_sync.py 后台同步线程

**编排层**
- orchestrator.py 的流水线逻辑
- 驳回重试机制
- 经验统一沉淀逻辑
- CLI 入口（main.py run）

**接入层**
- main.py webhook 服务
- 飞书事件订阅配置
- 后台 sync task 启动

**测试**
- 每个阶段的测试文件
- 测试数据准备

**演示和交付**
- Demo 演示脚本编写
- 演示用的测试 Brief 数据准备
- 答辩 PPT 素材（架构图、流程图、对比数据）
- README.md 完善

### 状态判断规则

扫描项目目录中实际存在的文件来判断状态：
- 文件存在且内容完整（不是空文件/stub）→ ✅已完成
- 文件存在但包含 stub/TODO/placeholder → 🔨进行中
- 文件不存在 → ⬜待开始
- 无法判断 → ⬜待开始（保守标注）

## 执行

1. 先读 CLAUDE.md 全文
2. 扫描项目目录结构，了解哪些文件已存在
3. 对已存在的文件，快速浏览内容判断完成度（是真实实现还是 stub）
4. 按三轮角色生成任务清单
5. 输出 TODO.md 到项目根目录
6. 输出 todo.json 到项目根目录
7. 打印汇总：总任务数 / 已完成 / 进行中 / 待开始 / 总预估工时
