#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ingest.py: 実行エージェント(Claude Code / Codex)が書き出した data/new_events.json を取り込み、
検証・重複排除して data/events.json を更新し、docs/ を再生成する。

使い方:  python3 scripts/ingest.py
入力:    data/new_events.json  … 本日抽出したイベントのJSON配列
         data/status.json      … 巡回ステータスのJSON配列
出力:    data/events.json, data/archive.json, docs/index.html, docs/calendar.ics
標準ライブラリのみで動作する(pip install 不要)。
"""

import json
import sys

from radar_lib import (ARCHIVE_FILE, DATA_FILE, NEW_FILE, STATUS_FILE,
                       apply_aliases, apply_flagship, apply_overrides, dedupe_events,
                       load_json, mark_crawl_start, merge, parse_sources, region_ok,
                       render_html, render_ics, split_archive, update_changelog)

KNOWN_FILE = DATA_FILE.parent / "known_events.json"


def write_known_digest(events):
    """巡回エージェント照合用のコンパクトな既知イベント台帳(AGENTS.md B手順2参照)。

    巡回時はこの台帳に照らして「新規または変更のあるイベントだけ」を
    data/new_events.json に出力する(既知で無変化のイベントは再出力しない)。
    events.json(774KB超)を直接読ませないための小さな写しであり、
    ingest.py だけが生成する。1イベント1行のJSONで、grepでも照合できる。"""
    keys = ("source", "title", "date_start", "date_end", "url")
    rows = sorted(
        ({k: ev.get(k) for k in keys} for ev in events),
        key=lambda r: (r.get("date_start") or "", r.get("title") or ""))
    body = ",\n  ".join(
        json.dumps(r, ensure_ascii=False, separators=(", ", ": ")) for r in rows)
    KNOWN_FILE.write_text(
        '{\n "_readme": "既知イベントの照合用ダイジェスト。ingest.py が自動生成する。'
        '直接編集しない。巡回時はここに載っているイベントを new_events.json に再出力しない'
        '(日付・会場等が変わった場合を除く)。",\n'
        f' "events": [\n  {body}\n ]\n}}\n', encoding="utf-8")


def main():
    # --mark-start: 日次巡回の開始時刻だけを記録して終了する(AGENTS.md 手順1の冒頭)。
    if "--mark-start" in sys.argv[1:]:
        mark_crawl_start()
        return
    # --maintenance: 巡回を伴わない保守作業(UI改修など)での再生成。
    # サイトの LAST UPDATE(最終巡回時刻)を進めない。日次更新ではフラグなしで実行する。
    maintenance = "--maintenance" in sys.argv[1:]
    new_events = load_json(NEW_FILE, [])
    if not isinstance(new_events, list):
        sys.exit("data/new_events.json はJSON配列である必要があります。")
    statuses = load_json(STATUS_FILE, [])

    # 開催地不問の定点(sources.yaml で anywhere: true)の name 集合。
    anywhere_sources = {s["name"] for s in parse_sources()["sources"] if s.get("anywhere")}

    store = load_json(DATA_FILE, {"events": []})
    events, added, changes = merge(store.get("events", []), new_events)
    events, removed = dedupe_events(events)

    # 重複ID→正本IDの恒久台帳(data/aliases.json)を適用する。similar_event を
    # すり抜けた既知の重複を毎回正本IDへ統合し、次回巡回での復活を防ぐ。
    events, aliased = apply_aliases(events)

    # フラッグシップ(旗艦)会議は既存・新規を問わず毎回 importance の下限を強制する
    # (格下げ防止・既存データへの遡及適用の両方を兼ねる)。
    events = [apply_flagship(ev) for ev in events]

    # 地域外(対象地域外・ECB/BIS主催でもなく・anywhere定点でもない)イベントを除去する。
    # 既存データの掃除としても、新規追加分のフィルタとしても毎回効く。
    before = len(events)
    events = [ev for ev in events if region_ok(ev, anywhere_sources)]
    region_removed = before - len(events)

    events, to_archive = split_archive(events)

    if to_archive:
        arch = load_json(ARCHIVE_FILE, {"events": []})
        arch["events"] += to_archive
        ARCHIVE_FILE.write_text(json.dumps(arch, ensure_ascii=False, indent=1),
                                encoding="utf-8")

    DATA_FILE.write_text(json.dumps({"events": events}, ensure_ascii=False, indent=1),
                         encoding="utf-8")
    write_known_digest(events)

    # 追加・実質更新の履歴(data/changelog.json)を更新し、HTML埋め込み用の窓を得る。
    changelog = update_changelog(changes)

    # レンダリング直前にユーザー管理の手動上書き(data/overrides.json)を適用する。
    # events (data/events.json への保存分)には反映しない = オーバーライドは表示専用。
    render_events = apply_overrides([dict(ev) for ev in events])
    render_html(render_events, statuses, changelog=changelog, maintenance=maintenance)
    render_ics(render_events)

    # 取込済みの入力ファイルは空に戻す(次回実行の取り違え防止)
    NEW_FILE.write_text("[]", encoding="utf-8")

    print(f"完了: 新規 {added} 件 / 掲載中 {len(events)} 件 / "
          f"アーカイブ移動 {len(to_archive)} 件 / 重複除去 {removed} 件 / "
          f"エイリアス統合 {aliased} 件 / 地域外除去 {region_removed} 件 / "
          f"履歴記録 追加{len(changes['added'])}件・更新{len(changes['updated'])}件")


if __name__ == "__main__":
    main()
