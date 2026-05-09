"""
基线生成器：从 PGA Tour 基线 + 差点缩放系数，生成其它差点档位的 JSON 基线。

使用方法（在仓库根目录）：
    python core/baselines/_generate.py

生成后会覆盖 amateur_scratch / amateur_5 / amateur_10 / amateur_20 / amateur_25 五个 JSON
（amateur_15 是手工拟合的，不会被覆盖）
"""

import json
from pathlib import Path

BASELINES_DIR = Path(__file__).parent
PGA_FILE = BASELINES_DIR / "pga_tour.json"
PROTECTED = {"pga_tour"}  # 只保护 PGA Tour，业余 6 档全部由生成器统一管理


# 各差点相对 PGA Tour 的"每位置加杆数"系数
# 来源：Broadie + Lou Stagner 业余统计的近似拟合
# 关键约束：曲线必须单调（差点越高，期望杆数越高）
# 结构：(short_offset, mid_offset, long_offset)
# - short = 0-80 码
# - mid = 80-180 码
# - long = 180+ 码
SCALING = {
    "amateur_scratch": {  # 0 差点
        "tee": 0.03,
        "fairway": (0.05, 0.10, 0.15),
        "rough": (0.08, 0.15, 0.20),
        "sand": 0.18,
        "recovery": 0.25,
        "green_base": 0.05,
        "green_per_yd": 0.005,
        "round_total_vs_tour": -3,
    },
    "amateur_5": {
        "tee": 0.07,
        "fairway": (0.10, 0.18, 0.25),
        "rough": (0.15, 0.22, 0.32),
        "sand": 0.28,
        "recovery": 0.40,
        "green_base": 0.10,
        "green_per_yd": 0.010,
        "round_total_vs_tour": -7,
    },
    "amateur_10": {
        "tee": 0.12,
        "fairway": (0.15, 0.25, 0.35),
        "rough": (0.22, 0.32, 0.45),
        "sand": 0.38,
        "recovery": 0.55,
        "green_base": 0.15,
        "green_per_yd": 0.013,
        "round_total_vs_tour": -11,
    },
    "amateur_15": {  # ⭐ 用户当前差点档位
        "tee": 0.18,
        "fairway": (0.20, 0.32, 0.45),
        "rough": (0.30, 0.42, 0.55),
        "sand": 0.48,
        "recovery": 0.70,
        "green_base": 0.18,
        "green_per_yd": 0.016,
        "round_total_vs_tour": -14,
    },
    "amateur_20": {
        "tee": 0.25,
        "fairway": (0.28, 0.42, 0.58),
        "rough": (0.40, 0.55, 0.72),
        "sand": 0.62,
        "recovery": 0.88,
        "green_base": 0.24,
        "green_per_yd": 0.020,
        "round_total_vs_tour": -18,
    },
    "amateur_25": {
        "tee": 0.32,
        "fairway": (0.36, 0.54, 0.72),
        "rough": (0.52, 0.70, 0.90),
        "sand": 0.78,
        "recovery": 1.05,
        "green_base": 0.30,
        "green_per_yd": 0.026,
        "round_total_vs_tour": -23,
    },
}

NAMES = {
    "amateur_scratch": "业余 0 差点",
    "amateur_5": "业余 5 差点",
    "amateur_10": "业余 10 差点",
    "amateur_15": "业余 15 差点",
    "amateur_20": "业余 20 差点",
    "amateur_25": "业余 25 差点",
}


def distance_band(yds: int) -> int:
    """返回距离段索引：0=short, 1=mid, 2=long"""
    if yds <= 80:
        return 0
    if yds <= 180:
        return 1
    return 2


def scale_baseline(pga: dict, level: str) -> dict:
    s = SCALING[level]
    out = {
        "name": NAMES[level],
        "label": level,
        "source": "PGA Tour 基线 + 业余差点缩放系数（见 _generate.py 注释）",
        "version": pga["version"],
        "distance_unit": "yards",
        "notes": f"差点 {level.replace('amateur_', '')} 业余球手平均水平。"
                 f"比 PGA Tour 总 SG 约 {s['round_total_vs_tour']} 杆/轮。",
    }

    # tee
    out["tee"] = {}
    for par_type, distances in pga["tee"].items():
        out["tee"][par_type] = {
            d: round(v + s["tee"], 3) for d, v in distances.items()
        }

    # fairway / rough（按距离段缩放）
    for lie in ("fairway", "rough"):
        out[lie] = {}
        offsets = s[lie]
        for d_str, v in pga[lie].items():
            band = distance_band(int(d_str))
            out[lie][d_str] = round(v + offsets[band], 3)

    # sand / recovery（按距离段缩放，但用单一 offset 简化）
    for lie in ("sand", "recovery"):
        out[lie] = {}
        offset = s[lie]
        for d_str, v in pga[lie].items():
            d = int(d_str)
            # 短距离 sand/recovery offset 减半（短挖起杆相对简单）
            adj = offset * 0.7 if d <= 60 else offset
            out[lie][d_str] = round(v + adj, 3)

    # green（推杆基线，按推杆距离码数线性增加）
    out["green"] = {}
    for d_str, v in pga["green"].items():
        d_yd = int(d_str)
        offset = s["green_base"] + s["green_per_yd"] * d_yd
        out["green"][d_str] = round(v + offset, 3)

    return out


def main() -> None:
    with PGA_FILE.open("r", encoding="utf-8") as f:
        pga = json.load(f)

    for level in SCALING:
        out_path = BASELINES_DIR / f"{level}.json"
        if out_path.stem in PROTECTED:
            print(f"⏭  跳过受保护基线：{out_path.name}")
            continue
        baseline = scale_baseline(pga, level)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(baseline, f, ensure_ascii=False, indent=2)
        print(f"✅ 生成：{out_path.name}")


if __name__ == "__main__":
    main()
