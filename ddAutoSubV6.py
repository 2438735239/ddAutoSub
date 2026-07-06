import tkinter as tk
from tkinter import ttk, messagebox
import requests
import json
import time
from datetime import datetime, timedelta
import threading
import urllib3
import logging
from json import JSONDecodeError
import subprocess
import shutil
import tempfile
import os
import signal

# 屏蔽 SSL 证书校验警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==================== 日志系统 ====================
import os as _os

# 日志写入用户目录，兼容双击启动（工作目录为 / 的情况）
_log_dir = _os.path.expanduser("~/Library/Logs/ddAutoSub")
_os.makedirs(_log_dir, exist_ok=True)
log_filename = _os.path.join(
    _log_dir,
    f"抢场日志_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
)

logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    encoding="utf-8",
    format="%(asctime)s - %(message)s"
)


# ==================== mitmproxy 抓包 Addon 脚本 ====================
# 这个脚本会被写入临时文件，由 mitmdump 加载执行
CAPTURE_ADDON_TEMPLATE = '''
import json
import os

OUTPUT_FILE = {output_file!r}

class CaptureAddon:
    def request(self, flow):
        try:
            host = flow.request.pretty_host
            if "sportmeta" not in host:
                return

            headers = dict(flow.request.headers)
            auth = headers.get("authorization", "") or headers.get("Authorization", "")
            ua = headers.get("user-agent", "") or headers.get("User-Agent", "")

            if not auth:
                return

            # 提取 Bearer token
            token = ""
            auth_lower = auth.lower()
            if auth_lower.startswith("bearer "):
                token = auth.split(" ", 1)[1]
            elif auth_lower.startswith("bearer"):
                token = auth[6:].strip()

            if not token:
                return

            data = {{
                "token": token,
                "user_agent": ua,
                "host": host,
                "url": flow.request.pretty_url
            }}

            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # 只抓第一次就足够了
            import mitmproxy.ctx
            mitmproxy.ctx.log.info(f"✅ 已捕获 Token (长度:{{len(token)}}) 来自 {{host}}")
        except Exception:
            pass

addons = [CaptureAddon()]
'''


# ==================== Token 自动抓取器 ====================

class TokenCapturer:
    """管理 mitmproxy 生命周期，自动抓取钉钉预约页面的 Bearer Token 和 User-Agent"""

    MITMDUMP_PORT = 8080

    def __init__(self, log_callback=print):
        self.log = log_callback
        self.process = None
        self.capture_file = None
        self.network_service = None
        self._capture_addon_path = None
        self._mitmdump_path = None

    # ── 环境检查 ──────────────────────────────

    @staticmethod
    def _find_mitmdump():
        """
        查找 mitmdump 可执行文件路径。
        .app 双击启动时 PATH 不含用户 Python bin 目录，需要手动搜索。
        """
        # 1. 先按 PATH 找
        found = shutil.which("mitmdump")
        if found:
            return found

        # 2. 搜索常见 Python bin 目录
        candidates = []
        home = os.path.expanduser("~")
        for py_ver in ["3.12", "3.11", "3.10", "3.9", "3.8"]:
            candidates.append(os.path.join(home, f"Library/Python/{py_ver}/bin/mitmdump"))
        candidates.append("/usr/local/bin/mitmdump")

        for c in candidates:
            if os.path.isfile(c) and os.access(c, os.X_OK):
                return c

        return None

    def check_prerequisites(self):
        """
        检查 mitmdump 是否已安装、CA 证书是否存在。
        返回 (ok: bool, message: str)
        """
        self._mitmdump_path = self._find_mitmdump()
        if not self._mitmdump_path:
            return False, (
                "未检测到 mitmproxy，请先安装：\n\n"
                "    pip install mitmproxy\n\n"
                "安装后在终端执行一次 mitmdump 以生成 CA 证书。"
            )

        # 检查 CA 证书目录
        cert_dir = os.path.expanduser("~/.mitmproxy")
        if not os.path.isdir(cert_dir):
            return False, (
                "mitmproxy CA 证书尚未生成。\n\n"
                "请在终端执行一次：\n"
                "    mitmdump\n"
                "然后按 Ctrl+C 退出，证书会自动生成到 ~/.mitmproxy/"
            )

        # 检查是否有证书文件
        cert_files = [f for f in os.listdir(cert_dir) if f.endswith(".pem")]
        if not cert_files:
            return False, (
                "未找到 mitmproxy CA 证书文件。\n\n"
                "请在终端执行一次：\n"
                "    mitmdump\n"
                "然后按 Ctrl+C 退出即可。"
            )

        return True, ""

    def _detect_network_service(self):
        """探测当前活跃的 macOS 网络服务名称"""
        try:
            result = subprocess.run(
                ["networksetup", "-listallnetworkservices"],
                capture_output=True, text=True, timeout=5
            )
            services = result.stdout.strip().split("\n")
            # 第一行是标题 "An asterisk...", 跳过
            for s in services:
                s = s.strip()
                if not s or s.startswith("An asterisk"):
                    continue
                # 优先 Wi-Fi
                if "Wi-Fi" in s:
                    return s
            # 否则返回第一个有效服务
            for s in services:
                s = s.strip()
                if s and not s.startswith("An asterisk"):
                    return s
        except Exception:
            pass
        return "Wi-Fi"  # 兜底默认值

    def _get_proxy_state(self):
        """获取当前代理状态"""
        svc = self.network_service
        try:
            http = subprocess.run(
                ["networksetup", "-getwebproxy", svc],
                capture_output=True, text=True, timeout=5
            )
            https = subprocess.run(
                ["networksetup", "-getsecurewebproxy", svc],
                capture_output=True, text=True, timeout=5
            )
            http_enabled = "Enabled: Yes" in http.stdout
            https_enabled = "Enabled: Yes" in https.stdout
            return {"http": http_enabled, "https": https_enabled}
        except Exception:
            return {"http": False, "https": False}

    def _set_proxy(self, enable: bool):
        """设置或关闭系统 HTTP/HTTPS 代理"""
        svc = self.network_service
        if enable:
            cmds = [
                ["networksetup", "-setwebproxy", svc, "127.0.0.1", str(self.MITMDUMP_PORT)],
                ["networksetup", "-setsecurewebproxy", svc, "127.0.0.1", str(self.MITMDUMP_PORT)],
            ]
        else:
            cmds = [
                ["networksetup", "-setwebproxystate", svc, "off"],
                ["networksetup", "-setsecurewebproxystate", svc, "off"],
            ]

        for cmd in cmds:
            try:
                subprocess.run(cmd, capture_output=True, timeout=10)
            except Exception as e:
                self.log(f"⚠️ 代理设置命令失败: {' '.join(cmd)} — {e}")

    # ── 主流程 ────────────────────────────────

    def start(self):
        """
        启动抓包流程。返回 (ok: bool, message: str)
        成功时在后台运行 mitmdump，等待捕获。
        """
        # 1. 环境检查
        ok, msg = self.check_prerequisites()
        if not ok:
            return False, msg

        # 2. 探测网络服务
        self.network_service = self._detect_network_service()
        self.log(f"🌐 当前网络服务: {self.network_service}")

        # 3. 保存原始代理状态
        self.original_proxy = self._get_proxy_state()

        # 4. 创建捕获输出文件
        fd, self.capture_file = tempfile.mkstemp(suffix=".json", prefix="ddautosub_capture_")
        os.close(fd)
        # 确保文件一开始不存在（mitmproxy addon 会创建它）
        if os.path.exists(self.capture_file):
            os.remove(self.capture_file)

        # 5. 写入 addon 脚本
        fd, self._capture_addon_path = tempfile.mkstemp(suffix=".py", prefix="ddautosub_addon_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(CAPTURE_ADDON_TEMPLATE.format(output_file=self.capture_file))

        # 6. 启动 mitmdump（用完整路径，兼容 .app 双击启动）
        try:
            self.process = subprocess.Popen(
                [self._mitmdump_path, "-s", self._capture_addon_path, "--quiet",
                 "-p", str(self.MITMDUMP_PORT)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid  # 创建独立进程组，方便后续 kill
            )
            # 等待 mitmdump 启动
            time.sleep(1.5)
            if self.process.poll() is not None:
                return False, "mitmdump 启动失败，请检查端口 8080 是否被占用"
            self.log(f"✅ mitmdump 已启动 (端口 {self.MITMDUMP_PORT})")
        except Exception as e:
            return False, f"启动 mitmdump 失败: {e}"

        # 7. 设置系统代理
        self._set_proxy(True)
        self.log(f"🔧 系统代理已设置为 127.0.0.1:{self.MITMDUMP_PORT}")

        # 8. 重启钉钉（确保新代理生效）
        self._restart_dingtalk()

        return True, ""

    def _restart_dingtalk(self):
        """重启钉钉以确保 WebView 使用新的代理设置"""
        # 先退出现有钉钉
        subprocess.run(["killall", "DingTalk"], capture_output=True)
        time.sleep(1)

        # 重新启动钉钉
        try:
            subprocess.Popen(["open", "-a", "DingTalk"])
            self.log("🚀 钉钉已重新启动")
        except Exception as e:
            self.log(f"⚠️ 启动钉钉失败: {e}")

    def check_result(self):
        """
        轮询检查是否已捕获到数据。
        返回 (token: str|None, user_agent: str|None)
        """
        if not self.capture_file or not os.path.exists(self.capture_file):
            return None, None

        try:
            with open(self.capture_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            token = data.get("token", "")
            ua = data.get("user_agent", "")
            if token:
                self.log(f"🎯 捕获成功! Token 长度:{len(token)}, 来源:{data.get('host', '?')}")
                return token, ua
        except (json.JSONDecodeError, IOError):
            pass

        return None, None

    def stop(self):
        """停止抓包，恢复系统代理，清理临时文件"""
        # 恢复系统代理
        if self.network_service:
            self._set_proxy(False)
            self.log("🔧 系统代理已恢复")

        # 停止 mitmdump
        if self.process and self.process.poll() is None:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                self.process.wait(timeout=5)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.log("🛑 mitmdump 已停止")

        # 清理临时文件
        for path in [self.capture_file, self._capture_addon_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass


# ==================== 后端逻辑 ====================

class HDUSportsBooker:
    def __init__(self, token, user_agent, openid="241080010", nickname="项利豪", phone="18457777858",
                 log_callback=print, max_403_retries=3, token_refresh_endpoint=None):
        self.base_url = "https://sportmeta.hdu.edu.cn"
        self.token = token
        self.user_agent = user_agent
        self.max_403_retries = max_403_retries
        self.token_refresh_endpoint = token_refresh_endpoint
        self.headers = self._build_headers(token, user_agent)
        self.user_info = {
            "openid": openid,
            "nickname": nickname,
            "phone": phone
        }
        self.log = log_callback

    def _build_headers(self, token, user_agent):
        """构建请求头"""
        return {
            "Host": "sportmeta.hdu.edu.cn",
            "Accept": "*/*",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": user_agent,
            "Referer": "https://sportmeta.hdu.edu.cn/book/dingtalk/?v=1.0.16",
            "Connection": "keep-alive"
        }

    def build_payload(self, date, venue_name, venue_type, site_id, time_list, start_time, end_time):
        return {
            "orderData": {
                "openid": self.user_info["openid"],
                "nickname": self.user_info["nickname"],
                "phone": self.user_info["phone"],
                "date": date,
                "venue_name": venue_name,
                "venue_type": venue_type,
                "site_id": site_id,
                "total_price": 0,
                "time_list": time_list,
                "start_time": start_time,
                "end_time": end_time
            }
        }

    def write_log(self, msg):
        self.log(msg)
        logging.info(msg)

    # ==================== Token/Header 刷新机制 ====================

    def refresh_token_and_headers(self):
        """
        尝试重新获取有效的 Token 和 Header。
        策略优先级:
        1. 如果配置了 token_refresh_endpoint，向该端点请求新 token
        2. 否则访问主页面 https://sportmeta.hdu.edu.cn/book/dingtalk/ 获取新的 session/cookie
        3. 从响应中尝试提取新的 Authorization token
        返回: (new_token, new_headers) 或 (None, None)
        """
        session = requests.Session()

        # 策略 1: 配置了专用 refresh endpoint
        if self.token_refresh_endpoint:
            try:
                self.write_log("🔄 [Token刷新] 尝试从 refresh endpoint 获取新 Token...")
                resp = session.get(
                    self.token_refresh_endpoint,
                    headers={
                        "User-Agent": self.user_agent,
                        "Accept": "application/json",
                        "Referer": "https://sportmeta.hdu.edu.cn/book/dingtalk/?v=1.0.16",
                    },
                    timeout=5,
                    verify=False
                )
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        new_token = data.get("token") or data.get("access_token") or data.get("data", {}).get("token")
                        if new_token:
                            self.write_log(f"✅ [Token刷新] 成功获取新 Token (长度:{len(str(new_token))})")
                            new_headers = self._build_headers(new_token, self.user_agent)
                            # 合并 session cookies
                            for cookie in session.cookies:
                                pass  # cookies 由 session 自动管理
                            self.token = new_token
                            self.headers = new_headers
                            return new_token, new_headers
                    except JSONDecodeError:
                        # 可能返回的不是 JSON，尝试从文本中提取
                        pass
            except Exception as e:
                self.write_log(f"⚠️ [Token刷新] refresh endpoint 请求失败: {str(e)[:100]}")

        # 策略 2: 访问主页面获取新的 session 和可能的 token
        try:
            self.write_log("🔄 [Token刷新] 尝试从主页面获取新 Session/Token...")
            main_url = "https://sportmeta.hdu.edu.cn/book/dingtalk/?v=1.0.16"
            resp = session.get(
                main_url,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Referer": "https://sportmeta.hdu.edu.cn/",
                },
                timeout=8,
                verify=False
            )

            if resp.status_code == 200:
                # 尝试从页面中提取 token
                page_text = resp.text
                import re

                # 常见 token 格式: Bearer xxx, token=xxx, "token":"xxx"
                token_patterns = [
                    r'["\']token["\']\s*[:=]\s*["\']([^"\']+)["\']',
                    r'bearer\s+([A-Za-z0-9\-_.]+)',
                    r'access_token["\']?\s*[:=]\s*["\']([^"\']+)["\']',
                ]

                extracted_token = None
                for pattern in token_patterns:
                    match = re.search(pattern, page_text, re.IGNORECASE)
                    if match:
                        extracted_token = match.group(1)
                        break

                if extracted_token:
                    self.write_log(f"✅ [Token刷新] 从主页面提取到 Token (长度:{len(extracted_token)})")
                    self.token = extracted_token
                    self.headers = self._build_headers(extracted_token, self.user_agent)
                    return extracted_token, self.headers

                # 即使没提取到 token，也可能获得了新的 session/cookie
                # 更新 headers，合并从 session 获得的 cookie
                cookies_dict = session.cookies.get_dict()
                if cookies_dict:
                    cookie_str = "; ".join([f"{k}={v}" for k, v in cookies_dict.items()])
                    self.headers["Cookie"] = cookie_str
                    self.write_log(f"🔄 [Token刷新] 已更新 Session Cookie ({len(cookies_dict)} 项)")
                    return self.token, self.headers
                else:
                    self.write_log("⚠️ [Token刷新] 主页面未返回有效 Cookie/Token")

            else:
                self.write_log(f"⚠️ [Token刷新] 主页面返回状态码: {resp.status_code}")

        except requests.exceptions.Timeout:
            self.write_log("⚠️ [Token刷新] 主页面请求超时")
        except Exception as e:
            self.write_log(f"⚠️ [Token刷新] 主页面请求异常: {str(e)[:100]}")

        self.write_log("❌ [Token刷新] 所有刷新策略均失败")
        return None, None

    def _handle_403_retry(self, request_func, url, payload, site_id, operation_name):
        """
        处理 403 并带 Token 刷新的重试逻辑。

        Args:
            request_func: 实际发起 HTTP 请求的函数
            url: 请求 URL
            payload: 请求体
            site_id: 场地 ID
            operation_name: 操作名称（用于日志）

        Returns:
            (success: bool, response: requests.Response or None)
        """
        for retry_attempt in range(self.max_403_retries + 1):
            try:
                response = requests.post(
                    url,
                    headers=self.headers,
                    data=json.dumps(payload),
                    timeout=5,
                    verify=False
                )

                # 如果不是 403，直接返回
                if response.status_code != 403:
                    return True, response

                # 是 403 —— 尝试刷新 Token 后重试
                if retry_attempt < self.max_403_retries:
                    self.write_log(
                        f"⚠️ [场地 {site_id}] {operation_name} 遭遇 403 Forbidden "
                        f"(第 {retry_attempt + 1}/{self.max_403_retries} 次)，正在刷新 Token..."
                    )

                    new_token, new_headers = self.refresh_token_and_headers()

                    if new_headers:
                        self.write_log(
                            f"🔄 [场地 {site_id}] Token 已刷新，立即重试 {operation_name}..."
                        )
                        continue  # 用新 headers 重试
                    else:
                        self.write_log(
                            f"❌ [场地 {site_id}] Token 刷新失败，{operation_name} 放弃重试"
                        )
                        return False, response
                else:
                    self.write_log(
                        f"❌ [场地 {site_id}] {operation_name} 403 重试 {self.max_403_retries} 次后仍失败"
                    )
                    return False, response

            except requests.exceptions.Timeout:
                self.write_log(f"[场地 {site_id}] {operation_name} 请求超时")
                return False, None
            except requests.exceptions.ConnectionError as e:
                self.write_log(f"[场地 {site_id}] {operation_name} 连接失败: {str(e)[:100]}")
                return False, None
            except Exception as e:
                self.write_log(f"[场地 {site_id}] {operation_name} 未知异常: {type(e).__name__} - {str(e)[:100]}")
                return False, None

        return False, None

    def check_book_info(self, payload):
        url = f"{self.base_url}/book/client/creat_book_info"
        site_id = payload["orderData"]["site_id"]

        success, response = self._handle_403_retry(
            requests.post, url, payload, site_id, "校验(creat_book_info)"
        )

        if not success:
            return False

        if response is None:
            return False

        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            status = response.status_code
            if status != 403:  # 403 已经在 _handle_403_retry 里处理过了
                self.write_log(
                    f"[场地 {site_id}] HTTP错误 | 状态码:{status} | {e}"
                )
            return False

        try:
            res_data = response.json()
        except JSONDecodeError:
            raw_text = response.text[:200]
            self.write_log(
                f"[场地 {site_id}] 校验失败 | 响应非JSON | "
                f"状态码:{response.status_code} | 响应原文:{raw_text}"
            )
            return False

        success_msg = res_data.get("message", "")
        if "预约成功" in success_msg or success_msg == "预约成功":
            self.write_log(f"[场地 {site_id}] 校验通过，准备下单")
            return True
        else:
            self.write_log(
                f"[场地 {site_id}] 校验失败 | 状态码:{response.status_code} | 返回:{res_data}"
            )
            return False

    def create_order(self, payload):
        url = f"{self.base_url}/book/client/creat_order"
        site_id = payload["orderData"]["site_id"]

        success, response = self._handle_403_retry(
            requests.post, url, payload, site_id, "下单(creat_order)"
        )

        if not success:
            return False

        if response is None:
            return False

        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            status = response.status_code
            if status != 403:
                self.write_log(
                    f"[场地 {site_id}] HTTP错误 | 状态码:{status} | {e}"
                )
            return False

        try:
            res_data = response.json()
        except JSONDecodeError:
            raw_text = response.text[:200]
            self.write_log(
                f"[场地 {site_id}] 下单失败 | 响应非JSON | "
                f"状态码:{response.status_code} | 响应原文:{raw_text}"
            )
            return False

        if res_data.get("status") == "success":
            order_num = res_data.get("data", {}).get("order_num")
            self.write_log(f"🎉 [场地 {site_id}] 抢场成功！订单号:{order_num}")
            return True
        else:
            self.write_log(
                f"[场地 {site_id}] 下单失败 | 状态码:{response.status_code} | 返回:{res_data}"
            )
            return False


# ==================== GUI ====================

class BookingApp:
    # ── 配色系统 · 现代简约风 ──────────────────
    COLORS = {
        "bg":           "#F5F5F7",   # 页面背景 (Apple-like)
        "shadow":       "#E5E5EA",   # 卡片阴影
        "card_bg":      "#FFFFFF",   # 卡片背景
        "card_border":  "#F0F0F3",   # 卡片边框
        "label":        "#1D1D1F",   # 标签文字
        "muted":        "#86868B",   # 次要文字
        "accent":       "#5E5CE6",   # 主强调色 (Indigo)
        "accent_hover": "#4B49D6",   # 悬停
        "accent_press": "#3E3CC0",   # 按下
        "success":      "#30D158",   # 成功绿
        "warning":      "#FF9F0A",   # 警告橙
        "input_bg":     "#F9F9FB",   # 输入框背景
        "input_focus":  "#F0EEFF",   # 输入框聚焦
    }

    def __init__(self, root):
        self.root = root
        self.root.title("无敌抢场王 V6")
        self.root.geometry("400x340")
        self.root.resizable(False, False)
        self.root.configure(bg=self.COLORS["bg"])

        # ── ttk 样式 · 现代简约 ─────────────────
        style = ttk.Style()
        style.theme_use("clam")
        default_font = ("SF Pro Display", 12)
        self.root.option_add("*Font", default_font)

        # 标签
        style.configure("Card.TLabel",
                        background=self.COLORS["card_bg"],
                        foreground=self.COLORS["label"],
                        font=("SF Pro Display", 12, "bold"))

        # Combobox
        style.configure("Modern.TCombobox",
                        fieldbackground=self.COLORS["input_bg"],
                        background=self.COLORS["card_bg"],
                        foreground=self.COLORS["label"],
                        arrowcolor=self.COLORS["accent"],
                        borderwidth=10,
                        relief="flat",
                        font=("SF Pro Display", 13))
        style.map("Modern.TCombobox",
                  fieldbackground=[("focus", self.COLORS["input_focus"])],
                  foreground=[("focus", self.COLORS["label"])])

        # 主按钮
        style.configure("Accent.TButton",
                        background=self.COLORS["accent"],
                        foreground="#FFFFFF",
                        borderwidth=0,
                        relief="flat",
                        font=("SF Pro Display", 13, "bold"),
                        padding=(20, 12))
        style.map("Accent.TButton",
                  background=[("active", self.COLORS["accent_hover"]),
                              ("pressed", self.COLORS["accent_press"]),
                              ("disabled", "#C7C7CC")],
                  foreground=[("disabled", "#FFFFFF")])

        # 抓取按钮
        style.configure("Capture.TButton",
                        background=self.COLORS["card_bg"],
                        foreground=self.COLORS["accent"],
                        borderwidth=1,
                        relief="flat",
                        font=("SF Pro Display", 12, "bold"),
                        padding=(16, 10))
        style.map("Capture.TButton",
                  background=[("active", self.COLORS["input_focus"]),
                              ("pressed", "#E8E6FF"),
                              ("disabled", self.COLORS["card_bg"])],
                  foreground=[("disabled", "#C7C7CC")])

        # 时间段选项
        self.real_times = [
            "08:00", "09:00", "10:00", "11:00",
            "11:40", "13:20", "14:00", "15:00",
            "16:00", "17:00", "18:00", "19:00",
            "20:00", "21:00"
        ]
        self.time_options = {}
        for i in range(len(self.real_times) - 1):
            start, end = self.real_times[i], self.real_times[i + 1]
            self.time_options[f"[{i}] {start}-{end}"] = ([i], start, end)
        for i in range(len(self.real_times) - 2):
            start, end = self.real_times[i], self.real_times[i + 2]
            self.time_options[f"[{i},{i+1}] {start}-{end}"] = ([i, i + 1], start, end)

        # ── 状态 ────────────────────────────────
        self.is_running = False
        self.global_success = False
        self.capturer = None
        self._capture_poll_id = None

        # ── 内部状态 ────────────────────────────
        self._captured_token = ""
        self._captured_ua = ""
        self._date = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
        self._sites = [1, 2, 3, 4, 9, 10, 11, 12]
        self._max_403_retries = 3

        self.setup_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_ui(self):
        C = self.COLORS
        bg, card = C["bg"], C["card_bg"]

        # ── 标题区 ──────────────────────────────
        header = tk.Frame(self.root, bg=bg)
        header.pack(fill=tk.X, padx=0, pady=(30, 20))

        tk.Label(header, text="无敌抢场王",
                 font=("SF Pro Display", 26, "bold"),
                 fg=C["label"], bg=bg).pack()

        tk.Label(header, text="抓包 · 预约 · 全自动",
                 font=("SF Pro Display", 12),
                 fg=C["muted"], bg=bg).pack(pady=(2, 0))

        # ── 卡片容器 · 带阴影 ─────────────────────
        # 阴影层
        shadow = tk.Frame(self.root, bg=C["shadow"], bd=0,
                          highlightthickness=0)
        shadow.pack(fill=tk.X, padx=22, pady=(0, 0))
        # 卡片主体
        card_frame = tk.Frame(shadow, bg=card, bd=0,
                              highlightbackground=C["card_border"],
                              highlightthickness=1)
        card_frame.pack(fill=tk.X, padx=(2, 2), pady=(2, 4), ipady=16)

        # ── 时间段 ──────────────────────────────
        time_row = tk.Frame(card_frame, bg=card)
        time_row.pack(fill=tk.X, padx=22, pady=(12, 14))

        tk.Label(time_row, text="时间段",
                 font=("SF Pro Display", 12, "bold"),
                 fg=C["label"], bg=card,
                 width=6, anchor="w").pack(side=tk.LEFT)

        self.time_combo = ttk.Combobox(
            time_row,
            values=list(self.time_options.keys()),
            style="Modern.TCombobox",
            width=26,
            state="readonly"
        )
        self.time_combo.current(0)
        self.time_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))

        # ── 分割线 ──────────────────────────────
        sep = tk.Frame(card_frame, bg=C["card_border"], height=1)
        sep.pack(fill=tk.X, padx=22, pady=(0, 14))

        # ── 抓取按钮 ────────────────────────────
        capture_row = tk.Frame(card_frame, bg=card)
        capture_row.pack(fill=tk.X, padx=22, pady=(0, 2))

        self.capture_btn = ttk.Button(
            capture_row,
            text="抓取凭证",
            style="Capture.TButton",
            command=self.start_capture
        )
        self.capture_btn.pack(fill=tk.X, ipady=6)

        # 抓取状态
        self.capture_status = tk.Label(
            card_frame, text="",
            font=("SF Pro Display", 10),
            fg=C["muted"], bg=card
        )
        self.capture_status.pack(pady=(4, 8))

        # ═══ 主按钮 · 卡片外 ─══════════════════════
        btn_frame = tk.Frame(self.root, bg=bg)
        btn_frame.pack(fill=tk.X, padx=22, pady=(18, 14))

        self.start_btn = ttk.Button(
            btn_frame,
            text="定时抢场 · 今晚 20:00",
            style="Accent.TButton",
            command=self.start_task
        )
        self.start_btn.pack(fill=tk.X, ipady=8)

        # ── 底部 ────────────────────────────────
        tk.Label(self.root,
                 text=f"日志  {log_filename}",
                 font=("SF Pro Display", 9),
                 fg=C["muted"], bg=bg).pack(pady=(0, 16))

    def log(self, msg):
        """仅写入日志文件，不显示在 UI 上"""
        logging.info(msg)

    # ==================== 一键抓取 ====================

    def start_capture(self):
        """用户点击「一键抓取」按钮"""
        if self.capturer is not None:
            messagebox.showinfo("提示", "抓取正在进行中，请先在钉钉中打开预约页面...")
            return

        # 禁用抓取按钮，显示进度
        self.capture_btn.config(state="disabled", text="准备中...")
        self.capture_status.config(text="")

        threading.Thread(target=self._capture_thread, daemon=True).start()

    def _capture_thread(self):
        """在后台线程中启动抓包流程"""
        self.capturer = TokenCapturer(log_callback=self.log)

        ok, msg = self.capturer.start()

        if not ok:
            # 启动失败，恢复 UI
            self.capturer = None
            self.root.after(0, lambda: self._on_capture_failed(msg))
            return

        # 启动成功，切换按钮状态并开始轮询
        self.root.after(0, lambda: self._on_capture_started())

        # 开始轮询结果（每 500ms 检查一次）
        self._schedule_poll()

    def _on_capture_started(self):
        """抓取环境准备就绪后的 UI 更新"""
        self.capture_status.config(
            text="👆 请在钉钉中打开体育预约页面",
            fg=self.COLORS["warning"]
        )
        self.capture_btn.config(
            text="等待抓取... 打开钉钉预约页",
            state="disabled"
        )

    def _on_capture_failed(self, msg):
        """抓取启动失败"""
        self.capture_btn.config(text="抓取凭证", state="normal")
        self.capture_status.config(text="")
        messagebox.showerror("抓取失败", msg)

    def _schedule_poll(self):
        """定时轮询抓取结果"""
        if self.capturer is None:
            return

        token, ua = self.capturer.check_result()

        if token:
            # 抓取成功！
            self._on_capture_success(token, ua)
            return

        # 超时检查（2 分钟后停止）
        # 继续轮询
        self._capture_poll_id = self.root.after(500, self._schedule_poll)

    def _on_capture_success(self, token, ua):
        """抓取成功后更新 UI"""
        if self._capture_poll_id:
            self.root.after_cancel(self._capture_poll_id)
            self._capture_poll_id = None

        # 存入内部变量
        self._captured_token = token
        self._captured_ua = ua

        # 清理抓取器
        if self.capturer:
            self.capturer.stop()
            self.capturer = None

        # 恢复 UI
        self.capture_btn.config(
            text="抓取凭证",
            state="normal"
        )
        self.capture_status.config(
            text="已就绪 · 可开始抢场",
            fg=self.COLORS["success"]
        )

        self.log(f"🎉 Token & UA 自动抓取完成 (Token 长度:{len(token)})")

    def cancel_capture(self):
        """取消当前抓取"""
        if self._capture_poll_id:
            self.root.after_cancel(self._capture_poll_id)
            self._capture_poll_id = None

        if self.capturer:
            self.capturer.stop()
            self.capturer = None

        self.capture_btn.config(text="抓取凭证", state="normal")
        self.capture_status.config(text="")

    def on_closing(self):
        """窗口关闭时清理抓包后台进程"""
        self.cancel_capture()
        self.root.destroy()

    # ==================== 抢场逻辑 ====================

    def start_task(self):
        if self.is_running:
            return

        token = self._captured_token
        ua = self._captured_ua

        if not token or not ua:
            messagebox.showerror("错误", "请先点击「一键抓取」获取 Token 和 UA")
            return

        self.is_running = True
        self.global_success = False
        self.start_btn.config(state="disabled")

        time_list, start_time, end_time = self.time_options[self.time_combo.get()]

        config = {
            "date": self._date,
            "venue_name": "综合馆羽毛球",
            "venue_type": "badminton",
            "time_list": time_list,
            "start_time": start_time,
            "end_time": end_time
        }

        target_sites = self._sites
        max_403_retries = self._max_403_retries
        refresh_url = None

        threading.Thread(target=self.wait_and_run,
                          args=(token, ua, config, target_sites,
                                max_403_retries, refresh_url),
                          daemon=True).start()

    def wait_and_run(self, token, ua, config, target_sites, max_403_retries, refresh_url):
        self.log(f"任务已启动，等待20:00开抢 | 场地:{target_sites} | 403重试次数:{max_403_retries}")
        if refresh_url:
            self.log(f"🔗 Token刷新端点: {refresh_url}")
        else:
            self.log("🔗 Token刷新策略: 自动访问主页面获取")

        target = datetime.now().replace(hour=20, minute=0, second=0, microsecond=0)

        while datetime.now() < target:
            time.sleep(0.1)

        self.log("⏰ 时间到，开始冲锋")

        threads = []

        for sid in target_sites:
            cfg = config.copy()
            cfg["site_id"] = sid

            t = threading.Thread(target=self.site_worker,
                                  args=(token, ua, cfg, max_403_retries, refresh_url))
            threads.append(t)
            t.start()
            time.sleep(0.08)

        for t in threads:
            t.join()

        self.is_running = False

        def done():
            self.start_btn.config(state="normal")

            if self.global_success:
                messagebox.showinfo("完成", "🎉 已成功抢到场地")
            else:
                messagebox.showwarning("失败", f"❌ 全部失败，详情见日志文件：{log_filename}")

        self.root.after(0, done)

    def site_worker(self, token, ua, cfg, max_403_retries, refresh_url):
        booker = HDUSportsBooker(
            token, ua,
            log_callback=self.log,
            max_403_retries=max_403_retries,
            token_refresh_endpoint=refresh_url
        )
        payload = booker.build_payload(**cfg)

        for i in range(10):
            if self.global_success:
                return

            if booker.check_book_info(payload):
                if booker.create_order(payload):
                    self.global_success = True
                    return

            time.sleep(0.15)


if __name__ == "__main__":
    root = tk.Tk()
    app = BookingApp(root)
    root.mainloop()
