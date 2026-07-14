# Seminar Radar — ドイツ経済・金融セミナー自動収集カレンダー

毎日1回、Claude(Claude Code Routines)がAnthropicのクラウド上で自動実行され、

1. `sources.yaml` の定点観測リスト(ECB・ブンデスバンク・4大研究所ほか)を巡回
2. web検索で定点リスト外のセミナーも発見
3. 抽出したイベントを `scripts/ingest.py` が検証・重複排除して蓄積
4. `docs/index.html`(カレンダー+一覧)と `docs/calendar.ics` を再生成してプッシュ

する仕組み。GitHub Pages の固定URLをブラウザで開くだけで最新版が見られる。

- **手元PCへのインストール不要**(設定は全てブラウザ)
- **API従量課金なし**: RoutinesはClaude定額課金(Pro/Max)の利用枠内で動く
- Claudeの役割は「読む・探す・抽出する」だけ。日付検証・重複排除・HTML生成は
  決定論的なPythonコード(`scripts/`)が行うので出力が安定する

---

## 初期セットアップ(ブラウザのみ・所要20分程度)

### 1. GitHubリポジトリを作る
1. github.com にログイン(なければ無料アカウント作成)
2. 右上「+」→「New repository」→ 名前 `seminar-radar`、**Public** → Create
3. リポジトリ画面の「uploading an existing file」(Add file → Upload files)に、
   このフォルダの**中身**(README.md, ROUTINE.md, sources.yaml, scripts, data, docs,
   optional)をドラッグ&ドロップ → Commit changes

### 2. GitHub Pages を有効化
Settings → Pages → Source「Deploy from a branch」/ Branch `main`・フォルダ `/docs` → Save。
数分後 `https://<ユーザー名>.github.io/seminar-radar/` が固定URLになる。

### 3. ClaudeにGitHubを接続してRoutineを作る
1. ブラウザで **claude.ai/code** を開く(定額課金アカウントでログイン)
2. 初回はGitHub連携を求められるので許可し、`seminar-radar` リポジトリへの
   アクセスを与える(全リポジトリではなくこのリポジトリだけに絞ってよい)
3. **claude.ai/code/routines** を開き「New routine」
   - リポジトリ: `seminar-radar`
   - トリガー: Scheduled / 毎日 / 06:30(Europe/Berlin)など好きな時刻
   - プロンプト欄には次の1行だけ書く:

     ```
     リポジトリ直下の ROUTINE.md を読み、その指示に従って本日の更新を実行せよ。
     ```

   - ブランチ保護の設定がある場合は「mainへのプッシュを許可」
     (Allow unrestricted branch pushes 相当)を有効にする。
     Routinesは既定で `claude/` 接頭辞のブランチにしかプッシュできないため
4. 保存したら「Run now」(即時実行)で初回を回す

### 4. 初回実行の確認
1. 実行ログ(claude.ai/code のセッション一覧)で完了を確認
2. Pages のURLを開き、最下部「巡回ステータス」を見る
3. 失敗しているソースがあれば対処:
   - **URLが古い場合**(特に `verified: false` の IfW/RWI/SUERF/ZEW):
     GitHub上で `sources.yaml` を直接編集(鉛筆アイコン)して正しいURLに直す
   - **ネットワークが遮断されている場合**(403 / host_not_allowed 系のエラー):
     Routineの実行環境は既定で接続先が許可リスト方式のことがある。
     claude.ai/code の環境設定(Environment / Network)で、巡回先ドメイン
     (ecb.europa.eu, bundesbank.de, ifo.de, diw.de, ifw-kiel.de, rwi-essen.de,
     safe-frankfurt.de, imfs-frankfurt.de, hof.uni-frankfurt.de, suerf.org, zew.de)
     を許可リストに追加するか、ネットワーク制限を緩和する

以後は毎日自動で更新される。

---

## 日々の使い方

- 固定URLをブックマークして開くだけ。カレンダー+月別一覧
- フィルタ: テーマ①②③ / 現地・オンライン / 無料のみ / キーワード検索
- 直近4日以内の新検出には **NEW** バッジ
- `docs/calendar.ics` も毎回生成している(将来Outlook等でICS購読が
  可能になった場合に備えたもの)

## メンテナンス(全てブラウザで完結)

- **巡回先の追加・削除・検索観点の変更**: GitHub上で `sources.yaml` を直接編集
- **コードの修正や機能追加**: claude.ai/code でこのリポジトリを開き、
  Claudeに日本語で指示すれば編集からコミットまでやってくれる
  (VS CodeのClaude Code拡張でも同じことができるが、ローカルにgitが
  ない環境ではブラウザ版 claude.ai/code を使うのが簡単)
- **利用枠**: Routinesの実行は定額課金の利用枠を消費する。使いすぎが
  気になる場合は実行を週3回などに減らせばよい

## 予備手段: GitHub Actions + API従量課金版

Routinesが使えない/やめたい場合のために、同じ処理をGitHub Actions +
Anthropic API(従量課金)で回す版も同梱している。
`optional/daily.yml.disabled` を `.github/workflows/daily.yml` として
コミットし、APIキーをSecrets(`ANTHROPIC_API_KEY`)に登録すれば動く。
本体は `scripts/update_api.py`。詳細はファイル内コメント参照。
