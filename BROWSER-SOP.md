# BROWSER-SOP.md

## 目的

当用户说“浏览器打开”“接管浏览器”“读登录态页面/微信文章/后台页面”时，走这份 SOP。

目标：**先验证可接管，再执行任务；默认给结果，不给借口。**

---

## 0. 适用场景

触发词包括但不限于：
- 浏览器打开这篇
- 接管
- 用浏览器读
- 读微信文章
- 读取登录态页面
- 后台页面/控制台/管理台

如果只是普通公开网页，优先 `web_fetch` / `web_search`。  
如果遇到登录态、验证码墙、反爬、JS 重页面，立刻切真实浏览器链路。

---

## 1. 基本原则

1. **不要先吹能接管。先验证。**
2. **不要让用户手配环境，除非安全边界要求。**
3. **优先最低风险本机方案：独立 Chrome + CDP + 独立临时 user-data-dir。**
4. **拿不到正文就明确说没拿到，禁止编总结。**
5. **一旦接管成功，优先直接产出结果，再谈增强能力。**

---

## 2. 默认执行方案（Windows）

### Step A：确认 Chrome 路径

PowerShell：

```powershell
$chromePaths = @(
  'C:\Program Files\Google\Chrome\Application\chrome.exe',
  'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
  "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)
$chrome = $chromePaths | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $chrome) { Write-Error 'chrome.exe not found'; exit 1 }
```

### Step B：启动独立可接管 Chrome

```powershell
$profileDir = Join-Path $env:TEMP 'openclaw-chrome-cdp'
New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
Start-Process -FilePath $chrome -ArgumentList @('--remote-debugging-port=9222', "--user-data-dir=$profileDir", 'about:blank')
```

### Step C：验证 CDP 端口

```powershell
Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:9222/json/version' | Select-Object -ExpandProperty Content
```

返回 JSON 且含 `webSocketDebuggerUrl`，才算接管入口可用。

### Step D：agent-browser 接管

```powershell
agent-browser --cdp 9222 open "<URL>"
agent-browser --cdp 9222 wait 5000
agent-browser --cdp 9222 get title
agent-browser --cdp 9222 get url
agent-browser --cdp 9222 eval "document.body.innerText"
```

### Step E：抽取结果

优先级：
1. `eval "document.body.innerText"`
2. `snapshot -c -d 6`
3. 必要时截图 + 再读页面结构

---

## 3. 微信文章专用规则

1. 先试 `web_fetch`
2. 若被拦截（验证码/私网/特殊 IP/空壳页），**立刻切 CDP 浏览器链路**
3. 打开后必须验证：
   - 标题是否正确
   - URL 是否仍是原文章链接
   - `document.body.innerText` 是否出现正文，而不是异常页
4. 若仍是异常页，再向用户汇报“正文未拿到”——不是先汇报，必须在真实浏览器验证后再说

---

## 4. 输出规则

### 用户只要结果时
- 直接给正文总结/提炼
- 不复盘工具细节
- 不解释一堆失败尝试

### 用户要求能力增强时
在结果后补：
- 这次暴露的能力短板
- 应该固化成什么默认工作流
- 下一步最值得补的 1-3 项

---

## 5. 禁忌

- 禁止在未验证 CDP 可用前说“我来接管”
- 禁止把“浏览器能力存在”误当成“浏览器接管链路可用”
- 禁止拿不到正文却假装读过
- 禁止遇阻后把环境问题直接甩给用户
- 禁止连续两次用同一路子空转

---

## 6. 本次已验证可用命令

```powershell
$chromePaths = @(
  'C:\Program Files\Google\Chrome\Application\chrome.exe',
  'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
  "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)
$chrome = $chromePaths | Where-Object { Test-Path $_ } | Select-Object -First 1
$profileDir = Join-Path $env:TEMP 'openclaw-chrome-cdp'
New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
Start-Process -FilePath $chrome -ArgumentList @('--remote-debugging-port=9222', "--user-data-dir=$profileDir", 'about:blank')
Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:9222/json/version' | Select-Object -ExpandProperty Content
agent-browser --cdp 9222 open "https://mp.weixin.qq.com/s/loJB2RIvH8yowq9f_HE4Uw"
agent-browser --cdp 9222 wait 5000
agent-browser --cdp 9222 eval "document.body.innerText"
```

---

## 7. 以后默认心智

**公开网页靠抓取，复杂网页靠浏览器，登录态网页靠接管。**  
别再每次临场想。按 SOP 干。