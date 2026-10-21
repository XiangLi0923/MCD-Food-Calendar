# -*- coding: utf-8 -*-
"""第二轮：在 mcp.mcd.cn 上试各种鉴权头格式"""
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

variants = [
    ("Authorization: Bearer", {"Authorization": f"Bearer {token}"}),
    ("authToken: Bearer", {"authToken": f"Bearer {token}"}),
    ("auth-token", {"auth-token": token}),
    ("token", {"token": token}),
    ("accessToken", {"accessToken": token}),
    ("Authorization + authToken", {"Authorization": token, "authToken": token}),
    ("Authorization: Bearer + authToken: Bearer", {"Authorization": f"Bearer {token}", "authToken": f"Bearer {token}"}),
]

url = "https://mcp.mcd.cn"
for label, hdr in variants:
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream",
               "MCP-Protocol-Version": "2025-03-26"}
    headers.update(hdr)
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode("utf-8", "replace")
            print(f"[OK] {label} -> {r.status} sid={bool(r.headers.get('Mcp-Session-Id'))} body={body[:220]}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        msg = body.replace("\n", " ")[:140]
        print(f"[{e.code}] {label} -> {msg}")
    except Exception as e:
        print(f"[ERR] {label} -> {type(e).__name__}: {str(e)[:120]}")

# 附加：GET 探测，看服务器是否要求 SSE 端点
print("\n[GET probe]")
try:
    req = urllib.request.Request(url, headers={"Authorization": token, "Accept": "text/event-stream"}, method="GET")
    with urllib.request.urlopen(req, timeout=8) as r:
        print("GET ->", r.status, r.headers.get("Content-Type"), r.read()[:200])
except urllib.error.HTTPError as e:
    print(f"GET -> {e.code}: {e.read()[:200]}")
except Exception as e:
    print(f"GET -> {type(e).__name__}: {str(e)[:100]}")
