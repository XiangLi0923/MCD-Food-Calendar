# -*- coding: utf-8 -*-
"""1) 完整解析 160 条营养数据为结构化 JSON；2) 打印门店/促销等工具 schema"""
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(BASE, "raw")


def parse_nutrition():
    with open(os.path.join(RAW, "02_nutrition.json"), "r", encoding="utf-8") as f:
        obj = json.load(f)
    text = obj["result"]["content"][0]["text"]
    body = text[text.find("## Original Response") + len("## Original Response"):].strip()
    data = json.loads(body)["data"]

    header_part, rows_part = data.split(":\n", 1)
    count = int(header_part[1:header_part.index("]")])
    fields = header_part[header_part.index("{") + 1:header_part.rindex("}")].split(",")

    items = []
    for line in rows_part.splitlines():
        line = line.strip()
        if not line:
            continue
        vals = [v.strip() for v in line.split(",")]
        if len(vals) != len(fields):
            continue
        rec = dict(zip(fields, vals))
        for k in fields[2:]:
            rec[k] = int(rec[k]) if rec[k].isdigit() else None
        items.append(rec)

    with open(os.path.join(RAW, "nutrition_parsed.json"), "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    print(f"声明条数={count} 解析条数={len(items)}")
    print("字段:", fields)

    mains = [i for i in items if any(k in i["productName"] for k in ("堡", "卷", "饭", "鸡"))]
    print(f"\n主食类（含堡/卷/饭/鸡）: {len(mains)} 条，抽样：")
    for i in mains[:12]:
        print(f"  {i['productName']}: {i['energyKcal']}kcal 蛋白{i['protein']}g 脂肪{i['fat']}g 钠{i['sodium']}mg")

    kcal = [i for i in items if i["energyKcal"]]
    print(f"\n热量范围: {min(i['energyKcal'] for i in kcal)} ~ {max(i['energyKcal'] for i in kcal)} kcal")
    print(f"蛋白最高 top5: {sorted(kcal, key=lambda x: x['protein'] or 0, reverse=True)[:5]}")
    lowfat = sorted([i for i in kcal if i["fat"]], key=lambda x: x["fat"])[:5]
    print(f"脂肪最低 top5: {[(i['productName'], i['fat'], i['protein'], i['sodium']) for i in lowfat]}")
    return items


def show_schemas():
    with open(os.path.join(RAW, "01_tools_list.json"), "r", encoding="utf-8") as f:
        obj = json.load(f)
    want = {"query-nearby-stores", "query-promotions", "campaign-calendar",
            "query-store-coupons", "available-coupons", "order-list"}
    print("\n=== 相关工具 schema ===")
    for t in obj["result"]["tools"]:
        if t["name"] in want:
            props = t.get("inputSchema", {}).get("properties", {})
            req = t.get("inputSchema", {}).get("required", [])
            print(f"\n[{t['name']}] required={req}")
            for k, v in props.items():
                print(f"   - {k}: {v.get('description', '')[:110]}")


if __name__ == "__main__":
    parse_nutrition()
    show_schemas()
