$base = 'C:\Users\iveco\.openclaw\workspace\passive_radar'
$files = Get-ChildItem $base -Filter 'pr_parallel_20260802_*.md' | Sort-Object Name
Write-Output ("报告数: " + $files.Count)
$total_runs = 0; $total_m = 0; $total_adsb = 0
foreach ($f in $files) {
  $c = [System.IO.File]::ReadAllText($f.FullName, [System.Text.Encoding]::UTF8)
  $matchSec = $false; $mcnt = 0
  foreach ($line in ($c -split "`n")) {
    if ($line -match '## 匹配') { $matchSec = $true; continue }
    if ($matchSec -and $line -match '^- ') { $mcnt++ }
  }
  $adsb = 0
  $inAdsb = $false
  foreach ($line in ($c -split "`n")) {
    if ($line -match '## ADS-B') { $inAdsb = $true; continue }
    if ($inAdsb -and $line -match '^## ') { $inAdsb = $false }
    if ($inAdsb -and $line -match '^\| [A-Z0-9?]') { $adsb++ }
  }
  $total_runs++
  $total_m += $mcnt
  $total_adsb += $adsb
  Write-Output ("{0} | OK={1} ADSB={2}" -f $f.Name.Substring(13), $mcnt, $adsb)
}
Write-Output ""
if ($total_adsb -gt 0) {
  Write-Output ("汇总: {0} runs | matches {1} | ADSB refs {2} | rate {3:P1}" -f $total_runs, $total_m, $total_adsb, ($total_m/$total_adsb))
}
