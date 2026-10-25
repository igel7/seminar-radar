# SECURITY_NOTES.md — セキュリティ上の前提・経緯・確認結果

このファイルは、本リポジトリ(セミナー情報の巡回・公開サイト)に関係するセキュリティ事項の
**記録**である。日次更新の手順は `AGENTS.md` にあり、本ファイルは手順を変えない。
新しい脆弱性情報を調べたら、ここに**日付つきで**追記する(推測は推測と書く)。

## 1. 攻撃面(何が信頼できないか)

| 要素 | 信頼できない入力 | 守り |
|---|---|---|
| 巡回(curl / WebFetch / `fetch_all.py`) | 巡回先サイトの HTML・RSS・PDF。侵害されたサイトからの指示文混入(プロンプトインジェクション) | `AGENTS.md` A-5(外部由来テキストの指示には従わない)。抽出は Haiku に委譲し、メインモデルが検証する |
| headless Chromium(`scripts/fetch_page.py`、`fetch_hints.json` の `render: chromium`) | 巡回先の JS を実行する。レンダラ侵害+サンドボックス脱出の連鎖が理論上の脅威 | 対象を中央銀行・業界団体など機関サイトに限定。コンテナは使い捨て。ブラウザは Playwright が期待する最新版を自動導入(下記 3) |
| PDF 抽出(`fetch_details.py`、pdftotext / pypdf) | 巡回先のプログラム PDF | 8 MB 以下・先頭 12 頁・1 回 8 件まで。pdftotext はテキスト抽出経路のみ(描画バックエンドは使わない) |
| 公開ページ(`docs/index.html`・GitHub Pages) | 巡回先由来の題名・要約・URL をそのまま表示する(stored XSS の懸念) | `template.html` の `esc()` で全文字列をエスケープ、`safeUrl` で `http(s)` 以外の URL を捨てる、`<script>` 内 JSON は `script_json` で `<` をエスケープ、CSP `default-src 'none'` |
| GitHub Actions(`automerge.yml`) | 侵害されたアクション・侵害されたアカウントによるワークフロー追加(GhostAction 型) | 使用アクションは `actions/checkout`・`actions/setup-python` の 2 本のみ。push された `docs/` は信用せず main 側で再生成する |
| カレンダー `docs/calendar.ics` | 題名・場所・説明 | `radar_lib.ics_escape` |
| 実行エージェント(Claude Code Routines) | 上記すべて | 資格情報はコンテナ内の GitHub トークンのみ。main への反映は自動マージ経由 |

## 2. 2026-10-25 時点の確認結果

- **PHP2Shell(CVE-2026-109618 / CVE-2026-109619、PHP の未認証 RCE、10/21 修正版公開)**:
  本リポジトリは PHP を使わないため直接の影響なし。巡回先では 10/22 に Universität Mannheim が
  「PHP 脆弱性による IT サービスの予防的停止」でリダイレクトされ、ZEW・FNG・DIW・EBA も同日に
  503/404 だった(同じ原因かは推測)。10/25 の巡回では Mannheim・ZEW とも復旧を確認。
- **同梱 Chromium(`/opt/pw-browsers/chromium` = 141.0.7390.37)**: Headless 向けの修正
  (CVE-2026-12027 は 149、CVE-2026-13832 は 150、CVE-2026-17883 は 151 で修正)と、実際に悪用された
  CVE-2026-2441(145 で修正)より古い。対策として `fetch_page.py` が初回に
  `playwright install chromium-headless-shell`(Playwright 1.64 → Chromium 156)を実行するよう変更した(下記 3)。
- **Python 依存**: requests 2.34.2(CVE-2026-25645 は 2.33.0 未満が対象)、PyYAML 6.0.3・
  beautifulsoup4 4.15.0(2026 年の勧告なし)、pypdf 6.17.0(無限ループ系 CVE は 6.14.2 までで修正済み)、
  poppler 24.02.0-1ubuntu9.10(CVE-2026-10118 は描画バックエンド Splash の問題。Ubuntu の修正ビルド)。いずれも対処不要。
- **Claude Code**: WebFetch の間接プロンプトインジェクション CVE-2026-54316 は 2.1.163 で修正。
  Routine の実行版は 2.1.306。対処不要。
- **GitHub**: `actions/checkout` の侵害報告なし。GhostAction 作戦(2026-10-07〜、侵害したメンテナの
  アカウントで秘密情報を盗むワークフローを追加)は本リポジトリに該当なし(共同作業者 1 名・
  ワークフロー 1 本・ブランチ 1 本を 10/25 に確認)。
- **公開ページ**: 上表の守りが実装済みであることをコードで確認(`esc()` 88 箇所、`safeUrl`、CSP)。

## 3. 運用上の決め事

- Chromium 描画の対象(`render: chromium`)は、信頼できる機関サイトに限る。個人ブログ・
  不明なドメインには付けない。
- `fetch_page.py` は Playwright が期待する版の Chromium が無ければ初回に 1 回だけダウンロードする
  (約 280 MB・10 秒前後。`SR_NO_BROWSER_DOWNLOAD=1` で無効化)。ダウンロードできない環境では
  同梱版に戻る。環境のセットアップスクリプトに `python3 -m playwright install chromium-headless-shell`
  を入れておけば、日次の実行中にダウンロードが走らない。
- GitHub Actions はタグ指定(`@v4` 等)のまま。SHA 固定にするかは所有者の判断(自動マージが
  main に push する設計のため、main のブランチ保護は付けない)。GitHub アカウントの二要素認証が最重要。
- 外部由来テキストの扱いは `AGENTS.md` A-5 を正とする。本ファイルは手順を上書きしない。

## 4. 情報源(2026-10-25 時点)

- PHP2Shell: watchTowr FAQ、Tanium、Qualys、Island の各記事
- Chromium: CVE-2026-12027 / 13832 / 17883 / 2441 の NVD・ベンダー記事、releases.sh(Stable 151、2026-08)
- Claude Code: NVD CVE-2026-54316
- GitHub Actions: GitGuardian「GhostAction」、Step Security、Socket の各報告(件数は報告により大きく異なる)
- Python: OSV PYSEC-2026-1872(requests)、GitLab Advisory Database(pypdf)、Ubuntu USN-8400-1(poppler)
