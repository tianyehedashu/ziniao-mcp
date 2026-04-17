"""Tests for the ``media_contract`` extension chain.

Covers the three entry points that make ``--save-images`` work:

1. :func:`ziniao_mcp.sites.save_media.compile_media_contract` — the
   declarative JSON → items compiler.
2. :meth:`ziniao_mcp.sites._base.SitePlugin.media_contract` — the default
   fallback that dispatches to the compiler.
3. End-to-end: declarative rules + :func:`apply_media_contract` actually
   write files and patch the response.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from ziniao_mcp.sites import SitePlugin
from ziniao_mcp.sites.save_media import apply_media_contract, compile_media_contract


def _png_bytes() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 24


def _b64_png() -> str:
    return base64.b64encode(_png_bytes()).decode("ascii")


# --- compile_media_contract ------------------------------------------------


def test_compile_returns_empty_for_non_list_rules() -> None:
    assert compile_media_contract(None, {"images": []}) == []
    assert compile_media_contract({}, {"images": []}) == []
    assert compile_media_contract("nope", {"images": []}) == []
    assert compile_media_contract([], {"images": []}) == []


def test_compile_list_rule_extracts_both_base64_and_url() -> None:
    """Multi-field list rule without explicit ``stem_suffix`` uses the
    safe default ``-{idx}-{field}`` so per-field files cannot collide."""
    rules = [{
        "items_at": "images",
        "fields": [
            {"key": "encodedImage", "source": "base64"},
            {"key": "fifeUrl", "source": "url"},
        ],
    }]
    result = {
        "images": [
            {"encodedImage": _b64_png(), "seed": 1},
            {"fifeUrl": "https://storage.example/a.jpg", "seed": 2},
        ],
    }
    items = compile_media_contract(rules, result)
    assert items == [
        {
            "source": "base64",
            "value": _b64_png(),
            "stem_suffix": "-0-encodedImage",
            "path": ["images", 0, "encodedImage"],
        },
        {
            "source": "url",
            "value": "https://storage.example/a.jpg",
            "stem_suffix": "-1-fifeUrl",
            "path": ["images", 1, "fifeUrl"],
        },
    ]


def test_compile_single_field_list_rule_keeps_clean_idx_suffix() -> None:
    """Single-field list rule defaults to ``-{idx}`` (no noisy field suffix)."""
    rules = [{
        "items_at": "images",
        "fields": [{"key": "fifeUrl", "source": "url"}],
    }]
    result = {"images": [
        {"fifeUrl": "https://host/a.jpg"},
        {"fifeUrl": "https://host/b.jpg"},
    ]}
    items = compile_media_contract(rules, result)
    assert [it["stem_suffix"] for it in items] == ["-0", "-1"]


def test_compile_rejects_multi_field_template_missing_field_placeholder() -> None:
    """Multi-field rule with user-supplied template lacking ``{field}``
    must raise — silent file-name collisions would be a data-loss bug."""
    rules = [{
        "items_at": "images",
        "fields": [
            {"key": "encodedImage", "source": "base64"},
            {"key": "fifeUrl", "source": "url"},
        ],
        "stem_suffix": "-{idx}",
    }]
    result = {"images": [{"encodedImage": _b64_png(), "fifeUrl": "https://h/x.png"}]}
    with pytest.raises(ValueError, match="collide"):
        compile_media_contract(rules, result)


def test_compile_skips_missing_fields_quietly() -> None:
    """An element missing all declared fields should be ignored."""
    rules = [{
        "items_at": "images",
        "fields": [{"key": "encodedImage", "source": "base64"}],
    }]
    result = {"images": [{"seed": 99}]}
    assert compile_media_contract(rules, result) == []


def test_compile_rejects_non_url_for_url_source() -> None:
    """A value declared as ``source: url`` but not starting with http is skipped."""
    rules = [{
        "items_at": "items",
        "fields": [{"key": "u", "source": "url"}],
    }]
    result = {"items": [{"u": "not-a-url"}]}
    assert compile_media_contract(rules, result) == []


def test_compile_single_rule() -> None:
    rules = [{"at": "logo_b64", "source": "base64", "stem_suffix": "-logo"}]
    result = {"logo_b64": _b64_png()}
    items = compile_media_contract(rules, result)
    assert items == [{
        "source": "base64",
        "value": _b64_png(),
        "stem_suffix": "-logo",
        "path": ["logo_b64"],
    }]


def test_compile_single_rule_field_placeholder() -> None:
    rules = [{"at": "thumb_url", "source": "url", "stem_suffix": "-{field}"}]
    result = {"thumb_url": "https://host/x.webp"}
    items = compile_media_contract(rules, result)
    assert items[0]["stem_suffix"] == "-thumb_url"


def test_compile_missing_dotted_path_is_silent() -> None:
    rules = [{"at": "data.missing", "source": "base64"}]
    assert compile_media_contract(rules, {"data": {}}) == []


def test_compile_invalid_rule_in_list_does_not_break_others() -> None:
    """A bad rule in the middle should be skipped, good ones preserved."""
    rules = [
        {"items_at": "images", "fields": [{"key": "encodedImage", "source": "base64"}]},
        "bogus-non-dict",
        {"no_items_at_no_at": True},
        {"at": "logo", "source": "base64"},
    ]
    result = {"images": [{"encodedImage": _b64_png()}], "logo": _b64_png()}
    items = compile_media_contract(rules, result)
    assert len(items) == 2
    assert items[0]["path"] == ["images", 0, "encodedImage"]
    assert items[1]["path"] == ["logo"]


def test_compile_nested_items_at() -> None:
    rules = [{
        "items_at": "data.page.items",
        "fields": [{"key": "img", "source": "base64"}],
        "stem_suffix": "-{idx}",
    }]
    result = {"data": {"page": {"items": [{"img": _b64_png()}]}}}
    items = compile_media_contract(rules, result)
    assert items[0]["path"] == ["data", "page", "items", 0, "img"]


def test_compile_single_rule_supports_list_index_in_dotted_path() -> None:
    """Numeric path segments dereference lists (``data.pages.0.url``)."""
    rules = [{"at": "data.pages.0.url", "source": "url", "stem_suffix": "-first"}]
    result = {"data": {"pages": [
        {"url": "https://host/first.jpg"},
        {"url": "https://host/second.jpg"},
    ]}}
    items = compile_media_contract(rules, result)
    assert items == [{
        "source": "url",
        "value": "https://host/first.jpg",
        "stem_suffix": "-first",
        "path": ["data", "pages", 0, "url"],
    }]


def test_compile_list_index_out_of_range_is_silent() -> None:
    rules = [{"at": "arr.5.url", "source": "url"}]
    result = {"arr": [{"url": "https://h/x.jpg"}]}
    assert compile_media_contract(rules, result) == []


def test_compile_negative_list_index() -> None:
    rules = [{"at": "arr.-1.url", "source": "url", "stem_suffix": "-last"}]
    result = {"arr": [
        {"url": "https://h/a.jpg"},
        {"url": "https://h/b.jpg"},
    ]}
    items = compile_media_contract(rules, result)
    assert items[0]["value"] == "https://h/b.jpg"
    assert items[0]["path"] == ["arr", -1, "url"]


# --- SitePlugin.media_contract default ------------------------------------


def test_default_plugin_without_media_contract_returns_empty() -> None:
    assert SitePlugin().media_contract({"images": [{"encodedImage": _b64_png()}]}, spec={}) == []


def test_default_plugin_reads_spec_media_contract() -> None:
    """When the preset JSON carries ``media_contract``, the default
    :meth:`SitePlugin.media_contract` must compile it — no override needed."""
    spec = {
        "media_contract": [{
            "items_at": "images",
            "fields": [{"key": "encodedImage", "source": "base64"}],
        }],
    }
    result = {"images": [{"encodedImage": _b64_png()}]}
    items = SitePlugin().media_contract(result, spec)
    assert len(items) == 1
    assert items[0]["source"] == "base64"


def test_plugin_override_takes_precedence() -> None:
    """Subclasses override ``media_contract`` for custom logic."""
    class CustomPlugin(SitePlugin):
        def media_contract(self, result: dict, spec: dict) -> list[dict]:
            return [{"source": "base64", "value": "fixed", "stem_suffix": "-x", "path": []}]

    items = CustomPlugin().media_contract({"images": []}, spec={"media_contract": [{"items_at": "images"}]})
    assert items == [{"source": "base64", "value": "fixed", "stem_suffix": "-x", "path": []}]


# --- End-to-end declarative contract --------------------------------------


def test_declarative_contract_writes_file(tmp_path: Path) -> None:
    """Full path: preset JSON declares contract → default plugin compiles →
    :func:`apply_media_contract` writes file + patches result."""
    spec = {
        "media_contract": [{
            "items_at": "images",
            "fields": [{"key": "encodedImage", "source": "base64"}],
            "stem_suffix": "-{idx}",
        }],
    }
    result = {"ok": True, "images": [{"encodedImage": _b64_png(), "seed": 1}]}
    items = SitePlugin().media_contract(result, spec)
    out = apply_media_contract(result, items, str(tmp_path / "gen"))

    saved = out.get("_saved_image_paths", [])
    assert len(saved) == 1
    p = Path(saved[0])
    assert p.suffix == ".png"
    assert p.read_bytes().startswith(b"\x89PNG")
    assert "[saved:" in out["images"][0]["encodedImage"]
    assert result["images"][0]["encodedImage"] == _b64_png()


def test_declarative_contract_with_url_download(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """URL-source declarations trigger an HTTP download."""
    import httpx

    class FakeResp:
        status_code = 200
        content = b"\xff\xd8\xff\xe0" + b"\x00" * 32
        headers = {"content-type": "image/jpeg"}

    monkeypatch.setattr(httpx, "get", lambda *a, **kw: FakeResp())

    spec = {
        "media_contract": [{
            "items_at": "images",
            "fields": [{"key": "fifeUrl", "source": "url"}],
            "stem_suffix": "-{idx}",
        }],
    }
    result = {"images": [{"fifeUrl": "https://storage.example/x.jpg"}]}
    items = SitePlugin().media_contract(result, spec)
    out = apply_media_contract(result, items, str(tmp_path / "dl"))
    saved = out.get("_saved_image_paths", [])
    assert len(saved) == 1
    assert Path(saved[0]).suffix == ".jpg"


def test_spec_for_page_fetch_strips_media_contract() -> None:
    """The daemon never consumes ``media_contract``; it must be filtered out."""
    from ziniao_mcp.sites.pagination import _spec_for_page_fetch

    spec = {
        "url": "https://host/x",
        "media_contract": [{"at": "logo", "source": "base64"}],
        "_ziniao_secret_values": ["s"],
    }
    out = _spec_for_page_fetch(spec)
    assert "media_contract" not in out
    assert "_ziniao_secret_values" not in out
    assert out["url"] == "https://host/x"
