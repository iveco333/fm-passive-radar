$base = 'C:\Users\iveco\.openclaw\workspace\passive_radar'
$files = Get-ChildItem $base -Filter 'pr_parallel_20260802_*.md' | Sort-Object Name
Write-Output ("报告文件数: " + $files.Count)
$total_runs = 0; $total_matches = 0; $total_adsb = 0; $total_fa = 0
foreach ($f in $files) {
  $c = Get-Content $f.FullName -Raw
  $ok = ([regex]::Matches($c, '\[OK\]')).Count
  $no = ([regex]::Matches($c, '\[NO\]')).Count
  $adsb = ([regex]::Matches($c, 'ADS-B\]  ')).Count
  $total_runs++
  $total_matches += $ok
  $total_adsb += $adsb
  $total_fa += $no
  Write-Output ("{0} | OK={1} NO={2} ADSB={3}" -f $f.Name, $ok, $no, $adsb)
}
Write-Output ""
Write-Output ("=== 汇总: {0} 次运行, 匹配 {1}, 未匹配 {2}, ADS-B参照 {3} ===" -f $total_runs, $total_matches, $total_fa, $total_adsb)
if ($total_adsb -gt 0) { Write-Output ("匹配率(按ADS-B参照): {0:P1}" -f ($total_matches / $total_adsb)) }
