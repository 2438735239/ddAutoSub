import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import requests
import json
import time
from datetime import datetime, timedelta
import threading
import urllib3
import logging
from json import JSONDecodeError

# 屏蔽 SSL 证书校验警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==================== 日志系统 ====================
log_filename = f"抢场日志_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    encoding="utf-8",
    format="%(asctime)s - %(message)s"
)


# ==================== 后端逻辑 ====================

class HDUSportsBooker:
    def __init__(self, token, user_agent, openid="XXX", nickname="XXX", phone="XXX",
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
        if "预约成功" in success_msg or success_msg == "\u9884\u7ea6\u6210\u529f":
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
    # ── 配色系统 ──────────────────────────────
    COLORS = {
        "bg":           "#F0F2F5",   # 页面背景
        "card_bg":      "#FFFFFF",   # 卡片背景
        "card_border":  "#DDE1E6",   # 卡片边框
        "label":        "#4A5568",   # 标签文字
        "text":         "#2D3748",   # 正文
        "muted":        "#A0AEC0",   # 次要文字
        "accent":       "#4F46E5",   # 主强调色
        "accent_hover": "#4338CA",   # 悬停
        "accent_press": "#3730A3",   # 按下
        "success":      "#10B981",   # 成功绿
        "input_bg":     "#F7F8FA",   # 输入框背景
        "input_focus":  "#EEF2FF",   # 输入框聚焦
        "input_border": "#CBD5E0",   # 输入框边框
        "scroll_bg":    "#1E293B",   # 日志区背景
        "scroll_fg":    "#E2E8F0",   # 日志区文字
        "warn":         "#F59E0B",   # 警告橙
        "error":        "#EF4444",   # 错误红
    }

    def __init__(self, root):
        self.root = root
        self.root.title("无敌抢场王 V5 · 403自动刷新重试")
        self.root.geometry("560x780")
        self.root.resizable(False, False)
        self.root.configure(bg=self.COLORS["bg"])

        # ── 全局 ttk 样式 ──────────────────────
        style = ttk.Style()
        style.theme_use("clam")

        # 基础字体
        default_font = ("Segoe UI", 12)
        self.root.option_add("*Font", default_font)

        # 标签样式
        style.configure("Card.TLabel",
                        background=self.COLORS["card_bg"],
                        foreground=self.COLORS["label"],
                        font=("Segoe UI", 12, "bold"))

        # 副标题
        style.configure("Muted.TLabel",
                        background=self.COLORS["bg"],
                        foreground=self.COLORS["muted"],
                        font=("Segoe UI", 10))

        # Entry 样式
        style.configure("Modern.TEntry",
                        fieldbackground=self.COLORS["input_bg"],
                        borderwidth=8,
                        relief="flat",
                        font=("SF Mono", 11))

        style.map("Modern.TEntry",
                  fieldbackground=[("focus", self.COLORS["input_focus"])])

        # Combobox 样式
        style.configure("Modern.TCombobox",
                        fieldbackground=self.COLORS["input_bg"],
                        background=self.COLORS["card_bg"],
                        arrowcolor=self.COLORS["accent"],
                        borderwidth=8,
                        relief="flat")

        style.map("Modern.TCombobox",
                  fieldbackground=[("focus", self.COLORS["input_focus"])],
                  foreground=[("focus", self.COLORS["text"])])

        # 强调按钮样式
        style.configure("Accent.TButton",
                        background=self.COLORS["accent"],
                        foreground="#FFFFFF",
                        borderwidth=0,
                        relief="flat",
                        font=("Segoe UI", 13, "bold"),
                        padding=(20, 10))

        style.map("Accent.TButton",
                  background=[("active", self.COLORS["accent_hover"]),
                              ("pressed", self.COLORS["accent_press"]),
                              ("disabled", self.COLORS["muted"])],
                  foreground=[("disabled", "#E2E8F0")])

        # 新时间段
        self.real_times = [
            "08:00", "09:00", "10:00", "11:00",
            "11:40", "13:20", "14:00", "15:00",
            "16:00", "17:00", "18:00", "19:00",
            "20:00", "21:00"
        ]

        self.time_options = {}

        # 单小时段
        for i in range(len(self.real_times) - 1):
            start = self.real_times[i]
            end = self.real_times[i + 1]
            self.time_options[f"[{i}] {start}-{end}"] = ([i], start, end)

        # 连续两小时段
        for i in range(len(self.real_times) - 2):
            start = self.real_times[i]
            end = self.real_times[i + 2]
            self.time_options[f"[{i},{i+1}] {start}-{end}"] = ([i, i + 1], start, end)

        self.is_running = False
        self.global_success = False

        self.setup_ui()

    def setup_ui(self):
        bg = self.COLORS["bg"]
        card = self.COLORS["card_bg"]

        # ═══ 顶部标题栏 ═══════════════════════════
        header = tk.Frame(self.root, bg=bg)
        header.pack(fill=tk.X, padx=0, pady=(20, 10))

        tk.Label(header, text="⚡ 无敌抢场王 V5",
                 font=("Segoe UI", 22, "bold"),
                 fg=self.COLORS["accent"], bg=bg).pack()

        tk.Label(header, text="多场地并发 · 错峰秒杀 · 403自动刷新重试",
                 font=("Segoe UI", 11),
                 fg=self.COLORS["muted"], bg=bg).pack(pady=(2, 0))

        # ═══ 配置卡片 ═════════════════════════════
        card_frame = tk.Frame(self.root, bg=card, bd=0,
                              highlightbackground=self.COLORS["card_border"],
                              highlightthickness=1)
        card_frame.pack(fill=tk.X, padx=20, pady=(5, 12), ipady=10)

        rows = [
            ("🔑 Bearer Token", None),
            ("🌐 User-Agent",   None),
            ("📅 预约日期",     None),
            ("🏸 场地号",       "1,2,3,4,9,10,11,12"),
            ("⏱  时间段",      None),
            ("🔁 403重试次数",  "3"),
            ("🔄 Token刷新URL", "(可选)"),
        ]

        label_width = 14
        entry_width = 38

        for i, (title, default) in enumerate(rows):
            row_frame = tk.Frame(card_frame, bg=card)
            row_frame.pack(fill=tk.X, padx=16, pady=(10 if i == 0 else 4, 2))

            ttk.Label(row_frame, text=title, style="Card.TLabel",
                      width=label_width, anchor="w").pack(side=tk.LEFT)

            if "Token" in title and "刷新" not in title:
                self.token_entry = ttk.Entry(row_frame, style="Modern.TEntry",
                                              width=entry_width)
                self.token_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            elif "Agent" in title:
                self.ua_entry = ttk.Entry(row_frame, style="Modern.TEntry",
                                           width=entry_width)
                self.ua_entry.insert(0,
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.6 "
                    "Safari/605.1.15 DingTalk(8.3.15-macOS-54673844) "
                    "nw DTWKWebView Channel/201200 Architecture/x86_64 webDt/PC")
                self.ua_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            elif "日期" in title:
                target_date = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
                self.date_var = tk.StringVar(value=target_date)
                date_entry = ttk.Entry(row_frame, style="Modern.TEntry",
                                        textvariable=self.date_var,
                                        state="readonly", width=entry_width)
                date_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            elif "场地" in title:
                self.site_entry = ttk.Entry(row_frame, style="Modern.TEntry",
                                             width=entry_width)
                self.site_entry.insert(0, default)
                self.site_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            elif "时间段" in title:
                self.time_combo = ttk.Combobox(row_frame,
                                                values=list(self.time_options.keys()),
                                                style="Modern.TCombobox",
                                                width=entry_width - 2,
                                                state="readonly")
                self.time_combo.current(0)
                self.time_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
            elif "403重试" in title:
                self.retry_var = tk.StringVar(value=default)
                retry_entry = ttk.Entry(row_frame, style="Modern.TEntry",
                                         textvariable=self.retry_var,
                                         width=entry_width)
                retry_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            elif "刷新URL" in title:
                self.refresh_url_entry = ttk.Entry(row_frame, style="Modern.TEntry",
                                                    width=entry_width)
                self.refresh_url_entry.insert(0, default)
                self.refresh_url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # ═══ 操作按钮 ═════════════════════════════
        btn_frame = tk.Frame(self.root, bg=bg)
        btn_frame.pack(fill=tk.X, padx=20, pady=(0, 8))

        self.start_btn = ttk.Button(btn_frame,
                                     text="🚀  设置定时任务 (今晚 20:00 执行)",
                                     style="Accent.TButton",
                                     command=self.start_task)
        self.start_btn.pack(fill=tk.X, ipady=6)

        # ═══ 底部状态 / 日志 ═══════════════════════
        bottom_frame = tk.Frame(self.root, bg=bg)
        bottom_frame.pack(fill=tk.X, padx=20, pady=(0, 6))

        ttk.Label(bottom_frame, text=f"📝 日志文件: {log_filename}",
                  style="Muted.TLabel", background=bg).pack(side=tk.LEFT)

        self.log_area = scrolledtext.ScrolledText(
            self.root,
            width=64,
            height=18,
            state="disabled",
            bg=self.COLORS["scroll_bg"],
            fg=self.COLORS["scroll_fg"],
            insertbackground=self.COLORS["scroll_fg"],
            font=("SF Mono", 10),
            relief="flat",
            borderwidth=0,
            padx=12,
            pady=10,
            highlightthickness=0
        )
        self.log_area.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))

    def log(self, msg):
        def update():
            self.log_area.config(state="normal")
            # 根据消息类型加颜色标记
            self.log_area.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
            self.log_area.see(tk.END)
            self.log_area.config(state="disabled")

        self.root.after(0, update)

    def start_task(self):
        if self.is_running:
            return

        token = self.token_entry.get().strip()
        ua = self.ua_entry.get().strip()

        try:
            self.target_sites = [int(x.strip()) for x in self.site_entry.get().replace('，', ',').split(",")]
        except:
            messagebox.showerror("错误", "场地号格式错误")
            return

        # 读取 403 重试次数
        try:
            max_403_retries = int(self.retry_var.get().strip())
            if max_403_retries < 0:
                max_403_retries = 0
            elif max_403_retries > 10:
                max_403_retries = 10
        except:
            max_403_retries = 3

        # 读取 Token 刷新 URL
        refresh_url = self.refresh_url_entry.get().strip()
        if refresh_url == "(可选)" or refresh_url == "":
            refresh_url = None

        if not token or not ua:
            messagebox.showerror("错误", "Token 和 UA 不能为空")
            return

        self.is_running = True
        self.global_success = False
        self.start_btn.config(state="disabled")

        time_list, start_time, end_time = self.time_options[self.time_combo.get()]

        config = {
            "date": self.date_var.get(),
            "venue_name": "综合馆羽毛球",
            "venue_type": "badminton",
            "time_list": time_list,
            "start_time": start_time,
            "end_time": end_time
        }

        threading.Thread(target=self.wait_and_run,
                          args=(token, ua, config, max_403_retries, refresh_url),
                          daemon=True).start()

    def wait_and_run(self, token, ua, config, max_403_retries, refresh_url):
        self.log(f"任务已启动，等待20:00开抢 | 403重试次数:{max_403_retries}")
        if refresh_url:
            self.log(f"🔗 Token刷新端点: {refresh_url}")
        else:
            self.log("🔗 Token刷新策略: 自动访问主页面获取")

        target = datetime.now().replace(hour=20, minute=0, second=0, microsecond=0)

        while datetime.now() < target:
            time.sleep(0.1)

        self.log("⏰ 时间到，开始冲锋")

        threads = []

        for sid in self.target_sites:
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
