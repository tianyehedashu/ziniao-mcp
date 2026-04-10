#Requires -Version 5.1
<#
.SYNOPSIS
  按自然日切片循环调用 ziniao rakuten rpp-search，避免长区间按日/按计划一次请求失败。

.DESCRIPTION
  生成若干条 ziniao 命令（默认每段 ChunkDays 天），分别 -o 到 exports 目录。
  selection_type: 1=按日汇总, 2=按计划（计划×日明细，需后台会话在 RPP 报表域）。

.PARAMETER OutDir
  输出目录，默认 .\exports

.EXAMPLE
  .\fetch_rpp_search_slices.ps1 -StartDate 2026-03-11 -EndDate 2026-04-09 -SelectionType 2 -ChunkDays 7
#>
param(
    [Parameter(Mandatory = $true)][string]$StartDate,
    [Parameter(Mandatory = $true)][string]$EndDate,
    [ValidateRange(1, 31)][int]$ChunkDays = 7,
    [ValidateSet(1, 2)][int]$SelectionType = 1,
    [string]$OutDir = "exports",
    [string]$NamePrefix = "rpp_search"
)

$ErrorActionPreference = "Stop"
$s0 = [datetime]::ParseExact($StartDate, "yyyy-MM-dd", $null)
$s1 = [datetime]::ParseExact($EndDate, "yyyy-MM-dd", $null)
if ($s1 -lt $s0) { throw "EndDate must be >= StartDate" }

if (-not (Test-Path -LiteralPath $OutDir)) {
    New-Item -ItemType Directory -Path $OutDir | Out-Null
}

$cur = $s0
$idx = 0
while ($cur -le $s1) {
    $segEnd = $cur.AddDays($ChunkDays - 1)
    if ($segEnd -gt $s1) { $segEnd = $s1 }
    $a = $cur.ToString("yyyy-MM-dd")
    $b = $segEnd.ToString("yyyy-MM-dd")
    $fn = Join-Path $OutDir ("{0}_st{1}_{2}_{3}.json" -f $NamePrefix, $SelectionType, ($a -replace '-', ''), ($b -replace '-', ''))
    $cmd = "ziniao rakuten rpp-search -V start_date=$a -V end_date=$b -V selection_type=$SelectionType --all -o $fn"
    Write-Output $cmd
    $idx++
    $cur = $segEnd.AddDays(1)
}

Write-Host ("# Generated {0} command(s). Paste/run each in a shell where ziniao + RMS login are ready." -f $idx) -ForegroundColor DarkGray
