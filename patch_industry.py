# -*- coding: utf-8 -*-
"""补查未分类股票的行业（10只/批，针对首轮未返回的沪深股票）"""
import json
import time

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://gushitong.baidu.com/",
}
BATCH = 10


def query_industry(code_list):
    stocks = [{"code": c, "market": "ab", "type": "stock"} for c in code_list]
    url = ("https://finance.pae.baidu.com/api/getrelatedblock?stock="
           + json.dumps(stocks, ensure_ascii=False) + "&finClientType=pc")
    for attempt in range(4):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            j = r.json()
            res = j.get("Result") or {}
            out = {}
            for key, val in res.items():
                for ct in val:
                    if ct.get("name") == "行业":
                        lst = ct.get("list", [])
                        l1 = [x for x in lst if x.get("describe") == "申万一级"]
                        l2 = [x for x in lst if x.get("describe") == "申万二级"]
                        out[key] = l1[0]["name"] if l1 else (l2[0]["name"] if l2 else None)
            return out
        except Exception as e:
            if attempt == 3:
                print(f"批次失败: {e}", flush=True)
                return {}
            time.sleep(3 * (attempt + 1))
    return {}


if __name__ == "__main__":
    mp = json.load(open("industry_map.json", encoding="utf-8"))
    uncl = [c for c, v in mp.items() if v["industry"] == "未分类" and c[0] in "01236"]
    print(f"待补查沪深股票: {len(uncl)} 只", flush=True)
    filled = 0
    for i in range(0, len(uncl), BATCH):
        chunk = uncl[i:i + BATCH]
        out = query_industry(chunk)
        for c, ind in out.items():
            if ind:
                mp[c]["industry"] = ind
                filled += 1
        if (i // BATCH) % 20 == 0:
            print(f"补查进度: {min(i + BATCH, len(uncl))}/{len(uncl)}，已补 {filled}", flush=True)
        time.sleep(0.15)
    with open("industry_map.json", "w", encoding="utf-8") as f:
        json.dump(mp, f, ensure_ascii=False, indent=1)
    still = sum(1 for v in mp.values() if v["industry"] == "未分类")
    print(f"补查完成：新分类 {filled} 只，剩余未分类 {still} 只", flush=True)
