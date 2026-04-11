[根 CLAUDE](../CLAUDE.md) » **ziniao**

## 职责

与 **PyPI 发行名**一致的顶层包：`pip install ziniao` 后 `import ziniao` 获得与 `ziniao_webdriver` 相同的公开符号，并附带 `__version__`。避免 RPA 脚本维护两套导入。

## 入口与公开 API

- 唯一实现源：`ziniao_webdriver`（见 [ziniao_webdriver/CLAUDE.md](../ziniao_webdriver/CLAUDE.md)）。
- 实现方式：`ziniao/__init__.py` 将 `ziniao_webdriver.__all__` 映射到本包命名空间。

## 依赖关系

- 依赖由根 `pyproject.toml` 的 `[project]` 声明；本目录无独立子项目文件。

## 测试

- 包行为契约见 `tests/test_ziniao_namespace.py` 等。
