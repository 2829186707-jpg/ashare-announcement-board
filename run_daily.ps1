# Daily fetch + push script (Task Scheduler: weekdays 08:35)
$ErrorActionPreference = 'Continue'
$root = $PSScriptRoot
$py   = 'C:\Users\veken\AppData\Local\Programs\Python\Python314\python.exe'
Set-Location $root
$ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
function Log($m){ "$ts $m" | Out-File "$root\daily.log" -Append -Encoding utf8 }

Log '=== DAILY START ==='
# 1. Fetch announcements (resume from last_date)
try {
  Log 'Fetching announcements...'
  & $py fetch.py *>> "$root\daily.log"
  Log 'Fetch done'
} catch {
  Log "Fetch FAILED: $_"
}

# 2. Regenerate date index for static page
try {
  & $py -c "import json,os;ds=sorted([f[:-5] for f in os.listdir('data') if f.endswith('.json') and f not in ('state.json','dates.json')],reverse=True);json.dump(ds,open('data/dates.json','w',encoding='utf-8'),ensure_ascii=False)"
  Log 'dates.json regenerated'
} catch {
  Log "dates.json FAILED: $_"
}

# 3. Commit and push (skip if no changes)
try {
  $changed = git status --porcelain
  if ($changed) {
    git add -A
    git commit -m "daily update $ts"
    git push origin main
    Log 'Commit + push done'
  } else {
    Log 'No changes, skip commit'
  }
} catch {
  Log "git FAILED: $_"
}
Log '=== DAILY END ==='
