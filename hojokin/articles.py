"""記事本文の取り出し。

data/articles/<コード>.md に人（Claude）が書いた記事があればそれを使い、無ければデータから自動で組み立てる。
どちらも {"title", "summary", "body_html", "written"} の形で返す。
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import markdown

from .model import Subsidy, rate_fraction, yen

ARTICLE_DIR = Path("data/articles")


def parse_markdown_article(text: str) -> dict:
    """先頭の '---' で囲んだ frontmatter（title / summary）と Markdown 本文に分ける。"""
    meta: dict[str, str] = {}
    body = text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip().strip('"')
        body = text[m.end():]
    html = markdown.markdown(body, extensions=["tables", "sane_lists"])
    return {"title": meta.get("title", ""), "summary": meta.get("summary", ""), "body_html": html, "written": True}


def load_article(code: str, article_dir: Path = ARTICLE_DIR) -> dict | None:
    path = article_dir / f"{code}.md"
    if not path.exists():
        return None
    return parse_markdown_article(path.read_text(encoding="utf-8"))


def fmt_date(d: datetime | None) -> str:
    return f"{d.year}年{d.month}月{d.day}日" if d else "記載なし"


def example_cost(s: Subsidy) -> str | None:
    """補助率と上限から「満額もらうのに必要な事業費」を出す。"""
    frac = rate_fraction(s.rate)
    if not frac or not s.max_limit or frac >= 1:
        return None
    need = int(s.max_limit / frac)
    need = (need // 10000) * 10000 if need >= 10000 else need
    return f"補助率が{s.rate}なので、上限の{yen(s.max_limit)}を満額受け取るには、おおよそ{yen(need)}以上の事業費が必要になります。"


def auto_summary(s: Subsidy) -> str:
    return (f"{s.area_label()}を対象にした「{s.title}」の概要です。上限額は{yen(s.max_limit)}、"
            f"補助率は{s.rate or '記載なし'}。締切は{fmt_date(s.end)}です。")


def auto_article(s: Subsidy, now: datetime) -> dict:
    """人が書いた記事が無いときの穴埋め。データから読める範囲のことだけを、断定せずに書く。"""
    area = s.area_label()
    who = s.employees or "従業員数の制約なし"
    purposes = "、".join(s.purposes) if s.purposes else "事業者の支援"

    parts: list[str] = []
    parts.append("<h2>この補助金でできること</h2>")
    lead = s.catch or s.title
    parts.append(f"<p>「{lead}」は、{area}の事業者向けに用意された制度で、目的の分類は「{purposes}」です。")
    if s.institution:
        parts.append(f"制度の名称は「{s.institution}」で、")
    parts.append(f"対象となる従業員規模は「{who}」とされています。</p>")
    if s.detail_text:
        head = s.detail_text.replace("\n", " ")[:220]
        parts.append(f"<p>公式の案内では「{head}…」と説明されています。詳しい条件は下の公式概要と、リンク先の公募要領で確認してください。</p>")

    parts.append("<h2>対象になる事業者</h2><ul>")
    parts.append(f"<li>地域: {area}{('（' + s.area_detail + '）') if s.area_detail else ''}</li>")
    parts.append(f"<li>従業員規模: {who}</li>")
    if s.industries_all:
        parts.append("<li>業種: 指定なし（ほぼすべての業種が対象）</li>")
    else:
        parts.append(f"<li>業種: {'、'.join(s.industries)}</li>")
    parts.append("</ul>")

    parts.append("<h2>もらえる金額の目安</h2>")
    parts.append(f"<p>上限額は<strong>{yen(s.max_limit)}</strong>、補助率は<strong>{s.rate or '記載なし'}</strong>です。")
    ex = example_cost(s)
    if ex:
        parts.append(ex)
    parts.append("補助金は原則として後払いなので、いったん自社で費用を立て替える必要があります。</p>")

    parts.append("<h2>締切とスケジュール</h2><ul>")
    parts.append(f"<li>受付開始: {fmt_date(s.start)}</li>")
    parts.append(f"<li>受付締切: {fmt_date(s.end)}</li>")
    if s.project_end:
        parts.append(f"<li>事業の完了期限: {fmt_date(s.project_end)}</li>")
    parts.append("</ul>")
    left = s.days_left(now)
    if s.is_accepting(now) and left is not None:
        if left <= 7:
            parts.append(f"<p>締切まで<strong>あと{left}日</strong>です。GビズID の取得には数週間かかることがあるので、まだ持っていない場合は間に合わない可能性があります。</p>")
        else:
            parts.append(f"<p>締切まであと{left}日あります。申請には GビズID（プライム）が必要なことが多いので、未取得なら先に申請しておくのが安全です。</p>")
    elif s.is_upcoming(now):
        parts.append("<p>まだ受付は始まっていません。公募要領が出たら、要件を早めに確認しておくと準備が楽になります。</p>")
    else:
        parts.append("<p>この回の受付は終わっています。同じ制度が次年度や次回公募で再度出ることが多いので、参考として残しています。</p>")

    parts.append("<h2>申請のポイント</h2><ul>")
    parts.append("<li>電子申請（jGrants）" + ("に対応しています。" if s.electronic else "の記載はありません。公式ページで申請方法を確認してください。") + "</li>")
    if s.multiple:
        parts.append("<li>複数回の申請ができる制度です。</li>")
    parts.append("<li>金額・要件は変更されることがあります。必ず公式ページの最新の公募要領で確認してください。</li></ul>")
    return {"title": s.title, "summary": auto_summary(s), "body_html": "\n".join(parts), "written": False}


def article_for(s: Subsidy, now: datetime, article_dir: Path = ARTICLE_DIR) -> dict:
    a = load_article(s.code, article_dir)
    if a is None:
        return auto_article(s, now)
    if not a["title"]:
        a["title"] = s.title
    if not a["summary"]:
        a["summary"] = auto_summary(s)
    return a


def faq_for(s: Subsidy, now: datetime) -> list[tuple[str, str]]:
    """データから確実に答えられる Q&A だけ。構造化データ（FAQPage）と本文の両方に使う。"""
    qa: list[tuple[str, str]] = []
    if s.end:
        left = s.days_left(now)
        tail = f"（本日から数えてあと{left}日）" if s.is_accepting(now) and left is not None else ""
        qa.append((f"{s.title}の締切はいつですか？", f"受付締切は{fmt_date(s.end)} {s.end.strftime('%H:%M')}です{tail}。受付開始は{fmt_date(s.start)}です。"))
    qa.append((f"{s.title}の上限額と補助率は？", f"上限額は{yen(s.max_limit)}、補助率は{s.rate or '公式ページに記載'}です。" + (example_cost(s) or "")))
    who = s.employees or "従業員数の制約なし"
    ind = "業種の指定はありません" if s.industries_all else "対象業種は" + "、".join(s.industries) + "です"
    qa.append((f"{s.title}は誰が申請できますか？", f"対象地域は{s.area_label()}、従業員規模は「{who}」です。{ind}。"))
    return qa


def pending(subsidies: list[Subsidy], now: datetime, accepting_only: bool = True, article_dir: Path = ARTICLE_DIR) -> list[Subsidy]:
    """記事がまだ書かれていない補助金。募集中のものを締切が近い順に返す。"""
    out = [s for s in subsidies if not (article_dir / f"{s.code}.md").exists()]
    if accepting_only:
        out = [s for s in out if s.is_accepting(now) or s.is_upcoming(now)]
    far = datetime.max.replace(tzinfo=now.tzinfo)
    out.sort(key=lambda s: (s.end or far))
    return out
