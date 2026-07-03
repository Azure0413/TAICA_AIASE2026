"""給 Pi bridge / 使用者呼叫的 CLI：capture / retrieve / inject / list / forget。

`capture` / `retrieve` / `inject` 由 Pi extension 在 agent 生命週期事件中呼叫；
`list` / `forget` 由 Pi 的斜線命令 `/recall`、`/forget` 包裝供使用者手動觸發。
"""
from __future__ import annotations
import argparse
import json
import sys

from .core import (
    capture,
    retrieve,
    build_injection,
    make_observation,
    list_all,
    forget,
    forget_by_summary,
)


def _format_obs_brief(o: dict) -> str:
    from datetime import datetime, timezone
    ts = o.get("timestamp", 0)
    when = (
        datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        if ts else "----"
    )
    tags = ",".join(o.get("tags") or [])
    short_id = (o.get("id") or "")[:10]
    summary = o.get("summary", "")
    head = f"[{short_id}] {when}"
    if tags:
        head += f" #{tags}"
    return f"{head}\n  {summary}"


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m memory.cli")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("capture", help="記下一條 observation")
    c.add_argument("--summary", required=True)
    c.add_argument("--session", default="cli")
    c.add_argument("--tags", default="")

    r = sub.add_parser("retrieve", help="檢索相關 observation (JSON)")
    r.add_argument("--query", required=True)
    r.add_argument("--k", type=int, default=8)

    i = sub.add_parser("inject", help="輸出已格式化的注入文字")
    i.add_argument("--query", required=True)
    i.add_argument("--budget", type=int, default=2000)

    l = sub.add_parser("list", help="列出所有記憶（可選關鍵字過濾）")
    l.add_argument("--query", default="")
    l.add_argument("--limit", type=int, default=50)

    f = sub.add_parser("forget", help="刪除一筆記憶（以 id 或 summary）")
    f.add_argument("--id", default=None)
    f.add_argument("--summary", default=None)

    args = p.parse_args(argv)
    if args.cmd == "capture":
        tags = [t for t in args.tags.split(",") if t]
        capture(make_observation(args.summary, session_id=args.session, tags=tags))
        print(f"Remembered: {args.summary}")
    elif args.cmd == "retrieve":
        print(json.dumps(retrieve(args.query, args.k), ensure_ascii=False))
    elif args.cmd == "inject":
        sys.stdout.write(build_injection(args.query, args.budget))
    elif args.cmd == "list":
        items = list_all()
        if args.query:
            q = args.query.lower()
            items = [o for o in items if q in (o.get("summary", "") + " " + " ".join(o.get("tags") or [])).lower()]
        items = items[: args.limit]
        if not items:
            print("(沒有匹配的記憶)")
            return
        print(f"Total: {len(items)}")
        for o in items:
            print(_format_obs_brief(o))
            print()
    elif args.cmd == "forget":
        if not (args.id or args.summary):
            print("Error: 需提供 --id 或 --summary", file=sys.stderr)
            sys.exit(2)
        ok = forget(args.id) if args.id else forget_by_summary(args.summary)
        print("Forgotten." if ok else "(查無該筆記憶)")


if __name__ == "__main__":
    main()
