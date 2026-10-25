# -*- coding: utf-8 -*-
"""把候选池升级成「一顿饭」。

为什么需要这层（用户实测反馈）：
  单推一个厚牛堡、一杯咖啡、一份随心配，都不算"一顿饭"——
  吃不饱、不像样，决策疲劳没被真正解决。

规则（全部基于真实菜单价，合计 = 各部分相加，超预算自动降配）：
  垫一下 → 保留轻量单品，不凑组合
  正常（或不选份量）→ 主食 + 小食，或官方套餐
  很饿         → 主食 + 小食 + 饮品，或官方四件套
  减脂/清爽    → 小食优先 玉米杯/苹果片/脆薯，饮品优先 无糖/纯悦/柠檬茶/美式
  甜一点       → 小食优先 派/新地/麦旋风，饮品优先 奶铁/朱古力
"""
from __future__ import annotations

from .candidates import Candidate, SIZE_BIG_MIN, SIZE_LIGHT_MAX

SET_WORDS = ("套餐", "三件套", "四件套", "随心配", "组合", "双拼")
DRINK_CATS = {"饮品", "麦咖啡™"}
SIDE_CATS = {"小食甜品 /其他", "小食拼盘 /多人餐", "开心乐园"}
FRIED_SIDE_WORDS = ("鸡翅", "鸡块", "鸡球", "脆汁鸡", "V翅", "鸡排", "鸡腿")

# 每种感觉对应的小食 / 饮品偏好词（按优先级）
SIDE_PREF = {
    "清爽": ["玉米", "苹果", "脆薯"],
    "甜一点": ["派", "新地", "麦旋风", "冰淇淋"],
    "满足": ["薯条", "鸡块", "鸡翅"],
    "想尝鲜": ["芝士条", "鸡球", "脆薯"],
    "热乎": ["鸡块", "薯条"],
}
DRINK_PREF = {
    "清爽": ["无糖", "纯悦", "柠檬", "美式", "苹果汁"],
    "热乎": ["热牛奶", "热拿铁", "豆浆", "朱古力", "热美式"],
    "甜一点": ["奶铁", "朱古力", "橙", "麦旋风"],
    "满足": ["可乐", "雪碧"],
}
SIDE_DEFAULT = ["薯条", "鸡块", "玉米"]
DRINK_DEFAULT = ["可乐", "雪碧", "柠檬红茶"]


def classify(c: Candidate) -> str:
    if any(w in c.name for w in SET_WORDS):
        return "set"
    if c.category in DRINK_CATS:
        return "drink"
    if c.category in SIDE_CATS:
        return "side"
    if c.category == "炸鸡" and any(w in c.name for w in FRIED_SIDE_WORDS):
        return "side"
    if c.is_main:
        return "main"
    return "side"


def _band(price: float) -> str:
    if price < SIZE_LIGHT_MAX:
        return "light"
    if price > SIZE_BIG_MIN:
        return "big"
    return "normal"


def _pref_words(q, table: dict, default: list[str]) -> list[str]:
    for feel in q.feel:
        if feel in table:
            return table[feel]
    return default


def _pick(items: list[Candidate], budget_left: float | None, priority: list[str]) -> Candidate | None:
    """在预算内选一个：优先命中偏好词，其次最接近预算的（不浪费钱）。"""
    ok = [c for c in items if c.price_yuan is not None
          and (budget_left is None or c.price_yuan <= budget_left + 0.01)]
    if not ok:
        return None
    for w in priority:
        hit = [c for c in ok if w in c.name]
        if hit:
            return max(hit, key=lambda c: c.price_yuan)  # 同样命中时选贵一点的，份量更足
    return max(ok, key=lambda c: c.price_yuan)


def _combo(main: Candidate, side: Candidate | None, drink: Candidate | None) -> Candidate:
    parts = [(main.name, main.price_yuan)]
    if side:
        parts.append((side.name, side.price_yuan))
    if drink:
        parts.append((drink.name, drink.price_yuan))
    total = round(sum(p for _, p in parts), 2)
    return Candidate(
        code=f"combo:{main.code}", name=" + ".join(n for n, _ in parts),
        category=main.category, tags=main.tags,
        price_yuan=total, original_yuan=None, discount_type=None, image=main.image,
        size_band=_band(total), is_new=main.is_new, is_pop=main.is_pop,
        is_multi=False, is_nonfood=False, is_main=True,
        main_code=main.code, parts=tuple(parts),
    )


def build_meals(pool: list[Candidate], q) -> list[Candidate]:
    """pool 必须是已经过硬过滤（预算/忌口/无价剔除）的候选。"""
    sets = [c for c in pool if classify(c) == "set"]
    mains = [c for c in pool if classify(c) == "main"]
    sides = [c for c in pool if classify(c) == "side"]
    drinks = [c for c in pool if classify(c) == "drink"]
    budget = q.budget_yuan

    if q.size == "垫一下":
        light = [c for c in pool if c.size_band == "light"]
        return light or pool

    side_pri = _pref_words(q, SIDE_PREF, SIDE_DEFAULT)
    drink_pri = _pref_words(q, DRINK_PREF, DRINK_DEFAULT)

    meals = list(sets)
    for m in mains:
        left = (budget - m.price_yuan) if (budget is not None and m.price_yuan is not None) else None
        side = _pick(sides, left, side_pri)
        if side:
            left = (left - side.price_yuan) if left is not None else None
        drink = None
        if q.size == "很饿":
            drink = _pick(drinks, left, drink_pri)
        if side or drink:
            combo = _combo(m, side, drink)
            if budget is not None and combo.price_yuan > budget + 0.01:
                if drink:      # 超预算：先减饮品
                    combo = _combo(m, side, None)
            if budget is not None and combo.price_yuan > budget + 0.01:
                continue       # 再超就放弃这条组合
            meals.append(combo)
        elif budget is None:
            meals.append(m)    # 没配到小食的单品主食，仅在无预算限制时保留
    return meals
