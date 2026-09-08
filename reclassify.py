# -*- coding: utf-8 -*-
"""重新分类已有公告数据：应用新分类规则（人事变动降级、同主题核心筛选）并清洗摘要乱码符号"""
import glob
import json
import os
import re

from rules import classify, keep_core_important, clean_summary

if __name__ == "__main__":
    total = 0
    stats = {}
    for f in sorted(glob.glob(os.path.join("data", "*.json"))):
        if os.path.basename(f) == "state.json":
            continue
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        anns = data.get("announcements", [])
        for a in anns:
            tname, imp = classify(a["title"])
            a["type"] = tname
            a["important"] = imp
            if a.get("summary"):
                a["summary"] = clean_summary(a["summary"])
        keep_core_important(anns)
        data["important_count"] = sum(1 for a in anns if a["important"])
        data["total"] = len(anns)
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        total += len(anns)
        stats[f] = f"{data['important_count']}/{len(anns)}"
    print(f"处理完成，共 {total} 条")
    for k, v in stats.items():
        print(f"  {os.path.basename(k)}: 重要 {v}")
