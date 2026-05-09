"""中文术语映射

把英文 / 代码内部 key 映射为中文，用于 demo 输出、报告生成等。
所有展示给用户的文本都从这里取，方便统一替换。
"""

#: SG 四大类别的中文名
SG_CATEGORY_CN: dict[str, str] = {
    "off_tee": "开球",
    "approach": "进攻杆",
    "around_green": "果岭周围",
    "putting": "推杆",
    "total": "总计",
}

#: 落点类型中文
LIE_CN: dict[str, str] = {
    "tee": "发球台",
    "fairway": "球道",
    "rough": "长草",
    "sand": "沙坑",
    "recovery": "树林/障碍",
    "green": "果岭",
    "holed": "进洞",
}

#: 球杆中文（按你的偏好：用挖起杆，不是楔形杆）
CLUB_CN: dict[str, str] = {
    "driver": "1 号木",
    "3w": "3 号木",
    "5w": "5 号木",
    "3h": "3 号小鸡腿",
    "4h": "4 号小鸡腿",
    "3i": "3 号铁",
    "4i": "4 号铁",
    "5i": "5 号铁",
    "6i": "6 号铁",
    "7i": "7 号铁",
    "8i": "8 号铁",
    "9i": "9 号铁",
    "pw": "PW（48° 挖起杆）",
    "gw": "GW（52° 挖起杆）",
    "sw": "SW（56° 挖起杆）",
    "lw": "LW（60° 挖起杆）",
    "putter": "推杆",
}

#: 差点档位中文标签
BASELINE_CN: dict[str, str] = {
    "pga_tour": "PGA Tour 平均",
    "amateur_scratch": "业余 0 差点",
    "amateur_5": "业余 5 差点",
    "amateur_10": "业余 10 差点",
    "amateur_15": "业余 15 差点",
    "amateur_20": "业余 20 差点",
    "amateur_25": "业余 25 差点",
}


def sg_label(category: str) -> str:
    """SG 类别 → 中文标签。"""
    return SG_CATEGORY_CN.get(category, category)


def lie_label(lie: str) -> str:
    """落点 → 中文标签。"""
    return LIE_CN.get(lie, lie)


def club_label(club: str | None) -> str:
    """球杆 → 中文标签。"""
    if club is None:
        return "（未记录）"
    return CLUB_CN.get(club.lower(), club)


def baseline_label(label: str) -> str:
    """基线代号 → 中文标签。"""
    return BASELINE_CN.get(label, label)
