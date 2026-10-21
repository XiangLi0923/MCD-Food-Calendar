# -*- coding: utf-8 -*-
"""测 query-meal-detail 与 calculate-price，确认名称/价格链路"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_mcp import McpClient, load_config, save

STORE = "3350325"
CODES = ["9900016075"]


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
    return {"_text": text[:1200]}


def main():
    url, token = load_config()
    c = McpClient(url, token)
    c.initialize()

    # 先从菜单里多取几个 code
    res = c.call_tool("query-meals", {"storeCode": STORE, "orderType": 1, "beType": 1})
    body = extract(res)
    codes = []
    for cat in body.get("data", {}).get("categories", []):
        for m in cat.get("meals", []):
            if m.get("code"):
                codes.append((cat.get("name", "").replace("\n", ""), m["code"]))
    print(f"共 {len(codes)} 个 code，取前 6 个做详情")
    print("前 6:", codes[:6])

    details = []
    for cat, code in codes[:6]:
        try:
            res = c.call_tool("query-meal-detail", {"storeCode": STORE, "orderType": 1, "beType": 1, "code": code})
            d = extract(res)
            details.append((cat, code, d))
            print(f"\n[detail {code} / {cat}]")
            print(json.dumps(d, ensure_ascii=False)[:900])
        except Exception as e:
            print(f"[detail {code}] ERR {e}")
    save("22_meal_details", [{"category": c0, "code": c1, "detail": d} for c0, c1, d in details])

    # calculate-price 核验
    if details:
        test_code = details[0][1]
        try:
            res = c.call_tool("calculate-price", {
                "storeCode": STORE, "orderType": 1, "beType": 1,
                "items": [{"productCode": test_code, "quantity": 1}],
            })
            print(f"\n[calculate-price {test_code}]")
            print(json.dumps(extract(res), ensure_ascii=False)[:900])
            save("23_price", res)
        except Exception as e:
            print(f"[calculate-price] ERR {e}")


if __name__ == "__main__":
    main()
