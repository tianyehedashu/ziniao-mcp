#Requires -Version 5.1
<#
.SYNOPSIS
  为损坏或不完整的 .venv 补写 pyvenv.cfg（修复 "failed to locate pyvenv.cfg"）。

.DESCRIPTION
  常见于 .venv 目录被部分删除、拷贝不完整或同步中断后，Scripts\python.exe
  仍存在但根目录缺少 pyvenv.cfg。在仓库根执行本脚本后，再运行
  `uv sync`（若报「文件正在使用」，请先关闭占用 .venv 的 IDE/终端/Python）。

  说明：不在仓库根调用 `uv python find`（无 --no-project 时会解析到本仓库 .venv；
  带 --no-project 时部分环境会长时间阻塞），改为读取 %APPDATA%\uv\python 下已安装的
  uv 托管 CPython。

  占用 .venv 的常见进程：本仓库 `E:\...\ziniao\.venv\Scripts\python.exe -m ziniao_mcp`（MCP /
  调试）。可用 -StopZiniaoDaemon 结束后再 -Sync。

.EXAMPLE
  pwsh -File scripts/repair_venv_pyvenv_cfg.ps1
  pwsh -File scripts/repair_venv_pyvenv_cfg.ps1 -StopZiniaoDaemon -Sync -ReinstallPywin32
#>
param(
    [switch]$StopZiniaoDaemon,
    [switch]$Sync,
    [switch]$ReinstallPywin32
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if ($StopZiniaoDaemon) {
    $needle = (Join-Path $Root ".venv\Scripts\python.exe")
    Get-CimInstance Win32_Process -Filter "name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and ($_.CommandLine.Contains($needle)) -and ($_.CommandLine -match 'ziniao_mcp') } |
        ForEach-Object {
            Write-Host "Stopping ziniao_mcp PID $($_.ProcessId)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    Start-Sleep -Milliseconds 500
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Error "未找到 .venv\Scripts\python.exe。请在仓库根执行: uv venv"
}

$UvPyRoot = Join-Path $env:APPDATA "uv\python"
$PyExe = $null
if (Test-Path $UvPyRoot) {
    foreach ($pat in @("cpython-3.11.*", "cpython-3.10.*", "cpython-3.12.*")) {
        $dir = Get-ChildItem $UvPyRoot -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like $pat } |
            Sort-Object Name -Descending |
            Select-Object -First 1
        if ($dir) {
            $candidate = Join-Path $dir.FullName "python.exe"
            if (Test-Path $candidate) {
                $PyExe = $candidate
                break
            }
        }
    }
}
if (-not $PyExe) {
    Write-Error "未在 $UvPyRoot 找到 uv 托管的 CPython。请先执行: uv python install 3.11"
}

$HomeDir = Split-Path -Parent $PyExe
if ($HomeDir -match '\\Scripts$') {
    Write-Error "解析到的 Python 路径异常（home 不应为 ...\Scripts）。请检查 uv 托管 Python 安装。"
}
$VerLine = & $PyExe -c "import sys; print('%d.%d.%d' % sys.version_info[:3])"
$UvLine = ""
try {
    $UvRaw = & uv --version 2>&1 | Out-String
    if ($UvRaw -match 'uv\s+(\S+)') { $UvLine = $Matches[1] }
} catch { }

$Lines = @(
    "home = $HomeDir",
    "implementation = CPython"
)
if ($UvLine) { $Lines += "uv = $UvLine" }
$Lines += "version_info = $VerLine"
$Lines += "include-system-site-packages = false"
$Body = ($Lines -join "`n") + "`n"

$CfgPath = Join-Path $Root ".venv\pyvenv.cfg"
[System.IO.File]::WriteAllText($CfgPath, $Body, [System.Text.UTF8Encoding]::new($false))
Write-Host "已写入: $CfgPath"

if ($Sync) {
    Write-Host "Running: uv sync --link-mode=copy"
    & uv sync --link-mode=copy
}

if ($ReinstallPywin32) {
    if ($env:OS -notlike 'Windows*') {
        Write-Warning "-ReinstallPywin32 仅适用于 Windows，已跳过。"
    } else {
        Write-Host "Running: uv pip install --reinstall-package pywin32"
        & uv pip install --python ".venv\Scripts\python.exe" --reinstall-package pywin32 pywin32
    }
}

if (-not $Sync) {
    Write-Host "下一步（可选）: uv sync --link-mode=copy"
    Write-Host "若报「文件正在使用」: pwsh -File scripts/repair_venv_pyvenv_cfg.ps1 -StopZiniaoDaemon -Sync"
}
