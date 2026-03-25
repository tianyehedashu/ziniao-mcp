# 本仓库反自动化检测能力索引

本文档汇总 **ziniao-mcp / ziniao_webdriver** 中与反检测、拟人化相关的实现位置与能力边界；**正文与配置示例均写在本 skill 内**，不引用 skill 目录外的文件。

---

## 1. 总体架构（三层）

| 层级 | 实现位置 | 作用摘要 |
|------|----------|----------|
| **协议层** | 使用 **nodriver** 仅通过 **CDP** 连接浏览器；紫鸟场景下由客户端启动浏览器，Python 侧「只连不启」 | 无 ChromeDriver、无 `$cdc_*`、不引入 Playwright/Puppeteer 类全局污染；`navigator.webdriver` 不因 WebDriver 规范被强制为 true |
| **JS 环境** | `ziniao_webdriver/js_patches.py`（规范实现）+ `apply_stealth()`（`ziniao_mcp/stealth/__init__.py`）；`ziniao_mcp/stealth/js_patches.py` 为 re-export shim | `Page.addScriptToEvaluateOnNewDocument` + 对已有 tab `evaluate`，覆盖/伪造易被探测的 API 与指纹 |
| **行为层** | `ziniao_mcp/stealth/human_behavior.py`；由 `ziniao_mcp/tools/input.py` 等统一调度 | 贝塞尔鼠标轨迹、随机延迟、拟人输入/滚动等 |

会话侧注入入口：`SessionManager._apply_stealth_to_browser`（`ziniao_mcp/session.py`），在 `open_store` / `connect` 建立 nodriver `Browser` 后调用。

---

## 2. 紫鸟侧「双点」注入

| 时机 | 机制 | 脚本 |
|------|------|------|
| **店铺打开前** | 紫鸟 HTTP `startBrowser` 的 `injectJsInfo`（由 `ZiniaoClient.open_store` 传入） | `STEALTH_JS_MINIMAL`（`js_patches.py`）：toString 保护、webdriver、permissions、chrome 补全、清理 |
| **CDP 连接后** | `apply_stealth()` | `STEALTH_JS`（`build_stealth_js()` 拼接）：完整补丁集（默认不含 WebGL vendor，见第 3 节） |

精简版故意省略依赖 DOM 或过早起作用的补丁；完整版在新文档与后续导航中生效。

### 脚本版本对照

| 版本 | 变量名 | 包含的补丁 | 用途 |
|------|--------|------------|------|
| 完整版 | `STEALTH_JS` | 全部 12 段（`webgl_vendor` 默认不参与拼接） | CDP 连接后注入 |
| 精简版 | `STEALTH_JS_MINIMAL` | toString + webdriver + permissions + chrome + cleanup | 紫鸟 `injectJsInfo` 预注入 |

---

## 3. JS 补丁清单（`js_patches.py`）

注入顺序约束：**`PATCH_NATIVE_TOSTRING` 必须最先，`PATCH_STEALTH_CLEANUP` 必须最后**。

| 常量 | 对抗点 / 作用 |
|------|----------------|
| `PATCH_NATIVE_TOSTRING` | 被改写函数的 `toString` 仍返回 `[native code]` |
| `PATCH_NAVIGATOR_WEBDRIVER` | `navigator.webdriver` → `false`（兜底） |
| `PATCH_NAVIGATOR_PLUGINS` | 空 `plugins` 时伪造 PDF 相关 `PluginArray` |
| `PATCH_NAVIGATOR_PERMISSIONS` | `permissions.query(notifications)` 与 `Notification.permission` 一致 |
| `PATCH_WINDOW_CHROME` | 补全 `chrome.app` / `runtime` / `loadTimes` / `csi` 等 |
| `PATCH_IFRAME_WEBDRIVER` | iframe 内 `navigator.webdriver` + `MutationObserver` |
| `PATCH_WEBGL_VENDOR` | WebGL vendor/renderer 伪装（**默认关闭**，避免与紫鸟自带指纹冲突；`build_stealth_js(webgl_vendor=True)` 开启） |
| `PATCH_CANVAS_FINGERPRINT` | Canvas 导出确定性微噪声 |
| `PATCH_AUDIO_FINGERPRINT` | `AudioBuffer.getChannelData` 微扰动 |
| `PATCH_WEBRTC_LEAK` | `RTCPeerConnection` 代理为 relay、清空 ICE，减真实 IP 泄露 |
| `PATCH_AUTOMATION_FLAGS` | `languages` / `hardwareConcurrency` / `deviceMemory` 异常时兜底 |
| `PATCH_STEALTH_CLEANUP` | 移除 `window.__stealth_native` |

`build_stealth_js(...)` 按布尔参数逐项开关，示例见下节。

---

## 4. 人类行为模拟（`human_behavior.py`）

| 符号 | 说明 |
|------|------|
| `BehaviorConfig` | `delay_*`、`typing_*`、`mouse_movement`、`mouse_steps` |
| `random_delay` | 操作间正态分布随机等待 |
| `human_click` / `human_fill` / `human_type` / `human_hover` / `human_scroll` | 贝塞尔移动、点击区域随机偏移、逐字节奏与长停顿、分段滚动等 |

**MCP 工具链上的调度**（`ziniao_mcp/tools/input.py`）：若 `StealthConfig.enabled && human_behavior` 则走完整拟人 + `random_delay`；否则若为紫鸟店铺会话（`backend_type == "ziniao"`）仍可走 **简化拟人**（如 `_move_mouse_humanlike`、无配置时的 `human_type`/`human_fill` 等）；纯 Chrome 无 stealth 时多为原生 `click`/`send_keys`。

---

## 5. 配置（`StealthConfig` / YAML / `build_stealth_js`）

- 类定义：`ziniao_mcp/stealth/__init__.py` → `StealthConfig`（`enabled`、`js_patches`、`human_behavior`；`delay_range` → `delay_min_ms`/`delay_max_ms`；`typing_speed` → `typing_min_ms`/`typing_max_ms`；`mouse_movement`）。
- 守护进程：`ziniao_mcp/cli/daemon.py` 从用户配置中的 `stealth` 字典读取并传入 `SessionManager`（与安装包/向导生成的 `~/.ziniao/config.yaml` 等一致，键路径为 `ziniao.stealth`）。

### `ziniao.stealth`（YAML）

```yaml
ziniao:
  stealth:
    enabled: true           # 总开关
    js_patches: true        # JS 环境伪装开关
    human_behavior: true    # 人类行为模拟开关
    delay_range: [200, 800] # 操作间延迟范围 (ms)
    typing_speed: [50, 150] # 打字速度范围 (ms/字符)
    mouse_movement: true    # 鼠标轨迹模拟开关
```

### 补丁粒度（Python，进程内拼接脚本）

```python
from ziniao_webdriver.js_patches import build_stealth_js  # 规范路径
# 或兼容旧代码: from ziniao_mcp.stealth.js_patches import build_stealth_js

script = build_stealth_js(
    native_tostring=True,      # toString 保护（建议始终开启）
    webdriver=True,             # navigator.webdriver 覆盖
    plugins=True,               # navigator.plugins 伪造
    permissions=True,           # navigator.permissions 修正
    chrome_obj=True,            # window.chrome 补全（含 chrome.app）
    iframe_webdriver=True,      # iframe webdriver 修补
    webgl_vendor=False,         # WebGL 指纹伪造（默认关闭）
    canvas_fingerprint=True,    # Canvas 指纹噪声
    audio_fingerprint=True,     # AudioContext 指纹噪声
    webrtc_leak=True,           # WebRTC IP 泄露防护
    automation_flags=True,      # 自动化标志修正
)
```

---

## 6. 其他相关实现（补充）

| 项 | 位置 | 说明 |
|----|------|------|
| 录制器页面内存储 | `ziniao_mcp/tools/recorder.py` | 使用 **Symbol** 键在 `window` 上挂状态，降低枚举可见性（注释中标明 anti-detection 意图） |
| UA / 设备模拟 | `ziniao_mcp/tools/emulation.py` | 紫鸟场景下 UA 常与硬件指纹由客户端管理，工具侧可能跳过 UA 覆盖（见源码说明） |
| iframe 内操作 | `ziniao_mcp/iframe.py` | 隔离世界 + 坐标合成；**不是**独立「反检测层」，但减少因跨 frame 操作失败而暴露自动化特征 |

---

## 7. MCP 层不覆盖的范围

以下维度由 **紫鸟客户端 / 操作系统 / Chromium 网络栈** 等负责，本仓库 MCP 不兜底：

| 检测维度 | 说明 | 责任方 |
|----------|------|--------|
| 浏览器启动参数 | `--disable-blink-features` 等 | 紫鸟客户端 |
| 代理/IP | 店铺级代理和 IP 轮换 | 紫鸟客户端 |
| User-Agent | 可由 MCP `emulate` 等工具覆盖 | MCP tools |
| 字体指纹 | 依赖操作系统字体库 | 紫鸟客户端 / OS |
| TLS 指纹 (JA3/JA4) | 取决于 Chromium 版本与编译 | Chromium |
| HTTP/2 指纹 | 取决于网络栈 | Chromium |
| Screen 属性一致性 | `outerWidth/Height` 等与窗口尺寸匹配 | 紫鸟客户端 |

---

## 8. 测试与源码树

```text
uv run pytest tests/test_stealth.py -v
```

```text
ziniao_webdriver/
├── js_patches.py        # 补丁常量, build_stealth_js, STEALTH_JS / STEALTH_JS_MINIMAL（规范实现）
└── ...

ziniao_mcp/stealth/
├── __init__.py          # StealthConfig, apply_stealth
├── js_patches.py        # re-export shim → ziniao_webdriver.js_patches
└── human_behavior.py    # 拟人化 CDP 输入
```

独立 RPA 脚本（`nodriver` + `ZiniaoClient`）若**不**经过 `SessionManager`，需自行决定是否调用与 MCP 等价的 JS 注入逻辑；紫鸟店铺仍可通过 `open_store(..., js_info=...)` 使用客户端侧 `injectJsInfo`（与 MCP 打开店铺时注入 `STEALTH_JS_MINIMAL` 对齐，见 [lifecycle.md](lifecycle.md)）。
