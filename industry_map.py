# -*- coding: utf-8 -*-
"""生成/更新 东财行业映射表：股票代码 -> {名称, 东财行业}"""
import json
import time

import requests

BASE_URL = "https://push2.eastmoney.com/api/qt/clist/get"
# 深主板A + 创业板 + 沪主板A + 科创板
FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
FIELDS = "f12,f14,f100"
OUT_FILE = "industry_map.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "application/json, text/plain, */*",
}


def fetch_page(pn, pz=100):
    url = (f"{BASE_URL}?pn={pn}&pz={pz}&po=1&np=1&fltt=2&invt=2"
           f"&fid=f3&fs={FS}&fields={FIELDS}")
    for attempt in range(4):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            print(f"  第{pn}页第{attempt + 1}次失败: {e}", flush=True)
        time.sleep(2 * (attempt + 1))
    return {}


def build_map():
    mapping = {}
    pn = 1
    while True:
        data = fetch_page(pn)
        diff = (data.get("data") or {}).get("diff") or []
        if not diff:
            if mapping:
                print(f"第 {pn} 页无数据，结束", flush=True)
            else:
                print("未获取到任何数据，请检查网络后重试", flush=True)
            break
        for item in diff:
            code = item.get("f12")
            if code:
                mapping[code] = {
                    "name": item.get("f14") or "",
                    "industry": item.get("f100") or "未分类",
                }
        print(f"第 {pn} 页完成，已累计 {len(mapping)} 只", flush=True)
        if len(diff) < 100:
            break
        pn += 1
        time.sleep(0.4)
    return mapping


if __name__ == "__main__":
    m = build_map()
    if m:
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=1)
        print(f"完成：共 {len(m)} 只股票 -> {OUT_FILE}")
    else:
        print("失败：行业映射为空")
