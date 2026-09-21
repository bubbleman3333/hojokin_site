"""使い方:
  python -m hojokin fetch [--limit N]        jGrants から取り込む
  python -m hojokin build [--out dist] [--site-url URL]   サイトを生成
  python -m hojokin pending [--all] [--limit N] [--json]  記事がまだ無い補助金を出す
  python -m hojokin all                       fetch → build
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from .articles import pending
from .build import ROOT, Builder, load_config, load_subsidies
from .jgrants import sync
from .model import JST


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="hojokin", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--limit", type=int, default=None, help="詳細を取る件数の上限（試し用）")
    b = sub.add_parser("build")
    b.add_argument("--out", default="dist")
    b.add_argument("--site-url", default=None)
    q = sub.add_parser("pending")
    q.add_argument("--all", action="store_true", help="終了分も含める")
    q.add_argument("--limit", type=int, default=None)
    q.add_argument("--json", action="store_true", help="コードだけを JSON 配列で出す")
    a = sub.add_parser("all")
    a.add_argument("--out", default="dist")
    a.add_argument("--site-url", default=None)
    args = p.parse_args(argv)

    site, _ = load_config()
    if args.cmd in ("fetch", "all"):
        sync(ROOT / "data" / "subsidies", limit=getattr(args, "limit", None))
    if args.cmd in ("build", "all"):
        n = Builder(Path(args.out), args.site_url or site["site_url"]).build()
        print(f"{n} 件から {args.out}/ を生成した")
    if args.cmd == "pending":
        subs = load_subsidies(ROOT / "data" / "subsidies")
        rows = pending(subs, datetime.now(JST), accepting_only=not args.all)
        if args.limit:
            rows = rows[: args.limit]
        if args.json:
            print(json.dumps([s.code for s in rows], ensure_ascii=False))
        else:
            for s in rows:
                end = s.end.strftime("%Y-%m-%d") if s.end else "----------"
                print(f"{s.code}\t{end}\t{s.area_label()}\t{s.title}")
            print(f"合計 {len(rows)} 件")


if __name__ == "__main__":
    main()
