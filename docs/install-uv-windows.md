# Windows 下安装 uv

[uv](https://docs.astral.sh/uv/) 是 Python 包与项目管理工具，提供 `uvx` 命令可免安装直接运行 PyPI 上的包（如 `uvx ziniao serve` 启动本项目的 MCP 服务）。以下为在 **Windows** 上的安装方式。

## 方式一：PowerShell 一键安装（推荐）

在 **PowerShell** 中执行（非 CMD）：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

安装完成后**关闭并重新打开**终端，执行 `uv --version` 检查是否可用。

若提示无法执行脚本，可先执行：

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

再重新运行上述安装命令。

## 方式二：WinGet

已安装 [Windows Package Manager (WinGet)](https://learn.microsoft.com/zh-cn/windows/package-manager/winget/) 时：

```powershell
winget install --id=astral-sh.uv -e
```



## 方式三：pip（需先有 Python）

若系统已安装 Python 和 pip：

```powershell
pip install uv
```

## 安装后

- 使用 **uv**：`uv --version`、`uv sync`、`uv run ...` 等
- 使用 **uvx**：无需先安装包即可运行，例如：
  ```powershell
  uvx ziniao serve --help
  ```
  uv 会自动拉取 Python 与依赖并在隔离环境中执行。

## 升级 uv

```powershell
uv self update
```

## 在本仓库里开发（Windows）

克隆后若 `uv sync` / `pytest` 遇权限或文件占用，见 [dev-environment-windows.md](dev-environment-windows.md)（用户级 `uv.toml`、`uv tool install` 规避 `Scripts\*.exe` 占用、pytest basetemp、一键脚本）。

## 参考

- 官方安装文档：[Installation | uv](https://docs.astral.sh/uv/getting-started/installation/)
