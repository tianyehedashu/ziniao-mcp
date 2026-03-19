"""Allow running the CLI via python -m ziniao_mcp.cli (e.g. when ziniao script is not on PATH)."""

from . import main

if __name__ == "__main__":
    main()
