import json
from datetime import datetime
from pathlib import Path

from hojokin.articles import auto_article, faq_for, parse_markdown_article, pending
from hojokin.build import Builder, load_subsidies
from hojokin.model import JST, Subsidy
from test_model import raw


def make_data(tmp_path: Path) -> tuple[Path, Path]:
    data = tmp_path / "subsidies"
    data.mkdir()
    (data / "a.json").write_text(json.dumps(raw()), encoding="utf-8")
    (data / "b.json").write_text(json.dumps(raw(id="a0W2", name="S-00000002", title="終わった補助金", target_area_search="全国",
                                                acceptance_end_datetime="2025-01-01T00:00:00Z", acceptance_start_datetime="2024-12-01T00:00:00Z")), encoding="utf-8")
    (data / "c.json").write_text(json.dumps(raw(id="a0W3", name="S-00000003", title="東京の補助金", target_area_search="東京都",
                                                acceptance_end_datetime="2026-10-10T00:00:00Z")), encoding="utf-8")
    articles = tmp_path / "articles"
    articles.mkdir()
    (articles / "S-00000001.md").write_text("---\ntitle: 書いた記事のタイトル\nsummary: 要約です\n---\n## 向いている会社\n本文です。\n", encoding="utf-8")
    return data, articles


def test_build_generates_pages(tmp_path):
    data, articles = make_data(tmp_path)
    out = tmp_path / "dist"
    now = datetime(2026, 10, 1, tzinfo=JST)
    n = Builder(out, "https://example.com/site", now=now, data_dir=data, article_dir=articles).build()
    assert n == 3
    page = (out / "s/S-00000001/index.html").read_text(encoding="utf-8")
    assert "書いた記事のタイトル" in page and "本文です。" in page and "編集部の解説" in page
    assert 'href="https://example.com/site/static/style.css"' in page
    assert "300万円" in page and "あと43日" in page
    assert '"@type":"FAQPage"' in page and "締切はいつですか" in page
    auto = (out / "s/S-00000003/index.html").read_text(encoding="utf-8")
    assert "この補助金でできること" in auto  # 記事が無いので自動文
    assert "編集部の解説" not in auto
    closed = (out / "s/S-00000002/index.html").read_text(encoding="utf-8")
    assert "募集終了" in closed and 'name="robots" content="noindex"' in closed
    for path in ("area/iwate/index.html", "area/tokyo/index.html", "area/zenkoku/calendar.ics", "purpose/new-business/index.html",
                 "industry/manufacturing/index.html", "closed/index.html", "ranking/index.html", "nationwide/index.html",
                 "search/index.html", "search.json", "calendar.ics", "weekly/index.html", "weekly/2026-w37/index.html",
                 "about/index.html", "privacy/index.html", "robots.txt", ".nojekyll", "404.html", "feed.xml"):
        assert (out / path).exists(), path
    sitemap = (out / "sitemap.xml").read_text(encoding="utf-8")
    assert "https://example.com/site/s/S-00000001/" in sitemap
    assert "S-00000002" not in sitemap  # noindex はサイトマップに入れない
    assert "closed/" not in sitemap
    rows = json.loads((out / "search.json").read_text(encoding="utf-8"))
    assert {r["c"] for r in rows} == {"S-00000001", "S-00000002", "S-00000003"}
    ics = (out / "calendar.ics").read_text(encoding="utf-8")
    assert "BEGIN:VEVENT" in ics and "DTSTART;VALUE=DATE:20261113" in ics and "S-00000002" not in ics


def test_pending_lists_only_unwritten_accepting(tmp_path):
    data, articles = make_data(tmp_path)
    subs = load_subsidies(data)
    now = datetime(2026, 10, 1, tzinfo=JST)
    codes = [s.code for s in pending(subs, now, accepting_only=True, article_dir=articles)]
    assert codes == ["S-00000003"]  # 1 は記事あり、2 は終了
    codes_all = [s.code for s in pending(subs, now, accepting_only=False, article_dir=articles)]
    assert set(codes_all) == {"S-00000002", "S-00000003"}


def test_auto_article_and_faq():
    s = Subsidy.from_raw(raw())
    now = datetime(2026, 10, 1, tzinfo=JST)
    a = auto_article(s, now)
    assert not a["written"]
    assert "600万円以上の事業費" in a["body_html"]
    faq = faq_for(s, now)
    assert len(faq) == 3 and "あと43日" in faq[0][1]


def test_parse_markdown_article():
    a = parse_markdown_article("---\ntitle: T\nsummary: S\n---\n## 見出し\n\n- 一つ\n- 二つ\n")
    assert a["title"] == "T" and a["summary"] == "S" and a["written"]
    assert "<h2>見出し</h2>" in a["body_html"] and "<li>一つ</li>" in a["body_html"]
