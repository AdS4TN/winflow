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
    .timeline-chart { max-width:100%; overflow-x:auto; overflow-y:hidden; padding:2px 2px 10px; scrollbar-color:#cbb8a3 #f2e7d8; scrollbar-width:thin; }
    .timeline-chart::-webkit-scrollbar { height:10px; }
    .timeline-chart::-webkit-scrollbar-track { background:#f2e7d8; border-radius:999px; }
    .timeline-chart::-webkit-scrollbar-thumb { background:#cbb8a3; border-radius:999px; border:2px solid #f2e7d8; }
    .timeline-scale { position:relative; height:34px; margin-left:148px; border-bottom:1px solid var(--line); min-width:760px; background:linear-gradient(180deg,rgba(255,255,255,.34),rgba(255,255,255,0)); }
    .tick { position:absolute; top:0; bottom:0; border-left:1px solid rgba(121,108,95,.28); pointer-events:none; }
    .tick span { position:absolute; top:2px; transform:translateX(-50%); padding:1px 4px; border-radius:6px; background:rgba(255,250,241,.88); font-size:11px; color:var(--muted); white-space:nowrap; font-variant-numeric:tabular-nums; }
    .lane { display:grid; grid-template-columns:140px minmax(760px, 1fr); min-width:900px; min-height:38px; align-items:center; }
    .lane-label { min-width:0; max-width:140px; font-size:12px; color:#5d5146; padding:0 12px 0 2px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-weight:650; }
    .lane-track { position:relative; height:38px; border-bottom:1px dashed rgba(203,184,163,.82); background:linear-gradient(180deg,rgba(255,255,255,.32),rgba(255,255,255,0)); }
    .lane-track .tick { opacity:.55; }
    .lane-track .tick span { display:none; }
    .timeline-band { position:absolute; top:8px; height:20px; border-radius:999px; min-width:8px; cursor:pointer; border:1px solid rgba(255,255,255,.52); box-shadow:0 3px 10px rgba(36,28,22,.16), inset 0 1px 0 rgba(255,255,255,.28); transition:transform .14s ease, box-shadow .14s ease, filter .14s ease; }
    .timeline-band::after { content:''; position:absolute; inset:2px 5px auto; height:38%; border-radius:999px; background:rgba(255,255,255,.22); pointer-events:none; }
    .timeline-band:hover, .timeline-band:focus { z-index:3; transform:translateY(-1px) scaleY(1.08); filter:saturate(1.1); box-shadow:0 8px 18px rgba(36,28,22,.22), 0 0 0 3px rgba(155,92,37,.12); outline:none; }
    .timeline-band.app { background:linear-gradient(90deg,#d98a38,var(--app) 55%,var(--app-dark)); }
    .timeline-band.web { background:linear-gradient(90deg,#45a6c7,var(--web) 55%,var(--web-dark)); }
    @media(max-width: 820px) { main.wrap { grid-template-columns: 1fr; } .item { grid-template-columns: 76px minmax(0,1fr); } .timeline-viz-header { flex-direction:column; } .view-toggle { align-self:flex-start; } .timeline-scale { margin-left:118px; min-width:680px; } .lane { grid-template-columns:110px minmax(680px,1fr); min-width:790px; } .lane-label { max-width:110px; font-size:11px; } }
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
            <div class="sub">每个事件一条轨道，色块长度表示持续区间。</div>
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
  const ticks = buildTicks(rangeStart, rangeEnd);
  const tickHtml = ticks.map(t => `<div class="tick" style="left:${pct(t, rangeStart, rangeEnd).toFixed(3)}%"><span>${fmt(t)}</span></div>`).join('');
  const laneMap = new Map();
  bands.forEach((band, index) => {
    band._index = index;
    const key = band.event_key || 'unknown:' + index;
    if(!laneMap.has(key)){
      laneMap.set(key, { key, label: band.title || key, firstStart: Number(band.start_ts||0), totalSeconds: 0, bands: [] });
    }
    const lane = laneMap.get(key);
    lane.firstStart = Math.min(lane.firstStart, Number(band.start_ts||0));
    lane.totalSeconds += Number(band.total_active_seconds||0);
    lane.bands.push(band);
  });
  const lanes = Array.from(laneMap.values()).sort((a, b) => a.firstStart - b.firstStart || b.totalSeconds - a.totalSeconds);
  const laneHtml = lanes.map(lane => {
    const blocks = lane.bands.map(band => {
      const left = Math.max(0, Math.min(100, pct(band.start_ts, rangeStart, rangeEnd)));
      const rawWidth = pct(band.end_ts, rangeStart, rangeEnd) - pct(band.start_ts, rangeStart, rangeEnd);
      const width = Math.min(100 - left, Math.max(0.6, rawWidth));
      const typeClass = band.event_type === 'web' ? 'web' : 'app';
      const label = band.title || band.event_key || '活动';
      return `<button type="button" class="timeline-band ${typeClass}" style="left:${left.toFixed(3)}%;width:${width.toFixed(3)}%" title="${esc(bandTooltip(band))}" aria-label="定位到 ${esc(label)} ${fmt(band.start_ts)} 到 ${fmt(band.end_ts)}" onclick="focusBandItem(${Number(band._index)})"></button>`;
    }).join('');
    return `<div class="lane"><div class="lane-label" title="${esc(lane.label)}">${esc(lane.label)}</div><div class="lane-track">${tickHtml}${blocks}</div></div>`;
  }).join('');
  chart.innerHTML = `<div class="timeline-scale">${tickHtml}</div>${laneHtml}`;
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
