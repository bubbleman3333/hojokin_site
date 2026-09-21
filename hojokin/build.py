"""data/ から dist/ に静的サイトを書き出す。"""
from __future__ import annotations

import json
import shutil
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

import markdown as md
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .articles import ARTICLE_DIR, article_for, faq_for
from .model import INDUSTRIES, JST, PREFECTURES, PURPOSES, Subsidy, slug_of, yen

ROOT = Path(__file__).resolve().parent.parent
PER_PAGE = 50
WEEKS_KEPT = 52


def load_subsidies(data_dir: Path) -> list[Subsidy]:
    out = []
    for path in sorted(data_dir.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("title"):
            out.append(Subsidy.from_raw(raw))
    return out


def load_config(root: Path = ROOT) -> tuple[dict, dict]:
    site = json.loads((root / "config" / "site.json").read_text(encoding="utf-8"))
    ads = json.loads((root / "config" / "affiliate.json").read_text(encoding="utf-8"))
    return site, ads


def fmt_dt(d: datetime | None, with_time: bool = True) -> str:
    if not d:
        return "記載なし"
    s = f"{d.year}年{d.month}月{d.day}日"
    return s + (f" {d.strftime('%H:%M')}" if with_time else "")


def week_key(d: datetime) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-w{w:02d}"


def ics_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


class Builder:
    def __init__(self, out_dir: Path, site_url: str, now: datetime | None = None, data_dir: Path | None = None,
                 article_dir: Path = ARTICLE_DIR, root: Path = ROOT):
        self.out = out_dir
        self.site_url = site_url.rstrip("/")
        self.now = now or datetime.now(JST)
        self.data_dir = data_dir or root / "data" / "subsidies"
        self.article_dir = article_dir
        self.root = root
        self.site, self.ads = load_config(root)
        self.env = Environment(loader=FileSystemLoader(root / "templates"), autoescape=select_autoescape(["html", "xml"]))
        self.env.filters["yen"] = yen
        self.env.filters["dt"] = fmt_dt
        self.env.filters["date"] = lambda d: fmt_dt(d, with_time=False)
        self.env.globals.update(url=self.url, site=self.site, ads=self.ads, now=self.now, PREFECTURES=PREFECTURES,
                                purpose_slug=lambda p: slug_of(PURPOSES, p), industry_slug=lambda i: slug_of(INDUSTRIES, i))
        self.sitemap: list[tuple[str, datetime | None]] = []

    # ---- 部品 ----
    def url(self, path: str = "") -> str:
        return f"{self.site_url}/{path.lstrip('/')}"

    def write(self, path: str, text: str) -> None:
        target = self.out / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def render(self, template: str, path: str, *, noindex: bool = False, lastmod: datetime | None = None, **ctx) -> None:
        canonical = self.url(path.replace("index.html", ""))
        html = self.env.get_template(template).render(canonical=canonical, noindex=noindex, **ctx)
        self.write(path, html)
        if not noindex:
            self.sitemap.append((canonical, lastmod))

    def paginate(self, template: str, base: str, items: list[Subsidy], *, title: str, description: str, noindex: bool = False, **ctx) -> None:
        pages = max(1, (len(items) + PER_PAGE - 1) // PER_PAGE)
        for i in range(pages):
            chunk = items[i * PER_PAGE:(i + 1) * PER_PAGE]
            path = f"{base}index.html" if i == 0 else f"{base}page/{i + 1}/index.html"
            self.render(template, path, noindex=noindex, title=title if i == 0 else f"{title}（{i + 1}ページ目）", description=description,
                        items=chunk, page=i + 1, pages=pages, base=base, count=len(items), **ctx)

    # ---- 本体 ----
    def build(self) -> int:
        if self.out.exists():
            shutil.rmtree(self.out)
        self.out.mkdir(parents=True)
        shutil.copytree(self.root / "static", self.out / "static")
        subs = load_subsidies(self.data_dir)
        now = self.now
        far = now + timedelta(days=36500)

        def by_deadline(lst):
            return sorted(lst, key=lambda s: s.end or far)

        accepting = by_deadline([s for s in subs if s.is_accepting(now)])
        upcoming = sorted([s for s in subs if s.is_upcoming(now)], key=lambda s: s.start)
        closed = sorted([s for s in subs if not s.is_accepting(now) and not s.is_upcoming(now)], key=lambda s: s.end or now, reverse=True)
        new = sorted([s for s in subs if s.is_new(now, self.site["new_days"])], key=lambda s: s.first_seen, reverse=True)
        deadline = [s for s in accepting if s.days_left(now) is not None and s.days_left(now) <= self.site["deadline_days"]]
        ranking = sorted([s for s in accepting if s.max_limit], key=lambda s: -s.max_limit)[:100]
        nationwide = [s for s in accepting if "全国" in s.areas]

        by_area: dict[str, list[Subsidy]] = defaultdict(list)
        by_purpose: dict[str, list[Subsidy]] = defaultdict(list)
        by_industry: dict[str, list[Subsidy]] = defaultdict(list)
        by_week: dict[str, list[Subsidy]] = defaultdict(list)
        for s in subs:
            for a in s.areas:
                by_area[a].append(s)
            for p in s.purposes:
                by_purpose[p].append(s)
            if not s.industries_all:
                for i in s.industries:
                    by_industry[i].append(s)
            if s.first_seen and (now - s.first_seen).days < WEEKS_KEPT * 7:
                by_week[week_key(s.first_seen)].append(s)

        def order(lst: list[Subsidy]) -> list[Subsidy]:
            live = by_deadline([s for s in lst if s.is_accepting(now) or s.is_upcoming(now)])
            live_ids = {id(s) for s in live}
            done = sorted([s for s in lst if id(s) not in live_ids], key=lambda s: s.end or now, reverse=True)
            return live + done

        def index_rows(table, groups):
            return [(k, slug_of(table, k), len(v), sum(1 for s in v if s.is_accepting(now))) for k, v in groups.items()]

        area_index = index_rows(PREFECTURES, by_area)
        area_index.sort(key=lambda t: list(PREFECTURES).index(t[0]) if t[0] in PREFECTURES else 99)
        purpose_index = sorted(index_rows(PURPOSES, by_purpose), key=lambda t: -t[3])
        industry_index = sorted(index_rows(INDUSTRIES, by_industry), key=lambda t: -t[3])
        weeks = sorted(by_week.keys(), reverse=True)
        week_index = [(w, len(by_week[w])) for w in weeks]
        latest_fetch = max((s.fetched_at for s in subs if s.fetched_at), default=now)
        self.env.globals.update(area_index=area_index, purpose_index=purpose_index, industry_index=industry_index, week_index=week_index[:8],
                                sidebar_deadline=deadline[:6], sidebar_ranking=ranking[:5],
                                stats=dict(total=len(subs), accepting=len(accepting), new=len(new), deadline=len(deadline),
                                           upcoming=len(upcoming), areas=len(by_area), updated=latest_fetch))

        # 個別ページ
        for s in subs:
            art = article_for(s, now, self.article_dir)
            related = [r for r in order(by_area.get(s.areas[0], [])) if r is not s and r.is_accepting(now)][:6]
            if len(related) < 6 and s.purposes:
                related += [r for r in order(by_purpose.get(s.purposes[0], [])) if r is not s and r not in related and r.is_accepting(now)][:6 - len(related)]
            closed_old = (not s.is_accepting(now) and not s.is_upcoming(now) and s.end is not None
                          and (now - s.end).days > self.site["noindex_closed_after_days"])
            self.render("subsidy.html", f"{s.path}index.html", s=s, art=art, related=related, faq=faq_for(s, now),
                        noindex=closed_old, lastmod=s.fetched_at)

        # 一覧
        self.render("index.html", "index.html", new=new[:10], deadline=deadline[:10], ranking=ranking[:10], nationwide=nationwide[:10], upcoming=upcoming[:6])
        self.paginate("list.html", "accepting/", accepting, title="募集中の補助金・助成金一覧", description=f"現在募集中の補助金・助成金 {len(accepting)} 件を締切が近い順に並べています。毎朝更新。")
        self.paginate("list.html", "deadline/", deadline, title=f"締切まで{self.site['deadline_days']}日以内の補助金", description="締切が迫っている補助金・助成金です。GビズID の取得も含めて早めに動く必要があります。")
        self.paginate("list.html", "new/", new, title="新着の補助金・助成金", description=f"直近{self.site['new_days']}日で新しく公開された補助金・助成金です。")
        self.paginate("list.html", "upcoming/", upcoming, title="これから公募が始まる補助金", description="受付開始日が未来の補助金・助成金です。準備期間があるうちに要件を確認できます。")
        self.paginate("list.html", "nationwide/", nationwide, title="全国どこからでも申請できる補助金", description="対象地域が全国の補助金・助成金です。所在地を問わず申請できます。")
        self.paginate("list.html", "ranking/", ranking, title="上限額が大きい補助金ランキング", description="募集中の補助金・助成金を上限額の大きい順に並べたランキングです。", ranked=True)
        self.paginate("list.html", "closed/", closed, title="募集が終了した補助金", description="過去に公募された補助金・助成金です。次回公募の参考にしてください。", noindex=True)
        for a, slug, _, _ in area_index:
            self.paginate("list.html", f"area/{slug}/", order(by_area[a]), title=f"{a}の補助金・助成金一覧",
                          description=f"{a}を対象地域にした補助金・助成金の一覧です。募集中のものを締切順に、その後に終了分を並べています。", kind="area", key=a, slug=slug)
            self.write(f"area/{slug}/calendar.ics", self.ics([s for s in by_area[a] if s.is_accepting(now)], f"{a}の補助金締切"))
        for p, slug, _, _ in purpose_index:
            self.paginate("list.html", f"purpose/{slug}/", order(by_purpose[p]), title=f"「{p}」向けの補助金・助成金",
                          description=f"目的が「{p}」に分類されている補助金・助成金の一覧です。", kind="purpose", key=p)
        for i, slug, _, _ in industry_index:
            self.paginate("list.html", f"industry/{slug}/", order(by_industry[i]), title=f"{i}向けの補助金・助成金",
                          description=f"対象業種に「{i}」が含まれる補助金・助成金の一覧です（業種不問のものは含みません）。", kind="industry", key=i)
        for w in weeks:
            items = sorted(by_week[w], key=lambda s: s.first_seen, reverse=True)
            y, n = w.split("-w")
            self.paginate("list.html", f"weekly/{w}/", items, title=f"{y}年 第{int(n)}週の新着補助金まとめ",
                          description=f"{y}年第{int(n)}週に新しく公開された補助金・助成金 {len(items)} 件のまとめです。")
        self.render("areas.html", "area/index.html", title="都道府県別の補助金・助成金", description="都道府県ごとの補助金・助成金の件数と一覧です。")
        self.render("categories.html", "purpose/index.html", title="目的別の補助金・助成金", description="やりたいことから探す補助金・助成金の一覧です。", rows=purpose_index, base="purpose")
        self.render("categories.html", "industry/index.html", title="業種別の補助金・助成金", description="業種から探す補助金・助成金の一覧です。", rows=industry_index, base="industry")
        self.render("weeks.html", "weekly/index.html", title="週ごとの新着補助金まとめ", description="毎週の新着補助金・助成金を週単位でまとめています。", rows=week_index)
        self.render("search.html", "search/index.html", title="補助金を探す・診断する", description="都道府県・目的・従業員規模・キーワードから、いま申請できる補助金・助成金を絞り込めます。")

        # 固定ページ
        for name in ("about", "privacy"):
            text = (self.root / "content" / f"{name}.md").read_text(encoding="utf-8")
            title = text.splitlines()[0].lstrip("# ").strip()
            body = md.markdown("\n".join(text.splitlines()[1:]))
            self.render("page.html", f"{name}/index.html", title=title, description=title, body=body)
        self.write("404.html", self.env.get_template("404.html").render(canonical=self.url("404.html"), noindex=True))

        # 機械向け
        self.write("search.json", self.search_json(subs))
        self.write("calendar.ics", self.ics(accepting, "補助金の締切（全国）"))
        self.write_sitemap()
        self.write_feed(new[:30])
        self.write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {self.url('sitemap.xml')}\n")
        self.write(".nojekyll", "")
        return len(subs)

    def search_json(self, subs: list[Subsidy]) -> str:
        rows = []
        for s in subs:
            st, _ = s.status(self.now)
            rows.append({"c": s.code, "t": s.title, "a": s.areas, "p": s.purposes, "i": [] if s.industries_all else s.industries,
                         "e": s.end.strftime("%Y-%m-%d") if s.end else None, "m": s.max_limit, "r": s.rate, "w": s.employees, "s": st})
        return json.dumps(rows, ensure_ascii=False, separators=(",", ":"))

    def ics(self, items: list[Subsidy], name: str) -> str:
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:-//{self.site['name']}//JA", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
                 f"X-WR-CALNAME:{ics_escape(name)}", "X-WR-TIMEZONE:Asia/Tokyo"]
        stamp = self.now.strftime("%Y%m%dT%H%M%SZ")
        for s in items:
            if not s.end:
                continue
            day = s.end.strftime("%Y%m%d")
            nxt = (s.end + timedelta(days=1)).strftime("%Y%m%d")
            lines += ["BEGIN:VEVENT", f"UID:{s.code}@hojokin", f"DTSTAMP:{stamp}", f"DTSTART;VALUE=DATE:{day}", f"DTEND;VALUE=DATE:{nxt}",
                      f"SUMMARY:{ics_escape('【締切】' + s.title)}",
                      f"DESCRIPTION:{ics_escape('上限 ' + yen(s.max_limit) + ' / 補助率 ' + (s.rate or '記載なし') + '\n' + self.url(s.path))}",
                      f"URL:{self.url(s.path)}", "END:VEVENT"]
        lines.append("END:VCALENDAR")
        return "\r\n".join(lines) + "\r\n"

    def write_sitemap(self) -> None:
        rows = []
        for loc, lastmod in self.sitemap:
            lm = f"<lastmod>{lastmod.strftime('%Y-%m-%d')}</lastmod>" if lastmod else ""
            rows.append(f"<url><loc>{escape(loc)}</loc>{lm}</url>")
        self.write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                   + "\n".join(rows) + "\n</urlset>\n")

    def write_feed(self, items: list[Subsidy]) -> None:
        entries = []
        for s in items:
            art = article_for(s, self.now, self.article_dir)
            pub = (s.first_seen or self.now).strftime("%a, %d %b %Y %H:%M:%S %z")
            link = escape(self.url(s.path))
            entries.append(f"<item><title>{escape(s.title)}</title><link>{link}</link><guid>{link}</guid>"
                           f"<pubDate>{pub}</pubDate><description>{escape(art['summary'])}</description></item>")
        self.write("feed.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
                   f"<title>{escape(self.site['name'])}</title><link>{escape(self.url())}</link><description>{escape(self.site['description'])}</description>\n"
                   + "\n".join(entries) + "\n</channel></rss>\n")
