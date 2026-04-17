"""iframe 支持：上下文切换 + 元素代理 + 协议级事件。

通过 CDP 隔离世界（Isolated World）在 iframe 内执行 JS，
结合协议级 Input 事件实现跨文档上下文的元素交互。
对上层工具透明——find_element 自动选择主文档或 iframe 路径。
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional, Union

if TYPE_CHECKING:
    from nodriver import Tab
    from nodriver.core.element import Element

    from .session import StoreSession

_logger = logging.getLogger("ziniao-mcp-debug")


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class IFrameContext:
    """当前活动的 iframe 上下文。"""

    frame_id: str
    context_id: int
    selector: str
    url: str = ""


@dataclass
class _CompatPosition:
    """与 nodriver Position 接口兼容的位置对象。"""

    left: float
    top: float
    width: float
    height: float

    @property
    def x(self) -> float:
        return self.left

    @property
    def y(self) -> float:
        return self.top

    @property
    def center(self) -> tuple[float, float]:
        return (self.left + self.width / 2, self.top + self.height / 2)

    def to_viewport(self, scale: float = 1):
        from nodriver import cdp  # pylint: disable=import-outside-toplevel

        return cdp.page.Viewport(
            x=self.x,
            y=self.y,
            width=self.width,
            height=self.height,
            scale=scale,
        )

    def __repr__(self) -> str:
        return (
            f"<Position(x={self.left}, y={self.top}, "
            f"width={self.width}, height={self.height})>"
        )


# ---------------------------------------------------------------------------
# IFrameElement — iframe 内元素的代理
# ---------------------------------------------------------------------------


class IFrameElement:
    """iframe 内元素的代理，接口兼容 nodriver Element 的常用子集。

    所有交互通过 CDP 协议级事件完成，不受 DOM 文档上下文限制。
    """

    def __init__(
        self,
        tab: "Tab",
        abs_x: float,
        abs_y: float,
        width: float,
        height: float,
        context_id: int,
        backend_node_id: Optional[int] = None,
    ):
        self._tab = tab
        self._abs_x = abs_x
        self._abs_y = abs_y
        self._width = width
        self._height = height
        self._context_id = context_id
        self.backend_node_id = backend_node_id

    async def click(self) -> None:
        from nodriver import cdp  # pylint: disable=import-outside-toplevel

        cx, cy = self._abs_x + self._width / 2, self._abs_y + self._height / 2
        await self._tab.send(
            cdp.input_.dispatch_mouse_event(
                "mousePressed",
                x=cx,
                y=cy,
                button=cdp.input_.MouseButton.LEFT,
                buttons=1,
                click_count=1,
            )
        )
        await self._tab.send(
            cdp.input_.dispatch_mouse_event(
                "mouseReleased",
                x=cx,
                y=cy,
                button=cdp.input_.MouseButton.LEFT,
                buttons=1,
                click_count=1,
            )
        )

    async def mouse_click(self) -> None:
        await self.click()

    async def get_position(self) -> _CompatPosition:
        return _CompatPosition(
            left=self._abs_x,
            top=self._abs_y,
            width=self._width,
            height=self._height,
        )

    async def mouse_move(self) -> None:
        from nodriver import cdp  # pylint: disable=import-outside-toplevel

        cx, cy = self._abs_x + self._width / 2, self._abs_y + self._height / 2
        await self._tab.send(cdp.input_.dispatch_mouse_event("mouseMoved", x=cx, y=cy))

    async def clear_input(self) -> None:
        from nodriver import cdp  # pylint: disable=import-outside-toplevel

        await self.click()
        await asyncio.sleep(0.1)
        await self._tab.send(
            cdp.input_.dispatch_key_event(
                "rawKeyDown",
                windows_virtual_key_code=65,
                modifiers=2,
            )
        )
        await self._tab.send(
            cdp.input_.dispatch_key_event(
                "keyUp",
                windows_virtual_key_code=65,
                modifiers=2,
            )
        )
        await asyncio.sleep(0.05)
        await self._tab.send(
            cdp.input_.dispatch_key_event(
                "rawKeyDown",
                windows_virtual_key_code=8,
            )
        )
        await self._tab.send(
            cdp.input_.dispatch_key_event(
                "keyUp",
                windows_virtual_key_code=8,
            )
        )

    async def send_keys(self, text: str) -> None:
        from nodriver import cdp  # pylint: disable=import-outside-toplevel

        for i, char in enumerate(text):
            await self._tab.send(cdp.input_.dispatch_key_event("char", text=char))
            base_delay = random.uniform(0.05, 0.15)
            if i > 0 and random.random() < 0.05:
                base_delay += random.uniform(0.3, 0.8)
            await asyncio.sleep(base_delay)

    async def send_file(self, *paths: str) -> None:
        from nodriver import cdp  # pylint: disable=import-outside-toplevel

        if not self.backend_node_id:
            raise RuntimeError("无法上传文件：缺少 backend_node_id")
        await self._tab.send(
            cdp.dom.set_file_input_files(
                files=list(paths),
                backend_node_id=cdp.dom.BackendNodeId(self.backend_node_id),
            )
        )


# ---------------------------------------------------------------------------
# 帧内 JS 执行
# ---------------------------------------------------------------------------


def _format_cdp_exception(exc: Any) -> str:
    """Render a ``cdp.runtime.ExceptionDetails`` into a human-readable string.

    Only reads string-typed fields (``text``, ``exception.description``); the
    ``exception`` field itself is a ``RemoteObject`` so it must never be used
    as the message directly or callers will see ``repr(RemoteObject(...))``.
    """
    text = getattr(exc, "text", "") or ""
    exc_obj = getattr(exc, "exception", None)
    desc = getattr(exc_obj, "description", None) if exc_obj is not None else None
    parts = [p for p in (text, desc) if p]
    return ": ".join(parts) or "unknown error"


async def eval_in_frame(
    tab: "Tab",
    context_id: int,
    expression: str,
    *,
    return_by_value: bool = True,
    await_promise: bool = True,
    strict: bool = False,
) -> Any:
    """在 iframe 的 isolated world 中执行 JavaScript。

    ``await_promise`` 与顶层 ``tab.evaluate`` 一致：为 True 时等待 Promise 解析。

    解包规则与 :func:`ziniao_mcp.cli.dispatch._safe_eval_js` 对齐——``value``
    字段用 ``is not None`` 判断（避免 ``0``/``""``/``False``/``[]`` 这类
    JSON-falsy 值被当空返回），并兜底处理 ``unserializable_value``。

    ``strict=True`` 时脚本异常会抛 :class:`RuntimeError`，让 step 层的
    ``on_error`` 能捕获并落盘快照；``strict=False``（默认）保持旧的"静默
    吞错返回 None"行为，供不介意异常的探测型调用方使用。
    """
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    result = await tab.send(
        cdp.runtime.evaluate(
            expression=expression,
            context_id=cdp.runtime.ExecutionContextId(context_id),
            return_by_value=return_by_value,
            await_promise=await_promise,
        )
    )
    if not result:
        return None
    remote_obj, exception = result
    if exception:
        if strict:
            raise RuntimeError(
                f"iframe eval failed: {_format_cdp_exception(exception)}"
            )
        _logger.debug("iframe eval 异常: %s", exception)
        return None
    if remote_obj is None:
        return None
    if not return_by_value:
        return remote_obj
    if remote_obj.value is not None:
        return remote_obj.value
    if getattr(remote_obj, "unserializable_value", None) is not None:
        return str(remote_obj.unserializable_value)
    return None


# ---------------------------------------------------------------------------
# iframe 内元素查找
# ---------------------------------------------------------------------------


async def _get_iframe_offset(
    tab: "Tab",
    iframe_selector: str,
) -> tuple[float, float]:
    """获取 iframe 在主文档中的绝对视口偏移量（含边框补偿）。"""
    js = (
        "(() => {"
        f"  const iframe = document.querySelector({_json.dumps(iframe_selector)});"
        "  if (!iframe) return null;"
        "  const rect = iframe.getBoundingClientRect();"
        "  return { x: rect.x + (iframe.clientLeft || 0),"
        "           y: rect.y + (iframe.clientTop || 0) };"
        "})()"
    )
    offset = await tab.evaluate(js, return_by_value=True)
    if not offset or not isinstance(offset, dict):
        return (0.0, 0.0)
    return (offset.get("x", 0.0), offset.get("y", 0.0))


async def find_element_in_frame(
    tab: "Tab",
    selector: str,
    iframe_ctx: IFrameContext,
    *,
    timeout: float = 10,
) -> Optional[IFrameElement]:
    """在 iframe 内查找元素，返回含绝对视口坐标的 IFrameElement 代理。"""
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    js_find = (
        "(() => {"
        f"  const el = document.querySelector({_json.dumps(selector)});"
        "  if (!el) return null;"
        "  const rect = el.getBoundingClientRect();"
        "  return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };"
        "})()"
    )

    deadline = asyncio.get_event_loop().time() + timeout
    elem_rect: Optional[dict] = None
    while asyncio.get_event_loop().time() < deadline:
        elem_rect = await eval_in_frame(tab, iframe_ctx.context_id, js_find)
        if elem_rect and isinstance(elem_rect, dict):
            break
        await asyncio.sleep(0.3)

    if not elem_rect or not isinstance(elem_rect, dict):
        return None

    offset_x, offset_y = await _get_iframe_offset(tab, iframe_ctx.selector)
    abs_x = offset_x + elem_rect["x"]
    abs_y = offset_y + elem_rect["y"]

    backend_node_id = None
    try:
        result = await tab.send(
            cdp.runtime.evaluate(
                expression=f"document.querySelector({_json.dumps(selector)})",
                context_id=cdp.runtime.ExecutionContextId(iframe_ctx.context_id),
                return_by_value=False,
            )
        )
        if result:
            remote_obj = result[0]
            if hasattr(remote_obj, "object_id") and remote_obj.object_id:
                node = await tab.send(
                    cdp.dom.describe_node(object_id=remote_obj.object_id)
                )
                if node and hasattr(node, "backend_node_id"):
                    backend_node_id = int(node.backend_node_id)
    except Exception:  # pylint: disable=broad-exception-caught
        _logger.debug("获取 iframe 内元素 backend_node_id 失败（非关键）")

    return IFrameElement(
        tab=tab,
        abs_x=abs_x,
        abs_y=abs_y,
        width=elem_rect["width"],
        height=elem_rect["height"],
        context_id=iframe_ctx.context_id,
        backend_node_id=backend_node_id,
    )


_VISIBLE_MARKER = "data-ziniao-visible"


async def _select_first_visible_in_main_doc(
    tab: "Tab", selector: str, timeout: float
) -> Optional[Union["Element", IFrameElement]]:
    """主文档中优先选择第一个可见且可交互的元素，避免 querySelector 命中 type=hidden 等不可见节点。"""
    sel_escaped = _json.dumps(selector)
    js_mark_first_visible = (
        f"(function(sel) {{"
        f"  const els = document.querySelectorAll(sel);"
        f"  for (const el of els) {{"
        f"    if (el.offsetParent === null) continue;"
        f"    const r = el.getBoundingClientRect();"
        f"    if (r.width <= 0 || r.height <= 0) continue;"
        f"    const s = window.getComputedStyle(el);"
        f"    if (s.visibility === 'hidden' || s.display === 'none' || parseFloat(s.opacity) === 0) continue;"
        f"    if (el.type === 'hidden') continue;"
        f"    el.setAttribute({_json.dumps(_VISIBLE_MARKER)}, '1');"
        f"    return true;"
        f"  }}"
        f"  return false;"
        f"}})({sel_escaped})"
    )
    try:
        marked = await tab.evaluate(js_mark_first_visible, return_by_value=True)
        if marked is True:
            elem = await tab.select(f'[{_VISIBLE_MARKER}="1"]', timeout=timeout)
            await tab.evaluate(
                f"document.querySelector('[{_VISIBLE_MARKER}=\"1\"]')?.removeAttribute({_json.dumps(_VISIBLE_MARKER)})",
                return_by_value=True,
            )
            return elem
    except Exception:  # pylint: disable=broad-exception-caught
        _logger.debug(
            "_select_first_visible_in_main_doc failed, falling back to tab.select"
        )
    return None


async def find_element(
    tab: "Tab",
    selector: str,
    store: "StoreSession",
    *,
    timeout: float = 10,
) -> Optional[Union["Element", IFrameElement]]:
    """统一元素查找：自动根据 iframe 上下文选择查找路径。

    主文档下优先返回第一个可见、可交互的元素（避免命中 type=hidden 等），
    再回退到 tab.select(selector)。
    返回 nodriver Element 或 IFrameElement，二者接口兼容。
    """
    if store.iframe_context:
        return await find_element_in_frame(
            tab,
            selector,
            store.iframe_context,
            timeout=timeout,
        )
    elem = await _select_first_visible_in_main_doc(tab, selector, timeout)
    if elem is not None:
        return elem
    return await tab.select(selector, timeout=timeout)


# ---------------------------------------------------------------------------
# Frame 树收集
# ---------------------------------------------------------------------------


async def collect_frames(tab: "Tab") -> list[dict]:
    """收集页面中所有 frame 的信息。"""
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    frame_tree = await tab.send(cdp.page.get_frame_tree())
    if not frame_tree:
        return []

    frames: list[dict] = []

    def _walk(tree, depth: int = 0) -> None:
        f = tree.frame
        frames.append(
            {
                "frame_id": str(f.id_),
                "url": f.url,
                "name": f.name or "",
                "depth": depth,
            }
        )
        for child in tree.child_frames or []:
            _walk(child, depth + 1)

    _walk(frame_tree)
    return frames


# ---------------------------------------------------------------------------
# Frame 切换
# ---------------------------------------------------------------------------


async def switch_to_frame(tab: "Tab", selector: str) -> IFrameContext:
    """切换到指定 iframe，创建 isolated world 并返回上下文。"""
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    elem = await tab.select(selector, timeout=10)
    if not elem:
        raise RuntimeError(f"未找到 iframe 元素: {selector}")

    node = await tab.send(cdp.dom.describe_node(backend_node_id=elem.backend_node_id))
    if not node:
        raise RuntimeError(f"无法获取 iframe 节点描述: {selector}")

    frame_id = getattr(node, "frame_id", None)
    if not frame_id:
        raise RuntimeError(f"元素 {selector} 不是有效的 iframe（无 frame_id）")

    context_id = await tab.send(
        cdp.page.create_isolated_world(
            frame_id=cdp.page.FrameId(str(frame_id)),
            world_name="ziniao_iframe_context",
            grant_univeral_access=True,
        )
    )

    url = ""
    try:
        url_result = await tab.send(
            cdp.runtime.evaluate(
                expression="window.location.href",
                context_id=cdp.runtime.ExecutionContextId(int(context_id)),
                return_by_value=True,
            )
        )
        if url_result:
            remote_obj = url_result[0]
            url = getattr(remote_obj, "value", "") or ""
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    return IFrameContext(
        frame_id=str(frame_id),
        context_id=int(context_id),
        selector=selector,
        url=url,
    )
