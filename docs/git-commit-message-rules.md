# Git 提交说明规则

## 基本要求

所有主 Agent 和子 Agent 在本项目提交 commit 时，必须使用中文提交说明。

提交说明不能只有一个过短标题，应包含：

1. 中文标题：一句话说明本次提交做了什么。
2. 中文正文：补充说明为什么改、改了哪些关键点、验证结果或风险。

推荐格式：

```text
修复：强化 Webhook 鉴权与事件级去重

说明：
- 配置 Webhook token 后，缺失或错误 token 都会拒绝。
- 去重键从 record_id 收紧为 event_id 优先，缺失时回退到 record_id + 时间字段。
- 已通过 Webhook 鉴权与去重相关 TDD 测试。
```

常用标题前缀：

- `测试：...`
- `修复：...`
- `文档：...`
- `合并：...`
- `重构：...`

## 子 Agent 提交要求

子 Agent 提交前必须确认：

1. 只提交自己负责的文件边界。
2. commit 标题和正文都使用中文。
3. 正文写清测试命令和结果。
4. 不把测试日志、临时目录、运行产物混入提交。

子 Agent 推荐提交格式：

```text
测试：覆盖 reviewer 红线门禁

说明：
- 新增红线命中后不得进入排期或完成状态的 TDD 用例。
- 覆盖返工次数达到上限时红线仍必须硬中止的场景。
- 验证命令：python -m pytest tests/test_pipeline_red_flag_tdd.py -q --tb=short。
- 当前阶段允许红灯，失败点集中在 orchestrator.py 的红线处理逻辑。
```

## Windows / PowerShell 编码注意事项

不要在 Windows PowerShell 中通过普通管道直接把中文传给 `git commit-tree`、`git commit -m` 或其他会写入 Git 对象的命令。

已发生过的问题：

- 在 PowerShell 中重写 commit message 时，中文经管道传给 `git commit-tree`。
- 提交对象里的中文被写成字面量 `?`。
- GitHub 提交列表显示为 `????????`，不是页面显示问题，而是 Git 对象本身已经损坏。

正确做法：

1. 普通提交优先使用 UTF-8 message 文件：

```powershell
git commit -F commit-message.txt
```

其中 `commit-message.txt` 必须以 UTF-8 保存。

2. 自动化重写历史时，使用 Python、Node.js 或其他能明确写入 UTF-8 bytes 的脚本，把 message 通过 `stdin` 传给 Git。

3. 重写后必须验证 Git 对象里的提交说明：

```powershell
python -c "import subprocess; data=subprocess.check_output(['git','log','--format=%s','-5']); print(data.decode('utf-8'))"
```

4. 推送前必须确认：

```powershell
git diff --stat <rewrite-before-backup>..HEAD
```

该命令应为空，表示只改了 commit message，没有改代码内容。

5. 如果已经推到远端，修复提交说明时必须：

- 先创建备份分支。
- 从未损坏的备份分支重新生成历史。
- 使用 `git push --force-with-lease origin main` 推送，避免覆盖别人新提交。

## 本地 Hook 固化

本仓库提供版本化的提交说明校验：

- `.githooks/commit-msg`
- `scripts/validate_commit_message.py`

每个 worktree 首次提交前都应启用：

```powershell
git config core.hooksPath .githooks
```

校验规则：

1. commit 标题必须包含中文。
2. commit 正文必须包含中文描述，写清原因、关键改动和验证结果。
3. 禁止英文-only、无正文、连续 `????`、`æ–‡æ¡£` 这类 mojibake 乱码进入 Git 对象。
4. 主 Agent 和子 Agent 都必须遵守同一规则；子 Agent 的任务提示词中也要明确这条要求。

如果 hook 拦截提交，不要绕过 `--no-verify`，应重新生成 UTF-8 message 文件再提交。

## 禁止事项

1. 不要提交英文-only 的 commit message。
2. 不要只写 `fix`、`update`、`wip` 这类无描述标题。
3. 不要用 PowerShell 普通管道传中文 commit message。
4. 不要在未创建备份分支时重写已推送历史。
5. 不要把测试生成物、日志和临时目录混入提交。
6. 不要用 `--no-verify` 绕过 commit message hook。
