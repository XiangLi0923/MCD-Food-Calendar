# -*- coding: utf-8 -*-
"""卡片与整盒渲染。纯文本，先保证「看得懂」，不追求好看。

每张卡片包含：角色、价格、餐品、子项（暂无）、理由、命中输入、警告、数据来源。
营养参考：当前版本**不展示**（数据层未接入按需查询，宁缺不编）。
"""
from __future__ import annotations

from .adapter import Catalog
from .recommend import Box, Plan, Query

LINE = "─" * 46


def _price(plan: Plan) -> str:
    p = plan.cand.price_yuan
    return f"¥{p:.2f}" if p is not None else "价格待确认"


def render_card(plan: Plan, idx: int | None = None) -> str:
    c = plan.cand
    head = f"【{plan.label}】{_price(plan)}"
    if idx:
        head = f"【{idx}. {plan.label}】{_price(plan)}"
    rows = [
        head,
        f"  {c.name}",
    ]
    meta = plan.meta or {}
    parts = meta.get("parts") or []
    if parts:
        for it in parts:
            if it.get("price_yuan") is not None:
                price = f"¥{it['price_yuan']:.2f}"
            elif it.get("single_price_yuan") is not None:
                price = f"单点 ¥{it['single_price_yuan']:.2f}"
            else:
                price = "价格并入套餐"
            # 热量未知就不显示，不写"热量未知"占位
            kcal = f"  {it['kcal']} kcal" if it.get("kcal") is not None else ""
            rows.append(f"    · {it['name']}  {price}{kcal}")
    elif not meta.get("parts_known", True):
        rows.append("    · （套餐子项未展开，含什么以门店为准）")

    rows.append(f"  分类：{c.category}")
    rows.append(f"  为什么是它：{plan.reason}")

    nut = meta.get("nutrition") or {}
    if nut.get("complete"):
        rows.append(f"  热量合计：约 {nut['kcal']} kcal · 蛋白 {nut.get('protein_g')}g")
    price_meta = meta.get("price") or {}
    if price_meta.get("was"):
        rows.append(f"  价格：¥{price_meta['now']:.2f}（原价 ¥{price_meta['was']:.2f}，省 ¥{price_meta['save']:.2f}）")
    if plan.matched:
        rows.append(f"  对上你的：{'、'.join(dict.fromkeys(plan.matched))}")
    for w in plan.warnings:
        rows.append(f"  ⚠ {w}")
    return "\n".join(rows)


def render_box(box: Box, q: Query, cat: Catalog, inputs: str) -> str:
    out = [
        f"门店：{cat.store_name or cat.store}（{cat.store}）",
        f"你输入的：{inputs}",
        f"候选 {box.pool_size} 个 · 价格中位数 ¥{box.stats.get('median', 0):.2f} · seed {box.seed}",
        LINE,
    ]
    if not box.plans:
        out.append("这个条件下没有可选餐品。")
        for n in box.notes:
            out.append(f"· {n}")
        return "\n".join(out)

    for i, p in enumerate(box.plans, 1):
        out.append(render_card(p, i))
        out.append("")

    if box.notes:
        for n in box.notes:
            out.append(f"· {n}")
        out.append("")

    src = {"online": "实时", "cache": "10 分钟内的缓存", "snapshot": "离线快照（非实时）"}.get(cat.source, cat.source)
    out.append(LINE)
    out.append(f"数据：{src} · 抓取于 {cat.fetched_at} · 以门店实际供应与价格为准")
    out.append("忌口按名称匹配，不含成分与交叉接触信息，过敏请向门店核实。")
    return "\n".join(out)


def render_json(box: Box, q: Query, cat: Catalog) -> dict:
    return {
        "store": {"storeCode": cat.store, "storeName": cat.store_name},
        "source": cat.source,
        "fetched_at": cat.fetched_at,
        "seed": box.seed,
        "pool_size": box.pool_size,
        "input": {
            "entry": q.entry, "state": q.state, "feel": q.feel, "size": q.size,
            "budget_yuan": q.budget_yuan, "exclude": q.exclude, "raw_text": q.raw_text,
        },
        "plans": [
            {
                "role": p.role, "label": p.label,
                "code": p.cand.code, "name": p.cand.name,
                "category": p.cand.category,
                "price_yuan": p.cand.price_yuan,
                "original_yuan": p.cand.original_yuan,
                "parts": (p.meta or {}).get("parts", []),
                "parts_known": (p.meta or {}).get("parts_known", False),
                "nutrition": (p.meta or {}).get("nutrition", {}),
                "price": (p.meta or {}).get("price", {}),
                "image": (p.meta or {}).get("image"),
                "tags": list(p.cand.tags),
                "reason": p.reason,
                "matched": p.matched,
                "warnings": p.warnings,
            }
            for p in box.plans
        ],
        "notes": box.notes,
    }
