"""``import ziniao`` 与 ``ziniao_webdriver`` 公开 API 对齐。"""

import ziniao
import ziniao_webdriver


def test_ziniao_reexports_webdriver_public_api():
    for name in ziniao_webdriver.__all__:
        assert getattr(ziniao, name) is getattr(ziniao_webdriver, name)
    assert isinstance(ziniao.__version__, str)
    assert ziniao.__all__ == list(ziniao_webdriver.__all__) + ["__version__"]
