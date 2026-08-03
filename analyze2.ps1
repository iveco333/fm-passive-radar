$base = 'C:\Users\iveco\.openclaw\workspace\passive_radar'
$files = Get-ChildItem $base -Filter 'pr_parallel_20260802_*.md' | Sort-Object Name
Write-Output ("报告数: " + $files.Count)
$total_runs = 0; $total_m = 0; $total_adsb = 0
foreach ($f in $files) {
  $c = Get-Content $f.FullName -Raw
  # count matched lines in 匹配 section
  $matchSec = $false; $mcnt = 0
  foreach ($line in ($c -split "`n")) {
    if ($line -match '^## 匹配') { $matchSec = $true; continue }
    if ($matchSec -and $line -match '^- ') { $mcnt++ }
  }
  # count ADS-B rows: lines starting with |  (skip header separators)
  $adsb = 0
  $inAdsb = $false
  foreach ($line in ($c -split "`n")) {
    if ($line -match '^## ADS-B') { $inAdsb = $true; continue }
    if ($inAdsb -and $line -match '^## ') { $inAdsb = $false }
    if ($inAdsb -and $line -match '^\| [A-Z0-9?]') { $adsb++ }
  }
  $total_runs++
  $total_m += $mcnt
  $total_adsb += $adsb
  Write-Output ("{0} | 匹配={1} ADS-B={2}" -f $f.Name.Substring(13), $mcnt, $adsb)
}
Write-Output ""
Write-Output ("汇总: {0} 次运行 | 匹配 {1} | ADS-B参照 {2} | 匹配率 {3:P1}" -f $total_runs, $total_m, $total_adsb, ($total_m/$total_adsb))
