"""人类行为模拟工具函数。

为 nodriver Tab 操作注入拟人化的随机性：延迟、鼠标轨迹、输入节奏等，
降低被行为分析系统检测为自动化程序的概率。
"""

from __future__ import annotations

import asyncio
import math
import random
import weakref
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Union

if TYPE_CHECKING:
    from nodriver import Tab
    from nodriver.core.element import Element

    from ..iframe import IFrameElement


_MOUSE_POS_CACHE: "weakref.WeakKeyDictionary[Tab, tuple[float, float]]" = (
    weakref.WeakKeyDictionary()
)
"""Per-tab last-known mouse position. Uses weak references so closed tabs are
garbage-collected instead of leaking entries; avoids polluting ``Tab``'s
attribute namespace (which belongs to the nodriver library)."""


@dataclass
class BehaviorConfig:
    """人类行为模拟参数。"""

    delay_min_ms: int = 200
    delay_max_ms: int = 800
    typing_min_ms: int = 50
    typing_max_ms: int = 150
    mouse_movement: bool = True
    mouse_steps: int = 15


_DEFAULT_CFG = BehaviorConfig()


async def random_delay(
    min_ms: int | None = None,
    max_ms: int | None = None,
    *,
    cfg: BehaviorConfig | None = None,
) -> None:
    """在操作间插入符合正态分布的随机等待。"""
    c = cfg or _DEFAULT_CFG
    lo = min_ms if min_ms is not None else c.delay_min_ms
    hi = max_ms if max_ms is not None else c.delay_max_ms
    mean = (lo + hi) / 2
    std = (hi - lo) / 4
    delay = max(lo, min(hi, random.gauss(mean, std)))
    await asyncio.sleep(delay / 1000)


def _bezier_curve(
    start: tuple[float, float],
    end: tuple[float, float],
    steps: int,
) -> list[tuple[int, int]]:
    """生成三次贝塞尔曲线上的离散点，模拟鼠标轨迹。"""
    sx, sy = start
    ex, ey = end
    dx, dy = ex - sx, ey - sy
    dist = math.hypot(dx, dy)

    spread = max(30, dist * 0.3)
    cp1 = (
        sx + dx * random.uniform(0.2, 0.4) + random.gauss(0, spread * 0.3),
        sy + dy * random.uniform(0.2, 0.4) + random.gauss(0, spread * 0.3),
    )
    cp2 = (
        sx + dx * random.uniform(0.6, 0.8) + random.gauss(0, spread * 0.3),
        sy + dy * random.uniform(0.6, 0.8) + random.gauss(0, spread * 0.3),
    )

    points: list[tuple[int, int]] = []
    for i in range(steps + 1):
        t = i / steps
        inv = 1 - t
        x = inv**3 * sx + 3 * inv**2 * t * cp1[0] + 3 * inv * t**2 * cp2[0] + t**3 * ex
        y = inv**3 * sy + 3 * inv**2 * t * cp1[1] + 3 * inv * t**2 * cp2[1] + t**3 * ey
        points.append((round(x), round(y)))
    return points


async def _move_mouse_humanlike(
    tab: "Tab",
    target_x: float,
    target_y: float,
    *,
    cfg: BehaviorConfig | None = None,
) -> None:
    """沿贝塞尔曲线将鼠标从当前位置移动到目标坐标。

    起止坐标保存在模块级的 ``_MOUSE_POS_CACHE``（``WeakKeyDictionary``）里，
    而不是通过 ``tab.evaluate`` 写入 ``window._lastMouseX``。这样做原因：

    - 避免每次鼠标移动触发 2 次 ``Runtime.evaluate``（默认 deep 序列化 +
      ``user_gesture=True``）；后者在部分环境下（Chrome 导航中、
      Worker 初始化、iframe context 切换）会让 CDP 响应延迟，甚至
      挂住 daemon 命令。
    - 无状态残留：tab 对象被回收时字典条目自动清理，不污染 nodriver
      库的属性空间、也不依赖页面 JS 上下文。
    """
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    c = cfg or _DEFAULT_CFG
    start = _MOUSE_POS_CACHE.get(tab, (0, 0))
    end = (target_x, target_y)
    points = _bezier_curve(start, end, c.mouse_steps)

    for px, py in points:
        await tab.send(cdp.input_.dispatch_mouse_event("mouseMoved", x=px, y=py))
        await asyncio.sleep(random.uniform(0.005, 0.02))

    try:
        _MOUSE_POS_CACHE[tab] = (target_x, target_y)
    except TypeError:
        # Defensive: some mocks/tabs may not support weak references.
        # Losing the cache just resets the next move's start to (0,0),
        # which is acceptable (visible as a slightly longer trajectory).
        pass


async def _get_box_from_element(
    elem: Union["Element", "IFrameElement"],
) -> dict | None:
    """从已解析的元素获取边界框。"""
    try:
        pos = await elem.get_position()
        if pos is None:
            return None
        return {
            "x": pos.left,
            "y": pos.top,
            "width": pos.width,
            "height": pos.height,
        }
    except Exception:
        return None


async def _get_element_box(tab: "Tab", selector: str) -> dict | None:
    """获取元素的边界框信息。返回 {x, y, width, height} 或 None。"""
    elem = await tab.select(selector, timeout=5)
    if not elem:
        return None
    return await _get_box_from_element(elem)


async def human_click(
    tab: "Tab",
    selector: str,
    *,
    cfg: BehaviorConfig | None = None,
    element: Optional[Union["Element", "IFrameElement"]] = None,
) -> None:
    """拟人化点击：鼠标轨迹移动 -> 随机偏移 -> 点击。

    当 element 已提供（如 IFrameElement）时直接使用，跳过 tab.select。
    主文档 nodriver Element 最终用 DOM ``click()``（CDP callFunctionOn），避免仅合成鼠标事件在部分环境下不命中。
    iframe 内仍用 ``Input.dispatchMouseEvent`` 坐标点击。
    """
    from ..iframe import IFrameElement  # pylint: disable=import-outside-toplevel

    c = cfg or _DEFAULT_CFG
    if element:
        elem_ref: Optional[Union["Element", "IFrameElement"]] = element
        box = await _get_box_from_element(element)
    else:
        elem_ref = await tab.select(selector, timeout=5)
        box = await _get_box_from_element(elem_ref) if elem_ref else None

    if not box:
        if not elem_ref:
            elem_ref = await tab.select(selector, timeout=5)
        if elem_ref:
            if isinstance(elem_ref, IFrameElement):
                await elem_ref.mouse_click()
            else:
                await elem_ref.click()
        return

    offset_x = random.uniform(box["width"] * 0.2, box["width"] * 0.8)
    offset_y = random.uniform(box["height"] * 0.2, box["height"] * 0.8)
    target_x = box["x"] + offset_x
    target_y = box["y"] + offset_y

    if c.mouse_movement:
        await _move_mouse_humanlike(tab, target_x, target_y, cfg=c)
    if isinstance(elem_ref, IFrameElement):
        await tab.mouse_click(target_x, target_y)
    else:
        await elem_ref.click()


async def human_type(
    tab: "Tab",
    text: str,
    selector: str = "",
    *,
    cfg: BehaviorConfig | None = None,
    element: Optional[Union["Element", "IFrameElement"]] = None,
) -> None:
    """拟人化逐字输入：每个字符间隔随机波动，偶尔较长停顿模拟思考。"""
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    c = cfg or _DEFAULT_CFG
    if selector or element:
        await human_click(tab, selector, cfg=c, element=element)
        await random_delay(100, 300, cfg=c)

    for i, char in enumerate(text):
        await tab.send(cdp.input_.dispatch_key_event("char", text=char))
        base_delay = random.uniform(c.typing_min_ms, c.typing_max_ms)
        if i > 0 and random.random() < 0.05:
            base_delay += random.uniform(300, 800)
        await asyncio.sleep(base_delay / 1000)


async def human_fill(
    tab: "Tab",
    selector: str,
    value: str,
    *,
    cfg: BehaviorConfig | None = None,
    element: Optional[Union["Element", "IFrameElement"]] = None,
) -> None:
    """拟人化填写：点击聚焦 -> 全选清除 -> 逐字输入。"""
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    c = cfg or _DEFAULT_CFG
    await human_click(tab, selector, cfg=c, element=element)
    await random_delay(100, 300, cfg=c)
    await tab.send(
        cdp.input_.dispatch_key_event(
            "rawKeyDown",
            windows_virtual_key_code=65,
            modifiers=2,
        )
    )
    await tab.send(
        cdp.input_.dispatch_key_event(
            "keyUp",
            windows_virtual_key_code=65,
            modifiers=2,
        )
    )
    await asyncio.sleep(random.uniform(0.05, 0.15))
    await tab.send(
        cdp.input_.dispatch_key_event(
            "rawKeyDown",
            windows_virtual_key_code=8,
        )
    )
    await tab.send(
        cdp.input_.dispatch_key_event(
            "keyUp",
            windows_virtual_key_code=8,
        )
    )
    await asyncio.sleep(random.uniform(0.1, 0.25))
    await human_type(tab, value, cfg=c)


async def human_hover(
    tab: "Tab",
    selector: str,
    *,
    cfg: BehaviorConfig | None = None,
    element: Optional[Union["Element", "IFrameElement"]] = None,
) -> None:
    """拟人化悬停：贝塞尔曲线移动鼠标到元素上。"""
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    c = cfg or _DEFAULT_CFG
    if element:
        box = await _get_box_from_element(element)
    else:
        box = await _get_element_box(tab, selector)

    if not box:
        target = element or await tab.select(selector, timeout=5)
        if target:
            await target.mouse_move()
        return

    target_x = box["x"] + random.uniform(box["width"] * 0.3, box["width"] * 0.7)
    target_y = box["y"] + random.uniform(box["height"] * 0.3, box["height"] * 0.7)

    if c.mouse_movement:
        await _move_mouse_humanlike(tab, target_x, target_y, cfg=c)
    else:
        await tab.send(
            cdp.input_.dispatch_mouse_event("mouseMoved", x=target_x, y=target_y)
        )


async def human_scroll(
    tab: "Tab",
    direction: str = "down",
    distance: int = 500,
    *,
    cfg: BehaviorConfig | None = None,
) -> None:
    """拟人化滚动：分多段小幅滚动，每段距离和间隔随机化。"""
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    c = cfg or _DEFAULT_CFG
    remaining = abs(distance)
    sign = -1 if direction == "up" else 1

    while remaining > 0:
        chunk = min(remaining, random.randint(40, 120))
        await tab.send(
            cdp.input_.dispatch_mouse_event(
                "mouseWheel",
                x=0,
                y=0,
                delta_x=0,
                delta_y=sign * chunk,
            )
        )
        remaining -= chunk
        await asyncio.sleep(random.uniform(0.02, 0.08))

    await random_delay(50, 200, cfg=c)
