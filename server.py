# -*- coding: utf-8 -*-
"""麦麦食历 · 本地网页服务（零依赖：只用标准库 http.server）。

把 mcd_box 的能力暴露成两个 API，前端是 web/index.html。

启动：
    python server.py                 # http://127.0.0.1:8000 （在线：真实 MCP，自动缓存）
    python server.py --offline       # 只读 data/snapshot 快照（无 Token、无网络可用）
    python server.py --port 8080

接口（全部 GET，返回 JSON）：
    /api/parse?text=...           文本解析回显（不推荐，只解析）
    /api/box?...                  开盒：state/feel/size/budget/exclude/text/random/seed/offline
    静态文件：/  → web/index.html
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from mcd_box.adapter import DEFAULT_STORE, Adapter  # noqa: E402
from mcd_box.candidates import build  # noqa: E402
from mcd_box.enrich import enrich  # noqa: E402
from mcd_box.entry import (  # noqa: E402
    describe_inputs, intuition_query, parse_text, random_query, validate,
)
from mcd_box.recommend import open_box  # noqa: E402
from mcd_box.render import render_json  # noqa: E402

WEB_DIR = os.path.join(ROOT, "web")
INDEX = os.path.join(WEB_DIR, "index.html")

# 由 --offline 启动参数设置：置真时所有请求都只读快照
SERVER_OFFLINE = False


def _first(q: dict, key: str) -> str:
    v = q.get(key)
    return v[0].strip() if v else ""


def _num(q: dict, key: str) -> float | None:
    v = _first(q, key)
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _csv(q: dict, key: str) -> list[str]:
    v = _first(q, key)
    return [x.strip() for x in v.replace("，", ",").split(",") if x.strip()] if v else []


def _json(payload: dict, status: int = 200) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def api_parse(params: dict) -> tuple[dict, int]:
    text = _first(params, "text")
    if not text:
        return {"error": "缺少 text 参数"}, 400
    p = parse_text(text)
    return {
        "echo": p.echo,
        "hit_count": p.hit_count,
        "unresolved": p.unresolved,
        "fields": {
            "state": p.query.state, "feel": p.query.feel, "size": p.query.size,
            "budget_yuan": p.query.budget_yuan, "exclude": p.query.exclude,
        },
    }, 200


def api_box(params: dict) -> tuple[dict, int]:
    text = _first(params, "text")
    is_random = _first(params, "random") in ("1", "true", "yes")
    offline = SERVER_OFFLINE or _first(params, "offline") in ("1", "true", "yes")
    store = _first(params, "store") or DEFAULT_STORE

    # 入口选择：显式字段优先于 text（解析回显后用户确认/修改的场景）
    state, feel, size = _first(params, "state"), _csv(params, "feel"), _first(params, "size")
    budget, exclude = _num(params, "budget"), _csv(params, "exclude")

    if is_random:
        q = random_query(store=store, budget=budget, exclude=exclude)
    elif text:
        q = parse_text(text, store=store).query
        q.state = state or q.state
        q.feel = feel or q.feel
        q.size = size or q.size
        q.budget_yuan = budget if budget is not None else q.budget_yuan
        q.exclude = exclude or q.exclude
    else:
        q = intuition_query(store=store, budget=budget, exclude=exclude,
                            state=state or None, feel=feel, size=size or None)

    problems = validate(q)
    if problems:
        return {"error": "；".join(problems)}, 400

    ad = Adapter(store=store, mode="offline" if offline else "auto")
    try:
        cat = ad.get_catalog()
    except Exception as e:
        return {"error": f"取数失败：{e}", "hint": "可加 offline=1 用本地快照"}, 502

    pool, _stats = build(cat)
    seed = _num(params, "seed")
    q.seed = int(seed) if seed else random.SystemRandom().randrange(10 ** 12)
    box = open_box(pool, q, rng=random.Random(q.seed))
    box = enrich(box, ad, cat)

    out = render_json(box, q, cat)
    out["inputs_desc"] = describe_inputs(q)
    return out, 200


def api_catalog(params: dict) -> tuple[dict, int]:
    """给前端背景用的"菜单词"：真实餐品名 + 门店规模，让界面里飘的是真东西。"""
    store = _first(params, "store") or DEFAULT_STORE
    offline = SERVER_OFFLINE or _first(params, "offline") in ("1", "true", "yes")
    try:
        cat = Adapter(store=store, mode="offline" if offline else "auto").get_catalog()
    except Exception as e:
        return {"error": str(e)}, 502
    words = [i.name for i in cat.items if i.name][:80]
    return {
        "store": {"storeCode": cat.store, "storeName": cat.store_name},
        "count": len(cat.items),
        "categories": len(cat.categories),
        "words": words,
        "source": cat.source,
        "fetched_at": cat.fetched_at,
    }, 200


class Handler(BaseHTTPRequestHandler):
    server_version = "MaiBox/0.1"

    def _send(self, body: bytes, ctype: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # 允许从预览面板的静态副本（file:// 或别的端口）跨源调用本地 API
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        # Chrome 的私有网络访问（PNA）预检要求显式许可，否则从沙箱页面请求 127.0.0.1 会被拦成 Failed to fetch
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802  CORS 预检
        self._send(b"", "text/plain; charset=utf-8", 204)

    def do_HEAD(self) -> None:  # 预览工具会用 HEAD 探测，别报 501
        path = urlparse(self.path).path
        ok = path in ("/", "/index.html") or path.startswith("/api/")
        self._send(b"", "text/html; charset=utf-8", 200 if ok else 404)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path in ("/", "/index.html"):
                if not os.path.exists(INDEX):
                    self._send(_json({"error": "web/index.html 缺失"}), "application/json; charset=utf-8", 500)
                    return
                self._send(open(INDEX, "rb").read(), "text/html; charset=utf-8")
            elif path == "/logo.svg":
                logo = os.path.join(WEB_DIR, "logo.svg")
                if os.path.exists(logo):
                    self._send(open(logo, "rb").read(), "image/svg+xml; charset=utf-8")
                else:
                    self._send(b"", "image/svg+xml", 404)
            elif path == "/favicon.ico":
                self._send(b"", "image/x-icon", 204)
            elif path == "/api/parse":
                payload, status = api_parse(parse_qs(urlparse(self.path).query))
                self._send(_json(payload, status), "application/json; charset=utf-8", status)
            elif path == "/api/box":
                payload, status = api_box(parse_qs(urlparse(self.path).query))
                self._send(_json(payload, status), "application/json; charset=utf-8", status)
            elif path == "/api/catalog":
                payload, status = api_catalog(parse_qs(urlparse(self.path).query))
                self._send(_json(payload, status), "application/json; charset=utf-8", status)
            else:
                self._send(_json({"error": "not found"}), "application/json; charset=utf-8", 404)
        except Exception as e:  # 不把异常带出线程
            self._send(_json({"error": str(e)}), "application/json; charset=utf-8", 500)

    def log_message(self, fmt, *args):  # 安静一点
        sys.stderr.write("[web] %s\n" % (fmt % args))


def main() -> int:
    global SERVER_OFFLINE
    ap = argparse.ArgumentParser(description="麦麦食历本地网页服务")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--offline", action="store_true", help="只读快照，不发网络请求")
    args = ap.parse_args()
    SERVER_OFFLINE = args.offline

    print(f"麦麦食历 → http://{args.host}:{args.port}  （{'离线快照模式' if args.offline else '在线模式，自动缓存 10 分钟'}）")
    print("按 Ctrl+C 停止")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
