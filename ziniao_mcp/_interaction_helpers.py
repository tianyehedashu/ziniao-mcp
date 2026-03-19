"""Shared interaction dispatch helpers for both MCP tools and CLI daemon."""

from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING, Any, Optional, Union

if TYPE_CHECKING:
    from nodriver import Tab
    from nodriver.core.element import Element

    from .iframe import IFrameElement
    from .stealth.human_behavior import BehaviorConfig


def _get_behavior_cfg(sm: Any) -> Optional["BehaviorConfig"]:
    sc = sm.stealth_config
    if sc.enabled and sc.human_behavior:
        return sc.to_behavior_config()
    return None


def _is_ziniao(sm: Any) -> bool:
    try:
        return sm.get_active_session().backend_type == "ziniao"
    except RuntimeError:
        return False


async def dispatch_click(
    tab: "Tab",
    selector: str,
    elem: Union["Element", "IFrameElement"],
    sm: Any,
) -> None:
    cfg = _get_behavior_cfg(sm)
    is_zn = _is_ziniao(sm)
    if cfg:
        from .stealth import human_click, random_delay  # pylint: disable=import-outside-toplevel
        await random_delay(cfg=cfg)
        await human_click(tab, selector, cfg=cfg, element=elem)
    elif is_zn:
        from .stealth.human_behavior import _move_mouse_humanlike, _get_box_from_element  # pylint: disable=import-outside-toplevel
        box = await _get_box_from_element(elem)
        if box:
            cx = box["x"] + box["width"] / 2
            cy = box["y"] + box["height"] / 2
            await _move_mouse_humanlike(tab, cx, cy)
            await tab.mouse_click(cx, cy)
        else:
            await elem.mouse_click()
    else:
        await elem.click()


async def dispatch_fill(
    tab: "Tab",
    selector: str,
    value: str,
    elem: Union["Element", "IFrameElement"],
    sm: Any,
) -> None:
    cfg = _get_behavior_cfg(sm)
    is_zn = _is_ziniao(sm)
    if cfg:
        from .stealth import human_fill, random_delay  # pylint: disable=import-outside-toplevel
        await random_delay(cfg=cfg)
        await human_fill(tab, selector, value, cfg=cfg, element=elem)
    elif is_zn:
        from .stealth.human_behavior import human_fill as _hfill  # pylint: disable=import-outside-toplevel
        await _hfill(tab, selector, value, element=elem)
    else:
        await elem.clear_input()
        await elem.send_keys(value)


async def dispatch_type(
    tab: "Tab",
    text: str,
    selector: str,
    elem: Optional[Union["Element", "IFrameElement"]],
    sm: Any,
) -> None:
    cfg = _get_behavior_cfg(sm)
    is_zn = _is_ziniao(sm)
    if cfg:
        from .stealth import human_type, random_delay  # pylint: disable=import-outside-toplevel
        await random_delay(cfg=cfg)
        await human_type(tab, text, selector, cfg=cfg, element=elem)
    elif is_zn:
        from .stealth.human_behavior import human_type as _htype  # pylint: disable=import-outside-toplevel
        await _htype(tab, text, selector, element=elem)
    else:
        from nodriver import cdp  # pylint: disable=import-outside-toplevel
        if elem:
            await elem.click()
        for char in text:
            await tab.send(cdp.input_.dispatch_key_event("char", text=char))
            await asyncio.sleep(random.uniform(0.03, 0.1))


async def dispatch_hover(
    tab: "Tab",
    selector: str,
    elem: Union["Element", "IFrameElement"],
    sm: Any,
) -> None:
    cfg = _get_behavior_cfg(sm)
    is_zn = _is_ziniao(sm)
    if cfg:
        from .stealth import human_hover, random_delay  # pylint: disable=import-outside-toplevel
        await random_delay(cfg=cfg)
        await human_hover(tab, selector, cfg=cfg, element=elem)
    elif is_zn:
        from .stealth.human_behavior import human_hover as _hhover  # pylint: disable=import-outside-toplevel
        await _hhover(tab, selector, element=elem)
    else:
        await elem.mouse_move()
