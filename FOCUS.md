# FOCUS.md — 今回限りの重点調査指示(実行後にこのファイルを削除すること)

通常の更新に加えて、以下を優先的に実施せよ。

## 目的

次の8ソースは現在イベント一覧に到達できていない。それぞれの
「正しいイベント一覧ページURL」を重点調査する。

1. **JS描画系(必ず `python3 scripts/fetch_page.py <URL>` を使う。候補URLの確認にも使ってよい)**
   - IMFS Frankfurt
   - CFS – Center for Financial Studies
   - HNB – Croatian National Bank
   - MNB – Magyar Nemzeti Bank
2. **URL構造不明系(sitemap.xml、トップページのナビ、web検索 `site:` 指定、現地語ページを使って一覧ページを探す)**
   - NBR – National Bank of Romania(BEARSセミナー。例: `site:bnr.ro BEARS`)
   - SWP – Stiftung Wissenschaft und Politik
   - BNB – Bulgarian National Bank
3. **ECB Calls for Papers** — 旧一覧(/press/calls/)は廃止された模様。後継の一覧ページ(research portal 等)を探す。

## ルール

- 発見した正URLは、必ず `data/status.json` の該当ソースの `error` 欄に
  `代替URL: <URL>` の形式で記録する(発見できなければ「一覧ページ発見できず: 試行内容」を記録)。
- `sources.yaml` 自体は書き換えない(従来どおり)。
- 発見したページからのイベント抽出も通常どおり行う。
- Cloudflare/ボット防御系(NBP、リトアニア中銀、アルバニア中銀、SUERF)は
  今回は深追いしなくてよい(通常の1回試行のみ)。
- この重点調査に検索回数を優先配分してよい(discovery検索は最小限で可)。
