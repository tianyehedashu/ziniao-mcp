"""JavaScript 环境伪装脚本集合。

通过 CDP Page.addScriptToEvaluateOnNewDocument 在页面加载前注入，
覆盖可能暴露的自动化痕迹。

nodriver 原生不产生 __playwright*/__pw_* 全局变量，也不设置 navigator.webdriver，
因此相比 Playwright 时代精简了 PATCH_PLAYWRIGHT_GLOBALS 和 PATCH_CONSOLE_DEBUG_TRAP
两个补丁。但仍主动覆盖 navigator.webdriver 作为安全兜底。

补丁注入顺序：
- PATCH_NATIVE_TOSTRING 必须最先注入，为后续所有被覆盖函数建立 toString 保护
- PATCH_STEALTH_CLEANUP 必须最后注入，清除临时辅助属性
"""

# ---------------------------------------------------------------------------
# 基础设施 — 必须第一个注入
# ---------------------------------------------------------------------------

PATCH_NATIVE_TOSTRING = """
(() => {
    const _origToString = Function.prototype.toString;
    const _overrides = new WeakMap();

    Function.prototype.toString = function() {
        if (_overrides.has(this)) return _overrides.get(this);
        return _origToString.call(this);
    };

    _overrides.set(
        Function.prototype.toString,
        'function toString() { [native code] }'
    );

    Object.defineProperty(window, '__stealth_native', {
        value: function(fn, name) {
            _overrides.set(
                fn,
                'function ' + (name || fn.name || '') + '() { [native code] }'
            );
        },
        configurable: true,
        writable: false,
        enumerable: false,
    });
})();
"""

# ---------------------------------------------------------------------------
# Navigator 系列
# ---------------------------------------------------------------------------

PATCH_NAVIGATOR_WEBDRIVER = """
(() => {
    Object.defineProperty(navigator, 'webdriver', {
        get: () => false,
        configurable: true,
    });
})();
"""

PATCH_NAVIGATOR_PLUGINS = """
(() => {
    function makePluginArray(plugins) {
        const arr = Object.create(PluginArray.prototype);
        const items = [];
        for (let i = 0; i < plugins.length; i++) {
            const p = Object.create(Plugin.prototype);
            Object.defineProperties(p, {
                name:        { value: plugins[i].name, enumerable: true },
                filename:    { value: plugins[i].filename, enumerable: true },
                description: { value: plugins[i].description, enumerable: true },
                length:      { value: plugins[i].mimeTypes.length, enumerable: true },
            });
            for (let j = 0; j < plugins[i].mimeTypes.length; j++) {
                const mt = Object.create(MimeType.prototype);
                Object.defineProperties(mt, {
                    type:        { value: plugins[i].mimeTypes[j].type, enumerable: true },
                    suffixes:    { value: plugins[i].mimeTypes[j].suffixes, enumerable: true },
                    description: { value: plugins[i].mimeTypes[j].description, enumerable: true },
                    enabledPlugin: { value: p, enumerable: true },
                });
                Object.defineProperty(p, j, { value: mt, enumerable: false });
            }
            items.push(p);
            Object.defineProperty(arr, i, { value: p, enumerable: false });
        }
        Object.defineProperty(arr, 'length', { value: items.length, enumerable: true });
        arr.item = function(index) { return items[index] || null; };
        arr.namedItem = function(name) {
            return items.find(p => p.name === name) || null;
        };
        arr.refresh = function() {};
        return arr;
    }

    if (navigator.plugins.length === 0) {
        const pluginData = [
            {
                name: 'Chrome PDF Plugin',
                filename: 'internal-pdf-viewer',
                description: 'Portable Document Format',
                mimeTypes: [{ type: 'application/x-google-chrome-pdf', suffixes: 'pdf',
                              description: 'Portable Document Format' }],
            },
            {
                name: 'Chrome PDF Viewer',
                filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai',
                description: '',
                mimeTypes: [{ type: 'application/pdf', suffixes: 'pdf',
                              description: '' }],
            },
            {
                name: 'Chromium PDF Viewer',
                filename: 'internal-pdf-viewer',
                description: '',
                mimeTypes: [{ type: 'application/pdf', suffixes: 'pdf',
                              description: '' }],
            },
        ];
        const fakePlugins = makePluginArray(pluginData);
        Object.defineProperty(navigator, 'plugins', {
            get: () => fakePlugins,
            configurable: true,
        });
    }
})();
"""

PATCH_NAVIGATOR_PERMISSIONS = """
(() => {
    const originalQuery = navigator.permissions.query.bind(navigator.permissions);
    navigator.permissions.query = async function(desc) {
        if (desc.name === 'notifications') {
            const real = await originalQuery(desc).catch(() => null);
            if (real) return real;
            const fake = Object.create(PermissionStatus.prototype);
            Object.defineProperties(fake, {
                state: { get: () => Notification.permission, enumerable: true },
                onchange: { value: null, writable: true, enumerable: true },
            });
            return fake;
        }
        return originalQuery(desc);
    };
    if (window.__stealth_native) {
        window.__stealth_native(navigator.permissions.query, 'query');
    }
})();
"""

# ---------------------------------------------------------------------------
# window.chrome 补全（含 chrome.app）
# ---------------------------------------------------------------------------

PATCH_WINDOW_CHROME = """
(() => {
    if (!window.chrome) window.chrome = {};

    if (!window.chrome.app) {
        window.chrome.app = {
            InstallState: {
                DISABLED: 'disabled',
                INSTALLED: 'installed',
                NOT_INSTALLED: 'not_installed',
            },
            RunningState: {
                CANNOT_RUN: 'cannot_run',
                READY_TO_RUN: 'ready_to_run',
                RUNNING: 'running',
            },
            getDetails: function() { return null; },
            getIsInstalled: function() { return false; },
            installState: function(cb) { if (cb) cb('not_installed'); },
            isInstalled: false,
        };
    }

    if (!window.chrome.runtime) {
        window.chrome.runtime = {
            connect: function() { return { onMessage: { addListener: function() {} },
                                           postMessage: function() {}, onDisconnect: { addListener: function() {} } }; },
            sendMessage: function(msg, cb) { if (cb) cb(); },
            onMessage: { addListener: function() {}, removeListener: function() {} },
            onConnect: { addListener: function() {} },
            id: undefined,
        };
    }
    if (!window.chrome.loadTimes) {
        window.chrome.loadTimes = function() {
            return {
                commitLoadTime: Date.now() / 1000,
                connectionInfo: 'http/1.1',
                finishDocumentLoadTime: Date.now() / 1000 + 0.1,
                finishLoadTime: Date.now() / 1000 + 0.2,
                firstPaintAfterLoadTime: 0,
                firstPaintTime: Date.now() / 1000 + 0.05,
                navigationType: 'Other',
                npnNegotiatedProtocol: 'unknown',
                requestTime: Date.now() / 1000 - 0.3,
                startLoadTime: Date.now() / 1000 - 0.2,
                wasAlternateProtocolAvailable: false,
                wasFetchedViaSpdy: false,
                wasNpnNegotiated: false,
            };
        };
    }
    if (!window.chrome.csi) {
        window.chrome.csi = function() {
            return {
                onloadT: Date.now(),
                startE: Date.now() - 500,
                pageT: 500 + Math.random() * 100,
                tran: 15,
            };
        };
    }

    if (window.__stealth_native) {
        window.__stealth_native(window.chrome.loadTimes, 'loadTimes');
        window.__stealth_native(window.chrome.csi, 'csi');
        if (window.chrome.app) {
            window.__stealth_native(window.chrome.app.getDetails, 'getDetails');
            window.__stealth_native(window.chrome.app.getIsInstalled, 'getIsInstalled');
            window.__stealth_native(window.chrome.app.installState, 'installState');
        }
    }
})();
"""

# ---------------------------------------------------------------------------
# iframe webdriver 修补
# ---------------------------------------------------------------------------

PATCH_IFRAME_WEBDRIVER = """
(() => {
    function patchIframe(iframe) {
        try {
            if (iframe.contentWindow && iframe.contentWindow.navigator) {
                Object.defineProperty(iframe.contentWindow.navigator, 'webdriver', {
                    get: () => undefined,
                    configurable: false,
                });
            }
        } catch(e) {}
    }

    function observeIframe(iframe) {
        iframe.addEventListener('load', () => patchIframe(iframe));
    }

    document.querySelectorAll('iframe').forEach(f => {
        observeIframe(f);
        patchIframe(f);
    });

    const observer = new MutationObserver(mutations => {
        for (const m of mutations) {
            for (const node of m.addedNodes) {
                if (node.tagName === 'IFRAME') {
                    observeIframe(node);
                    patchIframe(node);
                } else if (node.querySelectorAll) {
                    node.querySelectorAll('iframe').forEach(f => {
                        observeIframe(f);
                        patchIframe(f);
                    });
                }
            }
        }
    });
    observer.observe(document.documentElement || document, {
        childList: true, subtree: true
    });
})();
"""

# ---------------------------------------------------------------------------
# WebGL 指纹伪造
# ---------------------------------------------------------------------------

PATCH_WEBGL_VENDOR = """
(() => {
    const getParameterProto = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(param) {
        const UNMASKED_VENDOR  = 0x9245;
        const UNMASKED_RENDERER = 0x9246;
        if (param === UNMASKED_VENDOR)  return 'Intel Inc.';
        if (param === UNMASKED_RENDERER) return 'Intel Iris OpenGL Engine';
        return getParameterProto.call(this, param);
    };

    if (typeof WebGL2RenderingContext !== 'undefined') {
        const getParameterProto2 = WebGL2RenderingContext.prototype.getParameter;
        WebGL2RenderingContext.prototype.getParameter = function(param) {
            const UNMASKED_VENDOR  = 0x9245;
            const UNMASKED_RENDERER = 0x9246;
            if (param === UNMASKED_VENDOR)  return 'Intel Inc.';
            if (param === UNMASKED_RENDERER) return 'Intel Iris OpenGL Engine';
            return getParameterProto2.call(this, param);
        };
    }

    if (window.__stealth_native) {
        window.__stealth_native(
            WebGLRenderingContext.prototype.getParameter, 'getParameter'
        );
        if (typeof WebGL2RenderingContext !== 'undefined') {
            window.__stealth_native(
                WebGL2RenderingContext.prototype.getParameter, 'getParameter'
            );
        }
    }
})();
"""

# ---------------------------------------------------------------------------
# Canvas 指纹噪声 — 对 toDataURL / toBlob 输出注入微量像素扰动
# ---------------------------------------------------------------------------

PATCH_CANVAS_FINGERPRINT = """
(() => {
    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    const origToBlob = HTMLCanvasElement.prototype.toBlob;
    const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;

    const seed = Math.floor(Math.random() * 256);

    function addNoise(data) {
        for (let i = 0; i < data.length; i += 4) {
            const idx = i / 4;
            if (((idx * 13 + seed) & 0xFF) < 5) {
                const ch = ((idx * 7 + seed) & 0xFF) % 3;
                const delta = (((idx * 11 + seed) & 0xFF) % 2) === 0 ? 1 : -1;
                data[i + ch] = Math.max(0, Math.min(255, data[i + ch] + delta));
            }
        }
    }

    HTMLCanvasElement.prototype.toDataURL = function(...args) {
        try {
            const ctx = this.getContext('2d');
            if (ctx && this.width > 0 && this.height > 0) {
                const imgData = origGetImageData.call(ctx, 0, 0, this.width, this.height);
                addNoise(imgData.data);
                const tmp = document.createElement('canvas');
                tmp.width = this.width; tmp.height = this.height;
                tmp.getContext('2d').putImageData(imgData, 0, 0);
                return origToDataURL.apply(tmp, args);
            }
        } catch(e) {}
        return origToDataURL.apply(this, args);
    };

    HTMLCanvasElement.prototype.toBlob = function(cb, ...rest) {
        try {
            const ctx = this.getContext('2d');
            if (ctx && this.width > 0 && this.height > 0) {
                const imgData = origGetImageData.call(ctx, 0, 0, this.width, this.height);
                addNoise(imgData.data);
                const tmp = document.createElement('canvas');
                tmp.width = this.width; tmp.height = this.height;
                tmp.getContext('2d').putImageData(imgData, 0, 0);
                return origToBlob.call(tmp, cb, ...rest);
            }
        } catch(e) {}
        return origToBlob.call(this, cb, ...rest);
    };

    if (window.__stealth_native) {
        window.__stealth_native(HTMLCanvasElement.prototype.toDataURL, 'toDataURL');
        window.__stealth_native(HTMLCanvasElement.prototype.toBlob, 'toBlob');
    }
})();
"""

# ---------------------------------------------------------------------------
# AudioContext 指纹噪声 — 对 getChannelData 注入微量扰动
# ---------------------------------------------------------------------------

PATCH_AUDIO_FINGERPRINT = """
(() => {
    if (typeof AudioBuffer === 'undefined') return;

    const origGetChannelData = AudioBuffer.prototype.getChannelData;
    const seed = Math.floor(Math.random() * 10000);

    AudioBuffer.prototype.getChannelData = function(channel) {
        const buf = origGetChannelData.call(this, channel);
        for (let i = 0; i < buf.length; i += 100) {
            buf[i] += ((i * 7 + seed + channel) % 10 - 5) * 0.0000001;
        }
        return buf;
    };

    if (window.__stealth_native) {
        window.__stealth_native(AudioBuffer.prototype.getChannelData, 'getChannelData');
    }
})();
"""

# ---------------------------------------------------------------------------
# WebRTC IP 泄露防护 — 强制 relay-only ICE 策略
# ---------------------------------------------------------------------------

PATCH_WEBRTC_LEAK = """
(() => {
    const OrigRTC = window.RTCPeerConnection || window.webkitRTCPeerConnection;
    if (!OrigRTC) return;

    const handler = {
        construct(target, args) {
            const config = Object.assign({}, args[0] || {});
            config.iceTransportPolicy = 'relay';
            if (!config.iceServers) config.iceServers = [];
            args[0] = config;
            return Reflect.construct(target, args);
        },
    };

    const PatchedRTC = new Proxy(OrigRTC, handler);

    if (window.RTCPeerConnection) {
        window.RTCPeerConnection = PatchedRTC;
        if (window.__stealth_native) {
            window.__stealth_native(PatchedRTC, 'RTCPeerConnection');
        }
    }
    if (window.webkitRTCPeerConnection) {
        window.webkitRTCPeerConnection = PatchedRTC;
    }
})();
"""

# ---------------------------------------------------------------------------
# 自动化标志修正
# ---------------------------------------------------------------------------

PATCH_AUTOMATION_FLAGS = """
(() => {
    const origLangs = navigator.languages;
    if (!origLangs || origLangs.length === 0) {
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
            configurable: true,
        });
    }

    const origHWC = navigator.hardwareConcurrency;
    if (!origHWC || origHWC < 2) {
        Object.defineProperty(navigator, 'hardwareConcurrency', {
            get: () => 4,
            configurable: false,
        });
    }

    const origMem = navigator.deviceMemory;
    if (!origMem || origMem < 2) {
        Object.defineProperty(navigator, 'deviceMemory', {
            get: () => 8,
            configurable: false,
        });
    }
})();
"""

# ---------------------------------------------------------------------------
# 清理 — 必须最后一个注入
# ---------------------------------------------------------------------------

PATCH_STEALTH_CLEANUP = """
(() => {
    try { delete window.__stealth_native; } catch(e) {
        Object.defineProperty(window, '__stealth_native', {
            value: undefined, configurable: true, writable: true,
        });
    }
})();
"""


# ---------------------------------------------------------------------------
# 构建函数
# ---------------------------------------------------------------------------

def build_stealth_js(
    *,
    native_tostring: bool = True,
    webdriver: bool = True,
    plugins: bool = True,
    permissions: bool = True,
    chrome_obj: bool = True,
    iframe_webdriver: bool = True,
    webgl_vendor: bool = False,
    canvas_fingerprint: bool = True,
    audio_fingerprint: bool = True,
    webrtc_leak: bool = True,
    automation_flags: bool = True,
) -> str:
    """按需拼接反检测 JS 脚本。

    注入顺序有约束：native_tostring 必须在最前，cleanup 在最后。
    webgl_vendor 默认关闭，因为紫鸟浏览器通常自行处理 WebGL 指纹。
    """
    parts: list[str] = []

    if native_tostring:
        parts.append(PATCH_NATIVE_TOSTRING)

    if webdriver:
        parts.append(PATCH_NAVIGATOR_WEBDRIVER)
    if plugins:
        parts.append(PATCH_NAVIGATOR_PLUGINS)
    if permissions:
        parts.append(PATCH_NAVIGATOR_PERMISSIONS)
    if chrome_obj:
        parts.append(PATCH_WINDOW_CHROME)
    if iframe_webdriver:
        parts.append(PATCH_IFRAME_WEBDRIVER)
    if webgl_vendor:
        parts.append(PATCH_WEBGL_VENDOR)
    if canvas_fingerprint:
        parts.append(PATCH_CANVAS_FINGERPRINT)
    if audio_fingerprint:
        parts.append(PATCH_AUDIO_FINGERPRINT)
    if webrtc_leak:
        parts.append(PATCH_WEBRTC_LEAK)
    if automation_flags:
        parts.append(PATCH_AUTOMATION_FLAGS)

    if native_tostring:
        parts.append(PATCH_STEALTH_CLEANUP)

    return "\n".join(parts)


STEALTH_JS = build_stealth_js()

STEALTH_JS_MINIMAL = build_stealth_js(
    plugins=False,
    iframe_webdriver=False,
    webgl_vendor=False,
    canvas_fingerprint=False,
    audio_fingerprint=False,
    webrtc_leak=False,
    automation_flags=False,
)
