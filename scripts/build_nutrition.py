# -*- coding: utf-8 -*-
"""抓一次营养表，存成快照（离线也能算热量）。

产出：data/snapshot/nutrition.json
格式：给设计"套餐热量"用，必须带抓取时间，且不覆盖已有快照（--force 才覆盖）。
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from mcd_box.adapter import load_token, load_url  # noqa: E402
from mcd_box.mcp_client import McpClient  # noqa: E402

OUT = os.path.join(ROOT, "data", "snapshot", "nutrition.json")
FIELDS = ["productName", "nutritionDescription", "energyKj", "energyKcal",
          "protein", "fat", "carbohydrate", "sodium", "calcium"]


def parse_rows(raw: str) -> list[dict]:
    """麦当劳营养表返回的是一段 CSV 文本：'[160]{a,b,c}:\n名,说明,1288,308,...'"""
    rows = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line or line.startswith("["):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 9:
            continue
        rec = dict(zip(FIELDS, parts[:9]))
        try:
            rec["energyKcal"] = float(rec["energyKcal"] or 0)
            rec["protein"] = float(rec["protein"] or 0)
        except ValueError:
            continue
        rows.append(rec)
    return rows


def main() -> int:
    if os.path.exists(OUT) and "--force" not in sys.argv:
        print(f"快照已存在：{OUT}\n如需重新抓取，加 --force")
        return 0
    token = load_token()
    if not token:
        print("没有可用 Token：请设置 YOUR_MCP_TOKEN 或用已有营养快照")
        return 1
    client = McpClient(load_url(), token)
    client.initialize()
    data = client.call_tool("list-nutrition-foods", {})
    raw = data.get("data") if isinstance(data, dict) else ""
    rows = parse_rows(raw if isinstance(raw, str) else "")
    payload = {
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": "list-nutrition-foods",
        "count": len(rows),
        "rows": rows,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"营养快照已写入 {OUT}（{len(rows)} 条，抓取于 {payload['fetched_at']}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
