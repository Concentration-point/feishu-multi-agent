# video-workbench

本地视频批量工作台（MVP 骨架）。

目标：
- 批量扫描视频
- 批量重命名（支持 preview / apply / rollback）
- 为后续 transcript / docx / mindmap 留好结构

## 当前状态

这是第一版工程骨架，已实现：
- `probe`：扫描目录中的视频文件并输出元数据
- `rename preview`：预览重命名方案
- `rename apply`：执行重命名并写入日志
- `rename rollback`：按日志回滚文件名

预留未实现命令：
- `transcript run`
- `docx build`
- `mindmap build`
- `pipeline run`

## 运行

```bash
python app.py probe ./your-videos --json
python app.py rename preview ./your-videos --rule "{stem}_{index}"
python app.py rename apply ./your-videos --rule "{stem}_{index}"
python app.py rename rollback ./your-videos --map ./your-videos/logs/rename-log.json
```

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

## 输出约定

- `--json` 输出结构化结果
- 默认输出人类可读文本
- 改名日志默认保存到：`<directory>/logs/rename-log.json`

## 目录建议

```text
videos/
├─ logs/
│  └─ rename-log.json
├─ transcripts/
├─ docs/
└─ mindmaps/
```
