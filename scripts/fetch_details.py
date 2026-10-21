#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_details.py: 登壇者補完のためのイベント詳細ページ取得(AGENTS.md B手順1.6)。

日次巡回(fetch_all.py)は一覧ページしか読まないため、詳細ページにしか書かれていない
登壇者は構造的に取れない。このスクリプトは、収載済みで登壇者が未記録のイベントから
**1日あたり最大 LIMIT 件**だけ詳細ページ(イベントの url)を取得し、**登壇者に関係する
本文だけを抜粋**(最大 EXCERPT_MAX_CHARS 字)してテキスト化し、エージェントが登壇者だけを
抽出して「薄いレコード」(手順4)で追記できる形に整える。LLMは使わない(標準ライブラリのみ)。

2026-10-21 改訂(登壇者の埋まり率を上げつつトークンを増やさないため):
  - 全文(最大6万字)ではなく、<main>/<article> の本文から登壇者系キーワード周辺の行だけを
    抜粋して保存する(1件あたり 2〜8 千字。以前の 1/5〜1/10)
  - 上限を 5 件から LIMIT 件に引き上げ(抜粋なので合計トークンは以前と同等以下)
  - 対象を importance >= MIN_IMPORTANCE かつ開催 MAX_DAYS_AHEAD 日以内に絞る
    (importance 0 の研究セミナーは題名に報告者が入っていてほぼ埋まっている)
  - 再確認は固定間隔ではなく**開催日基準**(RECHECK_DAYS_BEFORE 日前を通過するたび)
  - 本文が薄いページ(THIN_CHARS 未満)は「Programme / Agenda / Conference details」等の
    リンクを 1 ホップだけ辿る(Gerzensee → CEPR のように本体が別サイトにある場合)
  - 403/JS殻は headless Chromium で 1 回だけ描画を試す(使えない環境では自動で諦める)

候補の条件(すべて満たすもの):
  - data/events.json に収載済みで、まだ終わっていない(date_end または date_start が今日以降)
  - importance >= MIN_IMPORTANCE、date_start が今日から MAX_DAYS_AHEAD 日以内
  - speakers が空/未記録
  - url が http(s) で、一覧ページ(sources.yaml の url・fetch_hints の alt_urls)や
    サイトのトップ(パスが "/" だけ)ではない
  - 状態台帳(data/detail_state.json)上、未試行か、前回試行のあとに開催日基準の再確認時点
    (RECHECK_DAYS_BEFORE)を通過していて、試行回数が MAX_TRIES 未満
優先順位: 未試行 → importance の高い順 → 開催日の近い順。

出力:
  - data/cache/detail--<event_id>.txt … 詳細ページの登壇者関連抜粋。コミットしない
  - data/cache/detail_manifest.json … 取得した各イベントの薄いレコードの雛形
    ({id, title, date_start, themes, source, url, speakers: []} + cache パス)。
    エージェント(サブエージェント)は雛形の speakers だけを埋めて new_events.json に入れる。
    title・date_start を書き換えないこと(既存イベントへの一致に使う)
  - data/detail_state.json … URL別の試行台帳。このスクリプトだけが書く。コミット対象

使い方:
    python3 scripts/fetch_details.py             # 最大 LIMIT 件を取得
    python3 scripts/fetch_details.py --limit 3   # 件数を変える
    python3 scripts/fetch_details.py --dry-run   # 候補の一覧だけ出して取得も台帳更新もしない
    python3 scripts/fetch_details.py --profile uk  # 英国モード(data/uk/ の収載分・台帳)
"""

import argparse
import concurrent.futures
import json
import re
from datetime import date, timedelta
from pathlib import Path

import os
import sys

# --profile uk  ==  SR_PROFILE=uk  (AGENTS.md「プロファイル」参照)。
# radar_lib はプロファイルを import 時に確定するため、import より前に環境変数へ写す。
_argv = sys.argv[1:]
for _i, _a in enumerate(_argv):
    if _a == "--profile" and _i + 1 < len(_argv):
        os.environ["SR_PROFILE"] = _argv[_i + 1]
    elif _a.startswith("--profile="):
        os.environ["SR_PROFILE"] = _a.split("=", 1)[1]

sys.path.insert(0, str(Path(__file__).resolve().parent))
from radar_lib import DATA_DIR, DATA_FILE, PROFILE_ID, ROOT, TODAY, load_json, parse_sources  # noqa: E402
from fetch_all import (CACHE_DIR, HINTS_FILE, MIN_TEXT_CHARS, classify_failure, decode,  # noqa: E402
                       fetch, html_to_text, render_with_chromium)

STATE_FILE = DATA_DIR / "detail_state.json"     # プロファイル別(data/uk/ 等)
MANIFEST_FILE = CACHE_DIR / "detail_manifest.json"
LIMIT = 15                  # 1日あたりの取得上限(抜粋保存なので 15 件で旧 5 件分以下のトークン)
MIN_IMPORTANCE = 1          # これ未満(研究セミナー等)は対象外
MAX_DAYS_AHEAD = 90         # 開催がこれより先のイベントは対象外(登壇者は直前に公表される)
RECHECK_DAYS_BEFORE = (45, 21, 7)   # 開催日基準の再確認時点(この日数前を通過するたびに再取得)
RETRY_DAYS = 21             # date_start が無い場合の予備ルール(固定間隔)
MAX_TRIES = 4               # 同じURLの試行回数上限(初回 + 再確認3回)
EXCERPT_MAX_CHARS = 8_000   # 抜粋の上限
THIN_CHARS = 3_000          # 本文がこれ未満なら「薄いページ」として 1 ホップ辿る
WINDOW_LINES = 6            # キーワード行の前後に残す行数
MAX_CHROMIUM = 5            # 1 回の実行で Chromium 描画を試す上限(1 件 10〜20 秒かかる)
STATE_KEEP_DAYS = 180       # 収載から外れたイベントの台帳エントリを残す日数

# 登壇者が書かれている箇所の目印(英・独・仏・伊)。行単位で照合する
SPEAKER_KW = re.compile(
    r"(speakers?\b|keynote|panel|chair\b|chaired|moderat|discussant|fireside|"
    r"opening remarks|welcome address|closing remarks|presenter|lecturer|"
    r"referent|vortragende|redner|sprecher|podium|begrüßung|grußwort|moderation|"
    r"programm\b|programme\b|program\b|agenda|intervenant|relatore|"
    r"\bProf\.|\bDr\.|\bProfessor\b|Governor|Executive Board|Vorstand|Präsident|President)",
    re.I)
# リンクだけの行(ナビゲーション項目)で有効とみなす強い目印
STRONG_KW = re.compile(
    r"(speakers?\b|keynote|panel|moderat|discussant|referent|vortragende|redner|sprecher|podium)", re.I)
# 薄いページから辿るリンクの目印(リンク文言または URL)
FOLLOW_KW = re.compile(
    r"(programme|program\b|agenda|conference details|event details|details|schedule|"
    r"speakers|more information|further information|event page|read more|weiterlesen|"
    r"zum programm|mehr erfahren)", re.I)


def norm_url(u):
    return re.sub(r"[?#].*$", "", (u or "").strip()).rstrip("/").lower()


def is_site_root(u):
    """パスもクエリも無いサイトトップか(https://example.org/ など)。
    WordPress の https://example.org/?p=123 のようなクエリ付き個別ページはトップ扱いにしない。"""
    return bool(re.fullmatch(r"https?://[^/?#]+/?", (u or "").strip()))


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


def source_hint(name):
    hints = load_json(HINTS_FILE, {})
    h = hints.get(name) if isinstance(hints, dict) else None
    return h if isinstance(h, dict) else {}


def is_upcoming(ev):
    last = ev.get("date_end") or ev.get("date_start") or ""
    return last >= TODAY.isoformat()


def days_to_event(ev, on=None):
    try:
        return (date.fromisoformat(ev.get("date_start") or "") - (on or TODAY)).days
    except ValueError:
        return None


def eligible(entry, ev):
    """台帳エントリから見て再試行してよいか。未試行なら True。
    開催日基準: 前回試行のあとに RECHECK_DAYS_BEFORE のいずれかの時点を通過していれば再試行。
    (例: 前回が開催 50 日前なら 45 日前を過ぎた日に、次は 21 日前、7 日前に再確認)"""
    if not entry:
        return True, "未試行"
    if entry.get("tries", 0) >= MAX_TRIES:
        return False, "試行上限"
    try:
        last = date.fromisoformat(entry.get("last") or "")
    except ValueError:
        return True, "台帳不正"
    now_d = days_to_event(ev)
    if now_d is None:
        ok = last + timedelta(days=RETRY_DAYS) <= TODAY
        return ok, "固定間隔" if ok else "待機"
    last_d = (date.fromisoformat(ev["date_start"]) - last).days
    for cp in RECHECK_DAYS_BEFORE:
        if last_d > cp >= now_d:
            return True, f"開催{cp}日前の再確認"
    return False, "待機"


def pick_candidates(events, state, limit):
    listing = listing_urls()
    cands = []
    for ev in events:
        url = ev.get("url") or ""
        if not url.startswith(("http://", "https://")):
            continue
        if ev.get("speakers") or not is_upcoming(ev):
            continue
        if (ev.get("importance") or 0) < MIN_IMPORTANCE:
            continue
        d = days_to_event(ev)
        if d is not None and d > MAX_DAYS_AHEAD:
            continue
        nu = norm_url(url)
        if nu in listing or is_site_root(url):
            continue
        entry = state.get(nu)
        ok, why = eligible(entry, ev)
        if not ok:
            continue
        cands.append((0 if not entry else 1, -(ev.get("importance") or 0),
                      ev.get("date_start") or "", ev, why))
    cands.sort(key=lambda c: c[:3])
    return [(c[3], c[4]) for c in cands[:limit]]


# ---------------------------------------------------------------- 本文抜粋

def body_text(html, base_url):
    """<main>/<article> があればその中身だけ、無ければ全体をテキスト化する。
    戻り値 (text, mode)。"""
    for tag in ("main", "article"):
        m = re.search(rf"(?is)<{tag}\b[^>]*>.*?</{tag}>", html)
        if m:
            inner = html_to_text(m.group(0), base_url, _allow_main_fallback=False)
            if len(inner) >= MIN_TEXT_CHARS:
                return inner, tag
    return html_to_text(html, base_url), "full"


def cut_to_title(text, title):
    """ナビゲーションは見出し(イベント題名)より前に並ぶことが多いので、題名が本文中に
    現れる最初の行(先頭の <title> 行を除く)より前を落とす。見つからなければそのまま。"""
    if not title:
        return text
    key = re.sub(r"\s+", " ", title).strip().lower()[:40]
    if len(key) < 12:
        return text
    lines = text.split("\n")
    for i, line in enumerate(lines[1:], start=1):
        if key in re.sub(r"\s+", " ", line).lower() and "[http" not in line:
            # ナビ(「題名 [URL]」の形のリンク行)は飛ばし、見出しとして現れる行で切る
            return "\n".join(lines[i:])
    return text


def excerpt(text, title):
    """登壇者系キーワードを含む行の前後 WINDOW_LINES 行だけを残し、EXCERPT_MAX_CHARS に収める。
    キーワードが無いページは先頭から EXCERPT_MAX_CHARS 字。戻り値 (抜粋, 元の字数, 抜粋前の字数)。"""
    full_len = len(text)
    text = cut_to_title(text, title)
    lines = [ln for ln in text.split("\n")]
    keep = set()
    for i, ln in enumerate(lines):
        if not ln.strip():
            continue
        link_only = bool(re.fullmatch(r"\s*[^\[\]]{0,80}\[https?://[^\]]+\]\s*", ln))
        hit = STRONG_KW.search(ln) if link_only else SPEAKER_KW.search(ln)
        if hit:
            lo, hi = max(0, i - WINDOW_LINES), min(len(lines), i + WINDOW_LINES + 1)
            keep.update(range(lo, hi))
    if keep:
        out, prev = [], -1
        for i in sorted(keep):
            if not lines[i].strip():
                continue
            if prev >= 0 and i > prev + 1:
                out.append("…")
            if not out or out[-1] != lines[i]:
                out.append(lines[i])
            prev = i
        joined = "\n".join(out)
    else:
        joined = "\n".join(ln for ln in lines if ln.strip())
    return joined[:EXCERPT_MAX_CHARS], full_len, len(joined)


def follow_link(text, base_url, listing):
    """薄いページから辿る候補リンクを 1 本選ぶ。「テキスト [URL]」の形から探す。"""
    for m in re.finditer(r"([^\n\[\]]{0,80})\[(https?://[^\]\s]+)\]", text):
        label, url = m.group(1).strip(), m.group(2)
        if norm_url(url) == norm_url(base_url) or norm_url(url) in listing:
            continue
        if re.search(r"\.(pdf|ics|jpg|png)$", url, re.I):
            continue
        if FOLLOW_KW.search(label) or FOLLOW_KW.search(url.rsplit("/", 1)[-1]):
            return url
    return None


class Fetcher:
    def __init__(self):
        self.chromium_left = MAX_CHROMIUM
        self.listing = listing_urls()

    def get(self, url):
        code, final_url, body, charset = fetch(url)
        html = decode(body, charset) if body else ""
        return code, final_url or url, html

    def get_with_chromium(self, url, hint):
        """403/JS殻のとき、Chromium 描画を 1 回だけ試す。使えない環境では以後試さない。"""
        if self.chromium_left <= 0:
            return None
        self.chromium_left -= 1
        got = render_with_chromium(url)
        if not got:
            self.chromium_left = 0   # 環境で使えない(or 落ちた)なら以後は試さない
            return None
        return got[2].decode("utf-8", "ignore")

    def run(self, ev):
        notes = []
        code, final_url, html = self.get(ev["url"])
        text, mode = body_text(html, final_url) if html else ("", "none")
        fail = classify_failure(code, text)
        if fail in ("FAIL-BLOCKED", "FAIL-THIN", "FAIL-HTTP") and code != 404:
            hint = source_hint(ev.get("source") or "")
            html2 = self.get_with_chromium(ev["url"], hint)
            if html2:
                t2, m2 = body_text(html2, ev["url"])
                if not classify_failure(200, t2):
                    code, final_url, text, mode, fail = 200, ev["url"], t2, m2, None
                    notes.append("Chromium で描画して取得")
        if not fail and len(text) < THIN_CHARS:
            nxt = follow_link(text, final_url, self.listing)
            if nxt:
                c2, f2, h2 = self.get(nxt)
                t2, m2 = body_text(h2, f2) if h2 else ("", "none")
                if not classify_failure(c2, t2) and len(t2) > len(text):
                    notes.append(f"本文が薄いため 1 ホップ辿った: {f2}")
                    text, mode, final_url = t2, m2, f2
        return ev, code, final_url, text, mode, fail, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=LIMIT)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--profile", default=PROFILE_ID,
                    help="プロファイル de/uk(既定 de。SR_PROFILE と同義。冒頭で処理済み)")
    args = ap.parse_args()

    store = load_json(DATA_FILE, {})
    events = store.get("events", []) if isinstance(store, dict) else []
    state = load_json(STATE_FILE, {})
    if not isinstance(state, dict):
        state = {}

    chosen = pick_candidates(events, state, max(0, args.limit))
    print(f"登壇者未記録の詳細ページ取得 [profile={PROFILE_ID}]: 候補 {len(chosen)} 件"
          f"(上限 {args.limit}・importance>={MIN_IMPORTANCE}・開催{MAX_DAYS_AHEAD}日以内)")
    if not chosen:
        print("  (候補なし。抽出対象の詳細ページはありません)")
        if not args.dry_run:
            MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
            MANIFEST_FILE.write_text("[]\n", encoding="utf-8")
        return
    if args.dry_run:
        for ev, why in chosen:
            print(f"  imp{ev.get('importance')} {ev.get('date_start')} ({why}) "
                  f"{ev.get('title')[:60]}  {ev['url']}")
        return

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    fetcher = Fetcher()
    # 通常取得は並列、Chromium は Fetcher 内で直列に数を絞る(Playwright の同時起動を避ける)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        results = list(ex.map(fetcher.run, [ev for ev, _ in chosen]))
    total_chars = 0
    for ev, code, final_url, text, mode, fail, notes in results:
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
        ex_text, full_len, pre_len = excerpt(text, ev.get("title") or "")
        total_chars += len(ex_text)
        cache = CACHE_DIR / f"detail--{ev['id']}.txt"
        head = [f"# event_id: {ev['id']}", f"# title: {ev.get('title')}",
                f"# date_start: {ev.get('date_start')}", f"# url: {final_url}",
                f"# fetched: {TODAY}",
                f"# note: 本文({mode}、{full_len:,}字)から登壇者関連の行を抜粋({len(ex_text):,}字)。"
                "抜粋に無い名前を補わないこと"]
        head += [f"# note: {n}" for n in notes]
        cache.write_text("\n".join(head) + "\n\n" + ex_text + "\n", encoding="utf-8")
        manifest.append({"cache": str(cache.relative_to(ROOT)),
                         "excerpt_chars": len(ex_text),
                         "record": {"id": ev["id"], "title": ev.get("title"),
                                    "date_start": ev.get("date_start"),
                                    "themes": ev.get("themes"), "source": ev.get("source"),
                                    "url": ev.get("url"), "speakers": []}})
        extra = f"  [{mode} {full_len:,}→{len(ex_text):,}字]" + ("" if not notes else "  " + "; ".join(notes))
        print(line + f"  -> {cache.relative_to(ROOT)}" + extra)
    print(f"  抜粋合計 {total_chars:,} 字(キャッシュ {len(manifest)} 件)")

    # 台帳の整理: 収載から外れて久しいエントリは落とす
    live_ids = {e.get("id") for e in events}
    cutoff = (TODAY - timedelta(days=STATE_KEEP_DAYS)).isoformat()
    state = {u: e for u, e in state.items()
             if e.get("event_id") in live_ids or (e.get("last") or "") >= cutoff}
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                          encoding="utf-8")
    MANIFEST_FILE.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
                             encoding="utf-8")


if __name__ == "__main__":
    main()
