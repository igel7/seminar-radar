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

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def safe_url(u):
    """http(s)以外のスキーム(javascript:等)のURLを除去する。"""
    u = str(u or "").strip()
    return u if _URL_RE.match(u) else None


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
    lang = ev.get("language")
    if isinstance(lang, str) and lang.lower() in ("de+en",):
        lang = "en+de"
    if lang not in ("en", "de", "en+de"):
        lang = None
    ev["language"] = lang
    country = ev.get("country")
    if isinstance(country, str):
        country = country.upper()
    if not (isinstance(country, str) and re.fullmatch(r"[A-Z]{2}", country)):
        country = None
    ev["country"] = country
    for key in ("organizer_short", "title_short"):
        val = ev.get(key)
        ev[key] = val if isinstance(val, str) and val else None
    ev["url"] = safe_url(ev.get("url"))
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
def script_json(obj):
    """<script>内に埋め込むJSON。"<"を全てエスケープし、"</script>"や"<!--"による
    タグ脱出・パーサ状態操作を防ぐ(U+2028/2029は旧ブラウザのJS構文対策)。"""
    return (json.dumps(obj, ensure_ascii=False)
            .replace("<", "\\u003c")
            .replace(" ", "\\u2028")
            .replace(" ", "\\u2029"))


def sanitize_statuses(statuses):
    """status.json はLLMが直接書くため、描画前に型とURLスキームを強制する。"""
    out = []
    for s in statuses if isinstance(statuses, list) else []:
        if not isinstance(s, dict):
            continue
        found = s.get("found")
        out.append({
            "name": str(s.get("name") or ""),
            "url": safe_url(s.get("url")) or "",
            "ok": bool(s.get("ok")),
            "found": found if isinstance(found, int) and not isinstance(found, bool) else 0,
            "error": str(s.get("error"))[:300] if s.get("error") is not None else None,
        })
    return out


def render_html(events, statuses):
    template = TEMPLATE_FILE.read_text(encoding="utf-8")
    events_sorted = [dict(e, url=safe_url(e.get("url"))) for e in
                     sorted(events, key=lambda e: (e["date_start"], e.get("title") or ""))]
    updated = datetime.now(TZ).strftime("%Y-%m-%d %H:%M (%Z)")
    # 置換はシングルパスで行う(データ内にプレースホルダ文字列を仕込む注入への対策)
    mapping = {
        "__EVENTS_JSON__": script_json(events_sorted),
        "__STATUS_JSON__": script_json(sanitize_statuses(statuses)),
        "__UPDATED__": updated,
        "__TODAY__": TODAY.isoformat(),
    }
    pattern = re.compile("|".join(map(re.escape, mapping)))
    html = pattern.sub(lambda m: mapping[m.group(0)], template)
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
