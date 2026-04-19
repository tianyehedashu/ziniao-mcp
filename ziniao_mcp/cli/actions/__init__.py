"""Action handlers extracted from dispatch.py.

Each module provides async handler functions with the signature
``async def handler(sm: Any, args: dict) -> dict``.
"""

from . import (
    getters,
    find,
    input,
    interaction,
    js,
    js_actions,
    media,
    navigation,
    state,
    upload,
)

# Re-export all handler functions for convenient import
from .navigation import navigate, wait, back, forward, reload  # noqa: F401
from .interaction import click, fill, type_text, insert_text, press_key, hover, drag, dblclick, focus, select_option, check, uncheck  # noqa: F401
from .upload import upload, upload_hijack, upload_react, clear_overlay  # noqa: F401
from .media import snapshot, screenshot  # noqa: F401
from .js import safe_eval_js, run_js_in_context  # noqa: F401
from .js_actions import eval_js, console  # noqa: F401
from .getters import get_text, get_html, get_value, get_attr, get_title, get_url, get_count  # noqa: F401
from .find import find_nth, find_text, find_role  # noqa: F401
from .state import is_visible, is_enabled, is_checked, scroll, scroll_into  # noqa: F401
from .input import keydown, keyup, mouse_move, mouse_down, mouse_up, mouse_wheel, clipboard  # noqa: F401
