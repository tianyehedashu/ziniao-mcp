# nodriver Examples

## 1. Basic Page Scraping

```python
import nodriver as uc

async def main():
    browser = await uc.start()
    tab = await browser.get("https://quotes.toscrape.com/")

    quotes = await tab.select_all(".quote .text")
    for q in quotes:
        print(q.text)

    browser.stop()

uc.loop().run_until_complete(main())
```

## 2. Form Filling

```python
import nodriver as uc

async def main():
    browser = await uc.start()
    tab = await browser.get("https://example.com/login")

    email = await tab.select("input[type=email]")
    await email.send_keys("user@example.com")

    password = await tab.select("input[type=password]")
    await password.send_keys("secret123")

    submit = await tab.find("Log in", best_match=True)
    await submit.click()

    await tab.sleep(2)
    browser.stop()

uc.loop().run_until_complete(main())
```

## 3. Connect to Existing Browser

```python
import nodriver as uc

async def main():
    browser = await uc.Browser.create(host="127.0.0.1", port=9222)

    tab = browser.tabs[0]
    print(f"Connected to: {tab.target.url}")

    title = await tab.evaluate("document.title")
    print(f"Title: {title}")

uc.loop().run_until_complete(main())
```

## 4. Multi-Tab

```python
import nodriver as uc

async def main():
    browser = await uc.start()

    tab1 = await browser.get("https://example.com")
    tab2 = await browser.get("https://github.com", new_tab=True)
    tab3 = await browser.get("https://news.ycombinator.com", new_window=True)

    for tab in browser.tabs:
        content = await tab.get_content()
        print(f"{tab.target.url}: {len(content)} chars")

    await tab2.close()
    browser.stop()

uc.loop().run_until_complete(main())
```

## 5. Cookie Persistence

```python
import nodriver as uc

async def main():
    browser = await uc.start()
    tab = await browser.get("https://example.com/login")

    # ... login steps ...

    await browser.cookies.save("session.dat")
    browser.stop()

async def resume():
    browser = await uc.start()
    await browser.cookies.load("session.dat")
    tab = await browser.get("https://example.com/dashboard")
    print(await tab.evaluate("document.title"))
    browser.stop()

uc.loop().run_until_complete(main())
```

## 6. Network Monitoring

```python
import nodriver as uc
from nodriver import cdp

async def main():
    browser = await uc.start()
    tab = await browser.get("about:blank")

    requests = []

    async def on_request(event: cdp.network.RequestWillBeSent):
        requests.append(event.request.url)

    async def on_response(event: cdp.network.ResponseReceived):
        if event.response.status >= 400:
            print(f"Error {event.response.status}: {event.response.url}")

    tab.add_handler(cdp.network.RequestWillBeSent, on_request)
    tab.add_handler(cdp.network.ResponseReceived, on_response)

    await tab.get("https://example.com")
    await tab.sleep(3)

    print(f"Total requests: {len(requests)}")
    browser.stop()

uc.loop().run_until_complete(main())
```

## 7. Dialog Handling

```python
import nodriver as uc
from nodriver import cdp

async def main():
    browser = await uc.start()
    tab = await browser.get("https://example.com")

    async def on_dialog(event: cdp.page.JavascriptDialogOpening):
        print(f"Dialog: {event.message}")
        await tab.send(cdp.page.handle_javascript_dialog(accept=True))

    tab.add_handler(cdp.page.JavascriptDialogOpening, on_dialog)

    await tab.evaluate("alert('Hello from automation!')")
    await tab.sleep(1)
    browser.stop()

uc.loop().run_until_complete(main())
```

## 8. Inject JS Before Page Load

```python
import nodriver as uc
from nodriver import cdp

async def main():
    browser = await uc.start()
    tab = browser.main_tab

    await tab.send(cdp.page.add_script_to_evaluate_on_new_document(
        source="""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => false
        });
        """
    ))

    await tab.get("https://nowsecure.nl")
    await tab.sleep(5)
    await tab.save_screenshot("stealth.png")
    browser.stop()

uc.loop().run_until_complete(main())
```

## 9. Device Emulation

```python
import nodriver as uc
from nodriver import cdp

async def main():
    browser = await uc.start()
    tab = browser.main_tab

    await tab.send(cdp.emulation.set_device_metrics_override(
        width=375, height=812,
        device_scale_factor=3, mobile=True
    ))
    await tab.send(cdp.network.set_user_agent_override(
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                   "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
                   "Mobile/15E148 Safari/604.1"
    ))

    await tab.get("https://example.com")
    await tab.save_screenshot("mobile.png")
    browser.stop()

uc.loop().run_until_complete(main())
```

## 10. File Upload

```python
import nodriver as uc

async def main():
    browser = await uc.start()
    tab = await browser.get("https://example.com/upload")

    file_input = await tab.select("input[type=file]")
    await file_input.send_file("/path/to/document.pdf")

    submit = await tab.find("Upload", best_match=True)
    await submit.click()

    await tab.sleep(3)
    browser.stop()

uc.loop().run_until_complete(main())
```

## 11. Screenshot & Element Flash

```python
import nodriver as uc

async def main():
    browser = await uc.start()
    tab = await browser.get("https://quotes.toscrape.com/")

    await tab.save_screenshot("full_page.png", full_page=True)

    first_quote = await tab.select(".quote")
    await first_quote.flash(duration=1)
    await first_quote.save_screenshot("first_quote.png")

    browser.stop()

uc.loop().run_until_complete(main())
```

## 12. Request Interception (CDP Fetch)

```python
import nodriver as uc
from nodriver import cdp

async def main():
    browser = await uc.start()
    tab = browser.main_tab

    await tab.send(cdp.fetch.enable(patterns=[
        cdp.fetch.RequestPattern(url_pattern="*.png", request_stage="Request"),
        cdp.fetch.RequestPattern(url_pattern="*.jpg", request_stage="Request"),
    ]))

    async def on_request_paused(event: cdp.fetch.RequestPaused):
        print(f"Blocked image: {event.request.url}")
        await tab.send(cdp.fetch.fail_request(
            request_id=event.request_id,
            reason=cdp.network.ErrorReason("BlockedByClient")
        ))

    tab.add_handler(cdp.fetch.RequestPaused, on_request_paused)

    await tab.get("https://example.com")
    await tab.sleep(3)
    browser.stop()

uc.loop().run_until_complete(main())
```

## 13. Wait for Element Pattern

```python
import nodriver as uc

async def main():
    browser = await uc.start()
    tab = await browser.get("https://example.com/spa")

    loaded = await tab.wait_for(selector=".content-loaded", timeout=15)
    if loaded:
        print("SPA content loaded!")
        print(loaded.text)

    browser.stop()

uc.loop().run_until_complete(main())
```

## 14. Proxy via BrowserContext

```python
import nodriver as uc

async def main():
    browser = await uc.start()

    tab = await browser.create_context(
        "https://httpbin.org/ip",
        proxy_server="http://user:pass@proxy:8080",
        new_window=True,
    )

    content = await tab.get_content()
    print(content)
    browser.stop()

uc.loop().run_until_complete(main())
```
