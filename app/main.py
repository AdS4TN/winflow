from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .activity_bands import build_activity_bands
from .browser_history import discover_browser_profiles, read_recent_browser_history
from .config import DEFAULT_BROWSER_SYNC_INTERVAL_SECONDS, DEFAULT_COLLECT_INTERVAL_SECONDS, DB_PATH
from .storage import init_db, insert_browser_visits, record_foreground_window
from .timeline import build_summary_text, build_timeline
from .windows_activity import get_foreground_window

HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Winflow 本地访问轨迹</title>
  <style>
    :root { color-scheme: light; --bg:#f7f1e8; --card:#fffaf1; --ink:#241c16; --muted:#796c5f; --line:#e3d6c5; --accent:#9b5c25; --app:#b86524; --app-dark:#7f431a; --web:#277ea0; --web-dark:#1f5874; }
    * { box-sizing: border-box; }
    body { margin:0; font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--ink); }
    header { position: sticky; top:0; z-index:2; backdrop-filter: blur(16px); background: rgba(247,241,232,.82); border-bottom:1px solid var(--line); }
    .wrap { max-width: 1120px; margin:0 auto; padding: 18px 22px; }
    h1 { margin:0; font-size: 26px; letter-spacing:-.03em; }
    .sub { color:var(--muted); margin-top:6px; font-size:14px; }
    .toolbar { display:flex; gap:10px; align-items:center; margin-top:14px; flex-wrap:wrap; }
    input, button, a.button, select { border:1px solid var(--line); border-radius:12px; padding:10px 12px; background:#fff; color:var(--ink); text-decoration:none; }
    button, a.button { cursor:pointer; background:#2b2119; color:#fff; border-color:#2b2119; }
    button.secondary { background:#fff; color:var(--ink); border-color:var(--line); }
    button.active { background:#9b5c25; border-color:#9b5c25; color:#fff; box-shadow:0 4px 12px rgba(155,92,37,.22); }
    main.wrap { display:grid; grid-template-columns: 300px 1fr; gap:18px; }
    .panel { background: rgba(255,250,241,.86); border:1px solid var(--line); border-radius:20px; padding:16px; box-shadow: 0 10px 30px rgba(91,63,35,.08); }
    .stat-title { font-weight:700; margin:0 0 10px; }
    .bar { margin:10px 0; }
    .bar .label { display:flex; justify-content:space-between; gap:12px; font-size:13px; color:var(--muted); min-width:0; }
    .bar .label span:first-child { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .bar .label span:last-child { flex:none; }
    .meter { height:8px; border-radius:99px; background:#eadcca; overflow:hidden; margin-top:5px; }
    .meter span { display:block; height:100%; background:linear-gradient(90deg,#c47a31,#7d4a21); }
    .timeline { position:relative; }
    .item { display:grid; grid-template-columns: 94px minmax(0,1fr); gap:12px; padding:12px 0; border-bottom:1px solid var(--line); scroll-margin:120px 0 24px; }
    .item:target, .item.focused { border-radius:14px; background:rgba(196,122,49,.10); box-shadow:0 0 0 1px rgba(196,122,49,.20) inset; }
    .time { color:var(--accent); font-variant-numeric: tabular-nums; font-size:13px; padding-top:2px; }
    .kind { display:inline-block; font-size:11px; border-radius:999px; padding:3px 8px; margin-right:8px; color:#fff; background:#6b4c32; }
    .kind.web { background:#315f7d; }
    .kind.band { background:#9b5c25; }
    .title { font-weight:650; line-height:1.35; overflow-wrap:anywhere; }
    .meta { color:var(--muted); font-size:13px; margin-top:4px; overflow-wrap:anywhere; }
    .samples { margin-top:8px; color:var(--muted); font-size:12px; }
    .sample { display:inline-block; max-width:100%; margin:3px 5px 0 0; padding:3px 7px; border:1px solid var(--line); border-radius:999px; background:#fffdf8; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; vertical-align:bottom; }
    .empty { color:var(--muted); padding:30px; text-align:center; }
    .timeline-viz { margin-bottom:18px; padding:14px 0 16px; border-block:1px solid rgba(227,214,197,.9); background:linear-gradient(180deg,rgba(255,253,248,.62),rgba(255,250,241,.18)); }
    .timeline-viz-header { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; margin:0 0 12px; padding:0 2px; }
    .timeline-viz-header .stat-title { margin-bottom:4px; }
    .view-toggle { display:flex; gap:4px; flex:none; padding:3px; border:1px solid var(--line); border-radius:999px; background:#fffdf8; }
    .view-toggle button { padding:7px 12px; border-radius:999px; font-size:12px; line-height:1; border-color:transparent; }
    .view-toggle button.secondary { background:transparent; color:var(--muted); }
    .view-toggle button.active { background:#2b2119; border-color:#2b2119; color:#fff; box-shadow:0 3px 10px rgba(36,28,22,.18); }
    .timeline-chart { max-width:100%; max-height:72vh; overflow:auto; padding:8px 2px 12px; scrollbar-color:#cbb8a3 #f2e7d8; scrollbar-width:thin; }
    .timeline-chart::-webkit-scrollbar { width:10px; height:10px; }
    .timeline-chart::-webkit-scrollbar-track { background:#f2e7d8; border-radius:999px; }
    .timeline-chart::-webkit-scrollbar-thumb { background:#cbb8a3; border-radius:999px; border:2px solid #f2e7d8; }
    .vertical-timeline { position:relative; min-width:620px; padding-left:76px; padding-right:2px; }
    .timeline-rail { position:absolute; left:62px; top:0; bottom:0; border-left:2px solid rgba(36,28,22,.45); }
    .time-tick { position:absolute; left:0; right:0; border-top:1px dashed rgba(121,108,95,.22); pointer-events:none; }
    .time-tick-label { position:absolute; left:-76px; top:-9px; width:54px; text-align:right; color:#5d5146; font-size:11px; font-weight:650; font-variant-numeric:tabular-nums; }
    .time-tick-dot { position:absolute; left:58px; top:-4px; width:9px; height:9px; border-radius:999px; background:#241c16; box-shadow:0 0 0 3px rgba(255,250,241,.9); }
    .timeline-card { appearance:none; position:absolute; left:86px; right:0; display:flex; align-items:flex-start; gap:10px; min-height:46px; padding:10px 12px; border-radius:10px; text-align:left; cursor:pointer; overflow:hidden; border:1px solid rgba(255,255,255,.62); box-shadow:0 8px 20px rgba(36,28,22,.10), inset 0 1px 0 rgba(255,255,255,.35); transition:transform .14s ease, box-shadow .14s ease, filter .14s ease; }
    .timeline-card:hover, .timeline-card:focus { z-index:6; transform:translateY(-1px); filter:saturate(1.06); box-shadow:0 14px 28px rgba(36,28,22,.18), 0 0 0 3px rgba(155,92,37,.12); outline:none; }
    .timeline-card.app { background:linear-gradient(135deg,rgba(255,246,221,.96),rgba(255,226,171,.88)); }
    .timeline-card.web { background:linear-gradient(135deg,rgba(226,248,255,.95),rgba(184,228,242,.86)); }
    .timeline-card.short { background:linear-gradient(135deg,rgba(255,231,214,.95),rgba(255,196,166,.82)); }
    .timeline-card::after { content:''; position:absolute; inset:0; background:repeating-linear-gradient(135deg,rgba(255,255,255,.16) 0 1px,transparent 1px 7px); pointer-events:none; opacity:.5; }
    .app-icon { position:relative; z-index:1; flex:none; display:grid; place-items:center; width:24px; height:24px; border-radius:7px; background:#fff; color:#241c16; font-size:13px; font-weight:800; box-shadow:0 2px 8px rgba(36,28,22,.14); overflow:hidden; }
    .app-icon.youtube { background:#ff0033; color:#fff; }
    .app-icon.github { background:#24292f; color:#fff; }
    .app-icon.chatgpt { background:#111827; color:#fff; }
    .app-icon.x { background:#050505; color:#fff; }
    .app-icon.code { background:#1473c3; color:#fff; }
    .app-icon.shell { background:#222; color:#d5f5ff; font-size:11px; }
    .app-icon.browser { background:linear-gradient(135deg,#fbbc05,#34a853 45%,#4285f4); color:#fff; }
    .timeline-card-body { position:relative; z-index:1; min-width:0; }
    .timeline-card-title { color:#2d251e; font-size:13px; font-weight:800; line-height:1.25; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .timeline-card-time { margin-top:2px; color:#6f6257; font-size:11px; font-weight:650; font-variant-numeric:tabular-nums; }
    .timeline-start-dot { position:absolute; left:58px; width:10px; height:10px; border-radius:999px; background:#d43b3b; box-shadow:0 0 0 3px rgba(255,250,241,.9); z-index:5; }
    @media(max-width: 820px) { main.wrap { grid-template-columns: 1fr; } .item { grid-template-columns: 76px minmax(0,1fr); } .timeline-viz-header { flex-direction:column; } .view-toggle { align-self:flex-start; } .vertical-timeline { min-width:560px; padding-left:66px; } .timeline-rail { left:54px; } .timeline-card { left:74px; } .time-tick-label { left:-68px; width:48px; } .time-tick-dot, .timeline-start-dot { left:50px; } }
  </style>
</head>
<body>
  <header><div class="wrap">
    <h1>Winflow 本地访问轨迹</h1>
    <div class="sub">数据只从本机 SQLite 读取。先运行 <code>python -m app.main collect</code> 才会持续产生记录。</div>
    <div class="toolbar">
      <input id="day" type="date" />
      <button id="bandsBtn" class="active" onclick="setMode('bands')">活动带</button>
      <button id="rawBtn" class="secondary" onclick="setMode('raw')">原始事件</button>
      <button onclick="loadData()">查看</button>
      <a id="export" class="button" href="/api/export" target="_blank">导出 Markdown</a>
    </div>
  </div></header>
  <main class="wrap">
    <aside class="panel">
      <p class="stat-title">应用使用排行</p>
      <div id="apps"></div>
      <p class="stat-title" style="margin-top:22px">浏览器访问数</p>
      <div id="browsers"></div>
    </aside>
    <section class="panel timeline">
      <div id="timelineViz" class="timeline-viz">
        <div class="timeline-viz-header">
          <div>
            <p class="stat-title">活动带时间轴</p>
            <div class="sub">竖向时间轴展示活动带，卡片内暂时只放应用/网站图标和名称。</div>
          </div>
          <div class="view-toggle">
            <button id="compactRangeBtn" class="active" onclick="setRangeMode('compact')">紧凑</button>
            <button id="fullRangeBtn" class="secondary" onclick="setRangeMode('full')">全天</button>
          </div>
        </div>
        <div id="timelineChart" class="timeline-chart"></div>
      </div>
      <p class="stat-title" id="timeline-title">时间线</p>
      <div id="items"></div>
    </section>
  </main>
<script>
function pad(n){ return String(n).padStart(2,'0') }
function fmt(ts){ const d=new Date(ts*1000); return pad(d.getHours())+':'+pad(d.getMinutes()) }
function localDayValue(d){ return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate()) }
function esc(s){ return String(s ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])) }
let mode = 'bands';
let rangeMode = 'compact';
function minutes(seconds){ return Math.round(Number(seconds||0)/60) }
function setMode(next){
  mode = next;
  document.getElementById('bandsBtn').className = next === 'bands' ? 'active' : 'secondary';
  document.getElementById('rawBtn').className = next === 'raw' ? 'active' : 'secondary';
  loadData();
}
function setRangeMode(next){
  rangeMode = next === 'full' ? 'full' : 'compact';
  const compactBtn = document.getElementById('compactRangeBtn');
  const fullBtn = document.getElementById('fullRangeBtn');
  compactBtn.className = rangeMode === 'compact' ? 'active' : 'secondary';
  fullBtn.className = rangeMode === 'full' ? 'active' : 'secondary';
  compactBtn.setAttribute('aria-pressed', rangeMode === 'compact' ? 'true' : 'false');
  fullBtn.setAttribute('aria-pressed', rangeMode === 'full' ? 'true' : 'false');
  if(mode === 'bands') loadData();
}
function focusBandItem(index){
  const item = document.getElementById('band-' + index);
  if(!item) return;
  document.querySelectorAll('.item.focused').forEach(el => el.classList.remove('focused'));
  item.classList.add('focused');
  item.scrollIntoView({behavior:'smooth', block:'center'});
}
function floorToHour(ts){ return Math.floor(Number(ts||0) / 3600) * 3600 }
function ceilToHour(ts){ return Math.ceil(Number(ts||0) / 3600) * 3600 }
function buildTimelineRange(data){
  const bands = data.bands || [];
  if(rangeMode === 'full' || !bands.length){
    return { rangeStart: Number(data.start_ts||0), rangeEnd: Number(data.end_ts||0) };
  }
  const minStart = Math.min(...bands.map(b => Number(b.start_ts||0)));
  const maxEnd = Math.max(...bands.map(b => Number(b.end_ts||0)));
  return { rangeStart: floorToHour(minStart), rangeEnd: ceilToHour(maxEnd) };
}
function buildTicks(rangeStart, rangeEnd, stepSeconds = 3600){
  const ticks = [];
  let cursor = ceilToHour(rangeStart);
  while(cursor <= rangeEnd){
    ticks.push(cursor);
    cursor += stepSeconds;
  }
  return ticks;
}
function pct(ts, rangeStart, rangeEnd){
  if(rangeEnd <= rangeStart) return 0;
  return (Number(ts||0) - rangeStart) / (rangeEnd - rangeStart) * 100;
}
function bandTooltip(band){
  const samples = [...(band.sample_titles || []), ...(band.sample_details || [])].slice(0, 5);
  return [
    band.title || band.event_key || '活动',
    fmt(band.start_ts) + ' - ' + fmt(band.end_ts),
    '估算活跃：' + minutes(band.total_active_seconds) + ' 分钟',
    '命中：' + Number(band.hit_count || 0) + ' 次',
    band.subtitle || '',
    band.detail || '',
    samples.length ? '样本：\\n' + samples.join('\\n') : ''
  ].filter(Boolean).join('\\n');
}
function labelForBand(band){
  const raw = (band.title || band.subtitle || band.event_key || '活动').replace(/^app:|^web:/, '');
  return raw.length > 44 ? raw.slice(0, 43) + '…' : raw;
}
function iconForBand(band){
  const text = [band.event_key, band.title, band.subtitle, band.detail].join(' ').toLowerCase();
  if(text.includes('youtube')) return { cls:'youtube', text:'▶' };
  if(text.includes('github')) return { cls:'github', text:'GH' };
  if(text.includes('chatgpt') || text.includes('openai') || text.includes('codex')) return { cls:'chatgpt', text:'✺' };
  if(text.includes('twitter') || text.includes('x.com')) return { cls:'x', text:'𝕏' };
  if(text.includes('code.exe') || text.includes('cursor') || text.includes('antigravity')) return { cls:'code', text:'</>' };
  if(text.includes('powershell') || text.includes('terminal') || text.includes('cmd.exe')) return { cls:'shell', text:'>_' };
  if(text.includes('chrome') || text.includes('edge') || text.includes('browser')) return { cls:'browser', text:'●' };
  if(text.includes('explorer.exe')) return { cls:'', text:'📁' };
  if(band.event_type === 'web') return { cls:'browser', text:(labelForBand(band)[0] || 'W').toUpperCase() };
  return { cls:'', text:(labelForBand(band)[0] || 'A').toUpperCase() };
}
function assignVisualColumns(bands){
  const activeEnds = [];
  return bands.map((band, index) => {
    let column = activeEnds.findIndex(end => Number(band.start_ts||0) >= end + 60);
    if(column === -1){ column = activeEnds.length; activeEnds.push(0); }
    activeEnds[column] = Math.max(activeEnds[column], Number(band.end_ts||0));
    return {...band, _index:band._index ?? index, _column:Math.min(column, 4)};
  });
}
function renderTimelineViz(data){
  const viz = document.getElementById('timelineViz');
  const chart = document.getElementById('timelineChart');
  viz.style.display = mode === 'bands' ? '' : 'none';
  if(mode !== 'bands') return;
  const bands = data.bands || [];
  if(!bands.length){
    chart.innerHTML = '<div class="empty">暂无活动带可视化数据。</div>';
    return;
  }
  const { rangeStart, rangeEnd } = buildTimelineRange(data);
  const duration = Math.max(1, rangeEnd - rangeStart);
  const minutesInRange = duration / 60;
  const pixelsPerMinute = rangeMode === 'full' ? 0.9 : 2.2;
  const chartHeight = Math.max(360, Math.min(1800, Math.round(minutesInRange * pixelsPerMinute)));
  const tickStep = duration <= 2 * 3600 ? 1800 : 3600;
  const ticks = buildTicks(rangeStart, rangeEnd, tickStep);
  const yOf = ts => Math.max(0, Math.min(chartHeight, (Number(ts||0) - rangeStart) / duration * chartHeight));
  const tickHtml = ticks.map(t => `<div class="time-tick" style="top:${yOf(t).toFixed(1)}px"><span class="time-tick-label">${fmt(t)}</span><span class="time-tick-dot"></span></div>`).join('');
  const visualBands = assignVisualColumns(bands.map((band, index) => ({...band, _index:index})).sort((a, b) => Number(a.start_ts||0) - Number(b.start_ts||0) || Number(b.end_ts||0) - Number(a.end_ts||0)));
  const cardHtml = visualBands.map(band => {
    const top = yOf(band.start_ts);
    const bottom = yOf(band.end_ts);
    const height = Math.max(42, bottom - top);
    const offset = Number(band._column || 0) * 18;
    const icon = iconForBand(band);
    const label = labelForBand(band);
    const typeClass = band.event_type === 'web' ? 'web' : 'app';
    const shortClass = height <= 48 ? ' short' : '';
    return `<span class="timeline-start-dot" style="top:${Math.max(0, top - 5).toFixed(1)}px"></span><button type="button" class="timeline-card ${typeClass}${shortClass}" style="top:${top.toFixed(1)}px;min-height:${height.toFixed(1)}px;left:${86 + offset}px;right:${offset}px" title="${esc(bandTooltip(band))}" aria-label="定位到 ${esc(label)} ${fmt(band.start_ts)} 到 ${fmt(band.end_ts)}" onclick="focusBandItem(${Number(band._index)})"><span class="app-icon ${icon.cls}">${esc(icon.text)}</span><span class="timeline-card-body"><span class="timeline-card-title">${esc(label)}</span><span class="timeline-card-time">${fmt(band.start_ts)} to ${fmt(band.end_ts)}</span></span></button>`;
  }).join('');
  chart.innerHTML = `<div class="vertical-timeline" style="height:${chartHeight}px"><div class="timeline-rail"></div>${tickHtml}${cardHtml}</div>`;
}
function renderBars(el, rows, nameKey, valueKey, suffix){
  const max = Math.max(1, ...rows.map(r=>Number(r[valueKey]||0)));
  el.innerHTML = rows.length ? rows.map(r=>`<div class="bar"><div class="label"><span>${esc(r[nameKey])}</span><span>${suffix(r[valueKey])}</span></div><div class="meter"><span style="width:${Math.max(4, Number(r[valueKey]||0)/max*100)}%"></span></div></div>`).join('') : '<div class="empty">暂无数据</div>';
}
async function loadData(){
  const day = document.getElementById('day').value;
  const qs = day ? '?day='+encodeURIComponent(day) : '';
  document.getElementById('export').href = '/api/export'+qs;
  const res = await fetch((mode === 'bands' ? '/api/bands' : '/api/timeline')+qs);
  const data = await res.json();
  document.getElementById('timeline-title').textContent = data.day + (mode === 'bands' ? ' 活动带' : ' 原始时间线');
  if(mode === 'bands'){
    renderTimelineViz(data);
    const topBands = (data.stats && data.stats.top_bands || []).map(b => ({ name: b.title + ' · ' + b.subtitle, seconds: b.total_active_seconds }));
    const byType = (data.stats && data.stats.by_type || []).map(r => ({ name: r.event_type === 'web' ? '网页' : '应用', count: r.band_count }));
    renderBars(document.getElementById('apps'), topBands, 'name', 'seconds', v => minutes(v)+' 分钟');
    renderBars(document.getElementById('browsers'), byType, 'name', 'count', v => Number(v||0)+' 条');
    renderBands(data);
    return;
  }
  renderTimelineViz(data);
  renderBars(document.getElementById('apps'), data.stats.apps || [], 'process_name', 'seconds', v => minutes(v)+' 分钟');
  renderBars(document.getElementById('browsers'), data.stats.browsers || [], 'browser', 'count', v => Number(v||0)+' 次');
  renderRawItems(data);
}
function renderRawItems(data){
  const items = document.getElementById('items');
  if(!data.items.length){ items.innerHTML = '<div class="empty">暂无记录。请先运行采集命令。</div>'; return; }
  items.innerHTML = data.items.map(it => `<div class="item"><div class="time">${fmt(it.start_ts)}${it.end_ts!==it.start_ts ? '<br>↓ '+fmt(it.end_ts):''}</div><div><div class="title"><span class="kind ${it.kind}">${it.kind==='web'?'网页':'应用'}</span>${esc(it.title)}</div><div class="meta">${esc(it.subtitle)} ${it.detail ? ' · '+esc(it.detail):''}</div></div></div>`).join('');
}
function renderBands(data){
  const items = document.getElementById('items');
  if(!data.bands.length){ items.innerHTML = '<div class="empty">暂无活动带。采集一段时间后，超过阈值的事件会出现在这里。</div>'; return; }
  items.innerHTML = data.bands.map((b, index) => {
    const samples = [...(b.sample_titles || []), ...(b.sample_details || [])].slice(0, 6);
    const sampleHtml = samples.length ? `<div class="samples">${samples.map(s => `<span class="sample">${esc(s)}</span>`).join('')}</div>` : '';
    return `<div class="item" id="band-${b._index ?? index}"><div class="time">${fmt(b.start_ts)}<br>↓ ${fmt(b.end_ts)}</div><div><div class="title"><span class="kind ${b.event_type==='web'?'web':'band'}">${b.event_type==='web'?'网页':'活动'}</span>${esc(b.title)}</div><div class="meta">${esc(b.subtitle)} · 估算活跃 ${minutes(b.total_active_seconds)} 分钟 · 命中 ${Number(b.hit_count||0)} 次${b.detail ? ' · '+esc(b.detail):''}</div>${sampleHtml}</div></div>`;
  }).join('');
}
(function(){ const d=new Date(); document.getElementById('day').value = localDayValue(d); loadData(); setInterval(loadData, 30000); })();
</script>
</body>
</html>"""


def sync_browsers() -> int:
    visits = read_recent_browser_history()
    return insert_browser_visits(visits)


def collect_once(sync_browser: bool = True) -> None:
    init_db()
    window = get_foreground_window()
    if window:
        status = record_foreground_window(window)
        print(f"[window] {status}: {window.process_name} | {window.title}")
    else:
        print("[window] 未获取到前台窗口")
    if sync_browser:
        count = sync_browsers()
        print(f"[browser] 新增 {count} 条历史记录")


def collect_loop(interval: int, browser_interval: int) -> None:
    init_db()
    print(f"Winflow 采集中：DB={DB_PATH}，窗口间隔={interval}s，浏览器同步={browser_interval}s。Ctrl+C 停止。")
    last_browser_sync = 0
    try:
        while True:
            now = time.time()
            window = get_foreground_window()
            if window:
                record_foreground_window(window, int(now))
            if now - last_browser_sync >= browser_interval:
                count = sync_browsers()
                print(f"[{time.strftime('%H:%M:%S')}] 浏览器同步：新增 {count} 条")
                last_browser_sync = now
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n采集已停止")


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

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        day = qs.get("day", [None])[0]
        if parsed.path == "/":
            self._send(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if parsed.path == "/api/timeline":
            body = json.dumps(build_timeline(day), ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return
        if parsed.path == "/api/bands":
            body = json.dumps(build_activity_bands(day), ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return
        if parsed.path == "/api/export":
            body = build_summary_text(day).encode("utf-8")
            self._send(200, body, "text/markdown; charset=utf-8")
            return
        self._send(404, b"Not found", "text/plain; charset=utf-8")


def serve(host: str, port: int, open_browser: bool) -> None:
    init_db()
    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"
    print(f"Winflow Web UI: {url}")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Winflow Windows 本地访问轨迹 MVP")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="初始化数据库")
    sub.add_parser("once", help="采集一次当前前台窗口并同步浏览器历史")
    sub.add_parser("sync-browsers", help="同步浏览器历史")

    p_collect = sub.add_parser("collect", help="持续采集")
    p_collect.add_argument("--interval", type=int, default=DEFAULT_COLLECT_INTERVAL_SECONDS)
    p_collect.add_argument("--browser-interval", type=int, default=DEFAULT_BROWSER_SYNC_INTERVAL_SECONDS)

    p_serve = sub.add_parser("serve", help="启动本地 Web UI")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8765)
    p_serve.add_argument("--no-open", action="store_true")

    p_export = sub.add_parser("export", help="导出指定日期 Markdown")
    p_export.add_argument("--day", default=None, help="YYYY-MM-DD，默认今天")

    p_bands = sub.add_parser("bands", help="输出指定日期活动带 JSON")
    p_bands.add_argument("--day", default=None, help="YYYY-MM-DD，默认今天")

    args = parser.parse_args(argv)
    if args.cmd == "init":
        init_db()
        print(f"数据库已初始化：{DB_PATH}")
    elif args.cmd == "once":
        collect_once(sync_browser=True)
    elif args.cmd == "sync-browsers":
        profiles = discover_browser_profiles()
        print("发现浏览器配置：" + (", ".join(f"{p.browser}/{p.profile}" for p in profiles) or "无"))
        count = sync_browsers()
        print(f"新增 {count} 条浏览器历史记录")
    elif args.cmd == "collect":
        collect_loop(max(1, args.interval), max(30, args.browser_interval))
    elif args.cmd == "serve":
        serve(args.host, args.port, not args.no_open)
    elif args.cmd == "export":
        print(build_summary_text(args.day))
    elif args.cmd == "bands":
        print(json.dumps(build_activity_bands(args.day), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
