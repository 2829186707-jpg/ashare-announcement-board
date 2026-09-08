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

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

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
# 模板/报告头字段行（整句过滤）
_TEMPLATE_HEAD = re.compile(
    r"^(?:上市公司名称|信息披露义务人|股票上市地点|股票简称|股票代码|证券简称|证券代码|公告编号|公司代码|"
    r"住所|通讯地址|注册地址|办公地址|法定代表人|股份变动性质|签署日期|签署地点|报告日期|联系电话|"
    r"传真|电子信箱|联系人|收购人|出让方|受让方)[^，。；;]{0,40}[:：]")
# 保证声明/套话（整句过滤）
_DECLARE = re.compile(
    r"(?:本公司|公司)及?(?:董事会|监事会|全体董事|全体监事|全体成员|董事、监事|"
    r"董事、高级管理人员|全体董事、监事及高级管理人员)[^。；;]{0,25}?保证|"
    r"保证本公告内容不存在|保证本公告内容之|保证本公告内容真实|特此公告|"
    r"本公司及全体董事保证|本公司及全体监事保证|谨此公告|特此声明")
# 核心信息关键词（句子打分）
_CORE_KW = ["减持", "增持", "回购", "收购", "质押", "担保", "诉讼", "仲裁", "中标", "签订", "协议",
            "转让", "发行", "募集", "分红", "派息", "分配", "解除", "终止", "延期", "变更", "控制权",
            "表决权", "股份", "股权", "股票", "交易", "投资", "借款", "授信", "利润", "净利", "营业",
            "同比", "增长", "下降", "不超过", "不低于", "万元", "亿元", "授予", "解禁", "重组", "合并",
            "分立", "要约", "预案", "方案", "承诺", "预计", "金额", "比例", "万股", "%"]


# 报告头字段序列（句子内部挖除："上市公司名称：xxx 住所：xxx" 等；股份变动性质含关键信息，保留）
_FIELD_SEQ = re.compile(
    r"(?:上市公司名称|信息披露义务人名称|信息披露义务人|股票上市地点|股票简称|股票代码|证券简称|证券代码|公告编号|公司代码|"
    r"住所|通讯地址|注册地址|办公地址|法定代表人|签署日期|签署地点|报告日期|联系电话|传真|电子信箱)"
    r"\s*[:：]\s*[^，。；;]{0,60}")
# 简称定义噪音："（以下简称"公司"）" / "（以下简称"公司"或"本公司"）"
_ABBR = re.compile(r"[（(]以下简称[^）)]{1,40}[）)]")
# 声明片段："保证...真实、准确、完整"（容忍空格）
_ASSURE = re.compile(r"保证[^。；;]{0,24}真实[、，]?\s*准\s*确\s*[、，]?\s*完\s*整")
# 公司名（不计入关键词打分，避免"股份"二字误伤）
_CORP = re.compile(r"[\u4e00-\u9fa5]{2,20}股份有限公司")
# 目录行（权益变动报告书等）："....4" / "第二节信息披露义务人介绍...."
_TOC = re.compile(r"\d{1,2}\s*[。.·]{4,}|第[一二三四五六七八九十]+节")
# 名称字段变体："名称：xxx"（值不参与核心句）
_NAME_FIELD = re.compile(r"(?:信息披露义务人|收购人|出让方|受让方)?名称\s*[:：]\s*[^，。；;]{0,40}")


def _pick_core(text, title):
    """核心句提取：过滤模板/声明/报告头句，按信息量保留含数字或关键信息的句子"""
    # 优先取"重要内容提示"区域（若有），但仅作候选，仍需经句子过滤
    cand = text
    for marker in ["重要内容提示", "重要提示", "特别提示", "一、重要提示"]:
        idx = text.find(marker)
        if idx >= 0:
            seg = text[idx + len(marker): idx + len(marker) + 900]
            if len(seg.strip(" ：:。；;，, ")) > 40:
                cand = seg
                break
    # 按句切分，逐句过滤打分
    sents = [s.strip() for s in re.split(r"(?<=[。；;！？])", cand) if len(s.strip()) >= 8]
    picked, used = [], 0
    for s in sents:
        if _DECLARE.search(s) or _TEMPLATE_HEAD.match(s):
            continue
        s = _FIELD_SEQ.sub("", s)
        s = _NAME_FIELD.sub("", s)
        s = _ABBR.sub("", s)
        s = _ASSURE.sub("", s).strip(" ：:，, ")
        if len(s) < 8 or _TOC.search(s):
            continue
        s2 = _CORP.sub("", s)
        score = len(re.findall(r"\d", s2)) * 2 + sum(1 for k in _CORE_KW if k in s2) * 2
        if score < 2:
            continue
        picked.append(s)
        used += len(s)
        if used >= SUMMARY_MAX_CHARS:
            break
    out = "".join(picked)
    if len(out) < 60:
        # 兜底：保留全部非模板句（尽量保真）
        out = "".join(s for s in sents if not _DECLARE.search(s) and not _TEMPLATE_HEAD.match(s) and not _TOC.search(s))
        out = _FIELD_SEQ.sub("", out)
        out = _NAME_FIELD.sub("", out)
        out = _ABBR.sub("", out)
        out = _ASSURE.sub("", out)
    out = out[:SUMMARY_MAX_CHARS]
    if not out:
        out = text[:SUMMARY_MAX_CHARS]
    return out.strip(" ：:。；;，, ")


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
            pages = []
            for pno in range(n):
                t = doc[pno].get_text() or ""
                if t.strip():
                    pages.append(t.strip())
            doc.close()
            # 封面页检测：首页短（≤140字）且（极短 / 与标题高度重合 / 几乎无句号）；或首页为头字段页（含证券代码/公告编号）→ 跳过
            if len(pages) > 1:
                first = re.sub(r"\s+", "", pages[0])
                t0 = re.sub(r"\s+", "", title or "")
                overlap = sum(1 for ch in first if ch in t0) / max(len(first), 1)
                head_page = ("证券代码" in first or "公告编号" in first) and len(first) <= 1200
                if (len(first) <= 140 and (len(first) <= 40 or overlap > 0.45 or first.count("。") <= 1)) or head_page:
                    pages = pages[1:]
            text = " ".join(pages)
        except Exception:
            from pypdf import PdfReader
            reader = PdfReader(fname)
            pages = []
            for p in reader.pages[:PDF_PARSE_PAGES]:
                t = p.extract_text() or ""
                if t.strip():
                    pages.append(t.strip())
            if len(pages) > 1:
                first = re.sub(r"\s+", "", pages[0])
                t0 = re.sub(r"\s+", "", title or "")
                if len(first) <= 140 and (len(first) <= 40 or sum(1 for ch in first if ch in t0) / max(len(first), 1) > 0.45):
                    pages = pages[1:]
            text = " ".join(pages)
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
