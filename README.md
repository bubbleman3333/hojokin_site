# 補助金ウォッチ

国・都道府県・市区町村の補助金・助成金を、デジタル庁 jGrants の公開 API から毎日取り込み、
静的サイトとして GitHub Pages に配信する。**運用費ゼロ**（API はキー不要、GitHub Actions と Pages は無料枠）。

- 公開先: https://hojokin-watch.rakunowa.workers.dev/
- 記事の解説文は Claude（Claude Code のセッション）が書く。書いていない補助金はデータから自動で組み立てた文章で埋まる。

## 仕組み

```
jGrants API ──fetch──▶ data/subsidies/<id>.json ──┐
                                                  ├─build──▶ dist/ ──▶ GitHub Pages
data/articles/<コード>.md（Claude が書く記事）────┘
```

- `hojokin/jgrants.py` 取り込み。一覧を取り、新規・変更分だけ詳細を取り直す。
- `hojokin/model.py` 生データ → `Subsidy`。金額の表記、締切の判定、HTML の掃除、都道府県・目的・業種の slug。
- `hojokin/articles.py` 記事の読み込み、記事が無いときの自動文、FAQ。
- `hojokin/build.py` Jinja2 で `dist/` を書き出す。
- `.github/workflows/daily.yml` 毎朝 6 時（JST）に fetch → データをコミット → build → Pages に配信。

## 生成されるページ

| パス | 内容 |
| --- | --- |
| `/` | トップ。締切間近・新着・上限額ランキング・全国対象・都道府県/目的/業種の入口 |
| `/s/<コード>/` | 補助金 1 件ごとの記事ページ（要点表、解説、FAQ、公式概要、関連） |
| `/search/` | 都道府県・目的・従業員規模・キーワードで絞り込む検索・診断（`search.json` を JS で読む） |
| `/accepting/` `/deadline/` `/new/` `/upcoming/` `/nationwide/` `/ranking/` `/closed/` | 各種一覧（50 件ずつページ送り） |
| `/area/<slug>/` `/purpose/<slug>/` `/industry/<slug>/` | 都道府県・目的・業種ごとの一覧 |
| `/weekly/<年-w週>/` | 週ごとの新着まとめ |
| `/calendar.ics` `/area/<slug>/calendar.ics` | 締切カレンダー（Google カレンダー等に登録できる） |
| `/feed.xml` `/sitemap.xml` `/robots.txt` | RSS・サイトマップ |

SEO 向けに、全ページに canonical・OGP・構造化データ（WebSite/SearchAction、Article、BreadcrumbList、FAQPage、CollectionPage）を出す。
終了して 1 年経ったページと `/closed/` は noindex。

## コマンド（`.venv` を使う）

```powershell
.\.venv\Scripts\python -m hojokin fetch            # jGrants から取り込む（初回は 15 分ほど）
.\.venv\Scripts\python -m hojokin build --site-url http://127.0.0.1:8000   # ローカル確認用に生成
.\.venv\Scripts\python -m http.server 8000 -d dist  # ブラウザで http://127.0.0.1:8000/
.\.venv\Scripts\python -m hojokin pending           # 記事がまだ無い補助金（締切順）
.\.venv\Scripts\python -m pytest -q
```

## 記事を足す

`data/articles/README.md` の形式で `data/articles/<コード>.md` を置く。`pending` で出たコードの元データは
`data/subsidies/<id>.json`（`name` がコード）。push すれば Actions が生成して公開する。

## 広告を貼る

`config/affiliate.json` の各枠に広告タグの HTML をそのまま貼る。空なら何も出ない。

| 枠 | 出る場所 |
| --- | --- |
| `sidebar` | 右カラムの一番上 |
| `article_top` | 個別ページの要約の下 |
| `article_bottom` | 個別ページの公式概要の下 |
| `list_bottom` | 一覧ページの下・トップの上部 |
| `head` | `<head>` 内（AdSense の自動広告、Search Console の確認タグ、解析タグ） |

## 設定

`config/site.json`。`site_url` は Pages の URL。`new_days`（新着とみなす日数）、`deadline_days`（締切間近の日数）、
`noindex_closed_after_days`（終了後これだけ経ったページは検索に載せない）。
