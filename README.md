# ddAutoSub 🏸

[![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A graphical venue reservation assistant developed in Python, specifically designed for the HDU sports venue reservation system. It supports timed triggering, parameter customization, and automatic reservation process.

---

## ✨ Features

- **Scheduled Booking**: Built-in timer that triggers the booking request precisely at 20:00:00 with millisecond-level precision.
- **Auto Date Calculation**: Automatically calculates the `T+2` booking date (no manual input required).
- **Intuitive GUI**: A clean Tkinter interface for managing tokens, selecting courts, and monitoring real-time logs.
- **Multi-Slot Support**: Supports single-slot (1 hour) or consecutive-slot (2 hours) reservations.
- **Asynchronous Architecture**: Utilizes multi-threading to ensure the UI remains responsive during the countdown and booking process.

---

## 📸 Preview

<img width="226" alt="微信图片_2026-04-27_100435_451" src="https://github.com/user-attachments/assets/fe623d3e-4ee2-4b5a-ba6a-f9113e082e0c" />

---

## 🚀 Quick Start

### 1. Prerequisites
Ensure you have Python 3.9 or higher installed on your system.

Install the required dependency:
```bash
pip install requests
```
### 2. Obtain Authorization Token
Due to security protocols, you must manually extract your token from the DingTalk applet:

&emsp; &emsp; **1.** Use a packet capture tool (e.g., Charles, Fiddler, or HTTP Canary).

&emsp; &emsp; **2.** Enter the venue reservation in DingTalk.

&emsp; &emsp; **3.** Locate any request sent to sportmeta.hdu.edu.cn.

&emsp; &emsp; **4.** Copy the string following Bearer  in the Authorization header.

---

## 🛠 Parameter Guide

**Bearer Token:** Your identity credential. Note that tokens usually have an expiration time.

**Site ID:** The specific court number (e.g., Court #12).

**Time Slots:**

* [0] corresponds to 08:00 - 09:00.

* [0, 1] corresponds to 08:00 - 10:00 (consecutive 2-hour booking).

---

## 📝 Changelog

**v0.1.0 (2026-04-27)**

* Initial Release.

* Implemented the core two-step logic: creat_book_info and creat_order.

* Added the 20:00:00 scheduled execution feature.

* Integrated a real-time visual log viewer.

**v0.2.0 (2026-05-07)**

* The concurrent venue snatching function has been added.

* Added the option to manually input "User-Agent".

* Increase the number of repeated attempts for the court takeover operation.

---

## ⚖️ Disclaimer

* This project is for educational and research purposes only.

* Do not use this script for commercial purposes or to unfairly monopolize public resources.

* The developer is not responsible for any consequences resulting from the use of this script, including but not limited to account suspension or system restrictions.

* Please follow the venue management regulations and use the system fairly.

## ❗Attention

* When running the program, please close the packet capture software such as Charles and Fiddler.
