# 紫鸟 MCP 项目任务脚本（Windows，无需 make）
# 用法: .\task.ps1 <任务名>  或  .\task.ps1 help
# 示例: .\task.ps1 run   .\task.ps1 test   .\task.ps1 upgrade

param(
    [Parameter(Position = 0)]
    [string]$Task = "help"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot

function Invoke-Uv {
    param([string[]]$Args)
    & uv @Args
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

switch ($Task.ToLower()) {
    "help" {
        Write-Host "常用任务："
        Write-Host "  .\task.ps1 install         - 安装依赖"
        Write-Host "  .\task.ps1 run             - 启动 MCP 服务器 (ziniao serve)"
        Write-Host "  .\task.ps1 test            - 运行单元/常规测试（不含集成）"
        Write-Host "  .\task.ps1 test-all        - 运行全部测试（含集成，需 .env）"
        Write-Host "  .\task.ps1 test-integration - 仅运行集成测试（需配置 .env）"
        Write-Host "  .\task.ps1 upgrade         - 升级依赖并更新 lock 后同步安装"
        Write-Host "  .\task.ps1 lock            - 仅更新 lock 文件 (uv.lock)"
        Write-Host "  .\task.ps1 check           - 检查 lock 是否与 pyproject 一致"
    }
    "install" {
        Push-Location $ProjectRoot
        try {
            Invoke-Uv sync
        } finally { Pop-Location }
    }
    "run" {
        Push-Location $ProjectRoot
        try { Invoke-Uv run ziniao serve } finally { Pop-Location }
    }
    "test" {
        Push-Location $ProjectRoot
        try {
            Invoke-Uv run pytest tests/ -v --ignore=tests/integration_test.py
        } finally { Pop-Location }
    }
    "test-all" {
        Push-Location $ProjectRoot
        try { Invoke-Uv run pytest tests/ -v } finally { Pop-Location }
    }
    "test-integration" {
        Push-Location $ProjectRoot
        try { Invoke-Uv run pytest tests/integration_test.py -v } finally { Pop-Location }
    }
    "upgrade" {
        Push-Location $ProjectRoot
        try {
            Invoke-Uv lock --upgrade
            Invoke-Uv sync
        } finally { Pop-Location }
    }
    "lock" {
        Push-Location $ProjectRoot
        try { Invoke-Uv lock } finally { Pop-Location }
    }
    "check" {
        Push-Location $ProjectRoot
        try { Invoke-Uv lock --check } finally { Pop-Location }
    }
    default {
        Write-Error "未知任务: $Task。运行 .\task.ps1 help 查看可用任务。"
        exit 1
    }
}
