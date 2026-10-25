# -*- coding: utf-8 -*-
"""生成纯静态版（可直接丢到 Netlify / 任意静态托管）。

背景：Netlify 只能托管静态文件，跑不了 server.py。所以把"一顿饭"的候选
（含组合明细、热量、价格）在构建期全部算好，前端只做筛选 + 排序 + 渲染。

产出：
    web/static/index.html   像素风单页（无任何 fetch）
    web/static/data.js      window.MCD_DATA = {...}
    web/static.zip          可直接拖到 Netlify 的压缩包（index.html 在根）

用法：python scripts/build_static.py
"""
import json
import os
import shutil
import sys
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mcd_box import nutrition                                    # noqa: E402
from mcd_box.adapter import Adapter                             # noqa: E402
from mcd_box.candidates import build                            # noqa: E402
from mcd_box.meals import build_meals                           # noqa: E402
from mcd_box.recommend import Query                             # noqa: E402

OUT_DIR = os.path.join(ROOT, "web", "static")
SIZES = [("垫一下", "light"), ("正常", "normal"), ("很饿", "hungry")]


def meal_record(c, detail_names):
    """把 Candidate 变成前端要的扁平记录（明细 + 热量一次算完）。"""
    if c.parts:
        parts = [{"name": n, "price": p} for n, p in c.parts]
    else:
        parts = [{"name": n, "price": None} for n in detail_names]

    kcal_sum, matched = 0, 0
    for it in parts:
        row = nutrition.lookup(it["name"])
        if row:
            it["kcal"] = int(row.get("energyKcal") or 0)
            kcal_sum += it["kcal"]
            matched += 1
        else:
            it["kcal"] = None

    complete = bool(parts) and matched == len(parts)
    return {
        "code": c.code,
        "main": c.main_code or c.code,
        "name": c.name,
        "price": c.price_yuan,
        "was": c.original_yuan if (c.original_yuan and c.price_yuan and c.original_yuan > c.price_yuan) else None,
        "cat": c.category,
        "parts": parts,
        "kcal": kcal_sum if complete else None,
        "protein": round(sum(float(nutrition.lookup(i["name"])["protein"]) for i in parts
                             if nutrition.lookup(i["name"])), 1) if complete else None,
        "complete": complete,
        "new": c.is_new,
        "pop": c.is_pop,
        "set": (not c.parts) and bool(detail_names),
        "img": c.image,
    }


def main() -> int:
    ad = Adapter(mode="offline")
    cat = ad.get_catalog()
    pool, stats = build(cat)

    # 需要展开子项的套餐
    set_codes = [c.code for c in pool if not c.parts and not any(
        w in c.name for w in ("单品",)) and any(
        w in c.name for w in ("套餐", "三件套", "四件套", "随心配", "组合", "双拼"))]
    details = ad.get_detail_items(set_codes)

    data = {
        "store": {"code": cat.store, "name": cat.store_name},
        "fetched_at": cat.fetched_at,
        "built_at": time.strftime("%Y-%m-%d %H:%M"),
        "stats": stats,
        "nutrition_at": nutrition.table_meta().get("fetched_at", ""),
        "menus": {},
    }

    for label, key in SIZES:
        q = Query(size=label, budget_yuan=None)
        meals = build_meals(pool, q)
        seen, rows = set(), []
        for m in meals:
            k = m.main_code or m.code
            if k in seen:
                continue
            seen.add(k)
            rows.append(meal_record(m, details.get(m.code, [])))
        data["menus"][key] = rows
        print(f"{label}: {len(rows)} 份")

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "data.js"), "w", encoding="utf-8") as f:
        f.write("window.MCD_DATA = ")
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")

    # 把静态页与 logo 也复制进去（静态页本身不含后端调用）
    src_html = os.path.join(ROOT, "web", "static_index.html")
    if os.path.exists(src_html):
        shutil.copyfile(src_html, os.path.join(OUT_DIR, "index.html"))
        print("index.html 已生成")
    src_logo = os.path.join(ROOT, "web", "logo.svg")
    if os.path.exists(src_logo):
        shutil.copyfile(src_logo, os.path.join(OUT_DIR, "logo.svg"))

    # 打包：index.html / data.js 必须在压缩包根目录
    zip_path = os.path.join(ROOT, "web", "static.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name in ("index.html", "data.js", "logo.svg"):
            p = os.path.join(OUT_DIR, name)
            if os.path.exists(p):
                z.write(p, name)
    size_kb = os.path.getsize(zip_path) / 1024
    print(f"已打包 {zip_path}（{size_kb:.0f} KB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
