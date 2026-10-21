#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_status.py: 巡回ステータスの品質ゲート(AGENTS.md B手順5)。

書き出し直後の data/status.json を、前回コミット時点(git HEAD)の同ファイルと比較し、
巡回品質の劣化を疑わせる兆候を警告する:

  (a) 失敗ソース数の急増(前回比 +5 以上)
  (b) `tried:` 記録のない失敗エントリ(フォールバック・ラダー不履行の疑い)
  (c) 総取得件数の急減(前回比 -40% 以上。前回が20件未満の場合は判定しない)
  (d) 本日の fetch_all.py で NEW/CHANGED と判定されたのに status.json に記録がない
      ソース(=抽出の取りこぼし。このままコミットすると fetch_state.json のハッシュ
      更新により、次にページが変わるまでそのソースのイベントを拾えなくなる)
  (e) 本日初収載の importance 2 以上のイベントで url が一覧ページ/サイトトップのもの
      (=詳細ページが読めず、fetch_details.py の登壇者補完が構造的に不可能。
      fetch_hints.json の該当ソースに no_detail_pages: true があれば除外)

警告が1件でもあれば終了コード1(なければ0)。警告が出た場合の対応は AGENTS.md B手順5を
参照(該当ソースの巡回をやり直すか、やり直し不要と判断した理由を実行報告に書く)。
標準ライブラリのみで動作する。
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

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
from radar_lib import DATA_DIR, DATA_FILE, PROFILE_ID, ROOT, STATUS_FILE  # noqa: E402

FETCH_STATE_FILE = DATA_DIR / "fetch_state.json"
# git show HEAD:<path> 用のリポジトリ相対パス(de: data/status.json / uk: data/uk/status.json)
STATUS_REL = STATUS_FILE.relative_to(ROOT).as_posix()
TODAY = datetime.now(ZoneInfo("Europe/Berlin")).date().isoformat()

# 巡回ソースではない特殊行(比較・tried判定の対象外)
SPECIAL_ROWS = {"web検索(discovery)", "手動取込"}

FAIL_JUMP_THRESHOLD = 5      # 失敗数がこれ以上増えたら警告
FOUND_DROP_RATIO = 0.40      # 総取得件数がこの割合以上減ったら警告
FOUND_DROP_MIN_PREV = 20     # 前回の総取得件数がこれ未満なら件数急減の判定をしない

# 2b(死にURL)対応中、および恒常ブロック(fetch_hints の permanent_block。週次でのみ
# 再確認する)のエントリは tried: が無くても手順不履行とはみなさない
TRIED_EXEMPT_MARKERS = ("URL差し替え", "要整理", "恒常ブロック")


def load_current():
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"{STATUS_REL} が存在しない。手順4を先に実行すること。")
    except json.JSONDecodeError as e:
        sys.exit(f"{STATUS_REL} がJSONとして読めない: {e}")


def load_previous():
    """前回コミット時点の status.json。取れなければ None(初回実行など)。
    HEAD にまだファイルが無い場合(プロファイル初回の巡回)は空リストとして扱い、
    比較チェックは「前回ゼロ」から行う。"""
    try:
        out = subprocess.run(
            ["git", "show", f"HEAD:{STATUS_REL}"],
            cwd=ROOT, capture_output=True, text=True)
        if out.returncode != 0:
            err = out.stderr or ""
            if "does not exist" in err or "exists on disk, but not in" in err:
                return []        # HEAD に未登録(初回)
            return None
        return json.loads(out.stdout)
    except Exception:
        return None


def crawl_rows(entries):
    return [e for e in entries if e.get("name") not in SPECIAL_ROWS]


def main():
    current = crawl_rows(load_current())
    warnings = []

    # (b) tried: 記録のない失敗エントリ
    missing_tried = [
        e["name"] for e in current
        if not e.get("ok")
        and "tried:" not in (e.get("error") or "")
        and not any(m in (e.get("error") or "") for m in TRIED_EXEMPT_MARKERS)
    ]
    if missing_tried:
        warnings.append(
            "tried:(試行記録)のない失敗エントリが {} 件ある。フォールバック・ラダー"
            "(AGENTS.md B手順2a)を完遂したか確認し、未実施なら巡回をやり直すこと:\n    - "
            .format(len(missing_tried)) + "\n    - ".join(missing_tried))

    # (d) fetch_all.py が本日 NEW/CHANGED と判定したのに status.json に記録がないソース
    try:
        fetch_state = json.loads(FETCH_STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        fetch_state = {}
    status_names = {e.get("name") for e in current}
    unrecorded = [
        name for name, s in fetch_state.items()
        if isinstance(s, dict) and s.get("verdict") in ("NEW", "CHANGED")
        and s.get("last_fetch") == TODAY and name not in status_names
    ]
    if unrecorded:
        warnings.append(
            "fetch_all.py が本日 NEW/CHANGED と判定したのに status.json に記録がない"
            "ソースが {} 件ある。抽出を取りこぼしたまま commit しないこと:\n    - "
            .format(len(unrecorded)) + "\n    - ".join(unrecorded))

    # (e) 本日初収載の importance>=2 イベントで url が一覧ページ/サイトトップのもの
    #     (詳細ページが読めず、手順1.6 の登壇者補完が構造的に不可能になる。AGENTS.md スキーマ `url`)
    try:
        from fetch_details import is_site_root, listing_urls, norm_url, source_hint
        store = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        listing = listing_urls()
        bad_url = []
        for e in (store.get("events", []) if isinstance(store, dict) else []):
            if (e.get("importance") or 0) < 2 or e.get("first_seen") != TODAY:
                continue
            nu = norm_url(e.get("url"))
            if nu in listing or is_site_root(e.get("url")):
                if source_hint(e.get("source") or "").get("no_detail_pages"):
                    continue
                bad_url.append("{} ({}): {}".format(e.get("title"), e.get("source"), e.get("url")))
    except Exception as ex:  # 台帳や設定の不備で品質ゲート自体を止めない
        print("check_status: (e) url チェックをスキップ: {}".format(ex))
        bad_url = []
    if bad_url:
        warnings.append(
            "本日初収載の importance 2 以上のイベント {} 件で、url が一覧ページまたはサイトトップに"
            "なっている(詳細ページが読めず登壇者補完ができない)。一覧にある個別ページのURLに直すこと。"
            "サイトに個別ページが無い場合だけ fetch_hints.json の該当ソースに "
            "\"no_detail_pages\": true を付ける:\n    - ".format(len(bad_url)) + "\n    - ".join(bad_url))

    prev_raw = load_previous()
    if prev_raw is None:
        print("check_status: 前回の status.json が取得できないため、比較チェックはスキップ。")
    else:
        prev = crawl_rows(prev_raw)
        cur_fails = {e["name"] for e in current if not e.get("ok")}
        prev_fails = {e["name"] for e in prev if not e.get("ok")}

        # (a) 失敗数の急増
        if len(cur_fails) - len(prev_fails) >= FAIL_JUMP_THRESHOLD:
            new_fails = sorted(cur_fails - prev_fails)
            warnings.append(
                "失敗ソース数が急増している({} → {})。新たに失敗になったソース:\n    - "
                .format(len(prev_fails), len(cur_fails)) + "\n    - ".join(new_fails))

        # (c) 総取得件数の急減
        cur_found = sum(e.get("found") or 0 for e in current)
        prev_found = sum(e.get("found") or 0 for e in prev)
        if prev_found >= FOUND_DROP_MIN_PREV and cur_found < prev_found * (1 - FOUND_DROP_RATIO):
            warnings.append(
                "総取得件数が急減している({} → {})。取得手順が省略されていないか確認すること。"
                .format(prev_found, cur_found))

    if warnings:
        print("check_status: 警告 {} 件\n".format(len(warnings)))
        for i, w in enumerate(warnings, 1):
            print("[{}] {}\n".format(i, w))
        print("対応方法は AGENTS.md B手順5 を参照。警告を黙殺して commit しないこと。")
        sys.exit(1)

    print("check_status [profile={}]: 問題なし(失敗 {} 件 / 巡回 {} ソース)。".format(
        PROFILE_ID, sum(1 for e in current if not e.get("ok")), len(current)))


if __name__ == "__main__":
    main()
