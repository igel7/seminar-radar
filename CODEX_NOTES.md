# CODEX_NOTES.md — Codex Cloud 実行環境の検証記録

検証日: **2026-08-17** / 対象環境: Codex Cloud の環境 `seminar-radar`
(image: universal / エージェントのインターネットアクセス: 有効・無制限 / セットアップ後のキャッシュ: 有効)

このファイルは、日次更新を Codex Cloud で回そうとして判明した事実の記録である。
**同じ調査を二度やらないために残している。** 「試したが駄目だったこと」の節は特に重要で、
ここに書かれた方法は再試行しても通らない。

**秘密情報はこのファイルに書かない。** トークンは Codex 環境の環境変数 `GH_TOKEN` として
渡しており、値はリポジトリ内のどこにも記録していない。

---

## 結論(要約)

**Codex Cloud のエージェントコンテナから GitHub へ書き込む手段は存在しない。**
コンテナの外向き通信は MITM プロキシ(`http://proxy:8080` / envoy-mitmproxy)を経由し、
**GitHub 宛の書き込みメソッド(POST 等)が一律で遮断されている。** 読み取り(GET)は通る。

したがって:

- Codex は**巡回・抽出・データ生成・ローカルコミットまでは問題なく実行できる**
  (外部サイトの取得は通るので、巡回そのものは成功する)。
- しかし `git push` も GitHub API による書き込みも不可能で、**成果物を自力で GitHub に
  反映できない。** 反映は Codex のタスク画面から人が操作する経路(PR作成/push)に限られる。
- 結果として **Codex では無人の定期実行が成立しない。** 定期実行は Claude Code Routines に
  残し、Codex は手動実行(実行後に人がタスク画面で反映)に用いる。

---

## 確認済みの事実

### 通るもの

| 対象 | 結果 |
|---|---|
| 一般の外部サイト取得(巡回対象。例 ecb.europa.eu) | 200。**巡回は正常に動く** |
| `GET https://github.com/.../info/refs?service=git-upload-pack` | 200 |
| `GET https://api.github.com/repos/igel7/seminar-radar` | 200 |
| `git -c protocol.version=0 ls-remote --heads <URL>` | **成功**(main の SHA を取得できた) |
| GitHub API による認証・権限確認(GET) | 200 / `permissions: push: True` を取得 |
| `pip install <パッケージ>`(PyPI からのダウンロード) | 成功(playwright 1.62.0 を導入できた) |

### 通らないもの

| 対象 | 結果 |
|---|---|
| `git ls-remote`(既定のプロトコル v2) | `RPC failed; HTTP 403 curl 22` |
| `git push`(protocol v0 を明示しても) | `RPC failed; HTTP 403` + `send-pack: unexpected disconnect while reading sideband packet` |
| `POST https://api.github.com/repos/.../git/refs`(ブランチ作成) | `HTTP 403` / 本文 `Method forbidden`(プレーンテキスト = プロキシ由来。GitHub API なら JSON で返る) |
| `git clone --depth 1`(protocol v0 を明示しても) | `RPC failed; HTTP 403` / 終了コード 128。**fetch/clone も不可**(実際のオブジェクト転送は `POST /git-upload-pack` を使うため) |
| **web検索**(`web__run` ツール) | ツールは存在するが実行すると `http 401 Unauthorized`。**検索は使えない** |
| **headless Chromium**(`scripts/fetch_page.py`) | ブラウザ本体が存在しない。`/opt/pw-browsers` なし、`chromium`/`google-chrome` は PATH になし、`PLAYWRIGHT_BROWSERS_PATH` 未設定。`playwright` は pip で導入できたが `Failed to launch chromium because executable doesn't exist` |

### プロキシの規則(上記を統一的に説明する仮説)

**GitHub 宛の GET は通し、POST 以降の書き込みメソッドは 403 で拒否する。**

- gitプロトコル **v2** の ref 取得は `POST /git-upload-pack` を使う → 403
- gitプロトコル **v0** の ref 探索は `GET /info/refs` のみ → 通る
- `git push` は第1段階 `GET /info/refs?service=git-receive-pack` は通過し(資格情報が誤っていた
  段階では GitHub 本体から `Invalid username or token` が返ってきたことで確認済み)、
  第2段階の `POST /git-receive-pack` で 403 になる。
  `send-pack: unexpected disconnect` はパック送信中に切断された痕跡である。
- GitHub API の書き込み(POST)も同じく 403 で、本文がプレーンテキストの `Method forbidden`。

### エージェントに提供されているツール(2026-08-17 時点)

- **GitHub への PR 作成・push を行うツールは存在しない**(`make_pr` 等は提供されていない)。
- **web検索**: `web__run` が存在するが、実行すると `http 401 Unauthorized` になり使えない。
- **サブエージェントへの委譲機構は存在する**:
  `collaboration.spawn_agent` / `collaboration.followup_task` / `collaboration.send_message` /
  `collaboration.interrupt_agent` / `collaboration.list_agents` / `collaboration.wait_agent`。
  AGENTS.md A-3(トークン節約のための委譲)は Codex でも実行可能である。
- その他: `exec_command` / `apply_patch` / `update_plan` / `view_image` /
  `list_mcp_resources` / `read_mcp_resource` など。

### 環境の性質(判明したこと)

- エージェントは **root** で動作する。セットアップフェーズと同一ユーザー。
- **タスクごとにリポジトリのディレクトリが作り直される。** セットアップスクリプトで
  `git remote add` しても `.git/config` は次のタスクに残らない。
- 一方 **ホームディレクトリの内容は残る**(`~/.gitconfig`・`~/.git-credentials` は
  セットアップフェーズで書いたものがエージェントフェーズでも読める)。
  したがって git の設定は `git config --global` で入れる必要がある。
- **シークレット欄の値はエージェントフェーズでは参照できない**(セットアップフェーズのみ)。
  エージェントに値を渡す必要があるものは「環境変数」欄に入れる。
- **セットアップ後のキャッシュが有効**なため、セットアップスクリプトを書き換えても
  「キャッシュをリセットする」を押さないと反映されない。
- 環境変数として `HTTP_PROXY` / `HTTPS_PROXY` = `http://proxy:8080`、CA は
  `/usr/local/share/ca-certificates/envoy-mitmproxy-ca-cert.crt`(`SSL_CERT_FILE` 等に設定済み)。
  TLS 検証は正常に通っている(403 は HTTP 応答であり証明書エラーではない)。

---

## 試したが駄目だったこと(再試行しないこと)

以下はすべて実測で否定済みである。同じ道を再度試してトークンを浪費しないこと。

1. **セットアップスクリプトで `git remote add` して push** — リポジトリが作り直されるため
   `origin` が消える。`git config --global remote.origin.url` を使えば `origin` は解決できるが、
   push 自体が通らないので無意味。
2. **fine-grained PAT を資格情報ファイルに焼き込む** — トークン・ファイル形式ともに正常
   (長さ・接頭辞・バイト数・API での有効性と `push: True` 権限を確認済み)。
   それでも push は 403。**認証の問題ではない。**
3. **User-Agent の偽装**(`http.userAgent` を curl 相当にする) — 変化なし。403。
4. **`http.version=HTTP/1.1`** — 変化なし。403。
5. **匿名アクセス**(`credential.helper=` で資格情報を無効化)での ref 取得 —
   Public リポジトリなので匿名で読めるはずだが、プロトコル v2 では 403。
   これにより「認証・権限・UA のいずれも原因ではない」と確定した。
6. **GitHub API でのブランチ作成** — `Method forbidden` で 403。
7. **`gh` CLI** — コンテナに認証は入っていない(そもそも上記の理由で通らない)。

8. **`playwright install` によるブラウザ本体の導入** — 未実施。`pip install` は通るので
   ダウンロード自体は成功する可能性があるが、後述の理由により追求していない。

### 未検証・未確認(残っているもの)

- **Codex のタスク画面に push / PR 作成のボタンがあるか。** エージェント側にその手段が
  無いことは確定したので、**これが Codex から成果物を出す唯一の可能性**である。
  完了済みタスクの画面で確認すること。無ければ Codex はこのリポジトリの作業に使えない。
- Codex Cloud に「スケジュール実行の結果を自動で PR にする」設定があるか
  (あれば無人運用の可能性が残る。プラットフォーム側の push はコンテナのプロキシ制限を
  受けないため、これが唯一の抜け道になりうる)。
- `web__run` の 401 が恒久的なものか、一時的・アカウント設定由来のものか。

### 解決済み(記録として)

- **`.github/workflows/automerge.yml` の `codex/**` トリガーは正しく発火する。**
  2026-08-17 に Claude 側から `codex/automerge-trigger-test` ブランチを push して確認。
  ワークフローが起動し、data モードとして処理され、ブランチは自動削除された。
  つまり **Codex のブランチが GitHub 上に現れれば、以降の自動反映は問題なく動く。**

---

## 現時点の運用方針

**日次更新は Claude Code Routines で行う。Codex はこのリポジトリの日次更新には使わない。**

Codex 側で判明した制約を合わせると、日次更新の主要機能が3つとも欠ける。

| 必要な機能 | Codex での可否 |
|---|---|
| 定点観測リストの巡回(静的ページの取得) | **可**(これだけは正常に動く) |
| web検索による新規発見(手順3)・死んだURLの検索リカバリ(手順2) | **不可**(`web__run` が 401) |
| JS描画ソースの取得(`fetch_page.py`) | **不可**(ブラウザ本体が無い) |
| 成果物の GitHub への反映(手順6) | **不可**(書き込みが全面遮断) |

巡回はできても、新規発見が死に、取得できないソースが増え、しかも結果を人が手で
運び出す必要がある。**トークン上限対策として Codex に日次更新を委ねる案は成立しない。**

Codex を使う余地が残るのは、タスク画面に push / PR のボタンがあることが確認できた場合の
**コード作業(人がその場で差分を確認して反映する用途)**に限られる。

### トークンの後始末

`GH_TOKEN`(fine-grained PAT)は git push と GitHub API 書き込みのために用意したが、
**どちらも不可能と確定したため不要である。** 読み取りだけなら Public リポジトリなので
認証は要らない。以下を実施して撤去する。

1. GitHub: Settings → Developer settings → Fine-grained tokens → 該当トークンを削除(revoke)
2. Codex 環境: 環境変数 `GH_TOKEN` を削除(シークレット欄にも残っていれば削除)
3. Codex 環境のセットアップスクリプトから、資格情報を書き込む行を削除する
   (`credential.helper` / `~/.git-credentials` / `remote.origin.url` / `protocol.version`)。
   ローカルコミットに必要な identity だけ残せばよい:

```bash
git config --global user.name  "seminar-radar-codex"
git config --global user.email "codex@users.noreply.github.com"
```

4. キャッシュをリセットして、`~/.git-credentials` を含む古いスナップショットを破棄する

**トークンの値はこのリポジトリのどこにも記録していない。** 今後も記録しないこと。
