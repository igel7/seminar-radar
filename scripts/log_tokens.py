#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
log_tokens.py: 1回の巡回(Claude Code セッション)が消費したトークン量を
data/token_usage.json に追記する。

Claude Code は実行中のセッションの発話ログを
`~/.claude/projects/<cwdをエンコードしたディレクトリ>/<session-id>.jsonl`
にJSON Lines形式で書き出しており、assistant の各行に API が返した `usage`
(input / output / cache_creation / cache_read など)が入っている。
このスクリプトはそれを合算して1日1レコードとして記録する。

使い方:
    python3 scripts/log_tokens.py                 # 現在のセッション分を記録(AGENTS.md B手順5.5)
    python3 scripts/log_tokens.py --dry-run       # 記録せず内容だけ表示
    python3 scripts/log_tokens.py --summary       # 記録済みの直近20件を一覧表示
    python3 scripts/log_tokens.py --transcript PATH   # ログの場所を明示指定
    python3 scripts/log_tokens.py --no-render     # docs/index.html を作り直さない

注意(重要):
  このスクリプト自身がセッションの途中で動くため、**実行後のターン
  (コミット・プッシュ・実行報告)の消費分は記録に含まれない。**
  記録値は「その日の巡回のほぼ全量」であって厳密な総量ではない。
  レコードの `partial` フラグがこの意味を表す。

  記録後、更新履歴(サイトの News 欄)に当日のトークン数を載せるため
  `docs/index.html` を組み直す。ingest.py(手順5)の時点ではまだこの記録が
  存在しないため、ここで組み直さないと当日分だけ数字が出ない。
  イベントデータには一切触れず、LAST UPDATE も進めない(--no-render で抑止可)。

標準ライブラリのみで動作する(pip install 不要)。
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
USAGE_FILE = ROOT / "data" / "token_usage.json"
TZ = ZoneInfo("Europe/Berlin")

# 1レコードあたりのトークン集計キー(JSONの並び順もこの順にする)
COUNTERS = ("input_tokens", "cache_creation_tokens", "cache_read_tokens", "output_tokens")


def projects_dir(cwd: Path) -> Path:
    """Claude Code が発話ログを置くディレクトリ。cwd の英数字以外を '-' に置換した名前。"""
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(cwd))
    return Path.home() / ".claude" / "projects" / slug


def find_transcript(explicit: str | None) -> tuple[Path | None, str | None]:
    """発話ログのファイルと session_id を返す。見つからなければ (None, None)。"""
    if explicit:
        p = Path(explicit).expanduser()
        return (p, p.stem) if p.is_file() else (None, None)

    sid = os.environ.get("CLAUDE_CODE_SESSION_ID")
    candidates = [projects_dir(Path.cwd()), projects_dir(ROOT)]
    if sid:
        for d in candidates:
            p = d / f"{sid}.jsonl"
            if p.is_file():
                return p, sid
        # cwd から算出したディレクトリ名が合わない場合に備えて全プロジェクトを探す
        base = Path.home() / ".claude" / "projects"
        if base.is_dir():
            for p in base.glob(f"*/{sid}.jsonl"):
                return p, sid
    # session_id が取れない環境向けのフォールバック: 最も新しいログを使う
    for d in candidates:
        if d.is_dir():
            logs = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
            if logs:
                return logs[0], logs[0].stem
    return None, None


def _iter_entries(path: Path):
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue    # 書き込み途中の行などは黙って飛ばす


def collect(transcript: Path, session_id: str | None) -> dict:
    """発話ログを走査して usage を合算する。

    サブエージェント(Task/Agent ツール)の消費分は、同じセッションIDを持つ行、
    または同じプロジェクトディレクトリ内でこのセッションの時間帯に書かれた
    sidechain の行として現れるため、両方を拾う。
    """
    totals = dict.fromkeys(COUNTERS, 0)
    per_model: dict[str, dict] = {}
    seen: set[str] = set()          # uuid で重複計上を防ぐ
    turns = sidechain_turns = 0
    web_search = web_fetch = 0
    first_ts = last_ts = None

    def account(entry: dict) -> None:
        nonlocal turns, sidechain_turns, web_search, web_fetch, first_ts, last_ts
        usage = (entry.get("message") or {}).get("usage")
        if not isinstance(usage, dict):
            return
        uid = entry.get("uuid")
        if uid:
            if uid in seen:
                return
            seen.add(uid)
        model = (entry.get("message") or {}).get("model") or "unknown"
        bucket = per_model.setdefault(model, dict.fromkeys(COUNTERS, 0) | {"turns": 0})
        values = {
            "input_tokens": usage.get("input_tokens", 0),
            "cache_creation_tokens": usage.get("cache_creation_input_tokens", 0),
            "cache_read_tokens": usage.get("cache_read_input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
        }
        for key, value in values.items():
            if isinstance(value, int):
                totals[key] += value
                bucket[key] += value
        bucket["turns"] += 1
        turns += 1
        if entry.get("isSidechain"):
            sidechain_turns += 1
        server = usage.get("server_tool_use") or {}
        web_search += server.get("web_search_requests", 0) or 0
        web_fetch += server.get("web_fetch_requests", 0) or 0
        ts = entry.get("timestamp")
        if ts:
            first_ts = ts if first_ts is None or ts < first_ts else first_ts
            last_ts = ts if last_ts is None or ts > last_ts else last_ts

    own = [e for e in _iter_entries(transcript)]
    for entry in own:
        account(entry)

    # 同じディレクトリの別ファイルに書かれたサブエージェントのログを、
    # このセッションの時間帯(first_ts 以降)に限って合算する。
    if first_ts:
        for other in sorted(transcript.parent.glob("*.jsonl")):
            if other == transcript:
                continue
            for entry in _iter_entries(other):
                same_session = session_id and entry.get("sessionId") == session_id
                in_window = entry.get("isSidechain") and (entry.get("timestamp") or "") >= first_ts
                if same_session or in_window:
                    account(entry)

    record = {
        "session_id": session_id,
        "turns": turns,
        "sidechain_turns": sidechain_turns,
        **totals,
        "total_input_tokens": totals["input_tokens"] + totals["cache_creation_tokens"]
                              + totals["cache_read_tokens"],
        "total_tokens": sum(totals.values()),
        # 1ターンあたりの平均コンテキストサイズ。この値が肥大している(例: 10万超)場合、
        # 文脈に大きなファイルや生HTMLを流し込んでいる兆候(AGENTS.md A-3/B の分業が
        # 機能していない疑い)なので、日次の傾向監視に使う。
        "avg_context_tokens": round(
            (totals["input_tokens"] + totals["cache_creation_tokens"]
             + totals["cache_read_tokens"]) / turns) if turns else 0,
        "web_search_requests": web_search,
        "web_fetch_requests": web_fetch,
        "first_message_at": first_ts,
        "last_message_at": last_ts,
        "models": per_model,
    }
    return record


def load_records() -> list:
    if not USAGE_FILE.exists():
        return []
    try:
        data = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        sys.exit(f"{USAGE_FILE} が壊れています。手で修復してください。")
    return data if isinstance(data, list) else []


def save_records(records: list) -> None:
    USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    USAGE_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=1) + "\n",
                          encoding="utf-8")


def upsert(records: list, record: dict) -> str:
    """同じ日・同じセッションの記録があれば置き換える(再実行しても二重に増えない)。"""
    for i, old in enumerate(records):
        same_session = record["session_id"] and old.get("session_id") == record["session_id"]
        same_day = old.get("date") == record["date"] and old.get("agent") == record["agent"]
        if same_session or same_day:
            records[i] = record
            return "updated"
    records.append(record)
    records.sort(key=lambda r: (r.get("date") or "", r.get("recorded_at") or ""))
    return "added"


def print_summary(limit: int) -> None:
    records = load_records()
    if not records:
        print("記録がまだありません。")
        return
    print(f"{'date':<12}{'agent':<8}{'turns':>6}{'output':>10}{'cache_read':>12}"
          f"{'total':>12}{'ctx/turn':>10}")
    for r in records[-limit:]:
        turns = r.get("turns", 0)
        ctx = r.get("avg_context_tokens") or (
            round(r.get("total_input_tokens", 0) / turns) if turns else 0)
        print(f"{r.get('date',''):<12}{r.get('agent',''):<8}{turns:>6}"
              f"{r.get('output_tokens',0):>10,}{r.get('cache_read_tokens',0):>12,}"
              f"{r.get('total_tokens',0):>12,}{ctx:>10,}")
    total = sum(r.get("total_tokens", 0) for r in records[-limit:])
    print(f"{'':<26}{'':>10}{'合計':>12}{total:>12,}")


def main() -> None:
    ap = argparse.ArgumentParser(description="巡回1回分のトークン消費量を記録する")
    ap.add_argument("--transcript", help="発話ログ(.jsonl)のパスを明示指定する")
    ap.add_argument("--agent", default="claude", help="実行エージェント名(既定: claude)")
    ap.add_argument("--date", help="記録する日付 YYYY-MM-DD(既定: 実行日)")
    ap.add_argument("--note", help="レコードに残す短いメモ")
    ap.add_argument("--dry-run", action="store_true", help="ファイルに書かずに内容を表示する")
    ap.add_argument("--no-render", action="store_true",
                    help="記録するだけで docs/index.html を作り直さない")
    ap.add_argument("--summary", nargs="?", type=int, const=20, metavar="N",
                    help="記録済みの直近N件(既定20)を表示して終了する")
    args = ap.parse_args()

    if args.summary is not None:
        print_summary(args.summary)
        return

    transcript, session_id = find_transcript(args.transcript)
    if transcript is None:
        # Codex Cloud など、Claude Code の発話ログが存在しない環境。
        # ここで失敗して日次更新を止める意味はないので、警告だけ出して正常終了する。
        print("発話ログが見つからないためトークン消費量を記録しませんでした"
              "(Claude Code 以外の環境と思われる)。", file=sys.stderr)
        return

    record = {
        "date": args.date or datetime.now(TZ).date().isoformat(),
        "agent": args.agent,
        "recorded_at": datetime.now(TZ).isoformat(timespec="seconds"),
        # このスクリプト実行後のターン(コミット・プッシュ・報告)は含まれない
        "partial": True,
        **collect(transcript, session_id),
    }
    if args.note:
        record["note"] = args.note

    if args.dry_run:
        print(json.dumps(record, ensure_ascii=False, indent=1))
        return

    records = load_records()
    action = upsert(records, record)
    save_records(records)
    print(f"{USAGE_FILE.relative_to(ROOT)} に {record['date']} の記録を{'追加' if action == 'added' else '更新'}しました: "
          f"合計 {record['total_tokens']:,} tokens "
          f"(出力 {record['output_tokens']:,} / キャッシュ読取 {record['cache_read_tokens']:,} / "
          f"{record['turns']} ターン)")

    if not args.no_render:
        rerender()


def rerender() -> None:
    """更新履歴に当日のトークン数を反映させるため docs/index.html を組み直す。
    再生成に失敗しても記録自体は済んでいるので、警告だけ出して終了コードは変えない
    (数字が1日分載らないことより、日次更新が止まる方が損失が大きい)。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import radar_lib
        radar_lib.rerender_html()
    except Exception as e:      # noqa: BLE001 - 表示上のおまけなので握りつぶす
        print(f"docs/index.html の再生成に失敗しました(記録は済んでいます): {e}",
              file=sys.stderr)
        return
    print("docs/index.html を組み直しました(更新履歴にトークン数を反映)。")


if __name__ == "__main__":
    main()
