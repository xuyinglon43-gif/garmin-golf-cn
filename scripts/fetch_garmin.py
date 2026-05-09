"""
garmin-golf-cn · Python 端拉取器（绕开浏览器，全自动）

用法：
    python3.11 scripts/fetch_garmin.py                      # 中国版（默认）
    python3.11 scripts/fetch_garmin.py --domain garmin.com  # 全球版

凭证处理：
    - 首次运行：交互式输入邮箱 + 密码（getpass 隐式输入，终端不回显）
    - 登录后 OAuth token 缓存到 ~/.garmincache/，下次免输密码
    - 密码本身从不存盘、从不出现在日志
    - 如果开了 2FA，会提示输入验证码

输出：
    data/garmin-export-{yyyy-mm-dd}.json
    （data/ 在 .gitignore，绝不进仓库）

依赖：
    python3.11 -m pip install --user garth
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from getpass import getpass
from pathlib import Path

try:
    import garth
except ImportError:
    print("❌ 缺依赖：garth")
    print("   请先安装：python3.11 -m pip install --user garth")
    sys.exit(1)


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
TOKEN_CACHE = Path.home() / ".garmincache"


# ----------------------------------------------------------------------------
# Garmin Connect API 端点（基于 2026-05 实测 connect.garmin.cn 的真实路径）
# ----------------------------------------------------------------------------

GOLF_API_BASE = "/golf-api/gcs-golfcommunity/api/v2"

ENDPOINTS = {
    "clubs": f"{GOLF_API_BASE}/club/player?per-page=1000&include-stats=true",
    "summary": f"{GOLF_API_BASE}/scorecard/summary?per-page=10000&user-locale={{locale}}",
    "detail": f"{GOLF_API_BASE}/scorecard/detail"
              "?scorecard-ids={card_id}&include-longest-shot-distance=true",
    "shots":  f"{GOLF_API_BASE}/shot/scorecard/{{card_id}}/hole?hole-numbers={{hole_n}}",
}

RATE_LIMIT_S = 0.12  # 与浏览器版一致


# ----------------------------------------------------------------------------
# 工具函数
# ----------------------------------------------------------------------------


def semicircles_to_decimal(semicircles: int | None) -> float | None:
    if semicircles is None:
        return None
    return semicircles * (180 / 2**31)


def convert_loc(loc: dict | None) -> dict | None:
    if not isinstance(loc, dict):
        return loc
    return {
        "lat": semicircles_to_decimal(loc.get("lat")),
        "lon": semicircles_to_decimal(loc.get("lon")),
        "_raw_semicircles": {"lat": loc.get("lat"), "lon": loc.get("lon")},
    }


def deep_convert_locs(obj):
    """递归遍历，把所有 startLoc/endLoc 字段从 semicircles 转 lat/lon。"""
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if k in ("startLoc", "endLoc") and isinstance(v, dict):
                obj[k] = convert_loc(v)
            else:
                deep_convert_locs(v)
    elif isinstance(obj, list):
        for x in obj:
            deep_convert_locs(x)


# ----------------------------------------------------------------------------
# 登录
# ----------------------------------------------------------------------------


def authenticate(domain: str) -> None:
    """配置 garth + 登录。优先用本地 token，失败时交互登录。"""
    garth.client.configure(domain=domain)

    # 尝试加载已缓存的 OAuth token
    if TOKEN_CACHE.exists() and any(TOKEN_CACHE.iterdir()):
        try:
            garth.client.load(str(TOKEN_CACHE))
            # 校验 token 仍有效
            garth.client.refresh_oauth2()
            print(f"✓ 已使用缓存的 OAuth token（{TOKEN_CACHE}）")
            return
        except Exception as e:
            print(f"⚠️  缓存 token 失效（{e}），需要重新登录")

    # 交互登录
    print()
    print("=" * 60)
    print("  Garmin Connect 登录")
    print("  （凭证仅用于本地 OAuth 流程，不会上传或保存到仓库）")
    print("=" * 60)
    email = input("  邮箱：").strip()
    password = getpass("  密码（输入时不回显）：")
    print()

    try:
        garth.login(email, password)
    except Exception as e:
        msg = str(e)
        if "MFA" in msg or "verification" in msg.lower():
            print("⚠️  此账号开了 2FA，需要验证码")
            print("    （garth 0.8.0 暂不支持交互式 MFA，请考虑临时关闭 2FA")
            print("     或导出后再开回去）")
        print(f"❌ 登录失败：{e}")
        sys.exit(1)

    # 保存 token 供下次免登录
    TOKEN_CACHE.mkdir(parents=True, exist_ok=True)
    garth.client.dump(str(TOKEN_CACHE))
    print(f"✓ 登录成功，token 已缓存至 {TOKEN_CACHE}")


# ----------------------------------------------------------------------------
# API 调用（带限流）
# ----------------------------------------------------------------------------


_last_call_at = 0.0


def call_api(path: str, *, retry: int = 3) -> dict | list:
    """走 garth.client.connectapi 调用 Garmin API，带限流和重试。"""
    global _last_call_at
    elapsed = time.time() - _last_call_at
    if elapsed < RATE_LIMIT_S:
        time.sleep(RATE_LIMIT_S - elapsed)
    _last_call_at = time.time()

    last_err: Exception | None = None
    for attempt in range(1, retry + 1):
        try:
            return garth.client.connectapi(path)
        except Exception as e:
            last_err = e
            if attempt < retry:
                time.sleep(1.0 * 2 ** (attempt - 1))  # 指数退避
    raise RuntimeError(f"调用 {path} 失败（重试 {retry} 次）：{last_err}")


# ----------------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------------


def fetch_all(locale: str, max_rounds: int | None = None) -> dict:
    print("\n[1/3] 拉取球杆库…")
    try:
        clubs = call_api(ENDPOINTS["clubs"]) or []
        print(f"  ✓ {len(clubs)} 支球杆")
    except Exception as e:
        print(f"  ⚠️ 球杆库拉取失败（{e}），继续")
        clubs = []

    print("\n[2/3] 拉取轮次列表…")
    summary = call_api(ENDPOINTS["summary"].format(locale=locale))
    cards = summary.get("scorecardSummaries", []) if isinstance(summary, dict) else []
    if max_rounds:
        cards = cards[:max_rounds]
    print(f"  ✓ 找到 {len(cards)} 轮"
          + (f"（已限制到前 {max_rounds} 轮）" if max_rounds else ""))

    if not cards:
        print("  账号下无任何高尔夫轮次，退出。")
        return {"clubs": clubs, "rounds": [], "summary": summary}

    print(f"\n[3/3] 拉取每轮明细 + 每洞逐杆…")
    rounds = []
    total_shots = 0
    total_holes = 0
    failures = 0

    for i, card in enumerate(cards, 1):
        card_id = card.get("id")
        course_name = card.get("courseName", "未知球场")
        print(f"  [{i:>3}/{len(cards)}] {course_name} (id={card_id})", flush=True)

        try:
            detail = call_api(ENDPOINTS["detail"].format(card_id=card_id))
        except Exception as e:
            print(f"          ✗ 明细失败：{e}")
            failures += 1
            continue

        # 取出洞列表
        holes = []
        try:
            sc_list = detail.get("scorecardDetails", []) if isinstance(detail, dict) else []
            sc = next((x for x in sc_list if x and "scorecard" in x), None)
            if sc:
                holes = sc.get("scorecard", {}).get("holes", []) or []
        except Exception:
            holes = []

        shots_per_hole = []
        for hole in holes:
            hole_n = hole.get("number")
            try:
                shot_data = call_api(
                    ENDPOINTS["shots"].format(card_id=card_id, hole_n=hole_n)
                )
                # 转换 semicircles → lat/lon
                deep_convert_locs(shot_data)
                # 统计
                if isinstance(shot_data, dict):
                    for hs in shot_data.get("holeShots", []) or []:
                        total_shots += len(hs.get("shots", []) or [])
                shots_per_hole.append({"holeNumber": hole_n, "data": shot_data})
                total_holes += 1
            except Exception as e:
                print(f"          ✗ 第 {hole_n} 洞逐杆失败：{e}")
                failures += 1

        rounds.append({"summary": card, "detail": detail, "shots": shots_per_hole})

    return {
        "clubs": clubs,
        "rounds": rounds,
        "_stats": {
            "rounds": len(rounds),
            "holes": total_holes,
            "shots": total_shots,
            "failures": failures,
        },
    }


# ----------------------------------------------------------------------------
# CLI 入口
# ----------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Garmin Golf 数据拉取器（中国/全球版）")
    parser.add_argument(
        "--domain",
        default="garmin.cn",
        choices=["garmin.cn", "garmin.com"],
        help="Garmin Connect 域名（默认 garmin.cn）",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=None,
        help="最多拉多少轮（用于试跑）",
    )
    parser.add_argument(
        "--logout",
        action="store_true",
        help="清除本地 token 缓存后退出",
    )
    args = parser.parse_args()

    if args.logout:
        if TOKEN_CACHE.exists():
            for f in TOKEN_CACHE.iterdir():
                f.unlink()
            TOKEN_CACHE.rmdir()
            print(f"✓ 已清除 {TOKEN_CACHE}")
        else:
            print("（无缓存，无需清除）")
        return 0

    print(f"\n📍 目标：{args.domain}\n")

    authenticate(args.domain)
    locale = "zh_CN" if args.domain.endswith(".cn") else "en"

    start = time.time()
    data = fetch_all(locale, max_rounds=args.max_rounds)

    # 元数据
    data["_meta"] = {
        "tool": "garmin-golf-cn",
        "fetcher": "python",
        "domain": args.domain,
        "locale": locale,
        "exportedAt": datetime.now().isoformat(),
        "elapsedSeconds": round(time.time() - start, 1),
        "coordinateNote": "startLoc/endLoc 已转十进制经纬度；原始值在 _raw_semicircles 字段",
    }

    DATA_DIR.mkdir(exist_ok=True)
    out_path = DATA_DIR / f"garmin-export-{datetime.now():%Y-%m-%d}.json"
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    stats = data.get("_stats", {})
    elapsed = data["_meta"]["elapsedSeconds"]
    print()
    print("=" * 60)
    print(f"  ✅ 导出完成（{elapsed} 秒）")
    print(f"  轮次：{stats.get('rounds', 0)}  ·  洞：{stats.get('holes', 0)}  "
          f"·  击球：{stats.get('shots', 0)}  ·  失败：{stats.get('failures', 0)}")
    print(f"  文件：{out_path}")
    print(f"  大小：{out_path.stat().st_size / 1024:.1f} KB")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
