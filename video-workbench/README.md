# video-workbench

本地视频批量工作台（MVP）。

当前定位：
- **先把本地视频前处理 + 后处理打通**
- **不默认外发内容**
- **语音识别（ASR）保持本地优先，但当前 Windows 运行时仍存在兼容问题**

---

## 当前已实现

### 1. 扫描视频
- `probe`
- 识别目录中的视频文件
- 输出结构化 JSON

### 2. 批量重命名
- `rename preview`
- `rename apply`
- `rename rollback`
- 自动写入 `logs/rename-log.json`

### 3. 本地抽音频
- 使用**项目内便携 ffmpeg**（优先）
- 无需系统级安装 ffmpeg
- 音频输出到 `audio_tmp/`

### 4. 文档生成
- `docx build`
- 基于 transcript markdown 生成 `.docx`

### 5. 思维导图生成
- `mindmap build`
- 生成：
  - Markdown outline
  - Mermaid mindmap (`.mmd`)

### 6. 流水线编排
- `pipeline run`
- 能串起 transcript / docx / mindmap
- 明确告诉你哪步成功、哪步失败

---

## 当前未完成 / 已知限制

### 本地 ASR 仍未打通
已验证过两条本地 ASR 路线：

1. `faster-whisper`
   - 卡在 `ctranslate2` 初始化模型
2. `openai-whisper`
   - 卡在 `torch` 的 DLL 初始化（`c10.dll`）

这说明：
- **视频没问题**
- **ffmpeg 没问题**
- **抽音频没问题**
- **docx / 脑图没问题**
- **当前真正卡住的是本机 Windows 的本地推理 runtime**

因此本版本把 transcript 定义为：
- 已接上真实执行链路
- 但在当前机器上可能返回 `partial` / `error`

---

## 运行方式

```bash
python app.py --json probe ./your-videos
python app.py --json rename preview ./your-videos --rule "{mtime_date}_{index}_{stem}"
python app.py --json rename apply ./your-videos --rule "{mtime_date}_{index}_{stem}"
python app.py --json rename rollback ./your-videos --map ./your-videos/logs/rename-log.json

python app.py --json transcript run ./your-videos
python app.py --json docx build ./your-videos
python app.py --json mindmap build ./your-videos
python app.py --json pipeline run ./your-videos
```

---

## 命名模板

当前支持：
- `{stem}` 原文件名（不含扩展名）
- `{ext}` 扩展名（不含点）
- `{index}` 顺序编号（两位）
- `{mtime_date}` 文件修改日期（YYYY-MM-DD）

示例：

```text
{mtime_date}_{index}_{stem}
```

---

## 目录结构

```text
videos/
├─ logs/
│  └─ rename-log.json
├─ audio_tmp/
├─ transcripts/
├─ docs/
└─ mindmaps/
```

---

## 当前推荐使用姿势

### 适合现在就用的
- 批量整理视频文件名
- 预览并回滚重命名
- 从视频抽音频
- 先生成 transcript 占位文件
- 基于现有 transcript 产出 Word / 脑图骨架

### 暂时不适合吹成“已完成”的
- 纯本地一键视频转文字稿

这一步在当前机器上还差本地 ASR runtime 的稳定性。

---

## 设计原则

这版 MVP 刻意遵循几条硬规则：
- **先 probe，再 mutation**
- **先 preview，再 apply**
- **能回滚就别裸改**
- **优先真 backend，不造假软件**
- **输出尽量结构化，不让 agent 猜**
- **明确区分：backend 是否就绪、执行到哪一步、失败点在哪**

---

## 现在的判断

这不是一个“什么都没成”的空壳，
而是一个：

> **前处理和后处理已经站住，中间 ASR 还卡在本机运行时的本地工作台 MVP。**

方向没错，链路也没塌，只是 ASR 这颗钉子还没拔下来。🦞
