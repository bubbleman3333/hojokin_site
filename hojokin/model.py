"""jGrants の生データ 1 件を、テンプレートから扱いやすい形（Subsidy）に直す。"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

JST = timezone(timedelta(hours=9))

PREFECTURES: dict[str, str] = {
    "全国": "zenkoku", "北海道": "hokkaido", "青森県": "aomori", "岩手県": "iwate", "宮城県": "miyagi",
    "秋田県": "akita", "山形県": "yamagata", "福島県": "fukushima", "茨城県": "ibaraki", "栃木県": "tochigi",
    "群馬県": "gunma", "埼玉県": "saitama", "千葉県": "chiba", "東京都": "tokyo", "神奈川県": "kanagawa",
    "新潟県": "niigata", "富山県": "toyama", "石川県": "ishikawa", "福井県": "fukui", "山梨県": "yamanashi",
    "長野県": "nagano", "岐阜県": "gifu", "静岡県": "shizuoka", "愛知県": "aichi", "三重県": "mie",
    "滋賀県": "shiga", "京都府": "kyoto", "大阪府": "osaka", "兵庫県": "hyogo", "奈良県": "nara",
    "和歌山県": "wakayama", "鳥取県": "tottori", "島根県": "shimane", "岡山県": "okayama", "広島県": "hiroshima",
    "山口県": "yamaguchi", "徳島県": "tokushima", "香川県": "kagawa", "愛媛県": "ehime", "高知県": "kochi",
    "福岡県": "fukuoka", "佐賀県": "saga", "長崎県": "nagasaki", "熊本県": "kumamoto", "大分県": "oita",
    "宮崎県": "miyazaki", "鹿児島県": "kagoshima", "沖縄県": "okinawa",
}

# jGrants の「利用目的」。表記が変わった場合はハッシュの slug に落ちるだけで壊れはしない
PURPOSES: dict[str, str] = {
    "新たな事業を行いたい": "new-business",
    "販路拡大・海外展開をしたい": "sales-expansion",
    "イベント・事業運営支援がほしい": "event-operation",
    "事業を引き継ぎたい": "succession",
    "研究開発・実証事業を行いたい": "research",
    "人材育成を行いたい": "training",
    "資金繰りを改善したい": "cashflow",
    "設備整備・IT導入をしたい": "equipment-it",
    "雇用・職場環境を改善したい": "employment",
    "エコ・SDGs活動支援がほしい": "eco-sdgs",
    "災害（自然災害、感染症等）支援がほしい": "disaster",
    "教育・子育て・少子化支援がほしい": "education-childcare",
    "スポーツ・文化支援がほしい": "sports-culture",
    "安全・防災対策支援がほしい": "safety",
    "まちづくり・地域振興支援がほしい": "community",
    "海外展開をしたい": "overseas",
    "生産性を向上させたい": "productivity",
}

INDUSTRIES: dict[str, str] = {
    "農業、林業": "agriculture", "漁業": "fishery", "鉱業、採石業、砂利採取業": "mining", "建設業": "construction",
    "製造業": "manufacturing", "電気・ガス・熱供給・水道業": "utility", "情報通信業": "it", "運輸業、郵便業": "transport",
    "卸売業、小売業": "retail", "金融業、保険業": "finance", "不動産業、物品賃貸業": "realestate",
    "学術研究、専門・技術サービス業": "professional", "宿泊業、飲食サービス業": "hospitality",
    "生活関連サービス業、娯楽業": "lifestyle", "教育、学習支援業": "education", "医療、福祉": "medical",
    "複合サービス事業": "compound", "サービス業（他に分類されないもの）": "services",
    "公務（他に分類されるものを除く）": "public", "分類不能の産業": "other",
}
ALL_INDUSTRY_THRESHOLD = 18  # これ以上の業種が並んでいたら「業種不問」とみなす

# jGrants の対象地域には「東北地方」のような地方名も混ざるので、都道府県に展開する
REGIONS: dict[str, list[str]] = {
    "北海道地方": ["北海道"],
    "東北地方": ["青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県"],
    "関東・甲信越地方": ["茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県", "新潟県", "山梨県", "長野県"],
    "関東地方": ["茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県"],
    "東海・北陸地方": ["富山県", "石川県", "福井県", "岐阜県", "静岡県", "愛知県", "三重県"],
    "北陸地方": ["富山県", "石川県", "福井県"],
    "東海地方": ["岐阜県", "静岡県", "愛知県", "三重県"],
    "近畿地方": ["滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県"],
    "中国地方": ["鳥取県", "島根県", "岡山県", "広島県", "山口県"],
    "四国地方": ["徳島県", "香川県", "愛媛県", "高知県"],
    "九州・沖縄地方": ["福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県"],
    "九州地方": ["福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県"],
}


def slug_of(table: dict[str, str], name: str) -> str:
    if name in table:
        return table[name]
    return "x" + hashlib.md5(name.encode("utf-8")).hexdigest()[:8]


def parse_dt(value: str | None) -> datetime | None:
    """'2026-11-13T07:00:00Z' → JST の aware datetime。"""
    if not value:
        return None
    v = value.rstrip("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(v, fmt).replace(tzinfo=timezone.utc).astimezone(JST)
        except ValueError:
            continue
    return None


def yen(n: int | None) -> str:
    """3000000 → '300万円'、500000000 → '5億円'、0/None → '記載なし'。"""
    if not n:
        return "記載なし"
    oku, rest = divmod(int(n), 10**8)
    man, en = divmod(rest, 10**4)
    parts = []
    if oku:
        parts.append(f"{oku:,}億")
    if man:
        parts.append(f"{man:,}万")
    if en:
        parts.append(f"{en:,}")
    return "".join(parts) + "円"


def rate_fraction(rate: str | None) -> float | None:
    """'1/2' → 0.5、'2/3以内' → 0.667、'50%' → 0.5。読めなければ None。"""
    if not rate:
        return None
    m = re.search(r"(\d+)\s*/\s*(\d+)", rate)
    if m and int(m.group(2)):
        return int(m.group(1)) / int(m.group(2))
    m = re.search(r"(\d+(?:\.\d+)?)\s*[%％]", rate)
    if m:
        return float(m.group(1)) / 100
    return None


ALLOWED_TAGS = {"p", "br", "strong", "b", "em", "ul", "ol", "li", "table", "thead", "tbody", "tr", "td", "th", "h3", "h4", "a"}


def clean_html(html: str | None) -> str:
    """jGrants の概要 HTML から style や span を落とし、見出し・段落・表だけ残す。"""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style", "iframe"]):
        tag.decompose()
    for tag in soup.find_all(True):
        if tag.name in ("h1", "h2"):
            tag.name = "h3"
        if tag.name not in ALLOWED_TAGS:
            tag.unwrap()
            continue
        href = tag.get("href") if tag.name == "a" else None
        tag.attrs = {}
        if href and href.startswith("http"):
            tag.attrs = {"href": href, "rel": "nofollow noopener", "target": "_blank"}
    out = str(soup)
    out = re.sub(r"(<p>\s*(<br/?>)?\s*</p>\s*){2,}", "<p><br/></p>", out)
    return out.strip()


def html_to_text(html: str | None) -> str:
    if not html:
        return ""
    text = BeautifulSoup(html, "html.parser").get_text("\n")
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def _split_slash(value: str | None) -> list[str]:
    """'製造業 / 情報通信業' も '新潟県/富山県/石川県' も切る。業種名の中にある「、」では切らない。
    順序を保ったまま重複を除く（'全国/北海道/…/沖縄県' のような指定は全国扱いにする）。"""
    seen: list[str] = []
    for v in re.split(r"\s*/\s*", value or ""):
        v = v.strip()
        for w in REGIONS.get(v, [v]):
            if w and w not in seen:
                seen.append(w)
    if "全国" in seen:
        return ["全国"]
    return seen


@dataclass
class Subsidy:
    id: str
    code: str
    title: str
    catch: str
    detail_html: str
    detail_text: str
    purposes: list[str]
    industries: list[str]
    industries_all: bool
    areas: list[str]
    area_detail: str
    employees: str
    rate: str
    max_limit: int
    start: datetime | None
    end: datetime | None
    project_end: datetime | None
    url: str
    institution: str
    electronic: bool
    multiple: bool
    first_seen: datetime | None
    fetched_at: datetime | None

    @classmethod
    def from_raw(cls, raw: dict) -> "Subsidy":
        meta = raw.get("_meta", {})
        industries = _split_slash(raw.get("industry"))
        return cls(
            id=raw["id"],
            code=raw.get("name") or raw["id"],
            title=(raw.get("title") or "").strip(),
            catch=(raw.get("subsidy_catch_phrase") or "").strip(),
            detail_html=clean_html(raw.get("detail")),
            detail_text=html_to_text(raw.get("detail")),
            purposes=_split_slash(raw.get("use_purpose")),
            industries=industries,
            industries_all=len(industries) >= ALL_INDUSTRY_THRESHOLD or not industries,
            areas=_split_slash(raw.get("target_area_search")) or ["全国"],
            area_detail=(raw.get("target_area_detail") or "").strip(),
            employees=(raw.get("target_number_of_employees") or "").strip(),
            rate=(raw.get("subsidy_rate") or "").strip(),
            max_limit=int(raw.get("subsidy_max_limit") or 0),
            start=parse_dt(raw.get("acceptance_start_datetime")),
            end=parse_dt(raw.get("acceptance_end_datetime")),
            project_end=parse_dt(raw.get("project_end_deadline")),
            url=raw.get("front_subsidy_detail_page_url") or f"https://www.jgrants-portal.go.jp/subsidy/{raw['id']}",
            institution=(raw.get("institution_name") or "").strip(),
            electronic=(raw.get("request_reception_presence") or "") == "有",
            multiple=bool(raw.get("is_enable_multiple_request")),
            first_seen=parse_dt(meta.get("first_seen")),
            fetched_at=parse_dt(meta.get("fetched_at")),
        )

    @property
    def path(self) -> str:
        return f"s/{self.code}/"

    def is_upcoming(self, now: datetime) -> bool:
        return bool(self.start and self.start > now)

    def is_accepting(self, now: datetime) -> bool:
        if self.is_upcoming(now):
            return False
        return self.end is None or self.end >= now

    def days_left(self, now: datetime) -> int | None:
        if self.end is None:
            return None
        return (self.end.date() - now.date()).days

    def status(self, now: datetime) -> tuple[str, str]:
        """('accepting'|'upcoming'|'closed', 表示ラベル)"""
        if self.is_upcoming(now):
            return "upcoming", "公募予定"
        if self.is_accepting(now):
            left = self.days_left(now)
            if left is not None and left <= 7:
                return "accepting", "まもなく締切"
            return "accepting", "募集中"
        return "closed", "募集終了"

    def is_new(self, now: datetime, days: int) -> bool:
        return bool(self.first_seen and (now - self.first_seen).days < days)

    def area_label(self) -> str:
        return "・".join(self.areas)

    def area_slug(self) -> str:
        return slug_of(PREFECTURES, self.areas[0])
