# DeckForge PPT SOP

> 目标：把 PPT 当成“可编辑视觉系统”，不是把内容贴进模板。吸收 ppt-master 的强项：串行流水线、spec_lock、page_rhythm、SVG→PPTX、质量闸门；保留我们的优势：可控生图、学术材料理解、公式/图示安全渲染。

## 0. 安全边界

- 不直接安装未知 skill，不执行仓库脚本，除非老大明确批准。
- 对外部 PPT skill 先做只读学习和风险扫描。
- 源文件、生成物、图片资产默认留在本地 workspace。

## 1. 输入处理 Source Digest

输入可以是 PDF / DOCX / URL / Markdown / 图片 / 表格。

必须产出：

```text
source_digest.md
- 论文/材料基本信息
- 核心问题
- 方法/论证结构
- 关键数据/图表
- 可用于 PPT 的事实块
- 不确定/需核对项
```

## 2. Deck Brief

先确认或默认以下项：

```text
用途：课堂汇报 / 答辩 / 商务 / 方案 / 培训
时长：例如 15 分钟
页数：例如 15 页
受众：老师/同学/专家/老板/客户
核心信息：观众听完必须记住什么
风格：学术简洁 / 咨询 / 科技 / 发布会 / 杂志
输出：PPTX / PDF / 图片预览 / 讲稿
```

## 3. Eight Confirmations（一次性确认）

借鉴 ppt-master，但压缩成一屏：

1. Canvas：默认 16:9
2. Page Count：按时长和材料复杂度建议
3. Audience & Occasion：受众和场景
4. Style Objective：通用视觉 / 咨询逻辑 / 顶咨结论先行
5. Color Scheme：主色、辅助色、强调色，最多 4 色
6. Icon Approach：只选一个图标体系
7. Typography：PPT 安全字体，中文默认 Microsoft YaHei
8. Image Approach：用户图 / AI 生图 / 图表 / 公式图块

确认后进入自动执行，不再每步追问。

## 4. Design Spec + spec_lock

每个项目必须生成两份文件：

```text
design_spec.md      # 人看的设计说明
spec_lock.md        # 机器执行锁
```

spec_lock 必须锁定：

```text
colors:
  primary:
  secondary:
  accent:
  background:
typography:
  title_family:
  body_family:
  body_size:
icons:
  library:
  inventory:
images:
  style_anchor:
page_rhythm:
  P01: anchor
  P02: dense
  P03: dense
  P04: breathing
```

## 5. Page Rhythm：解决“每页都像卡片模板”的问题

每页必须标记节奏：

- `anchor`：封面、目录、章节、结尾
- `dense`：信息密集页，默认用于课堂/论文汇报
- `breathing`：重点结论页，可留白，但必须有强视觉锚点

论文课堂汇报默认：

```text
anchor: 1, 15
breathing: 2, 13, 15
其余 dense
```

## 6. 信息密度硬规则

除封面/章节/结束页外，每页至少满足：

```text
- 1 个主标题
- 1 句 takeaway
- ≥2 个内容模块（卡片/图示/表格/流程/公式图/注释）
- ≥1 个视觉锚点（图、网络、路径、公式块、数据图、概念图）
```

禁止：只有标题 + 三个短 bullet 的空白页。

## 7. 公式与符号安全规则

公式页不直接用 PPT 文本框硬写复杂公式。

优先级：

1. Python / LaTeX / matplotlib 渲染公式为 PNG/SVG
2. 用 SVG 原生 text + path 手工排版简单公式
3. 用生图做“公式解释视觉”，但不依赖生图生成精确可读公式

交付前必须截图抽检公式页，无乱码再发。

## 8. 生图优势怎么用

生图不负责精确文字，不负责复杂公式，不负责数据准确性。

生图负责：

- 封面主视觉
- 章节过渡背景
- 抽象概念图
- 技术融合/网络氛围图
- 论文方法框架的视觉隐喻
- 统一风格的公式页背景/解释插画

每个 deck 定义一个 `Deck Style Anchor`，所有图像 prompt 都带同一前缀：

```text
clean academic technology presentation style, white and deep navy palette,
cyan/orange accents, vector-like composition, consistent spacing,
no readable text, no logos, no watermark
```

## 9. SVG / 可编辑优先

吸收 ppt-master 的核心：先设计 SVG 页面，再转 PPTX。

原则：

- 文本、形状、图表尽量可编辑
- 生图只作为图片资产嵌入，不把整页做成不可编辑大图
- 图表和公式块可以用 PNG/SVG 保障正确性
- 复杂页面先输出 SVG，再导出 PPTX

## 10. 质量闸门 QA

交付前必须检查：

```text
内容：是否忠于原文，是否有幻觉
密度：是否太空，是否每页有视觉锚点
排版：是否对齐、留白是否合理
风格：颜色、字体、图标、生图是否一致
公式：是否乱码，是否可读
中文：是否乱码，是否字号稳定
PPTX：能否打开，元素是否可编辑
```

## 11. 交付包

标准交付：

```text
final.pptx
speaker-notes.md
slide-spec.json
style-bible.json
image-prompts.md
qa-report.md
```

## 12. 失败处理

- 生图失败：重试一次；仍失败则用矢量图/SVG兜底，不让流程卡死。
- 公式乱码：立刻改为 PNG/SVG 公式块。
- 页面太空：增加图示、流程、表格、注释或案例块，不靠无意义装饰填空。
- 风格漂移：回读 spec_lock，统一颜色/字体/图标/图像锚点。
