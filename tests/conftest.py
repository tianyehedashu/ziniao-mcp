"""Shared fixtures for ziniao-mcp tests."""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from ziniao_webdriver.client import ZiniaoClient

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _user_info() -> dict:
    return {
        "company": os.environ.get("ZINIAO_COMPANY", "test_co"),
        "username": os.environ.get("ZINIAO_USERNAME", "user"),
        "password": os.environ.get("ZINIAO_PASSWORD", "pass"),
    }


_SOCKET_PORT = int(os.environ.get("ZINIAO_SOCKET_PORT", "16851"))


@pytest.fixture()
def client_v5():
    return ZiniaoClient(
        client_path=os.environ.get(
            "ZINIAO_V5_CLIENT_PATH", r"C:\ziniao\starter.exe"
        ),
        socket_port=_SOCKET_PORT,
        user_info=_user_info(),
        version="v5",
    )


@pytest.fixture()
def client_v6():
    return ZiniaoClient(
        client_path=os.environ.get(
            "ZINIAO_V6_CLIENT_PATH", r"C:\ziniao\ziniao.exe"
        ),
        socket_port=_SOCKET_PORT,
        user_info=_user_info(),
        version="v6",
    )
