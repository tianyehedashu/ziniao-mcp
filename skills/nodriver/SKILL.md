---
name: nodriver
description: Automate browsers using nodriver (async CDP library, successor of undetected-chromedriver). Supports launching, connecting to existing browsers, element finding, clicking, typing, screenshots, cookie management, CDP low-level commands, and event handling. Use when asked to automate a browser, scrape pages, interact with web elements, use CDP protocol, or write nodriver/browser automation code.
allowed-tools: Bash(python:*), Bash(pip:*)
---

# nodriver — Browser Automation

nodriver is an async browser automation library that communicates directly via CDP (Chrome DevTools Protocol) without chromedriver or Selenium. It is the official successor of [undetected-chromedriver](https://github.com/ultrafunkamsterdam/nodriver).

**Requires**: Python 3.10+, Chrome/Chromium installed.

```bash
pip install nodriver
```

## Quick Start

```python
import nodriver as uc

async def main():
    browser = await uc.start()
    tab = await browser.get("https://example.com")

    elem = await tab.select("h1")
    print(elem.text)

    await tab.save_screenshot("page.jpg")
    browser.stop()

uc.loop().run_until_complete(main())
```

## Core Concepts

nodriver has 4 key objects:

| Object | Role |
|--------|------|
| `Browser` | Root process. Created via `await uc.start()` or `await Browser.create()` |
| `Tab` | A browser tab. Navigate, find elements, execute JS, take screenshots |
| `Element` | A DOM node. Click, type, get position, read attributes |
| `Config` | Startup configuration (headless, args, profile, etc.) |

## Launching a Browser

```python
import nodriver as uc

# Simple
browser = await uc.start()

# With options
browser = await uc.start(
    headless=False,
    user_data_dir="/path/to/profile",
    browser_executable_path="/path/to/chrome",
    browser_args=["--window-size=1920,1080"],
    lang="en-US",
)

# Using Config object
config = uc.Config()
config.headless = True
config.add_argument("--proxy-server=http://proxy:8080")
config.add_extension("/path/to/extension")
browser = await uc.Browser.create(config=config)
```

## Connecting to an Existing Browser

```python
browser = await uc.Browser.create(host="127.0.0.1", port=9222)
tab = browser.tabs[0]
```

## Navigation

```python
tab = await browser.get("https://example.com")
tab2 = await browser.get("https://other.com", new_tab=True)
tab3 = await browser.get("https://third.com", new_window=True)

await tab.back()
await tab.forward()
await tab.reload()
await tab.close()

html = await tab.get_content()
```

## Finding Elements

| Method | Finds by | Returns |
|--------|----------|---------|
| `tab.select(css)` | CSS selector | single Element |
| `tab.select_all(css)` | CSS selector | list of Elements |
| `tab.find(text)` | visible text (best match) | single Element |
| `tab.find_all(text)` | visible text | list of Elements |
| `tab.xpath(expr)` | XPath | list of Elements |
| `tab.wait_for(selector=, text=)` | CSS or text | Element (with timeout) |

All methods accept a `timeout` parameter (default 10s) and retry until found.

```python
btn = await tab.select("button.submit")
btn = await tab.find("Accept All", best_match=True)
links = await tab.select_all("a[href]")
items = await tab.find_all("product")
nodes = await tab.xpath("//div[@class='item']")
loaded = await tab.wait_for(selector="body", timeout=15)
```

`tab(selector=, text=, timeout=)` is a shorthand for `wait_for`:

```python
elem = await tab("button.next")
```

## Interacting with Elements

```python
await elem.click()
await elem.send_keys("hello world")
await elem.clear_input()
await elem.send_file("/path/to/file.pdf")
await elem.focus()
await elem.scroll_into_view()
await elem.mouse_move()
await elem.mouse_click()
await elem.mouse_drag(dest_element)
```

**Element properties**:

```python
elem.text              # text content
elem.text_all          # all text including children
elem.attrs             # HTML attributes dict
elem.parent            # parent Element
elem.children          # child Elements
html = await elem.get_html()
pos = await elem.get_position()  # Position(left, top, width, height, center)
```

**Execute JS on element**:

```python
result = await elem.apply("function(el) { return el.value; }")
await elem("scrollIntoView")  # call JS method
```

## JavaScript Execution

```python
result = await tab.evaluate("document.title")
result = await tab.evaluate("1 + 1", return_by_value=True)
obj = await tab.js_dumps("navigator")
```

## Screenshots

```python
await tab.save_screenshot("page.jpg")
await tab.save_screenshot("full.png", full_page=True)
await elem.save_screenshot("element.png")
```

## Mouse & Keyboard (low-level)

```python
await tab.mouse_move(x=100, y=200, steps=10)
await tab.mouse_click(x=100, y=200)
await tab.mouse_drag((100, 200), (300, 400))
await tab.scroll_down(amount=150)
await tab.scroll_up(amount=150)
```

## Cookies

```python
all_cookies = await browser.cookies.get_all()
await browser.cookies.set_all([...])
await browser.cookies.save(".cookies.dat")
await browser.cookies.load(".cookies.dat")
await browser.cookies.clear()
```

## Event Handling

Register handlers for CDP events:

```python
from nodriver import cdp

async def on_request(event: cdp.network.RequestWillBeSent):
    print(event.request.url)

async def on_console(event: cdp.console.MessageAdded):
    print(event.message.text)

async def on_dialog(event: cdp.page.JavascriptDialogOpening):
    await tab.send(cdp.page.handle_javascript_dialog(accept=True))

tab.add_handler(cdp.network.RequestWillBeSent, on_request)
tab.add_handler(cdp.console.MessageAdded, on_console)
tab.add_handler(cdp.page.JavascriptDialogOpening, on_dialog)

# handler can also accept (event, tab) signature:
async def on_response(event, tab):
    print(f"[{tab.target.url}] {event.response.url}")

tab.add_handler(cdp.network.ResponseReceived, on_response)
tab.remove_handler(cdp.network.RequestWillBeSent, on_request)
```

## CDP Direct Commands

Use `tab.send()` to issue any CDP command:

```python
from nodriver import cdp

# Override User-Agent
await tab.send(cdp.network.set_user_agent_override(user_agent="Custom UA"))

# Emulate device metrics
await tab.send(cdp.emulation.set_device_metrics_override(
    width=375, height=812, device_scale_factor=3, mobile=True
))

# Inject script before page load
await tab.send(cdp.page.add_script_to_evaluate_on_new_document(
    source="window.__injected = true;"
))

# Dispatch mouse event
await tab.send(cdp.input_.dispatch_mouse_event(
    "mousePressed", x=100, y=200, button="left", click_count=1
))

# Dispatch key event
await tab.send(cdp.input_.dispatch_key_event("char", text="A"))

# Network interception
await tab.send(cdp.network.enable())
await tab.send(cdp.fetch.enable(patterns=[
    cdp.fetch.RequestPattern(url_pattern="*", request_stage="Request")
]))
```

Common CDP domains: `cdp.input_`, `cdp.network`, `cdp.page`, `cdp.runtime`, `cdp.emulation`, `cdp.dom`, `cdp.storage`, `cdp.overlay`, `cdp.console`, `cdp.target`, `cdp.fetch`.

## Window Management

```python
await tab.maximize()
await tab.minimize()
await tab.fullscreen()
await tab.set_window_size(left=0, top=0, width=1920, height=1080)
await tab.set_download_path("/downloads")
```

## Tab Access

```python
browser.tabs             # all tabs
browser.main_tab         # first tab
browser[0]               # by index
browser["google"]        # by title/url substring
```

## LocalStorage

```python
data = await tab.get_local_storage()
await tab.set_local_storage({"key": "value"})
```

## Async Pattern

nodriver is fully async. Use `uc.loop()` or `asyncio`:

```python
import nodriver as uc

async def main():
    browser = await uc.start()
    # ...
    browser.stop()

# Option 1: nodriver's loop helper
uc.loop().run_until_complete(main())

# Option 2: standard asyncio
import asyncio
asyncio.run(main())
```

`await tab` or `await tab.sleep(seconds)` lets the event loop process pending events.

## Anti-Detection Notes

nodriver inherently avoids detection because:
- No chromedriver binary (no `$cdc_` variables in DOM)
- No WebDriver protocol (no `navigator.webdriver = true` by spec)
- No Selenium/Playwright global variables injected
- Clean startup args (no `--enable-automation`)
- Direct CDP communication over WebSocket

For additional stealth (fingerprint spoofing, behavior simulation), layer your own JS patches via `cdp.page.add_script_to_evaluate_on_new_document`.

## Additional Resources

- For detailed API signatures, see [references/api-reference.md](references/api-reference.md)
- For complete usage examples, see [references/examples.md](references/examples.md)
- Official docs: https://ultrafunkamsterdam.github.io/nodriver
- GitHub: https://github.com/ultrafunkamsterdam/nodriver
