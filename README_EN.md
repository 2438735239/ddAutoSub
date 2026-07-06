# Invincible Court Booker

> An automated badminton court booking tool for Hangzhou Dianzi University Sports Complex.

A Python-based desktop application that automatically captures authentication credentials from DingTalk and books badminton courts precisely at 20:00 each night — no more manual booking struggles.

---

## Features

- **One-Click Credential Capture** — Auto-launches mitmproxy to capture Token and User-Agent; no manual copy-paste needed.
- **Scheduled Execution** — Waits in the background and fires requests exactly at 20:00 each night.
- **Multi-Court Concurrency** — Sends requests for multiple court numbers simultaneously, dramatically boosting success rate.
- **Automatic 403 Retry** — Refreshes expired tokens and retries automatically; no manual intervention required.
- **Minimal UI** — Only the time-slot selector and two buttons. Zero clutter.
- **Persistent Logging** — Detailed logs for each run saved to `~/Library/Logs/ddAutoSub/`.

---

## Requirements

| Dependency | Version | Notes |
|------------|---------|-------|
| macOS | 12.0+ | macOS only |
| Python | 3.9+ | 3.11 recommended |
| mitmproxy | 9.x | `pip install mitmproxy` |
| DingTalk | Latest | Required for accessing the sports booking page |

---

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/2438735239/ddAutoSub.git
cd ddAutoSub
```

### 2. Install Python dependencies

```bash
pip install requests mitmproxy
```

### 3. Generate and trust the mitmproxy CA certificate (one-time setup)

```bash
# Generate certificate
mitmdump
# Press Ctrl+C after seeing "HTTP(S) proxy listening at *:8080"

# Trust the certificate
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain \
  ~/.mitmproxy/mitmproxy-ca-cert.pem
```

### 4. Launch the app

```bash
python3 ddAutoSubV6.py
```

---

## Usage

### Step 1: Capture Credentials

1. Click the "Capture Credentials" button.
2. The app will automatically:
   - Start mitmproxy on port 8080
   - Configure the system HTTP/HTTPS proxy
   - Restart DingTalk
3. Navigate to the sports booking page in DingTalk.
4. You're ready when the status shows "Ready".

### Step 2: Select a Time Slot

Choose your desired time slot from the dropdown (single-hour and two-hour blocks supported).

### Step 3: Start Scheduled Booking

Click "Schedule Booking" and the app will count down in the background, firing requests exactly at 20:00. Results appear as a popup; detailed logs are saved to `~/Library/Logs/ddAutoSub/`.

---

## Advanced Configuration

Edit `ddAutoSubV6.py` to modify the following built-in defaults:

| Config | Default | Location |
|--------|---------|----------|
| Court numbers | `1,2,3,4,9,10,11,12` | `__init__` -> `self._sites` |
| 403 retry count | `3` | `__init__` -> `self._max_403_retries` |
| Booking date | Today + 2 days | `__init__` -> `self._date` |
| Venue name | 综合馆羽毛球 | `start_task` -> `config` |

---

## Build as Standalone App

To distribute to users without a Python environment:

```bash
# Install PyInstaller
pip install pyinstaller

# Build (no console window)
python3 -m PyInstaller --windowed --name "无敌抢场王" --clean ddAutoSubV6.py

# Output at dist/无敌抢场王.app
```

> Users still need to install mitmproxy and trust the CA certificate.

---

## FAQ

### Q: "mitmproxy not detected" when clicking "Capture Credentials"

A: Run `pip install mitmproxy` in terminal and try again.

### Q: Credential capture keeps failing

A: Check the following:
1. mitmproxy CA certificate is trusted (Keychain Access -> search "mitmproxy" -> Get Info -> Trust -> Always Trust)
2. System proxy is configured (System Preferences -> Network -> Advanced -> Proxies -> Web Proxy and Secure Web Proxy)
3. DingTalk is fully quit before reopening

### Q: It's past 20:00 but booking failed

A: Check the log file in `~/Library/Logs/ddAutoSub/`. Common reasons:
- `403 Forbidden` — Token expired; re-capture credentials.
- `校验失败` (validation failed) — The time slot has been taken.
- `连接失败` (connection failed) — Network issue; check VPN or campus network.

### Q: Double-clicking `.app` does nothing

A: Ensure mitmproxy is installed and the CA certificate is trusted. Check `~/Library/Logs/ddAutoSub/` for log files — if they exist, the app launched but may have encountered an error.

---

## Project Structure

```
ddAutoSub/
├── ddAutoSubV5.py          # V5: Multi-court concurrency + auto 403 retry
├── ddAutoSubV6.py          # V6: V5 base + one-click capture + minimal UI
├── 无敌抢场王.spec          # PyInstaller build config
├── README.md               # This file
└── dist/
    └── 无敌抢场王.app       # macOS packaged app
```

---

## Version History

| Version | Key Improvements |
|---------|-----------------|
| V5 | Multi-court concurrency, auto 403 token refresh, staggered timing |
| V6 | One-click credential capture, minimal UI, log path fix, macOS packaging |

---

## License

[MIT License](LICENSE)

> This project is for educational purposes only. Use responsibly.
