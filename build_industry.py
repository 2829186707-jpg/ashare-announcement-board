# -*- coding: utf-8 -*-
"""
生成 股票代码 -> 行业 映射表 industry_map.json

说明：东财行业接口（push2.eastmoney.com）在当前网络环境下对非浏览器客户端做连接封锁，
本脚本改用【申万一级行业】分类（来源：百度股市通），机构投研通用标准，质量更高。
后续东财接口恢复可用时，可用 update_industry.ps1 切换回东财口径。

流程：新浪全量A股代码 -> 百度 getrelatedblock 批量查询申万一级行业
"""
import json
import time

import requests

BAIDU_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://gushitong.baidu.com/",
}
SINA_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
BATCH = 30  # 百度接口大批量会丢数据，30只/批最稳


def fetch_all_codes():
    """新浪 hs_a 分页拉全量 A 股代码"""
    codes = {}
    page = 1
    while True:
        url = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
               f"Market_Center.getHQNodeData?page={page}&num=100&sort=symbol&asc=1&node=hs_a")
        try:
            r = requests.get(url, headers=SINA_HEADERS, timeout=20)
            arr = r.json()
        except Exception as e:
            print(f"第{page}页拉取失败: {e}，重试", flush=True)
            time.sleep(2)
            continue
        if not arr:
            break
        for it in arr:
            code = it.get("code", "")
            if code and code not in codes:
                codes[code] = it.get("name", "")
        print(f"代码进度: 第{page}页, 累计 {len(codes)} 只", flush=True)
        if len(arr) < 100:
            break
        page += 1
        time.sleep(0.3)
    return codes


def fetch_industries(code_list):
    """百度批量查询申万一级行业（80只/批）"""
    result = {}
    total_batches = (len(code_list) + BATCH - 1) // BATCH
    for i in range(0, len(code_list), BATCH):
        chunk = code_list[i:i + BATCH]
        bn = i // BATCH + 1
        stocks = [{"code": c, "market": "ab", "type": "stock"} for c in chunk]
        url = ("https://finance.pae.baidu.com/api/getrelatedblock?stock="
               + json.dumps(stocks, ensure_ascii=False) + "&finClientType=pc")
        got = False
        for attempt in range(4):
            try:
                r = requests.get(url, headers=BAIDU_HEADERS, timeout=30)
                j = r.json()
                res = j.get("Result") or {}
                for key, val in res.items():
                    for ct in val:
                        if ct.get("name") == "行业":
                            lst = ct.get("list", [])
                            l1 = [x for x in lst if x.get("describe") == "申万一级"]
                            l2 = [x for x in lst if x.get("describe") == "申万二级"]
                            result[key] = l1[0]["name"] if l1 else (l2[0]["name"] if l2 else "未分类")
                got = True
                break
            except Exception as e:
                print(f"批次{bn}第{attempt+1}次失败: {e}", flush=True)
                time.sleep(3 * (attempt + 1))
        if not got:
            for c in chunk:
                result[c] = "未分类"
        if bn % 5 == 0 or bn == total_batches:
            print(f"行业进度: 批 {bn}/{total_batches}", flush=True)
        time.sleep(0.2)
    return result


if __name__ == "__main__":
    codes = fetch_all_codes()
    print(f"共 {len(codes)} 只股票，开始查询行业...", flush=True)
    inds = fetch_industries(list(codes.keys()))
    mapping = {c: {"name": n, "industry": inds.get(c, "未分类")} for c, n in codes.items()}
    with open("industry_map.json", "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=1)
    stat = {}
    for m in mapping.values():
        stat[m["industry"]] = stat.get(m["industry"], 0) + 1
    print(f"完成: {len(mapping)} 只 -> industry_map.json", flush=True)
    print("行业分布(前10):", sorted(stat.items(), key=lambda x: -x[1])[:10], flush=True)
