"""回归 `_resolve_config` 与 `_merge_yaml_fallthrough` 的合并语义。

核心回归场景：项目 `config/config.yaml` 是模板骨架（字段存在但为空串），
全局 `~/.ziniao/config.yaml` 才是真实覆盖值。旧实现只读第一个候选文件，
导致项目模板的空串把全局真实值清零，`chrome.user_data_dir` 最终回落成
默认 `~/.ziniao/chrome-profile`，与 `ziniao config show` 展示结果不一致。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from ziniao_mcp import server as server_mod
from ziniao_mcp.server import (
    _load_yaml_file,
    _merge_yaml_fallthrough,
    _resolve_config,
)


# ------------------------------------------------------------------ #
#  合并规则
# ------------------------------------------------------------------ #

class TestMergeYamlFallthrough:
    def test_empty_string_in_project_falls_back_to_global(self) -> None:
        project = {"chrome": {"user_data_dir": "", "executable_path": ""}}
        base = {"chrome": {"user_data_dir": "D:/chrome-debug", "executable_path": "C:/chrome.exe"}}

        merged = _merge_yaml_fallthrough(project, base)

        assert merged["chrome"]["user_data_dir"] == "D:/chrome-debug"
        assert merged["chrome"]["executable_path"] == "C:/chrome.exe"

    def test_non_empty_project_overrides_global(self) -> None:
        project = {"chrome": {"user_data_dir": "E:/project-only"}}
        base = {"chrome": {"user_data_dir": "D:/chrome-debug"}}

        merged = _merge_yaml_fallthrough(project, base)

        assert merged["chrome"]["user_data_dir"] == "E:/project-only"

    def test_zero_port_in_project_falls_back_to_global(self) -> None:
        """``default_cdp_port: 0`` 在模板里表达"auto"，不应覆盖全局显式配置。"""
        project = {"chrome": {"default_cdp_port": 0}}
        base = {"chrome": {"default_cdp_port": 9222}}

        merged = _merge_yaml_fallthrough(project, base)

        assert merged["chrome"]["default_cdp_port"] == 9222

    def test_keys_only_in_base_are_preserved(self) -> None:
        project = {"chrome": {"user_data_dir": ""}}
        base = {"chrome": {"user_data_dir": "D:/x", "headless": True}}

        merged = _merge_yaml_fallthrough(project, base)

        assert merged["chrome"]["headless"] is True

    def test_nested_ziniao_section_merges_deeply(self) -> None:
        project = {
            "ziniao": {
                "browser": {"version": "", "client_path": "D:/ziniao.exe"},
                "stealth": {"enabled": False},
            }
        }
        base = {
            "ziniao": {
                "browser": {"version": "v6", "client_path": "C:/fallback.exe", "socket_port": 16851},
                "stealth": {"enabled": True, "js_patches": True},
            }
        }

        merged = _merge_yaml_fallthrough(project, base)

        assert merged["ziniao"]["browser"]["version"] == "v6"
        assert merged["ziniao"]["browser"]["client_path"] == "D:/ziniao.exe"
        assert merged["ziniao"]["browser"]["socket_port"] == 16851
        assert merged["ziniao"]["stealth"]["enabled"] is True
        assert merged["ziniao"]["stealth"]["js_patches"] is True

    def test_project_only_key_survives(self) -> None:
        project = {"chrome": {"new_key": "x"}}
        base: dict[str, Any] = {}

        merged = _merge_yaml_fallthrough(project, base)

        assert merged["chrome"]["new_key"] == "x"

    def test_empty_only_in_project_when_base_missing(self) -> None:
        """base 里完全没有的键，保留 project 空值，不引入 KeyError。"""
        project = {"chrome": {"executable_path": ""}}
        base: dict[str, Any] = {"chrome": {}}

        merged = _merge_yaml_fallthrough(project, base)

        assert merged["chrome"]["executable_path"] == ""


# ------------------------------------------------------------------ #
#  YAML 加载
# ------------------------------------------------------------------ #

class TestLoadYamlFile:
    def test_missing_file_returns_empty_dict(self, tmp_path: Path) -> None:
        assert _load_yaml_file(tmp_path / "missing.yaml") == {}

    def test_empty_yaml_returns_empty_dict(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.yaml"
        p.write_text("", encoding="utf-8")
        assert _load_yaml_file(p) == {}

    def test_malformed_yaml_logs_and_returns_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.yaml"
        p.write_text("chrome: [unclosed", encoding="utf-8")
        assert _load_yaml_file(p) == {}

    def test_none_path_returns_empty(self) -> None:
        assert _load_yaml_file(None) == {}


# ------------------------------------------------------------------ #
#  _resolve_config 集成
# ------------------------------------------------------------------ #

@pytest.fixture
def _isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """隔离 HOME、CWD、env 变量与 argv，确保测试不受外部真实配置影响。"""
    home = tmp_path / "home"
    home.mkdir()
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))  # Windows
    monkeypatch.chdir(cwd)
    for var in (
        "ZINIAO_COMPANY", "ZINIAO_USERNAME", "ZINIAO_PASSWORD",
        "ZINIAO_CLIENT_PATH", "ZINIAO_SOCKET_PORT", "ZINIAO_VERSION",
        "CHROME_PATH", "CHROME_EXECUTABLE_PATH",
        "CHROME_USER_DATA", "CHROME_USER_DATA_DIR",
        "CHROME_CDP_PORT",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("sys.argv", ["ziniao"])
    # dotenv_loader 会去找 ~/.ziniao/.env；用空目录隔离掉副作用
    monkeypatch.setattr(server_mod, "_print_package_version_and_exit", lambda: None)
    return tmp_path


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


class TestResolveConfigProjectGlobalMerge:
    """核心回归：项目模板空串 + 全局真实值 → 最终使用全局值。"""

    def test_project_empty_user_data_dir_falls_back_to_global(
        self, _isolated_env: Path
    ) -> None:
        cwd = _isolated_env / "cwd"
        home = _isolated_env / "home"

        _write_yaml(cwd / "config" / "config.yaml", {
            "chrome": {"executable_path": "", "user_data_dir": "", "default_cdp_port": 0, "headless": False},
            "ziniao": {"browser": {"version": "", "client_path": "", "socket_port": 0}},
        })
        _write_yaml(home / ".ziniao" / "config.yaml", {
            "chrome": {"user_data_dir": "D:/chrome-debug"},
        })

        cfg = _resolve_config()

        assert cfg["chrome"]["user_data_dir"] == "D:/chrome-debug"

    def test_explicit_config_argument_bypasses_merge(
        self, _isolated_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """显式 --config 走单文件语义，不与全局合并（避免"隐式"耦合）。"""
        cwd = _isolated_env / "cwd"
        home = _isolated_env / "home"

        explicit = cwd / "custom.yaml"
        _write_yaml(explicit, {"chrome": {"user_data_dir": ""}})
        _write_yaml(home / ".ziniao" / "config.yaml", {
            "chrome": {"user_data_dir": "D:/chrome-debug"},
        })

        monkeypatch.setattr("sys.argv", ["ziniao", "--config", str(explicit)])

        cfg = _resolve_config()

        assert cfg["chrome"]["user_data_dir"] == ""

    def test_env_var_still_wins_over_merged_yaml(
        self, _isolated_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cwd = _isolated_env / "cwd"
        home = _isolated_env / "home"

        _write_yaml(cwd / "config" / "config.yaml", {
            "chrome": {"user_data_dir": ""},
        })
        _write_yaml(home / ".ziniao" / "config.yaml", {
            "chrome": {"user_data_dir": "D:/chrome-debug"},
        })
        monkeypatch.setenv("CHROME_USER_DATA", "E:/from-env")

        cfg = _resolve_config()

        assert cfg["chrome"]["user_data_dir"] == "E:/from-env"

    def test_global_only_no_project_config(self, _isolated_env: Path) -> None:
        home = _isolated_env / "home"
        _write_yaml(home / ".ziniao" / "config.yaml", {
            "chrome": {"user_data_dir": "D:/only-global"},
        })

        cfg = _resolve_config()

        assert cfg["chrome"]["user_data_dir"] == "D:/only-global"

    def test_project_non_empty_still_wins_over_global(
        self, _isolated_env: Path
    ) -> None:
        cwd = _isolated_env / "cwd"
        home = _isolated_env / "home"

        _write_yaml(cwd / "config" / "config.yaml", {
            "chrome": {"user_data_dir": "E:/project-real"},
        })
        _write_yaml(home / ".ziniao" / "config.yaml", {
            "chrome": {"user_data_dir": "D:/chrome-debug"},
        })

        cfg = _resolve_config()

        assert cfg["chrome"]["user_data_dir"] == "E:/project-real"
