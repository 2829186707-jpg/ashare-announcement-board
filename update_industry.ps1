# Update EastMoney industry map (curl-based, EM blocks Python clients)
# Usage: powershell -ExecutionPolicy Bypass -File update_industry.ps1
$ErrorActionPreference = "Stop"
$BASE = "https://push2.eastmoney.com/api/qt/clist/get"
$FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
$FIELDS = "f12,f14,f100"
$out = @{}
$pn = 1
while ($true) {
    $url = "$BASE`?pn=$pn&pz=100&po=1&np=1&fltt=2&invt=2&fid=f3&fs=$FS&fields=$FIELDS"
    $raw = curl.exe -s --max-time 20 -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)" -H "Referer: https://quote.eastmoney.com/" $url
    if (-not $raw) { Write-Host "Page $pn empty, retry"; Start-Sleep -Seconds 2; continue }
    $j = $raw | ConvertFrom-Json
    $diff = $j.data.diff
    if (-not $diff) { Write-Host "No more data"; break }
    foreach ($it in $diff) {
        if ($it.f12) {
            $ind = if ($it.f100) { $it.f100 } else { "Unclassified" }
            $out[$it.f12] = @{ name = $it.f14; industry = $ind }
        }
    }
    Write-Host "Page $pn done, total $($out.Count)"
    if ($diff.Count -lt 100) { break }
    $pn++
    Start-Sleep -Milliseconds 400
}
$out | ConvertTo-Json -Depth 4 | Set-Content -Path "industry_map.json" -Encoding UTF8
Write-Host "Done: $($out.Count) stocks -> industry_map.json"
