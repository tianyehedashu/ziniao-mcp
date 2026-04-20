#Requires -Version 5.1
<#
.SYNOPSIS
    仓库根目录一键 `uv sync` + pytest。Windows 环境偏好见 docs/dev-environment-windows.md。

.EXAMPLE
    .\scripts\run_tests.ps1
    .\scripts\run_tests.ps1 -PytestArgs @("tests/test_daemon_idle.py", "-v")
#>
param(
    [string[]] $PytestArgs = @("tests/")
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

uv sync
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

uv run pytest @PytestArgs
exit $LASTEXITCODE
