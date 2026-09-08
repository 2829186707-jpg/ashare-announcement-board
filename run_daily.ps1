# -*- coding: utf-8 -*-
# 每日 8:35 计划任务脚本：抓取公告 -> 生成日期索引 -> 提交并推送 GitHub
$ErrorActionPreference = 'Continue'
$root = 'C:\Users\veken\Desktop\公告读取'
$py   = 'C:\Users\veken\AppData\Local\Programs\Python\Python314\python.exe'
Set-Location $root
$ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
function Log($m){ "$ts $m" | Out-File "$root\daily.log" -Append -Encoding utf8 }

Log '=== 开始每日任务 ==='
# 1. 抓取（断点续抓：上一交易日 ~ 今天）
try {
  Log '抓取公告...'
  & $py fetch.py *>> "$root\daily.log"
  Log '抓取完成'
} catch {
  Log "抓取失败: $_"
}

# 2. 生成日期索引（静态页日期下拉用）
try {
  & $py -c "import json,os;ds=sorted([f[:-5] for f in os.listdir('data') if f.endswith('.json') and f not in ('state.json','dates.json')],reverse=True);json.dump(ds,open('data/dates.json','w',encoding='utf-8'),ensure_ascii=False)"
  Log '日期索引已生成'
} catch {
  Log "日期索引失败: $_"
}

# 3. 提交并推送（无变更则跳过）
try {
  $changed = git status --porcelain
  if ($changed) {
    git add -A
    git commit -m "daily update $ts"
    git push origin main
    Log '提交并推送完成'
  } else {
    Log '无变更，跳过提交'
  }
} catch {
  Log "git 操作失败: $_"
}
Log '=== 每日任务结束 ==='
