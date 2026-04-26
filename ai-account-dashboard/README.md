# AI Account Dashboard

本地可用的 AI / Windsurf 账号看板 MVP。

## 怎么用

1. 双击 `启动 AI Account Dashboard.bat`
2. 浏览器打开后，点右上角 **新增账号**
3. 填邮箱、昵称、套餐、到期日期、日额度/周额度
4. 首页会自动显示账号卡片和额度进度条
5. 点「登录页」「订阅页」可打开官方页面
6. 点「导出备份」保存 JSON，换电脑或清缓存前一定要备份

## 重要边界

这个工具只做本地看板：

- 不自动注册账号
- 不自动开试用
- 不自动切换登录态
- 不读取 token
- 不绕过额度
- 不操作支付页

数据保存在浏览器 localStorage。要长期保存，请定期导出备份。

## 半自动额度更新

方式 A：在 Windsurf 官方账号/用量页面 `Ctrl+A` → `Ctrl+C`，回到 Dashboard 编辑账号，把文本粘到「智能解析」框，点「智能解析并填入」。

方式 B：打开 `bookmarklet.html`，把里面的「复制页面文本到剪贴板」拖到书签栏；以后在 Windsurf 页面点这个书签，再回 Dashboard 粘贴解析。

## v3：一键登录 / 独立浏览器 Profile

请优先双击 `launch-desktop.bat` 启动，而不是直接打开 html。

使用方式：

1. 双击 `launch-desktop.bat`
2. 浏览器会打开 Dashboard
3. 新增账号，填邮箱、昵称、登录页/订阅页
4. 点账号卡片里的 **一键登录/额度页**
5. 软件会用该邮箱对应的独立 Chrome/Edge Profile 打开 Windsurf 官方页面
6. 第一次你自己登录一次；以后再点同一个账号，会复用这个本地浏览器会话

说明：

- 不保存你的密码
- 不读取 token
- 不修改 Windsurf 本地登录态
- 每个邮箱一个独立浏览器 Profile，路径在 `browser-profiles/`
- 如果找不到 Chrome/Edge，可设置环境变量 `CHROME_PATH` 或 `EDGE_PATH`
