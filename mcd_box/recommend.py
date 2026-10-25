# -*- coding: utf-8 -*-
"""推荐规则：硬过滤 → 懂你 / 稳妥 / 惊喜 → 差异化校验 → 随机采样。

设计原则（PRD v2.1 §9）：
  - 不用综合评分。三条规则各自只看一件事：懂你看状态、稳妥看结构、惊喜看差异。
  - 每个方案的理由只能引用三类事实：用户说的话 / 接口给的数据 / 实际执行的规则。
  - 硬约束（预算、排除项）绝不放宽，凑不够三个就少给一个并说明。

状态与感觉的词表是**产品偏好设置**，不是对用户的心理判断，也不用来推断营养需要。
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .candidates import Candidate
from .meals import build_meals

# ---------------------------------------------------------------- 词表
# 状态 → 推荐倾向。只影响"往哪类餐品倾斜"，不做情绪分析、不推营养。
STATE_RULES: dict[str, dict] = {
    "累了":      {"words": ("堡", "卷", "鸡块", "派", "薯条"), "note": "单手能吃的"},
    "心情不错":  {"words": ("三件套", "四件套", "麦旋风", "新地", "拿铁", "咖啡"), "note": "有点仪式感的"},
    "有点低落":  {"words": ("堡", "粥", "热", "奶", "咖啡", "红茶"), "note": "热乎扎实的"},
    "想奖励自己": {"words": ("安格斯", "厚牛", "双层", "四件套", "限定", "联名"), "note": "贵一点、特别一点的"},
    "就想简单解决": {"words": ("随心配", "单品", "三件套", "圆筒", "派"), "note": "步骤少的"},
}

# 感觉 → 命中词（同时看名称与 tags）
FEEL_RULES: dict[str, tuple[str, ...]] = {
    "满足": ("堡", "牛", "鸡", "薯条", "鸡块", "安格斯", "炸", "脆"),
    "热乎": ("热", "咖", "奶", "粥", "堡", "红茶"),
    "清爽": ("玉米", "苹果", "柠檬", "茶", "脆薯", "沙拉"),
    "甜一点": ("冰淇淋", "新地", "麦旋风", "派", "朱古力", "甜", "橙"),
    "想尝鲜": ("上新", "限定", "联名", "限量", "新"),
}

SET_WORDS = ("套餐", "三件套", "四件套", "随心配", "组合", "双拼")
SIZE_LABEL = {"light": "垫一下", "normal": "正常", "big": "很饿", None: ""}

ROLE_LABEL = {"understand": "懂你款", "safe": "稳妥款", "surprise": "惊喜款"}


# ---------------------------------------------------------------- 结构
@dataclass
class Query:
    store: str = ""
    entry: str = "intuition"          # intuition | text | random
    budget_yuan: float | None = None  # None = 不限（不假定消费能力）
    exclude: list[str] = field(default_factory=list)
    state: str | None = None
    feel: list[str] = field(default_factory=list)
    size: str | None = None
    seed: int | None = None
    raw_text: str = ""                # 入口 B 的原话，仅留档

    def with_seed(self, seed: int) -> "Query":
        q = Query(**{**self.__dict__})
        q.seed = seed
        return q


@dataclass
class Plan:
    role: str
    label: str
    cand: Candidate
    reason: str
    matched: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class Box:
    plans: list[Plan]
    pool_size: int
    seed: int
    notes: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


# ---------------------------------------------------------------- 工具
def _text(c: Candidate) -> str:
    return f"{c.name} {' '.join(c.tags)}"


def _hits(c: Candidate, words: tuple[str, ...]) -> int:
    t = _text(c)
    return sum(1 for w in words if w in t)


def _mkey(c: Candidate) -> str:
    """去重主键：组合餐按主商品算，避免「板烧+薯条」和「板烧+玉米」被当成两款。"""
    return c.main_code or c.code


def _has_set(c: Candidate) -> bool:
    return any(w in c.name for w in SET_WORDS)


def _median(pool: list[Candidate]) -> float:
    prices = sorted(c.price_yuan for c in pool if c.price_yuan is not None)
    if not prices:
        return 0.0
    return prices[len(prices) // 2]


def _yuan(v: float | None) -> str:
    return f"¥{v:.2f}" if v is not None else "价格待确认"


# ---------------------------------------------------------------- 硬过滤
def _exclude_words(q: Query) -> tuple[str, ...]:
    """把「牛肉」这类分类键展开成实际要匹配的词（牛肉/牛堡/安格斯/巨无霸…）。

    坑：如果只拿 "牛肉" 去子串匹配，"芝士安格斯厚牛堡" 会漏过去。
    """
    from .entry import EXCLUDE_DICT   # 延迟导入，避免 entry ↔ recommend 循环

    words: list[str] = []
    for key in q.exclude:
        words.extend(EXCLUDE_DICT.get(key, (key,)))
    return tuple(dict.fromkeys(w for w in words if w))


def hard_filter(pool: list[Candidate], q: Query) -> tuple[list[Candidate], list[str]]:
    """只做用户明确要求的过滤。返回 (通过, 说明)。"""
    out, notes = [], []
    dropped_budget = dropped_exclude = dropped_price = 0
    ex_words = _exclude_words(q)

    for c in pool:
        if q.budget_yuan is not None and c.price_yuan is not None and c.price_yuan > q.budget_yuan:
            dropped_budget += 1
            continue
        if ex_words:
            t = _text(c) + c.category
            if any(w in t for w in ex_words):
                dropped_exclude += 1
                continue
        if c.price_yuan is None:
            dropped_price += 1          # 没价格就不进推荐，避免"多少钱"答不上来
            continue
        out.append(c)

    if dropped_budget:
        notes.append(f"预算 {_yuan(q.budget_yuan)} 内筛掉 {dropped_budget} 个超价餐品")
    if dropped_exclude:
        notes.append(f"按排除项 {q.exclude} 筛掉 {dropped_exclude} 个")
    if dropped_price:
        notes.append(f"{dropped_price} 个餐品没有价格，未进推荐")
    return out, notes


# ---------------------------------------------------------------- 三条规则
def _score_understand(c: Candidate, q: Query) -> tuple[float, list[str]]:
    score, matched = 0.0, []
    rule = STATE_RULES.get(q.state or "")
    if rule:
        h = _hits(c, rule["words"])
        if h:
            score += 3.0 * h
            matched.append(q.state)
    for feel in q.feel:
        h = _hits(c, FEEL_RULES.get(feel, ()))
        if h:
            score += 2.0 * h
            matched.append(feel)
    if q.size:
        want = {"垫一下": "light", "正常": "normal", "很饿": "big"}[q.size]
        if c.size_band == want:
            score += 1.5
            matched.append(f"份量·{q.size}")
    if _has_set(c):
        score += 0.8                       # 搭配完整，同分时优先
    if c.is_pop:
        score += 0.6
    if c.is_main and "甜一点" not in q.feel:
        score += 1.2                       # 一顿饭要有主食；除非明确只想吃甜的
    return score, matched


def pick_understand(pool: list[Candidate], q: Query) -> tuple[Candidate, list[str]]:
    weights = []
    for i, c in enumerate(pool):
        s, m = _score_understand(c, q)
        weights.append((s, i, c, m))
    weights.sort(key=lambda x: (-x[0], x[1]))
    best_score, _, best, matched = weights[0]
    # 什么都没选时，退化为"人气款"
    if best_score == 0 and not (q.state or q.feel or q.size):
        pops = [c for c in pool if c.is_pop] or pool
        return pops[0], []
    return best, matched


def pick_safe(pool: list[Candidate], q: Query, taken: set[str]) -> Candidate | None:
    cands = [c for c in pool if _mkey(c) not in taken]
    if not cands:
        return None
    med = _median(pool)
    # 先保留"搭配完整 + 非新品"的，避免推一个孤零零的单品或踩雷新品
    tier = [c for c in cands if _has_set(c) and not c.is_new and c.is_main]
    if not tier:
        tier = ([c for c in cands if _has_set(c) and c.is_main]
                or [c for c in cands if c.is_main and not c.is_new]
                or [c for c in cands if c.is_main] or cands)
    below = [c for c in tier if c.price_yuan <= med]
    base = below or tier
    base.sort(key=lambda c: (abs(c.price_yuan - med), -(_has_set(c)), c.price_yuan))
    return base[0]


def pick_surprise(pool: list[Candidate], q: Query, taken: set[str],
                  ref: Candidate | None) -> Candidate | None:
    cands = [c for c in pool if _mkey(c) not in taken]
    if not cands:
        return None
    med = _median(pool)
    ref_cat = ref.category if ref else None

    if "甜一点" not in q.feel:
        main_only = [c for c in cands if c.is_main]
        if main_only:
            cands = main_only

    def key(c: Candidate):
        diff_cat = 1 if (ref_cat and c.category != ref_cat) else 0
        tried = 0 if any(f in _text(c) for f in q.feel) else 1   # 用户没提过的更"惊喜"
        return (-diff_cat, -int(c.is_new), -tried, -int(c.price_yuan >= med), c.price_yuan)

    cands.sort(key=key)
    return cands[0]


# ---------------------------------------------------------------- 理由
def _reason_understand(p: Plan, q: Query) -> str:
    c = p.cand
    bits = []
    if q.state:
        note = STATE_RULES.get(q.state, {}).get("note", "")
        bits.append(f"你说「{q.state}」，挑了{note}这一挂")
    for f in q.feel[:2]:
        bits.append(f"命中「{f}」")
    if c.parts:
        bits.append(f"给你配齐了这顿：{' + '.join(n for n, _ in c.parts)}")
    elif _has_set(c):
        bits.append("搭配是完整的，不用再想加什么")
    if q.budget_yuan is not None:
        gap = q.budget_yuan - c.price_yuan
        if gap >= 0:
            bits.append(f"{_yuan(c.price_yuan)}，比你的预算还低 ¥{gap:.2f}")
        else:
            bits.append(f"{_yuan(c.price_yuan)}")
    else:
        bits.append(_yuan(c.price_yuan))
    return "；".join(bits) + "。"


def _reason_safe(p: Plan, q: Query, med: float) -> str:
    c = p.cand
    bits = ["主食和小食都配好了，选它不用再挑" if c.parts else "搭配是现成的，选它不用再挑"]
    if c.price_yuan <= med:
        bits.append(f"{_yuan(c.price_yuan)}，在这次候选里属于中位以下")
    else:
        bits.append(f"{_yuan(c.price_yuan)}")
    if not c.is_new:
        bits.append("不是这波新品，口味比较稳")
    return "；".join(bits) + "。"


def _reason_surprise(p: Plan, q: Query, ref: Candidate | None) -> str:
    c = p.cand
    bits = []
    if c.is_new:
        bits.append("这是这波上新/限定的")
    if ref and c.category != ref.category:
        bits.append(f"跟你前面那款不是一个品类（{c.category}）")
    if q.feel and not any(f in _text(c) for f in q.feel):
        bits.append("你这次没提这类，正好换个口味")
    if not bits:
        bits.append("换个你没点过的")
    bits.append(_yuan(c.price_yuan))
    return "；".join(bits) + "。"


# ---------------------------------------------------------------- 主流程
def open_box(pool: list[Candidate], q: Query, rng: random.Random | None = None) -> Box:
    """输入候选池与 Query，输出三个方案（可能少于三个，会说明原因）。"""
    seed = q.seed if q.seed is not None else random.SystemRandom().randrange(10 ** 12)
    rng = rng or random.Random(seed)

    filtered, notes = hard_filter(pool, q)
    meals = build_meals(filtered, q)      # 把单品凑成"一顿饭"
    med = _median(meals) if meals else 0.0

    if not meals:
        return Box(plans=[], pool_size=0, seed=seed,
                   notes=notes + ["这个条件下没有可选餐品"], stats={"median": med})

    plans: list[Plan] = []

    if q.entry == "random":
        # 真随机：在"一顿饭"的候选里均匀抽样，不排序、不用任何偏好。
        seen: set[str] = set()
        picks: list[Candidate] = []
        for c in rng.sample(meals, k=len(meals)):
            k = _mkey(c)
            if k in seen:
                continue
            seen.add(k)
            picks.append(c)
            if len(picks) >= 3:
                break
        for c in picks:
            plans.append(Plan("random", f"随机 {len(plans) + 1}", c,
                              f"在你的限制里随手抽到的：{_yuan(c.price_yuan)}。"))
    else:
        # 懂你
        c1, matched = pick_understand(meals, q)
        p1 = Plan("understand", ROLE_LABEL["understand"], c1, "", matched)
        p1.reason = _reason_understand(p1, q)
        plans.append(p1)

        # 稳妥
        c2 = pick_safe(meals, q, {_mkey(c1)})
        if c2:
            p2 = Plan("safe", ROLE_LABEL["safe"], c2, "")
            p2.reason = _reason_safe(p2, q, med)
            plans.append(p2)

        # 惊喜
        c3 = pick_surprise(meals, q, {_mkey(p.cand) for p in plans}, c1)
        if c3:
            p3 = Plan("surprise", ROLE_LABEL["surprise"], c3, "")
            p3.reason = _reason_surprise(p3, q, c1)
            plans.append(p3)

    # 差异化提示
    if len(plans) >= 2:
        cats = {p.cand.category for p in plans}
        if len(cats) == 1:
            for p in plans:
                p.warnings.append("三者同类，因可选范围有限")
    if len(plans) < 3:
        notes.append(f"只凑到 {len(plans)} 个符合条件的方案，没有硬凑第三个")

    return Box(plans=plans, pool_size=len(meals), seed=seed, notes=notes,
               stats={"median": round(med, 2), "priced": len(meals)})
