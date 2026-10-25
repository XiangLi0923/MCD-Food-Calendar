# -*- coding: utf-8 -*-
"""命令行入口：开盒 / 重开 / 换条件。

用法示例：
    python -m mcd_box.cli --state 累了 --feel 满足
    python -m mcd_box.cli --text "今天汇报搞砸了，想吃点满足的，别超过35元"
    python -m mcd_box.cli --random
    python -m mcd_box.cli --state 想奖励自己 --budget 40 --offline
    python -m mcd_box.cli --state 累了 --seed 1730000000000   # 复现同一盒
    python -m mcd_box.cli --random --json
"""
from __future__ import annotations

import argparse
import json
import random
import sys

from .adapter import DEFAULT_STORE, Adapter
from .candidates import build
from .enrich import enrich
from .entry import describe_inputs, intuition_query, parse_text, random_query, validate
from .recommend import open_box
from .render import render_box, render_json


def _split(v: str | None) -> list[str]:
    if not v:
        return []
    return [x.strip() for x in v.replace("，", ",").split(",") if x.strip()]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mcd_box", description="麦麦食历：今天吃什么，让魔盒替你少想一步")
    p.add_argument("--store", default=DEFAULT_STORE, help=f"门店编码（默认 {DEFAULT_STORE}）")
    p.add_argument("--state", help="当下状态：累了 / 心情不错 / 有点低落 / 想奖励自己 / 就想简单解决")
    p.add_argument("--feel", help="想吃的感觉，逗号分隔：满足,热乎,清爽,甜一点,想尝鲜")
    p.add_argument("--size", help="份量：垫一下 / 正常 / 很饿")
    p.add_argument("--budget", type=float, help="预算上限（元）。不填 = 不限")
    p.add_argument("--exclude", help="不吃什么，逗号分隔：牛肉,辣,冰,咖啡,猪肉,鱼")
    p.add_argument("--text", help="用一句话说（入口 B）")
    p.add_argument("--random", action="store_true", help="直接开盒，什么都不说（入口 C）")
    p.add_argument("--seed", type=int, help="固定随机种子，可复现同一盒")
    p.add_argument("--offline", action="store_true", help="只读 data/snapshot 快照")
    p.add_argument("--json", action="store_true", help="输出 JSON")
    p.add_argument("--echo-only", action="store_true", help="只显示文本解析结果，不出方案")
    return p


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    args = build_parser().parse_args(argv)

    # 入口 B：先解析、先回显
    parsed = None
    if args.text:
        parsed = parse_text(args.text, store=args.store)
        if not args.json:
            print(parsed.echo_text())
            if parsed.unresolved:
                print(f"  （{parsed.unresolved[0]}，可以直接用参数补充，或改用标签）")
            print()
            if parsed.hit_count == 0 and not (args.state or args.feel or args.budget):
                print("没读到可用的限制。用 --state / --feel / --budget 走标签更快。")
        if args.echo_only:
            return 0
        q = parsed.query
        # 命令行参数可覆盖解析结果，方便"确认后修改"
        q.state = args.state or q.state
        q.feel = _split(args.feel) or q.feel
        q.size = args.size or q.size
        q.budget_yuan = args.budget if args.budget is not None else q.budget_yuan
        q.exclude = _split(args.exclude) or q.exclude
    elif args.random:
        q = random_query(store=args.store, budget=args.budget, exclude=_split(args.exclude))
    else:
        q = intuition_query(store=args.store, budget=args.budget, exclude=_split(args.exclude),
                            state=args.state, feel=_split(args.feel), size=args.size)

    problems = validate(q)
    if problems:
        for x in problems:
            print(f"输入有问题：{x}", file=sys.stderr)
        return 2

    ad = Adapter(store=args.store, mode="offline" if args.offline else "auto")
    try:
        cat = ad.get_catalog()
    except Exception as e:  # 取数失败不静默
        print(f"取数失败：{e}", file=sys.stderr)
        print("可以加 --offline 用本地快照先看效果。", file=sys.stderr)
        return 1

    pool, _stats = build(cat)
    q.seed = args.seed if args.seed is not None else random.SystemRandom().randrange(10 ** 12)
    box = open_box(pool, q, rng=random.Random(q.seed))
    box = enrich(box, ad, cat)

    if args.json:
        print(json.dumps(render_json(box, q, cat), ensure_ascii=False, indent=2))
    else:
        print(render_box(box, q, cat, describe_inputs(q)))
        print("\n想换一盒：再跑一次（会自动换 seed）；想复现这盒：加 --seed {}".format(box.seed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
