# -*- coding: utf-8 -*-
"""抓一次真实菜单，存成离线快照。

快照是离线演示与评审复现的唯一数据来源：必须带抓取时间，且默认**不覆盖**已有快照
（--force 才覆盖，避免把旧的演示数据冲掉）。

用法：
    python scripts/build_snapshot.py            # 门店 3350112
    python scripts/build_snapshot.py 3350325    # 指定其他门店
    python scripts/build_snapshot.py --force    # 覆盖
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from mcd_box.adapter import (  # noqa: E402
    DEFAULT_STORE, DEFAULT_STORE_NAME, SNAPSHOT_DIR, Adapter,
)


def main() -> int:
    force = "--force" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    store = args[0] if args else DEFAULT_STORE

    path = os.path.join(SNAPSHOT_DIR, f"{store}.json")
    if os.path.exists(path) and not force:
        print(f"快照已存在：{path}\n如需重新抓取，加 --force")
        return 0

    ad = Adapter(store=store, mode="online", use_cache=False)
    cat = ad.get_catalog()
    if store == DEFAULT_STORE:
        cat.store_name = DEFAULT_STORE_NAME
    cat.source = "snapshot"

    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cat.to_dict(), f, ensure_ascii=False, indent=2)

    priced = [i.price_yuan for i in cat.items if i.price_yuan is not None]
    print(f"快照已写入 {path}")
    print(f"  门店 {cat.store} {cat.store_name}")
    print(f"  抓取时间 {cat.fetched_at}")
    print(f"  条目 {len(cat.items)} · 有价 {len(priced)} · 分类 {len(cat.categories)}")
    if priced:
        print(f"  价格区间 ¥{min(priced):.2f} – ¥{max(priced):.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
