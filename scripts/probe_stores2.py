# -*- coding: utf-8 -*-
"""门店搜索参数组合探测"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_mcp import McpClient, load_config, save


def brief(res):
    try:
        sc = res["result"].get("structuredContent")
        if sc:
            return json.dumps(sc, ensure_ascii=False)[:400]
        return res["result"]["content"][0]["text"][-400:]
    except Exception:
        return json.dumps(res, ensure_ascii=False)[:400]


def main():
    url, token = load_config()
    c = McpClient(url, token)
    c.initialize()

    combos = [
        ("A cityName", {"beType": 1, "searchType": 2, "cityName": "烟台"}),
        ("B keyword+city", {"beType": 1, "searchType": 2, "keyword": "麦当劳", "city": "烟台"}),
        ("C searchType1", {"beType": 1, "searchType": 1}),
        ("D city 烟台市", {"beType": 1, "searchType": 2, "city": "烟台市"}),
        ("E keyword only", {"beType": 1, "searchType": 2, "keyword": "麦当劳"}),
        ("F 定位", {"beType": 1, "searchType": 2, "city": "烟台", "latitude": 37.4638, "longitude": 121.4479}),
    ]
    for label, args in combos:
        try:
            res = c.call_tool("query-nearby-stores", args)
            print(f"\n[{label}] {brief(res)}")
            save(f"13_stores_{label.split()[0]}", res)
        except Exception as e:
            print(f"\n[{label}] ERR {e}")

    # 外送门店接口
    try:
        res = c.call_tool("delivery-query-stores", {"beType": 2, "orderType": 2, "city": "烟台"})
        print(f"\n[delivery-query-stores city] {brief(res)}")
        save("14_delivery_stores", res)
    except Exception as e:
        print(f"\n[delivery] ERR {e}")


if __name__ == "__main__":
    main()
