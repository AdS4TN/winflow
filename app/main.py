from __future__ import annotations

import argparse
import json
import sys

from .activity_bands import build_activity_bands
from .app_usage import build_usage_snapshot
from .collector import collect_loop, collect_once
from .config import DEFAULT_COLLECT_INTERVAL_SECONDS, DB_PATH
from .timeline import build_summary_text
from .uploader import UploadError, upload_loop, upload_pending, upload_usage
from .web import serve


DESC = 'Winflow Windows 本地自动工作日志'
HELP_INIT = '初始化本地数据库'
HELP_ONCE = '采集一次当前前台窗口'
HELP_COLLECT = '持续采集前台窗口'
HELP_INTERVAL = '采集间隔秒数，默认 5'
HELP_SERVE = '启动本地 Web UI'
HELP_HOST = '监听地址，默认 127.0.0.1'
HELP_PORT = '监听端口，默认 8765'
HELP_NO_OPEN = '启动后不自动打开浏览器'
HELP_WITH_COLLECTOR = '启动 Web UI 时同时启动后台采集器'
HELP_EMBED_INTERVAL = '内置采集器间隔秒数，默认 5'
HELP_EXPORT = '导出当天摘要 Markdown'
HELP_DAY = 'YYYY-MM-DD，默认今天'
HELP_BANDS = '输出活动带聚合 JSON'
HELP_USAGE = '输出应用使用统计 JSON'
HELP_IDLE_THRESHOLD = '空闲切分阈值秒数，默认 300'
HELP_UPLOAD = '上传应用使用统计到自托管服务端'
HELP_SERVER_URL = '上传服务器地址，默认读取 WINFLOW_SERVER_URL'
HELP_TOKEN = '上传 token，默认读取 WINFLOW_UPLOAD_TOKEN'
HELP_RETRY_PENDING = '先重试本地 pending 上传队列'
HELP_WATCH = '持续定时上传应用使用统计'
HELP_UPLOAD_INTERVAL = '持续上传间隔秒数，默认 300'
MSG_DB_INIT = '已初始化数据库：{path}'
MSG_PENDING_UPLOADED = '已上传 {count} 个 pending 快照'
MSG_UPLOAD_FAILED = '上传失败：{error}'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=DESC)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help=HELP_INIT)
    sub.add_parser("once", help=HELP_ONCE)

    p_collect = sub.add_parser("collect", help=HELP_COLLECT)
    p_collect.add_argument("--interval", type=int, default=DEFAULT_COLLECT_INTERVAL_SECONDS, help=HELP_INTERVAL)

    p_serve = sub.add_parser("serve", help=HELP_SERVE)
    p_serve.add_argument("--host", default="127.0.0.1", help=HELP_HOST)
    p_serve.add_argument("--port", type=int, default=8765, help=HELP_PORT)
    p_serve.add_argument("--no-open", action="store_true", help=HELP_NO_OPEN)
    p_serve.add_argument("--with-collector", action="store_true", help=HELP_WITH_COLLECTOR)
    p_serve.add_argument("--interval", type=int, default=DEFAULT_COLLECT_INTERVAL_SECONDS, help=HELP_EMBED_INTERVAL)

    p_export = sub.add_parser("export", help=HELP_EXPORT)
    p_export.add_argument("--day", default=None, help=HELP_DAY)

    p_bands = sub.add_parser("bands", help=HELP_BANDS)
    p_bands.add_argument("--day", default=None, help=HELP_DAY)

    p_usage = sub.add_parser("usage", help=HELP_USAGE)
    p_usage.add_argument("--day", default=None, help=HELP_DAY)
    p_usage.add_argument("--idle-threshold-seconds", type=int, default=300, help=HELP_IDLE_THRESHOLD)

    p_upload = sub.add_parser("upload-usage", help=HELP_UPLOAD)
    p_upload.add_argument("--day", default=None, help=HELP_DAY)
    p_upload.add_argument("--server-url", default=None, help=HELP_SERVER_URL)
    p_upload.add_argument("--token", default=None, help=HELP_TOKEN)
    p_upload.add_argument("--retry-pending", action="store_true", help=HELP_RETRY_PENDING)
    p_upload.add_argument("--watch", action="store_true", help=HELP_WATCH)
    p_upload.add_argument("--interval", type=int, default=300, help=HELP_UPLOAD_INTERVAL)

    args = parser.parse_args(argv)
    if args.cmd == "init":
        from .storage import init_db

        init_db()
        print(MSG_DB_INIT.format(path=DB_PATH))
    elif args.cmd == "once":
        collect_once()
    elif args.cmd == "collect":
        collect_loop(max(1, args.interval))
    elif args.cmd == "serve":
        serve(
            args.host,
            args.port,
            not args.no_open,
            with_collector=args.with_collector,
            collect_interval=args.interval,
        )
    elif args.cmd == "export":
        print(build_summary_text(args.day))
    elif args.cmd == "bands":
        print(json.dumps(build_activity_bands(args.day), ensure_ascii=False, indent=2))
    elif args.cmd == "usage":
        print(
            json.dumps(
                build_usage_snapshot(
                    args.day,
                    idle_threshold_seconds=max(0, args.idle_threshold_seconds),
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.cmd == "upload-usage":
        try:
            if args.watch:
                upload_loop(
                    args.day,
                    server_url=args.server_url,
                    upload_token=args.token,
                    interval_seconds=args.interval,
                )
                return 0
            if args.retry_pending:
                count = upload_pending(server_url=args.server_url, upload_token=args.token)
                if count:
                    print(MSG_PENDING_UPLOADED.format(count=count))
            result = upload_usage(args.day, server_url=args.server_url, upload_token=args.token)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        except UploadError as exc:
            print(MSG_UPLOAD_FAILED.format(error=exc), file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
