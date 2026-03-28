"""Re-export shim — 实际实现已迁移至 ziniao_webdriver.js_patches。

保留本模块以兼容已有的 ``from ziniao_mcp.stealth.js_patches import ...`` 用法。
"""

# 纯 re-export，符号供外部 import 使用。
# pylint: disable=unused-import
from ziniao_webdriver.js_patches import (  # noqa: F401
    PATCH_AUDIO_FINGERPRINT,
    PATCH_AUTOMATION_FLAGS,
    PATCH_CANVAS_FINGERPRINT,
    PATCH_IFRAME_WEBDRIVER,
    PATCH_NATIVE_TOSTRING,
    PATCH_NAVIGATOR_PERMISSIONS,
    PATCH_NAVIGATOR_PLUGINS,
    PATCH_NAVIGATOR_WEBDRIVER,
    PATCH_STEALTH_CLEANUP,
    PATCH_WEBGL_VENDOR,
    PATCH_WEBRTC_LEAK,
    PATCH_WINDOW_CHROME,
    STEALTH_JS,
    STEALTH_JS_MINIMAL,
    build_stealth_js,
)
