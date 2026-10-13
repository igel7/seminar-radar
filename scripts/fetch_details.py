#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_details.py: 登壇者補完のためのイベント詳細ページ取得(AGENTS.md B手順1.6)。

日次巡回(fetch_all.py)は一覧ページしか読まないため、詳細ページにしか書かれていない
登壇者は構造的に取れない。このスクリプトは、収載済みで登壇者が未記録のイベントから
**1日あたり最大 LIMIT 件**だけ詳細ページ(イベントの url)を取得して本文をテキスト化し、
エージェントが登壇者だけを抽出して「薄いレコード」(手順4)で追記できる形に整える。
LLMは使わない(標準ライブラリのみ)。

候補の条件(すべて満たすもの):
  - data/events.json に収載済みで、まだ終わっていない(date_end または date_start が今日以降)
  - speakers が空/未記録
  - url が http(s) で、一覧ページ(sources.yaml の url・fetch_hints の alt_urls)や
    サイトのトップ(パスが "/" だけ)ではない
  - 状態台帳(data/detail_state.json)上、未試行か、前回試行から RETRY_DAYS 日以上経過していて
    試行回数が MAX_TRIES 未満(登壇者は開催が近づいてから公表されることが多いので、
    一度「載っていなかった」ページも間を空けて再確認する)
優先順位: 未試行 → importance の高い順 → 開催日の近い順。

出力:
  - data/cache/detail--<event_id>.txt … 詳細ページ本文(先頭 DETAIL_MAX_CHARS 字)。コミットしない
  - data/cache/detail_manifest.json … 取得した各イベントの薄いレコードの雛形
    ({id, title, date_start, themes, source, url, speakers: []} + cache パス)。
    エージェント(サブエージェント)は雛形の speakers だけを埋めて new_events.json に入れる。
    title・date_start を書き換えないこと(既存イベントへの一致に使う)
  - data/detail_state.json … URL別の試行台帳。このスクリプトだけが書く。コミット対象

使い方:
    python3 scripts/fetch_details.py             # 最大 LIMIT 件を取得
    python3 scripts/fetch_details.py --limit 3   # 件数を変える
    python3 scripts/fetch_details.py --dry-run   # 候補の一覧だけ出して取得も台帳更新もしない
"""

import argparse
import concurrent.futures
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from radar_lib import DATA_FILE, ROOT, TODAY, load_json, parse_sources  # noqa: E402
from fetch_all import (CACHE_DIR, HINTS_FILE, classify_failure, decode, fetch,  # noqa: E402
                       html_to_text)

STATE_FILE = ROOT / "data" / "detail_state.json"
MANIFEST_FILE = CACHE_DIR / "detail_manifest.json"
LIMIT = 5                   # 1日あたりの取得上限(トークンと取得回数を抑えるため)
RETRY_DAYS = 21             # 同じURLを再確認するまでの間隔
MAX_TRIES = 3               # 同じURLの試行回数上限
DETAIL_MAX_CHARS = 60_000   # キャッシュ保存の上限(登壇者一覧はページ後方にあることが多い)
STATE_KEEP_DAYS = 180       # 収載から外れたイベントの台帳エントリを残す日数


def norm_url(u):
    return re.sub(r"[?#].*$", "", (u or "").strip()).rstrip("/").lower()


def listing_urls():
    """一覧ページとして使っているURL(詳細ページ候補から除外する)。"""
    urls = set()
    for src in parse_sources()["sources"]:
        urls.add(norm_url(src.get("url")))
    hints = load_json(HINTS_FILE, {})
    if isinstance(hints, dict):
        for h in hints.values():
            for u in (h.get("alt_urls") or []) if isinstance(h, dict) else []:
                urls.add(norm_url(u))
    urls.discard("")
    return urls


def is_upcoming(ev):
    last = ev.get("date_end") or ev.get("date_start") or ""
    return last >= TODAY.isoformat()


def eligible(entry):
    """台帳エントリから見て再試行してよいか。未試行なら True。"""
    if not entry:
        return True
    if entry.get("tries", 0) >= MAX_TRIES:
        return False
    try:
        last = date.fromisoformat(entry.get("last") or "")
    except ValueError:
        return True
    return last + timedelta(days=RETRY_DAYS) <= TODAY


def pick_candidates(events, state, limit):
    listing = listing_urls()
    cands = []
    for ev in events:
        url = ev.get("url") or ""
        if not url.startswith(("http://", "https://")):
            continue
        if ev.get("speakers") or not is_upcoming(ev):
            continue
        nu = norm_url(url)
        if nu in listing or re.fullmatch(r"https?://[^/]+", nu):
            continue
        entry = state.get(nu)
        if not eligible(entry):
            continue
        cands.append((0 if not entry else 1, -(ev.get("importance") or 0),
                      ev.get("date_start") or "", ev))
    cands.sort(key=lambda c: c[:3])
    return [c[3] for c in cands[:limit]]


def fetch_one(ev):
    code, final_url, body, charset = fetch(ev["url"])
    text = html_to_text(decode(body, charset), final_url) if body else ""
    fail = classify_failure(code, text)
    return ev, code, final_url, text, fail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=LIMIT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    store = load_json(DATA_FILE, {})
    events = store.get("events", []) if isinstance(store, dict) else []
    state = load_json(STATE_FILE, {})
    if not isinstance(state, dict):
        state = {}

    chosen = pick_candidates(events, state, max(0, args.limit))
    print(f"登壇者未記録の詳細ページ取得: 候補 {len(chosen)} 件(上限 {args.limit})")
    if not chosen:
        print("  (候補なし。抽出対象の詳細ページはありません)")
        if not args.dry_run:
            MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
            MANIFEST_FILE.write_text("[]\n", encoding="utf-8")
        return
    if args.dry_run:
        for ev in chosen:
            print(f"  imp{ev.get('importance')} {ev.get('date_start')} {ev.get('title')[:60]}  {ev['url']}")
        return

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        results = list(ex.map(fetch_one, chosen))
    for ev, code, final_url, text, fail in results:
        nu = norm_url(ev["url"])
        entry = state.get(nu) or {}
        entry.update({"event_id": ev["id"], "last": TODAY.isoformat(),
                      "tries": entry.get("tries", 0) + 1,
                      "result": fail or "ok", "http": code})
        state[nu] = entry
        label = fail or "OK"
        line = f"  {label:<13} imp{ev.get('importance')} {ev.get('date_start')} {ev.get('title')[:55]}"
        if fail:
            print(line + f"  ({code})")
            continue
        cache = CACHE_DIR / f"detail--{ev['id']}.txt"
        trunc = (f"# note: 全{len(text):,}字のうち先頭{DETAIL_MAX_CHARS:,}字のみ保存\n"
                 if len(text) > DETAIL_MAX_CHARS else "")
        cache.write_text(
            f"# event_id: {ev['id']}\n# title: {ev.get('title')}\n"
            f"# date_start: {ev.get('date_start')}\n# url: {final_url}\n# fetched: {TODAY}\n"
            + trunc + f"\n{text[:DETAIL_MAX_CHARS]}\n", encoding="utf-8")
        manifest.append({"cache": str(cache.relative_to(ROOT)),
                         "record": {"id": ev["id"], "title": ev.get("title"),
                                    "date_start": ev.get("date_start"),
                                    "themes": ev.get("themes"), "source": ev.get("source"),
                                    "url": ev.get("url"), "speakers": []}})
        print(line + f"  -> {cache.relative_to(ROOT)}")

    # 台帳の整理: 収載から外れて久しいエントリは落とす
    live_ids = {e.get("id") for e in events}
    cutoff = (TODAY - timedelta(days=STATE_KEEP_DAYS)).isoformat()
    state = {u: e for u, e in state.items()
             if e.get("event_id") in live_ids or (e.get("last") or "") >= cutoff}
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                          encoding="utf-8")
    MANIFEST_FILE.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
                             encoding="utf-8")
    print(f"抽出対象 {len(manifest)} 件。雛形: {MANIFEST_FILE.relative_to(ROOT)}"
          f"(speakers だけを埋めて new_events.json に入れる。title/date_start は変えない)")


if __name__ == "__main__":
    main()
