# -*- coding: utf-8 -*-
"""
公告抓取引擎：
1. 按日期范围从巨潮资讯拉取沪深两市全部公告（断点续抓，默认从上一次抓到日的次日补到今天）
2. 标题规则过滤：重要公告下载 PDF 正文并提取核心内容，例行公告仅保留标题
3. 匹配东财行业，写入 data/YYYY-MM-DD.json

用法：
  python fetch.py                  # 自动断点续抓（上次次日 -> 今天）
  python fetch.py 2026-09-04       # 抓指定单日
  python fetch.py 2026-09-04 2026-09-07  # 抓日期范围
"""
import datetime as dt
import json
import os
import re
import sys
import time

import requests
from concurrent.futures import ThreadPoolExecutor

from config import DATA_DIR, INDUSTRY_FILE, PDF_DIR, STATE_FILE, SUMMARY_MAX_CHARS, PDF_PARSE_PAGES, PDF_WORKERS, TIMEOUT

CNINFO_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
PDF_BASE = "http://static.cninfo.com.cn/"
COLUMNS = [("szse", "深市"), ("sse", "沪市")]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Content-Type": "application/x-www-form-urlencoded",
}

# ============ 标题分类规则（rules.py 统一维护） ============
from rules import classify, keep_core_important, clean_summary


# ============ 数据拉取 ============
def fetch_day(date_str):
    """拉取指定日期沪深两市全部公告，返回 [{...}]"""
    results = []
    for column, _name in COLUMNS:
        page = 1
        while True:
            data = {
                "pageNum": str(page),
                "pageSize": "30",
                "column": column,
                "tabName": "fulltext",
                "seDate": f"{date_str}~{date_str}",
                "sortName": "",
                "sortType": "",
                "isHLtitle": "true",
            }
            try:
                r = requests.post(CNINFO_URL, data=data, headers=HEADERS, timeout=TIMEOUT)
                j = r.json()
            except Exception as e:
                print(f"  [{date_str} {_name}] 请求失败: {e}", flush=True)
                time.sleep(3)
                continue
            total = j.get("totalAnnouncement", 0)
            items = j.get("announcements") or []
            for it in items:
                ts = it.get("announcementTime", 0)
                time_str = dt.datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M") if ts else ""
                results.append({
                    "sec_code": it.get("secCode", ""),
                    "sec_name": it.get("secName", ""),
                    "title": it.get("announcementTitle", ""),
                    "time": time_str,
                    "adjunct_url": it.get("adjunctUrl", "") or "",
                })
            if page * 30 >= total or not items:
                break
            page += 1
            time.sleep(0.15)
    return results


# ============ 核心内容提取 ============
def _pick_core(text, title):
    """从正文中挑选核心段落"""
    for marker in ["重要内容提示", "重要提示", "特别提示", "一、重要提示"]:
        idx = text.find(marker)
        if idx >= 0:
            seg = text[idx + len(marker): idx + len(marker) + 600]
            seg = seg.strip(" ：:。；;，, ")
            if len(seg) > 40:
                text = seg
                break
    else:
        # 未命中提示章节：跳过报告头（证券代码/简称/编号等）
        text = re.sub(
            r"^(?:证券代码[^，。；;]{0,30}[，。；;]?|证券简称[^，。；;]{0,30}[，。；;]?"
            r"|公告编号[^，。；;]{0,30}[，。；;]?|上市公司名称[^，。；;]{0,50}[，。；;]?"
            r"|股票简称[^，。；;]{0,30}[，。；;]?|股票代码[^，。；;]{0,30}[，。；;]?"
            r"|股票上市地点[^，。；;]{0,30}[，。；;]?|公司代码[^，。；;]{0,30}[，。；;]?){1,8}",
            "", text, count=1)
        text = re.sub(
            r"^(?:本公司及董事会全体成员[^。]{0,60}[。]?|本公司董事会及全体董事[^。]{0,60}[。]?"
            r"|本公司及全体董事[^。]{0,60}[。]?|本公司及监事会全体成员[^。]{0,60}[。]?"
            r"|重要内容提示[:：]?|特别提示[:：]?){0,4}",
            "", text, count=1)
        text = text.strip(" ：:。；;，, ")
    text = text[:SUMMARY_MAX_CHARS + 300]
    # 在句号/分号处截断，保持完整句子
    cut = -1
    for m in re.finditer(r"[。；;！？]\s", text):
        if m.end() <= SUMMARY_MAX_CHARS + 60:
            cut = m.end()
        else:
            break
    if cut > 80:
        text = text[:cut]
    return text.strip()[:SUMMARY_MAX_CHARS]


def extract_summary(adjunct_url, sec_name, title):
    """下载 PDF 并提取核心内容，返回 (摘要或None, 原文链接)"""
    if not adjunct_url:
        return None, None
    pdf_url = PDF_BASE + adjunct_url
    fname = os.path.join(PDF_DIR, f"{sec_name}_{os.path.basename(adjunct_url)}")
    ok = False
    for _ in range(2):
        try:
            r = requests.get(pdf_url, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 200 and len(r.content) > 100:
                with open(fname, "wb") as f:
                    f.write(r.content)
                ok = True
                break
        except Exception:
            time.sleep(2)
    if not ok:
        return None, pdf_url
    text = ""
    try:
        try:
            try:
                import pymupdf  # PyMuPDF：解析速度约为 pypdf 的 5-10 倍
            except ImportError:
                import fitz as pymupdf
            doc = pymupdf.open(fname)
            n = min(PDF_PARSE_PAGES, doc.page_count)
            for pno in range(n):
                t = doc[pno].get_text() or ""
                if t.strip():
                    text += t + "\n"
            doc.close()
        except Exception:
            from pypdf import PdfReader
            reader = PdfReader(fname)
            for p in reader.pages[:PDF_PARSE_PAGES]:
                t = p.extract_text() or ""
                if t.strip():
                    text += t + "\n"
        text = re.sub(r"\s+", " ", text).strip()
    except Exception:
        text = ""
    finally:
        try:
            os.remove(fname)
        except Exception:
            pass
    if not text:
        return None, pdf_url  # 扫描件无文本
    return clean_summary(_pick_core(text, title)), pdf_url


# ============ 行业匹配 ============
def load_industry():
    if os.path.exists(INDUSTRY_FILE):
        with open(INDUSTRY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ============ 主流程 ============
def get_fetch_range(argv):
    """计算抓取日期范围"""
    today = dt.date.today()
    if len(argv) >= 3:
        return [dt.date.fromisoformat(argv[1]), dt.date.fromisoformat(argv[2])]
    if len(argv) == 2:
        d = dt.date.fromisoformat(argv[1])
        return [d, d]
    # 断点续抓：从上次抓取日（含当天）补到今天
    # 含当天重抓是为了补上昨日盘后发布的公告；已有摘要会复用，不重复下载
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            last = json.load(f).get("last_date", "")
        if last:
            start = dt.date.fromisoformat(last)
            if start >= today:
                start = today - dt.timedelta(days=1)  # 当天已抓过则至少补昨日
            return [start, today]
    # 首次运行：补最近 4 天（覆盖跨周末/短假期，确保包含上一交易日）
    return [today - dt.timedelta(days=4), today]


def run_fetch(argv=None):
    argv = argv if argv is not None else sys.argv
    industry = load_industry()
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(PDF_DIR, exist_ok=True)
    rng = get_fetch_range(argv)
    if rng is None:
        return {"ok": True, "message": "已是最新"}
    start, end = rng
    days = (end - start).days + 1
    print(f"抓取范围: {start} ~ {end}（共 {days} 天）", flush=True)
    total_saved = 0
    total_important = 0
    d = start
    while d <= end:
        date_str = d.isoformat()
        print(f"[{date_str}] 拉取公告...", flush=True)
        items = fetch_day(date_str)
        if not items:
            print(f"[{date_str}] 无公告", flush=True)
            d += dt.timedelta(days=1)
            continue
        # 去重（同代码同标题）
        seen = set()
        uniq = []
        for it in items:
            key = (it["sec_code"], it["title"])
            if key in seen:
                continue
            seen.add(key)
            uniq.append(it)
        print(f"[{date_str}] 共 {len(uniq)} 条，开始分类与摘要...", flush=True)
        # 加载已有记录（复用已有摘要，避免重复下载）
        fpath = os.path.join(DATA_DIR, f"{date_str}.json")
        existing = []
        if os.path.exists(fpath):
            with open(fpath, "r", encoding="utf-8") as f:
                existing = json.load(f).get("announcements", [])
        existing_by_key = {(r["sec_code"], r["title"]): r for r in existing}
        saved = []
        need_extract = []  # (rec, adjunct_url) 待并发提取摘要的重要公告
        for i, it in enumerate(uniq, 1):
            key = (it["sec_code"], it["title"])
            old = existing_by_key.get(key)
            if old and old.get("summary"):
                saved.append(old)
                continue
            tname, important = classify(it["title"])
            rec = {
                "sec_code": it["sec_code"],
                "sec_name": it["sec_name"],
                "title": it["title"],
                "type": tname,
                "important": important,
                "time": it["time"],
                "summary": None,
                "url": None,
            }
            ind = industry.get(it["sec_code"])
            rec["industry"] = (ind or {}).get("industry", "未分类") if ind else "未分类"
            if important:
                need_extract.append((rec, it["adjunct_url"]))
                total_important += 1
            saved.append(rec)
            if i % 20 == 0 or i == len(uniq):
                print(f"    进度 {i}/{len(uniq)}，待提取摘要 {len(need_extract)} 条", flush=True)
        # 并发提取摘要（IO 密集，多线程提速明显）
        done = 0
        if need_extract:
            print(f"    并发提取 {len(need_extract)} 条摘要（{PDF_WORKERS} 线程）...", flush=True)

            def _do(pair):
                rec, adjunct = pair
                rec["summary"], rec["url"] = extract_summary(adjunct, rec["sec_name"], rec["title"])
                return rec

            with ThreadPoolExecutor(max_workers=PDF_WORKERS) as ex:
                extracted = list(ex.map(_do, need_extract))
            done = sum(1 for r in extracted if r["summary"])
            print(f"    并发提取完成：{done}/{len(extracted)} 条有摘要", flush=True)
        # 合并去重
        merged = { (r["sec_code"], r["title"]): r for r in existing + saved }
        merged_list = list(merged.values())
        # 同主题核心筛选：同公司同类型的重要公告最多保留2篇
        keep_core_important(merged_list)
        merged_list.sort(key=lambda r: r["time"], reverse=True)
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump({
                "date": date_str,
                "updated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total": len(merged_list),
                "important_count": sum(1 for r in merged_list if r["important"]),
                "announcements": merged_list,
            }, f, ensure_ascii=False, indent=1)
        total_saved += len(merged_list)
        print(f"[{date_str}] 已保存 {len(merged_list)} 条 -> data/{date_str}.json", flush=True)
        d += dt.timedelta(days=1)
    # 更新断点状态
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_date": end.isoformat(), "updated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}, f, ensure_ascii=False, indent=1)
    msg = f"完成：{days} 天共入库 {total_saved} 条，其中重要公告 {total_important} 条"
    print(msg, flush=True)
    return {"ok": True, "message": msg, "days": days, "total": total_saved, "important": total_important}


if __name__ == "__main__":
    run_fetch()
