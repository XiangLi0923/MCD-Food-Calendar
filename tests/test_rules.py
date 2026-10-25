# -*- coding: utf-8 -*-
"""规则测试：只跑离线快照，不依赖网络与 Token。

对应 PRD_V2 §13 的验收项：
    AC3 三方案真实差异 · AC4 随机真实性 · AC5 硬约束 · AC7 缺失诚实
    AC2 输入影响输出（用 T3 近似）

运行：python -m unittest discover -s tests -v
"""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcd_box.adapter import Adapter  # noqa: E402
from mcd_box.candidates import build  # noqa: E402
from mcd_box.enrich import enrich  # noqa: E402
from mcd_box.entry import EXCLUDE_DICT, parse_text  # noqa: E402
from mcd_box.recommend import STATE_RULES, Query, open_box  # noqa: E402

STATES = list(STATE_RULES)
FEELS = ["满足", "热乎", "清爽", "甜一点", "想尝鲜"]


def setUpModule():
    global POOL, CAT, ADAPTER
    ADAPTER = Adapter(mode="offline")
    CAT = ADAPTER.get_catalog()
    POOL, _ = build(CAT)


class TestHardConstraints(unittest.TestCase):
    def test_budget_never_exceeded(self):
        for budget in (12, 20, 30, 45):
            for state in STATES:
                q = Query(entry="intuition", state=state, budget_yuan=budget, seed=7)
                box = open_box(POOL, q, rng=random.Random(7))
                for p in box.plans:
                    self.assertIsNotNone(p.cand.price_yuan)
                    self.assertLessEqual(
                        p.cand.price_yuan, budget,
                        f"{p.cand.name} ¥{p.cand.price_yuan} 超出预算 ¥{budget}")

    def test_exclude_respected(self):
        words = EXCLUDE_DICT["牛肉"]
        for state in STATES:
            q = Query(entry="intuition", state=state, exclude=["牛肉"], seed=11)
            box = open_box(POOL, q, rng=random.Random(11))
            for p in box.plans:
                hit = [w for w in words if w in p.cand.name or w in " ".join(p.cand.tags)]
                self.assertFalse(hit, f"{p.cand.name} 命中了被排除的词 {hit}")

    def test_no_price_never_recommended(self):
        for p in open_box(POOL, Query(entry="intuition", state="累了", seed=3)).plans:
            self.assertIsNotNone(p.cand.price_yuan)


class TestDiversity(unittest.TestCase):
    def test_three_distinct_codes(self):
        for state in STATES:
            for feel in ([], ["满足"], ["想尝鲜"]):
                q = Query(entry="intuition", state=state, feel=feel, seed=42)
                box = open_box(POOL, q, rng=random.Random(42))
                codes = [p.cand.code for p in box.plans]
                self.assertEqual(len(codes), 3, f"{state}/{feel} 只出了 {len(codes)} 个方案")
                self.assertEqual(len(set(codes)), 3, f"{state}/{feel} 出现重复餐品 {codes}")

    def test_not_all_same_category(self):
        same = 0
        total = 0
        for state in STATES:
            for feel in FEELS:
                q = Query(entry="intuition", state=state, feel=[feel], seed=5)
                box = open_box(POOL, q, rng=random.Random(5))
                cats = {p.cand.category for p in box.plans}
                total += 1
                if len(cats) == 1:
                    same += 1
                    for p in box.plans:
                        self.assertTrue(p.warnings, "三者同类时必须给出警示")
        self.assertGreaterEqual((total - same) / total, 0.8,
                                f"只有 {(total - same)}/{total} 组合做到了品类不同")

    def test_no_nonfood_or_multiperson(self):
        for c in POOL:
            self.assertFalse(c.is_nonfood, f"{c.name} 是周边却进了候选池")
            self.assertFalse(c.is_multi, f"{c.name} 是多人餐却进了候选池")

    def test_meals_have_main(self):
        # 三款里至少两款是能当饭的
        for state in STATES:
            box = open_box(POOL, Query(entry="intuition", state=state, seed=9), rng=random.Random(9))
            self.assertGreaterEqual(sum(1 for p in box.plans if p.cand.is_main), 2,
                                    f"{state} 的方案里主食不足两款")


class TestInputSensitivity(unittest.TestCase):
    def test_state_changes_understand_pick(self):
        picked = set()
        for state in STATES:
            box = open_box(POOL, Query(entry="intuition", state=state, seed=123),
                           rng=random.Random(123))
            picked.add(box.plans[0].cand.code)
        self.assertGreaterEqual(len(picked), 3,
                                f"5 个状态只产生 {len(picked)} 种懂你款，区分度不够")

    def test_budget_changes_result(self):
        changed = 0
        total = 0
        for state in STATES:
            for budget in (20, 35):
                a = open_box(POOL, Query(entry="intuition", state=state, budget_yuan=None, seed=77),
                             rng=random.Random(77))
                b = open_box(POOL, Query(entry="intuition", state=state, budget_yuan=budget, seed=77),
                             rng=random.Random(77))
                total += 1
                if [p.cand.code for p in a.plans] != [p.cand.code for p in b.plans]:
                    changed += 1
        self.assertGreaterEqual(changed / total, 0.8, f"预算只影响了 {changed}/{total} 组")


class TestRandom(unittest.TestCase):
    def test_same_seed_same_box(self):
        q1 = Query(entry="random", seed=2026)
        q2 = Query(entry="random", seed=2026)
        a = open_box(POOL, q1, rng=random.Random(2026))
        b = open_box(POOL, q2, rng=random.Random(2026))
        self.assertEqual([p.cand.code for p in a.plans], [p.cand.code for p in b.plans])

    def test_seeds_give_variety(self):
        combos = set()
        for s in range(20):
            box = open_box(POOL, Query(entry="random", seed=s), rng=random.Random(s))
            combos.add(tuple(sorted(p.cand.code for p in box.plans)))
        self.assertGreaterEqual(len(combos), 8, f"20 个 seed 只有 {len(combos)} 种组合，像假随机")


class TestTextParsing(unittest.TestCase):
    CASES = [
        ("今天汇报搞砸了，想吃点满足的，别超过35元", 35, "有点低落", "满足"),
        ("太累了，随便吃点，30块以内", 30, "累了", None),
        ("心情不错，来点甜的，预算25", 25, "心情不错", "甜一点"),
        ("想奖励自己，不吃辣", None, "想奖励自己", None),
        ("来点热的，很饿", None, None, "热乎"),
    ]

    def test_slots(self):
        for text, budget, state, feel in self.CASES:
            p = parse_text(text)
            if budget is not None:
                self.assertEqual(p.query.budget_yuan, budget, f"{text} 预算解析错")
            if state is not None:
                self.assertEqual(p.query.state, state, f"{text} 状态解析错")
            if feel is not None:
                self.assertIn(feel, p.query.feel, f"{text} 感觉解析错")
            self.assertGreaterEqual(p.hit_count, 1, f"{text} 一个槽位都没抽到")

    def test_echo_always_has_five_rows(self):
        p = parse_text("随便")
        self.assertEqual(len(p.echo), 5)
        self.assertIn("我理解成这样", p.echo_text())

    def test_unresolved_when_nothing(self):
        p = parse_text("嗯")
        self.assertEqual(p.hit_count, 0)
        self.assertTrue(p.unresolved)


class TestMealsAndNutrition(unittest.TestCase):
    """组合成一顿饭 / 明细热量（新增能力，别退化）。"""

    def _plans(self, **kw):
        q = Query(entry="intuition", seed=13, **kw)
        box = open_box(POOL, q, rng=random.Random(13))
        return enrich(box, ADAPTER, CAT).plans

    def test_combo_price_equals_parts_sum(self):
        for p in self._plans(state="累了", size="很饿"):
            if p.cand.parts:
                total = round(sum(pr for _, pr in p.cand.parts), 2)
                self.assertAlmostEqual(p.cand.price_yuan, total, places=2,
                                       msg=f"{p.cand.name} 合计价与明细不相加")

    def test_combo_within_budget(self):
        for p in self._plans(state="累了", size="很饿", budget_yuan=40):
            self.assertLessEqual(p.cand.price_yuan, 40 + 0.01)

    def test_hungry_gets_multi_item_or_set(self):
        plans = self._plans(state="累了", size="很饿")
        rich = [p for p in plans if len(p.cand.parts) >= 2 or len(p.meta.get("parts", [])) >= 2]
        self.assertGreaterEqual(len(rich), 1, "饿坏了却只给了单品")

    def test_nutrition_complete_is_consistent(self):
        for p in self._plans(state="累了", size="正常"):
            nut = p.meta.get("nutrition") or {}
            parts = p.meta.get("parts") or []
            if nut.get("complete"):
                self.assertEqual(nut.get("matched"), nut.get("total"))
                self.assertIsNotNone(nut.get("kcal"))
                known = [i["kcal"] for i in parts if i.get("kcal") is not None]
                self.assertEqual(nut.get("kcal"), sum(known), "完整时热量合计应等于各项之和")
            else:
                # 不完整时前端不展示合计，这里只要求"不完整"时 matched < total
                self.assertLess(nut.get("matched", 0), max(nut.get("total", 1), 1))

    def test_every_plan_has_parts_or_known_false(self):
        for p in self._plans(state="随便", size="正常"):
            self.assertTrue(p.meta.get("parts_known") or p.meta.get("parts") == [],
                            "套餐子项状态不明")


if __name__ == "__main__":
    unittest.main(verbosity=2)
