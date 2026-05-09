"""
模拟数据 demo —— 不需要 Garmin 设备即可跑通核心 SG 计算

跑法（仓库根目录下）：
    python examples/demo_simulated.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 让脚本无需安装包就能直接 python examples/demo_simulated.py
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.sg import Round, Shot, calculate_round_sg  # noqa: E402
from core.terms import baseline_label, sg_label  # noqa: E402


SAMPLE = ROOT / "examples" / "sample_round.json"


def load_sample_round() -> Round:
    with SAMPLE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    shots = [Shot(**s) for s in data["shots"]]
    return Round(course_name=data["course_name"], date=data["date"], shots=shots)


def print_header(text: str) -> None:
    print("═" * 50)
    print(f"  {text}")
    print("═" * 50)


def print_row(label: str, value: float, hint: str = "") -> None:
    color_hint = ""
    if value <= -1.0:
        color_hint = "   ⚠️  弱项"
    elif value >= 1.0:
        color_hint = "   ⭐ 强项"
    # 中文标签两字符宽度对齐
    pad = 4 - len(label)
    print(f"  ▸ {label}{'　' * pad}: {value:+6.2f} 杆/轮{color_hint}{hint}")


def insight(result) -> str:
    """生成一句话洞察（找最弱项）。"""
    parts = {
        "off_tee": result.sg_off_tee,
        "approach": result.sg_approach,
        "around_green": result.sg_around_green,
        "putting": result.sg_putting,
    }
    weakest_key = min(parts, key=parts.get)
    weakest_value = parts[weakest_key]
    if weakest_value > -0.3:
        return "整体表现均衡，没有明显短板。继续保持。"
    return (
        f"你的【{sg_label(weakest_key)}】比 {baseline_label(result.baseline_label)} "
        f"多丢 {abs(weakest_value):.1f} 杆/轮，是当前最大的杆数漏洞。"
    )


def main() -> None:
    rd = load_sample_round()
    result = calculate_round_sg(rd, baseline_label="amateur_15")

    print()
    print_header("garmin-golf-cn · Strokes Gained Demo")
    print(f"  轮次：{rd.course_name} · {rd.date} · 总杆 {rd.total_strokes}")
    print(f"  对比基线：{baseline_label(result.baseline_label)}")
    print()

    print_row(sg_label("off_tee"), result.sg_off_tee)
    print_row(sg_label("approach"), result.sg_approach)
    print_row(sg_label("around_green"), result.sg_around_green)
    print_row(sg_label("putting"), result.sg_putting)
    print()
    print(f"  总 SG：{result.sg_total:+.2f} 杆/轮  "
          f"（vs {baseline_label(result.baseline_label)}）")
    print()
    print("  💡 洞察：" + insight(result))
    print()

    # 详细拆解（每杆）
    print_header("逐杆明细（前 10 杆）")
    print(f"  {'洞':<4}{'杆':<4}{'起点':<14}{'终点':<14}"
          f"{'类别':<10}{'SG':>7}")
    print("  " + "─" * 56)
    for sg in result.shots_breakdown[:10]:
        s = sg.shot
        start = f"{s.start_lie}@{s.start_distance_yards:.0f}"
        end = (
            "进洞" if s.end_lie == "holed"
            else f"{s.end_lie}@{s.end_distance_yards:.0f}"
        )
        cat = sg_label(sg.category)
        cat_pad = 5 - len(cat)
        print(f"  {s.hole_number:<4}{s.shot_number:<4}{start:<14}{end:<14}"
              f"{cat}{'　' * cat_pad}{sg.sg:+7.2f}")
    if len(result.shots_breakdown) > 10:
        print(f"  ... 还有 {len(result.shots_breakdown) - 10} 杆")
    print()

    # 跨基线对比
    print_header("跨基线对比（同一轮，不同对照组）")
    for label in ("pga_tour", "amateur_10", "amateur_15", "amateur_20"):
        r = calculate_round_sg(rd, baseline_label=label)
        print(f"  vs {baseline_label(label):<16} → 总 SG {r.sg_total:+6.2f} 杆/轮")
    print()


if __name__ == "__main__":
    main()
