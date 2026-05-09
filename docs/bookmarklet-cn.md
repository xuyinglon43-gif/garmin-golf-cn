# 浏览器书签栏导出工具 · 使用指南

如果你是普通 Garmin 用户，**这个工具不需要任何技术背景**——把按钮拖到书签栏，点一下，等几分钟，下载 JSON 文件，就这么简单。

## 30 秒上手

### 第一步：安装

1. 打开 [bookmarklet/dist/install.html](../bookmarklet/dist/install.html)（在你电脑上双击或在浏览器里打开）
2. 把页面上那个金色"⛳ 导出 Garmin 高尔夫"按钮**用鼠标拖**到浏览器顶部书签栏

⚠️ **关键**：不要点击按钮，要**拖动**。

如果浏览器没显示书签栏：
- Mac Chrome/Edge：`⌘ + Shift + B`
- Win Chrome/Edge：`Ctrl + Shift + B`
- Safari：`View → Show Favorites Bar`
- Firefox：右键导航栏 → `Customize Toolbar`

### 第二步：使用

1. 浏览器打开 https://connect.garmin.com 并登录
2. 任意一个 Garmin Connect 页面，点击书签栏的"⛳ 导出 Garmin 高尔夫"
3. 等待进度条走完
4. 点击"⬇ 下载"按钮，文件会保存到下载目录

完成。文件名形如 `garmin-golf-export-2026-05-09.json`。

## 时间预期

| 你的轮次数 | 大致耗时 |
|---|---|
| 10 轮以内 | 30 秒 - 1 分钟 |
| 20-50 轮 | 2-5 分钟 |
| 100+ 轮 | 10-15 分钟 |

时间花在抓"逐杆数据"——每洞需要单独发一个请求，限流后总共会很多次请求。

## 这个文件里有什么

下载到的 JSON 文件结构：

```json
{
  "_meta": {
    "tool": "garmin-golf-cn",
    "version": "0.2.0-bookmarklet",
    "exportedAt": "2026-05-09T03:45:00.000Z",
    "stats": {
      "rounds": 47,
      "holes": 846,
      "shots": 4231,
      "failures": 0,
      "elapsedSeconds": 187.3
    }
  },
  "clubs": [
    /* 你的所有球杆 + 距离统计 */
  ],
  "rounds": [
    {
      "summary": { /* 这一轮的概览：日期、球场、总杆等 */ },
      "detail":  { /* 每洞 par 数、得分、推杆数等 */ },
      "shots":   [ /* 每洞所有击球，含起点/终点经纬度 + 距离 + 球杆 */ ]
    },
    /* ... 更多轮次 */
  ]
}
```

**关键字段：起点/终点坐标已经从 Garmin 的 semicircles 半圆制转成了标准的十进制经纬度（lat/lon）**，可以直接拿去用 Google Maps、Mapbox 这类工具可视化。

## 隐私与安全

✅ **完全本地运行**：脚本只在你的浏览器里跑，所有请求直接发给 `connect.garmin.com`，不经过任何第三方服务器。

✅ **源码公开**：[bookmarklet/export.js](../bookmarklet/export.js) 任何人可审计。loader 版本通过 jsDelivr CDN 加载这个文件（一个 GitHub 镜像服务）。

✅ **MIT 协议**：免费开源，没有任何账号绑定或数据收集。

✅ **只读不写**：脚本仅调用 GET 请求，不会修改你的 Garmin 账号数据。

## 常见问题

**Q：点了书签栏没反应？**
A：检查 1）当前页面是 `connect.garmin.com` 开头吗 2）你登录了吗？没登录会弹提示

**Q：进度卡在某一轮？**
A：脚本会自动重试 3 次。如果卡住超过 30 秒看看浏览器 console（F12）有没有报错。失败会跳过该轮继续，最后会显示失败次数。

**Q：导出过程能关浏览器吗？**
A：不能。脚本在浏览器内运行，关 tab 就停了。但可以**取消**——弹窗里有取消按钮，已下载的轮次不会丢失。

**Q：用 Loader 版本失败，提示 CSP？**
A：用安装页底部的"备用方案"——内联版（自包含 14KB 脚本，不依赖 CDN）。

**Q：能定时自动跑吗？**
A：浏览器书签栏不能。等 Phase 5 上线 Python CLI 后，可以配 cron 自动同步。

**Q：导出的数据 Garmin 会改格式吗？**
A：可能会。Garmin 没有公开 API，端点是反向工程来的。如果某天突然失败，请[提 issue](https://github.com/xuyinglon43-gif/garmin-golf-cn/issues)，我会跟进。

## 下一步：用这个 JSON 干嘛

短期：
- 备份个人数据（数据所有权回到自己手上）
- 用任何工具可视化（Google Maps 看击球轨迹、Excel 算分类统计）

中期（即将上线）：
- 喂给 [garmin-golf-cn](../README.md) 的 Strokes Gained 分析引擎
- 生成中文 PDF 月报
- 接入 [golf-strategy-tools 网站](https://golf-strategy-tools.vercel.app) 的工具 #5 在线分析

长期（设备到货后）：
- 上 Python CLI，自动定期同步
- 落点类型推断精化（基于真实数据校准）
- 个人化训练计划生成

---

🔗 主项目说明：[README.md](../README.md)
🐛 报 Bug / 提建议：[GitHub Issues](https://github.com/xuyinglon43-gif/garmin-golf-cn/issues)
