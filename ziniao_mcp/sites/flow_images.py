"""Backward-compatibility shim.

The logic originally lived here was generalised into
:mod:`ziniao_mcp.sites.save_media` so that any site (not just Google Flow /
Imagen) can reuse the base64 / URL → disk primitives.

Existing imports like ``from ziniao_mcp.sites.flow_images import
strip_and_save_encoded_images`` continue to work via this module; new code
should import from :mod:`ziniao_mcp.sites.save_media` directly.
"""

from __future__ import annotations

from .save_media import (  # noqa: F401 — re-export for callers
    _download_fife_url,
    _ext_from_content_type,
    _image_ext_from_magic,
    download_url_to_file,
    save_base64_as_file,
    strip_and_save_encoded_images,
)

__all__ = [
    "_download_fife_url",
    "_ext_from_content_type",
    "_image_ext_from_magic",
    "download_url_to_file",
    "save_base64_as_file",
    "strip_and_save_encoded_images",
]
