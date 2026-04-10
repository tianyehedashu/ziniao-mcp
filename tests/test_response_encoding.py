"""Tests for lossless response body encoding pipeline.

Covers: decode_body_bytes, parse_charset, save_response_body.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from ziniao_mcp.sites import decode_body_bytes, parse_charset, save_response_body


# ---------------------------------------------------------------------------
# parse_charset
# ---------------------------------------------------------------------------

def test_parse_charset_standard() -> None:
    assert parse_charset("text/html; charset=shift_jis") == "shift_jis"


def test_parse_charset_quoted() -> None:
    assert parse_charset('text/html; charset="UTF-8"') == "UTF-8"


def test_parse_charset_missing() -> None:
    assert parse_charset("application/json") == ""


def test_parse_charset_empty() -> None:
    assert parse_charset("") == ""


# ---------------------------------------------------------------------------
# decode_body_bytes
# ---------------------------------------------------------------------------

def test_decode_utf8_body() -> None:
    raw = "こんにちは".encode("utf-8")
    assert decode_body_bytes(raw, "application/json; charset=utf-8") == "こんにちは"


def test_decode_shift_jis_body() -> None:
    text = "日本語テスト"
    raw = text.encode("shift_jis")
    assert decode_body_bytes(raw, "text/html; charset=shift_jis") == text


def test_decode_euc_jp_body() -> None:
    text = "文字化けテスト"
    raw = text.encode("euc-jp")
    assert decode_body_bytes(raw, "text/html; charset=euc-jp") == text


def test_decode_latin1_body() -> None:
    raw = bytes(range(0x80, 0x100))
    ct = "text/plain; charset=iso-8859-1"
    result = decode_body_bytes(raw, ct)
    assert result == raw.decode("iso-8859-1")


def test_decode_no_charset_valid_utf8() -> None:
    raw = "hello 🌍".encode("utf-8")
    assert decode_body_bytes(raw, "application/octet-stream") == "hello 🌍"


def test_decode_no_charset_invalid_utf8_falls_back() -> None:
    raw = b"\x82\xa0\x82\xa2"  # Shift_JIS "あい"
    result = decode_body_bytes(raw, "text/html")
    assert "\ufffd" in result  # graceful replacement, not crash


def test_decode_wrong_charset_falls_back() -> None:
    raw = b"\xff\xfe"
    result = decode_body_bytes(raw, "text/html; charset=nonexistent-codec")
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# save_response_body — raw bytes path (body_b64)
# ---------------------------------------------------------------------------

def test_save_raw_bytes_shift_jis(tmp_path: Path) -> None:
    """Shift_JIS bytes survive round-trip without corruption."""
    original = "価格：￥1,000".encode("shift_jis")
    b64 = base64.b64encode(original).decode()
    out = tmp_path / "out.csv"
    save_response_body("", str(out), body_b64=b64)
    assert out.read_bytes() == original


def test_save_raw_bytes_binary(tmp_path: Path) -> None:
    """Arbitrary binary (e.g. partial PDF) preserved byte-for-byte."""
    original = bytes(range(256))
    b64 = base64.b64encode(original).decode()
    out = tmp_path / "out.bin"
    save_response_body("", str(out), body_b64=b64)
    assert out.read_bytes() == original


def test_save_raw_bytes_utf8_json_prettified(tmp_path: Path) -> None:
    """UTF-8 JSON body_b64 gets pretty-printed automatically."""
    obj = {"key": "value", "n": 42}
    raw = json.dumps(obj).encode("utf-8")
    b64 = base64.b64encode(raw).decode()
    out = tmp_path / "out.json"
    save_response_body("", str(out), body_b64=b64)
    written = out.read_text(encoding="utf-8")
    assert json.loads(written) == obj
    assert "\n" in written  # indented


def test_save_utf8_plain_text_default(tmp_path: Path) -> None:
    """Non-JSON UTF-8 body is written as UTF-8 text (default -o behaviour)."""
    text = "hello,世界,csv-line\n"
    raw = text.encode("utf-8")
    b64 = base64.b64encode(raw).decode()
    out = tmp_path / "out.txt"
    save_response_body("", str(out), body_b64=b64)
    assert out.read_text(encoding="utf-8") == text


def test_save_raw_shift_jis_not_corrupted_as_json(tmp_path: Path) -> None:
    """Non-UTF-8 body that isn't JSON → raw bytes, no U+FFFD."""
    original = "商品名：テスト".encode("shift_jis")
    b64 = base64.b64encode(original).decode()
    out = tmp_path / "out.csv"
    save_response_body("", str(out), body_b64=b64)
    assert out.read_bytes() == original
    assert b"\xef\xbf\xbd" not in out.read_bytes()


# ---------------------------------------------------------------------------
# save_response_body — --output-encoding path
# ---------------------------------------------------------------------------

def test_save_with_output_encoding_transcodes(tmp_path: Path) -> None:
    """Shift_JIS response transcoded to UTF-8 via --output-encoding."""
    text = "日本語テスト"
    raw = text.encode("shift_jis")
    b64 = base64.b64encode(raw).decode()
    ct = "text/html; charset=shift_jis"
    out = tmp_path / "out.txt"
    save_response_body("", str(out), body_b64=b64, content_type=ct, output_encoding="utf-8")
    assert out.read_text(encoding="utf-8") == text


def test_save_with_decode_encoding_cp932_no_content_type(tmp_path: Path) -> None:
    """Rakuten-style CSV: server omits charset; explicit cp932 → utf-8 file."""
    text = "レビュータイプ,商品名"
    raw = text.encode("cp932")
    b64 = base64.b64encode(raw).decode()
    out = tmp_path / "reviews.csv"
    save_response_body("", str(out), body_b64=b64, content_type="text/csv", decode_encoding="cp932")
    assert out.read_text(encoding="utf-8") == text


def test_save_with_output_encoding_json_prettified(tmp_path: Path) -> None:
    """JSON body transcoded via --output-encoding still gets pretty-printed."""
    obj = {"msg": "テスト"}
    raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    b64 = base64.b64encode(raw).decode()
    out = tmp_path / "out.json"
    save_response_body("", str(out), body_b64=b64, content_type="application/json", output_encoding="utf-8")
    written = out.read_text(encoding="utf-8")
    assert json.loads(written) == obj
    assert "\n" in written


# ---------------------------------------------------------------------------
# save_response_body — legacy fallback (no body_b64)
# ---------------------------------------------------------------------------

def test_save_legacy_text_fallback(tmp_path: Path) -> None:
    """When body_b64 is absent, falls back to body_text path."""
    obj = {"legacy": True}
    text = json.dumps(obj)
    out = tmp_path / "out.json"
    save_response_body(text, str(out))
    written = out.read_text(encoding="utf-8")
    assert json.loads(written) == obj
    assert "\n" in written  # pretty-printed
