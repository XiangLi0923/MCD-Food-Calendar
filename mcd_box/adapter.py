# -*- coding: utf-8 -*-
"""取数层：把门店菜单变成一份干净的 Catalog。

三种数据来源，同一份结构：
    online    实时调用 query-meals（+ 需要时 calculate-price）
    cache     data/cache/<store>.json，10 分钟有效
    snapshot  data/snapshot/<store>.json，离线演示用，带抓取时间，永不被自动覆盖

铁律（踩过坑，别改回去）：
  1. 同一餐品会出现在多个菜单分类里 → **一切统计与核价必须按 code 去重**。
  2. 展示价用 query-meals 的 currentPrice（会员/促销后现价）；
     calculate-price 与它有 18/102 不一致（未应用麦金卡优惠），只用于改单重算。
  3. 没有价格就是 None，不许填 0 / 不许估算。
  4. 任何出网调用只发生在这个文件里。
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict

from .mcp_client import DEFAULT_URL, McpClient, McpError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, "data", "cache")
SNAPSHOT_DIR = os.path.join(ROOT, "data", "snapshot")
CONFIG_PATH = os.path.expanduser(os.path.join("~", ".workbuddy", "mcp.json"))

DEFAULT_STORE = "3350112"          # 麦当劳烟台保利餐厅（离用户最近，实测 599m）
DEFAULT_STORE_NAME = "麦当劳烟台保利餐厅"
CACHE_TTL = 600                    # 秒

# 「展示货架」类分类：跨品类的促销橱窗，不是真实品类。
# 餐品如果同时出现在「人气热卖」和「鸡肉汉堡/卷」，应归到后者——否则惊喜款靠"分类不同"就失效了。
SHELF_CATEGORIES = {"人气热卖"}


# ---------------------------------------------------------------- 配置
def load_token() -> str | None:
    """优先环境变量 YOUR_MCP_TOKEN（离线演示时为空），其次本机 mcp.json（开发用）。"""
    env = os.environ.get("YOUR_MCP_TOKEN", "").strip()
    if env:
        return env
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        servers = cfg.get("mcpServers", {})
        srv = servers.get("mcd-mcp") or servers.get("mcp-mcd")
        if srv:
            return (srv.get("headers", {}).get("Authorization") or "").strip() or None
    except (OSError, json.JSONDecodeError):
        pass
    return None


def load_url() -> str:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        servers = cfg.get("mcpServers", {})
        srv = servers.get("mcd-mcp") or servers.get("mcp-mcd")
        if srv and srv.get("url"):
            return srv["url"]
    except (OSError, json.JSONDecodeError):
        pass
    return DEFAULT_URL


# ---------------------------------------------------------------- 结构
@dataclass
class Item:
    """一个可下单的售卖单元（已按 code 去重）。"""
    code: str
    name: str
    category: str
    tags: list[str] = field(default_factory=list)
    price_yuan: float | None = None
    original_yuan: float | None = None
    discount_type: str | None = None
    image: str | None = None
    category_hits: int = 1          # 出现在几个分类里（>1 说明菜单重复展示）


@dataclass
class Catalog:
    store: str
    store_name: str
    source: str                     # online | cache | snapshot
    fetched_at: str
    items: list[Item] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "store": self.store,
            "store_name": self.store_name,
            "source": self.source,
            "fetched_at": self.fetched_at,
            "categories": self.categories,
            "items": [asdict(i) for i in self.items],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Catalog":
        return cls(
            store=d["store"],
            store_name=d.get("store_name", ""),
            source=d.get("source", "snapshot"),
            fetched_at=d.get("fetched_at", ""),
            categories=d.get("categories", []),
            items=[Item(**i) for i in d.get("items", [])],
        )


# ---------------------------------------------------------------- 解析
def parse_menu(payload: dict, store: str, store_name: str = "") -> Catalog:
    """把 query-meals 的返回变成 Catalog。

    结构要点（实测）：
      data.meals           → code → {name, image, currentPrice, originalPrice, discountType}
      data.categories[].meals[] → code + tags（**tags 只在这里**，且会出现重复）
    """
    data = payload.get("data") or {}
    catalog_map = data.get("meals") or {}
    cats = data.get("categories") or []

    meta: dict[str, dict] = {}
    for cat in cats:
        cname = (cat.get("name") or "").replace("\n", " ").strip()
        for m in cat.get("meals", []):
            code = m.get("code")
            if not code:
                continue
            slot = meta.setdefault(code, {"categories": [], "tags": [], "hits": 0})
            slot["hits"] += 1
            if cname and cname not in slot["categories"]:
                slot["categories"].append(cname)
            for t in m.get("tags") or []:
                if t not in slot["tags"]:
                    slot["tags"].append(t)

    def primary_category(cats_of_code: list[str]) -> str:
        """优先取真实品类，跳过「人气热卖」这类展示货架。"""
        for c in cats_of_code:
            if c not in SHELF_CATEGORIES:
                return c
        return cats_of_code[0] if cats_of_code else ""

    items: list[Item] = []
    for code, info in catalog_map.items():
        m = meta.get(code, {})
        cur, org = info.get("currentPrice"), info.get("originalPrice")

        def _f(v):
            try:
                return round(float(v), 2)
            except (TypeError, ValueError):
                return None

        items.append(Item(
            code=code,
            name=(info.get("name") or "").strip(),
            category=primary_category(m.get("categories", [])),
            tags=m.get("tags", []),
            price_yuan=_f(cur),
            original_yuan=_f(org),
            discount_type=info.get("discountType"),
            image=info.get("image"),
            category_hits=m.get("hits", 0),
        ))

    items.sort(key=lambda x: (x.category, x.price_yuan if x.price_yuan is not None else 1e9))
    return Catalog(
        store=store,
        store_name=store_name,
        source="online",
        fetched_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        items=items,
        categories=[(c.get("name") or "").replace("\n", " ").strip() for c in cats],
    )


# ---------------------------------------------------------------- 取数
class Adapter:
    """对外只暴露 get_catalog()。mode: auto | online | offline"""

    def __init__(self, store: str = DEFAULT_STORE, mode: str = "auto", use_cache: bool = True):
        self.store = store
        self.mode = mode
        self.use_cache = use_cache

    # -- 路径
    def _cache_path(self) -> str:
        return os.path.join(CACHE_DIR, f"{self.store}.json")

    def _snapshot_path(self) -> str:
        return os.path.join(SNAPSHOT_DIR, f"{self.store}.json")

    # -- 缓存
    def _read_cache(self) -> Catalog | None:
        path = self._cache_path()
        if not (self.use_cache and os.path.exists(path)):
            return None
        if time.time() - os.path.getmtime(path) > CACHE_TTL:
            return None
        with open(path, encoding="utf-8") as f:
            cat = Catalog.from_dict(json.load(f))
        cat.source = "cache"
        return cat

    def _write_cache(self, cat: Catalog) -> None:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(self._cache_path(), "w", encoding="utf-8") as f:
            json.dump(cat.to_dict(), f, ensure_ascii=False, indent=2)

    # -- 快照
    def _read_snapshot(self) -> Catalog | None:
        path = self._snapshot_path()
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            cat = Catalog.from_dict(json.load(f))
        cat.source = "snapshot"
        return cat

    # -- 在线
    def _fetch_online(self) -> Catalog:
        token = load_token()
        if not token:
            raise McpError("没有可用 Token：设置环境变量 YOUR_MCP_TOKEN，或用离线快照模式")
        client = McpClient(load_url(), token)
        client.initialize()
        payload = client.call_tool("query-meals", {
            "storeCode": self.store, "orderType": 1, "beType": 1,
        })
        cat = parse_menu(payload, self.store, DEFAULT_STORE_NAME if self.store == DEFAULT_STORE else "")
        if not cat.items:
            raise McpError(f"门店 {self.store} 返回空菜单")
        self._write_cache(cat)
        return cat

    # -- 对外
    def get_catalog(self) -> Catalog:
        if self.mode == "offline":
            cat = self._read_snapshot()
            if cat is None:
                raise McpError(f"离线模式缺少快照：{self._snapshot_path()}")
            return cat

        if self.mode == "auto":
            cat = self._read_cache()
            if cat is not None:
                return cat

        try:
            return self._fetch_online()
        except McpError:
            if self.mode == "online":
                raise
            cat = self._read_snapshot()      # 网络失败时兜底到快照
            if cat is None:
                raise
            return cat
