# -*- coding: utf-8 -*-
"""快速探测 MCP 端点与鉴权头的正确组合（不打印 Token）"""
import json
import os
import urllib.request
import urllib.error

CONFIG_PATH = os.path.expanduser(r"~/.workbuddy/mcp.json")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    cfg = json.load(f)
srv = cfg["mcpServers"].get("mcd-mcp") or cfg["mcpServers"].get("mcp-mcd")
token = srv["headers"]["Authorization"].replace("Bearer ", "").strip()

payload = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-03-26", "capabilities": {},
               "clientInfo": {"name": "probe", "version": "0.1"}},
}

combos = [
    ("https://open.mcd.cn/mcp", {"Authorization": token}),
    ("https://open.mcd.cn/mcp", {"Authorization": f"Bearer {token}"}),
    ("https://open.mcd.cn/mcp", {"authToken": token}),
    ("https://mcp.mcd.cn", {"authToken": token}),
    ("https://mcp.mcd.cn/mcp", {"Authorization": token}),
]

for url, hdr in combos:
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream",
               "MCP-Protocol-Version": "2025-03-26"}
    headers.update(hdr)
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    label = f"{url} + {list(hdr.keys())[0]}"
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode("utf-8", "replace")
            sid = r.headers.get("Mcp-Session-Id")
            print(f"[OK] {label} -> {r.status} sid={bool(sid)} body={body[:200]}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        print(f"[{e.code}] {label} -> {body[:160]}")
    except Exception as e:
        print(f"[ERR] {label} -> {type(e).__name__}: {str(e)[:120]}")
