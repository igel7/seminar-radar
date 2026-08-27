#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_all.py: 日次巡回の前段プリフェッチ+差分検知(AGENTS.md B手順1.5)。

sources.yaml の全ソースを並列取得し、本文をテキスト化して data/cache/ に保存、
内容ハッシュを前回実行時(data/fetch_state.json)と比較して、ソースごとに
「変化あり/変化なし/取得失敗」を判定・一覧表示する。LLMは使わない(標準ライブラリのみ)。

狙い: エージェントが読む必要があるのは「内容が変化したソースのテキスト」だけにする。
  - UNCHANGED のソースはページを読まずにスキップできる(同一内容→同一抽出なので精度損失なし)
  - CHANGED / NEW のソースは data/cache/<slug>.txt を読んで抽出する(生HTMLを読まない)
  - FAIL-* のソースだけ、従来どおり 2a のフォールバック・ラダーを回す

判定:
  NEW          初回取得(前回ハッシュなし)。抽出対象
  CHANGED      前回とテキスト内容が異なる。抽出対象
  UNCHANGED    前回と同一内容。抽出スキップ可(status.json には前回の found を引き継ぐ)
  FAIL-BLOCKED 401/403/423/429(ボット対策)。2a ラダーへ
  FAIL-SOFT404 200 だが本文がエラーページ(2a のソフト404ルール参照)。2a ラダーへ
  FAIL-THIN    2xx だがテキストがほぼ無い(JS描画の空殻の疑い)。2a ラダーへ
  FAIL-HTTP    その他の 4xx/5xx。2a ラダーへ(3回連続なら 2b の死にURL判定)
  FAIL-NET     接続不可(DNS/TLS/タイムアウト)。2a ラダーへ
  SKIP-BLOCK   fetch_hints.json で permanent_block 指定があり、週次再確認日でもない。
               取得を試みない(status.json には ok:false・恒常ブロックとして記録)

fetch_hints.json 連携:
  - 各ソースの alt_urls(過去の勝ちパターン)を元URLより先に試す
  - permanent_block: {"since": "YYYY-MM-DD", "recheck_days": 7, "last_recheck": "YYYY-MM-DD"}
    が付いたソースは、last_recheck から recheck_days 経過した日だけ取得を試み
    (出力に「再確認日」と明記)、それ以外の日はネットワークに触れない。
    再確認日の扱い(ラダー完遂・last_recheck の更新)はエージェントが行う。

状態ファイル:
  - data/fetch_state.json … ソース別の内容ハッシュ台帳。コミット対象(翌日のセッションが
    フレッシュな環境でも差分検知できるようにするため)。このスクリプトだけが書く。
  - data/cache/*.txt … 取得済み本文テキスト。ローカル作業用でコミットしない(.gitignore)。

使い方:
    python3 scripts/fetch_all.py              # 全ソースを取得・判定
    python3 scripts/fetch_all.py --only ECB   # 名前に部分一致するソースだけ(再取得・デバッグ用)
"""

import argparse
import concurrent.futures
import gzip
import hashlib
import html as htmllib
import io
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent))
from radar_lib import ROOT, STATUS_FILE, TODAY, load_json, parse_sources

STATE_FILE = ROOT / "data" / "fetch_state.json"
HINTS_FILE = ROOT / "data" / "fetch_hints.json"
CACHE_DIR = ROOT / "data" / "cache"
SOURCES_FILE = ROOT / "sources.yaml"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
TIMEOUT = 30
MAX_BYTES = 600_000
BLOCKED_CODES = {401, 403, 423, 429}
MIN_TEXT_CHARS = 500        # これ未満はJS空殻(THIN)とみなす
DEFAULT_RECHECK_DAYS = 7

# audit_urls.py と同じソフト404シグネチャ(小文字で比較)
SOFT404_MARKERS = [
    "page not found", "seite nicht gefunden", "does not exist",
    "no longer available", "nicht verfügbar", "runtime error",
    "an error occurred", "存在しません", "ページが見つかりません",
    "възникна системна грешка", "несъществуващ адрес",
    "stranica nije pronađena", "strona nie została znaleziona",
]

# ボット対策のチャレンジページ兆候(HTTP 200 でも「取得成功」と誤認しないため。
# 本文が短い場合のみ判定に使う — 正規ページの文中に紛れた語での誤爆を避ける)
CHALLENGE_MARKERS = [
    "just a moment", "checking your browser", "verify you are human",
    "verifying you are human", "attention required! | cloudflare",
    "ddos protection by", "please enable cookies", "captcha",
    "enable javascript and cookies",
]
CHALLENGE_MAX_CHARS = 3000


def max_page_chars():
    """sources.yaml の settings.max_page_chars(なければ30000)。"""
    m = re.search(r"^\s*max_page_chars:\s*(\d+)", SOURCES_FILE.read_text(encoding="utf-8"),
                  re.M)
    return int(m.group(1)) if m else 30000


def slug_of(name):
    """キャッシュファイル名。可読スラッグ+名前ハッシュ6桁(衝突・非ラテン名対策)。"""
    base = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower()[:50]
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:6]
    return f"{base or 'src'}-{digest}"


def fetch(url):
    """1 URL をGET。戻り値 (status_code|None, final_url, body_bytes, charset|None)。"""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Language": "en,de;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read(MAX_BYTES)
            if r.headers.get("Content-Encoding") == "gzip":
                try:
                    body = gzip.GzipFile(fileobj=io.BytesIO(body)).read(MAX_BYTES)
                except OSError:
                    pass
            charset = r.headers.get_content_charset()
            return r.status, r.geturl(), body, charset
    except urllib.error.HTTPError as e:
        return e.code, getattr(e, "geturl", lambda: url)(), b"", None
    except Exception as e:
        return None, url, str(e).encode("utf-8", "replace"), None


def decode(body, charset):
    if charset:
        try:
            return body.decode(charset, "replace")
        except LookupError:
            pass
    m = re.search(rb'<meta[^>]+charset=["\']?([A-Za-z0-9_-]+)', body[:4096], re.I)
    if m:
        try:
            return body.decode(m.group(1).decode("ascii"), "replace")
        except LookupError:
            pass
    return body.decode("utf-8", "replace")


def html_to_text(raw, base_url):
    """HTML/XML → 読みやすいプレーンテキスト。リンクは「テキスト [絶対URL]」として保持する
    (イベント詳細ページのURLを抽出できるようにするため)。"""
    # コメント・不可視要素を除去
    raw = re.sub(r"(?s)<!--.*?-->", " ", raw)
    raw = re.sub(r"(?is)<(script|style|noscript|template|svg|iframe)\b.*?</\1>", " ", raw)
    # <head> はタイトルだけ残す
    title = ""
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
    if m:
        title = re.sub(r"\s+", " ", m.group(1)).strip()
    raw = re.sub(r"(?is)<head\b.*?</head>", " ", raw)
    # リンクを「テキスト [URL]」に変換(相対URLは絶対化)
    def link_repl(m):
        href, inner = m.group(1), m.group(2)
        text = re.sub(r"<[^>]+>", " ", inner)
        text = re.sub(r"\s+", " ", text).strip()
        href = htmllib.unescape(href.strip())
        if href.startswith(("javascript:", "mailto:", "#", "data:")):
            return f" {text} "
        absolute = urljoin(base_url, href)
        if not absolute.startswith(("http://", "https://")):
            return f" {text} "
        return f" {text} [{absolute}] " if text else f" [{absolute}] "
    raw = re.sub(r'(?is)<a\b[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', link_repl, raw)
    # ブロック要素の境界を改行にしてからタグ除去
    raw = re.sub(r"(?i)<(?:br|/p|/div|/li|/tr|/h[1-6]|/section|/article|/table)\b[^>]*>",
                 "\n", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    text = htmllib.unescape(raw)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if title:
        text = f"{title}\n\n{text}"
    return text


def classify_failure(code, body_text):
    if code is None:
        return "FAIL-NET"
    if code in BLOCKED_CODES:
        return "FAIL-BLOCKED"
    if code >= 400:
        return "FAIL-HTTP"
    low = body_text.lower()
    if len(body_text) < CHALLENGE_MAX_CHARS and any(mk in low for mk in CHALLENGE_MARKERS):
        return "FAIL-BLOCKED"
    if any(mk in low for mk in SOFT404_MARKERS):
        return "FAIL-SOFT404"
    if len(body_text) < MIN_TEXT_CHARS:
        return "FAIL-THIN"
    return None


def recheck_due(block, today):
    """permanent_block の週次再確認日か。last_recheck が無ければ due 扱い。"""
    days = block.get("recheck_days") or DEFAULT_RECHECK_DAYS
    last = block.get("last_recheck") or block.get("since")
    if not last:
        return True
    try:
        return date.fromisoformat(last) + timedelta(days=days) <= today
    except ValueError:
        return True


def process_source(src, hints, prev_state, prev_status_ok, limit):
    """1ソースを取得・判定する。戻り値は state エントリ+表示用フィールドの辞書。"""
    name, main_url = src["name"], src["url"]
    hint = hints.get(name) if isinstance(hints.get(name), dict) else {}
    prev = prev_state.get(name) if isinstance(prev_state.get(name), dict) else {}

    entry = {"url": main_url, "last_fetch": TODAY.isoformat(),
             "hash": prev.get("hash"), "last_changed": prev.get("last_changed")}

    block = hint.get("permanent_block")
    is_recheck = False
    if isinstance(block, dict):
        if not recheck_due(block, TODAY):
            entry.update(verdict="SKIP-BLOCK", http=None,
                         note=f"恒常ブロック(since {block.get('since')}、"
                              f"次回再確認は last_recheck+{block.get('recheck_days', DEFAULT_RECHECK_DAYS)}日)")
            return name, entry
        is_recheck = True

    # 勝ちパターン(alt_urls)→元URL の順に試す
    candidates = []
    for u in (hint.get("alt_urls") or []):
        if u and u not in candidates:
            candidates.append(u)
    if main_url and main_url not in candidates:
        candidates.append(main_url)
    if not candidates:
        entry.update(verdict="FAIL-NET", http=None, note="URLが空(sources.yaml を確認)")
        return name, entry

    attempts = []
    for u in candidates:
        code, final_url, body, charset = fetch(u)
        if code is not None and code < 400:
            text = html_to_text(decode(body, charset), final_url)
            failure = classify_failure(code, text)
            if failure is None:
                # 取得成功: キャッシュ保存+ハッシュ比較。
                # ハッシュは切り詰め前の全文で計算する(キャッシュの max_page_chars 以降で
                # 起きた変化も CHANGED として検知できるようにするため)。
                digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]
                slug = slug_of(name)
                cache_file = CACHE_DIR / f"{slug}.txt"
                trunc_note = (f"# note: 全{len(text):,}字のうち先頭{limit:,}字のみ保存\n"
                              if len(text) > limit else "")
                cache_file.write_text(
                    f"# source: {name}\n# url: {final_url}\n{trunc_note}\n{text[:limit]}\n",
                    encoding="utf-8")
                if prev.get("hash") is None:
                    verdict = "NEW"
                elif prev.get("hash") != digest:
                    verdict = "CHANGED"
                elif prev_status_ok.get(name) is False:
                    # 前回の巡回が失敗だったソースは、内容が同一でも復旧分として取り直す
                    # (前回の found が 0 のままなので、引き継ぎ対象にしない)
                    verdict = "CHANGED"
                    entry["note"] = "前回の巡回が失敗のため、内容は同一でも抽出対象(復旧)"
                else:
                    verdict = "UNCHANGED"
                entry.update(
                    verdict=verdict, http=code, hash=digest, chars=len(text),
                    url_used=final_url,
                    cache_file=str(cache_file.relative_to(ROOT)),
                    last_changed=TODAY.isoformat() if verdict in ("NEW", "CHANGED")
                                 else prev.get("last_changed"))
                if is_recheck:
                    entry["note"] = "恒常ブロックの再確認日に取得成功(ブロック解除の可能性。fetch_hints の permanent_block を見直すこと)"
                return name, entry
            attempts.append((u, code, failure))
        else:
            attempts.append((u, code, classify_failure(code, "")))

    # 全候補が失敗
    # ボット対策(BLOCKED)は死にURLより情報量が多いので優先して報告する
    severity = {"FAIL-SOFT404": 0, "FAIL-THIN": 1, "FAIL-BLOCKED": 2,
                "FAIL-HTTP": 3, "FAIL-NET": 4}
    worst = min(attempts, key=lambda a: severity.get(a[2], 9))
    tried = ", ".join(f"{u} → {c if c is not None else 'NET-ERR'}" for u, c, _ in attempts)
    entry.update(verdict=worst[2], http=worst[1], note=f"tried: {tried}")
    if is_recheck:
        entry["note"] += "(恒常ブロックの再確認日: 2a ラダーを完遂し、fetch_hints の last_recheck を今日に更新すること)"
    return name, entry


def main():
    ap = argparse.ArgumentParser(description="全ソースの一括プリフェッチ+差分検知")
    ap.add_argument("--only", help="名前にこの文字列を含むソースだけ処理(部分一致)")
    args = ap.parse_args()

    sources = parse_sources()["sources"]
    if args.only:
        sources = [s for s in sources if args.only.lower() in s["name"].lower()]
        if not sources:
            sys.exit(f"--only '{args.only}' に一致するソースがありません。")

    hints = load_json(HINTS_FILE, {})
    state = load_json(STATE_FILE, {})
    if not isinstance(state, dict):
        state = {}
    # 前回の巡回ステータス(ok可否)。前回失敗したソースは UNCHANGED でも取り直す
    prev_status_ok = {e.get("name"): bool(e.get("ok"))
                      for e in load_json(STATUS_FILE, []) if isinstance(e, dict)}
    limit = max_page_chars()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    print(f"fetch_all: {len(sources)} sources を取得中...", file=sys.stderr)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        results = dict(ex.map(
            lambda s: process_source(s, hints, state, prev_status_ok, limit), sources))

    # 状態台帳を更新(--only 時も該当ソースだけ上書き)
    state.setdefault("_readme",
        "fetch_all.py が管理するソース別の内容ハッシュ台帳。手で編集しない。"
        "hash はキャッシュ本文テキストの sha256 先頭20桁。")
    for name, entry in results.items():
        keep = {k: v for k, v in entry.items() if k != "note"}
        state[name] = keep
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n",
                          encoding="utf-8")

    # 表示: 抽出対象 → 失敗 → スキップ → 変化なし(圧縮表示)
    order = {"NEW": 0, "CHANGED": 0, "FAIL-SOFT404": 1, "FAIL-THIN": 1, "FAIL-BLOCKED": 1,
             "FAIL-HTTP": 1, "FAIL-NET": 1, "SKIP-BLOCK": 2, "UNCHANGED": 3}
    rows = sorted(results.items(), key=lambda kv: (order.get(kv[1]["verdict"], 9), kv[0]))
    unchanged = []
    for name, e in rows:
        v = e["verdict"]
        if v == "UNCHANGED":
            unchanged.append(name)
            continue
        extra = ""
        if v in ("NEW", "CHANGED"):
            extra = f"  {e.get('chars', 0):,} chars  {e.get('cache_file')}"
            if e.get("url_used") and e["url_used"] != e["url"]:
                extra += f"  (取得URL: {e['url_used']})"
        print(f"{v:<13} {name}{extra}")
        if e.get("note"):
            print(f"{'':<13} └ {e['note']}")
    if unchanged:
        print(f"UNCHANGED     {len(unchanged)} 件(抽出スキップ可・status.json には前回の found を引き継ぐ):")
        print("              " + " / ".join(unchanged))

    counts = {}
    for _, e in results.items():
        counts[e["verdict"]] = counts.get(e["verdict"], 0) + 1
    print("\n合計:", "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print("NEW/CHANGED は data/cache/ のテキストから抽出。FAIL-* は AGENTS.md 2a のラダーへ。\n"
        "SKIP-BLOCK は ok:false(恒常ブロック)として記録する。")


if __name__ == "__main__":
    main()
