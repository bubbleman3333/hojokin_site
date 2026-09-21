from datetime import datetime

from hojokin.jgrants import norm_dt
from hojokin.model import JST, Subsidy, clean_html, rate_fraction, yen


def test_yen():
    assert yen(0) == "記載なし"
    assert yen(None) == "記載なし"
    assert yen(3000000) == "300万円"
    assert yen(500000000) == "5億円"
    assert yen(150000000) == "1億5,000万円"
    assert yen(12345) == "1万2,345円"


def test_rate_fraction():
    assert rate_fraction("1/2") == 0.5
    assert abs(rate_fraction("2/3以内") - 2 / 3) < 1e-9
    assert rate_fraction("50%") == 0.5
    assert rate_fraction("定額") is None
    assert rate_fraction(None) is None


def test_norm_dt_two_formats():
    assert norm_dt("2026-10-30T14:59:00.000Z") == "2026-10-30T14:59:00Z"
    assert norm_dt("2026-11-13T07:00Z") == "2026-11-13T07:00:00Z"
    assert norm_dt(None) is None


def test_clean_html_strips_style_keeps_structure():
    html = '<p><strong style="color: rgb(0,0,0);">■目的</strong></p><p><span style="font-size:13px">本文</span></p><h2>見出し</h2><script>x</script>'
    out = clean_html(html)
    assert "style=" not in out
    assert "<span" not in out
    assert "<strong>■目的</strong>" in out
    assert "<h3>見出し</h3>" in out
    assert "script" not in out


def raw(**over):
    base = {
        "id": "a0W1", "name": "S-00000001", "title": "テスト補助金", "subsidy_catch_phrase": "キャッチ",
        "detail": "<p>概要</p>", "use_purpose": "新たな事業を行いたい / 販路拡大・海外展開をしたい",
        "industry": "製造業 / 情報通信業", "target_area_search": "岩手県", "target_area_detail": None,
        "target_number_of_employees": "300名以下", "subsidy_rate": "1/2", "subsidy_max_limit": 3000000,
        "acceptance_start_datetime": "2026-09-08T01:00:00Z", "acceptance_end_datetime": "2026-11-13T07:00:00Z",
        "project_end_deadline": None, "request_reception_presence": "有", "is_enable_multiple_request": False,
        "front_subsidy_detail_page_url": "https://www.jgrants-portal.go.jp/subsidy/a0W1", "institution_name": "",
        "_meta": {"first_seen": "2026-09-10T00:00:00Z", "fetched_at": "2026-09-20T00:00:00Z"},
    }
    base.update(over)
    return base


def test_subsidy_status_and_days_left():
    s = Subsidy.from_raw(raw())
    now = datetime(2026, 10, 1, tzinfo=JST)
    assert s.is_accepting(now)
    assert s.status(now) == ("accepting", "募集中")
    assert s.days_left(now) == 43
    assert s.status(datetime(2026, 11, 10, tzinfo=JST)) == ("accepting", "まもなく締切")
    assert s.status(datetime(2026, 12, 1, tzinfo=JST)) == ("closed", "募集終了")
    assert s.status(datetime(2026, 9, 1, tzinfo=JST)) == ("upcoming", "公募予定")
    assert s.path == "s/S-00000001/"
    assert s.area_slug() == "iwate"
    assert s.purposes == ["新たな事業を行いたい", "販路拡大・海外展開をしたい"]
    assert s.industries == ["製造業", "情報通信業"] and not s.industries_all
    assert s.is_new(datetime(2026, 9, 20, tzinfo=JST), 14)
    assert not s.is_new(datetime(2026, 10, 20, tzinfo=JST), 14)


def test_all_industries_means_unrestricted():
    industries = " / ".join(f"業種{i}" for i in range(20))
    s = Subsidy.from_raw(raw(industry=industries))
    assert s.industries_all
