"""
garmin-golf-cn · Playwright 端 Garmin 数据拉取器

为什么用 Playwright 而不是 garth：
    Garmin Connect 的 /golf-api/ 端点（在 connect.{garmin.cn,garmin.com} 上）
    只接受 Web SPA 客户端的 OAuth token + session cookies。garth 库走的是
    手机端 OAuth client_id（GARMIN_CONNECT_MOBILE_ANDROID_DI），调用
    /golf-api/ 直接被网关 401 拒绝。

    Playwright 启动一个真实的 Chromium 浏览器，直接复用浏览器自身的认证流程，
    所以一切跟你在 Safari 里手动操作完全一样——但是自动化 + 无人值守。

用法：
    第一次：    python3.11 scripts/fetch_garmin_pw.py
                  → 自动打开浏览器窗口，你手动登录一次，登录状态自动保存
    后续：      python3.11 scripts/fetch_garmin_pw.py
                  → 完全无 UI（headless），用保存的状态自动拉数据
    试跑 3 轮： python3.11 scripts/fetch_garmin_pw.py --max-rounds 3
    清状态：    python3.11 scripts/fetch_garmin_pw.py --logout

输出：data/garmin-export-{yyyy-mm-dd}.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    print("❌ 缺依赖：playwright")
    print("   请先安装：python3.11 -m pip install --user playwright")
    print("           python3.11 -m playwright install chromium")
    sys.exit(1)


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
STATE_DIR = Path.home() / ".garmincache"
STATE_FILE = STATE_DIR / "playwright-state.json"

GOLF_API_BASE = "/golf-api/gcs-golfcommunity/api/v2"
RATE_LIMIT_S = 0.12


# ----------------------------------------------------------------------------
# semicircles 转 lat/lon
# ----------------------------------------------------------------------------

def semicircles_to_decimal(s):
    if s is None:
        return None
    return s * (180 / 2**31)


def deep_convert_locs(obj):
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if k in ("startLoc", "endLoc") and isinstance(v, dict):
                obj[k] = {
                    "lat": semicircles_to_decimal(v.get("lat")),
                    "lon": semicircles_to_decimal(v.get("lon")),
                    "_raw_semicircles": {"lat": v.get("lat"), "lon": v.get("lon")},
                }
            else:
                deep_convert_locs(v)
    elif isinstance(obj, list):
        for x in obj:
            deep_convert_locs(x)


# ----------------------------------------------------------------------------
# 登录（仅首次）
# ----------------------------------------------------------------------------

def interactive_login(domain: str) -> None:
    """打开有界面浏览器，让用户手动登录，保存状态。"""
    base_url = f"https://connect.{domain}/"
    print()
    print("=" * 60)
    print("  🌐 第一次使用：需要手动登录一次")
    print("=" * 60)
    print(f"  浏览器即将打开 {base_url}")
    print(f"  请在浏览器里登录你的 Garmin Connect 账号")
    print(f"  登录成功后，回到这个终端按 Enter 保存状态")
    print("=" * 60)
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
        )
        page = context.new_page()
        page.goto(base_url, timeout=60000)

        input("  ⏳ 登录完成后，回这里按 Enter ...")

        STATE_DIR.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(STATE_FILE))
        browser.close()

    print(f"\n✓ 登录状态已保存：{STATE_FILE}")
    print("  下次运行将直接 headless 模式，无需再登录。\n")


# ----------------------------------------------------------------------------
# 用 Playwright + 浏览器原生 fetch 拉数据
# ----------------------------------------------------------------------------

# 这段 JS 在浏览器里运行，借用浏览器现成的 session cookies 调用 /golf-api/
JS_FETCH = """
async (path) => {
    const resp = await fetch(path, {
        credentials: 'include',
        headers: {'Accept': 'application/json'},
    });
    if (!resp.ok) {
        return {__error: `HTTP ${resp.status}`, __status: resp.status};
    }
    const ctype = resp.headers.get('content-type') || '';
    if (!ctype.includes('json')) {
        return {__error: `Non-JSON (${ctype})`, __body: (await resp.text()).slice(0, 200)};
    }
    return await resp.json();
}
"""


def _fetch_via_navigation(page, browser, captured_responses, max_rounds, scorecards_url, domain):
    """Fallback：纯靠浏览器 navigation 触发 SPA 加载，从响应里截数据。

    用法是逐个 scorecard 导航 + 拦截 /golf-api/ 响应。慢但绝对靠谱。
    """
    import re
    print()
    print("  🔄 切换到 navigation 模式：通过 SPA 自身导航来触发数据加载")

    summary_data = captured_responses.get("summary", {})
    cards = summary_data.get("scorecardSummaries", []) or []
    if max_rounds:
        cards = cards[:max_rounds]
    print(f"  ✓ 用 SPA summary：{len(cards)} 轮"
          + (f"（限到前 {max_rounds}）" if max_rounds else ""))

    rounds_data = []
    total_shots = total_holes = failures = 0

    # 按 scorecard ID 分类收集 detail 和 shots
    captured_details: dict[str, dict] = {}
    captured_shots: dict[str, list] = {}

    def on_response(resp):
        url = resp.url
        if "/golf-api/scorecard/detail" in url and resp.status == 200:
            m = re.search(r"scorecard-ids=([^&]+)", url)
            if m:
                try:
                    captured_details[m.group(1)] = resp.json()
                except Exception:
                    pass
        elif "/golf-api/shot/scorecard/" in url and resp.status == 200:
            m = re.search(r"/shot/scorecard/([^/]+)/hole", url)
            if m:
                try:
                    captured_shots.setdefault(m.group(1), []).append(resp.json())
                except Exception:
                    pass

    page.on("response", on_response)

    for i, card in enumerate(cards, 1):
        card_id = card.get("id")
        cname = card.get("courseName", "未知球场")
        print(f"  [{i:>3}/{len(cards)}] {cname}", flush=True)
        try:
            page.goto(f"{scorecards_url}/{card_id}",
                      timeout=30000, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(0.5)
        except PWTimeout:
            pass

        detail = captured_details.get(card_id)
        shots_list = captured_shots.get(card_id, [])

        if not detail:
            print(f"          ✗ 没拦到 detail")
            failures += 1
            continue

        # 处理 shots
        shots_per_hole = []
        for shot_data in shots_list:
            deep_convert_locs(shot_data)
            if isinstance(shot_data, dict):
                for hs in shot_data.get("holeShots", []) or []:
                    total_shots += len(hs.get("shots", []) or [])
                    if hs.get("shots"):
                        total_holes += 1
            shots_per_hole.append({"data": shot_data})

        rounds_data.append({"summary": card, "detail": detail, "shots": shots_per_hole})

    browser.close()

    return {
        "clubs": [],  # 这条路径没拉 clubs
        "rounds": rounds_data,
        "_stats": {
            "rounds": len(rounds_data),
            "holes": total_holes,
            "shots": total_shots,
            "failures": failures,
            "mode": "navigation",
        },
    }


def call_api(page, path: str, retry: int = 3):
    """在浏览器内运行 fetch，结果直接返回到 Python。"""
    last_err = None
    for attempt in range(retry):
        time.sleep(RATE_LIMIT_S)
        try:
            result = page.evaluate(JS_FETCH, path)
            if isinstance(result, dict) and "__error" in result:
                last_err = f"{result['__error']}"
                if result.get("__body"):
                    last_err += f" body={result['__body']}"
                if attempt < retry - 1 and result.get("__status", 0) >= 500:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(last_err)
            return result
        except Exception as e:
            last_err = e
            if attempt < retry - 1:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"调用 {path} 失败：{last_err}")


def fetch_all(domain: str, max_rounds: int | None = None,
              headless: bool = False) -> dict:
    locale = "zh_CN" if domain.endswith(".cn") else "en"
    # 直接进 /app/scorecards 页面——这会触发 SPA 自己调 /golf-api/，
    # 既能建立 golf-api session 又能让我们抓到 SPA 的真实请求头
    scorecards_url = f"https://connect.{domain}/app/scorecards"

    # 收集 SPA 实际发出的 /golf-api/ 请求头部（用来对比 + 复用）
    captured_headers: dict[str, str] = {}
    captured_responses: dict[str, dict] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )
        context = browser.new_context(
            storage_state=str(STATE_FILE),
            locale="zh-CN",
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

        page = context.new_page()
        page.on("pageerror", lambda err: print(f"  [浏览器错误] {err}"))

        # 关键：拦截 /golf-api/ 请求，把头部存下来
        def on_request(req):
            if "/golf-api/" in req.url:
                # 第一个就够了，记下来
                if not captured_headers:
                    for k, v in req.headers.items():
                        captured_headers[k] = v

        def on_response(resp):
            if "/golf-api/scorecard/summary" in resp.url and resp.status == 200:
                try:
                    captured_responses["summary"] = resp.json()
                except Exception:
                    pass

        page.on("request", on_request)
        page.on("response", on_response)

        print(f"  → 打开 {scorecards_url}（让 SPA 自己触发 /golf-api/）")
        try:
            page.goto(scorecards_url, timeout=45000, wait_until="domcontentloaded")
        except PWTimeout:
            print(f"  ⚠️  页面加载超时，继续等待")

        # 等 SPA 完成它自己的所有 /golf-api/ 调用
        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except PWTimeout:
            pass

        # 看 SPA 的请求情况
        print(f"\n  📊 SPA 抓取情况：")
        print(f"     抓到 /golf-api/ 请求：{1 if captured_headers else 0}（看到 SPA 自己跑通 = 验证通过）")
        if captured_headers:
            sensitive = {"authorization", "cookie"}
            for k, v in captured_headers.items():
                if k.lower() in sensitive:
                    print(f"     {k}: <{len(v)} chars hidden>")
                elif k.lower().startswith(":"):
                    continue  # HTTP/2 伪头部
                else:
                    short_v = v[:80] + "..." if len(v) > 80 else v
                    print(f"     {k}: {short_v}")
        print(f"     SPA 抓到的 summary：{'✓ 有' if 'summary' in captured_responses else '✗ 没抓到'}")

        if not captured_headers:
            print()
            print("  ✗ SPA 自己也没成功调 /golf-api/——状态可能失效")
            print("  → 跑：python3.11 scripts/fetch_garmin_pw.py --relogin")
            browser.close()
            sys.exit(1)

        # 用 SPA 抓到的 summary 直接当作我们的 summary（已经成功了！）
        if "summary" in captured_responses:
            print(f"\n  ✓ 直接复用 SPA 抓到的 summary（轮次："
                  f"{len(captured_responses['summary'].get('scorecardSummaries', []))}）")

        # 现在用同一个 page evaluate，看我们自己 fetch 能不能也通过
        print(f"\n  → 测试自主 /golf-api/ 调用...")
        try:
            probe = call_api(
                page,
                f"{GOLF_API_BASE}/scorecard/summary?per-page=1&user-locale={locale}",
                retry=2,
            )
            if isinstance(probe, dict) and "scorecardSummaries" in probe:
                print(f"  ✓ 自主调用通过")
            else:
                print(f"  ⚠️  自主调用响应异常：{str(probe)[:200]}")
        except Exception as e:
            print(f"  ✗ 自主调用仍失败：{e}")
            print(f"  → 但我们有 SPA 抓到的 summary，可以继续用 navigation 模式")
            # Fallback: 用 navigation + 拦截响应模式
            return _fetch_via_navigation(
                page, browser, captured_responses, max_rounds, scorecards_url, domain
            )

        # 1. 球杆库
        print("\n[1/3] 拉取球杆库…")
        try:
            clubs = call_api(page, f"{GOLF_API_BASE}/club/player?per-page=1000&include-stats=true") or []
            print(f"  ✓ {len(clubs)} 支球杆")
        except Exception as e:
            print(f"  ⚠️ 球杆库失败（{e}），继续")
            clubs = []

        # 2. 轮次列表
        print("\n[2/3] 拉取轮次列表…")
        summary = call_api(
            page,
            f"{GOLF_API_BASE}/scorecard/summary?per-page=10000&user-locale={locale}",
        )
        cards = (summary or {}).get("scorecardSummaries", [])
        if max_rounds:
            cards = cards[:max_rounds]
        print(f"  ✓ 找到 {len(cards)} 轮"
              + (f"（已限到前 {max_rounds} 轮）" if max_rounds else ""))

        if not cards:
            return {"clubs": clubs, "rounds": [], "_stats": {"rounds": 0}}

        # 3. 每轮明细 + 每洞逐杆
        print(f"\n[3/3] 拉取每轮明细 + 逐杆…")
        rounds_data = []
        total_shots = total_holes = failures = 0

        for i, card in enumerate(cards, 1):
            card_id = card.get("id")
            cname = card.get("courseName", "未知球场")
            print(f"  [{i:>3}/{len(cards)}] {cname}", flush=True)

            try:
                detail = call_api(
                    page,
                    f"{GOLF_API_BASE}/scorecard/detail"
                    f"?scorecard-ids={card_id}&include-longest-shot-distance=true",
                )
            except Exception as e:
                print(f"          ✗ 明细失败：{e}")
                failures += 1
                continue

            holes = []
            try:
                sc_list = (detail or {}).get("scorecardDetails", []) or []
                sc = next((x for x in sc_list if x and "scorecard" in x), None)
                if sc:
                    holes = (sc.get("scorecard", {}) or {}).get("holes", []) or []
            except Exception:
                holes = []

            shots_per_hole = []
            for hole in holes:
                hole_n = hole.get("number")
                try:
                    shot_data = call_api(
                        page,
                        f"{GOLF_API_BASE}/shot/scorecard/{card_id}/hole?hole-numbers={hole_n}",
                    )
                    deep_convert_locs(shot_data)
                    if isinstance(shot_data, dict):
                        for hs in shot_data.get("holeShots", []) or []:
                            total_shots += len(hs.get("shots", []) or [])
                    shots_per_hole.append({"holeNumber": hole_n, "data": shot_data})
                    total_holes += 1
                except Exception as e:
                    print(f"          ✗ 第 {hole_n} 洞失败：{e}")
                    failures += 1

            rounds_data.append({
                "summary": card,
                "detail": detail,
                "shots": shots_per_hole,
            })

        browser.close()

    return {
        "clubs": clubs,
        "rounds": rounds_data,
        "_stats": {
            "rounds": len(rounds_data),
            "holes": total_holes,
            "shots": total_shots,
            "failures": failures,
        },
    }


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Garmin Golf Playwright 拉取器")
    parser.add_argument("--domain", default="garmin.cn",
                        choices=["garmin.cn", "garmin.com"])
    parser.add_argument("--max-rounds", type=int, default=None)
    parser.add_argument("--logout", action="store_true",
                        help="清除登录状态")
    parser.add_argument("--relogin", action="store_true",
                        help="清除并重新登录")
    parser.add_argument("--headless", action="store_true",
                        help="完全无 UI（容易被 Cloudflare 反爬拦截，默认关闭）")
    args = parser.parse_args()

    if args.logout:
        if STATE_FILE.exists():
            STATE_FILE.unlink()
            print(f"✓ 已删除 {STATE_FILE}")
        return 0

    if args.relogin and STATE_FILE.exists():
        STATE_FILE.unlink()

    if not STATE_FILE.exists():
        interactive_login(args.domain)

    print(f"\n📍 目标：connect.{args.domain}"
          + ("（headless）" if args.headless else "（可见浏览器，避免反爬）"))
    start = time.time()
    data = fetch_all(args.domain, max_rounds=args.max_rounds, headless=args.headless)

    data["_meta"] = {
        "tool": "garmin-golf-cn",
        "fetcher": "playwright",
        "domain": args.domain,
        "exportedAt": datetime.now().isoformat(),
        "elapsedSeconds": round(time.time() - start, 1),
    }

    DATA_DIR.mkdir(exist_ok=True)
    out = DATA_DIR / f"garmin-export-{datetime.now():%Y-%m-%d}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    s = data["_stats"]
    print()
    print("=" * 60)
    print(f"  ✅ 完成（{data['_meta']['elapsedSeconds']} 秒）")
    print(f"  轮次 {s['rounds']}  ·  洞 {s['holes']}  "
          f"·  击球 {s['shots']}  ·  失败 {s['failures']}")
    print(f"  文件：{out}")
    print(f"  大小：{out.stat().st_size / 1024:.1f} KB")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
