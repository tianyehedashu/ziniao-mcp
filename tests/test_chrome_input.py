"""Raw CDP input-only client: method whitelist and WebSocket batching."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from ziniao_mcp import chrome_input as chrome_input_mod


def test_allowed_methods_are_input_domain_only():
    for method in chrome_input_mod.ALLOWED_INPUT_METHODS:
        assert method.startswith("Input.")


def test_rejects_runtime_evaluate():
    with pytest.raises(ValueError, match="not allowed"):
        chrome_input_mod.assert_input_only_method("Runtime.evaluate")


@pytest.mark.asyncio
async def test_send_input_only_dispatches_whitelisted_methods(monkeypatch):
    sent: list[dict] = []

    class FakeWS:
        def __init__(self) -> None:
            self._resp_id = 0

        async def send(self, payload: str) -> None:
            sent.append(json.loads(payload))

        async def recv(self) -> str:
            # Real CDP may interleave events; this fake only answers sequential command ids.
            self._resp_id += 1
            return json.dumps({"id": self._resp_id, "result": {}})

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=FakeWS())
    cm.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(chrome_input_mod.websockets, "connect", MagicMock(return_value=cm))

    await chrome_input_mod.send_input_only_cdp(
        "ws://127.0.0.1/devtools/page/fake",
        [
            ("Input.insertText", {"text": "a"}),
            ("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": 1, "y": 2, "deltaX": 0, "deltaY": 3}),
        ],
    )
    assert [x["method"] for x in sent] == ["Input.insertText", "Input.dispatchMouseEvent"]


@pytest.mark.asyncio
async def test_send_input_only_refuses_non_input_methods_before_send(monkeypatch):
    """Reverse contract: a single illegal method aborts the whole batch.

    Even if the illegal entry comes after legal ones, ``send_input_only_cdp``
    must validate **all** methods up front and refuse to open the WebSocket
    or invoke ``ws.send`` for any of them.
    """
    sent: list[dict] = []
    connect_called = {"n": 0}

    class FakeWS:
        async def send(self, payload):  # pragma: no cover - must not be reached
            sent.append(json.loads(payload))

        async def recv(self) -> str:  # pragma: no cover - must not be reached
            return json.dumps({"id": 1, "result": {}})

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=FakeWS())
    cm.__aexit__ = AsyncMock(return_value=None)

    def fake_connect(*_args, **_kwargs):
        connect_called["n"] += 1
        return cm

    monkeypatch.setattr(chrome_input_mod.websockets, "connect", fake_connect)

    with pytest.raises(ValueError, match="not allowed"):
        await chrome_input_mod.send_input_only_cdp(
            "ws://127.0.0.1/devtools/page/fake",
            [
                ("Input.insertText", {"text": "ok"}),
                ("Runtime.evaluate", {"expression": "1+1"}),
            ],
        )
    assert sent == [], "禁用方法绝不能进入 ws.send"
    assert connect_called["n"] == 0, "白名单失败时不应建立 WebSocket"


@pytest.mark.asyncio
async def test_send_input_only_ignores_non_command_events(monkeypatch):
    """CDP-style events without an ``id`` (or with an unknown ``id``) must be
    skipped without consuming the batch deadline as if they were responses."""

    class FakeWS:
        def __init__(self) -> None:
            self._step = 0

        async def send(self, _payload):  # pragma: no cover - body unused
            return None

        async def recv(self) -> str:
            self._step += 1
            if self._step == 1:
                # Simulated event without an id (e.g. Network.requestWillBeSent
                # if some other client enabled Network on this target).
                return json.dumps({"method": "Network.requestWillBeSent", "params": {}})
            if self._step == 2:
                # Stale id from a prior session: must be ignored, not fulfilled.
                return json.dumps({"id": 999, "result": {}})
            return json.dumps({"id": 1, "result": {}})

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=FakeWS())
    cm.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(chrome_input_mod.websockets, "connect", MagicMock(return_value=cm))

    await chrome_input_mod.send_input_only_cdp(
        "ws://127.0.0.1/x",
        [("Input.insertText", {"text": "a"})],
        timeout=2.0,
    )
