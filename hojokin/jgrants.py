"""jGrants（デジタル庁）の公開 API から補助金データを取ってきて data/subsidies/ に貯める。

API はキー不要。一覧はキーワード必須なので、ほぼ全件に当たる語を何個か投げて和集合を取る。
一覧に無い項目（概要・業種・補助率など）は詳細 API で取る。詳細は新規か変更があったものだけ取り直す。
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

API = "https://api.jgrants-portal.go.jp/exp/v1/public/subsidies"
# この 5 語で jGrants 上のほぼ全件が拾える（タイトルに含まれない補助金はごく稀）
KEYWORDS = ["補助", "助成", "支援", "事業", "金"]
DATA_DIR = Path("data/subsidies")
# 一覧と詳細でこの項目が違えば「変更あり」とみなして詳細を取り直す
CHANGE_KEYS = ("title", "acceptance_start_datetime", "acceptance_end_datetime", "subsidy_max_limit")


def norm_dt(value: str | None) -> str | None:
    """API の日時は '2026-10-30T14:59:00.000Z' と '2026-11-13T07:00Z' の 2 種類が混ざるので揃える。"""
    if not value:
        return None
    v = value.rstrip("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(v, fmt).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    return value


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = "hojokin-watch/1.0 (static site generator)"
    return s


def _get(session: requests.Session, url: str, params: dict | None = None, tries: int = 3) -> dict:
    last: Exception | None = None
    for i in range(tries):
        try:
            r = session.get(url, params=params, timeout=60)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001 - ネットワーク系は何でも再試行
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"jGrants API に失敗: {url} {params}: {last}")


def list_subsidies(session: requests.Session, keyword: str, acceptance: int) -> list[dict]:
    data = _get(session, API, {"keyword": keyword, "sort": "created_date", "order": "DESC", "acceptance": acceptance})
    return data.get("result", [])


def fetch_detail(session: requests.Session, subsidy_id: str) -> dict | None:
    data = _get(session, f"{API}/id/{subsidy_id}")
    result = data.get("result") or []
    return result[0] if result else None


def sync(data_dir: Path = DATA_DIR, keywords=KEYWORDS, sleep: float = 0.3, limit: int | None = None, log=print) -> tuple[int, int]:
    """一覧を取り、新規・変更のあった補助金だけ詳細を取り直して保存する。戻り値は (新規件数, 更新件数)。"""
    data_dir.mkdir(parents=True, exist_ok=True)
    session = _session()
    seen: dict[str, dict] = {}
    for kw in keywords:
        for acceptance in (1, 0):
            for row in list_subsidies(session, kw, acceptance):
                seen[row["id"]] = row
    log(f"一覧: {len(seen)} 件")

    todo: list[tuple[str, dict | None]] = []
    for sid, row in seen.items():
        path = data_dir / f"{sid}.json"
        if not path.exists():
            todo.append((sid, None))
            continue
        old = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for key in CHANGE_KEYS:
            a, b = old.get(key), row.get(key)
            if key.endswith("datetime"):
                a, b = norm_dt(a), norm_dt(b)
            if a != b:
                changed = True
        if changed:
            todo.append((sid, old))
    if limit is not None:
        todo = todo[:limit]
    log(f"詳細を取る: {len(todo)} 件")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new = updated = 0
    for i, (sid, old) in enumerate(todo, 1):
        detail = fetch_detail(session, sid)
        if detail is None:
            continue
        for key in ("acceptance_start_datetime", "acceptance_end_datetime", "project_end_deadline"):
            detail[key] = norm_dt(detail.get(key))
        # 一覧にしか無い項目は一覧から補う
        for key in ("target_area_search", "target_number_of_employees"):
            if not detail.get(key):
                detail[key] = seen[sid].get(key)
        # 初めて見た日時。初回の一括取り込みで全部が「新着」にならないよう、受付開始が過去ならそれを使う
        first_seen = (old or {}).get("_meta", {}).get("first_seen")
        if not first_seen:
            start = detail.get("acceptance_start_datetime")
            first_seen = start if start and start < now else now
        detail["_meta"] = {"first_seen": first_seen, "fetched_at": now}
        (data_dir / f"{sid}.json").write_text(json.dumps(detail, ensure_ascii=False, indent=1), encoding="utf-8")
        if old is None:
            new += 1
        else:
            updated += 1
        if i % 50 == 0:
            log(f"  {i}/{len(todo)}")
        time.sleep(sleep)
    log(f"新規 {new} 件、更新 {updated} 件")
    return new, updated
