# 无敌抢场王 / Invincible Court Booker

> 杭州电子科技大学综合馆羽毛球场地自动预约工具
>
> An automated badminton court booking tool for Hangzhou Dianzi University Sports Complex.

[中文文档](#中文文档) | [English](#english)

---

## 中文文档

### 项目简介

一个基于 Python 的桌面应用，能够自动从钉钉抓取认证凭证，并在每晚 20:00 准时并发抢场，帮你告别手动预约的痛苦。

### 功能特性

- **一键抓包** — 点击按钮自动启动 mitmproxy 代理，无需手动复制 Token 和 User-Agent
- **定时执行** — 设置任务后在后台等待，每晚 20:00 分准时发起请求
- **多场地并发** — 同时对多个场地号发起请求，大幅提高成功率
- **403 自动重试** — 遇到 Token 过期自动刷新并重试，无需人工干预
- **极简界面** — 只保留时间段选择和两个按钮，去除一切冗余信息
- **日志留存** — 每次运行的详细日志自动保存至 `~/Library/Logs/ddAutoSub/`

### 界面概览

```
┌──────────────────────────┐
│                          │
│       无敌抢场王          │
│    抓包 · 预约 · 全自动   │
│                          │
│  ┌────────────────────┐  │
│  │ 时间段    [▼ 选择] │  │
│  │ ────────────────── │  │
│  │ [   抓取凭证    ]   │  │
│  │   已就绪 · 可开始   │  │
│  └────────────────────┘  │
│                          │
│  [ 定时抢场 · 今晚20:00 ]│
│                          │
│  日志  抢场日志_xxx.log   │
└──────────────────────────┘
```

### 环境要求

| 依赖 | 版本要求 | 说明 |
|------|----------|------|
| macOS | 12.0+ | 仅支持 macOS |
| Python | 3.9+ | 推荐 3.11 |
| mitmproxy | 9.x | `pip install mitmproxy` |
| 钉钉 | 最新版 | 用于打开体育预约页面 |

### 快速开始

**1. 克隆项目**

```bash
git clone https://github.com/2438735239/ddAutoSub.git
cd ddAutoSub
```

**2. 安装 Python 依赖**

```bash
pip install requests mitmproxy
```

**3. 生成并信任 mitmproxy CA 证书（仅需一次）**

```bash
# 生成证书
mitmdump
# 看到 "HTTP(S) proxy listening at *:8080" 后按 Ctrl+C 退出

# 信任证书
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain \
  ~/.mitmproxy/mitmproxy-ca-cert.pem
```

**4. 启动应用**

```bash
python3 ddAutoSubV6.py
```

### 使用说明

**第一步：抓取凭证**

1. 点击「抓取凭证」按钮
2. 应用会自动：
   - 启动 mitmproxy 代理（端口 8080）
   - 设置系统 HTTP/HTTPS 代理
   - 重启钉钉
3. 在钉钉中打开体育预约页面
4. 看到 `已就绪 · 可开始抢场` 时说明抓取成功

**第二步：选择时间段**

在下拉菜单中选择你要预约的时间段（支持单小时和连续两小时）。

**第三步：启动定时任务**

点击「定时抢场 · 今晚 20:00」，应用会在后台倒计时，20:00 准时发起请求。预约结果会弹窗提示，详细日志可查看 `~/Library/Logs/ddAutoSub/` 目录。

### 高级配置

以下配置项已内置在代码中，如需修改可编辑 `ddAutoSubV6.py`：

| 配置项 | 默认值 | 位置 |
|--------|--------|------|
| 场地号 | `1,2,3,4,9,10,11,12` | `__init__` -> `self._sites` |
| 403 重试次数 | `3` | `__init__` -> `self._max_403_retries` |
| 预约日期 | 当天 + 2 天 | `__init__` -> `self._date` |
| 场馆名称 | 综合馆羽毛球 | `start_task` -> `config` |

### 打包为独立应用

如果想分发给没有 Python 环境的同学：

```bash
# 安装 PyInstaller
pip install pyinstaller

# 打包（无命令行窗口）
python3 -m PyInstaller --windowed --name "无敌抢场王" --clean ddAutoSubV6.py

# 产物在 dist/无敌抢场王.app
```

> 方案 A 打包（当前方式）：用户仍需自行安装 mitmproxy 并信任证书。

### 常见问题

**Q: 点击「抓取凭证」后提示 "未检测到 mitmproxy"**

A: 终端执行 `pip install mitmproxy` 安装后再试。

**Q: 抓取一直不成功**

A: 请确认：
1. mitmproxy CA 证书已信任（打开钥匙串 -> 搜索 mitmproxy -> 显示简介 -> 信任 -> 始终信任）
2. 系统代理已正确设置（系统偏好设置 -> 网络 -> 高级 -> 代理 -> 网页代理和安全网页代理）
3. 钉钉已完全退出后重新打开

**Q: 20:00 到了但没有抢到**

A: 查看 `~/Library/Logs/ddAutoSub/` 中当天的日志文件，常见原因：
- `403 Forbidden` — Token 已过期，请重新抓取凭证
- `校验失败` — 该时段已被其他人抢走
- `连接失败` — 网络问题，检查 VPN 或校园网连接

**Q: 双击 `.app` 没反应**

A: 确认已安装 mitmproxy 并信任证书。查看 `~/Library/Logs/ddAutoSub/` 中是否有日志文件，如有则说明应用已启动但可能有其他错误。

### 项目结构

```
ddAutoSub/
├── ddAutoSubV5.py          # V5 版本：多场地并发 + 403自动刷新
├── ddAutoSubV6.py          # V6 版本：V5 基础 + 一键抓包 + 极简UI
├── 无敌抢场王.spec          # PyInstaller 打包配置
├── README.md               # 本文件
└── dist/
    └── 无敌抢场王.app       # macOS 打包产物
```

### 版本历史

| 版本 | 核心改进 |
|------|----------|
| V5 | 多场地并发、403 自动刷新 Token、错峰秒杀 |
| V6 | 一键抓包获取凭证、极简 UI、日志路径修复、macOS 打包 |

### 许可协议

[MIT License](LICENSE)

> 本项目仅供学习交流使用。抢场有风险，入坑需谨慎。

---

## English

### Overview

A Python-based desktop application that automatically captures authentication credentials from DingTalk and books badminton courts precisely at 20:00 each night — no more manual booking struggles.

### Features

- **One-Click Credential Capture** — Auto-launches mitmproxy to capture Token and User-Agent; no manual copy-paste needed.
- **Scheduled Execution** — Waits in the background and fires requests exactly at 20:00 each night.
- **Multi-Court Concurrency** — Sends requests for multiple court numbers simultaneously, dramatically boosting success rate.
- **Automatic 403 Retry** — Refreshes expired tokens and retries automatically; no manual intervention required.
- **Minimal UI** — Only the time-slot selector and two buttons. Zero clutter.
- **Persistent Logging** — Detailed logs for each run saved to `~/Library/Logs/ddAutoSub/`.

### Requirements

| Dependency | Version | Notes |
|------------|---------|-------|
| macOS | 12.0+ | macOS only |
| Python | 3.9+ | 3.11 recommended |
| mitmproxy | 9.x | `pip install mitmproxy` |
| DingTalk | Latest | Required for accessing the sports booking page |

### Quick Start

**1. Clone the repo**

```bash
git clone https://github.com/2438735239/ddAutoSub.git
cd ddAutoSub
```

**2. Install Python dependencies**

```bash
pip install requests mitmproxy
```

**3. Generate and trust the mitmproxy CA certificate (one-time setup)**

```bash
# Generate certificate
mitmdump
# Press Ctrl+C after seeing "HTTP(S) proxy listening at *:8080"

# Trust the certificate
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain \
  ~/.mitmproxy/mitmproxy-ca-cert.pem
```

**4. Launch the app**

```bash
python3 ddAutoSubV6.py
```

### Usage

**Step 1: Capture Credentials**

1. Click the "Capture Credentials" button.
2. The app will automatically:
   - Start mitmproxy on port 8080
   - Configure the system HTTP/HTTPS proxy
   - Restart DingTalk
3. Navigate to the sports booking page in DingTalk.
4. You're ready when the status shows "Ready".

**Step 2: Select a Time Slot**

Choose your desired time slot from the dropdown (single-hour and two-hour blocks supported).

**Step 3: Start Scheduled Booking**

Click "Schedule Booking" and the app will count down in the background, firing requests exactly at 20:00. Results appear as a popup; detailed logs are saved to `~/Library/Logs/ddAutoSub/`.

### Advanced Configuration

Edit `ddAutoSubV6.py` to modify the following built-in defaults:

| Config | Default | Location |
|--------|---------|----------|
| Court numbers | `1,2,3,4,9,10,11,12` | `__init__` -> `self._sites` |
| 403 retry count | `3` | `__init__` -> `self._max_403_retries` |
| Booking date | Today + 2 days | `__init__` -> `self._date` |
| Venue name | 综合馆羽毛球 | `start_task` -> `config` |

### Build as Standalone App

To distribute to users without a Python environment:

```bash
# Install PyInstaller
pip install pyinstaller

# Build (no console window)
python3 -m PyInstaller --windowed --name "无敌抢场王" --clean ddAutoSubV6.py

# Output at dist/无敌抢场王.app
```

> Users still need to install mitmproxy and trust the CA certificate.

### FAQ

**Q: "mitmproxy not detected" when clicking "Capture Credentials"**

A: Run `pip install mitmproxy` in terminal and try again.

**Q: Credential capture keeps failing**

A: Check the following:
1. mitmproxy CA certificate is trusted (Keychain Access -> search "mitmproxy" -> Get Info -> Trust -> Always Trust)
2. System proxy is configured (System Preferences -> Network -> Advanced -> Proxies -> Web Proxy and Secure Web Proxy)
3. DingTalk is fully quit before reopening

**Q: It's past 20:00 but booking failed**

A: Check the log file in `~/Library/Logs/ddAutoSub/`. Common reasons:
- `403 Forbidden` — Token expired; re-capture credentials.
- `校验失败` (validation failed) — The time slot has been taken.
- `连接失败` (connection failed) — Network issue; check VPN or campus network.

**Q: Double-clicking `.app` does nothing**

A: Ensure mitmproxy is installed and the CA certificate is trusted. Check `~/Library/Logs/ddAutoSub/` for log files — if they exist, the app launched but may have encountered an error.

### Project Structure

```
ddAutoSub/
├── ddAutoSubV5.py          # V5: Multi-court concurrency + auto 403 retry
├── ddAutoSubV6.py          # V6: V5 base + one-click capture + minimal UI
├── 无敌抢场王.spec          # PyInstaller build config
├── README.md               # This file
└── dist/
    └── 无敌抢场王.app       # macOS packaged app
```

### Version History

| Version | Key Improvements |
|---------|-----------------|
| V5 | Multi-court concurrency, auto 403 token refresh, staggered timing |
| V6 | One-click credential capture, minimal UI, log path fix, macOS packaging |

### License

[MIT License](LICENSE)

> This project is for educational purposes only. Use responsibly.
