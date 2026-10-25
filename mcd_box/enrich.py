# -*- coding: utf-8 -*-
"""渲染前的补全：这一盒里有什么、多少热量、多少钱、图。

原则：
  - 组合餐（parts 已存在）直接用各部分的真实菜单价与营养；
  - 官方套餐需要展开子项才知道"含什么"，子项与营养都取不到时**明确写未知**，不估算；
  - 价格：现价 = 各项真实菜单价之和；原价只有官方套餐才有，用来算"省多少"。
"""
from __future__ import annotations

from . import nutrition
from .adapter import Adapter, Catalog
from .recommend import Box


def _single_items(cat: Catalog | None) -> list[tuple[str, float]]:
    """菜单里的单品（名称, 价格），用来回答"这个单点多少钱"。"""
    if not cat:
        return []
    return [(i.name, i.price_yuan) for i in cat.items
            if i.price_yuan is not None and not any(w in i.name for w in ("套餐", "三件套", "四件套"))]


def _single_price(name: str, items: list[tuple[str, float]]) -> float | None:
    exact = {n: p for n, p in items}
    if name in exact:
        return exact[name]
    # "中薯条" 在菜单里叫 "薯条"：取最长被包含的单品名
    best, best_len = None, 0
    for n, p in items:
        if n and n in name and len(n) > best_len:
            best, best_len = p, len(n)
    return best


def enrich(box: Box, adapter: Adapter | None, catalog: Catalog | None = None) -> Box:
    # 只有官方套餐需要展开子项：一次批量拿，带缓存
    need = [p.cand.code for p in box.plans if not p.cand.parts]
    details = adapter.get_detail_items(need) if (adapter and need) else {}

    for p in box.plans:
        c = p.cand
        if c.parts:
            parts = [{"name": n, "price_yuan": pr, "kcal": None, "single_price_yuan": pr}
                     for n, pr in c.parts]
        else:
            names = details.get(c.code) or []
            parts = [{"name": n, "price_yuan": None, "kcal": None} for n in names]

        singles = _single_items(catalog)
        for item in parts:
            if item["price_yuan"] is None:
                item["single_price_yuan"] = _single_price(item["name"], singles)

        for item in parts:
            row = nutrition.lookup(item["name"])
            if row:
                item["kcal"] = int(row.get("energyKcal") or 0)

        names = [i["name"] for i in parts]
        nut = nutrition.aggregate(names) if names else {
            "kcal": None, "protein_g": None, "matched": 0, "total": 0,
            "complete": False, "missing": [], "source_fetched_at": nutrition.table_meta().get("fetched_at", ""),
        }

        now = c.price_yuan
        was = c.original_yuan if (c.original_yuan and now and c.original_yuan > now) else None
        p.meta = {
            "parts": parts,
            "parts_known": bool(parts),
            "nutrition": nut,
            "image": c.image,
            "price": {
                "now": now,
                "was": was,
                "save": round(was - now, 2) if was else None,
            },
            "is_combo": bool(c.parts),
        }
    return box
