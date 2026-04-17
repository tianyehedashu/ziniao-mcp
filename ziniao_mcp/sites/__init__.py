"""Site preset runtime.

This package is split into focused modules; the public surface is re-exported
below so that ``from ziniao_mcp.sites import …`` continues to work unchanged:

- :mod:`._base`           — ``SitePlugin`` extension contract.
- :mod:`.discovery`       — preset scan / ``list_presets`` / ``load_preset`` / ``fork_preset`` / ``USER_DIR`` / ``BUILTIN_DIR``.
- :mod:`.plugin_loader`   — ``get_plugin`` (user / repo / builtin / entry_points).
- :mod:`.rendering`       — ``{{var}}`` substitution + type coercion.
- :mod:`.variables`       — ``secret`` / ``file`` / ``file_list`` resolution and file-ref tokens.
- :mod:`.validation`      — UI flow preset guard + ``header_inject`` normaliser.
- :mod:`.request`         — ``prepare_request`` / response body persistence + decoding helpers.
- :mod:`.pagination`      — ``run_site_fetch`` / ``paginate_all_generic`` / page merging.

Optional JSON fields on presets:

- ``auth``: ``{ "type": "cookie"|"xsrf"|"token"|"none", "hint": "..." }``
- ``header_inject``: ``list[dict]`` — declarative header injection rules.
  Each entry: ``{ "header": str, "source": "cookie"|"localStorage"|"sessionStorage"|"eval",
  "key": str, "expression": str, "transform": str }``.
- ``pagination``: ``body_field`` / ``offset`` config for ``--all`` (see built-in examples).
"""

from __future__ import annotations

from ._base import SitePlugin as SitePlugin
from .discovery import (
    BUILTIN_DIR as BUILTIN_DIR,
    USER_DIR as USER_DIR,
    _PRESET_ID_RE as _PRESET_ID_RE,
    _SKIP_DIRS as _SKIP_DIRS,
    _assert_safe_preset_id as _assert_safe_preset_id,
    _scan_dir as _scan_dir,
    _scan_ep_presets as _scan_ep_presets,
    _source_for_path as _source_for_path,
    fork_preset as fork_preset,
    list_presets as list_presets,
    load_preset as load_preset,
)
from .pagination import (
    _async_plugin_paginate_collect as _async_plugin_paginate_collect,
    _get_nested as _get_nested,
    _merge_page_bodies as _merge_page_bodies,
    _paginate_body_field as _paginate_body_field,
    _paginate_offset as _paginate_offset,
    _parse_body_dict as _parse_body_dict,
    _set_nested as _set_nested,
    _spec_for_page_fetch as _spec_for_page_fetch,
    _spec_with_body_dict as _spec_with_body_dict,
    paginate_all_generic as paginate_all_generic,
    plugin_overrides_paginate as plugin_overrides_paginate,
    run_site_fetch as run_site_fetch,
)
from .plugin_loader import (
    _load_plugin_from_file as _load_plugin_from_file,
    get_plugin as get_plugin,
)
from .rendering import (
    _VAR_RE as _VAR_RE,
    _coerce as _coerce,
    render_vars as render_vars,
)
from .request import (
    coerce_page_fetch_eval_result as coerce_page_fetch_eval_result,
    decode_body_bytes as decode_body_bytes,
    parse_charset as parse_charset,
    prepare_request as prepare_request,
    save_response_body as save_response_body,
)
from .response_contract import apply_response_contract as apply_response_contract
from .validation import (
    UI_ACTION_WHITELIST as UI_ACTION_WHITELIST,
    _SECRET_ALLOWED_STEP_FIELDS as _SECRET_ALLOWED_STEP_FIELDS,
    _VALID_INJECT_SOURCES as _VALID_INJECT_SOURCES,
    _normalize_header_inject as _normalize_header_inject,
    _validate_ui_preset as _validate_ui_preset,
    _walk_strings as _walk_strings,
)
from .variables import (
    _FILE_MAX_BYTES as _FILE_MAX_BYTES,
    _FILE_REF_PREFIX as _FILE_REF_PREFIX,
    _URL_REF_PREFIX as _URL_REF_PREFIX,
    _download_url_as_base64 as _download_url_as_base64,
    _read_file_as_base64 as _read_file_as_base64,
    _read_file_list_as_refs as _read_file_list_as_refs,
    _resolve_secret as _resolve_secret,
    resolve_file_refs as resolve_file_refs,
)

__all__ = [
    "BUILTIN_DIR",
    "SitePlugin",
    "UI_ACTION_WHITELIST",
    "USER_DIR",
    "apply_response_contract",
    "coerce_page_fetch_eval_result",
    "decode_body_bytes",
    "fork_preset",
    "get_plugin",
    "list_presets",
    "load_preset",
    "paginate_all_generic",
    "parse_charset",
    "plugin_overrides_paginate",
    "prepare_request",
    "render_vars",
    "resolve_file_refs",
    "run_site_fetch",
    "save_response_body",
]
