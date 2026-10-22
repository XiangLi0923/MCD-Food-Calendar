# -*- coding: utf-8 -*-
"""与麦当劳官方 MCP 通信的最小客户端（只用标准库）。

协议：JSON-RPC 2.0 over streamable HTTP，POST 到 https://mcp.mcd.cn
鉴权：Authorization: Bearer <token>   ← 手工客户端必须带 Bearer，裸 token 会 403
返回：可能是 application/json，也可能是 text/event-stream，统一由 extract() 归一

安全：Token 只在内存里，不打印、不落盘。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

DEFAULT_URL = "https://mcp.mcd.cn"
PROTOCOL_VERSION = "2025-03-26"


class McpError(RuntimeError):
    """MCP 调用失败（网络 / HTTP / JSON-RPC error）。"""


def extract(payload: dict) -> dict:
    """把一次 tools/call 的返回统一成业务数据 dict。

    三种形态：
      1) structuredContent 直接是 dict
      2) content[0].text 里带 '## Original Response' + JSON（麦当劳 MCP 的常见形态）
      3) 兜底：原样返回，供调用方看原始内容
    """
    if not payload:
        return {}
    r = payload.get("result", payload)
    if isinstance(r, dict) and isinstance(r.get("structuredContent"), dict):
        return r["structuredContent"]
    try:
        text = r["content"][0]["text"]
    except (KeyError, IndexError, TypeError):
        return {"_raw": r}
    marker = "## Original Response"
    idx = text.find(marker)
    if idx >= 0:
        body = text[idx + len(marker):].strip()
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            pass
    return {"_text": text}


class McpClient:
    def __init__(self, url: str = DEFAULT_URL, token: str = "", timeout: int = 60):
        if not token:
            raise McpError("缺少 MCP Token")
        self.url = url.rstrip("/")
        self.token = token if token.startswith("Bearer ") else "Bearer " + token
        self.timeout = timeout
        self.session_id: str | None = None
        self._id = 0

    # ---------- 底层 ----------
    def _post(self, payload: dict, extra_headers: dict | None = None) -> tuple[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": self.token,
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        if extra_headers:
            headers.update(extra_headers)
        req = urllib.request.Request(
            self.url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self.session_id = sid
                return resp.headers.get("Content-Type", ""), resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            hint = "（429 限流，稍后再试）" if e.code == 429 else ""
            raise McpError(f"HTTP {e.code}{hint}: {body[:300]}") from e
        except urllib.error.URLError as e:
            raise McpError(f"网络不可达: {e.reason}") from e

    @staticmethod
    def _parse_sse(body: str) -> dict:
        msgs = []
        for line in body.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                chunk = line[5:].strip()
                if chunk:
                    try:
                        msgs.append(json.loads(chunk))
                    except json.JSONDecodeError:
                        continue
        for m in reversed(msgs):
            if isinstance(m, dict) and ("result" in m or "error" in m):
                return m
        return msgs[-1] if msgs else {}

    def request(self, method: str, params: dict | None = None, notify: bool = False) -> dict:
        self._id += 1
        payload: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        if not notify:
            payload["id"] = self._id
        extra = {"MCP-Protocol-Version": PROTOCOL_VERSION} if method == "initialize" else None
        ctype, body = self._post(payload, extra)
        if notify:
            return {}
        msg = self._parse_sse(body) if "text/event-stream" in ctype else json.loads(body or "{}")
        if isinstance(msg, dict) and msg.get("error"):
            err = msg["error"]
            raise McpError(f"{err.get('code')}: {err.get('message')}")
        return msg

    # ---------- 对外 ----------
    def initialize(self) -> dict:
        res = self.request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "mcd-food-calendar", "version": "0.1.0"},
        })
        try:  # 部分服务端要求显式通知初始化完成
            self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        except Exception:
            pass
        return res

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        """调用工具，直接返回业务数据（已从 SSE/文本里解出来）。"""
        return extract(self.request("tools/call", {"name": name, "arguments": arguments or {}}))
