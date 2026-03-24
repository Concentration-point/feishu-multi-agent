# NEXT-STEPS.md

`video-workbench` 后续排障与推进清单。

这份文件的目标不是讲理想状态，而是把**已经踩过的坑**和**以后正确的推进顺序**钉死，避免重复考古。

---

## 当前项目状态

### 已经打通的
- 本地视频扫描（`probe`）
- 批量重命名（`preview / apply / rollback`）
- 项目内便携 ffmpeg
- 视频 → 音频抽取
- transcript 占位输出
- docx 生成
- 思维导图（Markdown / Mermaid）生成
- pipeline 编排

### 当前未打通的
- 本机本地 ASR

---

## 已确认的事实

### 1. 视频不是问题
真实样本视频可以被识别、复制、读入。

### 2. ffmpeg 方案是通的
项目内便携 ffmpeg 已经能正常：
- 读取视频
- 抽出 wav 音频

### 3. 后处理链没问题
基于 transcript 文件：
- `docx build` 能生成 Word
- `mindmap build` 能生成脑图骨架

### 4. 真正的问题是本机本地推理 runtime
当前尝试过两条路线：

#### faster-whisper
- Python 包安装成功
- 模型下载成功
- 卡在 `ctranslate2` 初始化 Whisper 模型
- 现象：`WhisperModel(...)` 或 `ctranslate2.models.Whisper(...)` 初始化阶段直接挂掉

#### openai-whisper
- Python 包安装成功
- 卡在 `torch` 导入时的 DLL 初始化
- 报错：
  - `OSError: [WinError 1114] 动态链接库(DLL)初始化例程失败`
  - 失败点：`torch\\lib\\c10.dll`

所以当前结论非常明确：

> 业务链没塌，塌的是 Windows 本地推理 runtime。

---

## 以后正确的推进顺序

### 第一优先：先修 torch / DLL 运行时
先查 `openai-whisper` 这条线，因为它的报错更明确。

#### 重点方向
- Visual C++ Redistributable 是否完整
- PyTorch 对应 wheel 与当前 Python 版本是否匹配
- 当前 CPU / 指令集 / oneDNN / OpenMP 兼容性
- 缺失的系统 DLL / 依赖项
- `c10.dll` 及其依赖是否可正常加载

#### 目标
做到：
```python
import torch
```
至少先不炸。

如果连 `import torch` 都不稳，就别谈 whisper。

---

### 第二优先：再看 ctranslate2
如果 torch 路线仍不理想，再查 `ctranslate2`。

#### 重点方向
- `ctranslate2` Windows issue
- CPU backend 兼容性
- `compute_type` 参数（如 `int8` / `float32`）
- 模型目录是否完整
- 是否存在原生层崩溃但没有正常 traceback 的问题

#### 目标
做到：
- `ctranslate2.models.Whisper(model_path, ...)` 初始化能成功
- 再谈 faster-whisper 转录

---

### 第三优先：再回到业务链验收
等本地 ASR runtime 稳了，再重新做完整验收：

1. 真视频 → 抽音频
2. 真音频 → 真 transcript
3. transcript → docx
4. transcript → mindmap
5. pipeline 全链验收

---

## 不要再重复做的事

### 1. 不要再把 demo 假文件当真视频测 transcript
之前 `tmp_demo` 里的 `.mp4/.mov` 只是占位文件，导致 ffmpeg 报：
- `moov atom not found`
- `Invalid data found when processing input`

这不是 backend 问题，只是样本是假的。

### 2. 不要再把 `.venv_asr` 和 `tools/ffmpeg` 提交进 Git
它们应该一直在 `.gitignore` 里。

### 3. 不要在当前主环境继续乱装依赖
ASR 相关依赖必须继续：
- 保持隔离
- 不污染主 Python

### 4. 不要为了验证业务链继续死磕远程 ASR
除非老大明确批准内容外发。
当前默认策略仍然是：
- **不外发音频**
- **本地优先**

---

## 推荐的最小排障目标
先别追求“一次全通”，先追求这两个最小里程碑：

### 里程碑 A
```python
import torch
```
不报 DLL 错。

### 里程碑 B
```python
import whisper
model = whisper.load_model('tiny')
```
至少能初始化。

### 里程碑 C
```python
from faster_whisper import WhisperModel
WhisperModel('tiny', device='cpu', compute_type='int8')
```
至少不在初始化阶段崩。

做到其中任意一条，后面就有继续推进的价值。

---

## 当前最准确的项目定义

`video-workbench` 不是空壳，也不是完整成品。

它现在最准确的定义是：

> 一个已经打通本地视频前处理与后处理、但中间 ASR 仍受 Windows 本地 runtime 阻塞的 MVP。

这句话以后不要再改口径。它就是当前事实。🦞
