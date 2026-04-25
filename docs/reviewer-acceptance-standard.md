# 审核 Agent 验收标准

## 一、模块目标

审核 Agent 的目标是把“主观审核”升级为“规则驱动审核”。

具体要求：

1. 审核前能够检索规则库
2. 审核时能够引用规则依据
3. 审核反馈能够指出问题原文和修改建议
4. 审核经验能够沉淀，并可反哺文案 Agent
5. 关键测试过程有日志，有可展示截图

---

## 二、验收范围

本次验收聚焦以下能力：

### 1. 规则库能力

- 能检索到广告法禁用词
- 能检索到平台规范
- 能检索到品牌调性检查清单
- 能检索到事实核查要点

### 2. 审核规则引用能力

- `reviewer` 的 prompt 中明确要求先查规则再审核
- 对“需修改 / 驳回”内容，反馈中必须包含：
  - 规则依据
  - 问题原文
  - 修改建议

### 3. 经验沉淀能力

- reviewer 的 hook 能生成审核经验
- `applicable_roles` 中必须包含：
  - `reviewer`
  - `copywriter`

### 4. 展示材料能力

- 有测试日志
- 有前后对比截图
- 可用于飞书汇报

---

## 三、运行命令

### 1. 规则库自检

```bash
python tests/test_reviewer_rules.py
```

### 2. Python 语法检查

```bash
python -m py_compile agents/base.py
```

---

## 四、输入数据

### 规则库文件

位于：

```text
knowledge/raw/rules/
```

至少包含：

```text
广告法禁用词.md
平台规范.md
品牌调性检查清单.md
事实核查要点.md
```

### 测试查询词

包括但不限于：

```text
禁用词 美妆
小红书 规范
品牌调性 检查
事实核查 数据 来源
```

---

## 五、预期输出

### 1. 规则库自检成功

运行：

```bash
python tests/test_reviewer_rules.py
```

预期输出中应包含：

```text
RESULT: PASS
```

并且日志中应能看到：

- 搜索规则关键词
- 命中规则文件
- 成功读取规则正文

### 2. reviewer/soul.md 验收通过

文件中应明确体现：

- 审核前必须先检索规则
- 需修改 / 驳回必须引用规则依据
- 禁止“感觉不太对”“再优化一下”这类模糊反馈

### 3. agents/base.py 验收通过

代码中应明确体现：

- reviewer 有专用 reflect prompt
- reviewer 的经验卡片包含违规模式总结
- reviewer 经验默认反哺 copywriter

即最终经验卡片中：

```json
"applicable_roles": ["reviewer", "copywriter"]
```

### 4. 展示材料验收通过

需要具备以下材料：

#### 日志文件

```text
artifacts/reviewer-rules-test.log
```

#### 前后对比图

```text
artifacts/reviewer-before-after-v4.png
```

---

## 六、通过标准

满足以下条件即视为审核 Agent 验收通过：

1. `tests/test_reviewer_rules.py` 真实运行成功
2. 输出结果为 `RESULT: PASS`
3. 规则库文件齐全且可检索、可读取
4. `agents/reviewer/soul.md` 已改为规则驱动审核逻辑
5. `agents/base.py` 中 reviewer hook 已支持经验反哺 copywriter
6. 已产生日志文件
7. 已产出前后对比截图

---

## 七、失败判定

出现以下任一情况，视为验收不通过：

1. 测试脚本运行失败
2. 未出现 `RESULT: PASS`
3. 规则库搜索不到对应规则文件
4. `agents/reviewer/soul.md` 仍然允许模糊主观反馈
5. reviewer hook 未包含 `copywriter`
6. 没有日志文件
7. 没有前后对比截图

---

## 八、交叉测试要求

开发者本人写完模块后，不能直接自己宣布通过。

必须由另外一个 Agent 或另一位同学按上述验收标准独立测试，重点检查：

1. 命令是否能真实运行
2. 输出是否符合预期
3. 日志是否真实生成
4. 展示图是否与代码改动一致
5. 是否存在“只改展示、不改逻辑”的假通过情况

---

## 九、交付物清单

最终需要提交：

```text
agents/reviewer/soul.md
agents/base.py
knowledge/raw/rules/广告法禁用词.md
knowledge/raw/rules/平台规范.md
knowledge/raw/rules/品牌调性检查清单.md
knowledge/raw/rules/事实核查要点.md
tests/test_reviewer_rules.py
artifacts/reviewer-rules-test.log
artifacts/reviewer-before-after-v4.png
```

---

## 十、一句话结论模板

验收通过时可写：

```text
审核 Agent 已完成规则驱动化改造。规则库检索与读取测试已真实跑通（RESULT: PASS），reviewer 已支持基于规则的审核反馈和经验反哺 copywriter，日志与前后对比材料已生成，满足本轮验收标准。
```
