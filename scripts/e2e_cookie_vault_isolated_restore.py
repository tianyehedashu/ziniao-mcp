#!/usr/bin/env python3
"""E2E：从已登录 Chrome 会话导出 AuthSnapshot → 全新 user-data-dir 启动 Chrome → restore → 截图。

复现「干净 profile + cookie-vault 快照恢复登录态」的手动测试流程（与对话中实际操作一致）。

前置条件
----------
- 项目根目录执行；已 ``uv sync``。
- ziniao daemon 可用；**源会话**（``--source-session``）里已在 ``--export-url`` 对应站点完成登录。

示例::

    uv run python scripts/e2e_cookie_vault_isolated_restore.py --source-session chrome-51157

已有快照、只跑「干净 Chrome + restore」::

    uv run python scripts/e2e_cookie_vault_isolated_restore.py \\
        --source-session chrome-51157 \\
        --skip-export \\
        --snapshot exports/my_snap.json

说明：``exports/`` 已在 ``.gitignore`` 中忽略；快照含 Cookie / storage，勿提交仓库。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _ziniao(
    argv: list[str],
    *,
    session: str | None = None,
    check: bool = True,
) -> dict:
    """Invoke ``python -m ziniao_mcp.cli --json …`` and parse the JSON envelope."""
    cmd: list[str] = [sys.executable, "-m", "ziniao_mcp.cli", "--json"]
    if session:
        cmd += ["--session", session]
    cmd += argv
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    raw = (proc.stdout or "").strip()
    if not raw:
        msg = proc.stderr.strip() or f"empty stdout (exit {proc.returncode})"
        if check:
            raise RuntimeError(msg)
        return {"success": False, "data": None, "error": msg}
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        tail = raw[:2000] + ("…" if len(raw) > 2000 else "")
        if check:
            raise RuntimeError(f"invalid JSON from ziniao: {exc}\n{tail}") from exc
        return {"success": False, "data": None, "error": tail}
    if check and not envelope.get("success"):
        raise RuntimeError(envelope.get("error") or str(envelope))
    return envelope


def _parse_launch_session(envelope: dict) -> str:
    data = envelope.get("data") or {}
    sid = data.get("session_id") or data.get("name")
    if not sid:
        raise RuntimeError(f"launch response missing session_id: {envelope}")
    return str(sid)


def main() -> int:
    # argparse 在部分 Windows 终端下用系统代码页打印 description，中文易乱码；详细说明见本文件顶部 docstring。
    p = argparse.ArgumentParser(
        description=(
            "E2E: export AuthSnapshot from a logged-in Chrome session, launch Chrome with a fresh "
            "--user-data-dir, cookie-vault restore, screenshot. Chinese details in the module docstring."
        ),
    )
    p.add_argument(
        "--source-session",
        required=True,
        help="已登录的 Chrome 会话 id（例如 chrome-51157）。用于 export 阶段。",
    )
    p.add_argument(
        "--snapshot",
        type=Path,
        default=ROOT / "exports" / "e2e_cookie_vault_isolated_snap.json",
        help="AuthSnapshot 写出路径（默认 exports/e2e_cookie_vault_isolated_snap.json）。",
    )
    p.add_argument(
        "--export-url",
        default="https://creator.douyin.com/",
        help="导出前导航的 URL（默认抖音创作者中心）。",
    )
    p.add_argument(
        "--restore-url",
        default="https://creator.douyin.com/",
        help="restore 时 --url 参数（默认抖音创作者中心）。",
    )
    p.add_argument(
        "--site-label",
        default="e2e-cookie-vault-isolated",
        help="cookie-vault export --site 标签。",
    )
    p.add_argument(
        "--clean-profile-parent",
        type=Path,
        default=Path.home() / ".ziniao" / "chrome-profiles",
        help="隔离 Chrome profile 根目录（默认 ~/.ziniao/chrome-profiles）。",
    )
    p.add_argument(
        "--clean-session-name",
        default="",
        help="launch --name；默认自动生成 e2e-cv-<时间戳>。",
    )
    p.add_argument(
        "--initial-tab-url",
        default="https://www.example.com/",
        help="干净 Chrome 启动后首 tab URL（默认 example.com）。",
    )
    p.add_argument(
        "--screenshot",
        type=Path,
        default=ROOT / "exports" / "e2e_cookie_vault_isolated_after_restore.png",
        help="restore 后截图路径。",
    )
    p.add_argument(
        "--skip-export",
        action="store_true",
        help="跳过 export（使用已有 --snapshot 文件）。",
    )
    args = p.parse_args()

    snap: Path = args.snapshot.resolve()
    shot: Path = args.screenshot.resolve()
    snap.parent.mkdir(parents=True, exist_ok=True)
    shot.parent.mkdir(parents=True, exist_ok=True)

    if not args.skip_export:
        print(f"[export] navigate export-url on source session {args.source_session!r} …", flush=True)
        _ziniao(["navigate", str(args.export_url)], session=args.source_session)
        _ziniao(["wait", "body", "--timeout", "25000"], session=args.source_session)
        print(f"[export] cookie-vault export → {snap} …", flush=True)
        exp = _ziniao(
            ["cookie-vault", "export", "-o", str(snap), "--site", str(args.site_label)],
            session=args.source_session,
        )
        data = exp.get("data") or {}
        print(
            f"      exported cookie_count={data.get('cookie_count')} redacted={data.get('redacted')}",
            flush=True,
        )
    else:
        if not snap.is_file():
            print(f"error: --skip-export but snapshot missing: {snap}", file=sys.stderr)
            return 2
        print(f"[export] skip-export; using snapshot {snap}", flush=True)

    clean_name = (args.clean_session_name or "").strip() or f"e2e-cv-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    profile_dir = (args.clean_profile_parent / clean_name).resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)

    print(f"[launch] isolated Chrome name={clean_name!r} profile={profile_dir} …", flush=True)
    launch = _ziniao(
        [
            "chrome",
            "launch",
            "--name",
            clean_name,
            "--user-data-dir",
            str(profile_dir),
            "--url",
            str(args.initial_tab_url),
        ],
    )
    new_sid = _parse_launch_session(launch)
    print(f"      new session_id={new_sid!r}", flush=True)

    print(f"[restore] cookie-vault restore on {new_sid!r} …", flush=True)
    rest = _ziniao(
        [
            "cookie-vault",
            "restore",
            str(snap),
            "--url",
            str(args.restore_url),
        ],
        session=new_sid,
    )
    rdata = rest.get("data")
    if isinstance(rdata, dict):
        print(
            "      "
            f"restored={rdata.get('restored')} imported_cookies={rdata.get('imported_cookies')} "
            f"local_storage_keys={rdata.get('imported_local_storage_keys')} "
            f"session_storage_keys={rdata.get('imported_session_storage_keys')}",
            flush=True,
        )

    _ziniao(["wait", "body", "--timeout", "25000"], session=new_sid)
    print(f"[screenshot] → {shot} …", flush=True)
    _ziniao(["screenshot", str(shot)], session=new_sid)
    url_env = _ziniao(["url"], session=new_sid, check=False)
    if url_env.get("success"):
        udata = url_env.get("data")
        final = udata.get("url") if isinstance(udata, dict) else udata
        print(f"      final url: {final}", flush=True)
    else:
        print(f"      url (json): {url_env.get('error')}", flush=True)

    print("Done. Inspect screenshot; cookie snapshot is sensitive — do not commit exports/.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
