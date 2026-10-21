# -*- coding: utf-8 -*-
"""深挖「500大卡套餐」：结构、价格、以及用营养表验证其真实热量"""
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


def norm(s):
    return s.replace(" ", "").replace("（", "(").replace("）", ")")


def main():
    with open(os.path.join(RAW, "20_meals.json"), "r", encoding="utf-8") as f:
        meals = extract(json.load(f))
    with open(os.path.join(RAW, "nutrition_parsed.json"), "r", encoding="utf-8") as f:
        nutrition = json.load(f)

    nut = {norm(n["productName"]): n for n in nutrition}

    target = None
    for cat in meals["data"]["categories"]:
        if "500" in cat["name"]:
            target = cat
            break

    if not target:
        print("未找到 500 大卡分类")
        return

    codes = [m["code"] for m in target["meals"]]
    print(f"分类名: {target['name'].strip()}  餐品数: {len(codes)}")
    print("codes:", codes)

    url, token = load_config()
    c = McpClient(url, token)
    c.initialize()

    # 批量核价
    batch = [{"productCode": x, "quantity": 1} for x in codes]
    res = c.call_tool("calculate-price", {"storeCode": STORE, "orderType": 1, "beType": 1, "items": batch})
    pb = extract(res)
    price_map = {p["productCode"]: p["subtotal"] for p in pb.get("data", {}).get("productList", [])}
    save("30_500kcal_price", res)

    all_detail = []
    for code in codes:
        res = c.call_tool("query-meal-detail", {"storeCode": STORE, "orderType": 1, "beType": 1, "code": code})
        d = extract(res).get("data") or {}
        all_detail.append(d)

        name = d.get("name", "?")
        price = price_map.get(code, 0) / 100
        print(f"\n{'='*60}\n[{name}]  ¥{price:.2f}  (code={code})")
        total_kcal = total_protein = total_fat = total_sodium = 0
        matched = 0
        miss = []
        for r in d.get("rounds", []):
            print(f"  · {r.get('name')}")
            for ch in r.get("choices", []):
                if ch.get("quantity", 0) > 0 and ch.get("isDefault") == 1:
                    cname = ch.get("name", "")
                    n = nut.get(norm(cname))
                    if n:
                        matched += 1
                        total_kcal += n["energyKcal"] or 0
                        total_protein += n["protein"] or 0
                        total_fat += n["fat"] or 0
                        total_sodium += n["sodium"] or 0
                        print(f"      - {cname} [{n['energyKcal']}kcal 蛋白{n['protein']}g 脂肪{n['fat']}g 钠{n['sodium']}mg]")
                    else:
                        miss.append(cname)
                        print(f"      - {cname} [营养缺失]")
        print(f"  => 默认组合合计: {total_kcal} kcal / 蛋白 {total_protein}g / 脂肪 {total_fat}g / 钠 {total_sodium}mg")
        if miss:
            print(f"  => 未匹配子项: {miss}")

    save("31_500kcal_details", all_detail)


if __name__ == "__main__":
    main()
