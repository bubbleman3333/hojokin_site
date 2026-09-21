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
from .model import JST, yen


def digest(s) -> str:
    """1 件分を記事執筆用の短いテキストにする。"""
    def d(x):
        return x.strftime("%Y-%m-%d") if x else "-"
    return "\n".join([
        f"=== {s.code}",
        f"title: {s.title}",
        f"catch: {s.catch}",
        f"area: {s.area_label()}" + (f"（{s.area_detail}）" if s.area_detail else ""),
        f"employees: {s.employees}",
        f"purposes: {' / '.join(s.purposes)}",
        f"industries: {'指定なし' if s.industries_all else ' / '.join(s.industries)}",
        f"rate: {s.rate or '-'}   max: {yen(s.max_limit)}",
        f"start: {d(s.start)}   end: {d(s.end)}   project_end: {d(s.project_end)}",
        f"electronic: {'有' if s.electronic else '-'}   multiple: {'yes' if s.multiple else 'no'}   institution: {s.institution or '-'}",
        "detail:",
        s.detail_text[:1800],
        "",
    ])


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
    d = sub.add_parser("digest", help="記事を書くための要約テキストを出す（Claude が読む用）")
    d.add_argument("codes", nargs="*", help="補助金コード。省略すると pending の先頭から")
    d.add_argument("--limit", type=int, default=40)
    d.add_argument("--offset", type=int, default=0)
    d.add_argument("--out", default=None, help="書き出すファイル（省略時は標準出力）")
    args = p.parse_args(argv)

    if args.cmd == "digest":
        subs = load_subsidies(ROOT / "data" / "subsidies")
        now = datetime.now(JST)
        if args.codes:
            by_code = {s.code: s for s in subs}
            rows = [by_code[c] for c in args.codes if c in by_code]
        else:
            rows = pending(subs, now)[args.offset: args.offset + args.limit]
        text = "\n".join(digest(s) for s in rows)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"{len(rows)} 件を {args.out} に書いた")
        else:
            print(text)
        return

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
