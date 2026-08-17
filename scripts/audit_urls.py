#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_urls.py: 定点ソースURLの軽量監査(リンク健全性チェック)。

sources.yaml の全URLに実ブラウザ相当UAでGETし、以下を判定して一覧表示する。
イベント抽出は行わない(LLM不要・数分で終わる)。

  OK        : 2xx で、本文にソフト404の兆候がない
  SOFT404   : HTTP 200 だが本文がサイト内エラーページ(「存在しません」等)
  HTTP-ERR  : 4xx/5xx(ボット対策系の 401/403/423/429 を除く)
  BLOCKED   : 401/403/423/429(ボット対策。死にURLではない。fetch_hints で対処)
  OFFSITE   : 別ドメインへリダイレクトされた(組織統合・ドメイン移転の疑い)
  NET-ERR   : 接続不可(DNS/TLS/タイムアウト)
  THIN      : 2xx だがテキストがほぼ無い(JS描画の空殻の可能性。参考情報)

用途: 「ok なのに実はページが死んでいる」ソースの炙り出し(AGENTS.md 2a のソフト404
ルール参照)。リトライジョブ(AGENTS.md C)の前段や、ユーザーの指示時に実行する。
標準ライブラリのみで動作する。
"""

import concurrent.futures
import gzip
import io
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from radar_lib import parse_sources

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
TIMEOUT = 30
MAX_BYTES = 300_000
BLOCKED_CODES = {401, 403, 423, 429}

# ソフト404の本文シグネチャ(小文字で比較)
SOFT404_MARKERS = [
    "page not found", "seite nicht gefunden", "does not exist",
    "no longer available", "nicht verfügbar", "runtime error",
    "an error occurred", "存在しません", "ページが見つかりません",
    "възникна системна грешка", "несъществуващ адрес",
    "stranica nije pronađena", "strona nie została znaleziona",
]


def fetch(url):
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
            return r.status, r.geturl(), body
    except urllib.error.HTTPError as e:
        return e.code, e.geturl() if hasattr(e, "geturl") else url, b""
    except Exception as e:
        return None, url, str(e).encode("utf-8", "replace")


def host(url):
    m = re.match(r"https?://([^/]+)", url or "")
    return (m.group(1) if m else "").lower().removeprefix("www.")


def text_of(body):
    try:
        html = body.decode("utf-8", "replace")
    except Exception:
        return "", ""
    title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    if m:
        title = re.sub(r"\s+", " ", m.group(1)).strip()[:80]
    html = re.sub(r"(?s)<(script|style).*?</\1>", "", html)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()
    return title, text


def audit_one(src):
    url = src["url"]
    code, final_url, body = fetch(url)
    if code is None:
        return src["name"], "NET-ERR", "-", body.decode("utf-8", "replace")[:70]
    note = ""
    title, text = text_of(body)
    if code in BLOCKED_CODES:
        verdict = "BLOCKED"
    elif code >= 400:
        verdict = "HTTP-ERR"
    elif host(final_url) != host(url) and host(final_url):
        verdict = "OFFSITE"
        note = f"→ {final_url[:70]}"
    else:
        low = text.lower()
        hit = next((mk for mk in SOFT404_MARKERS if mk in low), None)
        if hit:
            verdict = "SOFT404"
            note = f"marker: {hit}"
        elif len(text) < 500:
            verdict = "THIN"
            note = f"text {len(text)} chars"
        else:
            verdict = "OK"
    if title and not note:
        note = title
    return src["name"], verdict, str(code), note


def main():
    sources = parse_sources()["sources"]
    print(f"audit_urls: {len(sources)} sources を検査中...", file=sys.stderr)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(audit_one, sources))
    order = {"SOFT404": 0, "HTTP-ERR": 1, "OFFSITE": 2, "NET-ERR": 3,
             "THIN": 4, "BLOCKED": 5, "OK": 6}
    results.sort(key=lambda r: order.get(r[1], 9))
    wide = max(len(r[1]) for r in results)
    for name, verdict, code, note in results:
        print(f"{verdict:<{wide}}  {code:>4}  {name}")
        if note and verdict != "OK":
            print(f"{'':<{wide}}        └ {note}")
    counts = {}
    for _, v, _, _ in results:
        counts[v] = counts.get(v, 0) + 1
    print("\n合計:", "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print("SOFT404 / HTTP-ERR / OFFSITE は死にURLの疑い(AGENTS.md 2b の差し替え候補)。\n"
          "BLOCKED はボット対策(fetch_hints の代替手段で巡回する)。THIN はJS描画の可能性。")


if __name__ == "__main__":
    main()
