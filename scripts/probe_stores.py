# -*- coding: utf-8 -*-
"""实测门店 -> 菜单 -> 优惠券，保存原始返回"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_mcp import McpClient, load_config, save, OUT_DIR


def call(c, name, args, tag):
    try:
        res = c.call_tool(name, args)
        save(tag, res)
        return res
    except Exception as e:
        err = {"error": str(e)}
        save(tag + "_error", err)
        print(f"[{tag}] 失败: {e}")
        return None


def extract_body(res):
    """从 MCP content text 中取出 Original Response 的 JSON"""
    try:
        text = res["result"]["content"][0]["text"]
        i = text.find("## Original Response")
        return json.loads(text[i + len("## Original Response"):].strip())
    except Exception:
        return res


def main():
    url, token = load_config()
    c = McpClient(url, token)
    c.initialize()

    print("=== query-nearby-stores (city=烟台) ===")
    res = call(c, "query-nearby-stores", {"beType": 1, "searchType": 2, "city": "烟台"}, "10_stores")
    body = extract_body(res) if res else None
    if body:
        print(json.dumps(body, ensure_ascii=False)[:1200])

    store_code = None
    if body and isinstance(body.get("data"), list) and body["data"]:
        first = body["data"][0]
        print("\n[门店字段]:", list(first.keys()))
        store_code = first.get("storeCode") or first.get("code")
        print("[选用门店]:", first.get("storeName") or first.get("name"), store_code)

    if not store_code:
        # 尝试 keyword 搜索
        print("\n=== 回退：keyword 搜索 ===")
        res = call(c, "query-nearby-stores", {"beType": 1, "searchType": 2, "keyword": "烟台"}, "10b_stores_kw")
        body = extract_body(res) if res else None
        if body:
            print(json.dumps(body, ensure_ascii=False)[:800])

    if store_code:
        print(f"\n=== query-meals (storeCode={store_code}) ===")
        res = call(c, "query-meals", {"storeCode": store_code, "orderType": 1, "beType": 1}, "11_meals")
        mbody = extract_body(res) if res else None
        if mbody:
            data = mbody.get("data", {})
            cats = data.get("categories", [])
            print(f"分类数: {len(cats)}")
            for cat in cats[:20]:
                meals = cat.get("meals", [])
                print(f"  [{cat.get('name')}] {len(meals)} 项", end="")
                if meals:
                    m = meals[0]
                    print(f"  样例字段={list(m.keys())}")
                else:
                    print()
            if cats and cats[0].get("meals"):
                print("\n首个餐品完整数据:")
                print(json.dumps(cats[0]["meals"][0], ensure_ascii=False, indent=2)[:1500])

    print("\n=== available-coupons 复测 ===")
    res = call(c, "available-coupons", {}, "12_coupons")
    if res:
        print(json.dumps(res, ensure_ascii=False)[:500])


if __name__ == "__main__":
    main()
