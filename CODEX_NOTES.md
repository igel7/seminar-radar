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

### 通らないもの

| 対象 | 結果 |
|---|---|
| `git ls-remote`(既定のプロトコル v2) | `RPC failed; HTTP 403 curl 22` |
| `git push`(protocol v0 を明示しても) | `RPC failed; HTTP 403` + `send-pack: unexpected disconnect while reading sideband packet` |
| `POST https://api.github.com/repos/.../git/refs`(ブランチ作成) | `HTTP 403` / 本文 `Method forbidden`(プレーンテキスト = プロキシ由来。GitHub API なら JSON で返る) |

### プロキシの規則(上記を統一的に説明する仮説)

**GitHub 宛の GET は通し、POST 以降の書き込みメソッドは 403 で拒否する。**

- gitプロトコル **v2** の ref 取得は `POST /git-upload-pack` を使う → 403
- gitプロトコル **v0** の ref 探索は `GET /info/refs` のみ → 通る
- `git push` は第1段階 `GET /info/refs?service=git-receive-pack` は通過し(資格情報が誤っていた
  段階では GitHub 本体から `Invalid username or token` が返ってきたことで確認済み)、
  第2段階の `POST /git-receive-pack` で 403 になる。
  `send-pack: unexpected disconnect` はパック送信中に切断された痕跡である。
- GitHub API の書き込み(POST)も同じく 403 で、本文がプレーンテキストの `Method forbidden`。

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

### 未検証・未確認

- `git fetch` / `git clone`(v0 でも実際のパック取得は `POST /git-upload-pack` を使うため、
  同様に 403 になる可能性が高い。`ls-remote` だけは GET のみで完結するため通った)。
- **`.github/workflows/automerge.yml` の `codex/**` トリガーが実際に発火するか。**
  ブランチを GitHub 上に作れていないため、一度も検証できていない。
  Codex のタスク画面からブランチが push された時点で確認すること。
- Codex Cloud に「スケジュール実行の結果を自動で PR にする」設定があるか
  (あれば無人運用の可能性が残る。プラットフォーム側の push はコンテナのプロキシ制限を
  受けないため、これが唯一の抜け道になりうる)。
- headless Chromium(`scripts/fetch_page.py`)が Codex 環境で使えるか。
- Codex 環境に web 検索手段があるか(無い場合の記録方法は AGENTS.md 手順3に定めてある)。

---

## 現時点の運用方針

- **定期実行(無人)は Claude Code Routines で行う。**
- **Codex は手動実行で使う。** 実行後、成果物は Codex のタスク画面から人が反映する。
  エージェントは `python3 scripts/ingest.py` までとローカルコミットを済ませ、
  **push できない旨を報告して終了する**(AGENTS.md 手順6を参照)。
- Codex 環境の設定(参考。トークンの値は環境変数 `GH_TOKEN` にのみ存在する):
  - シークレット欄は使わない(エージェントから参照できないため)
  - セットアップスクリプトで git の identity を `--global` で設定しておくとコミットが通る

```bash
git config --global user.name  "seminar-radar-codex"
git config --global user.email "codex@users.noreply.github.com"
git config --global protocol.version 0
git config --global remote.origin.url https://github.com/igel7/seminar-radar.git
git config --global remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'
```

`protocol.version 0` と `remote.origin.url` は push が通らない現状では実益がないが、
読み取り(`ls-remote`)を行う場合に必要で、害もないため残している。
