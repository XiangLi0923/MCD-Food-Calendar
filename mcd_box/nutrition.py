# -*- coding: utf-8 -*-
"""营养查询：给"这一顿多少热量"用。

数据源：`data/snapshot/nutrition.json`（由 scripts/build_nutrition.py 从官方
`list-nutrition-foods` 抓取，160 条）。
已知限制：营养表**没有产品 code**，只能按名称匹配；套餐名（如"板烧鸡腿堡三件套"）
不在表里，必须展开成子项再查。匹配不到就说"未知"，**绝不估算**。
"""
from __future__ import annotations

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT = os.path.join(ROOT, "data", "snapshot", "nutrition.json")

# 名称别名：只做形式归一，不做跨规格合并（"可乐" 不会当成 "可乐中杯"）
ALIAS = {
    "纯牛奶(盒装)": "纯牛奶（盒装）",
    "纯牛奶（盒装）": "纯牛奶（盒装）",
    "可口可乐中杯": "可乐中杯",
    "可口可乐大杯": "可乐大杯",
    "可口可乐小杯": "可乐小杯",
    "无糖可乐中杯": "无糖可口可乐中杯",
}

_cache: dict | None = None


def normalize(name: str) -> str:
    s = (name or "").strip()
    s = s.replace("（", "(").replace("）", ")")
    s = re.sub(r"[™®]", "", s)
    s = re.sub(r"\s+", "", s)
    return s


def _load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    table, meta = {}, {}
    try:
        with open(SNAPSHOT, encoding="utf-8") as f:
            data = json.load(f)
        meta = {"fetched_at": data.get("fetched_at", ""), "count": data.get("count", 0)}
        for row in data.get("rows", []):
            table[normalize(row["productName"])] = row
    except (OSError, json.JSONDecodeError, KeyError):
        meta = {"fetched_at": "", "count": 0}
    _cache = {"table": table, "meta": meta}
    return _cache


def lookup(name: str) -> dict | None:
    """按名称查一行营养数据；查不到返回 None（调用方必须显示"未知"）。"""
    if not name:
        return None
    t = _load()["table"]
    key = normalize(name)
    if key in t:
        return t[key]
    alias = ALIAS.get(name) or ALIAS.get(key)
    if alias and normalize(alias) in t:
        return t[normalize(alias)]
    # 去掉括号里的口味/规格后缀再试一次（如"浓浓黑巧（冰/热）"）
    stripped = re.sub(r"\(.*?\)$", "", key)
    if stripped and stripped in t:
        return t[stripped]
    # 去掉常见修饰前缀（"原味双层深海鳕鱼堡" → "双层深海鳕鱼堡"）
    for pre in ("原味", "经典", "新", "蜜汁", "香辣", "酥脆"):
        if stripped.startswith(pre) and stripped[len(pre):] in t:
            return t[stripped[len(pre):]]
    return None


def aggregate(names: list[str]) -> dict:
    """合计一组餐品。返回 kcal / protein / 命中数 / 总数 / 是否完整。"""
    kcal, protein, matched, miss = 0.0, 0.0, 0, []
    for n in names:
        row = lookup(n)
        if row is None:
            miss.append(n)
            continue
        matched += 1
        kcal += float(row.get("energyKcal") or 0)
        protein += float(row.get("protein") or 0)
    total = len(names)
    return {
        "kcal": round(kcal) if matched else None,
        "protein_g": round(protein, 1) if matched else None,
        "matched": matched,
        "total": total,
        "complete": bool(total) and matched == total,
        "missing": miss,
        "source_fetched_at": _load()["meta"].get("fetched_at", ""),
    }


def table_meta() -> dict:
    return _load()["meta"]
