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
                       dedupe_events, load_json, merge, render_html, render_ics,
                       split_archive)


def main():
    new_events = load_json(NEW_FILE, [])
    if not isinstance(new_events, list):
        sys.exit("data/new_events.json はJSON配列である必要があります。")
    statuses = load_json(STATUS_FILE, [])

    store = load_json(DATA_FILE, {"events": []})
    events, added = merge(store.get("events", []), new_events)
    events, removed = dedupe_events(events)
    events, to_archive = split_archive(events)

    if to_archive:
        arch = load_json(ARCHIVE_FILE, {"events": []})
        arch["events"] += to_archive
        ARCHIVE_FILE.write_text(json.dumps(arch, ensure_ascii=False, indent=1),
                                encoding="utf-8")

    DATA_FILE.write_text(json.dumps({"events": events}, ensure_ascii=False, indent=1),
                         encoding="utf-8")
    render_html(events, statuses)
    render_ics(events)

    # 取込済みの入力ファイルは空に戻す(次回実行の取り違え防止)
    NEW_FILE.write_text("[]", encoding="utf-8")

    print(f"完了: 新規 {added} 件 / 掲載中 {len(events)} 件 / "
          f"アーカイブ移動 {len(to_archive)} 件 / 重複除去 {removed} 件")


if __name__ == "__main__":
    main()
