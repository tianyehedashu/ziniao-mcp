# nodriver API Reference

## Browser

### Creation

```python
# Factory method (async)
@classmethod
async def create(
    cls,
    config: Config = None,
    *,
    user_data_dir: PathLike = None,
    headless: bool = False,
    browser_executable_path: PathLike = None,
    browser_args: List[str] = None,
    sandbox: bool = True,
    host: str = None,        # connect to existing browser
    port: int = None,        # connect to existing browser
    **kwargs,
) -> Browser

# Convenience wrapper
async nodriver.start(**same_params) -> Browser
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `tabs` | `List[Tab]` | All page-type targets |
| `main_tab` | `Tab` | The initial tab |
| `cookies` | `CookieJar` | Cookie management |
| `connection` | `Connection` | Main WebSocket connection |
| `config` | `Config` | Browser configuration |
| `stopped` | `bool` | Whether browser has stopped |
| `websocket_url` | `str` | WebSocket debug URL |

### Methods

```python
async get(url="chrome://welcome", new_tab=False, new_window=False) -> Tab
async create_context(url, *, proxy_server=None, new_tab=False, new_window=True) -> Tab
async wait(time=0.1)             # alias: sleep
async update_targets()
async grant_all_permissions()
async tile_windows(windows=None, max_columns=0)  # requires mss
stop()
```

### Indexing

```python
browser[0]           # Tab by index
browser["google"]    # Tab by title/url substring match
```

---

## Tab

Inherits from `Connection`. Represents a browser tab.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `browser` | `Browser` | Parent browser |
| `target` | `TargetInfo` | CDP target info |
| `inspector_url` | `str` | DevTools URL for this tab |

### Navigation

```python
async get(url, new_tab=False, new_window=False) -> Tab
async back()
async forward()
async reload(ignore_cache=True, script_to_evaluate_on_load=None)
async close()
async get_content() -> str    # page HTML
```

### Element Finding

```python
async select(selector, timeout=10) -> Element
async select_all(selector, timeout=10, include_frames=False) -> List[Element]
async find(text, best_match=True, return_enclosing_element=True, timeout=10) -> Element
async find_all(text, timeout=10) -> List[Element]
async query_selector(selector) -> Element          # no retry
async query_selector_all(selector) -> List[Element] # no retry
async xpath(xpath, timeout=2.5) -> List[Element]
async wait_for(selector="", text="", timeout=10) -> Element
__call__(selector="", text="", timeout=10) -> Element  # alias for wait_for
```

**`select` vs `query_selector`**: `select` retries until timeout; `query_selector` returns immediately (may return None).

**`find` best_match**: Matches candidates by closest text length — `find("Accept All")` returns the button, not a script tag containing that text.

### JavaScript

```python
async evaluate(expression, await_promise=False, return_by_value=False)
async js_dumps(obj_name, return_by_value=True) -> dict
```

### Input

```python
async mouse_move(x, y, steps=10, flash=False)
async mouse_click(x, y, button="left", buttons=1, modifiers=0)
async mouse_drag(source_point, dest_point, relative=False, steps=1)
async scroll_down(amount=25)
async scroll_up(amount=25)
```

### Screenshots & Downloads

```python
async save_screenshot(filename="auto", format="jpeg", full_page=False) -> str
async set_download_path(path)
async download_file(url, filename=None)
```

### Window

```python
async get_window() -> Tuple[WindowID, Bounds]
async set_window_size(left, top, width, height)
async set_window_state(left=None, top=None, width=None, height=None, state="normal")
async maximize()
async minimize()
async fullscreen()
async medimize()        # restore to normal
```

### Storage

```python
async get_local_storage() -> dict
async set_local_storage(items: dict)
```

### Events

```python
add_handler(event_type_or_domain, handler)
remove_handler(event_type_or_domain, handler=None)
```

Handler signatures: `async def handler(event)` or `async def handler(event, tab)`.

### Misc

```python
async send(cdp_obj) -> result       # send any CDP command
async feed_cdp(cmd)                  # one-shot CDP
async verify_cf()                    # Cloudflare checkbox (requires opencv-python)
async bypass_insecure_connection_warning()
async flash_point(x, y, duration=0.5, size=10)
open_external_debugger()             # open DevTools in system browser
```

---

## Element

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `tab` | `Tab` | Owner tab |
| `node` | `cdp.dom.Node` | Underlying DOM node |
| `text` | `str` | Direct text content |
| `text_all` | `str` | All text including children |
| `attrs` | `ContraDict` | HTML attributes |
| `parent` | `Element` | Parent element |
| `children` | `List[Element]` | Child elements |
| `remote_object` | `RemoteObject` | CDP remote object |
| `object_id` | `str` | Object ID |
| `tag_name` | `str` | Tag name |

### Interaction

```python
async click()
async mouse_click(button="left", buttons=1, modifiers=0)
async mouse_move()
async mouse_drag(destination, relative=False, steps=1)
async send_keys(text)
async clear_input()
async send_file(*file_paths)
async focus()
async select_option()           # for <option> elements
async scroll_into_view()
```

### DOM & JS

```python
async apply(js_function, return_by_value=True)  # e.g., apply("function(el){return el.value}")
__call__(js_method)                               # e.g., element("play")
async get_html() -> str
async get_position(abs=False) -> Position
async query_selector(selector) -> Element
async query_selector_all(selector) -> List[Element]
async update()                  # refresh node data
async remove_from_dom()
async save_to_dom()
```

### Visual

```python
async save_screenshot(filename, format="png", scale=1)
async flash(duration=0.5)
async highlight_overlay()
```

---

## Config

```python
Config(
    user_data_dir=AUTO,           # str or Path; AUTO = temp dir, cleaned up on exit
    headless=False,
    browser_executable_path=AUTO, # AUTO = auto-detect Chrome
    browser_args=AUTO,
    sandbox=True,                 # False on Linux root
    lang="en-US",
    host=AUTO,                    # for connecting to existing browser
    port=AUTO,
    expert=AUTO,                  # disables site isolation, opens shadow roots
)
```

```python
config.add_argument("--proxy-server=http://proxy:8080")
config.add_extension("/path/to/crx_or_folder")
```

Default browser args:

```
--remote-allow-origins=*
--no-first-run
--no-service-autorun
--no-default-browser-check
--homepage=about:blank
--no-pings
--password-store=basic
--disable-infobars
--disable-breakpad
--disable-dev-shm-usage
--disable-session-crashed-bubble
--disable-search-engine-choice-screen
```

---

## CookieJar

```python
browser.cookies  # -> CookieJar

async get_all(requests_cookie_format=False) -> List[Cookie]
async set_all(cookies: List[cdp.network.CookieParam])
async save(file=".session.dat", pattern=".*")
async load(file=".session.dat", pattern=".*")
async clear()
```

---

## CDP Domains Quick Reference

All via `from nodriver import cdp`, sent with `await tab.send(cdp.xxx.method(...))`.

| Domain | Key Methods |
|--------|-------------|
| `cdp.page` | `navigate`, `reload`, `add_script_to_evaluate_on_new_document`, `handle_javascript_dialog`, `capture_screenshot` |
| `cdp.network` | `enable`, `set_user_agent_override`, `set_extra_http_headers`, `get_cookies`, `set_cookie` |
| `cdp.input_` | `dispatch_mouse_event`, `dispatch_key_event`, `dispatch_touch_event` |
| `cdp.emulation` | `set_device_metrics_override`, `set_user_agent_override`, `set_geolocation_override` |
| `cdp.runtime` | `evaluate`, `call_function_on`, `get_properties` |
| `cdp.dom` | `get_document`, `query_selector`, `get_outer_html`, `set_attribute_value` |
| `cdp.storage` | `get_cookies`, `set_cookies`, `clear_cookies` |
| `cdp.fetch` | `enable`, `fulfill_request`, `continue_request`, `fail_request` |
| `cdp.console` | `MessageAdded` (event) |
| `cdp.target` | `create_target`, `close_target`, `get_targets` |
| `cdp.overlay` | `highlight_node`, `hide_highlight` |

---

## Position

Returned by `Element.get_position()`:

```python
@dataclass
class Position:
    left: float
    top: float
    width: float
    height: float
    center: Tuple[float, float]
    abs_x: float  # absolute
    abs_y: float
```

---

## Utility Functions

```python
nodriver.loop() -> asyncio.AbstractEventLoop  # create and set event loop
nodriver.start(**kwargs) -> Browser            # convenience for Browser.create
```
