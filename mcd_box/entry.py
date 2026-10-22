# -*- coding: utf-8 -*-
"""三种入口 → 统一 Query。

入口 A 直觉输入：由命令行/对话直接给出结构化字段。
入口 B 自由表达：L0 规则解析（词典 + 正则），抽 5 类槽位：预算 / 忌口 / 感觉 / 状态 / 份量。
                 解析完**必须回显**给用户确认；抽不到就说抽不到，不猜。
入口 C 随机：不读任何偏好，只带门店与可选的预算/忌口。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .candidates import Candidate
from .recommend import FEEL_RULES, STATE_RULES, Query

# 忌口词：只做名称/分类的子串匹配，不是成分级判断
EXCLUDE_DICT = {
    "牛肉": ("牛肉", "牛堡", "安格斯", "巨无霸", "双层牛", "不素之霸"),
    "辣": ("辣", "龙焰", "韩式"),
    "冰": ("冰", "雪冰"),
    "咖啡": ("咖啡", "拿铁", "美式", "玛奇朵", "卡布"),
    "猪肉": ("猪柳", "火腿", "培根", "猪"),
    "鱼": ("鱼", "鳕"),
}

_FEEL_SYNONYMS = {
    "满足": ("满足", "饱", "扎实", "顶饱", "解馋"),
    "热乎": ("热乎", "热的", "暖", "暖和", "汤"),
    "清爽": ("清爽", "清淡", "不油", "轻一点"),
    "甜一点": ("甜", "甜的", "来点甜"),
    "想尝鲜": ("尝鲜", "新的", "试试新", "没吃过"),
}

_STATE_SYNONYMS = {
    "累了": ("累", "疲", "加班", "困", "没力气"),
    "心情不错": ("心情不错", "开心", "高兴", "心情好"),
    "有点低落": ("低落", "心情不好", "郁闷", "烦", "搞砸", "难受"),
    "想奖励自己": ("奖励", "犒劳", "奢侈", "放大招"),
    "就想简单解决": ("随便", "简单", "省事", "随便吃", "不挑了"),
}

_SIZE_SYNONYMS = {
    "垫一下": ("垫一下", "不饿", "少吃", "小份", "轻一点"),
    "很饿": ("很饿", "饿死", "特别饿", "超饿", "大份"),
    "正常": ("正常", "一般", "普通"),
}

_BUDGET_PATTERNS = (
    r"(\d+(?:\.\d+)?)\s*(?:元|块|rmb|RMB)?\s*(?:以内|以下|之内)",
    r"(?:不超过|别超过|不要超过|最多|顶多|预算)\s*(\d+(?:\.\d+)?)",
    r"(\d+(?:\.\d+)?)\s*(?:元|块)",
)

_ECHO_EMPTY = "—"


@dataclass
class Parsed:
    query: Query
    echo: list[tuple[str, str]] = field(default_factory=list)  # (槽位, 值)
    unresolved: list[str] = field(default_factory=list)        # 没读懂的片段提示

    @property
    def hit_count(self) -> int:
        return sum(1 for _, v in self.echo if v != _ECHO_EMPTY)

    def echo_text(self) -> str:
        rows = [f"  {k:<4}{v}" for k, v in self.echo]
        return "我理解成这样，对吗？\n" + "\n".join(rows)


def _find_first(text: str, table: dict[str, tuple[str, ...]]) -> str | None:
    for key, words in table.items():
        if any(w in text for w in words):
            return key
    return None


def _find_all(text: str, table: dict[str, tuple[str, ...]], limit: int = 2) -> list[str]:
    hits = [k for k, words in table.items() if any(w in text for w in words)]
    return hits[:limit]


def parse_budget(text: str) -> float | None:
    for pat in _BUDGET_PATTERNS:
        m = re.search(pat, text)
        if m:
            try:
                v = float(m.group(1))
            except (TypeError, ValueError):
                continue
            if 3 <= v <= 300:          # 明显不合理的数字（如"今天35度"）直接放弃
                return round(v, 2)
    return None


def parse_exclude(text: str) -> list[str]:
    out = []
    for key, words in EXCLUDE_DICT.items():
        if any(w in text for w in words):
            out.append(key)
    return out


def parse_text(text: str, store: str = "") -> Parsed:
    """L0 规则解析：能抽就抽，抽不到就留空并在回显里标出来。"""
    raw = (text or "").strip()
    budget = parse_budget(raw)
    exclude = parse_exclude(raw)
    feels = _find_all(raw, _FEEL_SYNONYMS)
    state = _find_first(raw, _STATE_SYNONYMS)
    size = _find_first(raw, _SIZE_SYNONYMS)

    q = Query(store=store, entry="text", budget_yuan=budget, exclude=exclude,
              state=state, feel=feels, size=size, raw_text=raw)

    echo = [
        ("预算", f"≤ ¥{budget:.0f}" if budget is not None else _ECHO_EMPTY),
        ("不要", "、".join(exclude) if exclude else _ECHO_EMPTY),
        ("想要", "、".join(feels) if feels else _ECHO_EMPTY),
        ("状态", state or _ECHO_EMPTY),
        ("份量", size or _ECHO_EMPTY),
    ]
    p = Parsed(query=q, echo=echo)
    if p.hit_count == 0:
        p.unresolved.append("这句我没读出具体限制")
    return p


def random_query(store: str = "", budget: float | None = None,
                 exclude: list[str] | None = None) -> Query:
    """入口 C：不读偏好，只带硬约束。"""
    return Query(store=store, entry="random", budget_yuan=budget, exclude=exclude or [])


def intuition_query(store: str = "", budget: float | None = None,
                    exclude: list[str] | None = None, state: str | None = None,
                    feel: list[str] | None = None, size: str | None = None) -> Query:
    return Query(store=store, entry="intuition", budget_yuan=budget,
                 exclude=exclude or [], state=state, feel=feel or [], size=size)


# ---------------------------------------------------------------- 校验
def validate(q: Query) -> list[str]:
    """把不合法的输入挡在推荐之前，返回提示（空 = 没问题）。"""
    problems = []
    if q.state and q.state not in STATE_RULES:
        problems.append(f"未知状态「{q.state}」，可选：{'、'.join(STATE_RULES)}")
    bad_feel = [f for f in q.feel if f not in FEEL_RULES]
    if bad_feel:
        problems.append(f"未知感觉「{'、'.join(bad_feel)}」，可选：{'、'.join(FEEL_RULES)}")
    if q.size and q.size not in ("垫一下", "正常", "很饿"):
        problems.append(f"未知份量「{q.size}」，可选：垫一下 / 正常 / 很饿")
    if q.budget_yuan is not None and q.budget_yuan <= 0:
        problems.append("预算要大于 0")
    return problems


def describe_inputs(q: Query) -> str:
    parts = []
    if q.state:
        parts.append(q.state)
    if q.feel:
        parts.append("想吃" + "、".join(q.feel))
    if q.size:
        parts.append(q.size)
    if q.budget_yuan is not None:
        parts.append(f"预算 ¥{q.budget_yuan:.0f}")
    if q.exclude:
        parts.append("不吃" + "、".join(q.exclude))
    return " · ".join(parts) if parts else "什么都没说"
