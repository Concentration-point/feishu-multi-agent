# 首轮联调最短命令清单

目标：在最短时间内确认这个项目能不能跑通 demo。

> 顺序不要乱。先环境，再飞书，再 demo。

---

## 0. 进入项目目录

```powershell
cd C:\Users\25723\.openclaw\workspace\multi-agent-feishu
```

---

## 1. 安装依赖

```powershell
pip install -r requirements.txt
```

如果提示某些包仍然缺失：

```powershell
pip install openai fastapi uvicorn python-dotenv httpx
```

---

## 2. 创建 `.env`

```powershell
copy .env.example .env
```

然后编辑 `.env`，至少填：

```env
FEISHU_APP_ID=cli_xxxxxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
BITABLE_APP_TOKEN=xxxxxxxxxxxxxxxx
PROJECT_TABLE_ID=tblxxxxxxxxxxxxxxxx
CONTENT_TABLE_ID=tblxxxxxxxxxxxxxxxx
LLM_API_KEY=sk-xxxxxxxxxxxxxxxx
LLM_MODEL=gpt-4o
```

如果用 OpenAI 兼容模型，按实际情况改：

```env
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o
```

---

## 3. 本地预检查

```powershell
python scripts/check_demo_ready.py --skip-network
```

预期：

- 依赖不再缺 `openai` / `fastapi` / `uvicorn`
- `.env` 必填项不再缺

如果这一步不过，不要跑后面的。

---

## 4. 飞书联通检查

```powershell
python scripts/check_demo_ready.py
```

这一步会检查：

- tenant_access_token 是否能拿到
- 项目主表是否可读
- 内容排期表是否可读
- 样本记录字段名是否覆盖代码映射

如果输出：

```text
DEMO_READY: YES
```

才进入下一步。

---

## 5. 跑 demo

```powershell
python demo/run_demo.py --scene 电商大促
```

也可以换场景：

```powershell
python demo/run_demo.py --scene 新品发布
python demo/run_demo.py --scene 品牌传播
```

如果已有飞书表格记录：

```powershell
python demo/run_demo.py --record-id recxxxxxx
```

---

## 6. Webhook 服务检查

```powershell
python main.py serve
```

另开一个终端：

```powershell
curl http://127.0.0.1:8000/healthz
```

预期：

```json
{"status":"ok"}
```

---

## 7. 常见失败判断

### 缺依赖

表现：

```text
ModuleNotFoundError: No module named 'openai'
```

处理：

```powershell
pip install -r requirements.txt
```

### `.env` 缺项

表现：

```text
MISSING FEISHU_APP_ID
MISSING BITABLE_APP_TOKEN
```

处理：补 `.env`。

### token 拿不到

重点检查：

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- 飞书应用是否存在

### 表不可读

重点检查：

- `BITABLE_APP_TOKEN`
- `PROJECT_TABLE_ID`
- `CONTENT_TABLE_ID`
- 飞书应用是否有多维表格读写权限
- 应用是否能访问该多维表格

### 字段不匹配

参考：

```text
docs/field-mapping-reference.md
```

字段名必须一字不差。

---

## 8. 首轮联调完成标准

满足下面三条，才算第一轮真正过：

1. `python scripts/check_demo_ready.py` 输出 `DEMO_READY: YES`
2. `python demo/run_demo.py --scene 电商大促` 能创建记录并跑完整流水线
3. 飞书多维表格里能看到主表字段和内容排期表被写入

没达到这三条，就别急着说“demo 跑通”。
