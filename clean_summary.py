# -*- coding: utf-8 -*-
"""清洗已有摘要中的报告头信息（证券代码/简称/编号等），无需重新下载PDF"""
import glob
import json
import os
import re

HEAD_RE = re.compile(
    r"^(?:证券代码[^，。；;]{0,30}[，。；;]?|证券简称[^，。；;]{0,30}[，。；;]?"
    r"|公告编号[^，。；;]{0,30}[，。；;]?|上市公司名称[^，。；;]{0,50}[，。；;]?"
    r"|股票简称[^，。；;]{0,30}[，。；;]?|股票代码[^，。；;]{0,30}[，。；;]?"
    r"|股票上市地点[^，。；;]{0,30}[，。；;]?|公司代码[^，。；;]{0,30}[，。；;]?){1,8}"
)
SKIP_HEAD = re.compile(
    r"^(?:本公司及董事会全体成员[^。]{0,60}[。]?|本公司董事会及全体董事[^。]{0,60}[。]?"
    r"|本公司及全体董事[^。]{0,60}[。]?|本公司及监事会全体成员[^。]{0,60}[。]?"
    r"|重要内容提示[:：]?|特别提示[:：]?){0,4}"
)


def clean(s):
    if not s:
        return s
    s2 = HEAD_RE.sub("", s, count=1)
    s2 = SKIP_HEAD.sub("", s2, count=1)
    s2 = s2.strip(" ：:。；;，, \t\r\n")
    return s2 if len(s2) > 15 else s


if __name__ == "__main__":
    total = 0
    changed = 0
    for f in glob.glob(os.path.join("data", "*.json")):
        if os.path.basename(f) == "state.json":
            continue
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for a in data.get("announcements", []):
            if a.get("summary"):
                total += 1
                new_s = clean(a["summary"])
                if new_s != a["summary"]:
                    a["summary"] = new_s
                    changed += 1
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
    print(f"处理完成：共 {total} 条摘要，优化 {changed} 条")
