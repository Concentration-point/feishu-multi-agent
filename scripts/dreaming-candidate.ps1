$ErrorActionPreference = 'Stop'
$root = 'C:\Users\25723\.openclaw\workspace'
$dreams = Join-Path $root 'DREAMS.md'
$today = Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'
$daily = Join-Path $root ('memory\' + (Get-Date -Format 'yyyy-MM-dd') + '.md')
$yesterday = Join-Path $root ('memory\' + (Get-Date).AddDays(-1).ToString('yyyy-MM-dd') + '.md')

if (!(Test-Path $dreams)) {
  @'
# DREAMS.md

Nightly candidate memory distillation. This file is review-only. Do not merge entries into MEMORY.md without human review or explicit assistant confirmation.

'@ | Set-Content -Encoding UTF8 $dreams
}

$items = @()
foreach ($p in @($yesterday, $daily)) {
  if (Test-Path $p) {
    $items += "- Source: $p"
    $content = Get-Content $p -Raw -Encoding UTF8
    $matches = Select-String -InputObject $content -Pattern '老大|确认|要求|规则|记住|TODO|待办|错误|纠错|learning|失败|修复' -AllMatches
    if ($matches) {
      $snippet = ($matches.Matches | Select-Object -First 12 | ForEach-Object { $_.Value }) -join ', '
      $items += "  - Signals: $snippet"
    } else {
      $items += "  - Signals: no strong candidate signals"
    }
  }
}

$block = @"

---

## Dream candidate - $today

Mode: stage-short-term / review-only

### Candidate Sources
$($items -join "`n")

### Review Queue
- [ ] Check whether any item deserves promotion to MEMORY.md
- [ ] Check whether memory-wiki needs structured entity/topic update
- [ ] Check whether any stale memory should be deprecated

### Guardrails
- Do not auto-merge into MEMORY.md.
- Do not replace memory slot.
- Mem0 remains supplement-only.
"@

Add-Content -Encoding UTF8 -Path $dreams -Value $block
Write-Output "Dreaming candidate appended to $dreams"
