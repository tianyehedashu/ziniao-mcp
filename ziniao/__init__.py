"""与 PyPI 发行名一致的 Python 包（``pip install ziniao`` → ``import ziniao``）。

紫鸟 HTTP 客户端等符号与 ``ziniao_webdriver`` 等价；公开名以 ``ziniao_webdriver.__all__`` 为准自动转发，避免双处维护漂移。
"""

from importlib.metadata import PackageNotFoundError, version as _dist_version

import ziniao_webdriver as _zw

globals().update({name: getattr(_zw, name) for name in _zw.__all__})

try:
    __version__ = _dist_version("ziniao")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = list(_zw.__all__) + ["__version__"]
del _zw
