"""Flow policy SSRF checks."""

from __future__ import annotations

import socket

from ziniao_mcp.flows.policy import allows_http_url


def _policy() -> dict:
    return {"external_call": {"http": {"enabled": True, "allow_private_network": False}}}


def test_http_policy_blocks_ipv6_loopback() -> None:
    assert allows_http_url(_policy(), "http://[::1]/") is False


def test_http_policy_blocks_dns_to_private(monkeypatch) -> None:
    def _fake_getaddrinfo(*_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    assert allows_http_url(_policy(), "https://metadata.example/") is False


def test_http_policy_allows_public_dns(monkeypatch) -> None:
    def _fake_getaddrinfo(*_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    assert allows_http_url(_policy(), "https://example.com/") is True


def test_private_network_override_still_respects_url_allowlist() -> None:
    policy = {
        "external_call": {
            "http": {
                "enabled": True,
                "allow_private_network": True,
                "url_allowlist": ["http://127.0.0.1:8000/*"],
            }
        }
    }
    assert allows_http_url(policy, "http://127.0.0.1:8000/health") is True
    assert allows_http_url(policy, "http://127.0.0.1:9000/health") is False
