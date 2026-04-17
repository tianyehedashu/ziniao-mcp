"""Tests for ``ziniao_mcp.sites.flow_images``."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from ziniao_mcp.sites.flow_images import strip_and_save_encoded_images


def test_strip_and_save_writes_png(tmp_path: Path) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    b64 = base64.b64encode(png).decode("ascii")
    result = strip_and_save_encoded_images(
        {"ok": True, "images": [{"encodedImage": b64, "seed": 1}]},
        str(tmp_path / "out" / "gen"),
    )
    saved = result.get("_saved_image_paths", [])
    assert len(saved) == 1
    p = Path(saved[0])
    assert p.read_bytes().startswith(b"\x89PNG")
    assert p.suffix == ".png"
    assert "[saved:" in result["images"][0]["encodedImage"]


def test_strip_no_images_unchanged() -> None:
    r = {"ok": True, "foo": 1}
    assert strip_and_save_encoded_images(r, "x") == r


def test_strip_empty_prefix_noop() -> None:
    r = {"ok": True, "images": [{"encodedImage": "abc"}]}
    out = strip_and_save_encoded_images(r, "   ")
    assert out is r


def _patch_httpx(monkeypatch: pytest.MonkeyPatch, resp_content: bytes, ct: str = "image/jpeg") -> None:
    """Patch httpx.get inside _download_fife_url (lazy import)."""
    import httpx as _httpx  # noqa: F811

    class FakeResp:
        status_code = 200
        content = resp_content
        headers = {"content-type": ct}

    monkeypatch.setattr(_httpx, "get", lambda *a, **kw: FakeResp())


def test_strip_fife_url_downloads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """fifeUrl images are downloaded via httpx and saved to disk."""
    jpg_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 20
    _patch_httpx(monkeypatch, jpg_bytes)

    result = strip_and_save_encoded_images(
        {"ok": True, "images": [{"fifeUrl": "https://storage.example/img.jpg", "seed": 42}]},
        str(tmp_path / "dl"),
    )
    saved = result.get("_saved_image_paths", [])
    assert len(saved) == 1
    assert Path(saved[0]).read_bytes() == jpg_bytes
    assert "[saved:" in result["images"][0]["fifeUrl"]


def test_strip_mixed_base64_and_fife(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Both encodedImage and fifeUrl on same item are handled."""
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    b64 = base64.b64encode(png).decode()
    jpg_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 10
    _patch_httpx(monkeypatch, jpg_bytes)

    result = strip_and_save_encoded_images(
        {"ok": True, "images": [
            {"encodedImage": b64, "seed": 1},
            {"fifeUrl": "https://storage.example/gen.jpg", "seed": 2},
        ]},
        str(tmp_path / "mix"),
    )
    saved = result.get("_saved_image_paths", [])
    assert len(saved) == 2
