"""Test MCP server startup with minimal environment (like Cursor)."""
import subprocess
import os
import sys
import time
import json
import threading

# 项目根目录：脚本所在目录的上一级
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)

INIT_REQUEST = json.dumps({
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test-cursor", "version": "0.1"},
    },
})

# uv：优先环境变量 UV_PATH，否则用 "uv"
_UV = os.environ.get("UV_PATH", "uv")
cmd = [
    _UV,
    "run", "--directory", _PROJECT_ROOT, "ziniao", "serve",
]

# Minimal env: only what Cursor would pass (env from mcp.json + bare minimum)
env = {
    "ZINIAO_COMPANY": "test",
    "ZINIAO_USERNAME": "test",
    "ZINIAO_PASSWORD": "test",
    "ZINIAO_CLIENT_PATH": r"C:\test",
    "ZINIAO_VERSION": "v5",
    "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\WINDOWS"),
}

print(f"Starting with minimal env: {sorted(env.keys())}", flush=True)
proc = subprocess.Popen(
    cmd,
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    env=env,
)
print(f"PID: {proc.pid}", flush=True)
time.sleep(3)

# Check if process is still running
rc = proc.poll()
if rc is not None:
    print(f"Process already exited with code {rc}!", flush=True)
    stderr = proc.stderr.read().decode("utf-8", errors="replace")
    print(f"Stderr: {stderr}", flush=True)
    sys.exit(1)

print("Process running, sending init request...", flush=True)
proc.stdin.write((INIT_REQUEST + "\n").encode("utf-8"))
proc.stdin.flush()

result = [None]
def reader():
    result[0] = proc.stdout.readline()

t = threading.Thread(target=reader, daemon=True)
t.start()
t.join(timeout=10)

if result[0]:
    print(f"Response: {result[0].decode('utf-8', errors='replace')}", flush=True)
elif not t.is_alive():
    print("Empty response!", flush=True)
else:
    print("TIMEOUT: No response in 10 seconds!", flush=True)

stderr_data = proc.stderr.read(8192) if proc.poll() is not None else b""
if stderr_data:
    print(f"Stderr: {stderr_data.decode('utf-8', errors='replace')}", flush=True)

proc.kill()
proc.wait()
remaining = proc.stderr.read()
if remaining:
    print(f"Remaining stderr: {remaining.decode('utf-8', errors='replace')}", flush=True)
print("Done.", flush=True)
