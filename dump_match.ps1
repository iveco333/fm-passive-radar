$f = 'C:\Users\iveco\.openclaw\workspace\passive_radar\pr_parallel_20260802_092912.md'
$c = [System.IO.File]::ReadAllText($f, [System.Text.Encoding]::UTF8)
$idx = $c.IndexOf('## 匹配')
if ($idx -ge 0) {
  Write-Output ("--- 匹配 section raw (offset " + $idx + ") ---")
  Write-Output $c.Substring($idx, [Math]::Min(400, $c.Length - $idx))
}
Write-Output '--- line check ---'
foreach ($line in ($c -split "`n")) {
  if ($line -match 'CHH7148|CES2795|频差') {
    Write-Output ("LINE:[" + $line + "]")
  }
}
