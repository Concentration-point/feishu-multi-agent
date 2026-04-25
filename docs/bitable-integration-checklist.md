# 飞书多维表格联调清单

这份清单的目标很简单：

**在真正跑 demo 前，确认项目已经和飞书多维表格打通。**

如果下面任一项没对齐，demo 大概率会炸，不是模型的问题，是工程接线没接上。

---

## 一、环境变量必须齐

至少要有：

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `BITABLE_APP_TOKEN`
- `PROJECT_TABLE_ID`
- `CONTENT_TABLE_ID`
- `LLM_API_KEY`

建议先执行：

```bash
python scripts/check_demo_ready.py --skip-network
```

---

## 二、飞书应用权限要确认

至少确认应用具备：

- 获取 tenant_access_token 的能力
- 读取多维表格记录
- 新增多维表格记录
- 更新多维表格记录
- 删除记录（如果测试/清理会用到）

如果后续要跑完整体验，还需要：

- 飞书 IM 发消息权限
- 知识空间 / 云文档相关权限

---

## 三、Bitable 基础 ID 要确认

### 1. `BITABLE_APP_TOKEN`
来自多维表格 URL。

示例：

```text
https://xxx.feishu.cn/base/APP_TOKEN?table=TABLE_ID
```

这里的 `APP_TOKEN` 就是 `BITABLE_APP_TOKEN`。

### 2. `PROJECT_TABLE_ID`
项目主表的 table id。

### 3. `CONTENT_TABLE_ID`
内容排期表的 table id。

> 注意：这两个表必须在同一个 Bitable App 下。

---

## 四、项目主表字段必须对齐

代码里当前要求这些字段名：

- 客户名称
- Brief 内容
- 项目类型
- 品牌调性
- 部门风格注入
- 状态
- Brief 解读
- 策略方案
- 审核总评
- 审核通过率
- 交付摘要
- 知识引用

只要字段名不一致，比如你在飞书里写成“品牌调性内容”或者“审核通过率%”，代码就会读写错位。

---

## 五、内容排期表字段必须对齐

代码里当前要求这些字段名：

- 关联项目
- 内容序号
- 内容标题
- 目标平台
- 内容类型
- 核心卖点
- 目标人群
- 成稿内容
- 字数
- 审核状态
- 审核反馈
- 计划发布日期
- 备注

---

## 六、联调顺序建议

### 第一步：只测依赖和配置

```bash
python scripts/check_demo_ready.py --skip-network
```

### 第二步：测飞书鉴权 + 多维表格读权限

```bash
python scripts/check_demo_ready.py
```

### 第三步：如果检查通过，再跑 demo

```bash
python demo/run_demo.py --scene 电商大促
```

---

## 七、最常见翻车点

### 1. `.env` 根本没建
这个最常见，也最蠢。

### 2. 应用权限不够
能拿 token，不代表能读写表。

### 3. `TABLE_ID` 填错
项目主表和内容表填反、或者填成别的 app 的 table，很常见。

### 4. 字段名和代码不一致
这是最隐蔽、最容易让人误以为“程序逻辑错了”的坑。

### 5. LLM key 没配
前面都通了，Agent 还是会在模型调用时死掉。

---

## 八、现在该怎么用

如果你要快速确认项目离“可跑 demo”还有多远：

1. 先补 `.env`
2. 跑 `python scripts/check_demo_ready.py`
3. 根据输出逐项补齐

别一上来硬跑 demo。那不是联调，是撞墙。 
