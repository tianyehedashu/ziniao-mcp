"""Shared keyboard key mapping and modifier parsing utilities."""

KEY_MAP: dict[str, int] = {
    "Enter": 13, "Tab": 9, "Escape": 27, "Backspace": 8,
    "Delete": 46, "ArrowUp": 38, "ArrowDown": 40,
    "ArrowLeft": 37, "ArrowRight": 39, "Space": 32,
    "Home": 36, "End": 35, "PageUp": 33, "PageDown": 34,
}

_MODIFIER_BITS: dict[str, int] = {
    "control": 2, "ctrl": 2,
    "alt": 1,
    "meta": 4, "command": 4,
    "shift": 8,
}


def parse_key(key: str) -> tuple[str, int, int]:
    """Parse a key string like ``"Control+a"`` into ``(actual_key, vk_code, modifiers)``.

    Returns:
        actual_key: The base key name (e.g. ``"a"``).
        vk_code: Windows virtual key code.
        modifiers: Bitmask of modifier flags.
    """
    modifiers = 0
    actual_key = key
    if "+" in key:
        parts = key.split("+")
        for mod in parts[:-1]:
            modifiers |= _MODIFIER_BITS.get(mod.strip().lower(), 0)
        actual_key = parts[-1].strip()

    vk = KEY_MAP.get(actual_key, ord(actual_key.upper()) if len(actual_key) == 1 else 0)
    return actual_key, vk, modifiers
