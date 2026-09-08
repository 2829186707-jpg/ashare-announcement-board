# -*- coding: utf-8 -*-
"""
本地公告看板服务：
- 浏览器访问 http://127.0.0.1:8765 查看看板
- 定时抓取由 Windows 计划任务负责：每个工作日 8:35 运行 run_daily.ps1（抓取+推送 GitHub）
- 启动时若发现漏抓（如长假后开机），自动补抓（兜底，与计划任务幂等）
- 看板提供"立即抓取"按钮手动触发
"""
import datetime as dt
import json
import os
import threading

from flask import Flask, jsonify, request, send_from_directory

from config import BASE_DIR, DATA_DIR, PORT, STATE_FILE
import fetch as fetcher

app = Flask(__name__, static_folder=None)


@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/data/<path:filename>")
def serve_data(filename):
    """静态数据文件（本地与 GitHub Pages 共用同一相对路径 data/xxx.json）"""
    return send_from_directory(DATA_DIR, filename)


@app.route("/api/dates")
def api_dates():
    """已有数据的日期列表（倒序，兼容旧接口）"""
    dates = []
    if os.path.isdir(DATA_DIR):
        for fn in os.listdir(DATA_DIR):
            if fn.endswith(".json") and fn not in ("state.json", "dates.json"):
                dates.append(fn[:-5])
    dates.sort(reverse=True)
    return jsonify(dates)


@app.route("/api/announcements")
def api_announcements():
    """某日全部公告（兼容旧接口）"""
    date = request.args.get("date", "")
    path = os.path.join(DATA_DIR, f"{date}.json")
    if not os.path.exists(path):
        return jsonify({"date": date, "updated_at": None, "total": 0, "important_count": 0,
                        "announcements": []})
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return jsonify(data)


@app.route("/api/state")
def api_state():
    """断点状态"""
    info = {"last_date": None, "today": dt.date.today().isoformat(), "weekday": dt.date.today().strftime("%A")}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            info.update(json.load(f))
    return jsonify(info)


@app.route("/api/fetch", methods=["POST"])
def api_fetch():
    """手动触发抓取（后台执行）"""
    def job():
        try:
            fetcher.run_fetch()
        except Exception as e:
            print(f"[手动抓取失败] {e}", flush=True)
    threading.Thread(target=job, daemon=True).start()
    return jsonify({"ok": True, "message": "抓取已开始，完成后刷新即可看到新数据"})


def run_fetch_job():
    try:
        fetcher.run_fetch()
    except Exception as e:
        print(f"[补抓失败] {e}", flush=True)


def backfill_if_needed():
    """启动时补抓：工作日且最后抓取日 < 今天（计划任务的兜底）"""
    try:
        if dt.date.today().weekday() >= 5:
            return
        last = ""
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                last = json.load(f).get("last_date", "")
        if not last or last < dt.date.today().isoformat():
            threading.Thread(target=run_fetch_job, daemon=True).start()
    except Exception as e:
        print(f"[启动补抓检查失败] {e}", flush=True)


if __name__ == "__main__":
    print(f"看板服务已启动：http://127.0.0.1:{PORT}", flush=True)
    print("定时抓取由 Windows 计划任务负责（每个工作日 8:35，run_daily.ps1）", flush=True)
    backfill_if_needed()
    app.run(host="127.0.0.1", port=PORT, threaded=True)
