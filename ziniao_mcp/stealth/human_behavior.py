"""人类行为模拟工具函数。

为 Playwright 页面操作注入拟人化的随机性：延迟、鼠标轨迹、输入节奏等，
降低被行为分析系统检测为自动化程序的概率。
"""

from __future__ import annotations

import asyncio
import math
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page  # type: ignore[reportMissingImports]


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
        x = (inv ** 3 * sx
             + 3 * inv ** 2 * t * cp1[0]
             + 3 * inv * t ** 2 * cp2[0]
             + t ** 3 * ex)
        y = (inv ** 3 * sy
             + 3 * inv ** 2 * t * cp1[1]
             + 3 * inv * t ** 2 * cp2[1]
             + t ** 3 * ey)
        points.append((round(x), round(y)))
    return points


async def _move_mouse_humanlike(
    page: "Page",
    target_x: float,
    target_y: float,
    *,
    cfg: BehaviorConfig | None = None,
) -> None:
    """沿贝塞尔曲线将鼠标从当前位置移动到目标坐标。"""
    c = cfg or _DEFAULT_CFG
    current = await page.evaluate(
        "() => ({x: window._lastMouseX || 0, y: window._lastMouseY || 0})"
    )
    start = (current["x"], current["y"])
    end = (target_x, target_y)
    points = _bezier_curve(start, end, c.mouse_steps)

    for px, py in points:
        await page.mouse.move(px, py)
        await asyncio.sleep(random.uniform(0.005, 0.02))

    await page.evaluate(
        f"() => {{ window._lastMouseX = {target_x}; window._lastMouseY = {target_y}; }}"
    )


async def human_click(
    page: "Page",
    selector: str,
    *,
    cfg: BehaviorConfig | None = None,
) -> None:
    """拟人化点击：鼠标轨迹移动 -> 随机偏移 -> 点击。"""
    c = cfg or _DEFAULT_CFG
    box = await page.locator(selector).bounding_box()
    if not box:
        await page.locator(selector).click()
        return

    offset_x = random.uniform(box["width"] * 0.2, box["width"] * 0.8)
    offset_y = random.uniform(box["height"] * 0.2, box["height"] * 0.8)
    target_x = box["x"] + offset_x
    target_y = box["y"] + offset_y

    if c.mouse_movement:
        await _move_mouse_humanlike(page, target_x, target_y, cfg=c)
    await page.mouse.click(target_x, target_y)


async def human_type(
    page: "Page",
    text: str,
    selector: str = "",
    *,
    cfg: BehaviorConfig | None = None,
) -> None:
    """拟人化逐字输入：每个字符间隔随机波动，偶尔较长停顿模拟思考。"""
    c = cfg or _DEFAULT_CFG
    if selector:
        await human_click(page, selector, cfg=c)
        await random_delay(100, 300, cfg=c)

    for i, char in enumerate(text):
        await page.keyboard.type(char, delay=0)
        base_delay = random.uniform(c.typing_min_ms, c.typing_max_ms)
        if i > 0 and random.random() < 0.05:
            base_delay += random.uniform(300, 800)
        await asyncio.sleep(base_delay / 1000)


async def human_fill(
    page: "Page",
    selector: str,
    value: str,
    *,
    cfg: BehaviorConfig | None = None,
) -> None:
    """拟人化填写：点击聚焦 -> 全选清除 -> 逐字输入。"""
    c = cfg or _DEFAULT_CFG
    await human_click(page, selector, cfg=c)
    await random_delay(100, 300, cfg=c)
    await page.keyboard.press("Control+a")
    await asyncio.sleep(random.uniform(0.05, 0.15))
    await page.keyboard.press("Backspace")
    await asyncio.sleep(random.uniform(0.1, 0.25))
    await human_type(page, value, cfg=c)


async def human_hover(
    page: "Page",
    selector: str,
    *,
    cfg: BehaviorConfig | None = None,
) -> None:
    """拟人化悬停：贝塞尔曲线移动鼠标到元素上。"""
    c = cfg or _DEFAULT_CFG
    box = await page.locator(selector).bounding_box()
    if not box:
        await page.locator(selector).hover()
        return

    target_x = box["x"] + random.uniform(box["width"] * 0.3, box["width"] * 0.7)
    target_y = box["y"] + random.uniform(box["height"] * 0.3, box["height"] * 0.7)

    if c.mouse_movement:
        await _move_mouse_humanlike(page, target_x, target_y, cfg=c)
    else:
        await page.mouse.move(target_x, target_y)


async def human_scroll(
    page: "Page",
    direction: str = "down",
    distance: int = 500,
    *,
    cfg: BehaviorConfig | None = None,
) -> None:
    """拟人化滚动：分多段小幅滚动，每段距离和间隔随机化。"""
    c = cfg or _DEFAULT_CFG
    remaining = abs(distance)
    sign = -1 if direction == "up" else 1

    while remaining > 0:
        chunk = min(remaining, random.randint(40, 120))
        await page.mouse.wheel(0, sign * chunk)
        remaining -= chunk
        await asyncio.sleep(random.uniform(0.02, 0.08))

    await random_delay(50, 200, cfg=c)
