#!/usr/bin/env python3
"""测试 ziniao 全部 CLI：执行各命令的 --help 或最小参数，记录结果并输出报告。

不依赖 daemon 的测试：仅执行 --help，验证命令可解析。
可选：若检测到 daemon，则对部分命令执行真实调用（需环境有会话）。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent
CLI = [sys.executable, "-m", "ziniao_mcp.cli"]


def run(args: list[str], timeout: float = 10.0) -> tuple[int, str, str]:
    """运行 ziniao 命令，返回 (returncode, stdout, stderr)。"""
    cmd = CLI + args
    try:
        r = subprocess.run(
            cmd,
            cwd=ROOT,
            capture_output=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return (r.returncode, r.stdout or "", r.stderr or "")
    except subprocess.TimeoutExpired:
        return (-1, "", "timeout")
    except Exception as e:
        return (-2, "", str(e))


def main() -> None:
    # 所有要测试的 CLI 调用：(描述, 参数列表, 期望退出码 0 表示必须成功)
    # 仅 --help 测试：不连 daemon，只验证解析
    tests = [
        ("主帮助", ["--help"], 0),
        ("serve --help", ["serve", "--help"], 0),
        ("store list --help", ["store", "list", "--help"], 0),
        ("store open --help", ["store", "open", "--help"], 0),
        ("store close --help", ["store", "close", "--help"], 0),
        ("store start-client --help", ["store", "start-client", "--help"], 0),
        ("store stop-client --help", ["store", "stop-client", "--help"], 0),
        ("chrome list --help", ["chrome", "list", "--help"], 0),
        ("chrome launch --help", ["chrome", "launch", "--help"], 0),
        ("chrome connect --help", ["chrome", "connect", "--help"], 0),
        ("chrome close --help", ["chrome", "close", "--help"], 0),
        ("session list --help", ["session", "list", "--help"], 0),
        ("session switch --help", ["session", "switch", "--help"], 0),
        ("session info --help", ["session", "info", "--help"], 0),
        ("nav go --help", ["nav", "go", "--help"], 0),
        ("nav navigate --help", ["nav", "navigate", "--help"], 0),
        ("nav tab --help", ["nav", "tab", "--help"], 0),
        ("nav frame --help", ["nav", "frame", "--help"], 0),
        ("nav wait --help", ["nav", "wait", "--help"], 0),
        ("nav back --help", ["nav", "back", "--help"], 0),
        ("nav forward --help", ["nav", "forward", "--help"], 0),
        ("nav reload --help", ["nav", "reload", "--help"], 0),
        ("act click --help", ["act", "click", "--help"], 0),
        ("act fill --help", ["act", "fill", "--help"], 0),
        ("act type --help", ["act", "type", "--help"], 0),
        ("act press --help", ["act", "press", "--help"], 0),
        ("act hover --help", ["act", "hover", "--help"], 0),
        ("act dblclick --help", ["act", "dblclick", "--help"], 0),
        ("info snapshot --help", ["info", "snapshot", "--help"], 0),
        ("info screenshot --help", ["info", "screenshot", "--help"], 0),
        ("info eval --help", ["info", "eval", "--help"], 0),
        ("info console --help", ["info", "console", "--help"], 0),
        ("info network --help", ["info", "network", "--help"], 0),
        ("info errors --help", ["info", "errors", "--help"], 0),
        ("info highlight --help", ["info", "highlight", "--help"], 0),
        ("info cookies --help", ["info", "cookies", "--help"], 0),
        ("info storage --help", ["info", "storage", "--help"], 0),
        ("info url --help", ["info", "url", "--help"], 0),
        ("info clipboard --help", ["info", "clipboard", "--help"], 0),
        ("rec start --help", ["rec", "start", "--help"], 0),
        ("rec stop --help", ["rec", "stop", "--help"], 0),
        ("rec replay --help", ["rec", "replay", "--help"], 0),
        ("rec list --help", ["rec", "list", "--help"], 0),
        ("rec delete --help", ["rec", "delete", "--help"], 0),
        ("sys quit --help", ["sys", "quit", "--help"], 0),
        ("sys emulate --help", ["sys", "emulate", "--help"], 0),
        ("get text --help", ["get", "text", "--help"], 0),
        ("get html --help", ["get", "html", "--help"], 0),
        ("get value --help", ["get", "value", "--help"], 0),
        ("get attr --help", ["get", "attr", "--help"], 0),
        ("get title --help", ["get", "title", "--help"], 0),
        ("get url --help", ["get", "url", "--help"], 0),
        ("get count --help", ["get", "count", "--help"], 0),
        ("find first --help", ["find", "first", "--help"], 0),
        ("find last --help", ["find", "last", "--help"], 0),
        ("find nth --help", ["find", "nth", "--help"], 0),
        ("find text --help", ["find", "text", "--help"], 0),
        ("find role --help", ["find", "role", "--help"], 0),
        ("is visible --help", ["is", "visible", "--help"], 0),
        ("is enabled --help", ["is", "enabled", "--help"], 0),
        ("is checked --help", ["is", "checked", "--help"], 0),
        ("scroll up --help", ["scroll", "up", "--help"], 0),
        ("scroll down --help", ["scroll", "down", "--help"], 0),
        ("scroll left --help", ["scroll", "left", "--help"], 0),
        ("scroll right --help", ["scroll", "right", "--help"], 0),
        ("scroll into --help", ["scroll", "into", "--help"], 0),
        ("batch run --help", ["batch", "run", "--help"], 0),
        ("mouse move --help", ["mouse", "move", "--help"], 0),
        ("mouse down --help", ["mouse", "down", "--help"], 0),
        ("mouse up --help", ["mouse", "up", "--help"], 0),
        ("mouse wheel --help", ["mouse", "wheel", "--help"], 0),
        ("network route --help", ["network", "route", "--help"], 0),
        ("network unroute --help", ["network", "unroute", "--help"], 0),
        ("network routes --help", ["network", "routes", "--help"], 0),
        ("network list --help", ["network", "list", "--help"], 0),
        ("network har-start --help", ["network", "har-start", "--help"], 0),
        ("network har-stop --help", ["network", "har-stop", "--help"], 0),
        # 顶层快捷命令 --help（部分无 --help 会直接连 daemon，这里只测有 help 的）
        ("list-stores --help", ["list-stores", "--help"], 0),
        ("chrome launch --help (top-level)", ["launch", "--help"], 0),
        ("navigate --help", ["navigate", "--help"], 0),
        ("tab --help", ["tab", "--help"], 0),
        ("wait --help", ["wait", "--help"], 0),
        ("back --help", ["back", "--help"], 0),
        ("forward --help", ["forward", "--help"], 0),
        ("reload --help", ["reload", "--help"], 0),
        ("click --help", ["click", "--help"], 0),
        ("eval --help", ["eval", "--help"], 0),
        ("title --help", ["title", "--help"], 0),
        ("url --help", ["url", "--help"], 0),
        ("scrollinto --help", ["scrollinto", "--help"], 0),
    ]

    passed = []
    failed = []
    for desc, args, expect in tests:
        code, out, err = run(args)
        if code == expect:
            passed.append((desc, args, code))
        else:
            failed.append((desc, args, code, err.strip() or out.strip()[:200]))

    # 输出到 stdout
    print("=" * 60)
    print("ziniao CLI 全量测试（仅 --help / 主帮助）")
    print("=" * 60)
    print(f"通过: {len(passed)}")
    for d, a, c in passed:
        print(f"  OK  {d}")
    print(f"\n失败: {len(failed)}")
    for d, a, c, msg in failed:
        print(f"  FAIL {d}")
        print(f"        args={a} -> exit={c}")
        if msg:
            print(f"        {msg[:150]}")
    print("=" * 60)

    # 写报告到 CLI_TEST_REPORT.md（仅追加本次结果摘要，不覆盖原有内容）
    report_path = ROOT / "CLI_TEST_REPORT.md"
    with open(report_path, "r", encoding="utf-8") as f:
        existing = f.read()

    # 若报告中有“全量测试结果”段则替换，否则在末尾追加
    marker = "## 全量 --help 测试结果"
    if marker in existing:
        before, _, after = existing.partition(marker)
        rest = after.split("\n")
        end = 0
        for i, line in enumerate(rest):
            if line.startswith("## ") and i > 0:
                end = i
                break
        if end:
            existing = before + marker + "\n\n" + "\n".join(rest[end:])
        else:
            existing = before + marker + "\n\n"
    else:
        existing = existing.rstrip() + "\n\n" + marker + "\n\n"

    lines = [
        f"- 通过: {len(passed)}",
        f"- 失败: {len(failed)}",
        "",
        "### 通过列表",
        "| 命令 |",
        "|------|",
    ]
    for d, _, _ in passed:
        lines.append(f"| `{d}` |")
    lines.extend(["", "### 失败列表", "| 命令 | 退出码 | 说明 |", "|------|--------|------|"])
    for d, _, c, msg in failed:
        lines.append(f"| `{d}` | {c} | {msg[:80] if msg else '-'} |")

    new_section = "\n".join(lines)
    if marker in existing and "通过:" in existing:
        # 替换已有段落内容
        idx = existing.index(marker)
        next_h2 = existing.find("\n## ", idx + 1)
        if next_h2 == -1:
            existing = existing[: idx + len(marker)] + "\n\n" + new_section + "\n"
        else:
            existing = existing[: idx + len(marker)] + "\n\n" + new_section + "\n" + existing[next_h2:]
    else:
        existing = existing + new_section + "\n"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(existing)

    print(f"\n已更新 {report_path}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
