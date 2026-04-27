import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import requests
import json
import time
from datetime import datetime, timedelta
import threading

class HDUSportsBooker:
    def __init__(self, token, openid="X", nickname="X", phone="X", log_callback=print):
        self.base_url = "https://sportmeta.hdu.edu.cn"
        self.headers = {
            "Host": "sportmeta.hdu.edu.cn",
            "Accept": "*/*",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.6 Safari/605.1.15 DingTalk(8.3.10-macOS-54337830) nw DTWKWebView Channel/201200 Architecture/x86_64 webDt/PC",
            "Referer": "https://sportmeta.hdu.edu.cn/book/dingtalk/?v=1.0.16",
            "Connection": "keep-alive"
        }
        self.user_info = {
            "openid": openid,
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
        self.log("[1/2] 正在校验场地信息...")
        try:
            response = requests.post(url, headers=self.headers, data=json.dumps(payload), timeout=5)
            response.raise_for_status()
            res_data = response.json()

            if "预约成功" in res_data.get("message", "") or res_data.get("message") == "\u9884\u7ea6\u6210\u529f":
                self.log(f" -> 场地校验成功，可预订时间: {res_data.get('available_times')}")
                return True
            else:
                self.log(f" -> 场地校验失败: {res_data}")
                return False
        except Exception as e:
            self.log(f" -> 请求异常: {e}")
            return False

    def create_order(self, payload):
        url = f"{self.base_url}/book/client/creat_order"
        self.log("[2/2] 正在生成最终订单...")
        try:
            response = requests.post(url, headers=self.headers, data=json.dumps(payload), timeout=5)
            response.raise_for_status()
            res_data = response.json()

            if res_data.get("status") == "success":
                order_num = res_data["data"].get("order_num")
                self.log(f" -> 🎉 抢场成功！订单号: {order_num}")
                return True
            else:
                self.log(f" -> 订单生成失败: {res_data}")
                return False
        except Exception as e:
            self.log(f" -> 请求异常: {e}")
            return False

    def execute_booking(self, booking_config):
        self.log(">>> 开始执行预约流程 <<<")
        payload = self.build_payload(**booking_config)

        if self.check_book_info(payload):
            time.sleep(0.1)
            success = self.create_order(payload)
            self.log(">>> 流程执行完毕 <<<")
            return success
        else:
            self.log("❌ 流程终止：未能通过第一步校验。")
            return False


# ==================== GUI 前端逻辑 ====================

class BookingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("无敌抢场王")
        self.root.geometry("450x550")
        self.root.resizable(False, False)

        # 动态生成选项字典: UI显示文本 -> (time_list, start_time, end_time)
        self.time_options = {}
        for i in range(13):  # 单个时段 0-12
            start = f"{8 + i:02d}:00"
            end = f"{9 + i:02d}:00"
            self.time_options[f"[{i}] {start}-{end}"] = ([i], start, end)
        for i in range(12):  # 连续两个时段
            start = f"{8 + i:02d}:00"
            end = f"{10 + i:02d}:00"
            self.time_options[f"[{i}, {i + 1}] {start}-{end}"] = ([i, i + 1], start, end)

        self.is_running = False
        self.setup_ui()

    def setup_ui(self):
        # --- 输入区域 ---
        frame_input = tk.Frame(self.root, padx=15, pady=15)
        frame_input.pack(fill=tk.X)

        # Token
        tk.Label(frame_input, text="Bearer Token:").grid(row=0, column=0, sticky="w", pady=5)
        self.token_entry = tk.Entry(frame_input, width=30)
        self.token_entry.grid(row=0, column=1, pady=5)

        # 日期 (固定 T+2)
        target_date = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
        tk.Label(frame_input, text="预约日期 (T+2):").grid(row=1, column=0, sticky="w", pady=5)
        self.date_var = tk.StringVar(value=target_date)
        tk.Entry(frame_input, textvariable=self.date_var, state="readonly", width=30).grid(row=1, column=1, pady=5)

        # 场地号
        tk.Label(frame_input, text="场地号 (Site ID):").grid(row=2, column=0, sticky="w", pady=5)
        self.site_entry = tk.Entry(frame_input, width=30)
        self.site_entry.insert(0, "12")  # 默认填12
        self.site_entry.grid(row=2, column=1, pady=5)

        # 时间段选择
        tk.Label(frame_input, text="时间段选择:").grid(row=3, column=0, sticky="w", pady=5)
        self.time_combo = ttk.Combobox(frame_input, values=list(self.time_options.keys()), width=28, state="readonly")
        self.time_combo.current(0)
        self.time_combo.grid(row=3, column=1, pady=5)

        # 按钮
        self.start_btn = tk.Button(self.root, text="设置定时任务 (今晚 20:00 执行)", bg="green", fg="white",
                                   command=self.start_task)
        self.start_btn.pack(pady=10)

        # --- 日志区域 ---
        tk.Label(self.root, text="运行日志:").pack(anchor="w", padx=15)
        self.log_area = scrolledtext.ScrolledText(self.root, width=55, height=15, state="disabled")
        self.log_area.pack(padx=15, pady=5)

    def log(self, message):

        def update_text():
            self.log_area.config(state="normal")
            self.log_area.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")
            self.log_area.see(tk.END)
            self.log_area.config(state="disabled")

        self.root.after(0, update_text)

    def start_task(self):
        if self.is_running:
            return

        token = self.token_entry.get().strip()
        site_id_str = self.site_entry.get().strip()
        selected_time_key = self.time_combo.get()

        if not token:
            messagebox.showerror("错误", "请输入有效的 Token！")
            return
        if not site_id_str.isdigit():
            messagebox.showerror("错误", "场地号必须为纯数字！")
            return

        self.is_running = True
        self.start_btn.config(state="disabled", text="任务已激活，等待中...")

        time_list, start_time, end_time = self.time_options[selected_time_key]
        booking_config = {
            "date": self.date_var.get(),
            "venue_name": "综合馆羽毛球",
            "venue_type": "badminton",
            "site_id": int(site_id_str),
            "time_list": time_list,
            "start_time": start_time,
            "end_time": end_time
        }

        threading.Thread(target=self.wait_and_execute, args=(token, booking_config), daemon=True).start()

    def wait_and_execute(self, token, config):
        self.log("已接受任务配置。")
        self.log(
            f"目标场地: {config['site_id']}号场地, 日期: {config['date']}, 时段: {config['start_time']}-{config['end_time']}")

        now = datetime.now()
        target_time = now.replace(hour=20, minute=0, second=0, microsecond=0)

        if now >= target_time:
            self.log("⚠️ 当前时间已过20:00，将立即执行脚本！")
        else:
            self.log(f"等待中... 系统将于今晚 20:00:00 准时触发抢场。")
            while datetime.now() < target_time:
                time.sleep(0.5)

        self.log("⏰ 时间到！开始发起请求...")

        booker = HDUSportsBooker(token=token, log_callback=self.log)
        success = booker.execute_booking(config)

        self.is_running = False

        def finish_ui():
            self.start_btn.config(state="normal", text="设置定时任务 (今晚 20:00 执行)")
            if success:
                messagebox.showinfo("结束", "🎉 恭喜，执行完毕，预约成功！请在小程序核实。")
            else:
                messagebox.showwarning("结束", "❌ 预约失败或被抢光，请查看日志详情。")

        self.root.after(0, finish_ui)

if __name__ == "__main__":
    root = tk.Tk()
    app = BookingApp(root)
    root.mainloop()