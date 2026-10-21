# -*- coding: utf-8 -*-
"""解析 list-nutrition-foods 原始返回，摸清字段结构"""
import json
import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
raw = os.path.join(BASE, "raw", "02_nutrition.json")

with open(raw, "r", encoding="utf-8") as f:
    obj = json.load(f)

text = obj["result"]["content"][0]["text"]
print("=== 原始文本长度:", len(text))
idx = text.find("## Original Response")
body = text[idx + len("## Original Response"):].strip()
print("=== JSON 段前 300 字符 ===")
print(body[:300])

outer = json.loads(body)
data_str = outer.get("data", "")
print("\n=== data 类型:", type(data_str), "长度:", len(data_str) if isinstance(data_str, str) else "-")
print("=== data 前 800 字符 ===")
print(data_str[:800])
