"""Site policy defaults for high-risk hosts."""

from __future__ import annotations

import pytest

from ziniao_mcp.site_policy import (
    configure_site_policies_from_merged_root,
    get_site_policy,
    host_from_url_or_host,
    policy_hint_for_url,
    reset_site_policies_cache,
)


@pytest.fixture(autouse=True)
def _reset_site_policy_cache():
    reset_site_policies_cache()
    yield
    reset_site_policies_cache()


def test_host_from_bare_domain():
    assert host_from_url_or_host("shopee.com.my/path") == "shopee.com.my"


def test_host_from_https_url():
    assert host_from_url_or_host("https://foo.shopee.com.my/x?y=1") == "foo.shopee.com.my"


def test_shopee_suffix_matches_builtins():
    pol = get_site_policy("https://foo.shopee.com.my/item")
    assert pol is not None
    assert pol.get("default_mode") == "passive"
    assert pol.get("allow_input_only") is True


def test_unknown_host_returns_none():
    assert get_site_policy("https://example.com/") is None


def test_policy_hint_mentions_passive_path():
    hint = policy_hint_for_url("https://shopee.com.my/")
    assert hint
    assert "passive" in hint.lower()
    assert "chrome connect" in hint.lower()


def test_yaml_policy_hint_override() -> None:
    configure_site_policies_from_merged_root(
        {
            "site_policy": {
                "policies": {
                    "shopee.com.my": {"policy_hint": "Custom: use passive-open only."},
                },
            },
        },
    )
    assert policy_hint_for_url("https://shopee.com.my/item") == "Custom: use passive-open only."


def test_yaml_partial_merge_keeps_builtin_keys() -> None:
    configure_site_policies_from_merged_root(
        {
            "site_policy": {
                "policies": {
                    "shopee.com.my": {"policy_hint": "x"},
                },
            },
        },
    )
    pol = get_site_policy("https://shopee.com.my/")
    assert pol is not None
    assert pol.get("default_mode") == "passive"
    assert pol.get("allow_runtime_attach") is False


def test_yaml_adds_new_host() -> None:
    configure_site_policies_from_merged_root(
        {
            "site_policy": {
                "policies": {
                    "highrisk.example": {
                        "default_mode": "passive",
                        "allow_runtime_attach": False,
                        "allow_stealth": False,
                        "allow_input_only": True,
                    },
                },
            },
        },
    )
    pol = get_site_policy("https://app.highrisk.example/path")
    assert pol is not None
    assert pol.get("default_mode") == "passive"
    hint = policy_hint_for_url("https://highrisk.example/")
    assert hint
    assert "passive" in hint.lower()


@pytest.mark.parametrize(
    "url",
    [
        "https://shopee.tw/",
        "https://shopee.sg/cart",
        "https://shopee.co.id/buyer",
        "https://shopee.com.br/anything",
        "https://seller.shopee.tw/portal",
        "https://mall.shopee.com/x",
    ],
)
def test_shopee_tld_family_all_match_passive(url: str) -> None:
    """Shopee shares the same anti-bot front across regional TLDs;
    every documented entry (and their subdomains) should hint passive."""
    pol = get_site_policy(url)
    assert pol is not None, url
    assert pol.get("default_mode") == "passive"
    assert pol.get("allow_runtime_attach") is False
    assert policy_hint_for_url(url)
