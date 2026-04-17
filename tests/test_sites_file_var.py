"""Unit tests for ``type: file`` variable support.

Covers ``_coerce``, ``_read_file_as_base64``, ``resolve_file_refs``,
and ``_resolve_body_file_refs`` (from dispatch).
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from ziniao_mcp.sites import (
    _FILE_REF_PREFIX,
    _URL_REF_PREFIX,
    resolve_file_refs,
)
from ziniao_mcp.sites import _coerce  # noqa: PLC2701


# ---------------------------------------------------------------------------
# _coerce + _read_file_as_base64
# ---------------------------------------------------------------------------

def test_coerce_file_local(tmp_path: Path) -> None:
    f = tmp_path / "test.png"
    f.write_bytes(b"\x89PNG\r\n")
    result = _coerce(str(f), {"type": "file"})
    assert result.startswith(_FILE_REF_PREFIX)
    assert str(f.resolve()) in result


def test_coerce_file_url() -> None:
    url = "https://example.com/image.jpg"
    result = _coerce(url, {"type": "file"})
    assert result == _URL_REF_PREFIX + url


def test_coerce_file_base64_passthrough() -> None:
    b64 = base64.b64encode(b"\x89PNG").decode("ascii")
    result = _coerce(b64, {"type": "file"})
    assert result == b64


def test_coerce_file_nonexistent_path_raises() -> None:
    with pytest.raises(FileNotFoundError, match="non-existent path"):
        _coerce("./does_not_exist.png", {"type": "file"})


def test_coerce_file_empty_string() -> None:
    assert _coerce("", {"type": "file"}) == ""


def test_coerce_str_unchanged() -> None:
    """Existing str type is NOT affected by file additions."""
    assert _coerce("hello", {"type": "str"}) == "hello"


def test_coerce_int_unchanged() -> None:
    assert _coerce("42", {"type": "int"}) == 42


# ---------------------------------------------------------------------------
# _coerce + file_list
# ---------------------------------------------------------------------------

def test_coerce_file_list_comma_separated(tmp_path: Path) -> None:
    a = tmp_path / "a.png"
    a.write_bytes(b"A")
    b = tmp_path / "b.png"
    b.write_bytes(b"B")
    result = _coerce(f"{a},{b}", {"type": "file_list"})
    assert isinstance(result, list)
    assert len(result) == 2
    assert all(r.startswith(_FILE_REF_PREFIX) for r in result)


def test_coerce_file_list_mixed_url_and_path(tmp_path: Path) -> None:
    a = tmp_path / "pic.png"
    a.write_bytes(b"X")
    url = "https://example.com/c.webp"
    result = _coerce(f"{a},{url}", {"type": "file_list"})
    assert result[0].startswith(_FILE_REF_PREFIX)
    assert result[1] == _URL_REF_PREFIX + url


def test_coerce_file_list_empty_string() -> None:
    assert _coerce("", {"type": "file_list"}) == []


def test_coerce_file_list_skip_blank_entries(tmp_path: Path) -> None:
    a = tmp_path / "a.png"
    a.write_bytes(b"A")
    result = _coerce(f" , {a} , , ", {"type": "file_list"})
    assert len(result) == 1
    assert result[0].startswith(_FILE_REF_PREFIX)


def test_coerce_file_list_accepts_python_list(tmp_path: Path) -> None:
    a = tmp_path / "a.png"
    a.write_bytes(b"A")
    result = _coerce([str(a), "https://host/b.jpg"], {"type": "file_list"})
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0].startswith(_FILE_REF_PREFIX)
    assert result[1].startswith(_URL_REF_PREFIX)


# ---------------------------------------------------------------------------
# resolve_file_refs
# ---------------------------------------------------------------------------

def test_resolve_expands_file_token(tmp_path: Path) -> None:
    f = tmp_path / "pic.png"
    content = b"\x89PNG\r\n\x1a\n"
    f.write_bytes(content)
    token = _FILE_REF_PREFIX + str(f)
    result = resolve_file_refs(token)
    assert result == base64.b64encode(content).decode("ascii")


def test_resolve_expands_nested_dict(tmp_path: Path) -> None:
    f = tmp_path / "nested.bin"
    f.write_bytes(b"DATA")
    obj = {"outer": {"image": _FILE_REF_PREFIX + str(f), "text": "hi"}}
    resolved = resolve_file_refs(obj)
    assert resolved["outer"]["image"] == base64.b64encode(b"DATA").decode()
    assert resolved["outer"]["text"] == "hi"


def test_resolve_expands_list(tmp_path: Path) -> None:
    f = tmp_path / "list.bin"
    f.write_bytes(b"AB")
    obj = [_FILE_REF_PREFIX + str(f), "plain"]
    resolved = resolve_file_refs(obj)
    assert resolved[0] == base64.b64encode(b"AB").decode()
    assert resolved[1] == "plain"


def test_resolve_file_not_found_raises() -> None:
    with pytest.raises(FileNotFoundError):
        resolve_file_refs(_FILE_REF_PREFIX + "/nonexistent/file.bin")


def test_resolve_file_too_large(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import ziniao_mcp.sites as sites_mod
    monkeypatch.setattr(sites_mod, "_FILE_MAX_BYTES", 10)
    f = tmp_path / "big.bin"
    f.write_bytes(b"X" * 100)
    with pytest.raises(ValueError, match="too large"):
        resolve_file_refs(_FILE_REF_PREFIX + str(f))


def test_resolve_plain_string_unchanged() -> None:
    assert resolve_file_refs("hello world") == "hello world"


def test_resolve_non_string_passthrough() -> None:
    assert resolve_file_refs(42) == 42
    assert resolve_file_refs(None) is None


# ---------------------------------------------------------------------------
# _resolve_body_file_refs (from dispatch)
# ---------------------------------------------------------------------------

def test_resolve_body_json_string(tmp_path: Path) -> None:
    from ziniao_mcp.cli.dispatch import _resolve_body_file_refs  # noqa: PLC2701

    f = tmp_path / "body.bin"
    f.write_bytes(b"\x01\x02")
    body_str = json.dumps({"image": _FILE_REF_PREFIX + str(f)})
    result = _resolve_body_file_refs(body_str, resolve_file_refs)
    assert isinstance(result, dict)
    assert result["image"] == base64.b64encode(b"\x01\x02").decode()


def test_resolve_body_dict(tmp_path: Path) -> None:
    from ziniao_mcp.cli.dispatch import _resolve_body_file_refs  # noqa: PLC2701

    f = tmp_path / "body2.bin"
    f.write_bytes(b"OK")
    body = {"data": _FILE_REF_PREFIX + str(f)}
    result = _resolve_body_file_refs(body, resolve_file_refs)
    assert result["data"] == base64.b64encode(b"OK").decode()


def test_resolve_body_empty() -> None:
    from ziniao_mcp.cli.dispatch import _resolve_body_file_refs  # noqa: PLC2701

    assert _resolve_body_file_refs("", resolve_file_refs) == ""
    assert _resolve_body_file_refs(None, resolve_file_refs) is None
