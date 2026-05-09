"""
将 export.js 打包成 bookmarklet 形式。

输出：
    dist/export.bookmarklet.txt   完整的 javascript: URL，复制到书签
    dist/install.html             安装页（含可拖到书签栏的链接）

跑法（仓库根目录下）：
    python bookmarklet/build.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "export.js"
DIST = ROOT / "dist"
INSTALL_TEMPLATE = ROOT / "install.template.html"


def minify_js(source: str) -> str:
    """非常保守的 JS 压缩。

    只做：
      - 删除 /* ... */ 块注释
      - 删除 // 单行注释（注意保留 URL 中的 //）
      - 多空白合并
    不做：
      - 不重命名变量（保持可调试）
      - 不删除分号或括号
    """
    # 删除块注释（非贪婪）
    source = re.sub(r"/\*[\s\S]*?\*/", "", source)

    # 删除行注释，但只在 // 不是字符串里时
    # 简化策略：逐行处理，跳过出现在引号里的 //
    lines: list[str] = []
    for line in source.split("\n"):
        # 只在不在字符串里时去掉 //... 注释
        out_chars: list[str] = []
        in_str: str | None = None
        i = 0
        while i < len(line):
            ch = line[i]
            nxt = line[i + 1] if i + 1 < len(line) else ""
            if in_str:
                out_chars.append(ch)
                if ch == "\\" and nxt:  # 转义，保留两字符
                    out_chars.append(nxt)
                    i += 2
                    continue
                if ch == in_str:
                    in_str = None
                i += 1
                continue
            if ch in ("'", '"', "`"):
                in_str = ch
                out_chars.append(ch)
                i += 1
                continue
            if ch == "/" and nxt == "/":
                break  # 行尾注释
            out_chars.append(ch)
            i += 1
        lines.append("".join(out_chars))

    source = "\n".join(lines)

    # 多个空白合并为单空格（但保留字符串里的）
    # 简单处理：把 \n 和多空格变单空格
    source = re.sub(r"\s+", " ", source)
    source = source.strip()
    return source


def make_bookmarklet(minified: str) -> str:
    """包成 javascript: URL 形式。"""
    # quote 以避免 # & ? 等字符破坏 URL；但保留 JS 常见字符
    encoded = quote(minified, safe="!#$&()*+,/:;=?@~`-_.")
    return f"javascript:{encoded}"


INSTALL_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>garmin-golf-cn · 安装书签栏导出脚本</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body {{
      font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
      max-width: 720px; margin: 60px auto; padding: 0 20px;
      line-height: 1.7; color: #2a2a26; background: #f8f6f0;
    }}
    h1 {{ color: #9a7b3c; font-size: 28px; margin-bottom: 4px; }}
    .subtitle {{ color: #888; margin-bottom: 32px; font-size: 14px; }}
    h2 {{ color: #2a2a26; font-size: 18px; margin-top: 40px; }}
    code {{
      background: #2a2a26; color: #c4a060;
      padding: 2px 6px; border-radius: 3px;
      font-family: "SF Mono", Menlo, monospace;
      font-size: 13px;
    }}
    .bookmarklet {{
      display: inline-block; margin: 16px 0;
      padding: 14px 28px; border-radius: 8px;
      background: #9a7b3c; color: #1a1a18;
      text-decoration: none; font-weight: 600;
      box-shadow: 0 4px 12px rgba(154, 123, 60, 0.3);
      transition: transform 0.1s;
    }}
    .bookmarklet:hover {{ transform: translateY(-1px); }}
    .step {{
      background: white; border-left: 4px solid #9a7b3c;
      padding: 14px 20px; margin: 12px 0;
      border-radius: 0 6px 6px 0;
    }}
    .step .num {{
      display: inline-block; background: #9a7b3c; color: white;
      width: 24px; height: 24px; border-radius: 12px;
      text-align: center; line-height: 24px;
      font-weight: 700; margin-right: 10px;
    }}
    .privacy {{
      background: #ecf3eb; border-left: 4px solid #6fa86a;
      padding: 14px 20px; border-radius: 0 6px 6px 0;
      margin-top: 24px;
    }}
    footer {{ margin-top: 60px; color: #888; font-size: 13px; text-align: center; }}
    a {{ color: #9a7b3c; }}
  </style>
</head>
<body>
  <h1>garmin-golf-cn</h1>
  <div class="subtitle">浏览器书签栏导出脚本 · v{version}</div>

  <h2>一、安装：把按钮拖到书签栏</h2>
  <p>下面这个按钮，<strong>用鼠标拖到浏览器顶部的书签栏</strong>就完成安装：</p>
  <a class="bookmarklet" href="{loader_url}">⛳ 导出 Garmin 高尔夫</a>
  <p style="font-size: 13px; color: #888;">
    不能直接点击——必须用鼠标拖动到书签栏（Bookmarks Bar / 收藏栏）。<br>
    如果浏览器没显示书签栏，按 <code>⌘+Shift+B</code>（Mac）或 <code>Ctrl+Shift+B</code>（Win）打开。
  </p>
  <details style="margin-top: 16px; font-size: 13px;">
    <summary style="cursor: pointer; color: #888;">备用方案：如果上面这个不工作（CSP 拦截）</summary>
    <p>有些 Garmin 页面的 CSP（内容安全策略）可能拦截外部脚本加载。这种情况下用下面这个内联版本，体积大但完全自包含：</p>
    <a class="bookmarklet" style="background: #555;" href="{inline_url}">⛳ 导出 Garmin 高尔夫（内联版）</a>
    <p style="color: #888;">⚠️ Safari 用户优先用第一个；它的书签 URL 长度限制更严。</p>
  </details>

  <h2>二、使用：三步导出全部数据</h2>
  <div class="step"><span class="num">1</span>登录 <a href="https://connect.garmin.com" target="_blank">Garmin Connect</a>，确保你能在网页里看到自己的高尔夫记录。</div>
  <div class="step"><span class="num">2</span>在 Garmin Connect 任意页面，点击书签栏里的"⛳ 导出 Garmin 高尔夫"。</div>
  <div class="step"><span class="num">3</span>等待进度条走完（50 轮约 3-5 分钟），点"⬇ 下载"保存 JSON 文件到本地。</div>

  <h2>三、隐私说明</h2>
  <div class="privacy">
    <strong>这个脚本只读取你的数据，不上传任何东西到第三方服务器。</strong><br>
    所有网络请求都直接发给 <code>connect.garmin.com</code>，下载的 JSON 也只在你浏览器里生成。<br>
    脚本完整源码公开在
    <a href="https://github.com/xuyinglon43-gif/garmin-golf-cn/blob/main/bookmarklet/export.js" target="_blank">GitHub</a>，
    任何人都可以审计。
  </div>

  <h2>四、下一步做什么</h2>
  <p>下载到的 <code>garmin-golf-export-yyyy-mm-dd.json</code> 文件可以：</p>
  <ul>
    <li>用 <code>garmin-golf-cn</code> 的 Python 工具做 Strokes Gained 分析（即将上线）</li>
    <li>导入即将上线的网页工具，浏览器内可视化（即将上线）</li>
    <li>自己写代码做任何分析——数据完全是你的</li>
  </ul>

  <footer>
    许多帕 × Claude · MIT License ·
    <a href="https://github.com/xuyinglon43-gif/garmin-golf-cn">GitHub</a>
  </footer>
</body>
</html>
"""


#: GitHub raw 走 jsDelivr CDN（免费、CORS 友好、有 SLA），主分支自动跟踪
LOADER_TEMPLATE = """(function(){
  if(window._ggcLoading)return;
  window._ggcLoading=true;
  var s=document.createElement('script');
  s.src='https://cdn.jsdelivr.net/gh/xuyinglon43-gif/garmin-golf-cn@main/bookmarklet/export.js?t='+Date.now();
  s.onerror=function(){
    alert('❌ 脚本加载失败。可能是网络问题或 Garmin 页面的 CSP 限制。\\n\\n备选方案：见 install.html 的"备用方案"部分。');
    window._ggcLoading=false;
  };
  document.body.appendChild(s);
})();"""


def extract_version(source: str) -> str:
    """从 export.js 抓 VERSION 常量。"""
    m = re.search(r"const\s+VERSION\s*=\s*['\"]([^'\"]+)['\"]", source)
    return m.group(1) if m else "unknown"


def main() -> int:
    if not SRC.exists():
        print(f"❌ 找不到源文件：{SRC}", file=sys.stderr)
        return 1

    DIST.mkdir(exist_ok=True)
    source = SRC.read_text(encoding="utf-8")
    version = extract_version(source)

    # ---- 方案 A：Loader（推荐，小体积，自动更新） ----
    loader_min = minify_js(LOADER_TEMPLATE)
    loader_bm = make_bookmarklet(loader_min)
    (DIST / "loader.bookmarklet.txt").write_text(loader_bm, encoding="utf-8")

    # ---- 方案 B：Inline（备用，大体积，不依赖 CDN） ----
    inline_min = minify_js(source)
    inline_bm = make_bookmarklet(inline_min)
    (DIST / "inline.bookmarklet.txt").write_text(inline_bm, encoding="utf-8")

    # ---- 安装 HTML 页 ----
    out_html = DIST / "install.html"
    out_html.write_text(
        INSTALL_HTML.format(
            loader_url=loader_bm.replace('"', "&quot;"),
            inline_url=inline_bm.replace('"', "&quot;"),
            version=version,
        ),
        encoding="utf-8",
    )

    src_size = len(source.encode("utf-8"))
    print(f"✅ 源文件：               {src_size:>7,} 字节")
    print(f"✅ Loader bookmarklet：   {len(loader_bm):>7,} 字节  ⭐ 推荐")
    print(f"✅ Inline bookmarklet：   {len(inline_bm):>7,} 字节  （备用）")
    print(f"✅ 输出：")
    print(f"   - dist/loader.bookmarklet.txt")
    print(f"   - dist/inline.bookmarklet.txt")
    print(f"   - dist/install.html")
    print()
    print("打开 install.html 看带按钮的安装页。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
