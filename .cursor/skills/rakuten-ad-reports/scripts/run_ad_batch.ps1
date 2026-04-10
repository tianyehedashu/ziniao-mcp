#requires -Version 5.1
<#
.SYNOPSIS
  乐天 RMS 广告：按 A～F 组合一键落盘 + 可选汇总（JST 起止自动算）。

.DESCRIPTION
  - 在已 open-store 且登录 RMS 的终端执行。
  - 默认输出目录：exports/batch_<start>_<end>/（可用 -OutRoot / -SiteSlug 调整）。
  - 跑完建议：python .../aggregate_ad_exports.py -d <该目录>
  - rpp-search-item 不可跨自然月：Last30/Custom 跨月时本脚本仍只打一条 item 请求；按月切段、merge_rpp_search_json.py、再汇总见 references/SCRIPTS.md。

.PARAMETER Pack
  字母组合，不区分大小写。例如 A、AC、B、EF。
  A=复盘包(RPP/TDA item + 券店/券品)  B=仅 RPP+TDA 按商品  C=RPP 日+计划+按商品
  E=CPA  F=仅券店+券品  G=DEAL CSV（日期自动转 YYYYMMDD）

.EXAMPLE
  .\run_ad_batch.ps1 -Range Last7 -Pack AC

.EXAMPLE
  .\run_ad_batch.ps1 -Range Custom -StartDate 2026-04-01 -EndDate 2026-04-09 -Pack A -SiteSlug myshop
#>
param(
    [ValidateSet('Last7', 'Last30', 'ThisMonth', 'PrevMonth', 'Custom')]
    [string]$Range = 'Last7',

    [string]$StartDate = '',
    [string]$EndDate = '',

    [Parameter(Mandatory = $true)]
    [string]$Pack,

    [string]$OutRoot = 'exports',
    [string]$SiteSlug = '',

    [switch]$DryRun,
    [switch]$NoAggregate,
    [switch]$SkipCpnadv,
    [switch]$OpenStore,
    [string]$ZiniaoSite = ''
)

$ErrorActionPreference = 'Stop'
$script:DryRun = [bool]$DryRun

function Get-JstNow {
    $tz = [System.TimeZoneInfo]::FindSystemTimeZoneById('Tokyo Standard Time')
    [System.TimeZoneInfo]::ConvertTimeFromUtc((Get-Date).ToUniversalTime(), $tz)
}

function Get-ResolvedRange {
    param(
        [string]$Range,
        [string]$StartDate,
        [string]$EndDate
    )
    $jst = Get-JstNow
    $yesterday = $jst.Date.AddDays(-1)

    if ($Range -eq 'Custom') {
        if (-not $StartDate -or -not $EndDate) {
            throw 'Custom range requires -StartDate and -EndDate (YYYY-MM-DD).'
        }
        return @{ Start = $StartDate; End = $EndDate }
    }

    switch ($Range) {
        'Last7' {
            $e = $yesterday
            $s = $e.AddDays(-6)
            return @{ Start = $s.ToString('yyyy-MM-dd'); End = $e.ToString('yyyy-MM-dd') }
        }
        'Last30' {
            $e = $yesterday
            $s = $e.AddDays(-29)
            return @{ Start = $s.ToString('yyyy-MM-dd'); End = $e.ToString('yyyy-MM-dd') }
        }
        'ThisMonth' {
            $monthStart = Get-Date -Year $jst.Year -Month $jst.Month -Day 1
            if ($yesterday -lt $monthStart) {
                Write-Warning 'JST yesterday is before this calendar month (e.g. 1st of month). Using previous full month instead.'
                $prev = $monthStart.AddMonths(-1)
                $lastDay = [DateTime]::DaysInMonth($prev.Year, $prev.Month)
                $e = Get-Date -Year $prev.Year -Month $prev.Month -Day $lastDay
                $s = $prev
                return @{ Start = $s.ToString('yyyy-MM-dd'); End = $e.ToString('yyyy-MM-dd') }
            }
            return @{ Start = $monthStart.ToString('yyyy-MM-dd'); End = $yesterday.ToString('yyyy-MM-dd') }
        }
        'PrevMonth' {
            $firstThis = Get-Date -Year $jst.Year -Month $jst.Month -Day 1
            $firstPrev = $firstThis.AddMonths(-1)
            $lastDay = [DateTime]::DaysInMonth($firstPrev.Year, $firstPrev.Month)
            $e = Get-Date -Year $firstPrev.Year -Month $firstPrev.Month -Day $lastDay
            return @{ Start = $firstPrev.ToString('yyyy-MM-dd'); End = $e.ToString('yyyy-MM-dd') }
        }
    }
    throw "Unknown Range: $Range"
}

function Invoke-ZiniaoLine {
    param([string]$Line)
    Write-Host ">> $Line" -ForegroundColor Cyan
    if ($script:DryRun) { return }
    Invoke-Expression $Line
}

$rng = Get-ResolvedRange -Range $Range -StartDate $StartDate -EndDate $EndDate
$start = $rng.Start
$end = $rng.End

$letters = $Pack.ToUpperInvariant().ToCharArray() |
    Where-Object { $_ -match '[A-K]' } |
    ForEach-Object { $_.ToString() } |
    Select-Object -Unique
$set = @{}
foreach ($ch in $letters) { $set[$ch] = $true }

$batchName = "batch_$start`_$end"
$out = if ($SiteSlug) { Join-Path (Join-Path $OutRoot $SiteSlug) $batchName } else { Join-Path $OutRoot $batchName }
if (-not $script:DryRun) {
    New-Item -ItemType Directory -Path $out -Force | Out-Null
}

$here = $PSScriptRoot
$agg = Join-Path $here 'aggregate_ad_exports.py'

Write-Host "JST range: $start .. $end | Out: $out | Pack: $($letters -join '')" -ForegroundColor Green

if ($OpenStore) {
    if (-not $ZiniaoSite) { throw '-OpenStore requires -ZiniaoSite.' }
    Invoke-ZiniaoLine "ziniao open-store $ZiniaoSite"
}

# --- RPP / TDA / CPA ---
if ($set.ContainsKey('C')) {
    Invoke-ZiniaoLine "ziniao rakuten rpp-search -V start_date=$start -V end_date=$end -V selection_type=1 --all -o `"$out/rpp_daily.json`""
    Invoke-ZiniaoLine "ziniao rakuten rpp-search -V start_date=$start -V end_date=$end -V selection_type=2 --all -o `"$out/rpp_campaign.json`""
}

if ($set.ContainsKey('A') -or $set.ContainsKey('B') -or $set.ContainsKey('C')) {
    Invoke-ZiniaoLine "ziniao rakuten rpp-search-item -V start_date=$start -V end_date=$end --all -o `"$out/rpp_item.json`""
}

if ($set.ContainsKey('A') -or $set.ContainsKey('B')) {
    Invoke-ZiniaoLine "ziniao rakuten tda-reports-search-item -V start_date=$start -V end_date=$end --all -o `"$out/tda_item.json`""
}

if ($set.ContainsKey('E')) {
    Invoke-ZiniaoLine "ziniao rakuten cpa-reports-search -V start_date=$start -V end_date=$end -o `"$out/cpa.json`""
}

# --- 券 ---
$wantCpn = ($set.ContainsKey('A') -or $set.ContainsKey('F')) -and -not $SkipCpnadv
if ($wantCpn) {
    Invoke-ZiniaoLine "ziniao rakuten cpnadv-performance-retrieve -V start_date=$start -V end_date=$end --all -o `"$out/cpnadv_shop.json`""
    Invoke-ZiniaoLine "ziniao rakuten cpnadv-performance-retrieve-item -V start_date=$start -V end_date=$end --all -o `"$out/cpnadv_item.json`""
}

# --- DEAL ---
if ($set.ContainsKey('G')) {
    $ds = $start.Replace('-', '')
    $de = $end.Replace('-', '')
    Invoke-ZiniaoLine "ziniao rakuten datatool-deal-csv -V start_date=$ds -V end_date=$de -V period=daily -o `"$out/deal_daily.csv`""
}

# --- H / I / J / K：脚本不代跑或需按月，避免误调用 ---
if ($set.ContainsKey('H')) {
    Write-Warning 'H R-Mail: run manually, e.g. ziniao rakuten rmail-reports -o "<path>/rmail.html"'
}
if ($set.ContainsKey('I')) {
    $ym = $start.Substring(0, 7)
    Write-Warning "I purchase (monthly): ziniao rakuten shared-purchase-detail -V target_month=$ym -o `"$out/purchase_$ym.json`""
}
if ($set.ContainsKey('J')) {
    $ym = $start.Substring(0, 7)
    Write-Warning "J affiliate pending (monthly): ziniao rakuten afl-report-pending -V date=$ym -o `"$out/afl_$ym.json`""
}
if ($set.ContainsKey('K')) {
    Write-Host 'K: strategy only; no fetch. Conclude from summary + context.' -ForegroundColor DarkYellow
}
if ($set.ContainsKey('D')) {
    Write-Warning 'D Expert needs shop_url: ziniao --json rakuten rpp-exp-merchant, then rpp-exp-report / tda-exp-report (see SKILL).'
}

if (-not $NoAggregate -and -not $script:DryRun) {
    if (Test-Path $agg) {
        Write-Host ">> python `"$agg`" -d `"$out`" -o `"$out/summary.json`"" -ForegroundColor Cyan
        & python $agg -d $out -o "$out/summary.json"
    }
    else {
        Write-Warning "aggregate_ad_exports.py not found: $agg"
    }
}
