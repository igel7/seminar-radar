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
SOURCES_FILE = ROOT / "sources.yaml"

TZ = ZoneInfo("Europe/Berlin")
TODAY = datetime.now(TZ).date()
THEMES = ["central_bank", "real_economy", "fin_markets"]
OVERRIDES_FILE = ROOT / "data" / "overrides.json"

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

# 対象地域(開催国ISO 3166-1 alpha-2)。
# 対象=ドイツ・スイス・オーストリア・中東欧・バルカン・バルト・ウクライナ。
# 英仏・ベネルクス(ルクセンブルク含む)・北欧・南欧・トルコは対象外。
REGION = {
    "DE", "CH", "AT",              # ドイツ・スイス・オーストリア
    "PL", "CZ", "SK", "HU", "SI",  # 中東欧
    "HR", "RS", "BA", "AL", "RO", "BG",  # バルカン
    "LT", "LV", "EE",              # バルト三国
    "UA",                          # ウクライナ
}

# ECB・BIS 主催かどうかの判定(単語境界。大文字小文字・全半角ゆれを吸収するため
# casefold済みの文字列に対して使う)。
_ANYWHERE_ORG_RE = re.compile(r"\becb\b|\bbis\b")

# フラッグシップ(旗艦)会議のタイトル部分一致パターン(casefold)。
# 該当すれば importance の下限を3に強制する(格下げ防止)。
# 根拠: いずれも中銀総裁・理事級の登壇が慣例の、機関の看板年次会議シリーズ。
FLAGSHIP_PATTERNS = [
    "european economic integration",       # CEEI (OeNB)
    "lamfalussy",                          # MNB Lámfalussy Lectures
    "lámfalussy",
    "european banking congress",           # Frankfurt EBC
    "ecb and its watchers",                # ECB and its Watchers
    "ecb watchers",
    "ecb forum on central banking",        # ECB Forum on Central Banking (Sintra)
    "ecb annual research conference",      # ECB Annual Research Conference
    "conference of the european systemic risk board",  # ESRB年次会議
    "snb research conference",             # SNB Research Conference
    "national bank of ukraine",            # NBU/NBP 年次研究会議
    "cebra biennial",                      # NBP/BoL/CEBRA Biennial Conference
]

# 都市名の表記ゆれ正規化(casefoldキー → 正式名)。
# 値は現データの多数派表記(英語exonym優先、Frankfurtのみドイツ語正式名)。
_CITY_CANON = {
    "frankfurt": "Frankfurt am Main",
    "frankfurt/main": "Frankfurt am Main",
    "frankfurt am main": "Frankfurt am Main",
    "frankfurt a.m.": "Frankfurt am Main",
    "frankfurt (main)": "Frankfurt am Main",
    "münchen": "Munich",
    "muenchen": "Munich",
    "wien": "Vienna",
    "köln": "Cologne",
    "koeln": "Cologne",
    "cologne": "Cologne",
    "praha": "Prague",
    "prag": "Prague",
    "warszawa": "Warsaw",
    "warschau": "Warsaw",
    "kiew": "Kyiv",
    "kiev": "Kyiv",
    "brüssel": "Brussels",
    "bruxelles": "Brussels",
    "brussel": "Brussels",
    "roma": "Rome",
    "rom": "Rome",
    "zürich": "Zurich",
    "zuerich": "Zurich",
    "genève": "Geneva",
    "genf": "Geneva",
    "geneve": "Geneva",
    "halle": "Halle (Saale)",
    "halle saale": "Halle (Saale)",
}


def safe_url(u):
    """http(s)以外のスキーム(javascript:等)のURLを除去する。"""
    u = str(u or "").strip()
    return u if _URL_RE.match(u) else None


def region_ok(ev, anywhere_sources):
    """開催地域が対象かどうかを決定論的に判定する。次のいずれかでTrue:
    (1) country が None(オンライン)または REGION 内
    (2) organizer_short/organizer に ECB・BIS が単語として含まれる(開催国不問)
    (3) event の source が anywhere_sources(sources.yaml で anywhere: true の定点)に含まれる"""
    country = ev.get("country")
    if country is None or country in REGION:
        return True
    for key in ("organizer_short", "organizer"):
        val = ev.get(key)
        if val and _ANYWHERE_ORG_RE.search(str(val).casefold()):
            return True
    if ev.get("source") in anywhere_sources:
        return True
    return False


def apply_flagship(ev):
    """タイトルが FLAGSHIP_PATTERNS のいずれかに部分一致すれば importance の下限を
    3に強制する(既存の3を下回る値での格下げは発生しない: maxを取るだけ)。"""
    title = unicodedata.normalize("NFKC", str(ev.get("title") or "")).casefold()
    if any(pat in title for pat in FLAGSHIP_PATTERNS):
        ev["importance"] = max(ev.get("importance") or 0, 3)
    return ev


def apply_overrides(events):
    """data/overrides.json (ユーザー管理の手動上書きファイル)を適用する。
    形式: {"<event_id>": {"フィールド": 値, ...}}。存在しないidは無視。
    ファイルが無い/壊れている場合も例外を投げず、無変更で継続する。"""
    overrides = load_json(OVERRIDES_FILE, {})
    if not isinstance(overrides, dict):
        return events
    for ev in events:
        patch = overrides.get(ev.get("id"))
        if isinstance(patch, dict):
            ev.update(patch)
    return events


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


# ----------------------------------------------------------------------
# \u30d5\u30a1\u30b8\u30fc\u91cd\u8907\u5224\u5b9a(\u8a00\u3044\u56de\u3057\u9055\u3044\u3067\u4e8c\u91cd\u767b\u9332\u3055\u308c\u305f\u30a4\u30d9\u30f3\u30c8\u306e\u691c\u51fa)
# ----------------------------------------------------------------------
_STOPWORDS = {
    "the", "of", "and", "in", "on", "for", "a", "an", "at", "to", "with",
    "und", "der", "die", "das", "f\u00fcr", "im", "zu", "ein", "eine",
}
_ORDINAL_RE = re.compile(r"^\d+(st|nd|rd|th)$")
_GENERIC_TOKENS = {
    "conference", "seminar", "workshop", "symposium", "annual", "event",
    "events", "meeting", "lecture", "konferenz", "tagung", "veranstaltung",
    "forum", "summit", "program", "programme",
}


def sig_tokens(title):
    """\u30bf\u30a4\u30c8\u30eb\u3092\u6b63\u898f\u5316\u3057\u3001\u30b9\u30c8\u30c3\u30d7\u30ef\u30fc\u30c9\u30fb\u6570\u5b57\u30fb\u5e8f\u6570\u3092\u9664\u3044\u305f\u5358\u8a9e\u96c6\u5408\u3092\u8fd4\u3059\u3002"""
    t = unicodedata.normalize("NFKC", str(title or "")).lower()
    words = re.findall(r"\w+", t)
    return {
        w for w in words
        if w not in _STOPWORDS and not w.isdigit() and not _ORDINAL_RE.match(w)
    }


def _similar_by_date_and_title(a, b):
    """\u7d4c\u8def1(\u65e5\u4ed8\u5b8c\u5168\u4e00\u81f4 + \u30bf\u30a4\u30c8\u30eb\u8a9e\u91cd\u8907\u3001\u5b9a\u70b9\u30bd\u30fc\u30b9\u540c\u58eb\u306f\u5bfe\u8c61\u5916\u306e\u5b89\u5168\u5f01\u3064\u304d):
    \u958b\u50ac\u65e5\u304c\u5b8c\u5168\u4e00\u81f4\u3057\u3001\u540c\u4e00\u90fd\u5e02\u3067\u3001\u30bf\u30a4\u30c8\u30eb\u306e\u6709\u610f\u8a9e\u91cd\u8907\u5ea6\u304c\u4e00\u5b9a\u4ee5\u4e0a\u3042\u308b\u5834\u5408\u306b\u540c\u4e00\u3068\u307f\u306a\u3059\u3002
    \u5b9a\u70b9\u89b3\u6e2c\u30bd\u30fc\u30b9\u540c\u58eb(discovery/\u624b\u52d5\u53d6\u8fbc\u3092\u542b\u307e\u306a\u3044\u7d44\u307f\u5408\u308f\u305b)\u306f\u5bfe\u8c61\u5916\u3068\u3059\u308b
    (\u540c\u3058\u5b9a\u70b9\u30da\u30fc\u30b8\u306b\u8f09\u308b\u5225\u30a4\u30d9\u30f3\u30c8\u3092\u8aa4\u3063\u3066\u7d71\u5408\u3057\u306a\u3044\u305f\u3081\u306e\u5b89\u5168\u5f01)\u3002"""
    if a.get("date_start") != b.get("date_start"):
        return False
    city_a, city_b = a.get("city"), b.get("city")
    if not city_a or not city_b or str(city_a).casefold() != str(city_b).casefold():
        return False
    src_a, src_b = str(a.get("source") or ""), str(b.get("source") or "")
    if not any(("web\u691c\u7d22" in s or "\u624b\u52d5\u53d6\u8fbc" in s) for s in (src_a, src_b)):
        return False
    org_a, org_b = a.get("organizer_short"), b.get("organizer_short")
    org_tokens = set()
    if org_a:
        org_tokens |= sig_tokens(org_a)
    if org_b:
        org_tokens |= sig_tokens(org_b)
    ov = len((sig_tokens(a.get("title")) & sig_tokens(b.get("title")))
             - _GENERIC_TOKENS - org_tokens)
    org_match = bool(org_a) and bool(org_b) and str(org_a).casefold() == str(org_b).casefold()
    return (org_match and ov >= 2) or (ov >= 3)


def _similar_by_period_and_title_containment(a, b):
    """\u7d4c\u8def2(\u958b\u50ac\u671f\u9593\u306e\u91cd\u306a\u308a + \u30bf\u30a4\u30c8\u30eb\u306e\u5305\u542b\u95a2\u4fc2\u3001\u5b89\u5168\u5f01\u306a\u3057):
    \u958b\u50ac\u671f\u9593(date_start\u301cdate_end)\u304c\u4ea4\u5dee\u3057\u3001\u540c\u4e00\u90fd\u5e02\u3067\u3001\u30bf\u30a4\u30c8\u30eb\u306e\u6709\u610f\u8a9e\u96c6\u5408\u304c
    \u3069\u3061\u3089\u304b\u3092\u90e8\u5206\u96c6\u5408\u3068\u3059\u308b\u5305\u542b\u95a2\u4fc2\u306b\u3042\u308c\u3070\u540c\u4e00\u3068\u307f\u306a\u3059\u3002
    \u5305\u542b + \u540c\u90fd\u5e02 + \u671f\u9593\u4ea4\u5dee\u306f\u8aa4\u308a\u306b\u304f\u3044\u5f37\u3044\u30b7\u30b0\u30ca\u30eb\u306a\u306e\u3067\u3001\u5b9a\u70b9\u30bd\u30fc\u30b9\u540c\u58eb\u3067\u3082
    \u5b89\u5168\u5f01\u306a\u3057\u3067\u30de\u30fc\u30b8\u5bfe\u8c61\u3068\u3059\u308b\u3002"""
    a_s, b_s = a.get("date_start"), b.get("date_start")
    if not a_s or not b_s:
        return False
    a_e = a.get("date_end") or a_s
    b_e = b.get("date_end") or b_s
    if not (a_s <= b_e and b_s <= a_e):
        return False
    city_a, city_b = a.get("city"), b.get("city")
    if not city_a or not city_b or str(city_a).casefold() != str(city_b).casefold():
        return False
    # _GENERIC_TOKENS(conference/programme等の一般語)を除いた集合同士で包含を見る。
    # "OeNB|SUERF|...Yale PFS Conference" と "...Yale Program on Financial Stability
    # Conference" のように、"program"のような一般語の有無だけで包含が壊れるのを防ぐ。
    ta = sig_tokens(a.get("title")) - _GENERIC_TOKENS
    tb = sig_tokens(b.get("title")) - _GENERIC_TOKENS
    if min(len(ta), len(tb)) < 3:
        return False
    return ta <= tb or tb <= ta


def similar_event(a, b):
    """\u540c\u4e00\u30a4\u30d9\u30f3\u30c8\u304c\u8a00\u3044\u56de\u3057\u9055\u3044\u306e\u30bf\u30a4\u30c8\u30eb\u3067\u5225\u767b\u9332\u3055\u308c\u3066\u3044\u306a\u3044\u304b\u3092\u5224\u5b9a\u3059\u308b\u3002
    \u7d4c\u8def1\u30fb\u7d4c\u8def2\u306e\u3044\u305a\u308c\u304b\u304cTrue\u306a\u3089True\u3002\u5404\u7d4c\u8def\u306e\u8da3\u65e8\u306f\u5404\u95a2\u6570\u306e docstring \u3092\u53c2\u7167\u3002"""
    return (_similar_by_date_and_title(a, b)
            or _similar_by_period_and_title_containment(a, b))


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
    city = ev.get("city")
    if city:
        city = str(city).strip()
        city = _CITY_CANON.get(city.casefold(), city)
        if city.casefold() == "online":
            ev["format"] = "online"
        ev["city"] = city
    if ev.get("format") == "online":
        ev["city"] = None
        ev["country"] = None
    for key in ("organizer_short", "title_short"):
        val = ev.get(key)
        ev[key] = val if isinstance(val, str) and val else None
    importance = ev.get("importance")
    if isinstance(importance, str) and importance.isdigit():
        importance = int(importance)
    if not (isinstance(importance, int) and not isinstance(importance, bool)
            and importance in (1, 2, 3)):
        importance = None
    ev["importance"] = importance
    ev["registration_url"] = safe_url(ev.get("registration_url"))
    time_end = ev.get("time_end")
    if not (isinstance(time_end, str) and re.fullmatch(r"\d{2}:\d{2}", time_end)):
        time_end = None
    ev["time_end"] = time_end
    ev["url"] = safe_url(ev.get("url"))
    end = ev.get("date_end") or ev.get("date_start")
    if date.fromisoformat(end) < TODAY - timedelta(days=1):
        return None
    return ev


def _merge_importance(old_val, new_val):
    """フィールドマージ時の importance 専用ルール: 両者が非Nullなら max を維持
    (新値での格下げ・上書きによる意図しない低下を防ぐ)。片方のみ非Nullなら
    その非Null側を採用。両方Nullなら None。"""
    if old_val is not None and new_val is not None:
        return max(old_val, new_val)
    return old_val if old_val is not None else new_val


def _merge_date_range(old_start, old_end, new_start, new_end):
    """重複統合時の date_start/date_end 専用マージ。他フィールドは「非nullなら新値で
    上書き」だが、日付だけはこれに委ねる: 統合後の開始日は両者のmin、終了日
    (date_end未設定ならdate_start扱い)は両者のmaxを採用し、末日が開始日より後なら
    date_end に設定、同日なら None とする(1日開催扱い)。
    (後着レコードの date_start でそのまま上書きすると会期初日を喪失するための対策)"""
    old_e = old_end or old_start
    new_e = new_end or new_start
    starts = [s for s in (old_start, new_start) if s]
    if not starts:
        return old_start, old_end
    start = min(starts)
    ends = [e for e in (old_e, new_e) if e]
    end = max(ends) if ends else start
    return start, (end if end > start else None)


def load_json(path, default):
    if Path(path).exists():
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default
    return default


def merge(existing, new_events):
    """既存 + 新規 をマージ。first_seen は最初の値を維持。戻り値 (events, 追加件数)。
    ハッシュキーが一致しない場合でも、ファジー判定(similar_event)で同一と
    見なせる既存イベントがあれば、そちらへフィールドマージし新規追加しない
    (言い回し違いでの二重登録を未然に防ぐ)。"""
    by_key = {e["id"]: e for e in existing}
    added = 0
    for ev in new_events:
        ev = sanitize(dict(ev) if isinstance(ev, dict) else {})
        if not ev:
            continue
        k = event_key(ev)
        if k in by_key:
            old = by_key[k]
            new_start, new_end = _merge_date_range(
                old.get("date_start"), old.get("date_end"),
                ev.get("date_start"), ev.get("date_end"))
            for field, val in ev.items():
                if field in ("source", "importance"):
                    continue
                if val not in (None, "", "unknown", []):
                    old[field] = val
            old["importance"] = _merge_importance(old.get("importance"), ev.get("importance"))
            old["date_start"], old["date_end"] = new_start, new_end
        else:
            match = next((old for old in by_key.values() if similar_event(old, ev)), None)
            if match is not None:
                new_start, new_end = _merge_date_range(
                    match.get("date_start"), match.get("date_end"),
                    ev.get("date_start"), ev.get("date_end"))
                for field, val in ev.items():
                    if field in ("source", "importance"):
                        continue
                    if val not in (None, "", "unknown", []):
                        match[field] = val
                match["importance"] = _merge_importance(match.get("importance"), ev.get("importance"))
                match["date_start"], match["date_end"] = new_start, new_end
            else:
                ev["id"] = k
                ev["first_seen"] = TODAY.isoformat()
                by_key[k] = ev
                added += 1
    return list(by_key.values()), added


def dedupe_events(events):
    """既に data/events.json 内に残ってしまった言い回し違いの重複を、
    first_seen 昇順(同値は id)で走査しながら統合する。
    戻り値: (残ったイベントのリスト, 除去件数)。"""
    ordered = sorted(events, key=lambda e: (e.get("first_seen") or "", e.get("id") or ""))
    kept = []
    removed = 0
    for ev in ordered:
        match = next((k for k in kept if similar_event(k, ev)), None)
        if match is not None:
            new_start, new_end = _merge_date_range(
                match.get("date_start"), match.get("date_end"),
                ev.get("date_start"), ev.get("date_end"))
            for field, val in ev.items():
                if field in ("first_seen", "id", "source", "importance"):
                    continue
                if val not in (None, "", "unknown", []):
                    match[field] = val
            match["importance"] = _merge_importance(match.get("importance"), ev.get("importance"))
            match["date_start"], match["date_end"] = new_start, new_end
            removed += 1
        else:
            kept.append(ev)
    return kept, removed


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


def parse_sources():
    """sources.yaml を行ベースで解析する(このファイルは自前管理でフォーマットが
    安定しているため、PyYAML の無い環境でも動くよう汎用YAMLパーサは使わない)。
    戻り値: {"sources": [{"name", "url"}, ...], "topics": [str, ...]}。
    ファイルが無い/解析に失敗しても例外を投げず空の結果を返す(巡回を止めない)。"""
    empty = {"sources": [], "topics": []}
    try:
        text = SOURCES_FILE.read_text(encoding="utf-8")
    except OSError:
        return empty

    try:
        src_marker = re.search(r'^sources:\s*$', text, re.MULTILINE)
        topics_marker = re.search(r'^discovery_topics:\s*$', text, re.MULTILINE)
        sources_section = (text[src_marker.end():topics_marker.start()]
                            if src_marker and topics_marker else "")
        topics_section = text[topics_marker.end():] if topics_marker else ""

        sources = []
        # 各エントリの "name: ... \n url: ..." の直後、次の "- name:" (または末尾) までを
        # そのエントリのブロックとして anywhere: true の有無を調べる。
        entry_re = re.compile(
            r'-\s*name:\s*"([^"]*)"\s*\n\s*url:\s*"([^"]*)"(?P<rest>.*?)(?=\n\s*-\s*name:|\Z)',
            re.DOTALL)
        for m in entry_re.finditer(sources_section):
            name, url = m.group(1).strip(), m.group(2).strip()
            if name and url:
                anywhere = bool(re.search(r'^\s*anywhere:\s*true\s*$', m.group("rest"),
                                           re.MULTILINE | re.IGNORECASE))
                sources.append({"name": name, "url": url, "anywhere": anywhere})

        topics = []
        for m in re.finditer(r'^\s*-\s*"([^"]*)"\s*$', topics_section, re.MULTILINE):
            topic = m.group(1).strip()
            if topic:
                topics.append(topic)

        return {"sources": sources, "topics": topics}
    except Exception:
        return empty


def render_html(events, statuses):
    template = TEMPLATE_FILE.read_text(encoding="utf-8")
    events_sorted = [dict(e, url=safe_url(e.get("url"))) for e in
                     sorted(events, key=lambda e: (e["date_start"], e.get("title") or ""))]
    updated = datetime.now(TZ).strftime("%Y-%m-%d %H:%M (%Z)")
    # 置換はシングルパスで行う(データ内にプレースホルダ文字列を仕込む注入への対策)
    mapping = {
        "__EVENTS_JSON__": script_json(events_sorted),
        "__STATUS_JSON__": script_json(sanitize_statuses(statuses)),
        "__SOURCES_JSON__": script_json(parse_sources()),
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
