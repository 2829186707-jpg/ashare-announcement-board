# -*- coding: utf-8 -*-
"""对已有数据的重要公告重新提取核心摘要（复用 fetch.extract_summary）"""
import json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import fetch
from config import DATA_DIR, PDF_WORKERS

f = os.path.join(DATA_DIR, "2026-09-08.json")
d = json.load(open(f, encoding="utf-8"))
anns = d["announcements"]
imp = [x for x in anns if x["important"] and x.get("url")]
print(f"待重提取摘要: {len(imp)} 条")

BASE = "http://static.cninfo.com.cn/"

def work(rec):
    u = rec.get("url") or ""
    adjunct = u[len(BASE):] if u.startswith(BASE) else u
    try:
        s, _ = fetch.extract_summary(adjunct, rec["sec_name"], rec["title"])
        return rec["title"], s
    except Exception as e:
        return rec["title"], None

t0 = time.time()
with ThreadPoolExecutor(max_workers=PDF_WORKERS) as ex:
    results = list(ex.map(work, imp))
done = sum(1 for _, s in results if s)
print(f"重提取完成: {done}/{len(results)} 条有摘要, 耗时 {time.time()-t0:.1f}s")

for rec, (_, s) in zip(imp, results):
    rec["summary"] = s

json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False)
print("已写回:", f)
