# -*- coding: utf-8 -*-
"""
MCP 数据实测探针 —— 直连麦当劳官方 MCP 服务器（streamable HTTP）
用途：1) tools/list 拿到全部工具与参数 schema
     2) 依次调用营养 / 套餐 / 价格相关工具，保存原始 JSON 供归档与字段分析
安全：Token 从 ~/.workbuddy/mcp.json 读取，仅用于本机调用，不打印、不落盘到输出文件
"""
import json
import os
import sys
import urllib.request
import urllib.error

CONFIG_PATH = os.path.expanduser(r"~/.workbuddy/mcp.json")
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "raw")
os.makedirs(OUT_DIR, exist_ok=True)


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    srv = cfg["mcpServers"]["mcp-mcd"] if "mcp-mcd" in cfg["mcpServers"] else cfg["mcpServers"]["mcd-mcp"]
    token = srv["headers"]["Authorization"].strip()
    if not token.startswith("Bearer "):
        token = "Bearer " + token
    return srv["url"], token


class McpClient:
    def __init__(self, url, token):
        self.url = url.rstrip("/")
        self.token = token
        self.session_id = None
        self.msg_id = 0

    def _post(self, payload, extra_headers=None):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": self.token,
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        if extra_headers:
            headers.update(extra_headers)
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self.session_id = sid
                ctype = resp.headers.get("Content-Type", "")
                body = resp.read().decode("utf-8", errors="replace")
                return ctype, body
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {e.code}: {body[:500]}") from e

    def _parse_sse(self, body):
        # 从 SSE 流中提取 data: 行的 JSON（可能有多条事件，取最后一条含 result/error 的）
        msgs = []
        for line in body.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                payload = line[5:].strip()
                if not payload:
                    continue
                try:
                    msgs.append(json.loads(payload))
                except json.JSONDecodeError:
                    continue
        for m in reversed(msgs):
            if isinstance(m, dict) and ("result" in m or "error" in m):
                return m
        return msgs[-1] if msgs else None

    def request(self, method, params=None, notify=False):
        self.msg_id += 1
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        if not notify:
            payload["id"] = self.msg_id
        ctype, body = self._post(payload, {"MCP-Protocol-Version": "2025-03-26"} if method == "initialize" else None)
        if notify:
            return None
        if "text/event-stream" in ctype:
            return self._parse_sse(body)
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"_raw": body[:2000]}

    def initialize(self):
        res = self.request("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "mcd-weekly-canteen-probe", "version": "0.1.0"},
        })
        # 发送 initialized 通知（部分服务器要求）
        try:
            self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, None)
        except Exception:
            pass
        return res

    def list_tools(self):
        return self.request("tools/list", {})

    def call_tool(self, name, arguments=None):
        return self.request("tools/call", {"name": name, "arguments": arguments or {}})


def save(name, obj):
    path = os.path.join(OUT_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    return path


def main():
    url, token = load_config()
    print(f"[probe] server={url} token_len={len(token)} (不打印内容)")
    c = McpClient(url, token)
    init = c.initialize()
    print("[probe] initialize ->", json.dumps(init, ensure_ascii=False)[:400])
    save("00_initialize", init)

    tools = c.list_tools()
    save("01_tools_list", tools)
    if "result" in tools and "tools" in tools["result"]:
        names = [t["name"] for t in tools["result"]["tools"]]
        print(f"[probe] tools({len(names)}): {', '.join(names)}")
        for t in tools["result"]["tools"]:
            if t["name"] in ("list-nutrition-foods", "query-meals", "query-meal-detail", "calculate-price", "available-coupons"):
                print(f"\n[schema] {t['name']}: {json.dumps(t.get('inputSchema', {}), ensure_ascii=False)}")
    else:
        print("[probe] tools/list 异常:", json.dumps(tools, ensure_ascii=False)[:800])
        return

    calls = [
        ("02_nutrition", "list-nutrition-foods", {}),
        ("03_meals", "query-meals", {}),
    ]
    for tag, name, args in calls:
        try:
            res = c.call_tool(name, args)
            save(tag, res)
            brief = json.dumps(res, ensure_ascii=False)
            print(f"\n[{tag}] {name} -> {len(brief)} chars, preview: {brief[:600]}")
        except Exception as e:
            print(f"\n[{tag}] {name} 失败: {e}")
            save(tag + "_error", {"error": str(e)})


if __name__ == "__main__":
    main()
