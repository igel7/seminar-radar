# AGENTS.md — 日次更新の作業指示書

あなた(Claude Code)は毎日1回このリポジトリ上で実行され、ドイツ国内の
経済・金融セミナー情報を収集してカレンダーページを更新する。
以下の手順を上から順に、省略せずに実行すること。

## 手順

### 1. 設定を読む
`sources.yaml` を読み、`sources`(定点観測リスト)と `discovery_topics` を把握する。

### 2. 定点観測リストの巡回
`sources` の各URLについて、WebFetchツール(使えない場合は `curl -sL`)で
ページを取得し、後述のスキーマとルールに従って今後のイベントを抽出する。
ソースごとの成否を記録しておく(手順5で使う)。
1つのソースが取得失敗しても止まらず、次のソースへ進むこと。

### 3. web検索による発見
WebSearchツールで、`discovery_topics` の各観点について検索する
(英語とドイツ語のクエリを両方使う。合計8回程度まで)。
定点リストに載っていない新規イベントで、開催日・場所が検索結果から
確認できたものだけを同じスキーマで抽出する。

### 4. 抽出結果の書き出し
- 手順2と3で抽出した全イベントを1つのJSON配列にまとめ、
  `data/new_events.json` に書き込む(既存の `data/events.json` は編集しない。
  重複排除はスクリプトが行うので、重複を気にする必要はない)。
- 巡回ステータスを `data/status.json` に書き込む。形式:
  `[{"name": ソース名, "url": URL, "ok": true/false, "found": 件数, "error": 失敗理由(失敗時のみ)}]`
  web検索の分も `{"name": "web検索(discovery)", "url": "", ...}` として1行入れる。

### 5. 取り込みと再生成
```
python3 scripts/ingest.py
```
を実行する(標準ライブラリのみで動く)。エラーが出たら原因を修正して再実行。
`docs/index.html` が更新されたことを確認する。

### 6. コミットとプッシュ
変更された `data/` と `docs/` をコミットし、実行環境が指定するブランチ(`claude/...`)にプッシュする。
コミットメッセージ: `daily update YYYY-MM-DD`
プルリクエストは作らない。mainへの反映はGitHub Actionsの自動マージが行うので、mainに直接プッシュできなくてよい。

## イベントのスキーマ

各イベントは次のキーを持つJSONオブジェクト:

| キー | 内容 |
|---|---|
| `title` | 原文タイトル(英語/ドイツ語のまま。翻訳しない) |
| `title_ja` | 日本語の短い訳題(30字以内) |
| `organizer` | 主催者名(原文) |
| `date_start` | `"YYYY-MM-DD"` |
| `date_end` | `"YYYY-MM-DD"`。1日開催なら `null` |
| `time` | 開始時刻 `"HH:MM"`(現地時間)。不明なら `null` |
| `city` | 開催都市(例 `"Frankfurt am Main"`)。オンラインのみなら `"Online"` |
| `venue` | 会場名。不明なら `null` |
| `format` | `"onsite"` / `"online"` / `"hybrid"`。不明なら `null` |
| `themes` | 該当する全てを配列で: `"central_bank"`(中央銀行・金融政策) / `"real_economy"`(実体経済。特にエネルギー・オイルショック、防衛支出、インフラ投資、景気・貿易) / `"fin_markets"`(金融規制・監督・金融市場・金融安定) |
| `fee` | `"free"` / `"paid"` / `"unknown"` |
| `open_to_public` | 一般が申込可なら `true`、招待制なら `false`、不明なら `null` |
| `registration_note` | 申込に関する短い日本語メモ(例「要事前登録・無料」)。不明なら `null` |
| `url` | イベント詳細ページのURL(なければ掲載元ページのURL) |
| `summary_ja` | 内容の日本語要約(1〜2文) |
| `language` | 開催言語。`"en"` / `"de"` / `"en+de"`。不明なら `null` |
| `country` | 開催国のISO 3166-1 alpha-2コード(例 `"DE"`, `"AT"`)。オンラインのみ開催なら `null` |
| `organizer_short` | 主催者の一般的な略称(例 `"ECB"`, `"Bundesbank"`, `"IfW Kiel"`, `"SAFE"`)。定着した略称がなければ組織名の短い形 |
| `title_short` | カレンダーセル表示用の短い英語テーマ(40字以内目安)。原題から年号・回数・シリーズ名などの冠飾を落とした中核テーマ(例 "ECB Annual Research Conference 2026 – Geoeconomics and the International Trading System" → "Geoeconomics and Int'l Trading System") |
| `source` | 情報源の名前(sources.yamlの`name`、または`"web検索(discovery)"`) |

## 抽出ルール

- 上記3テーマのいずれかに該当するイベントのみ。該当しないものは含めない。
- 開催地がドイツ国内、またはオンライン参加可能、または主催がECB/ドイツの機関のものに限る。
- 実行日より前に終了したイベントは含めない。
- セミナー/会議/講演/シンポジウム/ワークショップのみ。以下は除外:
  統計・報告書の公表予定、記者会見、美術展・博物館ツアー、学校向けワークショップ、
  教員研修、採用イベント、開催日未定のCall for Papers。
- 日付が読み取れないイベントは含めない。**推測で日付を作らない。**
- ページに書かれていない情報は `null` / `"unknown"` とする。**捏造しない。**
- 開催言語はページの記載・告知文の言語から判断する。推測が難しければ `null`。

## 禁止事項

- `scripts/` `sources.yaml` `AGENTS.md` 本体を書き換えないこと
  (ingest.pyのエラー修正が必要な場合のみ最小限の修正を許可)。
- `data/events.json` を直接編集しないこと(必ず new_events.json 経由)。
- 外部への通知・イシュー作成・PR作成をしないこと。
