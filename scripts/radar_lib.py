#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_lib.py: seminar-radar の決定論的な処理(検証・重複排除・HTML/ICS生成)。
LLM(Claude)は抽出だけを担当し、データの整合性はこのコードが保証する。
"""

import hashlib
import json
import re
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "events.json"
NEW_FILE = ROOT / "data" / "new_events.json"
STATUS_FILE = ROOT / "data" / "status.json"
ARCHIVE_FILE = ROOT / "data" / "archive.json"
HTML_FILE = ROOT / "docs" / "index.html"
ICS_FILE = ROOT / "docs" / "calendar.ics"
TEMPLATE_FILE = ROOT / "scripts" / "template.html"

TZ = ZoneInfo("Europe/Berlin")
TODAY = datetime.now(TZ).date()
THEMES = ["central_bank", "real_economy", "fin_markets"]


# ----------------------------------------------------------------------
# 正規化・検証・マージ
# ----------------------------------------------------------------------
def norm_title(t):
    t = unicodedata.normalize("NFKC", str(t or "")).lower()
    return re.sub(r"[^a-z0-9\u3040-\u30ff\u4e00-\u9fff]+", "", t)


def event_key(ev):
    return hashlib.sha1(
        (norm_title(ev.get("title")) + "|" + str(ev.get("date_start"))).encode()
    ).hexdigest()[:16]


def valid_date(s):
    try:
        return bool(s) and bool(date.fromisoformat(str(s)))
    except ValueError:
        return False


def sanitize(ev):
    """必須項目の検証と型の整形。無効なら None。"""
    if not isinstance(ev, dict):
        return None
    if not ev.get("title") or not valid_date(ev.get("date_start")):
        return None
    if ev.get("date_end") and not valid_date(ev.get("date_end")):
        ev["date_end"] = None
    themes = [t for t in (ev.get("themes") or []) if t in THEMES]
    if not themes:
        return None
    ev["themes"] = themes
    if ev.get("fee") not in ("free", "paid", "unknown"):
        ev["fee"] = "unknown"
    if ev.get("format") not in ("onsite", "online", "hybrid"):
        ev["format"] = None
    end = ev.get("date_end") or ev.get("date_start")
    if date.fromisoformat(end) < TODAY - timedelta(days=1):
        return None
    return ev


def load_json(path, default):
    if Path(path).exists():
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default
    return default


def merge(existing, new_events):
    """既存 + 新規 をマージ。first_seen は最初の値を維持。戻り値 (events, 追加件数)。"""
    by_key = {e["id"]: e for e in existing}
    added = 0
    for ev in new_events:
        ev = sanitize(dict(ev) if isinstance(ev, dict) else {})
        if not ev:
            continue
        k = event_key(ev)
        if k in by_key:
            old = by_key[k]
            for field, val in ev.items():
                if val not in (None, "", "unknown", []) and field != "source":
                    old[field] = val
        else:
            ev["id"] = k
            ev["first_seen"] = TODAY.isoformat()
            by_key[k] = ev
            added += 1
    return list(by_key.values()), added


def split_archive(events, archive_days=30):
    keep, archive = [], []
    cutoff = TODAY - timedelta(days=archive_days)
    for ev in events:
        end = ev.get("date_end") or ev.get("date_start")
        (archive if date.fromisoformat(end) < cutoff else keep).append(ev)
    return keep, archive


# ----------------------------------------------------------------------
# 出力生成
# ----------------------------------------------------------------------
def render_html(events, statuses):
    template = TEMPLATE_FILE.read_text(encoding="utf-8")
    events_sorted = sorted(events, key=lambda e: (e["date_start"], e.get("title") or ""))
    updated = datetime.now(TZ).strftime("%Y-%m-%d %H:%M (%Z)")
    html = (template
            .replace("__EVENTS_JSON__", json.dumps(events_sorted, ensure_ascii=False))
            .replace("__STATUS_JSON__", json.dumps(statuses, ensure_ascii=False))
            .replace("__UPDATED__", updated)
            .replace("__TODAY__", TODAY.isoformat()))
    HTML_FILE.write_text(html, encoding="utf-8")


def ics_escape(s):
    return (str(s or "").replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n"))


def render_ics(events):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0",
             "PRODID:-//seminar-radar//DE", "CALSCALE:GREGORIAN",
             "X-WR-CALNAME:Germany Econ/Fin Seminars"]
    for ev in events:
        start = ev["date_start"].replace("-", "")
        end_date = date.fromisoformat(ev.get("date_end") or ev["date_start"]) + timedelta(days=1)
        desc = (f"{ev.get('summary_ja') or ''} / 主催: {ev.get('organizer') or '?'}"
                f" / {ev.get('url') or ''}")
        lines += ["BEGIN:VEVENT",
                  f"UID:{ev['id']}@seminar-radar",
                  f"DTSTART;VALUE=DATE:{start}",
                  f"DTEND;VALUE=DATE:{end_date.strftime('%Y%m%d')}",
                  f"SUMMARY:{ics_escape(ev.get('title'))}",
                  f"LOCATION:{ics_escape(ev.get('city'))}",
                  f"DESCRIPTION:{ics_escape(desc)}",
                  "END:VEVENT"]
    lines.append("END:VCALENDAR")
    ICS_FILE.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
