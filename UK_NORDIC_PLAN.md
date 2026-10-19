# 英国+北欧への拡大計画 — 「ドイツモード / 英国モード」の切替

> 状態: **実装済み(2026-10-19)。** 未決事項はすべてユーザー回答済み(末尾「決定事項」)。
> 残作業: 英国 Routine の作成と初回巡回(人の作業。README「英国モード」参照)、要人名簿の追記(提案→承認後)。
> 計画からの差分は末尾「実装時の差分」を参照。

## 要望(ユーザー指示の要約)

- 対象地域を現行の「ドイツ+中東欧」に加えて「英国+北欧」へ拡大する。
- 英国はドイツと同じ粒度でしっかり見る。北欧は**現地開催なら規模3(旗艦・大型会議)相当だけ**を対象にする。
- 「ドイツモード」と「英国モード」は**切替スイッチで排他的に切り替える**。同一画面に両方を出すことは想定しない。

## 現状整理(拡大に関係する箇所)

| 項目 | 現状 | 出典 |
|---|---|---|
| 対象地域の強制 | `REGION` 集合(DE/CH/AT/中東欧/バルカン/バルト/UA)と `region_ok()`。ECB・BIS 主催と `anywhere: true` の定点だけ開催国不問 | `scripts/radar_lib.py` |
| 地域ごとの重要度下限 | **存在しない**。旗艦パターン(`FLAGSHIP_PATTERNS`)で下限3を強制する仕組みはある | 同上 |
| 定点リスト | 1本(約77ソース)。`category`(cb/tt/uni/other)と `anywhere` の属性のみ。地域属性なし | `sources.yaml` |
| 発見検索の観点 | 1本(16観点、独語クエリ混在) | 同上 `discovery_topics` |
| 巡回の状態ファイル | `data/` 直下に1組(`events.json`・`known_events.json`・`status.json`・`fetch_state.json`・`detail_state.json`・`changelog.json`・`token_usage.json`) | `AGENTS.md` A-4 |
| 画面 | 1テンプレート→1ページ(`docs/index.html`、約1.4MB。イベントJSONを埋め込み)。UI言語 JA/EN/DE はページ内切替 | `scripts/template.html` |
| 画面のドイツ前提 | 既定フィルタ(Area=DE・Country=DE・★2以上)、Area選択肢「ドイツ/ドイツ以外」、◇印=ドイツ国外、「Frankfurt日帰り圏」チェック、対象地域パネル文言、主催グループ表(`ORG_GROUPS`)、`<title>` | 同上(約10箇所) |
| 英国所在の既存定点 | OMFIF・PRI(いずれもロンドン)。現状は**オンライン開催分だけ**収載。CEPR・OMFIF は `ORG_GROUPS` に `c:"GB"` で登録済み | `sources.yaml`・`template.html` |
| 要人名簿 | イングランド銀行6名(Bailey・Lombardelli・Ramsden・Pill・Braddick・Breeden)が既に登録。北欧中銀は未登録 | `data/people.json` |
| 日次のトークン消費 | 直近20日の平均 約2,700万トークン/日(最小1,700万・最大5,400万) | `python3 scripts/log_tokens.py --summary` |
| 自動マージ | `claude/**` push → `data/` を**丸ごと**取り込み `docs/` を main 側で再生成 | `.github/workflows/automerge.yml` |

## 方針(確定)

### 1. 「プロファイル」単位で地域ルール・定点・データ・ページを分ける

ドイツモード=プロファイル `de`、英国モード=プロファイル `uk`。

| 層 | de(現行) | uk(新規) | 備考 |
|---|---|---|---|
| 地域ルール | `REGION` 現行どおり。ECB・BIS 例外あり | GB・IE は全規模。DK/SE/NO/FI/IS は **開催国が付く(現地・ハイブリッド)なら importance 3 のみ**、完全オンラインは全規模。ECB・BIS 例外**なし** | `radar_lib.py` に `PROFILES` 辞書。`region_ok()` と重要度下限をプロファイルで切替 |
| 定点リスト | `sources.yaml` の `regions:` 未記載 = `[de]` | `regions: [uk]`。両方に出す定点(OMFIF・PRI・SUERF 等)は `[de, uk]` | 1ファイルのまま属性で分ける(既存エントリは無変更で後方互換) |
| 発見検索 | `discovery_topics`(現行) | `discovery_topics_uk`(新設。英語クエリ中心) | |
| 巡回状態ファイル | `data/` 直下(現行のまま) | `data/uk/` 配下に同じ構成(`cache/` も `data/uk/cache/`) | `data/people.json`・`data/fetch_hints.json` は**共用**(名簿・ソース名キーの台帳) |
| 手動取込 | `INBOX.md`・`data/manual/`・`FOCUS.md` | `INBOX_UK.md`・`data/uk/manual/`・`FOCUS_UK.md` | どちらの Routine が処理するかを分けるため |
| 出力ページ | `docs/index.html` | `docs/uk/index.html` | **同じテンプレート**からプロファイル設定(`__PROFILE_JSON__`)を差し込んで2枚生成 |
| ICS | `docs/calendar.ics` | `docs/uk/calendar.ics` | |

**同一画面に両方を出さない**という要望には「2枚のページ+ヘッダの切替スイッチ」が最も素直に合う。
1枚のページに両データを埋め込む案は、ページが約2.8MBに倍増し、フィルタ・リスト・共有リンクの
全ロジックにモード分岐が入るため採らない。

### 2. プロファイルの指定方法(スクリプト)

- 全スクリプト(`ingest.py`・`fetch_all.py`・`fetch_details.py`・`check_status.py`・`log_tokens.py`・
  `audit_urls.py`)が **`--profile uk`** を受け付ける(省略時 `de`。環境変数 `SR_PROFILE=uk` と同義)。
- `radar_lib.py` はプロファイルに応じてパス定数(`DATA_FILE` 等)を切り替える。
  `de` のときの値は現行と**一字も変わらない**(後方互換)。
- `parse_sources()` はプロファイルに属する定点だけを返す。`fetch_all.py` 等は自動的に
  そのプロファイルの定点だけを巡回する。

### 3. 切替スイッチ(UI)

- ヘッダの `JA | EN | DE` の隣に `DE | UK` のトグルを置く(見た目は `.langsw` と同系)。
  押すと相互のページへ遷移する(`/` ⇄ `/uk/`。相対リンク)。
- UI言語(`sr_uilang`)・テーマ(`sr_skin`)は同一オリジンの localStorage なので両ページで共有される。
  フィルタ保存(`sr_filters_v7`)とマイリスト(`sr_lists_v1`)は**プロファイル別のキー**にする
  (uk は `_uk` 接尾辞。de は現行キーのまま)。
- `/` は常にドイツ、`/uk/` は常に英国。最後に見たモードを記憶して自動で飛ばすことは**しない**。

### 4. 英国モードの画面仕様(ドイツモードとの対応)

| 要素 | ドイツモード | 英国モード |
|---|---|---|
| 既定フィルタ | Area=DE・Country=DE・★2以上・オンライン除外 | Area=GB・Country=GB・★2以上・**オンライン除外** |
| Area 選択肢 | ドイツ / ドイツ以外 | 英国 / 英国以外(=アイルランド・北欧) |
| ◇印(国外開催) | ドイツ国外 | 英国外 |
| 日帰り圏チェック | Frankfurt 日帰り圏 | **London 日帰り圏**(Bank 駅起点・片道4時間以内) |
| 対象地域パネル | 現行文言 | 「英国・アイルランド。北欧(DK/SE/NO/FI/IS)は現地開催なら旗艦・大型会議のみ、オンラインは全規模」 |
| 主催グループ表 | `ORG_GROUPS` | 英国・北欧の機関を**追記**(表は共用。`c:` で国を持つ) |
| `<title>` | ドイツ経済・金融セミナー | 英国経済・金融セミナー |
| 要約・申込メモ | ja/en/de の3言語 | **同じ3言語**(ドイツ語表記も残す) |
| テーマ軸 | 9テーマ | **同じ9テーマ**(EU–UK関係等は④地政学・③規制で吸収) |

### 5. 北欧「現地開催は規模3のみ」の実装

- 重要度は LLM が判定するため、スクリプト側でも強制する: プロファイル設定に
  `min_importance: {"DK": 3, "SE": 3, "NO": 3, "FI": 3, "IS": 3}` を持ち、`ingest.py` が
  `region_ok()` と同じ場所で、**`country` がこれらの国のイベントで importance が下限未満のもの**を
  除去する(新規・既存の両方に毎回効く)。完全オンライン(`country: null`)は対象外=全規模収載。
  ハイブリッドは開催国が付くので現地開催と同じ扱い(規模3のみ)。
- 定点は北欧の中央銀行(Riksbank・Norges Bank・Danmarks Nationalbank・Suomen Pankki・
  Seðlabanki Íslands)に絞る。研究所・大学の定例セミナーはどのみち規模3にならないので定点にしない。
- 北欧の旗艦会議は `FLAGSHIP_PATTERNS` にパターンを追加して下限3を保証する(ソース調査で確定)。
- 既存の BOFIT(`anywhere: true`・フィンランド)は現行どおりドイツモード側に残す
  (英国モードの Suomen Pankki 定点とは別エントリ)。

### 6. 日次更新の回し方

**Routine を2本にする。** 既存 Routine はそのまま(ドイツモード)。新 Routine のプロンプトは
「リポジトリ直下の AGENTS.md を読み、その指示に従って本日の**英国モード**の更新を実行せよ。」。
消費は1日あたり現状の2倍程度まで許容(ユーザー確認済み)。

- `AGENTS.md` に「プロファイル」の節を足す。英国モードでは B の全手順で `--profile uk` を付け、
  `data/` を `data/uk/` と読み替え、`INBOX_UK.md`・`FOCUS_UK.md` を使う。
  コミットメッセージは **`daily update YYYY-MM-DD uk (claude)`**。
- `.github/workflows/automerge.yml` の data モードは、現在 `data/` を丸ごとブランチから取り込む。
  2本の Routine が別々のブランチから push するため、**ブランチが変更したファイルだけ**を取り込む
  方式(`git diff --name-status` でファイル単位に checkout / rm)に改める。そうしないと、
  先に main へ入った他方のプロファイルのデータが古いコピーで巻き戻る。
  `docs/` は両プロファイル分を main 側で再生成する。
- 2本が同時刻に走らないよう、Routine の時刻は数時間ずらす(人の設定。例: de 06:30・uk 09:30)。

### 7. 収載ルール(英国モード固有。`AGENTS.md` に転記する)

- 開催地: GB・IE、またはオンライン。DK/SE/NO/FI/IS は現地開催・ハイブリッドなら規模3のみ。
  それ以外の国での開催は収載しない(ECB・BIS 主催でも収載しない。それらはドイツモードで見る)。
- 有料の業界会議(UK Finance 等)は**規模3相当のものだけ**収載する。
- Call for Papers が参加要件のイベントは通常どおり収載する(開催日未定の CfP は従来どおり除外)。
- 要約・申込メモは3言語セット(現行どおり)。

### 8. 英国・北欧の定点候補(実装フェーズで `scripts/audit_urls.py --profile uk` と実取得で検証して確定)

- 中央銀行・当局: Bank of England(イベント・研究会議)、PRA、FCA、HM Treasury、OBR
- 研究所・シンクタンク: NIESR、IFS、CEPR、Resolution Foundation、Institute for Government、
  Centre for European Reform、Chatham House、RUSI、IISS、Policy Exchange、Green Finance Institute、
  Grantham Research Institute(LSE)、E3G、Tony Blair Institute
- 大学: LSE(公開イベント・Centre for Macroeconomics・Financial Markets Group・Systemic Risk Centre)、
  Oxford(Saïd・Oxford Martin)、Cambridge(Judge)、KCL(Qatar Centre for Global Banking & Finance)、
  Imperial、Warwick、Bayes。アイルランド: Central Bank of Ireland、ESRI、Trinity College Dublin
- 業界・市場: UK Finance、TheCityUK、City of London Corporation、LSEG、ICMA、ISDA(規模3のみの運用)
- 日本・中国軸: Daiwa Anglo-Japanese Foundation、Japan Society、JETRO London、SOAS China Institute、
  China-Britain Business Council
- 既存定点で `[de, uk]` に広げる候補: OMFIF、PRI、SUERF、UNEP FI
- 北欧(中銀のみ): Riksbank、Norges Bank、Danmarks Nationalbank、Suomen Pankki、Seðlabanki Íslands

注意: Routines の実行環境がネットワーク許可リスト方式の場合、新ドメイン
(bankofengland.co.uk 等)の追加が必要になる(`README.md` 初期セットアップ4参照)。これは人の作業。

### 9. 変更箇所一覧

| ファイル | 変更 |
|---|---|
| `sources.yaml` | 各定点に `regions:`(省略時 `[de]`)。`discovery_topics_uk` 追加。英国・北欧定点の追加 |
| `scripts/radar_lib.py` | `PROFILES`(データ/出力パス・地域集合・重要度下限・ECB/BIS例外の有無・ICS名・検索観点キー)。`region_ok`/`parse_sources`/`render_html`/`render_ics` のプロファイル対応。`__PROFILE_JSON__` の差し込み |
| `scripts/ingest.py` ほか各スクリプト | `--profile`。重要度下限の強制(ingest) |
| `scripts/template.html` | `__PROFILE_JSON__` を読んで既定値・Area選択肢・◇判定・日帰り圏・パネル文言・`<title>`・localStorage キー接尾辞を切替。ヘッダに `DE | UK` スイッチ。`ORG_GROUPS` に英国・北欧機関を追記 |
| `.github/workflows/automerge.yml` | data モードをファイル単位の取り込みに変更。両プロファイルの `docs/` を再生成 |
| `.gitignore` | `data/uk/cache/` |
| `AGENTS.md` | プロファイルの節。英国モードの収載ルール。A-4 の禁止事項に `data/uk/` を追記 |
| `README.md` | 英国モードの説明・2本目の Routine の設定手順 |
| `data/uk/` | 初期ファイル一式。`INBOX_UK.md` |
| `data/people.json` | 英国・北欧の要人(**ユーザー管理ファイル。最終段階で提案→承認後に追記**) |

### 10. 段階

1. 決定(完了)
2. プロファイル機構(scripts + sources.yaml の属性 + automerge)。ドイツモードの出力が変わらないことを
   `docs/index.html` の再生成差分で確認する(回帰テスト)
3. 画面のモード対応(template.html)。英国側は空データでも崩れないことを確認
4. 定点調査(候補URLの検証・取捨)と `AGENTS.md` の英国節・検索観点・`README.md`
5. 初回巡回(英国 Routine の「Run now」)→ 1〜2週間 `log_tokens.py --summary --profile uk` で消費を比較
6. 要人名簿の英国・北欧追記(提案を出してユーザー承認のうえ実施)

## 決定事項(2026-10-19 ユーザー回答)

1. 英国モードの地域: GB+**IE**(全規模)+北欧 DK/SE/NO/FI/IS(現地開催は規模3のみ)。
2. ECB・BIS の開催国不問の例外は英国モードでは**適用しない**。
3. 英国モードのオンライン開催は**英国プロファイルの定点・検索から取れた分だけ**。
4. 北欧の**完全オンライン開催は規模1〜2でも収載**。ただし既定表示ではオンラインはチェックオフ(非表示)。
5. 日次更新は **Routine 2本**。トークンは現状の2倍程度まで許容。
6. 英国モードでも**ドイツ語表記(summary_de 等)を残す**(3言語セット維持)。
7. **London 日帰り圏を入れる**。Central line の Bank 駅を起点に片道4時間以内。
8. `/` はドイツ・`/uk/` は英国固定。自動遷移なし。
9. テーマ軸は9テーマをそのまま使う。
10. 定点候補は上記のとおり。有料の業界会議は規模3相当のみ。CfP が参加要件のものは通常どおり収載。
11. 要人名簿の追記は計画の最後に承認のうえ実施。

実装上の補足(ユーザー回答から導いた扱い): ハイブリッド開催は開催国が付くため、北欧では
現地開催と同じく規模3のみとする。

## 実装時の差分・補足(2026-10-19)

- **定点**: 英国・アイルランド 49 機関を実取得で検証し 43 件を登録(`regions: [uk]`)。PRA・HM Treasury・OBR
  (公開イベント一覧なし)、Green Finance Institute(一覧なし)、Tony Blair Institute(Vercel のボット対策)、
  City of London Corporation(文化イベント中心のJSページ)は定点にせず discovery で補完する。
  北欧は5中銀を登録。既存の OMFIF・PRI・SUERF・UNEP FI は `[de, uk]` に広げ、ICMA は新規で `[de, uk]`。
  verified: false(403・JS描画)が英国側で約17件ある。403 はこの実行環境のプロキシ固有の可能性があるため、
  初回巡回で `scripts/audit_urls.py --profile uk` を実行して見直す。
- **旗艦パターン**はプロファイル限定(`FLAGSHIP_PATTERNS_BY_PROFILE["uk"]`)で追加した。汎用語
  「annual research conference」(Riksbank)は大学の研究会議にも当たるため入れていない。Riksbank の
  年次研究会議は抽出時の importance 判定(機関の年次旗艦=3)に委ねる。
- **London 日帰り圏**は Trainline の所要時間(最速値)を根拠に 24 都市+Leamington Spa(Warwick)。
  Edinburgh(4h05)・Glasgow(4h30)は超過、Belfast・Dublin は鉄道直通なしで除外。
- **UI の付随変更**(ドイツモードにも影響): 「仕組み」パネルに「対象地域」の節を追加(以前は辞書にだけあり
  未表示だった)。狭幅(390px以下)でヘッダのツール列が折り返すようにした(改修前から横溢れしていた)。
- **CI の再生成**は `docs/` と `docs/uk/` の両方を行う。英国側は初回巡回まで `data/uk/meta.json` の
  固定時刻を LAST UPDATE に表示する。
- **ネットワーク許可リストに必要なドメイン**(Routines 環境が許可リスト方式の場合):
  bankofengland.co.uk, fca.org.uk, niesr.ac.uk, ifs.org.uk, cepr.org, resolutionfoundation.org,
  instituteforgovernment.org.uk, cer.eu, chathamhouse.org, rusi.org, my.rusi.org, iiss.org,
  policyexchange.org.uk, lse.ac.uk, centreformacroeconomics.ac.uk, fmg.ac.uk, systemicrisk.ac.uk,
  cep.lse.ac.uk, e3g.org, sbs.ox.ac.uk, oxfordmartin.ox.ac.uk, jbs.cam.ac.uk, bennettschool.cam.ac.uk,
  kcl.ac.uk, imperial.ac.uk, warwick.ac.uk, wbs.ac.uk, bayes.citystgeorges.ac.uk, mmf.ac.uk, iea.org.uk,
  ukandeu.ac.uk, centralbank.ie, esri.ie, tcd.ie, ukfinance.org.uk, thecityuk.com, lseg.com,
  icmagroup.org, isda.org, dajf.org.uk, japansociety.org.uk, jetro.go.jp, soas.ac.uk, cbbc.org,
  riksbank.se, norges-bank.no, nationalbanken.dk, cb.is(suomenpankki.fi・omfif.org・unpri.org・
  suerf.org・unepfi.org は既存)。
