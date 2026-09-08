# -*- coding: utf-8 -*-
"""公告看板配置"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PDF_DIR = os.path.join(BASE_DIR, "temp_pdf")
INDUSTRY_FILE = os.path.join(BASE_DIR, "industry_map.json")
STATE_FILE = os.path.join(DATA_DIR, "state.json")

# 看板服务端口
PORT = 8765
# 每天早上定时抓取时间（小时:分钟）
SCHEDULE_HOUR = 8
SCHEDULE_MINUTE = 0
# 核心内容摘要最大字符数
SUMMARY_MAX_CHARS = 200
# PDF 解析页数上限（核心"重要提示"基本在前 4 页，减半提速）
PDF_PARSE_PAGES = 4
# PDF 下载解析并发线程数（IO 密集，12 线程提速明显）
PDF_WORKERS = 12
# 单次请求超时（秒）
TIMEOUT = 30
