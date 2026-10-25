# -*- coding: utf-8 -*-
"""把"套餐含什么"抓成快照：离线时也能看到每个套餐的子项与热量。

只抓套餐类（名称含 套餐/三件套/四件套/随心配/组合/双拼），单品不需要展开。
产出：data/snapshot/details_<store>.json
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mcd_box.adapter import DEFAULT_STORE, DEFAULT_STORE_NAME, SNAPSHOT_DIR, Adapter  # noqa: E402

SET_WORDS = ("套餐", "三件套", "四件套", "随心配", "组合", "双拼")


def main() -> int:
    force = "--force" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    store = args[0] if args else DEFAULT_STORE
    out = os.path.join(SNAPSHOT_DIR, f"details_{store}.json")
    if os.path.exists(out) and not force:
        print(f"快照已存在：{out}\n如需重新抓取，加 --force")
        return 0

    cat = Adapter(store=store, mode="online", use_cache=False).get_catalog()
    if store == DEFAULT_STORE:
        cat.store_name = DEFAULT_STORE_NAME
    codes = [i.code for i in cat.items if any(w in i.name for w in SET_WORDS)]
    print(f"门店 {store}：待展开套餐 {len(codes)} 个")

    ad = Adapter(store=store, mode="online", use_cache=False)
    items = {}
    for code in codes:
        got = ad.get_detail_items([code])
        items.update(got)
    payload = {"fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "items": items}
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    ok = sum(1 for v in items.values() if v)
    print(f"已写入 {out}：{ok}/{len(codes)} 个套餐拿到子项")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
