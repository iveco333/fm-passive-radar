$base = 'C:\Users\iveco\.openclaw\workspace\passive_radar'
$files = Get-ChildItem $base -Filter 'pr_parallel_20260802_*.md' | Sort-Object Name
$total_m = 0; $total_adsb = 0
$reasons = @{}  # unmatched reason -> count
$matchStats = @() # matched entries: dist_diff, dop_diff
$snrStats = @()   # matched SNRs
foreach ($f in $files) {
  $c = [System.IO.File]::ReadAllText($f.FullName, [System.Text.Encoding]::UTF8)
  $inAdsb = $false; $inMatch = $false
  foreach ($line in ($c -split "`n")) {
    # ADS-B section rows: | CALLSIGN | alt | spd | hdg | hdist | sdist | brg | bi | fd |
    if ($line -match '^\| [A-Z]{3}[0-9]') { $total_adsb++; continue }
    # matched entries
    if ($line -match '^- ([A-Z0-9?]+): PR=([0-9.]+)km/([+-][0-9]+)Hz ADS-B=([0-9.]+)km/([+-][0-9]+)Hz') {
      $total_m++
      $dd = [Math]::Abs([double]$matches[4] - [double]$matches[2])
      $fd = [Math]::Abs([int]$matches[5] - [int]$matches[3])
      $matchStats += ,@($dd, $fd)
      continue
    }
    # unmatched reasons
    if ($line -match 'reason: (.*)') {
      $r = $matches[1]
      if ($reasons.ContainsKey($r)) { $reasons[$r]++ } else { $reasons[$r] = 1 }
    }
  }
}
Write-Output ("TOTAL matches: " + $total_m + " / ADSB refs: " + $total_adsb + "  rate: {0:P1}" -f ($total_m/$total_adsb))
Write-Output ""
Write-Output "=== unmatched reason distribution ==="
$reasons.GetEnumerator() | Sort-Object Value -Descending | ForEach-Object { Write-Output ("{0}: {1}" -f $_.Key, $_.Value) }
Write-Output ""
Write-Output "=== matched quality (dist_diff km / dop_diff Hz) ==="
foreach ($s in $matchStats) { Write-Output ("dist={0:N1}km  dop={1}Hz" -f $s[0], $s[1]) }
