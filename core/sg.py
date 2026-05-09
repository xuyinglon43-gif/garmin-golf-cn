"""
Strokes Gained 计算引擎

核心公式（Mark Broadie）：
    每杆 SG = 起点期望杆数 − 终点期望杆数 − 1

    若该杆进洞，终点期望杆数 = 0
    将 18 洞所有击球的 SG 按类别累加，得到一轮的 SG 拆解：
      - SG_off_tee   (开球，par 4/5 开球)
      - SG_approach  (进攻杆，距洞 ≥ 30 码的非开球非推杆)
      - SG_around_green (果岭周围，距洞 < 30 码的非推杆)
      - SG_putting   (推杆)
    SG_total = 各项之和 = 你比基线少打了多少杆
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# ----------------------------------------------------------------------------
# 常量
# ----------------------------------------------------------------------------

LieType = Literal["tee", "fairway", "rough", "sand", "recovery", "green", "holed"]

#: 距洞 30 码以内的非推杆 → 算"果岭周围"，否则算"进攻杆"
APPROACH_AROUND_GREEN_THRESHOLD_YD = 30.0

BASELINES_DIR = Path(__file__).parent / "baselines"


# ----------------------------------------------------------------------------
# 数据类
# ----------------------------------------------------------------------------


@dataclass
class Shot:
    """单一击球。"""

    hole_number: int  # 1-18
    shot_number: int  # 该洞的第几杆，从 1 开始
    start_lie: LieType  # 起点落点类型
    start_distance_yards: float  # 起点到洞的距离（码）
    end_lie: LieType  # 终点落点类型，进洞为 "holed"
    end_distance_yards: float  # 终点到洞的距离（码），进洞为 0
    par: int = 4  # 该洞 par，用于开球分类
    club: str | None = None  # 用了什么杆，可选


@dataclass
class Round:
    """一整轮 18 洞数据。"""

    course_name: str
    date: str  # ISO 格式 yyyy-mm-dd
    shots: list[Shot] = field(default_factory=list)

    @property
    def total_strokes(self) -> int:
        """总杆数 = 击球总数。"""
        return len(self.shots)


@dataclass
class ShotSG:
    """单一击球的 SG 明细。"""

    shot: Shot
    start_expected: float
    end_expected: float
    sg: float
    category: Literal["off_tee", "approach", "around_green", "putting"]


@dataclass
class StrokesGainedResult:
    """一轮 SG 计算结果。"""

    round_data: Round
    baseline_label: str
    sg_off_tee: float = 0.0
    sg_approach: float = 0.0
    sg_around_green: float = 0.0
    sg_putting: float = 0.0
    shots_breakdown: list[ShotSG] = field(default_factory=list)

    @property
    def sg_total(self) -> float:
        return (
            self.sg_off_tee
            + self.sg_approach
            + self.sg_around_green
            + self.sg_putting
        )

    def summary(self) -> dict:
        return {
            "course": self.round_data.course_name,
            "date": self.round_data.date,
            "total_strokes": self.round_data.total_strokes,
            "baseline": self.baseline_label,
            "sg_off_tee": round(self.sg_off_tee, 2),
            "sg_approach": round(self.sg_approach, 2),
            "sg_around_green": round(self.sg_around_green, 2),
            "sg_putting": round(self.sg_putting, 2),
            "sg_total": round(self.sg_total, 2),
        }


# ----------------------------------------------------------------------------
# 基线加载与查询
# ----------------------------------------------------------------------------


def load_baseline(label: str) -> dict:
    """加载一个基线 JSON。label 例如 'pga_tour' / 'amateur_15'。"""
    path = BASELINES_DIR / f"{label}.json"
    if not path.exists():
        available = sorted(p.stem for p in BASELINES_DIR.glob("*.json"))
        raise FileNotFoundError(
            f"找不到基线 '{label}'。可用基线：{available}"
        )
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _interpolate(table: dict[str, float], distance: float) -> float:
    """在距离表上线性插值。table 的 key 是字符串距离。"""
    distances = sorted(int(k) for k in table.keys())
    if distance <= distances[0]:
        return table[str(distances[0])]
    if distance >= distances[-1]:
        return table[str(distances[-1])]
    # 找两侧的相邻点
    for i in range(len(distances) - 1):
        d_lo, d_hi = distances[i], distances[i + 1]
        if d_lo <= distance <= d_hi:
            v_lo = table[str(d_lo)]
            v_hi = table[str(d_hi)]
            t = (distance - d_lo) / (d_hi - d_lo)
            return v_lo + t * (v_hi - v_lo)
    # 不应到达
    return table[str(distances[-1])]


def expected_strokes(
    baseline: dict,
    lie: LieType,
    distance_yards: float,
    par: int = 4,
) -> float:
    """查询给定 (lie, 距离, par) 的基线期望杆数。

    holed → 0
    tee → 按 par 类型查表
    其它（fairway/rough/sand/recovery/green）→ 按距离查表 + 插值
    """
    if lie == "holed":
        return 0.0

    if lie == "tee":
        par_key = f"par{par}"
        table = baseline["tee"].get(par_key)
        if table is None:
            # par 3 没有对应的就 fallback 到 fairway 表
            return _interpolate(baseline["fairway"], distance_yards)
        return _interpolate(table, distance_yards)

    if lie not in baseline:
        raise ValueError(f"未知的落点类型 '{lie}'，基线中无此项")

    return _interpolate(baseline[lie], distance_yards)


# ----------------------------------------------------------------------------
# SG 分类与计算
# ----------------------------------------------------------------------------


def categorize_shot(shot: Shot) -> Literal[
    "off_tee", "approach", "around_green", "putting"
]:
    """把一杆归到四个 SG 类别之一。

    分类规则（Broadie 标准）：
    - 推杆（起点在果岭）→ putting
    - par 4/5 开球（起点在 tee box）→ off_tee
    - par 3 开球 / fairway-rough-sand 远距离击球（≥ 30 码）→ approach
    - 30 码以内的非推杆击球 → around_green
    """
    if shot.start_lie == "green":
        return "putting"

    if shot.start_lie == "tee" and shot.par >= 4:
        return "off_tee"

    if shot.start_distance_yards >= APPROACH_AROUND_GREEN_THRESHOLD_YD:
        return "approach"

    return "around_green"


def calculate_shot_sg(shot: Shot, baseline: dict) -> ShotSG:
    """计算单一击球的 SG。"""
    start_expected = expected_strokes(
        baseline, shot.start_lie, shot.start_distance_yards, par=shot.par
    )
    end_expected = expected_strokes(
        baseline, shot.end_lie, shot.end_distance_yards, par=shot.par
    )
    sg = start_expected - end_expected - 1.0
    category = categorize_shot(shot)
    return ShotSG(
        shot=shot,
        start_expected=start_expected,
        end_expected=end_expected,
        sg=sg,
        category=category,
    )


def calculate_round_sg(
    round_data: Round,
    baseline_label: str = "amateur_15",
) -> StrokesGainedResult:
    """计算一轮的完整 SG 结果。"""
    baseline = load_baseline(baseline_label)
    result = StrokesGainedResult(
        round_data=round_data, baseline_label=baseline_label
    )

    for shot in round_data.shots:
        shot_sg = calculate_shot_sg(shot, baseline)
        result.shots_breakdown.append(shot_sg)
        if shot_sg.category == "off_tee":
            result.sg_off_tee += shot_sg.sg
        elif shot_sg.category == "approach":
            result.sg_approach += shot_sg.sg
        elif shot_sg.category == "around_green":
            result.sg_around_green += shot_sg.sg
        else:  # putting
            result.sg_putting += shot_sg.sg

    return result
