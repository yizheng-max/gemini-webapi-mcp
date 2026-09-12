# Windows 上让 Codex 调用已登录的 Gemini Web

这套方案不使用 Gemini 官方 API Key、Gemini CLI 或 Computer Use。调用链如下：

```text
Codex → gemini-webapi-mcp → 本机 Gemini Web 登录态 → Gemini 回答 → Codex
```

它还支持把 Codex 固定到一个已有的 Gemini 网页历史会话。你可以在浏览器和 Codex
之间交替发言；MCP 每次发送前都会读取该会话的最新服务端分支。

## 安全边界

- 优先让 `browser-cookie3` 自动读取 Chrome Cookie。
- 不要关闭 Chrome 的 App-Bound Encryption，也不要修改 Chrome 安全策略来绕过它。
- Chrome 127+（包括 Chrome 152）可能阻止第三方程序解密 Cookie。自动读取确实失败时，
  可用本仓库的窗口将两个 Cookie 一次性保存为 Windows DPAPI 密文。
- DPAPI 文件只能由保存它的 Windows 用户在本机解密。
- Cookie、DPAPI 文件和会话绑定文件必须放在 Git 仓库之外，绝不能提交。
- 本项目只把 Cookie 用于访问 Google Gemini Web 的 HTTPS 请求，不写入其他服务；如果你
  启用了系统代理，网络流量会经过该代理，因此应只使用你信任的代理。

## 1. 安装

下面示例全部放在 `F:` 盘。请根据你的非系统盘目录调整。先检查 Git 和 `uv`：

```powershell
git --version
uv --version
```

如果 Git 未安装，请先从 [Git for Windows](https://git-scm.com/download/win) 安装。
如果 `uv` 未安装，可将官方安装器指定到非系统盘（当前 PowerShell 会话随后立即可用）：

```powershell
$env:UV_INSTALL_DIR='F:\codex-tools\bin'
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
$env:Path="F:\codex-tools\bin;$env:Path"
uv --version
```

然后安装本项目：

```powershell
git clone https://github.com/yizheng-max/gemini-webapi-mcp.git F:\codex-tools\gemini-webapi-mcp
Set-Location F:\codex-tools\gemini-webapi-mcp
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -e .
New-Item -ItemType Directory -Force F:\codex-tools\gemini-web-credentials, F:\codex-tools\temp
```

## 2. 认证：先尝试 Chrome 自动读取

不要先复制 Cookie。先不设置 `GEMINI_CREDENTIAL_FILE`，启动器会让 MCP 自己通过
`browser-cookie3` 读取 Chrome：

```powershell
$env:GEMINI_MCP_SERVER='F:\codex-tools\gemini-webapi-mcp\.venv\Scripts\gemini-webapi-mcp.exe'
$env:GEMINI_BINDING_FILE='F:\codex-tools\gemini-web-credentials\bound-chat.json'
$env:GEMINI_MCP_TEMP='F:\codex-tools\temp'
python F:\codex-tools\gemini-webapi-mcp\scripts\windows\gemini_mcp_launcher.py
```

如果初始化成功，跳到第 3 节。

### Chrome App-Bound Encryption 失败时

Chrome 152 的 App-Bound Encryption 是安全机制，不建议解除。最小人工步骤是只在本机
窗口中输入 `__Secure-1PSID` 和 `__Secure-1PSIDTS`，脚本不会打印它们：

```powershell
$env:GEMINI_CREDENTIAL_FILE='F:\codex-tools\gemini-web-credentials\cookies.dpapi.json'
F:\codex-tools\gemini-webapi-mcp\.venv\Scripts\python.exe `
  F:\codex-tools\gemini-webapi-mcp\scripts\windows\capture_gemini_cookies.py
```

在当前已登录 Gemini 的 Chrome 页面按 `F12`，进入
`Application → Cookies → https://gemini.google.com`，把两个值粘贴到本地窗口。
之后启动器会在内存中解密并传给 MCP，不会输出 Cookie。

如果 Google 同时登录了多个账号，设置正确的索引：

```powershell
$env:GEMINI_ACCOUNT_INDEX='1'  # 0、1、2……与 Gemini 网页账号顺序一致
```

## 3. 添加到 Codex

Codex 的用户级配置通常位于 `$env:CODEX_HOME\config.toml`。本机实际路径应以
`codex mcp list` 和 `$env:CODEX_HOME` 为准。示例：

```toml
[mcp_servers.gemini]
command = "F:\\codex-tools\\gemini-webapi-mcp\\.venv\\Scripts\\python.exe"
args = ["F:\\codex-tools\\gemini-webapi-mcp\\scripts\\windows\\gemini_mcp_launcher.py"]

[mcp_servers.gemini.env]
GEMINI_MCP_SERVER = "F:\\codex-tools\\gemini-webapi-mcp\\.venv\\Scripts\\gemini-webapi-mcp.exe"
GEMINI_CREDENTIAL_FILE = "F:\\codex-tools\\gemini-web-credentials\\cookies.dpapi.json"
GEMINI_BINDING_FILE = "F:\\codex-tools\\gemini-web-credentials\\bound-chat.json"
GEMINI_MCP_TEMP = "F:\\codex-tools\\temp"
GEMINI_ACCOUNT_INDEX = "0"
```

若 Chrome 自动读取成功，删除示例中的 `GEMINI_CREDENTIAL_FILE` 行。检查：

```powershell
codex mcp list
```

`gemini` 应显示为 `enabled`。重新启动 Codex 或新开一个任务，使新工具列表生效。

## 4. 基本测试

直接对 Codex 说：

```text
请调用 Gemini，只回答：Gemini MCP 通信测试成功
```

连续对话测试：

```text
请调用 gemini_start_chat 新建临时会话。第一轮让 Gemini 记住数字 7319，只回答已记住；
第二轮问它刚才的数字是多少。告诉我两轮实际结果。
```

## 5. 绑定指定 Gemini 网页会话

在你希望长期使用的 Gemini 网页会话中复制地址栏 URL，例如：

```text
https://gemini.google.com/app/xxxxxxxx
https://gemini.google.com/u/1/app/xxxxxxxx
```

然后对 Codex 说：

```text
调用 gemini_bind_chat，绑定这个 Gemini 会话：https://gemini.google.com/app/xxxxxxxx
```

成功后，不带 `session_id` 的普通 `gemini_chat` 都会进入这个历史会话。绑定时不传
`model` 会保留网页会话的模型选择；只有明确传入 `model` 才会覆盖。显式指定
`session_id` 的临时会话仍具有更高优先级。

常用指令：

```text
调用 gemini_binding_status，告诉我当前绑定状态。
调用 gemini_unbind_chat，解除固定会话绑定。
```

绑定的是 Gemini 服务端会话 ID，不是对浏览器标签页做屏幕控制。因此标签页不必一直
打开；以后打开同一个 URL，仍能看到 Codex 通过 MCP 添加的消息。

## 6. 视频拆解

本地视频可以通过 `gemini_upload_file` 上传给 Gemini 做一次性分析。当前上传工具不会把
视频挂到固定会话或临时 `session_id`，因此后续 `gemini_chat` 不会自动继承视频内容；
需要补充问题时，应把问题合并进同一次上传提示，或再次上传文件。请先确认视频允许上传
给 Google，并在提示中明确需要的维度，例如结构、镜头、台词、节奏、情绪和可复用方法。
大文件受 Gemini 网页端限制。

示例：

```text
调用 Gemini 分析这个视频。按时间轴拆解镜头、画面、台词、节奏、情绪和转场；
先由你独立分析，再比较 Gemini 的结论，最后给我综合判断。
```

## 7. 常见问题

- **绑定失败但普通聊天成功：** URL 所属 Google 账号与 Cookie 账号通常不一致；检查
  `GEMINI_ACCOUNT_INDEX`，或为目标账号重新保存 DPAPI Cookie。
- **网页还在生成时调用失败：** 等网页回复完成后重试。服务器不会退回旧分支或误发
  到新会话。
- **明明能读取会话却提示仍在生成：** Gemini 的完成状态字段优先于富内容中的兼容
  字段；当前版本已兼容“状态 2 表示已完成”的网页响应，并有回归测试覆盖。若将来
  Google 再次调整协议，先更新本 Fork 并运行 `tests/test_chat_binding.py`。
- **认证失效：** 先调用 `gemini_reset`；仍失败再更新本机 DPAPI Cookie。
- **代理环境无法连接：** Windows 启动器会读取当前用户的系统 HTTP/HTTPS 代理，并
  通过 `GEMINI_PROXY` 传给底层客户端。
- **Gemini 网页协议变化：** 本项目依赖非公开的 Gemini Web 协议及其底层库；Google
  改版后可能需要同步更新。遇到突然失效时先查看本 Fork 与上游仓库的 Issues/提交。
- **不要提交：** `cookies.dpapi.json`、`bound-chat.json`、Cookie 明文、浏览器数据库。
- **验收范围：** 固定会话协议与分支同步已有自动化测试；由于会话属于具体 Google
  账号，发布前未对公开示例 URL 做真实写入。请用自己的会话 URL 首次绑定验证。

## 8. 工具清单

- `gemini_chat`：普通聊天；存在固定绑定时续接该网页会话。
- `gemini_start_chat`：创建临时多轮会话。
- `gemini_bind_chat`：绑定一个已有网页会话。
- `gemini_binding_status`：查看绑定状态。
- `gemini_unbind_chat`：解除绑定。
- `gemini_reset`：刷新认证客户端。
- `gemini_upload_file`：上传并分析视频、图片、PDF 等文件。
