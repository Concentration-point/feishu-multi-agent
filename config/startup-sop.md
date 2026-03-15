# Startup SOP

> 目的：电脑关机后，安全恢复 OpenClaw 在线状态；只启动，不重置，不乱改配置。

## 最低风险原则

只做三件事：

1. `openclaw status`
2. `openclaw gateway start`
3. 必要时再 `openclaw status`

## 标准流程

### Step 1：开机后先查状态

```bash
openclaw status
```

### Step 2：如果没跑，就启动 gateway

```bash
openclaw gateway start
```

### Step 3：再次确认

```bash
openclaw status
```

## 可以做的

- 检查状态
- 启动 gateway
- 如果怀疑卡住，再考虑：

```bash
openclaw gateway restart
```

## 不该做的

为了“只是重新上线”，不要碰这些：

- 重新跑初始化向导
- 重置配置
- 手动改 config
- 调 `config.apply` / `config.patch`
- 任何像“重新配置 / 重置 / 重新授权”的操作

## 桌面启动器

当前已放到桌面的文件：

- `启动 OpenClaw.cmd`

用途：
- 先看状态
- 再尝试启动
- 再看一遍状态
- 不修改配置

## 保险版设计要求

保险版应满足：
- 如果已在线：明确提示“已经在线”，直接退出
- 如果未在线：再尝试启动
- 不触碰配置
- 不触发重置逻辑

## 故障处理顺序

如果启动失败，按这个顺序想：

1. 是不是机器刚开机，服务还没起来
2. 是不是命令行环境没加载好
3. 是不是 gateway 卡住，需要 `restart`
4. 最后才考虑配置问题

不要一上来就走“重配系统”那条路。
