# -*- coding: utf-8 -*-
"""用真实门店拉菜单，分析价格与套餐结构"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_mcp import McpClient, load_config, save

STORE = "3350325"


def extract(res):
    sc = res["result"].get("structuredContent")
    if sc:
        return sc
    text = res["result"]["content"][0]["text"]
    i = text.find("## Original Response")
    if i >= 0:
        try:
            return json.loads(text[i + len("## Original Response"):].strip())
        except Exception:
            pass
    return {"_text": text[:1000]}


def main():
    url, token = load_config()
    c = McpClient(url, token)
    c.initialize()

    print("=== query-meals ===")
    res = c.call_tool("query-meals", {"storeCode": STORE, "orderType": 1, "beType": 1})
    save("20_meals", res)
    body = extract(res)
    if not body.get("success"):
        print(json.dumps(body, ensure_ascii=False)[:600])
        return

    cats = body.get("data", {}).get("categories", [])
    print(f"分类 {len(cats)} 个")
    total = 0
    sample_meal = None
    for cat in cats:
        meals = cat.get("meals", [])
        total += len(meals)
        print(f"\n[{cat.get('name')}] {len(meals)} 项")
        if meals and not sample_meal:
            sample_meal = meals[0]
    print(f"\n餐品总数: {total}")

    if sample_meal:
        print("\n=== 首个餐品完整结构 ===")
        print(json.dumps(sample_meal, ensure_ascii=False, indent=2)[:2000])

    # 假设有 price 字段，统计
    prices = []
    for cat in cats:
        for m in cat.get("meals", []):
            for k in ("price", "salePrice", "currentPrice", "originalPrice"):
                if k in m and isinstance(m[k], (int, float)):
                    prices.append((m.get("name"), m[k], k))
                    break
    if prices:
        print(f"\n价格样例（{len(prices)} 条）:")
        for p in prices[:10]:
            print(" ", p)
        vals = [p[1] for p in prices]
        print(f"价格范围: {min(vals)} ~ {max(vals)}")
    else:
        print("\n[!] 未发现数字价格字段，打印字段名:", list(sample_meal.keys()) if sample_meal else None)

    print("\n=== query-store-coupons ===")
    res = c.call_tool("query-store-coupons", {"storeCode": STORE, "orderType": 1, "beType": 1})
    save("21_store_coupons", res)
    sc = extract(res)
    print(json.dumps(sc, ensure_ascii=False)[:800])


if __name__ == "__main__":
    main()
