/**
 * garmin-golf-cn · 浏览器书签栏导出脚本
 *
 * 使用方法：
 *   1. 浏览器登录 https://connect.garmin.com
 *   2. 打开任意一个 connect.garmin.com 页面
 *   3. 点击书签栏里的"导出 Garmin 高尔夫"
 *   4. 等待进度条完成，点击下载按钮保存 JSON
 *
 * 这个脚本只读取数据，绝不修改你的账号或上传任何东西到第三方服务器。
 *
 * 端点参考：见 docs/garmin-api-reference.md
 * 协议：MIT
 */

(async function garminGolfCnExport() {
  'use strict';

  // ============================================================
  // 配置
  // ============================================================

  const VERSION = '0.2.3-bookmarklet';
  // API 路径区分（实测 2026-05 connect.garmin.cn 的实际路径）：
  //   /modern/proxy/gcs-golfcommunity/...  ← gsingers 老路径，已废弃
  //   /golf-api/gcs-golfcommunity/...      ← 现代路径（.cn 和 .com 都用这个）
  const BASE = `${location.origin}/golf-api/gcs-golfcommunity/api/v2`;
  // 中文用户用 zh_CN locale，让响应里的球场名等是中文
  const USER_LOCALE = (location.hostname.endsWith('.cn') ? 'zh_CN' : 'en');
  const RATE_LIMIT_MS = 120;          // 每个请求之间的最小间隔（毫秒）
  const MAX_RETRIES = 3;              // 单个请求最多重试次数
  const RETRY_BACKOFF_MS = 1000;      // 重试退避基数（指数退避）

  // ============================================================
  // 环境检查
  // ============================================================

  // 接受 connect.garmin.com（全球版）和 connect.garmin.cn（中国版）
  if (!/garmin\.(com|cn)$/.test(location.hostname)) {
    alert(
      '❌ 你需要先登录 Garmin Connect 才能使用此脚本。\n\n' +
      '请打开 https://connect.garmin.com（或 connect.garmin.cn）' +
      '登录后，再点击书签栏导出按钮。\n\n' +
      `当前页面：${location.hostname}`
    );
    return;
  }

  // 移除可能存在的旧弹窗
  const oldModal = document.getElementById('_ggc-modal');
  if (oldModal) oldModal.remove();
  const oldStyle = document.getElementById('_ggc-style');
  if (oldStyle) oldStyle.remove();

  // ============================================================
  // UI：注入样式 + 进度模态框
  // ============================================================

  const style = document.createElement('style');
  style.id = '_ggc-style';
  style.textContent = `
    #_ggc-modal {
      position: fixed; inset: 0;
      background: rgba(0,0,0,0.75); z-index: 999999;
      display: flex; align-items: center; justify-content: center;
      font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    }
    #_ggc-card {
      background: #1a1a18; color: #e8e6e0;
      border: 1px solid #9a7b3c; border-radius: 12px;
      padding: 24px 28px; min-width: 480px; max-width: 600px;
      box-shadow: 0 12px 40px rgba(0,0,0,0.6);
    }
    #_ggc-card h2 {
      margin: 0 0 6px 0; font-size: 18px; color: #9a7b3c;
      font-weight: 600;
    }
    #_ggc-card .subtitle { color: #888; font-size: 12px; margin-bottom: 18px; }
    #_ggc-stage { font-size: 14px; margin-bottom: 10px; min-height: 20px; }
    #_ggc-bar-bg {
      width: 100%; height: 8px; background: #2a2a26;
      border-radius: 4px; overflow: hidden;
    }
    #_ggc-bar-fg {
      height: 100%; background: linear-gradient(90deg, #9a7b3c, #c4a060);
      width: 0%; transition: width 0.2s;
    }
    #_ggc-detail {
      font-size: 12px; color: #999; margin-top: 8px;
      font-family: ui-monospace, "SF Mono", Menlo, monospace;
      max-height: 100px; overflow-y: auto;
    }
    #_ggc-detail .err { color: #d97777; }
    #_ggc-detail .ok  { color: #6fa86a; }
    #_ggc-actions { margin-top: 18px; display: flex; gap: 10px; }
    #_ggc-actions button, #_ggc-actions a {
      padding: 8px 16px; border-radius: 6px; cursor: pointer;
      border: 1px solid #9a7b3c; background: transparent; color: #9a7b3c;
      font-size: 13px; text-decoration: none; display: inline-block;
    }
    #_ggc-actions .primary {
      background: #9a7b3c; color: #1a1a18; border-color: #9a7b3c;
    }
    #_ggc-actions button:hover, #_ggc-actions a:hover { opacity: 0.85; }
    #_ggc-stats {
      margin-top: 14px; padding: 10px 12px; background: #242422;
      border-radius: 6px; font-size: 12px; color: #ccc;
    }
    #_ggc-stats span { color: #c4a060; font-weight: 600; }
  `;
  document.head.appendChild(style);

  const modal = document.createElement('div');
  modal.id = '_ggc-modal';
  modal.innerHTML = `
    <div id="_ggc-card">
      <h2>garmin-golf-cn · 数据导出</h2>
      <div class="subtitle">v${VERSION} · 数据仅在浏览器内处理，不上传任何服务器</div>
      <div id="_ggc-stage">准备中…</div>
      <div id="_ggc-bar-bg"><div id="_ggc-bar-fg"></div></div>
      <div id="_ggc-stats" style="display:none">
        轮次 <span id="_ggc-rounds">0</span> ·
        洞 <span id="_ggc-holes">0</span> ·
        击球 <span id="_ggc-shots">0</span> ·
        失败 <span id="_ggc-fails">0</span>
      </div>
      <div id="_ggc-detail"></div>
      <div id="_ggc-actions">
        <button id="_ggc-cancel">取消</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);

  const $stage   = document.getElementById('_ggc-stage');
  const $bar     = document.getElementById('_ggc-bar-fg');
  const $detail  = document.getElementById('_ggc-detail');
  const $actions = document.getElementById('_ggc-actions');
  const $stats   = document.getElementById('_ggc-stats');
  const $rounds  = document.getElementById('_ggc-rounds');
  const $holes   = document.getElementById('_ggc-holes');
  const $shots   = document.getElementById('_ggc-shots');
  const $fails   = document.getElementById('_ggc-fails');

  let cancelled = false;
  document.getElementById('_ggc-cancel').onclick = () => {
    cancelled = true;
    setStage('已取消');
  };

  function setStage(text) { $stage.textContent = text; }
  function setProgress(pct) { $bar.style.width = `${Math.min(100, pct)}%`; }
  function logDetail(text, kind = '') {
    const line = document.createElement('div');
    line.className = kind;
    line.textContent = text;
    $detail.appendChild(line);
    $detail.scrollTop = $detail.scrollHeight;
  }

  // ============================================================
  // 工具函数
  // ============================================================

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  /**
   * 半圆制（semicircles）转十进制经纬度。
   * Garmin 内部用 32 位整数表示坐标，一圈 = 2^32 个 semicircles。
   */
  function semicirclesToDecimal(semicircles) {
    if (semicircles == null) return null;
    return semicircles * (180 / Math.pow(2, 31));
  }

  function convertLoc(loc) {
    if (!loc || typeof loc !== 'object') return loc;
    return {
      lat: semicirclesToDecimal(loc.lat),
      lon: semicirclesToDecimal(loc.lon),
      _raw_semicircles: { lat: loc.lat, lon: loc.lon }, // 保留原始备查
    };
  }

  /**
   * 可中断 sleep（取消时立即返回）。
   */
  async function interruptibleSleep(ms) {
    const tick = 100;
    let elapsed = 0;
    while (elapsed < ms) {
      if (cancelled) return;
      await sleep(Math.min(tick, ms - elapsed));
      elapsed += tick;
    }
  }

  /**
   * 带重试 + 限流的 fetch JSON。
   * 用 fetch credentials:'include' 自动带上当前登录的 Garmin cookies。
   */
  let lastRequestAt = 0;
  async function fetchJSON(url, attempt = 1) {
    if (cancelled) throw new Error('已取消');
    const wait = RATE_LIMIT_MS - (Date.now() - lastRequestAt);
    if (wait > 0) await interruptibleSleep(wait);
    if (cancelled) throw new Error('已取消');
    lastRequestAt = Date.now();

    let resp;
    try {
      resp = await fetch(url, {
        credentials: 'include',
        headers: { 'Accept': 'application/json' },
      });
    } catch (err) {
      // 网络错误 / URL 不合法 / CORS 拒绝
      if (attempt < MAX_RETRIES && !cancelled) {
        const backoff = RETRY_BACKOFF_MS * Math.pow(2, attempt - 1);
        logDetail(
          `⟳ 重试 ${attempt}/${MAX_RETRIES - 1}：${url}（${err.message}）`,
          'err'
        );
        await interruptibleSleep(backoff);
        return fetchJSON(url, attempt + 1);
      }
      logDetail(`✗ fetch 失败：${url}`, 'err');
      logDetail(`  错误类型：${err.name} - ${err.message}`, 'err');
      throw err;
    }

    if (!resp.ok) {
      // HTTP 错误：保留完整诊断
      let bodyPreview = '';
      try {
        bodyPreview = (await resp.text()).slice(0, 200);
      } catch (_) { /* ignore */ }
      logDetail(
        `✗ HTTP ${resp.status} ${resp.statusText} on ${url}`,
        'err'
      );
      if (bodyPreview) {
        logDetail(`  响应前 200 字符：${bodyPreview}`, 'err');
      }
      if (attempt < MAX_RETRIES && resp.status >= 500 && !cancelled) {
        const backoff = RETRY_BACKOFF_MS * Math.pow(2, attempt - 1);
        await interruptibleSleep(backoff);
        return fetchJSON(url, attempt + 1);
      }
      throw new Error(`HTTP ${resp.status} on ${url}`);
    }

    // 检查响应是否真的是 JSON（防止登录过期返回 HTML）
    const ctype = resp.headers.get('content-type') || '';
    if (!ctype.includes('json')) {
      const bodyPreview = (await resp.text()).slice(0, 200);
      logDetail(`✗ 响应不是 JSON：${url}`, 'err');
      logDetail(`  Content-Type: ${ctype}`, 'err');
      logDetail(`  响应前 200 字符：${bodyPreview}`, 'err');
      throw new Error(`Non-JSON response (Content-Type: ${ctype})`);
    }

    return await resp.json();
  }

  // ============================================================
  // 主流程
  // ============================================================

  const startTime = Date.now();
  let failureCount = 0;

  // ------ 1. 球杆库 ------
  setStage('1/3 拉取球杆库…');
  let clubs = [];
  try {
    clubs = await fetchJSON(
      `${BASE}/club/player?per-page=1000&include-stats=true`
    );
    logDetail(`✓ 球杆库：${clubs.length} 支`, 'ok');
  } catch (err) {
    logDetail(`✗ 球杆库拉取失败：${err.message}（继续，球杆识别可能受影响）`, 'err');
    failureCount++;
  }

  // ------ 2. 轮次摘要 ------
  setStage('2/3 拉取轮次列表…');
  let summary;
  try {
    summary = await fetchJSON(
      `${BASE}/scorecard/summary?per-page=10000&user-locale=${USER_LOCALE}`
    );
  } catch (err) {
    alert(`致命错误：无法拉取轮次列表（${err.message}）。请检查登录状态后重试。`);
    setStage('失败：无法拉取轮次列表');
    return;
  }

  const scorecards = summary.scorecardSummaries || [];
  if (scorecards.length === 0) {
    setStage('未找到任何高尔夫轮次');
    logDetail('账号下没有任何 scorecard，已结束。');
    return;
  }
  logDetail(`✓ 找到 ${scorecards.length} 轮`, 'ok');
  $stats.style.display = 'block';
  $rounds.textContent = scorecards.length;

  // ------ 3. 每轮明细 + 每洞逐杆 ------
  const allRounds = [];
  let totalShots = 0;
  let totalHoles = 0;

  // 估算总请求数（用于进度计算）
  const estimatedHolePerRound = 18;
  const totalRequests = scorecards.length * (1 + estimatedHolePerRound);
  let doneRequests = 0;

  for (let i = 0; i < scorecards.length; i++) {
    if (cancelled) break;
    const card = scorecards[i];
    setStage(`3/3 第 ${i + 1}/${scorecards.length} 轮：${card.courseName || '未知球场'}`);

    // 每轮明细
    let detail;
    try {
      detail = await fetchJSON(
        `${BASE}/scorecard/detail?scorecard-ids=${card.id}` +
        `&include-longest-shot-distance=true`
      );
    } catch (err) {
      logDetail(`✗ 轮次 ${card.id} 明细拉取失败：${err.message}`, 'err');
      failureCount++;
      doneRequests += 1 + estimatedHolePerRound;
      setProgress((doneRequests / totalRequests) * 100);
      $fails.textContent = failureCount;
      continue;
    }
    doneRequests += 1;

    // 取出洞数（用于精确进度）
    let holes = [];
    try {
      const sc = (detail.scorecardDetails || [])
        .find((e) => e && e.scorecard !== undefined);
      holes = (sc && sc.scorecard && sc.scorecard.holes) || [];
    } catch (_) { /* ignore */ }

    // 每洞逐杆
    const shotsPerHole = [];
    for (const hole of holes) {
      if (cancelled) break;
      try {
        const shotData = await fetchJSON(
          `${BASE}/shot/scorecard/${card.id}/hole?hole-numbers=${hole.number}`
        );
        // 转换坐标
        if (shotData.holeShots && Array.isArray(shotData.holeShots)) {
          shotData.holeShots.forEach((hs) => {
            if (hs.shots && Array.isArray(hs.shots)) {
              hs.shots.forEach((shot) => {
                if (shot.startLoc) shot.startLoc = convertLoc(shot.startLoc);
                if (shot.endLoc) shot.endLoc = convertLoc(shot.endLoc);
                totalShots++;
              });
            }
          });
        }
        shotsPerHole.push({ holeNumber: hole.number, data: shotData });
        totalHoles++;
      } catch (err) {
        logDetail(
          `  ✗ 第 ${i + 1} 轮第 ${hole.number} 洞逐杆数据失败：${err.message}`,
          'err'
        );
        failureCount++;
      }
      doneRequests++;
      setProgress((doneRequests / totalRequests) * 100);
      $shots.textContent = totalShots;
      $holes.textContent = totalHoles;
      $fails.textContent = failureCount;
    }

    allRounds.push({
      summary: card,
      detail,
      shots: shotsPerHole,
    });
  }

  // ============================================================
  // 完成：组装最终输出 + 下载按钮
  // ============================================================

  if (cancelled) {
    setStage('已取消');
    $actions.innerHTML = '<button id="_ggc-close">关闭</button>';
    document.getElementById('_ggc-close').onclick = () => modal.remove();
    return;
  }

  setStage('✅ 全部完成');
  setProgress(100);

  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
  logDetail(`✓ 用时 ${elapsed} 秒`, 'ok');

  const exportData = {
    _meta: {
      tool: 'garmin-golf-cn',
      version: VERSION,
      exportedAt: new Date().toISOString(),
      stats: {
        rounds: allRounds.length,
        holes: totalHoles,
        shots: totalShots,
        failures: failureCount,
        elapsedSeconds: parseFloat(elapsed),
      },
      coordinateNote: 'startLoc/endLoc 已转换为十进制经纬度 (lat/lon)；原始 semicircles 值在 _raw_semicircles 字段保留',
    },
    clubs,
    rounds: allRounds,
  };

  const blob = new Blob([JSON.stringify(exportData, null, 2)], {
    type: 'application/json',
  });
  const blobUrl = URL.createObjectURL(blob);
  const filename = `garmin-golf-export-${
    new Date().toISOString().slice(0, 10)
  }.json`;

  $actions.innerHTML = `
    <a id="_ggc-download" class="primary" href="${blobUrl}" download="${filename}">⬇ 下载 ${filename}</a>
    <button id="_ggc-close">关闭</button>
  `;
  document.getElementById('_ggc-close').onclick = () => {
    URL.revokeObjectURL(blobUrl);
    modal.remove();
    style.remove();
  };

  // 控制台也输出一份，方便开发者
  console.log('[garmin-golf-cn] 导出完成', exportData._meta);
  window._ggcLastExport = exportData; // 调试用
})();
