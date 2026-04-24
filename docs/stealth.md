# 反自动化检测系统

ziniao-mcp 内置三层纵深反检测机制，从协议层到 API 层再到行为层逐级防护，自动生效，无需手动配置。

## 架构概览

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                      │
│  第一层：协议层隐身 (nodriver)                                        │
│  · 纯 CDP 直连，无 WebDriver 中间代理                                │
│  · 无额外二进制进程，不向 DOM 注入任何变量                             │
│  · 仅连接紫鸟已启动的浏览器，进程树零痕迹                              │
│                                                                      │
│  ┌───────────────────────────────────────────────────────────────┐   │
│  │                                                                │   │
│  │  第二层：JS 环境伪装 (js_patches.py)                            │   │
│  │  · 原型链 toString 保护     · Canvas/Audio 指纹噪声             │   │
│  │  · navigator 属性伪装       · WebRTC IP 泄露防护                │   │
│  │  · window.chrome 补全       · 自动化标志修正                     │   │
│  │                                                                │   │
│  │  ┌────────────────────────────────────────────────────────┐   │   │
│  │  │                                                         │   │   │
│  │  │  第三层：人类行为模拟 (human_behavior.py)                 │   │   │
│  │  │  · 贝塞尔曲线鼠标轨迹   · 正态分布随机延迟                │   │   │
│  │  │  · 拟人化逐字输入        · 分段滚动模拟                    │   │   │
│  │  │                                                         │   │   │
│  │  └────────────────────────────────────────────────────────┘   │   │
│  │                                                                │   │
│  │          __init__.py  (StealthConfig / apply_stealth)          │   │
│  └────────────────────────────┬───────────────────────────────────┘   │
│                               │                                       │
│                     session.py 在 CDP 连接时调用                      │
└───────────────────────────────┼───────────────────────────────────────┘
                                │
             紫鸟客户端启动浏览器 → nodriver 通过 CDP 端口连接
```

## 第一层：协议层隐身 (nodriver)

nodriver 是 [undetected-chromedriver](https://github.com/ultrafunkamsterdam/nodriver) 的下一代实现，是整个反检测体系的基石。它从协议层面消除了自动化浏览器最容易被检测的根源性痕迹。

### WebDriver 与 CDP 的异同

两者都是「你的程序 ↔ 浏览器」的通信方式，但设计目标和实现方式完全不同：

| 维度 | WebDriver (W3C) | CDP (Chrome DevTools Protocol) |
|---|---|---|
| **标准** | W3C 标准，跨浏览器 | Chrome/Chromium 专用，非 W3C |
| **连接方式** | HTTP + JSON，通常先连到 **driver 进程**（如 chromedriver），再由 driver 连浏览器 | 直接 **WebSocket/TCP** 连浏览器调试端口，无中间进程 |
| **谁在说话** | 你的代码 → ChromeDriver 等 → 浏览器（两层） | 你的代码 → 浏览器（一层） |
| **浏览器如何被控制** | Driver 通过厂商私有协议（如 Chrome DevTools Protocol）控制浏览器，同时 **向页面注入脚本** 做元素解析等 | 客户端直接发 CDP 命令；CDP 就是 Chrome 开发者工具用的同一套协议，**不要求** 向页面注入自动化用脚本 |
| **navigator.webdriver** | 规范要求：通过 WebDriver 控制时设为 `true` | 协议本身不要求改；只有用 `--enable-automation` 等启动参数时 Chrome 才会设 |
| **DOM/页面污染** | ChromeDriver 会在 `document` 上挂 `$cdc_` 等变量用于内部通信 | 无；只要不在自己的逻辑里注入，页面就是干净的 |
| **能力范围** | 高层：点击、输入、取属性、截图等，偏「测试/脚本」 | 底层 + 广：DOM、网络、性能、输入、缓存、Cookie、截图等，和 DevTools 一致 |
| **典型使用者** | Selenium、WebDriver 标准实现 | Puppeteer、Playwright（在其上再封装）、nodriver、以及本项目的 ziniao-mcp |

**共同点**：都能驱动浏览器完成点击、输入、导航等自动化操作；都依赖浏览器提供「可被远程控制」的接口。

**差异小结**：WebDriver 是「标准 + 中间层」，中间层（driver）会改浏览器/页面状态，易被检测；CDP 是「直连 + 无注入」，不强制改页面环境，反检测更友好。nodriver 只用 CDP、不用 WebDriver，因此没有 chromedriver 和 `navigator.webdriver` 等问题。

### 为什么选择 nodriver 而非 Selenium / Playwright / Puppeteer

传统自动化框架均存在结构性的检测缺陷：

| 框架 | 协议 | 核心检测点 |
|---|---|---|
| **Selenium + ChromeDriver** | WebDriver (W3C) | chromedriver 二进制向 DOM 注入 `$cdc_` 前缀变量；设置 `navigator.webdriver = true`；`--enable-automation` 暴露 Chrome 信息栏 |
| **Playwright** | CDP (封装层) | 注入 `__playwright_evaluation_script__`、`__pw_*` 全局变量；自定义 `Runtime.evaluate` 执行上下文 |
| **Puppeteer** | CDP (封装层) | 注入 `_puppeteerEvaluateBinding`；`Page.addScriptToEvaluateOnNewDocument` 的 sourceURL 包含 pptr 标识 |

nodriver 的根本差异在于：**它不依赖任何中间代理（如 chromedriver），而是直接通过 CDP 协议与 Chrome 通信。** 这从源头上避免了上述所有注入行为。

### nodriver 的具体防护

**1. 无 chromedriver 二进制 → 无 `cdc_` 痕迹**

Selenium 依赖 chromedriver 作为中间桥接，而 chromedriver 会在 `document` 上注入带 `$cdc_` 前缀的属性用于内部通信。这是目前最广泛的自动化检测手段之一：

```javascript
// 检测脚本常用方式
Object.keys(document).some(key => key.startsWith('$cdc_'))
```

nodriver 完全没有 chromedriver 进程，DOM 中不存在任何 `$cdc_` 变量。

**2. 无 WebDriver 协议 → `navigator.webdriver` 不被设置**

W3C WebDriver 规范要求浏览器在通过 WebDriver 协议控制时将 `navigator.webdriver` 设置为 `true`。nodriver 使用的 CDP 协议不触发此标志。

**3. 无自动化全局变量**

nodriver 执行 JavaScript 时不注入任何框架特有的绑定函数或全局变量：

| 变量 | 来源 | nodriver 中是否存在 |
|---|---|---|
| `$cdc_asdjflasutopfhvcZLmcfl_` | ChromeDriver | 不存在 |
| `__playwright_evaluation_script__` | Playwright | 不存在 |
| `__pw_*` | Playwright | 不存在 |
| `_puppeteerEvaluateBinding` | Puppeteer | 不存在 |
| `window.cdc_adoQpoasnfa76pfcZLmcfl` | ChromeDriver | 不存在 |

**4. 干净的浏览器启动参数**

nodriver 的默认启动参数仅包含功能性配置，不包含暴露自动化身份的参数：

```
--remote-allow-origins=*      # 允许 CDP 跨域连接
--no-first-run                # 跳过首次运行向导
--no-service-autorun          # 禁止后台服务自启
--no-default-browser-check    # 跳过默认浏览器检查
--homepage=about:blank        # 空白首页
--no-pings                    # 禁用超链接审计
--password-store=basic        # 基础密码存储
--disable-infobars            # 禁用信息栏
--disable-breakpad            # 禁用崩溃报告
--disable-dev-shm-usage       # 避免共享内存问题
```

注意：**没有** `--enable-automation`（Selenium 默认添加）、**没有** `--disable-blink-features=AutomationControlled`（这个参数本身也会被检测）。

**5. ziniao-mcp 中的特殊优势：仅连接不启动**

在本项目中，nodriver 的隐身效果更强 — 浏览器由紫鸟客户端启动，nodriver 仅通过 CDP 端口连接到已运行的浏览器：

```python
# session.py
browser = await nodriver.Browser.create(
    host="127.0.0.1",
    port=cdp_port,  # 紫鸟客户端返回的调试端口
)
```

这意味着：
- 浏览器进程树中没有 nodriver 或 Python 的父进程关系
- 浏览器的启动参数完全由紫鸟客户端控制（含店铺级指纹和代理配置）
- 从操作系统层面看，浏览器就是一个普通的用户打开的 Chrome 实例

---

## 注入时机

JS 环境伪装脚本在两个节点注入，确保页面加载前和运行中均受保护：

| 阶段 | 方式 | 脚本版本 | 说明 |
|---|---|---|---|
| 店铺打开时 | 紫鸟客户端 `injectJsInfo` | `STEALTH_JS_MINIMAL` | 在 CDP 连接建立前由客户端注入，覆盖最基本的检测点 |
| CDP 连接后 | `Page.addScriptToEvaluateOnNewDocument` + `evaluate` | `STEALTH_JS` | 完整补丁集，新页面自动继承 |

`STEALTH_JS_MINIMAL` 包含：toString 保护、webdriver 覆盖、permissions 修正、chrome 对象补全、清理。

`STEALTH_JS` 在此基础上增加：plugins 伪造、iframe webdriver、Canvas 噪声、Audio 噪声、WebRTC 防护、自动化标志修正。

---

## 第二层：JS 环境伪装

共 12 个独立补丁，按依赖顺序拼接为一段同步执行的脚本。

### 1. 原型链 toString 保护 (`PATCH_NATIVE_TOSTRING`)

**对抗的检测方式：** 检测脚本对被覆盖的函数调用 `.toString()`，若返回值不是 `function xxx() { [native code] }` 则判定为自动化。

**实现原理：**

```
原始调用链:  fn.toString()  →  Function.prototype.toString  →  返回函数源码

伪装后:      fn.toString()  →  被劫持的 toString  →  查 WeakMap
                                                      ├─ 命中 → 返回 "function xxx() { [native code] }"
                                                      └─ 未命中 → 调用原始 toString
```

使用 `WeakMap` 存储需要伪装的函数映射，外部代码无法枚举或访问该 Map。通过 `window.__stealth_native` 辅助函数（非枚举属性）为后续补丁注册伪装，脚本执行完毕后由 `PATCH_STEALTH_CLEANUP` 删除该辅助属性，不留任何全局痕迹。

**此补丁必须第一个注入**，否则后续补丁中被覆盖的函数将暴露真实源码。

### 2. navigator.webdriver 覆盖 (`PATCH_NAVIGATOR_WEBDRIVER`)

**对抗的检测方式：** `navigator.webdriver === true` 是自动化浏览器最基本的标志。

**实现原理：** 通过 `Object.defineProperty` 将 `navigator.webdriver` 的 getter 覆盖为返回 `false`，与真实 Chrome 行为一致。

虽然 nodriver 理论上不设置此属性，但部分 Chromium 版本或 CDP 连接模式下仍可能为 `true`，因此主动覆盖作为安全兜底。

### 3. navigator.plugins 伪造 (`PATCH_NAVIGATOR_PLUGINS`)

**对抗的检测方式：** 自动化浏览器的 `navigator.plugins` 通常为空数组，真实 Chrome 至少包含 PDF 相关插件。

**实现原理：** 当检测到 `navigator.plugins.length === 0` 时，构造一个完整的 `PluginArray` 对象，包含三个标准 Chrome 插件：

| 插件名 | 文件名 | MIME 类型 |
|---|---|---|
| Chrome PDF Plugin | `internal-pdf-viewer` | `application/x-google-chrome-pdf` |
| Chrome PDF Viewer | `mhjfbmdgcfjbbpaeojofohoefgiehjai` | `application/pdf` |
| Chromium PDF Viewer | `internal-pdf-viewer` | `application/pdf` |

通过 `Object.create(PluginArray.prototype)` 构造，确保 `instanceof` 检查通过。每个插件的 `item()`、`namedItem()`、`refresh()` 方法均完整实现。

### 4. navigator.permissions 修正 (`PATCH_NAVIGATOR_PERMISSIONS`)

**对抗的检测方式：** 调用 `navigator.permissions.query({name: 'notifications'})` 后检查返回的 `state` 是否与 `Notification.permission` 一致。自动化浏览器常返回异常值。

**实现原理：** 代理 `navigator.permissions.query`，对 `notifications` 权限查询进行兜底：优先使用原始查询结果，失败时构造一个 `PermissionStatus` 伪对象，其 `state` getter 直接读取 `Notification.permission` 以保持一致性。被覆盖的 `query` 函数通过 `__stealth_native` 注册 toString 伪装。

### 5. window.chrome 补全 (`PATCH_WINDOW_CHROME`)

**对抗的检测方式：** 真实 Chrome 浏览器的 `window.chrome` 包含 `app`、`runtime`、`loadTimes`、`csi` 等属性。缺少任一项即可判定为非标准环境。

**实现原理：** 逐一检查并补全以下对象：

| 属性 | 补全内容 |
|---|---|
| `chrome.app` | `InstallState`、`RunningState` 枚举，`getDetails()`、`getIsInstalled()`、`installState()` 方法 |
| `chrome.runtime` | `connect()`、`sendMessage()`、`onMessage`、`onConnect`，`id` 为 `undefined` |
| `chrome.loadTimes` | 返回包含 `commitLoadTime`、`connectionInfo` 等 13 个字段的时间数据对象 |
| `chrome.csi` | 返回 `onloadT`、`startE`、`pageT`、`tran` 四字段对象 |

所有补全的函数均通过 `__stealth_native` 注册 toString 伪装。

### 6. iframe webdriver 修补 (`PATCH_IFRAME_WEBDRIVER`)

**对抗的检测方式：** 检测脚本通过动态创建 iframe 并检查其 `contentWindow.navigator.webdriver`，绕过主框架的覆盖。

**实现原理：** 双重防护机制：

1. **即时修补** — 遍历页面中所有已存在的 iframe，覆盖其 `navigator.webdriver`
2. **持续监听** — 通过 `MutationObserver` 监听 DOM 变化，对新插入的 iframe 自动修补

每个 iframe 同时绑定 `load` 事件监听器，确保 iframe 内容重载后仍受保护。

### 7. WebGL 指纹伪造 (`PATCH_WEBGL_VENDOR`)

**对抗的检测方式：** 通过 `WEBGL_debug_renderer_info` 扩展读取 GPU 的 `UNMASKED_VENDOR_WEBGL` 和 `UNMASKED_RENDERER_WEBGL`，生成硬件指纹。

**实现原理：** 代理 `WebGLRenderingContext.prototype.getParameter` 和 `WebGL2RenderingContext.prototype.getParameter`，拦截对两个 debug 参数的查询并返回伪造值。其余参数查询透传给原始方法。

伪造值取值分两种模式：

| 模式 | 触发条件 | UNMASKED_VENDOR | UNMASKED_RENDERER |
|---|---|---|---|
| **占位兜底** | 未提供 `profile_seed` | `Intel Inc.` | `Intel Iris OpenGL Engine` |
| **稳定硬件池** | 提供 `profile_seed`（默认由 SessionManager 推导） | 从 `_WEBGL_POOL` 按 BLAKE2b 哈希选取 | 与 vendor 配对 |

`_WEBGL_POOL`（9 条）覆盖真实 Windows + Chrome + ANGLE 的典型硬件分布，涵盖 Intel UHD/Iris Xe、NVIDIA GTX/RTX、AMD Radeon，例如：

```
Google Inc. (Intel)   / ANGLE (Intel, Intel(R) UHD Graphics 730 Direct3D11 ..., D3D11)
Google Inc. (NVIDIA)  / ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 ..., D3D11)
Google Inc. (AMD)     / ANGLE (AMD, AMD Radeon(TM) Graphics Direct3D11 ..., D3D11)
```

同一 `profile_seed` 跨会话稳定（查 BrowserLeaks 不会抖动），不同 profile 得到不同 vendor/renderer，避免出现 "Intel Inc. / Intel Iris OpenGL Engine" 这类被 BrowserLeaks 标记为「非典型」的常见 stealth 占位。

**默认关闭**，因为紫鸟浏览器通常自行处理 WebGL 指纹，重复覆盖可能产生冲突。通过 `webgl_vendor=True` 开启（本机 Chrome launch/connect 路径由 SessionManager 自动开启）。

### 8. Canvas 指纹噪声 (`PATCH_CANVAS_FINGERPRINT`)

**对抗的检测方式：** 在 Canvas 上绘制特定图形，调用 `toDataURL()` 或 `toBlob()` 导出像素数据并哈希，不同硬件+驱动+OS 组合产生不同指纹。自动化环境中同一机器的多个实例指纹完全一致。

**实现原理：**

```
正常调用:  canvas.toDataURL()  →  原始像素数据  →  导出

伪装后:    canvas.toDataURL()  →  原始像素数据  →  确定性噪声注入  →  临时 Canvas 渲染  →  导出
```

关键设计：

- **确定性噪声** — 使用 `profile_seed` 派生的稳定种子（`seed`），同一像素位置的噪声值固定。提供 `profile_seed` 时 `seed` 跨刷新/跨标签/跨重启全部一致，同一 profile 的 BrowserLeaks Canvas Signature 稳定；缺省情况下退回到页面会话级 `Math.random()`（单 IIFE 内一致、跨刷新抖动）。这样既避开被"多次采样比对"，也避免"每次刷新 Uniqueness 100% 反向暴露反指纹"的问题
- **微量扰动** — 仅约 2% 的像素被修改，每个像素的 R/G/B 某一通道 ±1，人眼完全不可见
- **非破坏性** — 通过临时 Canvas 渲染噪声后的数据并导出，原始 Canvas 内容不受影响
- **WebGL 兼容** — 若 Canvas 使用的是 WebGL 上下文，`getContext('2d')` 返回 `null`，自动回退到原始方法

同时覆盖 `toDataURL` 和 `toBlob` 两个导出方法。

### 9. AudioContext 指纹噪声 (`PATCH_AUDIO_FINGERPRINT`)

**对抗的检测方式：** 通过 `OfflineAudioContext` 创建振荡器和压缩器节点，渲染音频后读取 `getChannelData()`，对采样数据求哈希。不同硬件的浮点运算精度差异产生唯一指纹。

**实现原理：** 代理 `AudioBuffer.prototype.getChannelData`，在返回的 `Float32Array` 中每隔 100 个采样点注入 0.0000001 量级的微量扰动。噪声算法基于 `profile_seed` 派生的稳定种子（同 Canvas），同一 profile 跨会话 Audio Signature 一致；未提供 seed 时回退到页面会话随机。

扰动量级远低于人耳感知阈值，不影响正常音频播放。

### 10. WebRTC IP 泄露防护 (`PATCH_WEBRTC_LEAK`)

**对抗的检测方式：** 通过 `RTCPeerConnection` 的 ICE 候选收集获取用户真实局域网 IP 地址，即使使用代理也会暴露。

**实现原理：** 使用 `Proxy` 拦截 `RTCPeerConnection` 构造函数，在创建实例前强制修改配置：

```javascript
config.iceTransportPolicy = 'relay';  // 仅允许 TURN 中继，禁止本地候选
config.iceServers = [];                // 清空 ICE 服务器（无 TURN 则不产生任何候选）
```

同时覆盖 `window.RTCPeerConnection` 和 `window.webkitRTCPeerConnection`（兼容旧版 Chrome）。Proxy 方式保持了完整的原型链和静态方法，`instanceof` 检查不受影响。

### 11. 自动化标志修正 (`PATCH_AUTOMATION_FLAGS`)

**对抗的检测方式：** 检查 `navigator.languages`、`navigator.hardwareConcurrency`、`navigator.deviceMemory` 等属性。自动化环境中这些值常为空或异常低。

**实现原理：** 逐一检查并兜底：

| 属性 | 条件 | 伪装值 |
|---|---|---|
| `navigator.languages` | 为空或不存在 | `['en-US', 'en']` |
| `navigator.hardwareConcurrency` | 小于 2 或不存在 | `4` |
| `navigator.deviceMemory` | 小于 2 或不存在 | `8` (GB) |

仅在值异常时覆盖，若浏览器已有合理值则不干预。

### 12. 辅助属性清理 (`PATCH_STEALTH_CLEANUP`)

**作用：** 删除 `window.__stealth_native` 临时辅助属性。该属性仅在脚本同步执行期间存在（页面代码尚未运行），清理后外部代码无法发现任何全局痕迹。

**此补丁必须最后一个注入。**

---

## 第三层：人类行为模拟

通过 CDP `Input.dispatchMouseEvent` / `Input.dispatchKeyEvent` 在协议层模拟操作，所有交互工具（`click`、`fill`、`type_text`、`hover`、`scroll`）自动启用。

### 鼠标轨迹模拟

使用三次贝塞尔曲线生成自然的鼠标移动路径：

```
起点 (Sx, Sy) ──── 控制点1 (随机偏移) ──── 控制点2 (随机偏移) ──── 终点 (Ex, Ey)
```

- 默认 15 步插值，每步间隔 5~20ms 随机抖动
- 两个控制点基于起终点距离的 30% 范围内随机生成
- 通过 `window._lastMouseX/Y` 记录上次鼠标位置，确保连续操作轨迹连贯

### 点击行为

```
鼠标移动 (贝塞尔曲线) → 到达元素区域 → 随机偏移 (20%~80% 范围内) → 执行点击
```

点击位置不会精确命中元素中心，而是在元素的 20%~80% 边界范围内随机取点，模拟真实用户的不精确性。

### 输入行为

| 操作 | 模拟策略 |
|---|---|
| 逐字输入 (`human_type`) | 每字符间隔 50~150ms 随机波动，约 5% 概率出现 300~800ms 长停顿（模拟思考） |
| 填写字段 (`human_fill`) | 点击聚焦 → Ctrl+A 全选 → Backspace 清除 → 逐字输入 |

### 滚动行为

分多段小幅滚动执行，而非一次性跳转：

- 每段滚动 40~120 像素
- 段间间隔 20~80ms
- 完成后额外等待 50~200ms

### 操作间延迟

所有操作间隔使用正态分布随机等待：

```
延迟 = clamp(gauss(mean, std), min, max)

其中: mean = (min + max) / 2,  std = (max - min) / 4
```

默认范围 200~800ms，可通过配置调整。

---

## 配置

通过 `config/config.yaml` 的 `ziniao.stealth` 节控制：

```yaml
ziniao:
  stealth:
    enabled: true           # 总开关
    js_patches: true        # JS 环境伪装开关
    human_behavior: true    # 人类行为模拟开关
    delay_range: [200, 800] # 操作间延迟范围 (ms)
    typing_speed: [50, 150] # 打字速度范围 (ms/字符)
    mouse_movement: true    # 鼠标轨迹模拟开关
    webgl_vendor: false     # WebGL vendor/renderer 伪造
    profile_seed: null      # 稳定指纹 seed；null 时由 SessionManager 自动推导
```

### 稳定指纹 (`profile_seed`)

提供非空 `profile_seed` 后，Canvas 噪声、AudioContext 噪声、WebGL vendor/renderer 均基于 BLAKE2b 派生的稳定参数，表现如下：

- **同一 profile 多次打开** — Canvas / Audio / WebGL 指纹稳定，BrowserLeaks 的 Uniqueness 不再 100%
- **不同 profile** — WebGL 硬件对从 `_WEBGL_POOL` 中近似均匀分布地选取，Canvas/Audio seed 独立变化
- **留白** — `profile_seed=None` 时完全保留页面会话级随机（和历史行为一致）

SessionManager 自动推导规则：

| 场景 | `profile_seed` |
|---|---|
| 紫鸟 `open_store` / `connect_store` | `ziniao:<store_id>` |
| `launch_chrome`（已知 `user_data_dir`） | `chrome:ud:<规范化绝对路径>` |
| `connect_chrome`（仅 CDP 端口） | `chrome:port:<cdp_port>` |

Python 层也可直接调用：

```python
from ziniao_webdriver.js_patches import derive_profile_fingerprint, build_stealth_js

fp = derive_profile_fingerprint("ziniao:my-store")
# fp["canvas_seed"], fp["audio_seed"], fp["webgl_vendor"], fp["webgl_renderer"]

script = build_stealth_js(profile_seed="ziniao:my-store", webgl_vendor=True)
```

### 补丁粒度控制

`build_stealth_js()` 支持按需开关每个补丁：

```python
from ziniao_mcp.stealth.js_patches import build_stealth_js

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

## 脚本版本

| 版本 | 变量名 | 包含的补丁 | 用途 |
|---|---|---|---|
| 完整版 | `STEALTH_JS` | 全部 12 个（webgl_vendor 除外） | CDP 连接后注入 |
| 精简版 | `STEALTH_JS_MINIMAL` | toString 保护 + webdriver + permissions + chrome 补全 + 清理 | 紫鸟客户端预注入 |

精简版省略了依赖 DOM 的补丁（plugins、iframe）和指纹类补丁（canvas、audio、webrtc），因为注入时机早于页面加载，这些 API 可能尚不可用。

---

## 文件结构

```
ziniao_mcp/stealth/
├── __init__.py          # 模块入口，StealthConfig 配置类，apply_stealth 注入函数
├── js_patches.py        # 12 个 JS 补丁常量，build_stealth_js 拼接函数
└── human_behavior.py    # 6 个拟人化操作函数 + BehaviorConfig 配置类
```

### js_patches.py

| 常量 | 行数 | 默认状态 |
|---|---|---|
| `PATCH_NATIVE_TOSTRING` | ~25 行 | 开启 |
| `PATCH_NAVIGATOR_WEBDRIVER` | ~5 行 | 开启 |
| `PATCH_NAVIGATOR_PLUGINS` | ~65 行 | 开启 |
| `PATCH_NAVIGATOR_PERMISSIONS` | ~18 行 | 开启 |
| `PATCH_WINDOW_CHROME` | ~70 行 | 开启 |
| `PATCH_IFRAME_WEBDRIVER` | ~40 行 | 开启 |
| `PATCH_WEBGL_VENDOR` | ~40 行 | **关闭** |
| `PATCH_CANVAS_FINGERPRINT` | ~55 行 | 开启 |
| `PATCH_AUDIO_FINGERPRINT` | ~20 行 | 开启 |
| `PATCH_WEBRTC_LEAK` | ~25 行 | 开启 |
| `PATCH_AUTOMATION_FLAGS` | ~25 行 | 开启 |
| `PATCH_STEALTH_CLEANUP` | ~10 行 | 开启 |

辅助函数：

| 名称 | 说明 |
|---|---|
| `derive_profile_fingerprint(profile_seed)` | 对任意字符串 seed 做 BLAKE2b 派生，返回 `{canvas_seed, audio_seed, webgl_vendor, webgl_renderer}` |
| `_WEBGL_POOL` | 9 条 Windows + Chrome + ANGLE 的真实硬件组合（Intel / NVIDIA / AMD） |
| `_build_seed_injection(fp)` | 构造把派生值挂到 window 的 JS 注入段，CLEANUP 负责删除 |

### human_behavior.py

| 函数 | 说明 |
|---|---|
| `random_delay(min_ms, max_ms)` | 正态分布随机等待 |
| `human_click(tab, selector)` | 贝塞尔曲线移动 + 随机偏移点击 |
| `human_type(tab, text, selector)` | 逐字输入，随机间隔，偶尔长停顿 |
| `human_fill(tab, selector, value)` | 点击 → 全选 → 清除 → 逐字输入 |
| `human_hover(tab, selector)` | 贝塞尔曲线移动到元素上 |
| `human_scroll(tab, direction, distance)` | 分段随机滚动 |

---

## 三层防护覆盖矩阵

| 检测维度 | 第一层 (nodriver) | 第二层 (JS 伪装) | 第三层 (行为模拟) |
|---|:---:|:---:|:---:|
| WebDriver 协议痕迹 (`$cdc_`, webdriver) | **消除** | 兜底覆盖 | — |
| 自动化全局变量 (`__playwright`, `__pw_`) | **不产生** | — | — |
| `navigator.plugins` 空数组 | — | **伪造** | — |
| `navigator.permissions` 异常 | — | **修正** | — |
| `window.chrome` 缺失 | — | **补全** | — |
| iframe `navigator.webdriver` | — | **持续修补** | — |
| Canvas 指纹 | — | **噪声注入** | — |
| AudioContext 指纹 | — | **噪声注入** | — |
| WebRTC IP 泄露 | — | **relay 策略** | — |
| WebGL 硬件指纹 | — | 可选伪造 | — |
| `Function.prototype.toString` 泄露 | — | **WeakMap 保护** | — |
| 鼠标轨迹规律性 | — | — | **贝塞尔曲线** |
| 点击位置过于精确 | — | — | **随机偏移** |
| 输入速度恒定 | — | — | **随机节奏** |
| 操作间无延迟 | — | — | **正态分布延迟** |
| 滚动一步到位 | — | — | **分段滚动** |

## 已知限制

以下检测维度当前**不在** ziniao-mcp 的覆盖范围内，由紫鸟浏览器客户端或运行环境负责：

| 检测维度 | 说明 | 责任方 |
|---|---|---|
| 浏览器启动参数 | `--disable-blink-features` 等参数 | 紫鸟客户端 |
| 代理/IP | 店铺级代理和 IP 轮换 | 紫鸟客户端 |
| User-Agent | 通过 MCP `emulate` 工具覆盖 | MCP tools |
| 字体指纹 | 依赖操作系统字体库 | 紫鸟客户端 / OS |
| TLS 指纹 (JA3/JA4) | 取决于 Chromium 版本和编译配置 | Chromium |
| HTTP/2 指纹 | 取决于网络栈配置 | Chromium |
| Screen 属性一致性 | `outerWidth/Height` 等与窗口尺寸匹配 | 紫鸟客户端 |

与上表互补：**Chromium 安全边界**（`Event.isTrusted`、用户激活与 `Runtime.evaluate` 的 `userGesture`、自动填充语义、权限/WebAuthn/支付等）与「纯 CDP 能否等价真人」的预期管理，见 [chrome-security-boundaries-automation.md](./chrome-security-boundaries-automation.md)。

---

## TODO / 后续立项

BrowserLeaks 复测留下以下增强项，均**超出 bug 修复范围**，待独立立项评估：

### 1. 硬件参数可配置 (`navigator.hardwareConcurrency` / `deviceMemory`)

当前 `PATCH_AUTOMATION_FLAGS` 仅在 `< 2` 时兜底覆盖（`hardwareConcurrency → 4`、`deviceMemory → 8`），实际测试中这两项通常暴露真实值（例如某台机器返回 12 核 / 32 GB）。当启用稳定 WebGL 硬件池伪装成「Intel UHD 集显」这类档次时，物理 CPU/内存参数应配套下调才不至于自相矛盾。

- 需求：`StealthConfig` 暴露 `hardware_concurrency: int | None` 和 `device_memory: int | None`，为 None 时沿用当前"仅兜底"策略，指定时无条件覆盖。
- 还可基于 `_WEBGL_POOL` 的档次派生默认：集显档 → 4/8 GB，独显档 → 8/16 GB，RTX 高端档 → 12/32 GB。

### 2. 网络与协议栈层指纹（JS 注入无法覆盖）

BrowserLeaks 的以下维度属于网络/协议层，**JS 补丁永远无法修饰**，需靠代理链 / Chromium 分支（例如 undetected-chromedriver 的 TLS patch 分支、jschon 等 JA3 改写工具、或自编译打 patch 的 Chromium）：

| 维度 | 检测依据 | 可能方案 |
|---|---|---|
| **TLS / JA3 / JA4** | ClientHello 密码套件与扩展顺序 | 专用 Chromium 编译 / 代理侧 TLS 重协商（如 gost、oxy-proxy） |
| **HTTP/2 指纹** | SETTINGS、HEADERS 顺序、WINDOW_UPDATE | Chromium 网络栈 patch |
| **QUIC 指纹** | 握手包、congestion control 参数 | 通常禁用 QUIC：`--disable-quic` |
| **TCP/IP** | TTL、Window Size、MSS、TCP Options | 操作系统/代理侧 TCP stack 调整 |
| **DNS Leak** | 绕过代理的 DNS 请求 | 代理端强制 DNS over SOCKS/HTTPS |
| **IP / Headers** | 出口 IP 地理、客户端 Headers 顺序 | 店铺级代理 + UA 协同 |

> ziniao-mcp 定位是"页面内反检测"；网络层请交由 Chromium 发行版或代理链解决。本项目不会在 `ziniao_webdriver` 里引入 TLS patch 之类的侵入式改动。

### 3. WebGL 硬件池扩展

当前 `_WEBGL_POOL` 只有 9 条 Windows + D3D11 条目，后续可视使用场景增补：

- macOS：`ANGLE (Apple, Apple M1 Pro, OpenGL 4.1)` 等 Metal 管线
- Linux：`Mesa DRI Intel(R) ...` / `NVIDIA 535.xx ...`
- 移动端 Chrome：`Qualcomm Adreno ...`

并补单元测试校验各条 renderer 字符串格式与当前 ANGLE 输出一致（使用 Chrome Platform Status 的 GPU 分布做权重）。

---

## 测试

```bash
uv run pytest tests/test_stealth.py -v
```

测试覆盖：

- JS 脚本构建（12 个补丁的开关组合、默认/精简版本对比）
- StealthConfig 配置解析（默认值、字典初始化、None 处理）
- apply_stealth 注入（多 tab 注入、异常处理、禁用跳过）
- 贝塞尔曲线生成（点数、起终点、类型）
- 拟人化操作（点击、输入、填写、悬停、滚动）
- SessionManager 集成（配置传递、注入调用）
