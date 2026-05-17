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
    :root { color-scheme: light; --bg:#f7f1e8; --card:#fffaf1; --ink:#241c16; --muted:#796c5f; --line:#e3d6c5; --accent:#9b5c25; }
    * { box-sizing: border-box; }
    body { margin:0; font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--ink); }
    header { position: sticky; top:0; z-index:2; backdrop-filter: blur(16px); background: rgba(247,241,232,.82); border-bottom:1px solid var(--line); }
    .wrap { max-width: 1120px; margin:0 auto; padding: 18px 22px; }
    h1 { margin:0; font-size: 26px; letter-spacing:-.03em; }
    .sub { color:var(--muted); margin-top:6px; font-size:14px; }
    .toolbar { display:flex; gap:10px; align-items:center; margin-top:14px; flex-wrap:wrap; }
    input, button, a.button { border:1px solid var(--line); border-radius:12px; padding:10px 12px; background:#fff; color:var(--ink); text-decoration:none; }
    button, a.button { cursor:pointer; background:#2b2119; color:#fff; border-color:#2b2119; }
    main.wrap { display:grid; grid-template-columns: 300px 1fr; gap:18px; }
    .panel { background: rgba(255,250,241,.86); border:1px solid var(--line); border-radius:20px; padding:16px; box-shadow: 0 10px 30px rgba(91,63,35,.08); }
    .stat-title { font-weight:700; margin:0 0 10px; }
    .bar { margin:10px 0; }
    .bar .label { display:flex; justify-content:space-between; gap:12px; font-size:13px; color:var(--muted); }
    .meter { height:8px; border-radius:99px; background:#eadcca; overflow:hidden; margin-top:5px; }
    .meter span { display:block; height:100%; background:linear-gradient(90deg,#c47a31,#7d4a21); }
    .timeline { position:relative; }
    .item { display:grid; grid-template-columns: 94px 1fr; gap:12px; padding:12px 0; border-bottom:1px solid var(--line); }
    .time { color:var(--accent); font-variant-numeric: tabular-nums; font-size:13px; padding-top:2px; }
    .kind { display:inline-block; font-size:11px; border-radius:999px; padding:3px 8px; margin-right:8px; color:#fff; background:#6b4c32; }
    .kind.web { background:#315f7d; }
    .title { font-weight:650; line-height:1.35; overflow-wrap:anywhere; }
    .meta { color:var(--muted); font-size:13px; margin-top:4px; overflow-wrap:anywhere; }
    .empty { color:var(--muted); padding:30px; text-align:center; }
    @media(max-width: 820px) { main.wrap { grid-template-columns: 1fr; } .item { grid-template-columns: 76px 1fr; } }
  </style>
</head>
<body>
  <header><div class="wrap">
    <h1>Winflow 本地访问轨迹</h1>
    <div class="sub">数据只从本机 SQLite 读取。先运行 <code>python -m app.main collect</code> 才会持续产生记录。</div>
    <div class="toolbar">
      <input id="day" type="date" />
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
      <p class="stat-title" id="timeline-title">时间线</p>
      <div id="items"></div>
    </section>
  </main>
<script>
function pad(n){ return String(n).padStart(2,'0') }
function fmt(ts){ const d=new Date(ts*1000); return pad(d.getHours())+':'+pad(d.getMinutes()) }
function esc(s){ return (s||'').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])) }
function renderBars(el, rows, nameKey, valueKey, suffix){
  const max = Math.max(1, ...rows.map(r=>Number(r[valueKey]||0)));
  el.innerHTML = rows.length ? rows.map(r=>`<div class="bar"><div class="label"><span>${esc(r[nameKey])}</span><span>${suffix(r[valueKey])}</span></div><div class="meter"><span style="width:${Math.max(4, Number(r[valueKey]||0)/max*100)}%"></span></div></div>`).join('') : '<div class="empty">暂无数据</div>';
}
async function loadData(){
  const day = document.getElementById('day').value;
  const qs = day ? '?day='+encodeURIComponent(day) : '';
  document.getElementById('export').href = '/api/export'+qs;
  const res = await fetch('/api/timeline'+qs);
  const data = await res.json();
  document.getElementById('timeline-title').textContent = data.day + ' 时间线';
  renderBars(document.getElementById('apps'), data.stats.apps || [], 'process_name', 'seconds', v => Math.round(Number(v||0)/60)+' 分钟');
  renderBars(document.getElementById('browsers'), data.stats.browsers || [], 'browser', 'count', v => Number(v||0)+' 次');
  const items = document.getElementById('items');
  if(!data.items.length){ items.innerHTML = '<div class="empty">暂无记录。请先运行采集命令。</div>'; return; }
  items.innerHTML = data.items.map(it => `<div class="item"><div class="time">${fmt(it.start_ts)}${it.end_ts!==it.start_ts ? '<br>↓ '+fmt(it.end_ts):''}</div><div><div class="title"><span class="kind ${it.kind}">${it.kind==='web'?'网页':'应用'}</span>${esc(it.title)}</div><div class="meta">${esc(it.subtitle)} ${it.detail ? ' · '+esc(it.detail):''}</div></div></div>`).join('');
}
(function(){ const d=new Date(); document.getElementById('day').value = d.toISOString().slice(0,10); loadData(); setInterval(loadData, 30000); })();
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
