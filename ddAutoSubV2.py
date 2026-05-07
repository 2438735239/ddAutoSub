import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import requests
import json
import time
from datetime import datetime, timedelta
import threading
import urllib3

# 屏蔽 SSL 证书校验警告[cite: 1, 2]
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ==================== 后端逻辑 ====================

class HDUSportsBooker:
    def __init__(self, token, user_agent, openid="X", nickname="X", phone="X",
                 log_callback=print):
        self.base_url = "https://sportmeta.hdu.edu.cn"
        self.headers = {
            "Host": "sportmeta.hdu.edu.cn",
            "Accept": "*/*",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": user_agent,  # 动态 User-Agent
            "Referer": "https://sportmeta.hdu.edu.cn/book/dingtalk/?v=1.0.16",
            "Connection": "keep-alive"
        }
        self.user_info = {
            "openid": openid,  # 用户身份标识[cite: 1, 2]
            "nickname": nickname,
            "phone": phone
        }
        self.log = log_callback

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

    def check_book_info(self, payload):
        url = f"{self.base_url}/book/client/creat_book_info"
        site_id = payload["orderData"]["site_id"]
        try:
            response = requests.post(url, headers=self.headers, data=json.dumps(payload), timeout=5, verify=False)
            res_data = response.json()

            if "预约成功" in res_data.get("message", "") or res_data.get("message") == "\u9884\u7ea6\u6210\u529f":
                self.log(f" -> [场地 {site_id}] 校验通过，准备下单...")
                return True
            else:
                self.log(f" -> [场地 {site_id}] 校验失败: {res_data.get('message')}")
                return False
        except Exception as e:
            self.log(f" -> [场地 {site_id}] 请求异常: {e}")
            return False

    def create_order(self, payload):
        url = f"{self.base_url}/book/client/creat_order"
        site_id = payload["orderData"]["site_id"]
        try:
            response = requests.post(url, headers=self.headers, data=json.dumps(payload), timeout=5, verify=False)
            res_data = response.json()

            if res_data.get("status") == "success":
                order_num = res_data["data"].get("order_num")
                self.log(f" -> 🎉 [场地 {site_id}] 抢场成功！订单号: {order_num}")
                return True
            else:
                self.log(f" -> [场地 {site_id}] 订单失败: {res_data.get('message')}")
                return False
        except Exception as e:
            self.log(f" -> [场地 {site_id}] 最终请求异常: {e}")
            return False


# ==================== GUI 前端逻辑 ====================

class BookingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("无敌抢场王 - 多场地并发版")
        self.root.geometry("450x650")
        self.root.resizable(False, False)

        self.time_options = {}
        for i in range(13):
            start = f"{8 + i:02d}:00"
            end = f"{9 + i:02d}:00"
            self.time_options[f"[{i}] {start}-{end}"] = ([i], start, end)
        for i in range(12):
            start = f"{8 + i:02d}:00"
            end = f"{10 + i:02d}:00"
            self.time_options[f"[{i}, {i + 1}] {start}-{end}"] = ([i, i + 1], start, end)

        self.is_running = False
        self.global_success = False
        self.setup_ui()

    def setup_ui(self):
        frame_input = tk.Frame(self.root, padx=15, pady=15)
        frame_input.pack(fill=tk.X)

        tk.Label(frame_input, text="Bearer Token:").grid(row=0, column=0, sticky="w", pady=5)
        self.token_entry = tk.Entry(frame_input, width=30)
        self.token_entry.grid(row=0, column=1, pady=5)

        tk.Label(frame_input, text="User-Agent:").grid(row=1, column=0, sticky="w", pady=5)
        self.ua_entry = tk.Entry(frame_input, width=30)
        self.ua_entry.insert(0,
                             "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.6 Safari/605.1.15 DingTalk(8.3.15-macOS-54673844) nw DTWKWebView Channel/201200 Architecture/x86_64 webDt/PC")
        self.ua_entry.grid(row=1, column=1, pady=5)

        target_date = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
        tk.Label(frame_input, text="预约日期 (T+2):").grid(row=2, column=0, sticky="w", pady=5)
        self.date_var = tk.StringVar(value=target_date)
        tk.Entry(frame_input, textvariable=self.date_var, state="readonly", width=30).grid(row=2, column=1, pady=5)

        tk.Label(frame_input, text="场地号 (逗号分隔):").grid(row=3, column=0, sticky="w", pady=5)
        self.site_entry = tk.Entry(frame_input, width=30)
        self.site_entry.insert(0, "12,13,14")
        self.site_entry.grid(row=3, column=1, pady=5)

        tk.Label(frame_input, text="时间段选择:").grid(row=4, column=0, sticky="w", pady=5)
        self.time_combo = ttk.Combobox(frame_input, values=list(self.time_options.keys()), width=28, state="readonly")
        self.time_combo.current(0)
        self.time_combo.grid(row=4, column=1, pady=5)

        self.start_btn = tk.Button(self.root, text="设置定时任务 (今晚 20:00 执行)", bg="green", fg="white",
                                   command=self.start_task)
        self.start_btn.pack(pady=10)

        tk.Label(self.root, text="运行日志:").pack(anchor="w", padx=15)
        self.log_area = scrolledtext.ScrolledText(self.root, width=55, height=18, state="disabled")
        self.log_area.pack(padx=15, pady=5)

    def log(self, message):
        def update_text():
            self.log_area.config(state="normal")
            self.log_area.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")
            self.log_area.see(tk.END)
            self.log_area.config(state="disabled")

        self.root.after(0, update_text)

    def start_task(self):
        if self.is_running: return

        token = self.token_entry.get().strip()
        ua = self.ua_entry.get().strip()
        site_str = self.site_entry.get().strip()

        try:
            self.target_sites = [int(s.strip()) for s in site_str.replace('，', ',').split(',')]
        except:
            messagebox.showerror("错误", "场地号格式不正确，请用英文逗号分隔数字！")
            return

        if not token or not ua:
            messagebox.showerror("错误", "Token 和 UA 不能为空！")
            return

        self.is_running = True
        self.global_success = False
        self.start_btn.config(state="disabled", text="多场地任务激活中...")

        time_list, start_time, end_time = self.time_options[self.time_combo.get()]
        config_template = {
            "date": self.date_var.get(),
            "venue_name": "综合馆羽毛球",
            "venue_type": "badminton",
            "time_list": time_list,
            "start_time": start_time,
            "end_time": end_time
        }

        threading.Thread(target=self.wait_and_execute, args=(token, ua, config_template), daemon=True).start()

    def wait_and_execute(self, token, ua, config_template):
        self.log(f"已接受任务。目标场地清单: {self.target_sites}")

        # 定时逻辑保持不变[cite: 1, 2]
        target_time = datetime.now().replace(hour=20, minute=0, second=0, microsecond=0)
        while datetime.now() < target_time:
            time.sleep(0.1)

        self.log("⏰ 20:00:00 到达！发起并发冲击...")

        threads = []
        for sid in self.target_sites:
            # 深拷贝配置并注入当前场地 ID
            site_cfg = config_template.copy()
            site_cfg["site_id"] = sid

            # 每个场地一个独立线程
            t = threading.Thread(target=self.site_task_thread, args=(token, ua, site_cfg))
            threads.append(t)
            t.start()

        for t in threads: t.join()

        self.is_running = False

        def finish_ui():
            self.start_btn.config(state="normal", text="设置定时任务 (今晚 20:00 执行)")
            if self.global_success:
                messagebox.showinfo("结束", "🎉 抢场结束，其中一个场地已成功下单！")
            else:
                messagebox.showwarning("结束", "❌ 全线溃败，所有场地均未抢到。")

        self.root.after(0, finish_ui)

    def site_task_thread(self, token, ua, site_cfg):
        """单个场地的抢场逻辑线程"""
        booker = HDUSportsBooker(token=token, user_agent=ua, log_callback=self.log)
        payload = booker.build_payload(**site_cfg)

        # 尝试 5 次重试循环[cite: 2]
        for i in range(5):
            if self.global_success: break  # 如果已经有场抢到了，直接收工

            if booker.check_book_info(payload):
                if booker.create_order(payload):
                    self.global_success = True
                    break
            time.sleep(0.2)  # 失败重试间隔


if __name__ == "__main__":
    root = tk.Tk()
    app = BookingApp(root)
    root.mainloop()