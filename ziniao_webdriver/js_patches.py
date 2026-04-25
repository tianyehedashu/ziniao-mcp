"""JavaScript 环境伪装脚本集合。

通过 CDP Page.addScriptToEvaluateOnNewDocument 在页面加载前注入，
覆盖可能暴露的自动化痕迹。

nodriver 原生不产生 __playwright*/__pw_* 全局变量，也不设置 navigator.webdriver，
因此相比 Playwright 时代精简了 PATCH_PLAYWRIGHT_GLOBALS。但仍主动覆盖
navigator.webdriver，并保留 console 序列化防护作为 CDP 连接场景的安全兜底。

补丁注入顺序：
- PATCH_NATIVE_TOSTRING 必须最先注入，为后续所有被覆盖函数建立 toString 保护
- PATCH_SEED_INJECTION 紧随其后（若有 profile_seed），为 Canvas/Audio/WebGL 提供稳定种子
- PATCH_STEALTH_CLEANUP 必须最后注入，清除临时辅助属性
"""

from __future__ import annotations

import hashlib
import json

# ---------------------------------------------------------------------------
# 基础设施 — 必须第一个注入
# ---------------------------------------------------------------------------

PATCH_NATIVE_TOSTRING = """
(() => {
    // 幂等 flag：build_stealth_js 外层 guard 依赖此标记，
    // 保证同一 realm 多次注册/evaluate 脚本时只完整执行一次。
    Object.defineProperty(window, '__stealth_applied__', {
        value: true, configurable: true, writable: false, enumerable: false,
    });

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
# Console 序列化防护
# ---------------------------------------------------------------------------

PATCH_CONSOLE_DEBUG_TRAP = """
(() => {
    if (!window.console) return;
    const methods = ['debug', 'log', 'info', 'warn', 'error', 'dir', 'table'];

    const sanitizeArg = (arg) => {
        try {
            if (!arg || typeof arg !== 'object') return arg;
            const ownStack = Object.getOwnPropertyDescriptor(arg, 'stack');
            if (ownStack && typeof ownStack.get === 'function') {
                return { name: 'Error', message: '', stack: '' };
            }
            if (arg instanceof Error) {
                return { name: arg.name || 'Error', message: arg.message || '' };
            }
        } catch(e) {
            return '[console-arg]';
        }
        return arg;
    };

    for (const method of methods) {
        const orig = console[method];
        if (typeof orig !== 'function') continue;
        const wrapped = function(...args) {
            return orig.apply(this, args.map(sanitizeArg));
        };
        try {
            Object.defineProperty(console, method, {
                configurable: true,
                writable: true,
                value: wrapped,
            });
            if (window.__stealth_native) {
                window.__stealth_native(wrapped, method);
            }
        } catch(e) {}
    }
})();
"""

# ---------------------------------------------------------------------------
# Navigator 系列
# ---------------------------------------------------------------------------

PATCH_NAVIGATOR_WEBDRIVER = """
(() => {
    if (navigator.webdriver !== false) {
        const getWebdriver = function() { return false; };
        if (window.__stealth_native) {
            window.__stealth_native(getWebdriver, 'get webdriver');
        }
        Object.defineProperty(navigator, 'webdriver', {
            get: getWebdriver,
            configurable: true,
        });
    }
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
        const getPlugins = function() { return fakePlugins; };
        if (window.__stealth_native) {
            window.__stealth_native(getPlugins, 'get plugins');
        }
        Object.defineProperty(navigator, 'plugins', {
            get: getPlugins,
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
    const mark = (fn, name) => {
        if (fn && window.__stealth_native) {
            try { window.__stealth_native(fn, name); } catch (e) {}
        }
        return fn;
    };

    if (!window.chrome) window.chrome = {};

    if (!window.chrome.app) {
        const app = {
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
            getDetails: mark(function getDetails() { return null; }, 'getDetails'),
            getIsInstalled: mark(function getIsInstalled() { return false; }, 'getIsInstalled'),
            installState: mark(function installState(cb) { if (cb) cb('not_installed'); }, 'installState'),
            isInstalled: false,
        };
        window.chrome.app = app;
    }

})();
"""

# ---------------------------------------------------------------------------
# iframe webdriver 修补
# ---------------------------------------------------------------------------

PATCH_IFRAME_WEBDRIVER = """
(() => {
    const iframeGetWebdriver = function() { return false; };
    if (window.__stealth_native) {
        window.__stealth_native(iframeGetWebdriver, 'get webdriver');
    }

    const contentWindowDesc = Object.getOwnPropertyDescriptor(
        HTMLIFrameElement.prototype, 'contentWindow'
    );
    const getContentWindow = function() {
        const win = contentWindowDesc.get.call(this);
        try {
            if (win && win.navigator && win.navigator.webdriver !== false) {
                Object.defineProperty(win.navigator, 'webdriver', {
                    get: iframeGetWebdriver,
                    configurable: true,
                });
            }
        } catch(e) {}
        return win;
    };
    if (window.__stealth_native) {
        window.__stealth_native(getContentWindow, 'get contentWindow');
    }

    function patchIframe(iframe) {
        try {
            if (iframe.contentWindow && iframe.contentWindow.navigator &&
                iframe.contentWindow.navigator.webdriver !== false) {
                Object.defineProperty(iframe.contentWindow.navigator, 'webdriver', {
                    get: iframeGetWebdriver,
                    configurable: true,
                });
            }
        } catch(e) {}
    }

    function observeIframe(iframe) {
        iframe.addEventListener('load', () => patchIframe(iframe));
    }

    function prepareIframe(iframe) {
        observeIframe(iframe);
        patchIframe(iframe);
        try {
            if (contentWindowDesc && contentWindowDesc.get &&
                !iframe.__stealth_iframe_contentWindow__) {
                Object.defineProperty(iframe, '__stealth_iframe_contentWindow__', {
                    value: true, configurable: true, enumerable: false,
                });
                Object.defineProperty(iframe, 'contentWindow', {
                    configurable: true,
                    get: getContentWindow,
                });
            }
        } catch(e) {}
    }

    const origCreateElement = Document.prototype.createElement;
    Document.prototype.createElement = function(...args) {
        const el = origCreateElement.apply(this, args);
        try {
            if (String(args[0]).toLowerCase() === 'iframe') {
                prepareIframe(el);
            }
        } catch(e) {}
        return el;
    };
    if (window.__stealth_native) {
        window.__stealth_native(Document.prototype.createElement, 'createElement');
    }

    document.querySelectorAll('iframe').forEach(f => {
        prepareIframe(f);
    });

    const observer = new MutationObserver(mutations => {
        for (const m of mutations) {
            for (const node of m.addedNodes) {
                if (node.tagName === 'IFRAME') {
                    prepareIframe(node);
                } else if (node.querySelectorAll) {
                    node.querySelectorAll('iframe').forEach(f => {
                        prepareIframe(f);
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
# 用户活动与焦点信号
# ---------------------------------------------------------------------------

PATCH_USER_ACTIVITY = """
(() => {
    let activeUntil = Date.now() + 45000;
    const markActive = () => { activeUntil = Date.now() + 45000; };
    const isActive = () => Date.now() < activeUntil;
    const getHasBeenActive = function() { return true; };
    const getIsActive = function() { return isActive(); };
    const getUserActivation = function() {
        return { hasBeenActive: true, isActive: isActive() };
    };
    if (window.__stealth_native) {
        window.__stealth_native(getHasBeenActive, 'get hasBeenActive');
        window.__stealth_native(getIsActive, 'get isActive');
        window.__stealth_native(getUserActivation, 'get userActivation');
    }

    [
        'pointerdown', 'pointermove', 'mousedown', 'mouseup', 'click',
        'keydown', 'touchstart', 'wheel',
    ].forEach(type => {
        try {
            window.addEventListener(type, markActive, { capture: true, passive: true });
        } catch(e) {}
    });

    if (typeof document.hasFocus === 'function') {
        document.hasFocus = function hasFocus() { return true; };
        if (window.__stealth_native) {
            window.__stealth_native(document.hasFocus, 'hasFocus');
        }
    }

    const defineActivation = (obj) => {
        if (!obj) return false;
        let ok = false;
        try {
            Object.defineProperty(obj, 'hasBeenActive', {
                get: getHasBeenActive,
                configurable: true,
            });
            ok = true;
        } catch(e) {}
        try {
            Object.defineProperty(obj, 'isActive', {
                get: getIsActive,
                configurable: true,
            });
            ok = true;
        } catch(e) {}
        return ok;
    };

    if (!defineActivation(navigator.userActivation)) {
        try {
            Object.defineProperty(navigator, 'userActivation', {
                get: getUserActivation,
                configurable: true,
            });
        } catch(e) {}
    }
})();
"""

# ---------------------------------------------------------------------------
# WebGL 指纹伪造
# ---------------------------------------------------------------------------

PATCH_WEBGL_VENDOR = """
(() => {
    // vendor/renderer 默认走 Intel 占位；若 PATCH_SEED_INJECTION 已按 profile
    // 种子赋值到 window.__STEALTH_WEBGL_VENDOR__ / __STEALTH_WEBGL_RENDERER__，
    // 则读取之以得到贴近真实硬件分布的组合（见 _WEBGL_POOL）。
    const SEED_VENDOR = (typeof window.__STEALTH_WEBGL_VENDOR__ === 'string')
        ? window.__STEALTH_WEBGL_VENDOR__ : 'Intel Inc.';
    const SEED_RENDERER = (typeof window.__STEALTH_WEBGL_RENDERER__ === 'string')
        ? window.__STEALTH_WEBGL_RENDERER__ : 'Intel Iris OpenGL Engine';

    const getParameterProto = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(param) {
        const UNMASKED_VENDOR  = 0x9245;
        const UNMASKED_RENDERER = 0x9246;
        if (param === UNMASKED_VENDOR)  return SEED_VENDOR;
        if (param === UNMASKED_RENDERER) return SEED_RENDERER;
        return getParameterProto.call(this, param);
    };

    if (typeof WebGL2RenderingContext !== 'undefined') {
        const getParameterProto2 = WebGL2RenderingContext.prototype.getParameter;
        WebGL2RenderingContext.prototype.getParameter = function(param) {
            const UNMASKED_VENDOR  = 0x9245;
            const UNMASKED_RENDERER = 0x9246;
            if (param === UNMASKED_VENDOR)  return SEED_VENDOR;
            if (param === UNMASKED_RENDERER) return SEED_RENDERER;
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

    // 优先读取 PATCH_SEED_INJECTION 注入的稳定种子（基于 profile 派生），
    // 缺省回退到页面会话级随机：单 IIFE 内 seed 一致，跨刷新不同。
    const seed = (typeof window.__STEALTH_SEED_CANVAS__ === 'number')
        ? (window.__STEALTH_SEED_CANVAS__ & 0xFF)
        : Math.floor(Math.random() * 256);

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
    const seed = (typeof window.__STEALTH_SEED_AUDIO__ === 'number')
        ? (window.__STEALTH_SEED_AUDIO__ & 0xFFFF)
        : Math.floor(Math.random() * 10000);

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

    // 用 Proxy 透明地改写 config.iceTransportPolicy=relay，
    // 同时保留原型链、name、length 等元信息。
    const handler = {
        construct(target, args, newTarget) {
            const config = Object.assign({}, args[0] || {});
            config.iceTransportPolicy = 'relay';
            if (!Array.isArray(config.iceServers)) config.iceServers = [];
            const newArgs = [config, ...args.slice(1)];
            return Reflect.construct(target, newArgs, newTarget);
        },
        get(target, prop, receiver) {
            // 确保 PatchedRTC.name / .prototype / .length 都透传到原构造器。
            return Reflect.get(target, prop, receiver);
        },
    };

    const PatchedRTC = new Proxy(OrigRTC, handler);

    // 兜底：即便 Proxy 的 toString 通过 Function.prototype.toString 走到 target，
    // 仍显式登记为 native，避免某些实现里 Proxy 显示异常。
    if (window.__stealth_native) {
        try {
            window.__stealth_native(PatchedRTC, OrigRTC.name || 'RTCPeerConnection');
        } catch (e) {}
    }

    if (window.RTCPeerConnection) {
        window.RTCPeerConnection = PatchedRTC;
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
        const getLanguages = function() { return ['en-US', 'en']; };
        if (window.__stealth_native) {
            window.__stealth_native(getLanguages, 'get languages');
        }
        Object.defineProperty(navigator, 'languages', {
            get: getLanguages,
            configurable: true,
        });
    }

    const origHWC = navigator.hardwareConcurrency;
    if (!origHWC || origHWC < 2) {
        const getHardwareConcurrency = function() { return 4; };
        if (window.__stealth_native) {
            window.__stealth_native(
                getHardwareConcurrency, 'get hardwareConcurrency'
            );
        }
        Object.defineProperty(navigator, 'hardwareConcurrency', {
            get: getHardwareConcurrency,
            configurable: false,
        });
    }

    const origMem = navigator.deviceMemory;
    if (!origMem || origMem < 2) {
        const getDeviceMemory = function() { return 8; };
        if (window.__stealth_native) {
            window.__stealth_native(getDeviceMemory, 'get deviceMemory');
        }
        Object.defineProperty(navigator, 'deviceMemory', {
            get: getDeviceMemory,
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


# 当启用 profile_seed 时追加：额外清理注入的 SEED 全局，避免残留痕迹。
# 与 PATCH_STEALTH_CLEANUP 分离，以便无 seed 时输出里不出现相关字面量。
_PATCH_SEED_CLEANUP = """
(() => {
    const gone = [
        '__STEALTH_SEED_CANVAS__',
        '__STEALTH_SEED_AUDIO__',
        '__STEALTH_WEBGL_VENDOR__',
        '__STEALTH_WEBGL_RENDERER__',
    ];
    for (const k of gone) {
        try { delete window[k]; } catch (e) {
            try {
                Object.defineProperty(window, k, {
                    value: undefined, configurable: true, writable: true,
                });
            } catch (e2) {}
        }
    }
})();
"""


# ---------------------------------------------------------------------------
# Profile 稳定种子池 — 基于 profile_seed 派生贴近真实硬件分布的组合
# ---------------------------------------------------------------------------
#
# 真实 Windows + Chrome + ANGLE 的 UNMASKED_VENDOR / UNMASKED_RENDERER 样本。
# 覆盖 Intel 集显、NVIDIA 独显、AMD 独显三大家族常见型号；分布接近 Steam
# 硬件普查与 Chrome Platform Status 的 GPU 装机率，避免出现一看就是 stealth
# 占位的 "Intel Inc. / Intel Iris OpenGL Engine" 这类非典型组合。

_WEBGL_POOL: tuple[tuple[str, str], ...] = (
    ("Google Inc. (Intel)",
     "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (Intel)",
     "ANGLE (Intel, Intel(R) UHD Graphics 730 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (Intel)",
     "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (NVIDIA)",
     "ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (NVIDIA)",
     "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 Ti Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (NVIDIA)",
     "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (NVIDIA)",
     "ANGLE (NVIDIA, NVIDIA GeForce RTX 4060 Laptop GPU Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (AMD)",
     "ANGLE (AMD, AMD Radeon(TM) Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (AMD)",
     "ANGLE (AMD, Radeon RX 580 Series Direct3D11 vs_5_0 ps_5_0, D3D11)"),
)


def derive_profile_fingerprint(profile_seed: str | None) -> dict[str, object]:
    """基于 *profile_seed* 稳定派生 Canvas/Audio/WebGL 指纹参数。

    *profile_seed* 为 None 或空串时返回全 None，表示不启用稳定种子；
    JS 侧会回退到原有 ``Math.random()`` 逻辑与默认 Intel 占位。

    使用 BLAKE2b 将任意字符串映射为 16 字节摘要，各字段互不相关：
    - bytes[0]      → canvas_seed  (0..255)
    - bytes[1:3]    → audio_seed   (0..65535)
    - bytes[3]      → webgl_idx    (mod len(_WEBGL_POOL))

    seed 越稳定越贴近"真实用户固定指纹"的行为，代价是失去反追踪能力；
    调用方应保证同一物理机/profile 只传一个稳定 key。
    """
    if not profile_seed:
        return {
            "canvas_seed": None,
            "audio_seed": None,
            "webgl_vendor": None,
            "webgl_renderer": None,
        }

    digest = hashlib.blake2b(
        profile_seed.encode("utf-8"), digest_size=16
    ).digest()
    canvas_seed = digest[0]
    audio_seed = int.from_bytes(digest[1:3], "big")
    gpu_idx = digest[3] % len(_WEBGL_POOL)
    vendor, renderer = _WEBGL_POOL[gpu_idx]
    return {
        "canvas_seed": canvas_seed,
        "audio_seed": audio_seed,
        "webgl_vendor": vendor,
        "webgl_renderer": renderer,
    }


def _build_seed_injection(fp: dict[str, object]) -> str:
    """构造 seed 注入 JS 片段：把派生值以非枚举属性挂到 window。

    放置在 PATCH_NATIVE_TOSTRING 之后、其他补丁之前；CLEANUP 负责收尾删除。
    全 None 时返回空串（等价于不启用稳定种子，补丁走随机回退分支）。
    """
    has_any = any(v is not None for v in fp.values())
    if not has_any:
        return ""

    def _js_define(name: str, value: object) -> str:
        if value is None:
            return ""
        return (
            "    Object.defineProperty(window, "
            f"{json.dumps(name)}, {{ value: {json.dumps(value)}, "
            "configurable: true, writable: false, enumerable: false });"
        )

    lines = [
        _js_define("__STEALTH_SEED_CANVAS__", fp.get("canvas_seed")),
        _js_define("__STEALTH_SEED_AUDIO__", fp.get("audio_seed")),
        _js_define("__STEALTH_WEBGL_VENDOR__", fp.get("webgl_vendor")),
        _js_define("__STEALTH_WEBGL_RENDERER__", fp.get("webgl_renderer")),
    ]
    body = "\n".join(ln for ln in lines if ln)
    return "(() => {\n" + body + "\n})();\n"


# ---------------------------------------------------------------------------
# 构建函数
# ---------------------------------------------------------------------------

_IDEMPOTENT_GUARD_PREFIX = """
// Stealth 整体幂等 guard：多次 addScript 注册或重复 evaluate 时，
// 跳过第二次及之后的执行，避免 permissions/canvas/webrtc 等补丁被双层包装。
// 真实幂等判定在 PATCH_NATIVE_TOSTRING 内设置 window.__stealth_applied__。
if (!window.__stealth_applied__) {
"""

_IDEMPOTENT_GUARD_SUFFIX = """
}
"""


def build_stealth_js(
    *,
    native_tostring: bool = True,
    console_debug_trap: bool = True,
    webdriver: bool = True,
    plugins: bool = True,
    permissions: bool = True,
    chrome_obj: bool = True,
    iframe_webdriver: bool = True,
    user_activity: bool = True,
    webgl_vendor: bool = False,
    canvas_fingerprint: bool = False,
    audio_fingerprint: bool = False,
    webrtc_leak: bool = True,
    automation_flags: bool = True,
    profile_seed: str | None = None,
) -> str:
    """按需拼接反检测 JS 脚本。

    注入顺序有约束：native_tostring 必须在最前，seed 注入紧随其后，cleanup 在最后。
    webgl_vendor 默认关闭，因为紫鸟浏览器通常自行处理 WebGL 指纹。

    *profile_seed* 非空时从 ``_WEBGL_POOL`` 派生稳定的 Canvas/Audio/WebGL 参数
    （见 ``derive_profile_fingerprint``）：同一 profile 多次打开指纹稳定、
    不同 profile 互不相同。Canvas/Audio 默认不改写，避免复用真实
    profile 时与站点已记录的历史设备指纹不一致；需要反追踪时再显式开启。

    输出脚本整体带幂等 guard：多次 addScript 注册（每新 tab 都要重注册）
    或重复 evaluate 时，只有第一次完整执行，避免双重包装与 WeakMap 重置。
    """
    parts: list[str] = []

    if native_tostring:
        parts.append(PATCH_NATIVE_TOSTRING)
    if console_debug_trap:
        parts.append(PATCH_CONSOLE_DEBUG_TRAP)

    seed_js = _build_seed_injection(derive_profile_fingerprint(profile_seed))
    if seed_js:
        parts.append(seed_js)

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
    if user_activity:
        parts.append(PATCH_USER_ACTIVITY)
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
        if seed_js:
            parts.append(_PATCH_SEED_CLEANUP)

    inner = "\n".join(parts)
    if not inner.strip():
        return ""
    return _IDEMPOTENT_GUARD_PREFIX + inner + _IDEMPOTENT_GUARD_SUFFIX


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
