"""JavaScript 环境伪装脚本集合。

通过 page.add_init_script() 或 context.add_init_script() 在页面加载前注入，
覆盖 CDP/Playwright 暴露的自动化痕迹。
"""

PATCH_NAVIGATOR_WEBDRIVER = """
(() => {
    try {
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
            configurable: false,
        });
    } catch(e) {}
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
            configurable: false,
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
})();
"""

PATCH_WINDOW_CHROME = """
(() => {
    if (!window.chrome) window.chrome = {};
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
})();
"""

PATCH_PLAYWRIGHT_GLOBALS = """
(() => {
    const propsToDelete = [];
    for (const key of Object.getOwnPropertyNames(window)) {
        if (key.startsWith('__playwright') || key.startsWith('__pw_')) {
            propsToDelete.push(key);
        }
    }
    for (const key of propsToDelete) {
        try { delete window[key]; } catch(e) {}
    }
})();
"""

PATCH_CONSOLE_DEBUG_TRAP = """
(() => {
    const _origDebug = console.debug;
    console.debug = function(...args) {
        if (args.length === 1 && typeof args[0] === 'string' &&
            (args[0].includes('CDP') || args[0].includes('DevTools'))) {
            return;
        }
        return _origDebug.apply(console, args);
    };
})();
"""

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
})();
"""

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


def build_stealth_js(
    *,
    webdriver: bool = True,
    plugins: bool = True,
    permissions: bool = True,
    chrome_obj: bool = True,
    playwright_globals: bool = True,
    console_debug: bool = True,
    iframe_webdriver: bool = True,
    webgl_vendor: bool = False,
    automation_flags: bool = True,
) -> str:
    """按需拼接反检测 JS 脚本。

    webgl_vendor 默认关闭，因为紫鸟浏览器通常自行处理 WebGL 指纹。
    """
    parts: list[str] = []
    if webdriver:
        parts.append(PATCH_NAVIGATOR_WEBDRIVER)
    if plugins:
        parts.append(PATCH_NAVIGATOR_PLUGINS)
    if permissions:
        parts.append(PATCH_NAVIGATOR_PERMISSIONS)
    if chrome_obj:
        parts.append(PATCH_WINDOW_CHROME)
    if playwright_globals:
        parts.append(PATCH_PLAYWRIGHT_GLOBALS)
    if console_debug:
        parts.append(PATCH_CONSOLE_DEBUG_TRAP)
    if iframe_webdriver:
        parts.append(PATCH_IFRAME_WEBDRIVER)
    if webgl_vendor:
        parts.append(PATCH_WEBGL_VENDOR)
    if automation_flags:
        parts.append(PATCH_AUTOMATION_FLAGS)
    return "\n".join(parts)


STEALTH_JS = build_stealth_js()

STEALTH_JS_MINIMAL = build_stealth_js(
    plugins=False,
    console_debug=False,
    iframe_webdriver=False,
    automation_flags=False,
)
