# 英国+北欧への拡大計画 — 「ドイツモード / 英国モード」の切替

> 状態: **草案(未決事項あり・実装未着手)**。2026-10-19 作成。
> 末尾「決めてほしい点」への回答を受けて確定版にする。実装はその後。

## 要望(ユーザー指示の要約)

- 対象地域を現行の「ドイツ+中東欧」に加えて「英国+北欧」へ拡大する。
- 英国はドイツと同じ粒度でしっかり見る。北欧は**現行の規模3(旗艦・大型会議)相当だけ**を対象にする。
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
| 自動マージ | `claude/**` push → `data/` のみ取り込み `docs/` を main 側で再生成 | `.github/workflows/automerge.yml` |

## 推奨方針(案)

### 1. 「プロファイル」単位で地域ルール・定点・データ・ページを分ける

ドイツモード=プロファイル `de`、英国モード=プロファイル `uk` とし、以下を**プロファイルごと**に持つ。

| 層 | de(現行) | uk(新規) | 備考 |
|---|---|---|---|
| 地域ルール | `REGION` 現行どおり | GB(+北欧 DK/SE/NO/FI/IS は importance 3 のみ) | `radar_lib.py` に `PROFILES` 辞書を置き、`region_ok(ev, profile)` にする |
| 定点リスト | `sources.yaml` の `regions:` 未記載 = `[de]` | `regions: [uk]`。両方に出す定点(OMFIF・PRI・SUERF・CEPR 等)は `[de, uk]` | 1ファイルのまま属性で分ける(既存エントリは無変更で後方互換) |
| 発見検索 | `discovery_topics`(現行) | `discovery_topics_uk`(新設。英語クエリ中心) | |
| 巡回状態ファイル | `data/` 直下(現行のまま) | `data/uk/` 配下に同じ構成 | 既存の禁止事項・スクリプトのパスを壊さない。`fetch_hints.json` はソース名キーなので共用可 |
| 出力ページ | `docs/index.html` | `docs/uk/index.html` | **同じテンプレート**からプロファイル設定(`__PROFILE_JSON__`)を差し込んで2枚生成 |
| ICS | `docs/calendar.ics` | `docs/uk/calendar.ics` | |

**同一画面に両方を出さない**という要望には「2枚のページ+ヘッダの切替スイッチ」が最も素直に合う。
1枚のページに両データを埋め込む案は、ページが約2.8MBに倍増し、フィルタ・リスト・共有リンクの
全ロジックにモード分岐が入るため採らない。

### 2. 切替スイッチ(UI)

- ヘッダの `JA | EN | DE` の隣に `DE | UK` のトグルを置く(見た目は `.langsw` と同系)。
  押すと相互のページへ遷移する(`/` ⇄ `/uk/`)。
- UI言語(`sr_uilang`)・テーマ(`sr_skin`)は同一オリジンの localStorage なので両ページで共有される。
  フィルタ保存(`sr_filters_v7`)とマイリスト(`sr_lists_v1`)は**プロファイル別のキー**にする
  (英国モードで Country=DE を保存しても意味がないため。マイリストの event id は
  プロファイル間で衝突しうるので分ける)。
- 最後に見たモードを記憶して `/` を開いたとき自動で `/uk/` へ飛ばすかは**未決**(下記)。

### 3. 英国モードの画面仕様(ドイツモードとの対応)

| 要素 | ドイツモード | 英国モード(案) |
|---|---|---|
| 既定フィルタ | Area=DE・Country=DE・★2以上・オンライン除外 | Area=GB・Country=GB・★2以上・オンライン除外 |
| Area 選択肢 | ドイツ / ドイツ以外 | 英国 / 北欧 |
| ◇印(国外開催) | ドイツ国外 | 英国外(=北欧) |
| 日帰り圏チェック | Frankfurt 日帰り圏 | **未決**(London 日帰り圏に置換 / 非表示) |
| 対象地域パネル | 現行文言 | 「英国。北欧(DK/SE/NO/FI/IS)は旗艦・大型会議のみ」 |
| 主催グループ表 | `ORG_GROUPS` | 英国・北欧の機関を**追記**(表は共用。`c:` で国を持つ) |
| `<title>` | ドイツ経済・金融セミナー | 英国経済・金融セミナー |
| 言語フィルタ | 英語 / ドイツ語 | 英語のみ(北欧語は想定しない)。選択肢自体はプロファイル設定で出し分け |

### 4. 北欧「規模3のみ」の実装

- 重要度は LLM が判定するため、「3だけ残す」をスクリプト側でも強制する:
  プロファイル設定に `min_importance: {"DK": 3, "SE": 3, "NO": 3, "FI": 3, "IS": 3}` を持ち、
  `ingest.py` が `region_ok()` と同じ場所で下限未満を除去する(新規・既存の両方に毎回効く)。
- 定点は北欧の中央銀行(Riksbank・Norges Bank・Danmarks Nationalbank・Suomen Pankki・
  Seðlabanki Íslands)に絞る(候補。URLは後続の実地確認が必要)。研究所・大学の定例セミナーは
  どのみち規模3にならないので定点にしない(巡回トークンの無駄を避ける)。
- 北欧の旗艦会議は `FLAGSHIP_PATTERNS` にパターンを追加して下限3を保証する(候補はソース調査で確定)。
- **既存の BOFIT(`anywhere: true`・フィンランド)との整合は未決**(下記)。

### 5. 日次更新の回し方

選択肢(いずれも `AGENTS.md` B に「プロファイル指定」の節を足す):

| 案 | 内容 | トークン影響(推測) | 備考 |
|---|---|---|---|
| (a) 1本の Routine で両方を順に実行 | 手順1.5〜6 を `--profile de` → `--profile uk` で2周 | 1日あたり +60〜90% | 1セッションが長くなり、文脈圧迫で後半の品質が落ちる懸念 |
| (b) Routine を2本にする(**推奨**) | 既存 Routine はそのまま。新 Routine のプロンプトを「英国モードで更新せよ」にする | 1日あたり +60〜90%(同じ) | セッションが分かれるので文脈が汚れない。コミットは `data/uk/` 配下だけ触るので衝突しない。自動マージは concurrency 直列 |
| (c) 隔日で交互に回す | 偶数日 de・奇数日 uk | ±0(ただし各地域の鮮度は2日に1回) | 節約したい場合の退避先 |

推奨は (b)。利用枠が気になる場合は (c) に落とす。
英国分の定点は30〜45ソース程度を想定しており(候補は下記)、1回の消費はドイツ分と同程度か
やや少ない見込み(推測。定点数と差分検知の当たり具合で変わる)。

### 6. 英国・北欧の定点候補(**未検証**。URL実在確認は実装フェーズで `scripts/audit_urls.py` を使って行う)

- 中央銀行・当局: Bank of England(イベント・研究会議)、PRA、FCA、HM Treasury、OBR
- 研究所・シンクタンク: NIESR、IFS、CEPR、Resolution Foundation、Institute for Government、
  Centre for European Reform、Chatham House、RUSI、IISS、Policy Exchange、Green Finance Institute、
  Grantham Research Institute(LSE)、E3G、Tony Blair Institute
- 大学: LSE(公開イベント・Centre for Macroeconomics・Financial Markets Group・Systemic Risk Centre)、
  Oxford(Saïd・Oxford Martin)、Cambridge(Judge)、KCL(Qatar Centre for Global Banking & Finance)、
  Imperial、Warwick、Bayes
- 業界・市場: UK Finance、TheCityUK、City of London Corporation、LSEG、ICMA、ISDA
- 日本・中国軸: Daiwa Anglo-Japanese Foundation、Japan Society、JETRO London、SOAS China Institute、
  China-Britain Business Council
- 既存定点で `[de, uk]` に広げる候補: OMFIF、PRI、SUERF、CEPR(未登録なら新規)、UNEP FI
- 北欧(中銀のみ): Riksbank、Norges Bank、Danmarks Nationalbank、Suomen Pankki(BOFIT と統合するか要検討)、
  Seðlabanki Íslands

注意: Routines の実行環境がネットワーク許可リスト方式の場合、新ドメイン
(bankofengland.co.uk 等)の追加が必要になる(`README.md` 初期セットアップ4参照)。これは人の作業。

### 7. 変更箇所一覧(実装時)

| ファイル | 変更 |
|---|---|
| `sources.yaml` | 各定点に `regions:`(省略時 `[de]`)。`discovery_topics_uk` 追加。英国・北欧定点の追加 |
| `scripts/radar_lib.py` | `PROFILES`(地域集合・重要度下限・既定フィルタ・UI文言キー・出力パス)。`region_ok`/`parse_sources`/`render_html`/`render_ics` のプロファイル対応。パス定数をプロファイルから引く |
| `scripts/ingest.py` | `--profile uk`。`data/uk/` の読み書き。重要度下限の強制 |
| `scripts/fetch_all.py` / `fetch_details.py` / `check_status.py` / `log_tokens.py` / `audit_urls.py` | `--profile` で状態ファイルのパスと対象ソースを切替 |
| `scripts/template.html` | `__PROFILE_JSON__` を読んで既定値・Area選択肢・◇判定・日帰り圏・パネル文言・`<title>`・localStorage キー接尾辞を切替。ヘッダに `DE | UK` スイッチ。`ORG_GROUPS` に英国・北欧機関を追記 |
| `.github/workflows/automerge.yml` | data モードでも code モードでも両プロファイルの `docs/` を再生成(`ingest.py --maintenance --profile de` と `--profile uk`) |
| `AGENTS.md` | 「プロファイル」の節(英国モードの地域ルール・北欧の重要度下限・要約言語・検索観点・状態ファイルのパス)。A-4 の禁止事項に `data/uk/` を追記 |
| `README.md` | 英国モードの説明・2本目の Routine の設定手順 |
| `data/uk/` | 初期ファイル一式(空) |
| `data/people.json` | 英国・北欧の要人(**ユーザー管理ファイル。追記は明示の指示があった場合のみ**) |

### 8. 段階

1. **決定**(本書の未決事項に回答をもらう)
2. **プロファイル機構**(scripts + sources.yaml の属性)。ドイツモードの出力が1バイトも変わらないことを
   `docs/index.html` の再生成差分で確認する(回帰テスト)
3. **画面のモード対応**(template.html)。英国側は空データでも崩れないことを Playwright で確認
4. **定点調査**(英国・北欧の候補URLを `audit_urls.py` で検証・取捨)と `AGENTS.md` の英国節・検索観点
5. **初回巡回**(手動セッションで英国プロファイルの初回収集)→ 2本目の Routine 設定 → 1〜2週間
   `log_tokens.py --summary` で消費を比較
6. 要人名簿の英国・北欧追記(ユーザー承認のうえ)

規模感(推測): 2〜3 は1セッションずつ、4 は定点数しだいで1〜2セッション。

## 決めてほしい点

既定値(太字)でよければ返事不要。変えたい項目だけ指示してほしい。

1. **英国モードの地域**: **GB のみ**+北欧(DK/SE/NO/FI/IS は規模3のみ)。アイルランド(IE)を
   英国側に含めるか(英語圏で近いが、含めると定点が増える。既定: **含めない**)。
2. **英国モードでの ECB・BIS 例外**: ドイツモードは ECB・BIS 主催なら開催国不問で収載する。
   英国モードでも同じにするか(既定: **適用しない**。ECB・BIS はドイツモードで見るため。
   ただし BIS がロンドンで開く会議は GB 開催として普通に拾われる)。
3. **オンライン開催の扱い**: 英国モードには**英国プロファイルの定点(`[uk]` または `[de, uk]`)
   から取れたオンライン開催だけ**を載せる(既定)。ドイツ系定点のオンライン開催(Bundesbank の
   ウェビナー等)は英国モードに出さない。
4. **北欧の下限**: 規模3のみ(既定)。北欧中銀のオンライン開催(BOFIT セミナー等。規模1〜2が多い)も
   3未満なら落とすか。既定: **落とす**。BOFIT は現行どおりドイツモード側(`anywhere: true`)に残す。
5. **日次更新の回し方**: 上記 5 の **(b) Routine 2本**(既定)/(a) 1本で2周/(c) 隔日交互。
   利用枠の上限感があれば教えてほしい(現状 平均2,700万トークン/日が 1.6〜1.9倍になる推測)。
6. **要約・申込メモの言語**: ドイツモードは ja/en/de の3言語必須。英国モードは
   **ja/en の2言語**にし、DE表示時は英語要約で代用するか(出力トークンを約1/3節約)。
   既定: **2言語**。
7. **日帰り圏チェック**: 英国モードでは (ア) 非表示 (イ) 「London 日帰り圏」(鉄道片道2時間程度:
   Oxford・Cambridge・Birmingham・Brighton 等)に置換。既定: **(ア) 非表示**
   (置換が必要なら、どこを拠点に考えるか教えてほしい)。
8. **モードの記憶**: 切替スイッチを押したモードを記憶し、次回 `/` を開いたとき自動で `/uk/` に
   飛ばすか。既定: **飛ばさない**(`/` は常にドイツ、`/uk/` は常に英国。ブックマークで使い分ける)。
9. **テーマ軸**: 9テーマ(①中銀〜⑨ウクライナ)を英国モードでも**そのまま使う**(既定)。
   英国固有の観点(例: EU–UK関係、Brexit後の規制分岐)は④地政学・③規制で吸収する。
   追加テーマが必要なら指示してほしい。
10. **定点候補の採否**: 上記 6 の候補から外したい機関・足したい機関があれば。特に
    「有料の業界会議(UK Finance 等)をどこまで拾うか」と「安全保障系(RUSI・IISS)を入れるか」。
11. **要人名簿**: 英国(FCA・PRA・HMT・OBR)と北欧中銀の総裁・副総裁級を、この計画の一部として
    エージェントが公式ページを根拠に追記してよいか(既定: **計画の最後に、承認のうえ実施**)。
