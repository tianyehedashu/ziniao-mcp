"""
紫鸟客户端通信模块

封装与紫鸟客户端的 HTTP 通信，支持启动客户端、打开/关闭店铺、获取 CDP 调试端口。
参考: https://open.ziniao.com/docSupport?docId=98
"""

from .client import ZiniaoClient

__all__ = ["ZiniaoClient"]
