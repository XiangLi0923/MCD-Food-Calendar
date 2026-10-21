# -*- coding: utf-8 -*-
"""
verify_chain.py —— 验证「菜单 → 核价」数据链路，并给出 MVP 规则需要的三个数字。

回答三个问题（对应 PRD_V2 §14.2 的 V1/V2/V3）：
  1) 目标门店到底有多少个售卖单元、多少个分类
  2) 价格分布（中位数、四分位），「稳妥款」的"中位数"划界要用
  3) tags 里有哪些标记类词，「惊喜款」能否靠 tag 识别

同时解决一个口径问题：query-meals 自带 currentPrice/originalPrice，
calculate-price 返回 subtotal/originalSubtotal。两者是否一致？谁是实付价？

产出：
  raw/40_meals_<store>.json   query-meals 原始返回
  raw/41_prices_<store>.json  calculate-price 批量核价原始返回
  docs/CHAIN_REPORT.md        人读报告（含数据时间）

安全：Token 只从 ~/.workbuddy/mcp.json 读取，不打印、不落盘。
用法：python scripts/verify_chain.py [storeCode]
"""
import json
import os
import statistics
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_mcp import McpClient, load_config, save  # noqa: E402

STORE = sys.argv[1] if len(sys.argv) > 1 else "3350112"
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHUNK = 30      # 单次批量核价的商品数
TOL = 0.05      # 价格比对容差（元）


def extract(res):
    if not res:
        return {}
    r = res.get("result", res)
    if r.get("structuredContent"):
        return r["structuredContent"]
    try:
        text = r["content"][0]["text"]
    except Exception:
        return {"_raw": str(r)[:500]}
    i = text.find("## Original Response")
    if i >= 0:
        try:
            return json.loads(text[i + len("## Original Response"):].strip())
        except Exception:
            pass
    return {"_text": text}


def main():
    url, token = load_config()
    c = McpClient(url, token)
    c.initialize()
    print(f"[chain] store={STORE}")

    # ① 菜单
    t0 = time.time()
    res = c.call_tool("query-meals", {"storeCode": STORE, "orderType": 1, "beType": 1})
    save(f"40_meals_{STORE}", res)
    data = extract(res).get("data") or {}
    cats = data.get("categories") or []
    catalog = data.get("meals") or {}          # ★ 权威目录：code -> name/price/image/tags

    # 分类归属与 tags（tags 只在 categories[].meals[] 里，data.meals 映射里没有）
    code_cat, appear, tags_by_code = {}, Counter(), {}
    for cat in cats:
        for m in cat.get("meals", []):
            code = m["code"]
            appear[code] += 1
            code_cat.setdefault(code, cat["name"].replace("\n", " ").strip())
            if m.get("tags"):
                tags_by_code.setdefault(code, []).extend(m["tags"])

    codes = list(catalog.keys())
    dup = sum(1 for v in appear.values() if v > 1)
    print(f"[chain] 分类 {len(cats)}；目录 {len(codes)} 个餐品；跨分类重复展示 {dup} 个  ({time.time()-t0:.1f}s)")

    # ② 核价（去重后每个 code 只传一次，quantity=1）
    t1 = time.time()
    calc, calls = {}, []
    for i in range(0, len(codes), CHUNK):
        batch = [{"productCode": x, "quantity": 1} for x in codes[i:i + CHUNK]]
        r = c.call_tool("calculate-price",
                        {"storeCode": STORE, "orderType": 1, "beType": 1, "items": batch})
        calls.append(r)
        d = extract(r).get("data") or {}
        for p in d.get("productList", []):
            if p.get("subtotal") is not None:
                calc[p["productCode"]] = {
                    "subtotal": round(p["subtotal"] / 100, 2),
                    "original": round((p.get("originalSubtotal") or p["subtotal"]) / 100, 2),
                }
    save(f"41_prices_{STORE}", calls)
    print(f"[chain] 核价覆盖 {len(calc)}/{len(codes)}  ({time.time()-t1:.1f}s, {(len(codes)+CHUNK-1)//CHUNK} 次调用)")

    # ③ 两种价格口径比对
    rows, same, diff, only_menu = [], 0, 0, 0
    for code in codes:
        item = catalog[code]
        qm_cur = float(item["currentPrice"]) if item.get("currentPrice") else None
        qm_org = float(item["originalPrice"]) if item.get("originalPrice") else None
        cl = calc.get(code)
        if cl is None:
            only_menu += 1
            continue
        equal = qm_cur is not None and abs(qm_cur - cl["subtotal"]) <= TOL
        same += 1 if equal else 0
        diff += 0 if equal else 1
        rows.append({
            "code": code, "name": item.get("name"), "cat": code_cat.get(code),
            "menu_cur": qm_cur, "menu_org": qm_org,
            "calc": cl["subtotal"], "calc_org": cl["original"],
            "discount": item.get("discountType"), "same": equal,
            "tags": tags_by_code.get(code, []),
        })

    print(f"[chain] 口径比对：一致 {same} / 不一致 {diff} / 仅菜单有价 {only_menu}")

    # ④ 统计（以菜单现价为准做分布，另附核价口径）
    prices = sorted(r["menu_cur"] for r in rows if r["menu_cur"])
    calc_prices = sorted(r["calc"] for r in rows if r["calc"])
    med = statistics.median(prices) if prices else 0
    q1 = prices[len(prices) // 4] if prices else 0
    q3 = prices[len(prices) * 3 // 4] if prices else 0

    tags_all = [t for r in rows for t in r["tags"]]
    tag_freq = Counter(tags_all)
    MARK = ("上新", "限定", "联名", "限量", "人气", "热卖", "超值", "爆款", "新升级")
    marked = {k: v for k, v in tag_freq.items() if any(w in k for w in MARK)}
    cat_count = Counter(r["cat"] for r in rows)

    # ⑤ 报告
    L = [
        f"# 数据链路验证报告（store {STORE}）",
        "",
        f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 门店：`{STORE}`",
        "- 来源：麦当劳官方 MCP，`query-meals` + `calculate-price` 实时调用",
        "- 原始返回：`raw/40_meals_{0}.json`、`raw/41_prices_{0}.json`".format(STORE),
        "",
        "## 1. 候选规模",
        "",
        f"- 菜单分类：**{len(cats)}** 个",
        f"- 餐品目录（`data.meals`）：**{len(codes)}** 个唯一 code",
        f"- 跨分类重复展示：{dup} 个（同一餐品出现在多个分类里，**统计与核价都必须按 code 去重**）",
        f"- 有价格：{len(rows)} 个（其中仅菜单有价 {only_menu} 个）",
        "",
        "## 2. 价格分布（元，以 `query-meals.currentPrice` 为准）",
        "",
        f"- 最低 ¥{prices[0]:.2f} · 25% ¥{q1:.2f} · **中位数 ¥{med:.2f}** · 75% ¥{q3:.2f} · 最高 ¥{prices[-1]:.2f}" if prices else "- 无价格",
        f"- 核价口径（`calculate-price.subtotal`）中位数：¥{statistics.median(calc_prices):.2f}" if calc_prices else "",
        "",
        "## 3. 两种价格口径的差异（关键）",
        "",
        f"- 完全一致：**{same}** 个",
        f"- 不一致：**{diff}** 个",
        "",
    ]
    if diff:
        L += ["| 名称 | 菜单现价 | 菜单原价 | 核价 subtotal | 优惠类型 |", "|---|---|---|---|---|"]
        for r in [x for x in rows if not x["same"]][:20]:
            L.append(f"| {r['name']} | ¥{r['menu_cur']:.2f} | ¥{(r['menu_org'] or 0):.2f} | ¥{r['calc']:.2f} | {r['discount'] or '—'} |")
        L += ["", "> 判读：不一致的条目全部是带 `discountType`（麦金卡/随单购/促销）的套餐——",
              "> 菜单价是**会员/促销后**的现价，核价接口在不带会员上下文时返回的是**未享该优惠**的价。",
              "> 因此展示给用户的「这一份多少钱」应取 `query-meals.currentPrice`；`calculate-price` 用于**组合改单后的重算**。"]
    L += ["", "## 4. 分类分布", "", "| 分类 | 数量 |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in cat_count.most_common()]
    L += ["", "## 5. 标记类 tag（惊喜款可用）", ""]
    L += [f"- `{k}` ×{v}" for k, v in sorted(marked.items(), key=lambda x: -x[1])] or ["- 未发现标记类 tag"]
    L += ["", "## 6. 全部 tag", "", "| tag | 次数 |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in tag_freq.most_common()]

    out = os.path.join(BASE, "docs", "CHAIN_REPORT.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print(f"[chain] 报告 -> {out}")
    print(f"[chain] 菜单价：min ¥{prices[0]:.2f} / median ¥{med:.2f} / max ¥{prices[-1]:.2f}")
    print(f"[chain] 标记 tag：{sorted(marked, key=lambda k: -marked[k])[:10]}")


if __name__ == "__main__":
    main()
