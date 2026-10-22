# -*- coding: utf-8 -*-
"""候选构建：Catalog → Candidate 列表，并做三条基础标注。

只做"打标签"和"粗筛"，不做推荐排序——排序是 recommend.py 的事。
标注依据全部来自接口字段（名称 / 分类 / tags / 价格），不做任何猜测式推断。

份量带阈值来自实测分布（门店 3350112，n=102）：
    ¥3.90 起，25% ¥14.50，中位数 ¥24.00，75% ¥33.50，最高 ¥73.00
    → light < 18 ≤ normal ≤ 35 < big
"""
from __future__ import annotations

from dataclasses import dataclass

from .adapter import Catalog, Item

# 「一个人吃」大概率不适合的词：出现在名称里就标为多人餐
MULTI_WORDS = ("双人", "三人", "四人", "分享", "拼盘", "全家", "家庭", "聚会", "多人", "组合装")
# 「新/限定」：惊喜款要靠这些词跳出来（实测 tags 里确实存在，见 CHAIN_REPORT）
NEW_WORDS = ("上新", "限定", "联名", "限量", "新升级")
# 「热度」：懂你款在用户什么都没选时的兜底
POP_WORDS = ("人气", "热卖", "爆款", "经典", "粉丝之选")
# 联名周边 / 非食品：会出现在"人气热卖"货架里且带"上新/限定"标记，必须挡在推荐之外
NON_FOOD_WORDS = ("帽", "丝巾", "徽章", "玩具", "公仔", "周边", "盲盒", "摆件", "抱枕",
                  "钥匙扣", "帆布袋", "手提袋", "立牌", "贴纸", "星愿贴", "水手帽",
                  "按摩", "捶", "痒痒挠", "水壶", "雨伞", "T恤", "玩偶", "手办", "挂件", "收纳")

# 「能当一顿饭」的判定：只看分类与名称，不猜份量。甜品/饮品/小食不算主食。
MAIN_CATEGORY_WORDS = ("堡", "套餐", "卷", "炸鸡", "单人餐", "随心配", "大堡口福", "牛鱼肉堡", "安格斯")
MAIN_NAME_WORDS = ("堡", "卷", "饭", "鸡腿", "鸡排")

SIZE_LIGHT_MAX = 18.0
SIZE_BIG_MIN = 35.0


@dataclass(frozen=True)
class Candidate:
    code: str
    name: str
    category: str
    tags: tuple[str, ...]
    price_yuan: float | None
    original_yuan: float | None
    discount_type: str | None
    image: str | None
    size_band: str          # light | normal | big | unknown
    is_new: bool            # 带 上新/限定/联名/限量/新升级
    is_pop: bool            # 带 人气/热卖/爆款/经典
    is_multi: bool          # 名称看着像多人餐
    is_nonfood: bool        # 周边/玩具/徽章，不是餐品
    is_main: bool           # 能当一顿饭（汉堡/套餐/卷/炸鸡），甜品饮品为 False

    @property
    def has_price(self) -> bool:
        return self.price_yuan is not None

    def __str__(self) -> str:
        p = f"¥{self.price_yuan:.2f}" if self.price_yuan is not None else "价格待确认"
        flags = "".join([
            "新" if self.is_new else "",
            "热" if self.is_pop else "",
            "多" if self.is_multi else "",
            "物" if self.is_nonfood else "",
            "" if self.is_main else "·非主食",
        ])
        return f"{self.name}（{p}·{self.size_band}{'·' + flags if flags else ''}）"


def _band(price: float | None) -> str:
    if price is None:
        return "unknown"
    if price < SIZE_LIGHT_MAX:
        return "light"
    if price > SIZE_BIG_MIN:
        return "big"
    return "normal"


def _hit(words: tuple[str, ...], *sources: str) -> bool:
    text = " ".join(s for s in sources if s)
    return any(w in text for w in words)


def to_candidate(item: Item) -> Candidate:
    return Candidate(
        code=item.code,
        name=item.name,
        category=item.category,
        tags=tuple(item.tags),
        price_yuan=item.price_yuan,
        original_yuan=item.original_yuan,
        discount_type=item.discount_type,
        image=item.image,
        size_band=_band(item.price_yuan),
        is_new=_hit(NEW_WORDS, item.name, *item.tags),
        is_pop=_hit(POP_WORDS, item.name, *item.tags),
        is_multi=_hit(MULTI_WORDS, item.name, item.category),
        is_nonfood=_hit(NON_FOOD_WORDS, item.name),
        is_main=(_hit(MAIN_CATEGORY_WORDS, item.category) or _hit(MAIN_NAME_WORDS, item.name))
                and not _hit(NON_FOOD_WORDS, item.name),
    )


def build(catalog: Catalog, drop_multi: bool = True,
          drop_nonfood: bool = True) -> tuple[list[Candidate], dict]:
    """返回 (候选列表, 统计)。

    默认剔除两类明显不该推荐的：
      - 多人餐（双人/分享/拼盘）：单人场景推双人套餐是错误
      - 非食品（帽子/丝巾/徽章/贴纸）：实测确实混在"人气热卖"里
    """
    all_c = [to_candidate(i) for i in catalog.items]
    multi = [c for c in all_c if c.is_multi]
    nonfood = [c for c in all_c if c.is_nonfood]
    pool = [c for c in all_c
            if not (drop_multi and c.is_multi) and not (drop_nonfood and c.is_nonfood)]

    stats = {
        "total": len(all_c),
        "pool": len(pool),
        "dropped_multi": len(multi),
        "dropped_nonfood": len(nonfood),
        "no_price": sum(1 for c in all_c if not c.has_price),
        "new": sum(1 for c in pool if c.is_new),
        "pop": sum(1 for c in pool if c.is_pop),
        "light": sum(1 for c in pool if c.size_band == "light"),
        "normal": sum(1 for c in pool if c.size_band == "normal"),
        "big": sum(1 for c in pool if c.size_band == "big"),
        "main": sum(1 for c in pool if c.is_main),
        "categories": len({c.category for c in pool}),
    }
    return pool, stats
