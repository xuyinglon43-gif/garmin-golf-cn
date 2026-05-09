# Garmin Connect 高尔夫数据 API 参考

> 这是一份**非官方**端点参考。Garmin 没有公开高尔夫数据 API，以下端点全部来自社区反向工程，用于自取自己账号的数据。

调研日期：2026-05-09
来源：`gsingers/garmin_golf` JS 书签栏脚本（v3 2021-03-18）+ Garmin 论坛公开讨论

---

## 端点清单

所有端点都在 `https://connect.garmin.com/modern/proxy/gcs-golfcommunity/api/v2/` 下，需要先在浏览器登录 Garmin Connect，然后凭 cookies 调用。

| # | 路径 | 用途 | 是否必需 |
|---|---|---|---|
| 1 | `/club/player?per-page=1000&include-stats=true` | 所有球杆 + 距离统计 | ⭐ 必需（识别球杆） |
| 2 | `/scorecard/summary?per-page=10000&user-locale=en` | 所有轮次摘要 | ⭐ 必需 |
| 3 | `/scorecard/detail?scorecard-ids={id}&include-longest-shot-distance=true` | 单轮次明细 | ⭐ 必需 |
| 4 | `/shot/scorecard/{cardId}/hole?hole-numbers={n}&image-size=IMG_730X730` | **逐杆数据**（每洞） | ⭐⭐⭐ 核心 |
| 5 | `/player/stats` | 玩家整体统计 | ⚪ 可选（我们自己算 SG） |
| 6 | `/shot/stats/drive` | 开球统计（最近 10 轮） | ⚪ 可选 |
| 7 | `/shot/stats/approach` | 进攻杆统计（最近 10 轮） | ⚪ 可选 |
| 8 | `/shot/stats/chip` | 切球统计（最近 10 轮） | ⚪ 可选 |
| 9 | `/shot/stats/putt` | 推杆统计（最近 10 轮） | ⚪ 可选 |

**核心通路**：1（球杆库） + 2（轮次列表） + 对每轮调用 3（明细） + 对每洞调用 4（逐杆）。这是最少必需调用集。

5-9 是 Garmin 自己算好的统计，我们要自己用 Strokes Gained 算法重算，所以**可以全部跳过**节省大量请求。

---

## 关键字段（根据社区记录推断，待真实数据校准）

### 端点 4 返回结构（最重要）

```json
{
  "holeShots": [
    {
      "holeNumber": 1,
      "shots": [
        {
          "shotNumber": 1,
          "clubId": "driver",
          "clubType": "Driver",
          "startLoc": { "lat": 426337022, "lon": -968558063 },
          "endLoc":   { "lat": 426541230, "lon": -968517823 },
          "distance": 245,
          "lieType": "Tee"
        },
        {
          "shotNumber": 2,
          "clubId": "7i",
          "startLoc": { "lat": 426541230, "lon": -968517823 },
          "endLoc":   { "lat": 426601122, "lon": -968501544 },
          "distance": 145,
          "lieType": "Fairway"
        }
      ]
    }
  ]
}
```

⚠️ **字段名不 100% 确认**——需要拿到真实账号数据后核对。`lieType` 可能是 `Fairway/Rough/Bunker/Green/Tee/Penalty/OutOfBounds` 等枚举值，也可能不存在（需要从坐标 + 球场地图推断）。

### 坐标格式

Garmin 内部用 **semicircles**（半圆制）：

```
decimal_degrees = semicircles × (180 / 2^31)
```

JavaScript 实现：
```js
function semicirclesToLatLon(semicircles) {
  return semicircles * (180 / Math.pow(2, 31));
}
```

Python 实现：
```python
def semicircles_to_decimal(semicircles: int) -> float:
    return semicircles * (180 / 2**31)
```

---

## 认证机制

书签栏脚本利用**浏览器已登录的 cookies session**，不需要单独 OAuth：

- 用户先在浏览器登录 Garmin Connect
- 当前页面 URL 必须是 `connect.garmin.com` 开头
- jQuery `$.getJSON()` 或 `fetch()` with `credentials: 'include'` 自动携带 cookies

如果用 Python 抓取（Phase 5），用 `python-garminconnect` 走 OAuth 即可。

---

## 调用规模估算

一个普通用户，假设打了 50 轮，每轮 18 洞：

| 端点 | 调用次数 |
|---|---|
| 端点 1（球杆） | 1 |
| 端点 2（轮次列表） | 1 |
| 端点 3（每轮明细） | 50 |
| 端点 4（每洞逐杆） | 50 × 18 = **900** ⚠️ |
| 端点 5-9（可选统计） | 5（如果调用） |
| **总计** | **957 次请求** |

900 次单洞请求是大头。**优化建议**：
- 串行调用（避免被 Garmin 限流）
- 加 100ms 间隔（保守估计）
- 总耗时 ≈ 100 秒（~1.7 分钟）
- 加上网络延迟实际可能 3-5 分钟

⚠️ **未来端点变更风险**：Garmin 可能合并或重构 API 端点（例如做成"一次拉一整轮所有杆"的端点），届时需要更新脚本。

---

## `gsingers/garmin_golf` 的实现局限

**优点**：
- 4 年前已经跑通，端点经过实战验证
- jQuery 写法兼容老 Garmin Connect 版本
- 一次性下载所有数据成 JSON，易于备份

**局限**（我们要改进的）：
- ⚠️ **依赖 jQuery**：Garmin 可能在未来 SPA 重构中移除 jQuery
- ⚠️ **同步全量下载**：每次都拉全部，不支持增量
- ⚠️ **无进度提示**：长时间黑盒等待，用户以为卡了
- ⚠️ **错误处理粗糙**：单次失败 fail 后用 console.log，用户看不到
- ⚠️ **`pendingRequests` 计数器有竞态风险**：并发回调时计数可能不准
- ⚠️ **无限流保护**：900 个请求一窝蜂上去可能被 Garmin 拦
- ⚠️ **不转换 semicircles**：导出的 JSON 还是 semicircles，下游不友好
- ⚠️ **无日期过滤**：用户想"只看最近 3 个月"做不到
- ⚠️ **会调用 5 个用不上的统计端点**：浪费请求
- ⚠️ **英文 UI**：国内用户不友好

---

## `garmin-golf-cn` 的设计目标

| 维度 | gsingers | garmin-golf-cn |
|---|---|---|
| 依赖 | jQuery | 原生 `fetch()` |
| 下载策略 | 全量 | 全量 / 增量 / 日期过滤 |
| 进度提示 | ❌ 静默 | ✅ 进度条 + 百分比 |
| 错误处理 | console.log | ✅ 模态框 + 重试 |
| 限流 | ❌ 无 | ✅ 100ms 间隔 + 重试退避 |
| 坐标 | semicircles | ✅ 已转 lat/lon |
| 用不上的端点 | 全调用 | ✅ 跳过统计端点 |
| 输出 | 单一原始 JSON | ✅ 原始 JSON + 标准化 JSON 双份 |
| UI 语言 | 英文 | ✅ 中文 |

---

## 下一步（Phase 1.2 启动）

调研结束。Phase 1.2 实现 `bookmarklet/export.js`：

1. 用纯 `fetch()` 重写所有端点调用
2. 跳过 5 个统计端点（端点 5-9）
3. 加进度模态框
4. 实现 100ms 限流间隔 + 失败重试
5. 输出双份 JSON：`golf-export-raw.json`（原始）+ `golf-export-standardized.json`（已转 lat/lon + 已对齐内部 schema）
6. 中文 UI

预计代码量：~300-400 行（含进度 UI 和错误处理）。
