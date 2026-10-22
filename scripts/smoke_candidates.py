# -*- coding: utf-8 -*-
"""冒烟测试：取数 → 候选构建，打印一份人看得懂的清单。

用法：
    python scripts/smoke_candidates.py            # 有网走在线/cache，没网自动退快照
    python scripts/smoke_candidates.py --offline  # 只读 data/snapshot
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from mcd_box.adapter import Adapter, DEFAULT_STORE  # noqa: E402
from mcd_box.candidates import build  # noqa: E402


def main() -> int:
    offline = "--offline" in sys.argv
    store = DEFAULT_STORE
    for a in sys.argv[1:]:
        if a.isdigit():
            store = a

    ad = Adapter(store=store, mode="offline" if offline else "auto")
    cat = ad.get_catalog()
    print(f"门店 {cat.store} {cat.store_name}")
    print(f"来源 {cat.source} · 抓取于 {cat.fetched_at} · 分类 {len(cat.categories)} 个 · 原始条目 {len(cat.items)} 个")

    dup = [i for i in cat.items if i.category_hits > 1]
    print(f"跨分类重复展示：{len(dup)} 个（已按 code 去重，不重复计数）")

    pool, st = build(cat)
    print("\n候选统计")
    print(f"  单人候选 {st['pool']} / 总数 {st['total']}（剔除多人餐 {st['dropped_multi']}，无价格 {st['no_price']}）")
    print(f"  份量带：light {st['light']} · normal {st['normal']} · big {st['big']}")
    print(f"  标记：上新/限定 {st['new']} · 人气/热卖 {st['pop']} · 覆盖分类 {st['categories']}")

    print("\n价格最低 5 个")
    for c in sorted([x for x in pool if x.has_price], key=lambda x: x.price_yuan)[:5]:
        print(f"  {c}")
    print("\n价格最高 5 个")
    for c in sorted([x for x in pool if x.has_price], key=lambda x: -x.price_yuan)[:5]:
        print(f"  {c}")
    print("\n带『上新/限定』的候选")
    for c in [x for x in pool if x.is_new][:10]:
        print(f"  [{c.category}] {c}")
    if not [x for x in pool if x.is_new]:
        print("  （无）")

    print("\n各分类候选数")
    from collections import Counter
    for k, v in Counter(c.category for c in pool).most_common():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
