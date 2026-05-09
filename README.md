# garmin-golf-cn

> 给中国佳明高尔夫用户的开源击杆增益（Strokes Gained）分析工具

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-green.svg)](https://www.python.org/)

## 项目愿景

国内有几万 Garmin 高尔夫用户（Approach S70 / Venu X1 / G82 / Z30 / CT10 / CT1 / fenix 等），但 Garmin Golf app 自带的统计很浅，只有 fairway%、GIR%、推杆数这种**结果指标**，无法回答"**我哪里漏了杆**"。

`garmin-golf-cn` 把你 Garmin Connect 上的逐杆数据拉到本地，用职业球手通用的 **Strokes Gained（击杆增益）** 框架做深度分析，告诉你：

- 开球、进攻杆、果岭周围、推杆**各项相对基线赚/赔了多少杆**
- 跟你**同差点档位的业余球手平均**比，你的强项弱项是什么
- 哪些距离段、哪些球洞是你最大的"杆数漏洞"

## 为什么是它

| | Garmin Golf 自带 | Arccos Caddie | garmin-golf-cn |
|---|---|---|---|
| 中文体验 | 翻译生硬 | ❌ 仅英文 | ✅ 完整中文 |
| Strokes Gained 分析 | ❌ | ✅ | ✅ |
| **业余球手基线**（不是 PGA Tour） | ❌ | ⚠️ 部分 | ✅ 6 档差点 |
| 数据所有权 | 锁在 Garmin 云 | 锁在 Arccos 云 | ✅ 本地 SQLite/JSON |
| 隐私 | — | 上传第三方 | ✅ 全部本地 |
| 价格 | 免费 | $100/年 | ✅ 免费 MIT |

## 当前状态

**Phase 0 · Day 0** ✅
- [x] 核心 SG 计算引擎（`core/sg.py`）
- [x] 6 档差点基线（差点 0/5/10/15/20/25）
- [x] 中文术语映射
- [x] 模拟数据 demo（无需 Garmin 设备即可跑通）

**Phase 1 · 浏览器书签栏导出** ✅
- [x] [Garmin API 端点完整参考](docs/garmin-api-reference.md)
- [x] [浏览器书签栏脚本](bookmarklet/export.js)（fetch + 进度条 + 限流 + 重试）
- [x] [中文安装页](bookmarklet/dist/install.html)（loader + inline 双版本）
- [x] [使用文档](docs/bookmarklet-cn.md)

**进行中 / 规划中**
- [ ] 数据格式标准化层（`core/garmin_adapter.py`）
- [ ] 中文 PDF 月报（weasyprint，复用 Noto CJK 管道）
- [ ] 网站工具集成（[golf-strategy-tools](https://golf-strategy-tools.vercel.app) 的工具 #5）
- [ ] Python 抓取器（基于 `python-garminconnect`）
- [ ] CLI 命令行工具（`ggc sync` / `ggc sg` / `ggc report`）

## 快速试跑（Day 0）

```bash
git clone https://github.com/xuyinglon43-gif/garmin-golf-cn.git
cd garmin-golf-cn
python examples/demo_simulated.py
```

预期输出：

```
═══════════════════════════════════════════
   garmin-golf-cn · Strokes Gained Demo
═══════════════════════════════════════════
轮次：阳光城高尔夫俱乐部 · 2026-05-08 · 总杆 89
对比基线：业余 15 差点

▸ 开球 SG（off the tee）       :  -0.32 杆/轮
▸ 进攻杆 SG（approach）        :  -1.45 杆/轮  ⚠️ 最弱
▸ 果岭周围 SG（around green）  :  +0.21 杆/轮
▸ 推杆 SG（putting）           :  -0.84 杆/轮

总 SG（vs 业余 15 差点基线）   :  -2.40 杆/轮
════════════════════════════════
洞察：你的进攻杆比同差点球手多丢 1.5 杆/轮，建议重点练 100-150 码铁杆
```

## 项目结构

```
garmin-golf-cn/
├── core/                    # SG 计算核心
│   ├── sg.py                # Strokes Gained 引擎
│   ├── baselines/           # 6 档差点基线 JSON
│   └── terms.py             # 中文术语映射
├── examples/                # 示例脚本
│   ├── demo_simulated.py    # 模拟数据 demo
│   └── sample_round.json    # 一份模拟轮次数据
└── docs/
    └── strokes-gained-explained-cn.md   # SG 原理中文科普
```

## 数据来源

- **PGA Tour 基线**：Mark Broadie《Every Shot Counts》(2014) 公开数据
- **业余球手基线**：基于 Lou Stagner / Arccos 公开统计 + Broadie 业余章节，按差点 0/5/10/15/20/25 分档
- 详见 `core/baselines/README.md`

## 路线图

**Phase 1（开源核心库）** ⬅️ 当前
- SG 计算引擎
- 6 档基线
- Demo

**Phase 2（数据接入）**
- Garmin Connect 抓取（API 端点已确认可用）
- 浏览器书签栏脚本（小白友好）
- 本地 SQLite 存储

**Phase 3（产品化）**
- CLI 工具
- 中文 PDF 月报
- 网站工具 #5 集成

## 协议

MIT License — 见 [LICENSE](LICENSE)

## 致敬

- Mark Broadie 教授奠定的 Strokes Gained 框架
- [`cyberjunky/python-garminconnect`](https://github.com/cyberjunky/python-garminconnect) 的 Garmin OAuth 实现
- [`gsingers/garmin_golf`](https://github.com/gsingers/garmin_golf) 反向工程 Garmin Golf API 端点
- 许多帕 × Claude · [高尔夫策略工具箱](https://golf-strategy-tools.vercel.app)
