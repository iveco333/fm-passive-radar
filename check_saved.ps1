$base = 'C:\Users\iveco\.openclaw\workspace\passive_radar'
$dats = Get-ChildItem $base -Filter 'fm_rsp1_20260802_*.dat' | Sort-Object Name
Write-Output ('IQ文件数: ' + $dats.Count)
$dats | ForEach-Object { Write-Output ("{0} | {1:N1} MB | {2}" -f $_.Name, ($_.Length/1MB), $_.LastWriteTime) }
$jsons = Get-ChildItem $base -Filter 'adsb_20260802_*.json' | Sort-Object Name
Write-Output ('ADS-B快照数: ' + $jsons.Count)
$mds = Get-ChildItem $base -Filter 'pr_parallel_20260802_*.md' | Sort-Object Name
Write-Output ('报告数: ' + $mds.Count)
$pngs = Get-ChildItem $base -Filter 'pr_parallel_20260802_*.png' | Sort-Object Name
Write-Output ('图数: ' + $pngs.Count)
$sum = ($dats | Measure-Object Length -Sum).Sum
Write-Output ('IQ总大小: ' + [math]::Round($sum/1MB,1) + ' MB')
