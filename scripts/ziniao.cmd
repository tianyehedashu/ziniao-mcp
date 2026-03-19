@echo off
rem Wrapper for "ziniao" CLI when the ziniao script is not on PATH.
rem Usage: add this script's directory to PATH, or call: scripts\ziniao.cmd --help
python -c "import sys; sys.argv = ['ziniao'] + sys.argv[1:]; from ziniao_mcp.cli import main; main()" %*
