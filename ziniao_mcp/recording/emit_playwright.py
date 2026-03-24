"""Generate Playwright-style TypeScript snippets from recording actions (string template)."""

from __future__ import annotations

import json
from typing import Any

from .locator import normalize_action_for_replay


def _pw_locator_from_action(act: dict[str, Any]) -> str:
    act = normalize_action_for_replay(act)
    loc = act.get("locator")
    if isinstance(loc, dict):
        strat = (loc.get("strategy") or "").lower()
        if strat == "testid":
            return f"page.getByTestId({json.dumps(str(loc.get('value', '')))})"
        if strat == "role":
            role = str(loc.get("role", "button"))
            name = str(loc.get("name", ""))
            if name:
                return f"page.getByRole({json.dumps(role)}, {{ name: {json.dumps(name)} }})"
            return f"page.getByRole({json.dumps(role)})"
        if strat == "text":
            return f"page.getByText({json.dumps(str(loc.get('text', '')))})"
        if strat == "aria":
            return f"page.getByLabel({json.dumps(str(loc.get('value', '')))})"
    sel = act.get("selector") or "body"
    return f"page.locator({json.dumps(sel)})"


def generate_playwright_typescript(
    actions: list[dict[str, Any]],
    start_url: str,
    name: str = "",
) -> str:
    """Emit a .spec.ts-style script using connectOverCDP (user fills port/context)."""
    title = name or "recording"
    lines: list[str] = [
        "/**",
        f" * Auto-generated Playwright-style replay — {title}",
        " * Requires: npm i -D @playwright/test playwright",
        " * Fill in chromium.connectOverCDP / CDP endpoint before running.",
        " */",
        "",
        "import { test, expect } from '@playwright/test';",
        "",
        "test('ziniao recording replay', async () => {",
        "  // const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');",
        "  // const context = browser.contexts()[0];",
        "  // const page = context.pages()[0] ?? await context.newPage();",
        "  const page = null as any; // TODO: obtain page from your CDP session",
        "",
    ]
    if start_url:
        lines.append(f"  await page.goto({json.dumps(start_url)});")
        lines.append("  await page.waitForLoadState('domcontentloaded');")
        lines.append("")

    step = 0
    for act in actions:
        act = normalize_action_for_replay(act)
        step += 1
        t = act.get("type", "")
        dm = int(act.get("delay_ms", 0) or 0)
        if dm > 100 and step > 1:
            lines.append(f"  await page.waitForTimeout({min(dm, 60_000)});")

        loc_expr = _pw_locator_from_action(act)

        if t == "click":
            lines.append(f"  // step {step}: click")
            lines.append(f"  await {loc_expr}.click();")
        elif t == "fill":
            val = json.dumps(str(act.get("value", "")))
            lines.append(f"  // step {step}: fill")
            lines.append(f"  await {loc_expr}.fill({val});")
        elif t == "select":
            val = json.dumps(str(act.get("value", "")))
            lines.append(f"  // step {step}: selectOption")
            lines.append(f"  await {loc_expr}.selectOption({val});")
        elif t == "press_key":
            key = json.dumps(str(act.get("key", "Enter")))
            lines.append(f"  await page.keyboard.press({key});")
        elif t == "navigate":
            url = json.dumps(str(act.get("url", "")))
            lines.append(f"  await page.goto({url});")
        else:
            lines.append(f"  // step {step}: unsupported {t}")

        lines.append("")

    lines.append("});")
    lines.append("")
    return "\n".join(lines)
