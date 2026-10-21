# -*- coding: utf-8 -*-
"""1) calculate-price 批量核价  2) 套餐子项 -> 营养表 名称匹配率"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_mcp import McpClient, load_config, save

STORE = "3350325"
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(BASE, "raw")


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
    return {"_text": text[:800]}


def main():
    url, token = load_config()
    c = McpClient(url, token)
    c.initialize()

    with open(os.path.join(RAW, "20_meals.json"), "r", encoding="utf-8") as f:
        meals = extract(json.load(f))
    with open(os.path.join(RAW, "nutrition_parsed.json"), "r", encoding="utf-8") as f:
        nutrition = json.load(f)
    nut_names = {n["productName"] for n in nutrition}

    codes = []
    for cat in meals["data"]["categories"]:
        for m in cat.get("meals", []):
            codes.append((cat["name"].replace("\n", ""), m["code"]))

    # 1) 批量核价：一次传 5 个
    batch = [{"productCode": code, "quantity": 1} for _, code in codes[:5]]
    res = c.call_tool("calculate-price", {"storeCode": STORE, "orderType": 1, "beType": 1, "items": batch})
    save("24_price_batch", res)
    b = extract(res)
    print("=== 批量核价（5 项）===")
    print(json.dumps(b, ensure_ascii=False)[:1200])
    if b.get("data"):
        plist = b["data"].get("productList", [])
        print(f"\nproductList {len(plist)} 项，分别带 subtotal: ", [(p['productName'], p['subtotal']) for p in plist])

    # 2) 名称匹配率：取 20 个餐品详情，展开子项名称，与营养表匹配
    print("\n=== 名称匹配测试（20 个餐品）===")
    hit, total_items, matched_pairs = 0, 0, []
    for cat, code in codes[:20]:
        res = c.call_tool("query-meal-detail", {"storeCode": STORE, "orderType": 1, "beType": 1, "code": code})
        d = extract(res)
        data = d.get("data") or {}
        name = data.get("name", "")
        sub_names = []
        for r in data.get("rounds", []):
            for ch in r.get("choices", []):
                if ch.get("isDefault") == 1 and ch.get("quantity", 0) > 0:
                    sub_names.append(ch.get("name", ""))
        for sn in sub_names:
            total_items += 1
            if sn in nut_names:
                hit += 1
                matched_pairs.append((name, sn, "exact"))
            else:
                # 模糊：去括号/空格后包含匹配
                f = any(sn.replace(" ", "") in nn.replace(" ", "") or nn.replace(" ", "") in sn.replace(" ", "") for nn in nut_names)
                if f:
                    hit += 1
                    matched_pairs.append((name, sn, "fuzzy"))
    print(f"子项总数={total_items} 命中={hit} 命中率={hit/total_items*100 if total_items else 0:.0f}%")
    for p in matched_pairs[:15]:
        print("  ", p)
    save("25_match_stats", {"total": total_items, "hit": hit, "pairs": matched_pairs})


if __name__ == "__main__":
    main()
