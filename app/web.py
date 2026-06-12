from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from mimetypes import guess_type
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, unquote, urlparse

from .activity_bands import build_activity_bands
from .app_usage import build_usage_snapshot
from .collector import COLLECTOR_STATUS, COLLECTOR_STOP_EVENT, embedded_collect_loop
from .config import (
    DEFAULT_COLLECT_INTERVAL_SECONDS,
    EXE_ICON_DIR,
    PACKAGE_STATIC_DIR,
    SOURCE_STATIC_DIR,
)
from .icon_map import serialize_icon_map
from .storage import init_db
from .timeline import build_summary_text, build_timeline

HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Winflow 轨迹中心</title>
  <style>
    :root {
      --bg-dark: #09090b;
      --panel-bg: rgba(24, 24, 27, 0.55);
      --panel-border: rgba(255, 255, 255, 0.08);
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --accent: #38bdf8;
      --accent-glow: rgba(56, 189, 248, 0.4);
      --font: 'Inter', system-ui, -apple-system, sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: var(--font);
      background-color: var(--bg-dark);
      background-image:
        radial-gradient(circle at 15% 50%, rgba(56, 189, 248, 0.12), transparent 30%),
        radial-gradient(circle at 85% 30%, rgba(168, 85, 247, 0.12), transparent 30%),
        linear-gradient(rgba(255, 255, 255, 0.02) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255, 255, 255, 0.02) 1px, transparent 1px);
      background-size: 100% 100%, 100% 100%, 40px 40px, 40px 40px;
      background-attachment: fixed;
      color: var(--text-main);
      min-height: 100vh;
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
    }
    header {
      position: sticky;
      top: 0;
      z-index: 50;
      backdrop-filter: blur(24px) saturate(1.8);
      -webkit-backdrop-filter: blur(24px) saturate(1.8);
      background: rgba(9, 9, 11, 0.65);
      border-bottom: 1px solid var(--panel-border);
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
    }
    .wrap { max-width: 1280px; margin: 0 auto; padding: 20px 24px; }
    .header-content { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 20px; }
    .title-area h1 { margin: 0; font-size: 26px; font-weight: 800; letter-spacing: -0.02em; background: linear-gradient(135deg, #fff 30%, #94a3b8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .title-area .sub { color: var(--text-muted); font-size: 13px; margin-top: 6px; font-weight: 500; }

    .toolbar { display: flex; gap: 12px; align-items: center; }
    input, button, a.button {
      font-family: inherit; font-size: 13px; font-weight: 600;
      border: 1px solid var(--panel-border); border-radius: 12px;
      padding: 10px 16px; background: rgba(255,255,255,0.03);
      color: var(--text-main); text-decoration: none;
      transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
    }
    input[type="date"]::-webkit-calendar-picker-indicator { filter: invert(1); opacity: 0.6; cursor: pointer; }
    input:hover, input:focus { background: rgba(255,255,255,0.08); outline: none; border-color: rgba(255,255,255,0.2); }

    button, a.button { cursor: pointer; display: inline-flex; align-items: center; justify-content: center; }
    button:hover, a.button:hover { background: rgba(255,255,255,0.1); border-color: rgba(255,255,255,0.3); transform: translateY(-1px); }
    button:active { transform: translateY(0); }
    button.active {
      background: rgba(255, 255, 255, 0.95);
      color: #09090b;
      border-color: transparent;
      box-shadow: 0 4px 16px rgba(255,255,255,0.15);
    }
    button.active:hover { background: #fff; box-shadow: 0 6px 24px rgba(255,255,255,0.25); }
    button.primary { background: var(--accent); color: #09090b; border: none; }
    button.primary:hover { background: #7dd3fc; box-shadow: 0 0 24px var(--accent-glow); }

    main.wrap { display: grid; grid-template-columns: 340px 1fr; gap: 24px; padding-top: 32px; padding-bottom: 64px; }
    @media(max-width: 960px) { main.wrap { grid-template-columns: 1fr; } }

    .panel {
      background: var(--panel-bg);
      backdrop-filter: blur(20px) saturate(1.5); -webkit-backdrop-filter: blur(20px) saturate(1.5);
      border: 1px solid var(--panel-border);
      border-radius: 24px;
      padding: 28px;
      box-shadow: 0 24px 48px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.08);
    }
    .stat-title { font-size: 16px; font-weight: 700; margin: 0 0 20px; color: #fff; display: flex; align-items: center; gap: 10px; letter-spacing: -0.01em; }
    .stat-title::before { content: ''; display: block; width: 4px; height: 16px; background: var(--accent); border-radius: 4px; box-shadow: 0 0 12px var(--accent-glow); }

    .bar { margin-bottom: 18px; }
    .bar .label { display: flex; justify-content: space-between; font-size: 13px; color: var(--text-main); margin-bottom: 8px; }
    .bar .label span:first-child { font-weight: 500; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; max-width: 75%; }
    .bar .label span:last-child { color: var(--text-muted); font-variant-numeric: tabular-nums; font-weight: 500; }
    .meter { height: 6px; border-radius: 99px; background: rgba(0,0,0,0.6); overflow: hidden; box-shadow: inset 0 1px 2px rgba(0,0,0,0.4); }
    .meter span { display: block; height: 100%; border-radius: 99px; background: linear-gradient(90deg, #38bdf8, #818cf8); box-shadow: 0 0 12px rgba(56,189,248,0.5); transition: width 0.6s cubic-bezier(0.34, 1.56, 0.64, 1); }
    #browsers .meter span { background: linear-gradient(90deg, #10b981, #059669); box-shadow: 0 0 12px rgba(16,185,129,0.4); }

    /* Timeline Styles */
    .timeline-viz { margin-bottom: 32px; }
    .timeline-viz-header { margin-bottom: 24px; display: flex; justify-content: space-between; align-items: flex-start; }
    .timeline-viz-header .sub { color: var(--text-muted); font-size: 13px; font-weight: 400; }

    .timeline-chart {
      width: 100%; overflow-x: auto; overflow-y: hidden;
      padding-bottom: 12px;
      scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.15) transparent;
    }
    .timeline-chart::-webkit-scrollbar { height: 8px; }
    .timeline-chart::-webkit-scrollbar-track { background: transparent; }
    .timeline-chart::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.15); border-radius: 99px; }
    .timeline-chart::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.25); }

    .timeline-prototype {
      min-width: 1000px;
      background: rgba(0, 0, 0, 0.25);
      border-radius: 20px;
      border: 1px solid rgba(255,255,255,0.06);
      padding: 0 16px 20px;
      box-shadow: inset 0 4px 20px rgba(0,0,0,0.5);
    }
    .timeline-scale { position: relative; height: 48px; border-bottom: 1px solid rgba(255,255,255,0.08); margin-bottom: 12px; }
    .tick { position: absolute; top: 0; bottom: -1000px; border-left: 1px dashed rgba(255,255,255,0.06); pointer-events: none; z-index: 0; }
    .tick span {
      position: absolute; top: 14px; transform: translateX(-50%);
      color: var(--text-muted); font-size: 11px; font-weight: 600;
      background: rgba(24, 24, 27, 0.8); backdrop-filter: blur(4px);
      padding: 4px 10px; border-radius: 8px;
      border: 1px solid rgba(255,255,255,0.08);
      letter-spacing: 0.05em;
    }

    .timeline-stage { position: relative; width: 100%; isolation: isolate; }
    .timeline-track { position: absolute; left: 0; right: 0; height: 52px; border-bottom: 1px solid rgba(255,255,255,0.02); }

    .timeline-band {
      position: absolute; height: 40px; min-width: 44px;
      padding: 0; border: 0; background: transparent; cursor: pointer;
      border-radius: 99px;
      transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
      transform-origin: center left;
    }
    .timeline-band-line {
      position: absolute; inset: 0; border-radius: 99px;
      background: linear-gradient(90deg, var(--brand) 0%, color-mix(in srgb, var(--brand) 40%, transparent) 100%);
      opacity: 0.8;
      box-shadow: inset 0 1px 1px rgba(255,255,255,0.25), 0 4px 16px color-mix(in srgb, var(--brand) 25%, transparent);
      transition: all 0.3s ease;
    }

    .timeline-band-logo {
      position: absolute; left: 4px; top: 4px; width: 32px; height: 32px;
      border-radius: 50%; display: grid; place-items: center;
      background: rgba(0,0,0,0.6); color: var(--brand);
      font-size: 13px; font-weight: 800;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.15), 0 2px 8px rgba(0,0,0,0.5);
      z-index: 2; transition: all 0.3s ease; backdrop-filter: blur(4px);
    }

    .timeline-band-meta {
      position: absolute; left: 46px; right: 12px; top: 50%; transform: translateY(-50%);
      font-size: 12.5px; font-weight: 600; color: #fff;
      text-shadow: 0 1px 3px rgba(0,0,0,0.8);
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      z-index: 2; pointer-events: none; opacity: 0.9; transition: opacity 0.2s ease;
    }

    /* Hover effects */
    .timeline-band:hover { z-index: 10 !important; transform: scale(1.02) translateY(-2px); }
    .timeline-band:hover .timeline-band-line { opacity: 1; box-shadow: inset 0 1px 1px rgba(255,255,255,0.4), 0 8px 32px color-mix(in srgb, var(--brand) 50%, transparent); filter: brightness(1.2) saturate(1.2); }
    .timeline-band:hover .timeline-band-logo { background: var(--brand); color: #000; box-shadow: 0 0 20px var(--brand); }
    .timeline-band:hover .timeline-band-meta { opacity: 1; }

    /* Displaced & Muted states */
    .timeline-band.is-displaced { transform: translateY(var(--push-y, 8px)); opacity: 0.3; }
    .timeline-band.is-muted { opacity: 0.25; filter: grayscale(0.8); }

    /* Idle state */
    .timeline-band.is-idle .timeline-band-line {
      background: rgba(255,255,255,0.03); box-shadow: inset 0 0 0 1px rgba(255,255,255,0.05);
      backdrop-filter: blur(8px);
    }
    .timeline-band.is-idle .timeline-band-logo { background: rgba(0,0,0,0.4); color: var(--text-muted); box-shadow: inset 0 0 0 1px rgba(255,255,255,0.1); }
    .timeline-band.is-idle .timeline-band-meta { color: var(--text-muted); text-shadow: none; font-weight: 500; opacity: 0.6; }
    .timeline-band.is-idle:hover .timeline-band-line { background: rgba(255,255,255,0.08); }
    .timeline-band.is-idle:hover .timeline-band-logo { color: #fff; background: rgba(0,0,0,0.8); }

    /* List items */
    .item {
      display: grid; grid-template-columns: 85px minmax(0,1fr); gap: 16px;
      padding: 18px; border-radius: 16px;
      transition: all 0.2s ease; margin-bottom: 8px;
      border: 1px solid transparent;
    }
    .item:hover { background: rgba(255,255,255,0.03); border-color: rgba(255,255,255,0.05); transform: translateX(4px); }
    .time { color: var(--text-muted); font-variant-numeric: tabular-nums; font-size: 13px; font-weight: 500; padding-top: 2px; line-height: 1.6; }
    .kind {
      display: inline-block; font-size: 11px; font-weight: 700; border-radius: 6px;
      padding: 4px 10px; margin-right: 10px; color: #000; letter-spacing: 0.03em;
    }
    .kind.band { background: linear-gradient(135deg, #a855f7, #7e22ce); box-shadow: 0 2px 8px rgba(168,85,247,0.3); color: #fff; }
    .kind.idle { background: rgba(255,255,255,0.1); color: var(--text-muted); border: 1px solid rgba(255,255,255,0.1); box-shadow: none; }
    .title { font-weight: 600; font-size: 15px; display: flex; align-items: center; color: #fff; }
    .meta { color: var(--text-muted); font-size: 13.5px; margin-top: 6px; line-height: 1.5; }
    .samples { margin-top: 12px; display: flex; flex-wrap: wrap; gap: 8px; }
    .sample {
      font-size: 12px; color: #cbd5e1; padding: 4px 12px;
      background: rgba(0,0,0,0.4); border: 1px solid rgba(255,255,255,0.08);
      border-radius: 8px; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
      transition: background 0.2s;
    }
    .sample:hover { background: rgba(255,255,255,0.08); }
    .empty { color: var(--text-muted); padding: 60px 20px; text-align: center; border: 1px dashed rgba(255,255,255,0.15); border-radius: 20px; font-size: 14px; background: rgba(0,0,0,0.2); }
  </style>
</head>
<body>
  <header>
    <div class="wrap header-content">
      <div class="title-area">
        <h1>Winflow 控制台</h1>
        <div class="sub">本地行为模式分析系统 ✦ SQLite 数据驱动</div>
      </div>
      <div class="toolbar">
        <input id="day" type="date" />
        <button id="bandsBtn" class="active" onclick="setMode('bands')">时间轴视图</button>
        <button id="rawBtn" onclick="setMode('raw')">原始数据流</button>
        <button class="primary" onclick="loadData()">刷新视图</button>
        <a id="export" class="button" href="/api/export" target="_blank">导出报表</a>
      </div>
    </div>
  </header>

  <main class="wrap">
    <aside class="panel">
      <p class="stat-title">焦点应用排行</p>
      <div id="apps"></div>
      <p class="stat-title" style="margin-top: 32px;">活动类型</p>
      <div id="browsers"></div>
    </aside>

    <section class="panel timeline">
      <div id="timelineViz" class="timeline-viz">
        <div class="timeline-viz-header">
          <div>
            <p class="stat-title" style="margin-bottom: 4px;">活动聚类时间轴</p>
            <div class="sub">横向展示你的 Windows 前台应用活动带，仅聚焦最活跃的 3 小时窗口</div>
          </div>
        </div>
        <div id="timelineChart" class="timeline-chart"></div>
      </div>
      <p class="stat-title" id="timeline-title">活动明细记录</p>
      <div id="items"></div>
    </section>
  </main>
<script>
function pad(n){ return String(n).padStart(2,'0') }
function fmt(ts){ const d=new Date(ts*1000); return pad(d.getHours())+':'+pad(d.getMinutes()) }
function localDayValue(d){ return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate()) }
function esc(s){ return String(s ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])) }
let mode = 'bands';
let hoveredBandId = null;
const FOCUS_WINDOW_SECONDS = 3 * 3600;

function minutes(seconds){ return Math.round(Number(seconds||0)/60) }
function setMode(next){
  mode = next;
  document.getElementById('bandsBtn').className = next === 'bands' ? 'active' : '';
  document.getElementById('rawBtn').className = next === 'raw' ? 'active' : '';
  loadData();
}

function floorToHour(ts){ return Math.floor(Number(ts||0) / 3600) * 3600 }
function ceilToHour(ts){ return Math.ceil(Number(ts||0) / 3600) * 3600 }

function buildTicks(rangeStart, rangeEnd){
  const ticks = [];
  let cursor = ceilToHour(rangeStart);
  while(cursor <= rangeEnd){
    ticks.push(cursor);
    cursor += 3600;
  }
  return ticks;
}
function pct(ts, rangeStart, rangeEnd){
  if(rangeEnd <= rangeStart) return 0;
  return (Number(ts||0) - rangeStart) / (rangeEnd - rangeStart) * 100;
}
function overlapSeconds(startA, endA, startB, endB){
  return Math.max(0, Math.min(Number(endA), Number(endB)) - Math.max(Number(startA), Number(startB)));
}

function hashHue(text){
  let hash = 0;
  for(const ch of String(text || 'A')) hash = (hash + ch.charCodeAt(0) * 17) % 360;
  return hash;
}

function appNameFromBand(band){
  return String(band.title || band.subtitle || '未知应用');
}

function uiBandsFromPayload(data){
  return (data.bands || []).map((band, index) => ({
    ...band,
    uiId: `${band.id || band.event_key || 'band'}::${band.start_ts || 0}::${band.end_ts || 0}::${index}`,
    appName: appNameFromBand(band),
    startTs: Number(band.start_ts || 0),
    endTs: Number(band.end_ts || band.start_ts || 0),
    activeSeconds: Number(band.total_active_seconds || 0),
    openCount: Number(band.hit_count || 0),
    kind: band.kind || band.event_type || 'app'
  })).filter(band => band.startTs > 0 && band.endTs >= band.startTs);
}

function brandForBand(band){
  const app = String(band.appName || '').toLowerCase();
  if(app.includes('chrome')) return { color:'#22c55e', iconText:'C', displayName:'Chrome' };
  if(app.includes('edge')) return { color:'#0ea5e9', iconText:'E', displayName:'Edge' };
  if(app.includes('firefox')) return { color:'#f97316', iconText:'Fx', displayName:'Firefox' };
  if(app.includes('brave')) return { color:'#fb923c', iconText:'B', displayName:'Brave' };
  if(app.includes('code') || app.includes('cursor') || app.includes('vscode')) return { color:'#3b82f6', iconText:'</>', displayName:band.appName };
  if(app.includes('terminal') || app.includes('powershell') || app.includes('cmd')) return { color:'#a855f7', iconText:'>_', displayName:band.appName };
  if(app.includes('explorer')) return { color:'#f59e0b', iconText:'EX', displayName:'File Explorer' };
  if(app.includes('codex') || app.includes('openai')) return { color:'#10b981', iconText:'AI', displayName:band.appName };
  if(app.includes('wechat') || app.includes('weixin')) return { color:'#22c55e', iconText:'W', displayName:'WeChat' };
  if(app === 'qq' || app.includes('tencent qq')) return { color:'#0ea5e9', iconText:'Q', displayName:'QQ' };
  if(app === 'idle' || band.kind === 'idle') return { color:'#52525b', iconText:'ID', displayName:'空闲' };
  return { color:`hsl(${hashHue(band.appName)}, 75%, 60%)`, iconText:String(band.appName || '?').slice(0,1).toUpperCase(), displayName:band.appName || '未知应用' };
}

function buildTimelineRange(bands, payloadRange){
  const payloadStart = Number(payloadRange?.start_ts || 0);
  const payloadEnd = Number(payloadRange?.end_ts || 0);
  if(!bands.length){
    const now = Math.floor(Date.now() / 1000);
    const rangeStart = floorToHour(now);
    return { rangeStart, rangeEnd: rangeStart + FOCUS_WINDOW_SECONDS };
  }
  const minStart = Math.min(...bands.map(b => Number(b.startTs || 0)));
  const maxEnd = Math.max(...bands.map(b => Number(b.endTs || 0)));
  const firstHour = floorToHour(payloadStart || minStart);
  const boundedEnd = payloadEnd || maxEnd;
  const lastPossibleStart = Math.max(firstHour, ceilToHour(boundedEnd) - FOCUS_WINDOW_SECONDS);
  let bestStart = firstHour;
  let bestScore = -1;
  for(let candidate = firstHour; candidate <= lastPossibleStart; candidate += 1800){
    const candidateEnd = candidate + FOCUS_WINDOW_SECONDS;
    const score = bands.reduce((sum, band) => {
      const overlap = overlapSeconds(band.startTs, band.endTs, candidate, candidateEnd);
      const weight = band.kind === 'idle' ? 0.2 : 1;
      return sum + overlap * weight + (overlap > 0 ? Number(band.openCount || 0) * 30 : 0);
    }, 0);
    if(score > bestScore){ bestScore = score; bestStart = candidate; }
  }
  return { rangeStart: bestStart, rangeEnd: bestStart + FOCUS_WINDOW_SECONDS };
}

function layoutBandsIntoTracks(bands, rangeStart, rangeEnd){
  const visibleBands = bands
    .filter(band => overlapSeconds(band.startTs, band.endTs, rangeStart, rangeEnd) > 0)
    .map(band => ({
      ...band,
      visualStartTs: Math.max(Number(band.startTs), rangeStart),
      visualEndTs: Math.min(Number(band.endTs), rangeEnd)
    }));
  const sorted = visibleBands.sort((a,b) => Number(a.visualStartTs) - Number(b.visualStartTs) || Number(a.visualEndTs) - Number(b.visualEndTs));
  const trackEnds = [];
  return sorted.map(band => {
    let trackIndex = trackEnds.findIndex(end => end <= Number(band.visualStartTs));
    if(trackIndex < 0){
      trackIndex = trackEnds.length;
      trackEnds.push(Number(band.visualEndTs));
    } else {
      trackEnds[trackIndex] = Number(band.visualEndTs);
    }
    const leftPercent = Math.max(0, Math.min(100, pct(band.visualStartTs, rangeStart, rangeEnd)));
    const rawWidth = pct(band.visualEndTs, rangeStart, rangeEnd) - pct(band.visualStartTs, rangeStart, rangeEnd);
    const widthPercent = Math.min(100 - leftPercent, Math.max(1.5, rawWidth));
    return { ...band, trackIndex, leftPercent, widthPercent };
  });
}

function durationLabel(seconds){
  const mins = Math.max(1, Math.round(Number(seconds || 0) / 60));
  if(mins < 60) return mins + ' min';
  const hours = Math.floor(mins / 60);
  const rest = mins % 60;
  return rest ? `${hours}h ${rest}m` : `${hours}h`;
}

function bandTooltip(band){
  return [
    band.appName || '活动',
    fmt(band.startTs) + ' - ' + fmt(band.endTs),
    '活跃时间：' + durationLabel(band.activeSeconds),
    '窗口命中：' + Number(band.openCount || 0) + ' 次'
  ].filter(Boolean).join('\n');
}

function bandsOverlapOrNearlyTouch(a, b, toleranceSeconds=10*60){
  let gap = 0;
  if(Number(a.endTs) < Number(b.startTs)) gap = Number(b.startTs) - Number(a.endTs);
  else if(Number(b.endTs) < Number(a.startTs)) gap = Number(a.startTs) - Number(b.endTs);
  return gap <= toleranceSeconds;
}

function setHoveredBand(id){
  hoveredBandId = id;
  if(window.latestBandsPayload) renderTimelineViz(window.latestBandsPayload);
}

function renderTimelineViz(data){
  window.latestBandsPayload = data || window.latestBandsPayload || {};
  const viz = document.getElementById('timelineViz');
  const chart = document.getElementById('timelineChart');
  viz.style.display = mode === 'bands' ? '' : 'none';
  if(mode !== 'bands') return;

  const bands = uiBandsFromPayload(window.latestBandsPayload);
  if(!bands.length){
    chart.innerHTML = '<div class="empty">暂无活动时间轴数据。请先运行采集器一段时间。</div>';
    return;
  }

  const { rangeStart, rangeEnd } = buildTimelineRange(bands, window.latestBandsPayload.range);
  const ticks = buildTicks(rangeStart, rangeEnd);
  const tickHtml = ticks.map(t => `<div class="tick" style="left:${pct(t, rangeStart, rangeEnd).toFixed(3)}%"><span>${fmt(t)}</span></div>`).join('');

  const positioned = layoutBandsIntoTracks(bands, rangeStart, rangeEnd);
  const trackCount = Math.max(1, ...positioned.map(b => b.trackIndex + 1));
  const trackHeight = 52;
  const stageHeight = trackCount * trackHeight + 12;

  const hovered = positioned.find(b => b.uiId === hoveredBandId);
  const trackHtml = Array.from({length: trackCount}, (_, index) => `<div class="timeline-track" style="top:${(index * trackHeight).toFixed(0)}px"></div>`).join('');

  const bandHtml = positioned.map(band => {
    const brand = brandForBand(band);
    const isHovered = hoveredBandId === band.uiId;
    const isDisplaced = !!hovered && hovered.uiId !== band.uiId && Math.abs(hovered.trackIndex - band.trackIndex) <= 1 && bandsOverlapOrNearlyTouch(hovered, band);
    const isMuted = !!hovered && hovered.uiId !== band.uiId && !isDisplaced;
    const isIdle = band.kind === 'idle';
    const pushY = isDisplaced ? (band.trackIndex < hovered.trackIndex ? -10 : 10) : 0;

    const classes = ['timeline-band', isIdle ? 'is-idle' : '', isDisplaced ? 'is-displaced' : '', isMuted ? 'is-muted' : ''].filter(Boolean).join(' ');
    const style = [
      `left:${band.leftPercent.toFixed(3)}%`,
      `width:${band.widthPercent.toFixed(3)}%`,
      `top:${(band.trackIndex * trackHeight + 6).toFixed(0)}px`,
      `--brand:${brand.color}`,
      `--push-y:${pushY}px`
    ].join(';');
    const meta = `${brand.displayName} · ${durationLabel(band.activeSeconds)} · ${Number(band.openCount || 0)} 次`;
    const safeId = esc(band.uiId);

    return `<button type="button" class="${classes}" style="${style}" title="${esc(bandTooltip(band))}" onmouseenter="setHoveredBand('${safeId}')" onmouseleave="setHoveredBand(null)" onfocus="setHoveredBand('${safeId}')" onblur="setHoveredBand(null)">
      <span class="timeline-band-line"></span>
      <span class="timeline-band-logo">${esc(brand.iconText)}</span>
      <span class="timeline-band-meta">${esc(meta)}</span>
    </button>`;
  }).join('');

  chart.innerHTML = `<div class="timeline-prototype"><div class="timeline-scale">${tickHtml}</div><div class="timeline-stage" style="height:${stageHeight}px;">${trackHtml}${bandHtml}</div></div>`;
}

function renderBars(el, rows, nameKey, valueKey, suffix){
  const max = Math.max(1, ...rows.map(r=>Number(r[valueKey]||0)));
  el.innerHTML = rows.length ? rows.map(r=>`<div class="bar"><div class="label"><span>${esc(r[nameKey])}</span><span>${suffix(r[valueKey])}</span></div><div class="meter"><span style="width:${Math.max(4, Number(r[valueKey]||0)/max*100)}%"></span></div></div>`).join('') : '<div class="empty">暂无数据记录</div>';
}

async function loadData(){
  const day = document.getElementById('day').value;
  const qs = day ? '?day='+encodeURIComponent(day) : '';
  document.getElementById('export').href = '/api/export'+qs;
  try {
    const res = await fetch((mode === 'bands' ? '/api/bands' : '/api/timeline')+qs);
    const data = await res.json();
    document.getElementById('timeline-title').textContent = data.day + (mode === 'bands' ? ' · 活动聚类分析' : ' · 原始数据流');

    if(mode === 'bands'){
      renderTimelineViz(data);
      const topBands = (data.stats && data.stats.top_bands || []).map(b => ({ name: b.title + (b.subtitle ? ' · ' + b.subtitle : ''), seconds: b.total_active_seconds }));
      const byType = (data.stats && data.stats.by_type || []).map(r => ({ name: '应用使用', count: r.band_count }));
      renderBars(document.getElementById('apps'), topBands, 'name', 'seconds', v => minutes(v)+' min');
      renderBars(document.getElementById('browsers'), byType, 'name', 'count', v => Number(v||0)+' 项');
      renderBands(data);
      return;
    }

    renderTimelineViz(data);
    renderBars(document.getElementById('apps'), data.stats.apps || [], 'process_name', 'seconds', v => minutes(v)+' min');
    renderBars(document.getElementById('browsers'), [{ name:'应用事件', count:(data.items || []).length }], 'name', 'count', v => Number(v||0)+' 条');
    renderRawItems(data);
  } catch (err) {
    console.error("加载数据失败", err);
  }
}

function renderRawItems(data){
  const items = document.getElementById('items');
  if(!data.items.length){ items.innerHTML = '<div class="empty">该日期暂无记录数据，请确保采集脚本正在运行。</div>'; return; }
  items.innerHTML = data.items.map(it => `<div class="item"><div class="time">${fmt(it.start_ts)}${it.end_ts!==it.start_ts ? '<br>↓ '+fmt(it.end_ts):''}</div><div><div class="title"><span class="kind app">应用</span>${esc(it.title)}</div><div class="meta">${esc(it.subtitle)} ${it.detail ? ' · '+esc(it.detail):''}</div></div></div>`).join('');
}

function renderBands(data){
  const items = document.getElementById('items');
  if(!data.bands.length){ items.innerHTML = '<div class="empty">暂无聚合的活动记录。系统会自动过滤掉极其短暂的碎片化操作。</div>'; return; }
  items.innerHTML = data.bands.map((b, index) => {
    const samples = [...(b.sample_titles || []), ...(b.sample_details || [])].slice(0, 8);
    const sampleHtml = samples.length ? `<div class="samples">${samples.map(s => `<span class="sample">${esc(s)}</span>`).join('')}</div>` : '';
    return `<div class="item" id="band-${b._index ?? index}">
      <div class="time">${fmt(b.start_ts)}<br>↓ ${fmt(b.end_ts)}</div>
      <div>
        <div class="title"><span class="kind band">活动</span>${esc(b.title)}</div>
        <div class="meta">${esc(b.subtitle)} · 专注约 ${minutes(b.total_active_seconds)} 分钟 · 窗口命中 ${Number(b.hit_count||0)} 次${b.detail ? ' · '+esc(b.detail):''}</div>
        ${sampleHtml}
      </div>
    </div>`;
  }).join('');
}

(function(){ const d=new Date(); document.getElementById('day').value = localDayValue(d); loadData(); setInterval(loadData, 30000); })();
</script>
</body>
</html>"""


USAGE_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Winflow 软件使用统计预览</title>
  <style>
    :root {
      color-scheme: dark;
      --bg:#080a0f;
      --panel:rgba(18,24,38,.78);
      --panel-2:rgba(12,17,28,.72);
      --line:rgba(148,163,184,.16);
      --text:#f8fafc;
      --muted:#94a3b8;
      --accent:#38bdf8;
      --green:#22c55e;
      --purple:#a855f7;
      --orange:#f59e0b;
    }
    * { box-sizing:border-box; }
    body {
      margin:0;
      min-height:100vh;
      font-family:Inter, "Segoe UI", ui-sans-serif, system-ui, sans-serif;
      color:var(--text);
      background:
        radial-gradient(circle at 16% 20%, rgba(56,189,248,.16), transparent 30%),
        radial-gradient(circle at 86% 10%, rgba(168,85,247,.14), transparent 28%),
        linear-gradient(180deg,#090b12,#06070b 58%,#050609);
    }
    .wrap { max-width:1180px; margin:0 auto; padding:28px 24px 56px; }
    header { display:flex; justify-content:space-between; align-items:flex-start; gap:20px; margin-bottom:24px; }
    h1 { margin:0; font-size:30px; letter-spacing:-.04em; }
    .sub { color:var(--muted); margin-top:7px; font-size:14px; }
    .toolbar { display:flex; gap:10px; align-items:center; flex-wrap:wrap; justify-content:flex-end; }
    input, button, a.button {
      border:1px solid var(--line);
      border-radius:12px;
      padding:10px 13px;
      background:rgba(255,255,255,.04);
      color:var(--text);
      text-decoration:none;
      font:inherit;
      font-size:13px;
      font-weight:650;
    }
    input[type="date"]::-webkit-calendar-picker-indicator { filter:invert(1); opacity:.72; }
    button, a.button { cursor:pointer; }
    button.primary { background:var(--accent); color:#061018; border-color:transparent; }
    button:hover, a.button:hover { border-color:rgba(255,255,255,.32); background:rgba(255,255,255,.08); }
    button.primary:hover { background:#7dd3fc; }
    .auto-refresh {
      display:inline-flex; align-items:center; gap:7px;
      color:var(--muted); font-size:13px; user-select:none;
    }
    .auto-refresh input { width:auto; accent-color:var(--accent); }
    .status-line { margin-top:10px; color:var(--muted); font-size:13px; min-height:18px; }
    .status-line strong { color:#e5e7eb; }
    .status-line code {
      color:#dbeafe; background:rgba(148,163,184,.12);
      padding:2px 5px; border-radius:6px;
    }
    .grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; margin-bottom:18px; }
    .card {
      background:var(--panel);
      border:1px solid var(--line);
      border-radius:22px;
      box-shadow:0 22px 44px rgba(0,0,0,.28), inset 0 1px 0 rgba(255,255,255,.06);
      backdrop-filter:blur(18px);
    }
    .metric { padding:20px; }
    .metric .label { color:var(--muted); font-size:13px; }
    .metric .value { margin-top:8px; font-size:28px; font-weight:800; letter-spacing:-.035em; }
    .main-card { padding:20px; }
    .section-title { display:flex; justify-content:space-between; gap:16px; align-items:baseline; margin-bottom:16px; }
    .section-title h2 { margin:0; font-size:18px; }
    .section-title span { color:var(--muted); font-size:13px; }
    .app-list { display:grid; gap:12px; }
    .app-row {
      padding:15px;
      border:1px solid rgba(148,163,184,.13);
      border-radius:18px;
      background:linear-gradient(180deg,rgba(255,255,255,.045),rgba(255,255,255,.02));
    }
    .app-head { display:grid; grid-template-columns:40px minmax(0,1fr) auto; gap:12px; align-items:center; }
    .icon {
      width:40px; height:40px; border-radius:10px;
      display:grid; place-items:center;
      color:var(--icon-text,#e5e7eb); font-weight:750; font-size:13px;
      background:#111827;
      border:1px solid rgba(148,163,184,.18);
      overflow:hidden;
    }
    .icon img { width:30px; height:30px; display:block; object-fit:contain; }
    .name { font-weight:800; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .process { color:var(--muted); font-size:12px; margin-top:2px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .duration { font-variant-numeric:tabular-nums; font-weight:800; }
    .bar { height:8px; border-radius:999px; background:rgba(0,0,0,.42); overflow:hidden; margin-top:12px; }
    .bar span { display:block; height:100%; width:0; border-radius:999px; background:linear-gradient(90deg,var(--brand,#38bdf8),color-mix(in srgb,var(--brand,#38bdf8) 35%,white)); }
    .empty { color:var(--muted); text-align:center; border:1px dashed var(--line); border-radius:18px; padding:44px 20px; }
    pre {
      margin:18px 0 0;
      padding:16px;
      max-height:360px;
      overflow:auto;
      border-radius:18px;
      background:rgba(0,0,0,.42);
      border:1px solid var(--line);
      color:#cbd5e1;
      font-size:12px;
      line-height:1.55;
    }
    @media(max-width:860px) {
      header { flex-direction:column; }
      .toolbar { justify-content:flex-start; }
      .grid { grid-template-columns:1fr; }
      .app-head { grid-template-columns:36px minmax(0,1fr); }
      .duration { grid-column:2; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div>
        <h1>软件使用统计预览</h1>
        <div class="sub">本页只读取本地处理结果：不上传服务器，不展示窗口标题、exe_path、完整 URL 或浏览器标签页明细。</div>
        <div id="collectorStatus" class="status-line">正在读取采集状态…</div>
      </div>
      <div class="toolbar">
        <input id="day" type="date" />
        <button class="primary" onclick="loadUsage()">刷新</button>
        <label class="auto-refresh"><input id="autoRefresh" type="checkbox" checked /> 自动刷新</label>
        <a class="button" href="/">返回控制台</a>
      </div>
    </header>

    <section class="grid">
      <div class="card metric"><div class="label">活跃软件总时长</div><div id="activeSeconds" class="value">--</div></div>
      <div class="card metric"><div class="label">软件数量</div><div id="appCount" class="value">--</div></div>
      <div class="card metric"><div class="label">设备</div><div id="deviceId" class="value" style="font-size:20px">--</div></div>
    </section>

    <section class="card main-card">
      <div class="section-title">
        <h2 id="title">应用排行</h2>
        <span id="meta">等待加载</span>
      </div>
      <div id="apps" class="app-list"></div>
      <pre id="json"></pre>
    </section>
  </div>
<script>
function pad(n){ return String(n).padStart(2,'0') }
function localDayValue(d){ return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate()) }
function esc(s){ return String(s ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])) }
function duration(seconds){
  const s = Math.max(0, Number(seconds||0));
  const h = Math.floor(s / 3600);
  const m = Math.round((s % 3600) / 60);
  if(h <= 0) return `${m}m`;
  return m ? `${h}h ${m}m` : `${h}h`;
}
function fallbackVisual(label){
  const s = String(label || '').trim();
  const palette = ['#64748b','#71717a','#78716c','#0f766e','#7c3aed','#b45309','#be123c','#0369a1'];
  let total = 0;
  for(const ch of s) total += ch.charCodeAt(0);
  const icon = s ? (s.charCodeAt(0) < 128 ? s.slice(0,2).toUpperCase() : s.slice(0,1)) : '?';
  return { color: palette[total % palette.length], text_color: '#f8fafc', icon };
}
function visualFor(row, label){
  const fallback = fallbackVisual(label);
  return {
    color: row?.color || fallback.color,
    textColor: row?.text_color || '#f8fafc',
    icon: row?.icon || fallback.icon,
  };
}
function iconMarkup(visual, className, alt){
  const icon = String(visual.icon || '?');
  const style = `--brand:${visual.color};--icon-text:${visual.textColor};--site-brand:${visual.color};--site-icon-text:${visual.textColor}`;
  if(icon.startsWith('/static/') || icon.startsWith('data:') || new RegExp('^https?://').test(icon)){
    return `<div class="${className}" style="${style}"><img src="${esc(icon)}" alt="${esc(alt || '')}" loading="lazy" /></div>`;
  }
  return `<div class="${className}" style="${style}">${esc(icon)}</div>`;
}
async function loadUsage(){
  const day = document.getElementById('day').value;
  const qs = day ? '?day=' + encodeURIComponent(day) : '';
  const res = await fetch('/api/apps/usage' + qs + (qs ? '&' : '?') + '_=' + Date.now(), {cache:'no-store'});
  const data = await res.json();
  renderUsage(data);
  await loadCollectorStatus();
}
async function loadDefaultDay(){
  try {
    const res = await fetch('/api/apps/usage?_=' + Date.now(), {cache:'no-store'});
    const data = await res.json();
    if(data.day){
      document.getElementById('day').value = data.day;
      renderUsage(data);
      await loadCollectorStatus();
      return;
    }
  } catch (err) {
    console.warn(err);
  }
  document.getElementById('day').value = localDayValue(new Date());
  loadUsage();
}
function renderUsage(data){
  const apps = data.apps || [];
  const maxSeconds = Math.max(1, ...apps.map(app => Number(app.seconds || 0)));
  document.getElementById('activeSeconds').textContent = duration(data.summary?.active_seconds || 0);
  document.getElementById('appCount').textContent = String(data.summary?.app_count || apps.length || 0);
  document.getElementById('deviceId').textContent = data.device_id || '--';
  document.getElementById('title').textContent = `${data.day || ''} 应用排行`;
  document.getElementById('meta').textContent = `生成于 ${new Date((data.generated_at || 0) * 1000).toLocaleString()} · 空闲阈值 ${Math.round((data.idle_threshold_seconds || 0) / 60)}m`;
  if(!apps.length){
    document.getElementById('apps').innerHTML = '<div class="empty">暂无本地统计数据。请先运行采集命令一段时间。</div>';
  } else {
    document.getElementById('apps').innerHTML = apps.map(app => {
      const visual = visualFor(app, app.app_name);
      const color = visual.color;
      const pct = Math.max(2, Number(app.seconds || 0) / maxSeconds * 100);
      return `<article class="app-row" style="--brand:${color};--icon-text:${visual.textColor}">
        <div class="app-head">
          ${iconMarkup(visual, 'icon', app.app_name)}
          <div><div class="name">${esc(app.app_name)}</div><div class="process">${esc((app.process_names || []).join(', '))}</div></div>
          <div class="duration">${duration(app.seconds)}</div>
        </div>
        <div class="bar"><span style="width:${pct.toFixed(2)}%"></span></div>
      </article>`;
    }).join('');
  }
  document.getElementById('json').textContent = JSON.stringify(data, null, 2);
}
async function loadCollectorStatus(){
  try {
    const res = await fetch('/api/collector/status?_=' + Date.now(), {cache:'no-store'});
    const data = await res.json();
    const status = document.getElementById('collectorStatus');
    const lastTick = data.last_tick_ts ? new Date(data.last_tick_ts * 1000).toLocaleTimeString() : '暂无';
    const lastWindow = data.last_window ? ` · 最近窗口 ${esc(data.last_window)}` : '';
    const error = data.last_error ? ` · 错误 ${esc(data.last_error)}` : '';
    status.innerHTML = data.running
      ? `采集器：<strong>运行中</strong> · 最近采集 ${lastTick}${lastWindow}${error}`
      : `采集器：<strong>未运行</strong> · 页面只会显示已有数据库记录。请用 <code>python -m app.main serve --with-collector</code> 或另开终端运行 <code>python -m app.main collect</code>`;
  } catch (err) {
    document.getElementById('collectorStatus').textContent = '采集状态读取失败';
  }
}
(function(){
  loadDefaultDay();
  setInterval(() => {
    const auto = document.getElementById('autoRefresh');
    if(auto && auto.checked) loadUsage();
  }, 5000);
})();
</script>
</body>
</html>"""


def _safe_join(root: Path, relative: str) -> Path | None:
    parts = PurePosixPath(unquote(relative)).parts
    if not parts or any(part in {"", ".", ".."} or "\\" in part for part in parts):
        return None
    try:
        root_resolved = root.resolve()
        target = root_resolved.joinpath(*parts).resolve()
    except OSError:
        return None
    if root_resolved not in [target, *target.parents]:
        return None
    return target


def static_file_for_request(request_path: str) -> Path | None:
    """把 `/static/...` URL 映射到安全的本地静态文件。

    内置 SVG 图标优先来自包内 `app/static`，本机 exe 图标来自可写缓存目录。
    源码树运行时仍兼容根目录 `static/`。
    """
    if not request_path.startswith("/static/"):
        return None
    relative = request_path.removeprefix("/static/")
    if relative.startswith("exe-icons/"):
        target = _safe_join(EXE_ICON_DIR, relative.removeprefix("exe-icons/"))
        return target if target and target.is_file() else None

    for root in (PACKAGE_STATIC_DIR, SOURCE_STATIC_DIR):
        target = _safe_join(root, relative)
        if target and target.is_file():
            return target
    return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print(f"[server] {self.address_string()} - {fmt % args}")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, request_path: str) -> None:
        target = static_file_for_request(request_path)
        if target is None:
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        content_type = guess_type(str(target))[0] or "application/octet-stream"
        self._send(200, target.read_bytes(), content_type)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        day = qs.get("day", [None])[0]
        if parsed.path.startswith("/static/"):
            self._send_static(parsed.path)
            return
        if parsed.path == "/":
            self._send(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if parsed.path == "/usage":
            self._send(200, USAGE_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if parsed.path == "/api/timeline":
            body = json.dumps(build_timeline(day), ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return
        if parsed.path == "/api/bands":
            body = json.dumps(build_activity_bands(day), ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return
        if parsed.path == "/api/icon-map":
            body = json.dumps(serialize_icon_map(), ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return
        if parsed.path == "/api/collector/status":
            body = json.dumps(COLLECTOR_STATUS, ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return
        if parsed.path == "/api/apps/usage":
            idle_threshold = int(qs.get("idle_threshold_seconds", [300])[0] or 300)
            body = json.dumps(
                build_usage_snapshot(
                    day,
                    idle_threshold_seconds=max(0, idle_threshold),
                ),
                ensure_ascii=False,
            ).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return
        if parsed.path == "/api/export":
            body = build_summary_text(day).encode("utf-8")
            self._send(200, body, "text/markdown; charset=utf-8")
            return
        self._send(404, b"Not found", "text/plain; charset=utf-8")


def serve(
    host: str,
    port: int,
    open_browser: bool,
    *,
    with_collector: bool = False,
    collect_interval: int = DEFAULT_COLLECT_INTERVAL_SECONDS,
) -> None:
    init_db()
    COLLECTOR_STOP_EVENT.clear()
    collector_thread: threading.Thread | None = None
    if with_collector:
        collector_thread = threading.Thread(
            target=embedded_collect_loop,
            args=(max(1, collect_interval),),
            name="winflow-embedded-collector",
            daemon=True,
        )
        collector_thread.start()
    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"
    mode = "Web + 内置采集" if with_collector else "仅 Web"
    print(f"Winflow Web UI: {url}（{mode}）")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
    finally:
        COLLECTOR_STOP_EVENT.set()
        server.server_close()
