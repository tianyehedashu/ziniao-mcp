"""Unit tests for cluster.json lease helpers."""

from __future__ import annotations

import time

import pytest

from ziniao_mcp import cluster as cl


@pytest.fixture()
def isolated_cluster(tmp_path, monkeypatch):
    monkeypatch.setattr(cl, "CLUSTER_FILE", tmp_path / "cluster.json")
    monkeypatch.setattr(cl, "CLUSTER_LOCK", tmp_path / "cluster.lock")
    yield


def test_cluster_status_creates_file(isolated_cluster, tmp_path) -> None:
    st = cl.cluster_status()
    assert st.get("version") == 1
    assert isinstance(st.get("leases"), list)
    assert (tmp_path / "cluster.json").exists()


def test_acquire_and_release(isolated_cluster) -> None:
    a = cl.acquire_lease(session_id="s1", ttl_sec=3600.0, owner="t", label="job")
    assert a["ok"] is True
    lid = a["lease_id"]
    st = cl.cluster_status()
    assert len(st["leases"]) == 1
    r = cl.release_lease(lid)
    assert r["released"] == 1
    st2 = cl.cluster_status()
    assert st2["leases"] == []


def test_acquire_respects_max_concurrent_browsers(isolated_cluster) -> None:
    cl.CLUSTER_FILE.write_text(
        '{"version": 1, "max_concurrent_browsers": 1, "leases": []}',
        encoding="utf-8",
    )
    first = cl.acquire_lease(session_id="s1", ttl_sec=3600.0)
    second = cl.acquire_lease(session_id="s2", ttl_sec=3600.0)
    assert first["ok"] is True
    assert second["ok"] is False
    assert "limit reached" in second["error"]


def test_acquire_rejects_duplicate_session_lease(isolated_cluster) -> None:
    first = cl.acquire_lease(session_id="s1", ttl_sec=3600.0)
    second = cl.acquire_lease(session_id="s1", ttl_sec=3600.0)
    assert first["ok"] is True
    assert second["ok"] is False
    assert second["existing_lease_id"] == first["lease_id"]


def test_prune_expired(isolated_cluster) -> None:
    state = {"leases": [{"lease_id": "x", "expires_at": time.time() - 10.0}]}
    removed = cl.prune_expired_leases(state)
    assert removed == 1
    assert state["leases"] == []
