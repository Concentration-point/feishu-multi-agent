# UPGRADE-ROADMAP.md

## Clawd 升级路线图 v1（已执行优先三项）

### 1. 浏览器接管默认化（已完成）
- 已产出：`BROWSER-SOP.md`
- 结果：微信 / 登录态 / 重 JS 页面不再默认死磕直抓，优先切真实 Chrome + CDP 接管链路
- 验证：已成功接管 Chrome 并读出微信文章正文

### 2. coding 工程纪律默认化（已完成）
- 已产出：`CODING-SOP.md`
- 结果：在 coding / debug / 配置排障 / 部署修复 / 接口联调场景默认执行
  - Define
  - Plan
  - Build
  - Verify
  - Review
  - Report
- 验证：已写入本地 SOP，并纳入能力台账

### 3. 资料摄入统一化（已完成）
- 已产出：`RETRIEVAL-SOP.md`
- 已安装：`markitdown`
- 结果：
  - 普通网页 → `web_fetch`
  - 登录态/微信/重 JS → 浏览器接管
  - PDF / DOCX / PPTX / XLSX → `markitdown`
  - 图片 / 截图 / 表格图 → OCR / 结构化抽取
- 验证：`markitdown --help` 成功，可用格式已纳入默认工作流

---

## 这三项完成后的默认状态

### 执行侧
- 不再先吹能做，再补验证
- 优先给结果，不把过程当结果

### 工具侧
- 浏览器 / 文档 / 网页三条主链已明确分工

### 方法侧
- 第一梯队学习已从“看懂”变成“写进 SOP + 可执行”

---

## 下一阶段候选（未执行）

1. 评估 `claude-mem` 是否值得系统级接入
2. 用真实 PDF / Word / PPT / Excel 跑一次 `markitdown` 实战验收
3. 继续压缩输出风格：默认更短、更硬、更结果导向
