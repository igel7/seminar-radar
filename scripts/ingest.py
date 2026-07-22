#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ingest.py: Claude(Routine)が書き出した data/new_events.json を取り込み、
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
                       apply_flagship, apply_overrides, dedupe_events, load_json,
                       merge, parse_sources, region_ok, render_html, render_ics,
                       split_archive)


def main():
    new_events = load_json(NEW_FILE, [])
    if not isinstance(new_events, list):
        sys.exit("data/new_events.json はJSON配列である必要があります。")
    statuses = load_json(STATUS_FILE, [])

    # 開催地不問の定点(sources.yaml で anywhere: true)の name 集合。
    anywhere_sources = {s["name"] for s in parse_sources()["sources"] if s.get("anywhere")}

    store = load_json(DATA_FILE, {"events": []})
    events, added = merge(store.get("events", []), new_events)
    events, removed = dedupe_events(events)

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

    # レンダリング直前にユーザー管理の手動上書き(data/overrides.json)を適用する。
    # events (data/events.json への保存分)には反映しない = オーバーライドは表示専用。
    render_events = apply_overrides([dict(ev) for ev in events])
    render_html(render_events, statuses)
    render_ics(render_events)

    # 取込済みの入力ファイルは空に戻す(次回実行の取り違え防止)
    NEW_FILE.write_text("[]", encoding="utf-8")

    print(f"完了: 新規 {added} 件 / 掲載中 {len(events)} 件 / "
          f"アーカイブ移動 {len(to_archive)} 件 / 重複除去 {removed} 件 / "
          f"地域外除去 {region_removed} 件")


if __name__ == "__main__":
    main()
