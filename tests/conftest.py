"""Shared fixtures for ziniao (PyPI) / ziniao-mcp (repo) tests."""

import json
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


def _rakuten_json_files() -> dict[str, dict]:
    return {
        "rpp-search": {
            "name": "乐天·RPP 报表检索",
            "description": "搜索型广告（RPP）报表检索（支持按日等维度）；使用当前标签页登录态调用 API。",
            "auth": {"type": "xsrf", "hint": "需先在当前浏览器标签页登录 RMS", "show_hint": False},
            "pagination": {
                "type": "body_field",
                "page_field": "page",
                "total_field": "data.totalPage",
                "start": 1,
                "max_pages": 500,
                "merge_items_field": "data.rppReports",
            },
            "navigate_url": "https://ad.rms.rakuten.co.jp/rpp/reports",
            "mode": "fetch",
            "url": "https://ad.rms.rakuten.co.jp/rpp/api/reports/search",
            "method": "POST",
            "headers": {"Accept": "application/json", "Accept-Language": "ja", "Content-Type": "application/json"},
            "header_inject": [{"header": "X-XSRF-TOKEN", "source": "cookie", "key": "XSRF-TOKEN"}],
            "vars": {
                "start_date": {"type": "str", "required": True, "description": "开始日", "example": "2026-03-01"},
                "end_date": {"type": "str", "required": True, "description": "结束日", "example": "2026-03-07"},
                "page": {"type": "int", "default": 1, "description": "页码"},
                "selection_type": {"type": "int", "default": 1, "description": "汇总维度"},
                "campaign_type": {"type": "str", "default": "1", "description": "推广计划类型"},
            },
            "body": {
                "page": "{{page}}",
                "selectionType": "{{selection_type}}",
                "periodType": 2,
                "startDate": "{{start_date}}",
                "endDate": "{{end_date}}",
                "reportFilter": 1,
                "campaignType": "{{campaign_type}}",
                "rankType": 1,
                "allUsers": True,
                "newUsers": True,
                "existingUsers": True,
                "noOfClicks": True,
                "adsalesBefore": True,
                "cpc": True,
                "h12": True,
                "h720": True,
                "gms": True,
                "roas": True,
                "cv": True,
                "cvr": True,
                "cpa": True,
            },
        },
        "rpp-search-item": {
            "name": "乐天·RPP 报表检索（商品维度）",
            "auth": {"type": "xsrf", "hint": "", "show_hint": False},
            "pagination": {
                "type": "body_field",
                "page_field": "page",
                "total_field": "data.totalPage",
                "start": 1,
                "max_pages": 500,
                "merge_items_field": "data.rppReports",
            },
            "navigate_url": "https://ad.rms.rakuten.co.jp/rpp/reports",
            "mode": "fetch",
            "url": "https://ad.rms.rakuten.co.jp/rpp/api/reports/search",
            "method": "POST",
            "headers": {"Accept": "application/json", "Accept-Language": "ja", "Content-Type": "application/json"},
            "header_inject": [{"header": "X-XSRF-TOKEN", "source": "cookie", "key": "XSRF-TOKEN"}],
            "vars": {
                "start_date": {"type": "str", "required": True, "description": "开始日", "example": "2026-03-01"},
                "end_date": {"type": "str", "required": True, "description": "结束日", "example": "2026-03-07"},
                "page": {"type": "int", "default": 1, "description": "页码"},
            },
            "body": {"page": "{{page}}", "selectionType": 3, "periodType": 0, "startDate": "{{start_date}}", "endDate": "{{end_date}}"},
        },
        "cpnadv-performance-retrieve-item": {
            "name": "乐天·运用型优惠券效果（商品维度）",
            "auth": {"type": "xsrf", "hint": "", "show_hint": False},
            "mode": "fetch",
            "url": "https://ad.rms.rakuten.co.jp/cpnadv/performance_reports/retrieve",
            "method": "POST",
            "headers": {},
            "vars": {"start_date": {"type": "str", "required": True, "description": ""}, "end_date": {"type": "str", "required": True, "description": ""}},
        },
        "tda-reports-search-item": {
            "name": "乐天·TDA 报表检索（商品维度）",
            "auth": {"type": "xsrf", "hint": "", "show_hint": False},
            "mode": "fetch",
            "url": "https://ad.rms.rakuten.co.jp/tda/api/aggregator/v2/reports/search",
            "method": "GET",
            "headers": {},
            "vars": {"start_date": {"type": "str", "required": True, "description": ""}, "end_date": {"type": "str", "required": True, "description": ""}},
        },
        "rpp-exp-report-item": {
            "name": "乐天·RPP 专家版报表（商品维度）",
            "auth": {"type": "xsrf", "hint": "", "show_hint": False},
            "mode": "fetch",
            "url": "https://ad.rms.rakuten.co.jp/rppexp/api/core/report",
            "method": "POST",
            "headers": {},
            "vars": {"start_date": {"type": "str", "required": True, "description": ""}, "end_date": {"type": "str", "required": True, "description": ""}},
        },
        "tda-exp-report-item": {
            "name": "乐天·TDA 专家版报表（商品维度）",
            "auth": {"type": "xsrf", "hint": "", "show_hint": False},
            "mode": "fetch",
            "url": "https://ad.rms.rakuten.co.jp/tdaexp/api/tdaexp-core/report",
            "method": "POST",
            "headers": {},
            "vars": {"start_date": {"type": "str", "required": True, "description": ""}, "end_date": {"type": "str", "required": True, "description": ""}},
        },
        "reviews-csv": {
            "name": "乐天·RMS 评论 CSV",
            "description": "review.rms.rakuten.co.jp 评论一览 CSV",
            "auth": {"type": "cookie", "hint": "需在当前标签页登录 RMS", "show_hint": False},
            "navigate_url": "https://review.rms.rakuten.co.jp/search/",
            "rakuten_review_csv": True,
            "output_decode_encoding": "cp932",
            "mode": "fetch",
            "url": "",
            "method": "GET",
            "headers": {"Accept": "*/*", "Accept-Language": "ja"},
            "vars": {
                "last_days": {"type": "int", "default": "30", "description": "往前多少天"},
                "start_date": {"description": "可选。开始日 YYYY-MM-DD"},
                "end_date": {"description": "可选。结束日 YYYY-MM-DD"},
                "kw": {"default": "", "description": "关键词"},
                "ao": {"default": "A", "description": "排序"},
                "st": {"type": "int", "default": "1", "description": "st 参数"},
                "tc": {"type": "int", "default": "0", "description": "tc 参数"},
                "ev": {"type": "int", "default": "0", "description": "ev 参数"},
                "sh": {"type": "int", "default": "0", "description": "开始时刻·时"},
                "si": {"type": "int", "default": "0", "description": "开始时刻·分"},
                "eh": {"type": "int", "default": "23", "description": "结束时刻·时"},
                "ei": {"type": "int", "default": "59", "description": "结束时刻·分"},
            },
        },
    }


_RAKUTEN_PLUGIN_PY = (
    '"""Rakuten site plugin (loaded from test repo)."""\n'
    "from __future__ import annotations\n"
    "import json\n"
    "from datetime import datetime, timedelta\n"
    "from urllib.parse import quote\n"
    "from zoneinfo import ZoneInfo\n"
    "from ziniao_mcp.sites._base import SitePlugin\n"
    "_JST = ZoneInfo('Asia/Tokyo')\n"
    "def _int_from_vars(merged, key, default):\n"
    "    if key not in merged:\n"
    "        return default\n"
    "    raw = merged.get(key, '')\n"
    "    if raw is None or str(raw).strip() == '':\n"
    "        return default\n"
    "    return int(str(raw).strip(), 10)\n"
    "class RakutenPlugin(SitePlugin):\n"
    "    site_id = 'rakuten'\n"
    "    def before_fetch(self, request, *, tab=None, store=None):\n"
    "        if not request.pop('rakuten_review_csv', False):\n"
    "            return request\n"
    "        merged = request.pop('_ziniao_merged_vars', None)\n"
    "        if not isinstance(merged, dict):\n"
    "            merged = {}\n"
    "        start_s = str(merged.get('start_date', '')).strip()\n"
    "        end_s = str(merged.get('end_date', '')).strip()\n"
    "        if start_s and end_s:\n"
    "            ds = datetime.strptime(start_s, '%Y-%m-%d')\n"
    "            de = datetime.strptime(end_s, '%Y-%m-%d')\n"
    "            if ds.date() > de.date():\n"
    "                raise ValueError('start_date must be on or before end_date')\n"
    "        elif start_s or end_s:\n"
    "            raise ValueError('start_date and end_date must be used together, or omit both and use last_days')\n"
    "        else:\n"
    "            raw_ld = str(merged.get('last_days', '30')).strip() or '30'\n"
    "            n = int(raw_ld, 10)\n"
    "            if n < 1:\n"
    "                raise ValueError('last_days must be >= 1')\n"
    "            end_d = datetime.now(_JST).date()\n"
    "            start_d = end_d - timedelta(days=n - 1)\n"
    "            ds = datetime(start_d.year, start_d.month, start_d.day)\n"
    "            de = datetime(end_d.year, end_d.month, end_d.day)\n"
    "        sy, sm, sd = ds.year, ds.month, ds.day\n"
    "        ey, em, ed = de.year, de.month, de.day\n"
    "        sh = _int_from_vars(merged, 'sh', 0)\n"
    "        si = _int_from_vars(merged, 'si', 0)\n"
    "        eh = _int_from_vars(merged, 'eh', 23)\n"
    "        ei = _int_from_vars(merged, 'ei', 59)\n"
    "        ev = _int_from_vars(merged, 'ev', 0)\n"
    "        tc = _int_from_vars(merged, 'tc', 0)\n"
    "        st = _int_from_vars(merged, 'st', 1)\n"
    "        ao = str(merged.get('ao', 'A') or 'A').strip() or 'A'\n"
    "        kw = str(merged.get('kw', '') or '')\n"
    "        request['url'] = (\n"
    "            'https://review.rms.rakuten.co.jp/search/csv/'\n"
    "            f'?sy={sy}&sm={sm}&sd={sd}&sh={sh}&si={si}'\n"
    "            f'&ey={ey}&em={em}&ed={ed}&eh={eh}&ei={ei}'\n"
    "            f'&ev={ev}&tc={tc}&kw={quote(kw, safe=\"\")}&ao={quote(ao, safe=\"\")}&st={st}'\n"
    "        )\n"
    "        return request\n"
    "    def after_fetch(self, response, request):\n"
    "        body_text = response.get('body', '')\n"
    "        if not body_text:\n"
    "            return response\n"
    "        try:\n"
    "            data = json.loads(body_text)\n"
    "        except (json.JSONDecodeError, TypeError):\n"
    "            return response\n"
    "        if data.get('status') == 'SUCCESS' and 'data' in data:\n"
    "            response['parsed'] = data['data']\n"
    "        return response\n"
    "SITE_PLUGIN = RakutenPlugin\n"
)


@pytest.fixture()
def rakuten_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Populate a fake repo with rakuten presets + plugin and redirect REPOS_DIR."""
    import ziniao_mcp.sites.repo as repo_mod

    repos_dir = tmp_path / "repos"
    rakuten_dir = repos_dir / "test-official" / "rakuten"
    rakuten_dir.mkdir(parents=True, exist_ok=True)

    for stem, data in _rakuten_json_files().items():
        (rakuten_dir / f"{stem}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    (rakuten_dir / "__init__.py").write_text(_RAKUTEN_PLUGIN_PY, encoding="utf-8")

    monkeypatch.setattr(repo_mod, "REPOS_DIR", repos_dir)
    monkeypatch.setattr(repo_mod, "REPOS_JSON", repos_dir / "repos.json")
    return repos_dir
