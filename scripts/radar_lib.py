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
CHANGELOG_FILE = ROOT / "data" / "changelog.json"
HTML_FILE = ROOT / "docs" / "index.html"
ICS_FILE = ROOT / "docs" / "calendar.ics"
TEMPLATE_FILE = ROOT / "scripts" / "template.html"
SOURCES_FILE = ROOT / "sources.yaml"

TZ = ZoneInfo("Europe/Berlin")
TODAY = datetime.now(TZ).date()
THEMES = ["central_bank", "real_economy", "fin_markets", "geopolitics", "climate_esg",
          "ai", "china", "japan"]
OVERRIDES_FILE = ROOT / "data" / "overrides.json"
ALIASES_FILE = ROOT / "data" / "aliases.json"

# 更新履歴(data/changelog.json)に「変更」として記録するフィールドのホワイトリスト。
# summary_ja・title_ja 等はLLMが毎日再抽出するたびに言い回しが変わりがちで、
# これを対象に含めると実質的な変化が無い日でも全イベントが更新扱いになってしまう。
# そのため、値が変わればユーザーにとって意味のある「実質的な変更」だけに絞る。
CHANGELOG_WATCHED_FIELDS = ("date_start", "date_end", "time", "time_end", "venue", "city",
                            "format", "fee", "fee_amount", "registration_url", "open_to_public")
CHANGELOG_KEEP_DAYS = 90    # data/changelog.json にファイルとして保持する日数
CHANGELOG_EMBED_DAYS = 30   # HTMLに埋め込み・表示する日数(ファイル保持より短い窓)

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
    "nürnberg": "Nuremberg",
    "nuernberg": "Nuremberg",
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
_ORDINAL_SUFFIX_RE = re.compile(r"^(\d+)(st|nd|rd|th)$", re.IGNORECASE)
_GENERIC_TOKENS = {
    "conference", "seminar", "workshop", "symposium", "annual", "event",
    "events", "meeting", "lecture", "konferenz", "tagung", "veranstaltung",
    "forum", "summit", "program", "programme",
}

# \u30ed\u30fc\u30de\u6570\u5b57(\u5168\u5927\u6587\u5b57\u30c8\u30fc\u30af\u30f3\u306e\u307f\u5bfe\u8c61\u3002\u5c0f\u6587\u5b57\u306e\u82f1\u5358\u8a9e\u304c\u305f\u307e\u305f\u307e\u30ed\u30fc\u30de\u6570\u5b57\u306e
# \u6587\u5b57\u3060\u3051\u3067\u69cb\u6210\u3055\u308c\u308b\u5834\u5408(\u4f8b "mix")\u306e\u8aa4\u5909\u63db\u3092\u907f\u3051\u308b\u305f\u3081\u306e\u5b89\u5168\u5f01)\u3002
# I\u301cXLIX(1\u301c49)\u7a0b\u5ea6\u306b\u9650\u5b9a\u3057\u3066\u5909\u63db\u3059\u308b(\u4f1a\u8b70\u306e\u56de\u6570\u8868\u8a18\u3067\u4f7f\u308f\u308c\u308b\u7bc4\u56f2)\u3002
_ROMAN_RE = re.compile(r"^(?=[MDCLXVI])M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")
_ROMAN_VALUES = {"M": 1000, "D": 500, "C": 100, "L": 50, "X": 10, "V": 5, "I": 1}


def _roman_to_int(s):
    total, prev = 0, 0
    for ch in reversed(s):
        val = _ROMAN_VALUES[ch]
        if val < prev:
            total -= val
        else:
            total += val
            prev = val
    return total


def _normalize_number_word(word, original):
    """\u82f1\u8a9e\u5e8f\u6570\u306e\u63a5\u5c3e\u8f9e\u9664\u53bb(35th\u21923\u7b49)\u3068\u3001\u5168\u5927\u6587\u5b57\u30c8\u30fc\u30af\u30f3\u306b\u9650\u3063\u305f
    \u30ed\u30fc\u30de\u6570\u5b57\u2192\u30a2\u30e9\u30d3\u30a2\u6570\u5b57\u5909\u63db(XXXV\u219235\u7b49\u30011\u301c49\u306e\u7bc4\u56f2\u306e\u307f)\u3092\u884c\u3046\u3002
    \u3069\u3061\u3089\u306b\u3082\u8a72\u5f53\u3057\u306a\u3051\u308c\u3070\u5c0f\u6587\u5b57\u5316\u6e08\u307f\u306e word \u3092\u305d\u306e\u307e\u307e\u8fd4\u3059\u3002
    (\u5909\u63db\u5f8c\u306e\u6570\u5b57\u30c8\u30fc\u30af\u30f3\u306f sig_tokens \u5074\u3067\u3044\u305a\u308c\u306b\u305b\u3088\u9664\u5916\u3055\u308c\u308b\u306e\u3067\u3001
    \u30ed\u30fc\u30de\u6570\u5b57\u3068\u30a2\u30e9\u30d3\u30a2\u6570\u5b57\u8868\u8a18\u3092\u540c\u4e00\u6271\u3044\u306b\u3067\u304d\u308b)\u3002"""
    m = _ORDINAL_SUFFIX_RE.match(word)
    if m:
        return m.group(1)
    if original.isupper() and _ROMAN_RE.match(original):
        val = _roman_to_int(original)
        if 1 <= val <= 49:
            return str(val)
    return word


def sig_tokens(title):
    """\u30bf\u30a4\u30c8\u30eb\u3092\u6b63\u898f\u5316\u3057(\u30ed\u30fc\u30de\u6570\u5b57\u30fb\u5e8f\u6570\u63a5\u5c3e\u8f9e\u3092\u30a2\u30e9\u30d3\u30a2\u6570\u5b57\u5316\u3057\u3066\u304b\u3089)\u3001
    \u30b9\u30c8\u30c3\u30d7\u30ef\u30fc\u30c9\u30fb\u6570\u5b57\u30fb\u5e8f\u6570\u3092\u9664\u3044\u305f\u5358\u8a9e\u96c6\u5408\u3092\u8fd4\u3059\u3002"""
    t = unicodedata.normalize("NFKC", str(title or ""))
    raw_words = re.findall(r"\w+", t)
    words = [_normalize_number_word(w.lower(), w) for w in raw_words]
    return {
        w for w in words
        if w not in _STOPWORDS and not w.isdigit() and not _ORDINAL_RE.match(w)
    }


def _norm_url_key(u):
    """重複判定用のURL正規化キー。フラグメント除去・末尾スラッシュ除去・
    スキームとホストの小文字化を行う(パスとクエリは大文字小文字を保持)。"""
    u = safe_url(u)
    if not u:
        return None
    u = u.split("#", 1)[0].rstrip("/")
    m = re.match(r"^(https?)://([^/]*)(.*)$", u, re.IGNORECASE)
    return m.group(1).lower() + "://" + m.group(2).lower() + m.group(3)


def _period_overlap(a, b):
    """開催期間(date_start〜date_end、end未設定はstart扱い)が交差するか。"""
    a_s, b_s = a.get("date_start"), b.get("date_start")
    if not a_s or not b_s:
        return False
    a_e = a.get("date_end") or a_s
    b_e = b.get("date_end") or b_s
    return a_s <= b_e and b_s <= a_e


def _sig_title_tokens(ev):
    return sig_tokens(ev.get("title")) - _GENERIC_TOKENS


def _title_overlap_ratio(a, b):
    """タイトル有意語(一般語除去後)の重複率 = 交差 / 小さい方の集合サイズ。
    片方に副題や言語違いの語が付いても、短い側が長い側にほぼ含まれていれば
    1.0に近づく。どちらかが空集合なら0.0。"""
    ta, tb = _sig_title_tokens(a), _sig_title_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def _org_compatible(a, b):
    """主催者情報(organizer + organizer_short)の語が1つでも重なるか。
    片方でも主催者情報が無ければ判定不能としてTrue(棄却しない)。
    共催イベント(『EWI, SVR, DIW Berlin』等)でも部分一致で通る。"""
    oa = sig_tokens(a.get("organizer")) | sig_tokens(a.get("organizer_short"))
    ob = sig_tokens(b.get("organizer")) | sig_tokens(b.get("organizer_short"))
    if not oa or not ob:
        return True
    return bool(oa & ob)


def _same_place(a, b):
    """同一会場判定: 両方cityが実値ならcasefold一致、両方が完全オンライン
    (format=='online'でcityがnull)なら同一とみなす。片方だけcityがない/onlineでない場合はFalse。
    """
    city_a, city_b = a.get("city"), b.get("city")
    if city_a and city_b:
        return str(city_a).casefold() == str(city_b).casefold()
    if a.get("format") == "online" and b.get("format") == "online":
        return True
    return False


def _same_city_strict(a, b):
    """都市の厳密一致判定(経路5専用): 両方 city が実値でcasefold一致、または
    両方 city が null(オンライン/不明問わず)なら同一とみなす。_same_place と異なり
    format=='online' かどうかは見ない(city=nullという事実だけで揃える)。"""
    city_a, city_b = a.get("city"), b.get("city")
    if city_a is None and city_b is None:
        return True
    if city_a and city_b:
        return str(city_a).casefold() == str(city_b).casefold()
    return False


def _similar_by_date_and_title(a, b):
    """\u7d4c\u8def1(\u65e5\u4ed8\u5b8c\u5168\u4e00\u81f4 + \u30bf\u30a4\u30c8\u30eb\u8a9e\u91cd\u8907\u3001\u5b9a\u70b9\u30bd\u30fc\u30b9\u540c\u58eb\u306f\u5bfe\u8c61\u5916\u306e\u5b89\u5168\u5f01\u3064\u304d):
    \u958b\u50ac\u65e5\u304c\u5b8c\u5168\u4e00\u81f4\u3057\u3001\u540c\u4e00\u90fd\u5e02\u3067\u3001\u30bf\u30a4\u30c8\u30eb\u306e\u6709\u610f\u8a9e\u91cd\u8907\u5ea6\u304c\u4e00\u5b9a\u4ee5\u4e0a\u3042\u308b\u5834\u5408\u306b\u540c\u4e00\u3068\u307f\u306a\u3059\u3002
    \u5b9a\u70b9\u89b3\u6e2c\u30bd\u30fc\u30b9\u540c\u58eb(discovery/\u624b\u52d5\u53d6\u8fbc\u3092\u542b\u307e\u306a\u3044\u7d44\u307f\u5408\u308f\u305b)\u306f\u5bfe\u8c61\u5916\u3068\u3059\u308b
    (\u540c\u3058\u5b9a\u70b9\u30da\u30fc\u30b8\u306b\u8f09\u308b\u5225\u30a4\u30d9\u30f3\u30c8\u3092\u8aa4\u3063\u3066\u7d71\u5408\u3057\u306a\u3044\u305f\u3081\u306e\u5b89\u5168\u5f01)\u3002"""
    if a.get("date_start") != b.get("date_start"):
        return False
    if not _same_place(a, b):
        return False
    # \u5b89\u5168\u5f01: \u540c\u4e00\u306e\u5b9a\u70b9\u30bd\u30fc\u30b9\u540c\u58eb\u306f\u5bfe\u8c61\u5916(\u540c\u3058\u5b9a\u70b9\u30da\u30fc\u30b8\u306b\u8f09\u308b\u540c\u30b7\u30ea\u30fc\u30ba\u306e
    # \u5225\u30a4\u30d9\u30f3\u30c8(\u8b1b\u6f14\u8005\u9055\u3044\u7b49)\u3092\u8aa4\u3063\u3066\u7d71\u5408\u3057\u306a\u3044\u305f\u3081)\u3002\u7570\u306a\u308b\u5b9a\u70b9\u540c\u58eb\u3084
    # web\u691c\u7d22/\u624b\u52d5\u53d6\u8fbc\u304c\u7d61\u3080\u30da\u30a2\u306f\u5224\u5b9a\u5bfe\u8c61\u3068\u3059\u308b\u3002
    src_a, src_b = str(a.get("source") or ""), str(b.get("source") or "")
    watch_only = not any(("web\u691c\u7d22" in s or "\u624b\u52d5\u53d6\u8fbc" in s)
                         for s in (src_a, src_b))
    if watch_only and src_a == src_b:
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
    if not _period_overlap(a, b):
        return False
    if not _same_place(a, b):
        return False
    # _GENERIC_TOKENS(conference/programme等の一般語)を除いた集合同士で包含を見る。
    # "OeNB|SUERF|...Yale PFS Conference" と "...Yale Program on Financial Stability
    # Conference" のように、"program"のような一般語の有無だけで包含が壊れるのを防ぐ。
    ta, tb = _sig_title_tokens(a), _sig_title_tokens(b)
    n = min(len(ta), len(tb))
    if n < 2:
        return False
    if not (ta <= tb or tb <= ta):
        return False
    # 有意語2語だけの包含("Scientific Workshop on Productivity"等)は単独では
    # 弱いシグナルなので、主催者の語が重なることを追加で要求する。
    return n >= 3 or _org_compatible(a, b)


def _similar_by_url(a, b):
    """経路3(URL一致 + 期間交差 + タイトル語の重複率):
    同一URLを指し開催期間が交差する2件は、タイトルが言語違い(英/独)や
    副題の有無で食い違っていても同一イベントである可能性が極めて高い。
    ただし一覧ページのURL(1つのURLを複数イベントが共有)経由の誤統合を防ぐため、
    タイトル有意語の重複率 >= 0.5 を要求する。
    都市の一致は要求しない(片方の抽出ミスや表記ゆれで都市が割れたケースを救う)。"""
    ua, ub = _norm_url_key(a.get("url")), _norm_url_key(b.get("url"))
    if not ua or ua != ub:
        return False
    if not _period_overlap(a, b):
        return False
    return _title_overlap_ratio(a, b) >= 0.5


def _similar_by_high_overlap(a, b):
    """経路4(期間交差 + 同一都市 + タイトル有意語の高重複率):
    URLも情報源も異なるが、タイトルの有意語がほぼ一致する場合
    (例: "Money Market Event – Geneva (Tschudin & Moser)" と
    "SNB Money Market Event: Speeches by Petra Tschudin and Thomas Moser")。
    同一シリーズの別回(講演者違い)は重複率が0.5前後に留まるため閾値0.8で弾ける。
    有意語2語だけの一致は経路2と同様に主催者の語の重なりを追加要求する。"""
    if not _period_overlap(a, b) or not _same_place(a, b):
        return False
    ta, tb = _sig_title_tokens(a), _sig_title_tokens(b)
    n = min(len(ta), len(tb))
    if n < 2:
        return False
    if len(ta & tb) / n < 0.8:
        return False
    return n >= 3 or _org_compatible(a, b)


def _similar_by_exact_date_and_title_containment(a, b):
    """経路5(開催開始日の完全一致 + 都市の厳密一致(両方nullも可) + タイトル正規化
    トークンの包含関係): ローマ数字(XXXV等)・英語序数接尾辞(35th等)の表記ゆれや、
    多言語タイトル(例 "35th Economic Forum..." と "XXXV Forum Ekonomiczne")で
    経路1〜4の閾値をすり抜けた重複を拾うための最終防御線。
    一般語(_GENERIC_TOKENS)を除いた有意語集合について、どちらか一方(2語以上)が
    もう一方の部分集合なら同一とみなす。定点ソース同士の安全弁は付けない
    (開催日+都市完全一致という強いシグナルのため)。"""
    if a.get("date_start") != b.get("date_start"):
        return False
    if not _same_city_strict(a, b):
        return False
    ta, tb = _sig_title_tokens(a), _sig_title_tokens(b)
    if not ta or not tb:
        return False
    if ta <= tb and len(ta) >= 2:
        return True
    if tb <= ta and len(tb) >= 2:
        return True
    return False


def similar_event(a, b):
    """同一イベントが言い回し違いのタイトルで別登録されていないかを判定する。
    経路1〜5のいずれかがTrueならTrue。各経路の趣旨は各関数の docstring を参照。"""
    return (_similar_by_date_and_title(a, b)
            or _similar_by_period_and_title_containment(a, b)
            or _similar_by_url(a, b)
            or _similar_by_high_overlap(a, b)
            or _similar_by_exact_date_and_title_containment(a, b))


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
    fee_amount = ev.get("fee_amount")
    if isinstance(fee_amount, str):
        try:
            fee_amount = float(fee_amount.replace(",", "").replace("€", "").strip())
        except ValueError:
            fee_amount = None
    if not (isinstance(fee_amount, (int, float)) and not isinstance(fee_amount, bool)
            and fee_amount >= 0):
        fee_amount = None
    ev["fee_amount"] = fee_amount
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
            and importance in (0, 1, 2, 3)):
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
    """既存 + 新規 をマージ。first_seen は最初の値を維持。戻り値 (events, 追加件数, changes)。
    ハッシュキーが一致しない場合でも、ファジー判定(similar_event)で同一と
    見なせる既存イベントがあれば、そちらへフィールドマージし新規追加しない
    (言い回し違いでの二重登録を未然に防ぐ)。
    changes は data/changelog.json 更新用(update_changelog)の差分情報:
      {"added": [新規追加イベントへの参照, ...],
       "updated": {id: (イベントへの参照, 変更フィールド名のset), ...}}
    updated は CHANGELOG_WATCHED_FIELDS のうち実際に値が変わったフィールドのみを持つ
    (同値上書きは記録しない)。同一イベントが同一実行内で複数回マッチした場合は
    フィールドsetを和集合にする。"""
    by_key = {e["id"]: e for e in existing}
    added = 0
    changes = {"added": [], "updated": {}}

    def record_update(ev_ref, before):
        # 当日追加分(first_seen==TODAY)は、追加直後の2回目実行等で誤って
        # 「更新」扱いされないよう記録しない。
        if ev_ref.get("first_seen") == TODAY.isoformat():
            return
        changed = {f for f in CHANGELOG_WATCHED_FIELDS if before.get(f) != ev_ref.get(f)}
        if not changed:
            return
        eid = ev_ref.get("id")
        if eid in changes["updated"]:
            changes["updated"][eid][1].update(changed)
        else:
            changes["updated"][eid] = (ev_ref, changed)

    for ev in new_events:
        ev = sanitize(dict(ev) if isinstance(ev, dict) else {})
        if not ev:
            continue
        k = event_key(ev)
        if k in by_key:
            old = by_key[k]
            before = {f: old.get(f) for f in CHANGELOG_WATCHED_FIELDS}
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
            record_update(old, before)
        else:
            match = next((old for old in by_key.values() if similar_event(old, ev)), None)
            if match is not None:
                before = {f: match.get(f) for f in CHANGELOG_WATCHED_FIELDS}
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
                record_update(match, before)
            else:
                ev["id"] = k
                ev["first_seen"] = TODAY.isoformat()
                by_key[k] = ev
                added += 1
                changes["added"].append(ev)
    return list(by_key.values()), added, changes


def _changelog_snap(ev):
    """イベントから更新履歴の表示用スナップショット(dict)を作る。
    イベントは開催終了から30日で split_archive により data/events.json から
    アーカイブへ移されて消えるため、履歴側にタイトル等の表示に必要な情報を
    その時点の値として焼き込んでおく(idの参照だけでは後から描画できなくなるため)。"""
    return {
        "id": ev.get("id"),
        "title": ev.get("title"),
        "title_ja": ev.get("title_ja"),
        "organizer_short": ev.get("organizer_short"),
        "date_start": ev.get("date_start"),
        "date_end": ev.get("date_end"),
        "city": ev.get("city"),
        "url": safe_url(ev.get("url")),
    }


def update_changelog(changes):
    """data/changelog.json (追加・実質更新の日次履歴)を更新する。
    changes は merge() が返す差分情報 {"added": [...], "updated": {id: (ev, fields), ...}}。
    added・updated が両方空でも呼んでよく、その場合は保持期限切れエントリの掃除だけが走る。

    ファイル形式: 日付降順の配列。各要素は
      {"date": "YYYY-MM-DD",
       "added": [スナップショット, ...],
       "updated": [スナップショット + "fields": [変更フィールド名, ...(ソート済み)], ...]}

    戻り値: TODAY - CHANGELOG_EMBED_DAYS 以降のエントリ(日付降順、HTML埋め込み用)。"""
    log = load_json(CHANGELOG_FILE, [])
    if not isinstance(log, list):
        log = []

    today_str = TODAY.isoformat()
    entry = next((e for e in log if isinstance(e, dict) and e.get("date") == today_str), None)
    if entry is None:
        entry = {"date": today_str, "added": [], "updated": []}
        log.append(entry)

    # added: 既存(当日分、同日2回目実行など)を id 順を保ったまま引き継ぎ、
    # 新規 id のみスナップショットを追記する。
    added_map, added_order = {}, []
    for a in entry.get("added") or []:
        if isinstance(a, dict) and a.get("id"):
            added_map[a["id"]] = a
            added_order.append(a["id"])
    for ev in changes.get("added", []):
        eid = ev.get("id")
        if not eid or eid in added_map:
            continue
        added_map[eid] = _changelog_snap(ev)
        added_order.append(eid)
    entry["added"] = [added_map[eid] for eid in added_order]

    # updated: 当日 added に載っているidは対象外(追加当日の変更はニュースにしない)。
    # 既存の updated があればフィールドを和集合にしスナップショットを最新化する。
    updated_map, updated_order = {}, []
    for u in entry.get("updated") or []:
        if isinstance(u, dict) and u.get("id"):
            updated_map[u["id"]] = u
            updated_order.append(u["id"])
    for eid, (ev, fields) in changes.get("updated", {}).items():
        if not eid or eid in added_map:
            continue
        if eid in updated_map:
            fields = set(updated_map[eid].get("fields") or []) | set(fields)
        else:
            updated_order.append(eid)
        snap = _changelog_snap(ev)
        snap["fields"] = sorted(fields)
        updated_map[eid] = snap
    entry["updated"] = [updated_map[eid] for eid in updated_order]

    # 保持期限切れ(CHANGELOG_KEEP_DAYS より古い)・日付が不正なエントリを除去する。
    cutoff = (TODAY - timedelta(days=CHANGELOG_KEEP_DAYS)).isoformat()
    log = [e for e in log if isinstance(e, dict) and valid_date(e.get("date"))
           and e["date"] >= cutoff]
    log.sort(key=lambda e: e["date"], reverse=True)

    CHANGELOG_FILE.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")

    embed_cutoff = (TODAY - timedelta(days=CHANGELOG_EMBED_DAYS)).isoformat()
    return [e for e in log if e["date"] >= embed_cutoff]


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


def apply_aliases(events):
    """data/aliases.json (重複ID→正本IDの恒久台帳。人が手動でメンテナンスする)を
    毎回適用する。similar_event のファジー判定をすり抜けた既知の重複(多言語タイトル・
    ローマ数字/序数ゆれ等)は、一度台帳に載せれば巡回のたびに何度でも正本IDへ統合され、
    次回の抽出で hash(タイトル+開催日)が再び重複IDと一致しても復活しない。
    処理:
      1) 各イベントの id が aliases のキーに一致すれば、値(正本ID)に書き換える
         (チェーンは1段のみ辿る。台帳自体が正本IDを指すよう運用する前提)。
      2) 書き換え後に同一 id が複数存在すれば、dedupe_events と同じ規則
         (first_seen最古維持・None/""/"unknown"/[]でない値で上書き・
         importanceは_merge_importance・日付は_merge_date_range)でフィールドマージし1件に統合する。
    aliases.json が無い/JSONとして壊れている場合も例外を投げず、空の台帳として扱う
    (巡回を止めない)。
    戻り値: (events, 統合件数)"""
    aliases = load_json(ALIASES_FILE, {})
    if not isinstance(aliases, dict):
        aliases = {}

    for ev in events:
        canon = aliases.get(ev.get("id"))
        if isinstance(canon, str) and canon:
            ev["id"] = canon
            # 重複側だった印(タイトル系フィールドのマージ優先度の判定に使う。保存前に除去)
            ev["_from_alias"] = True

    by_id = {}
    order = []
    merged = 0
    for ev in events:
        eid = ev.get("id")
        if eid in by_id:
            match = by_id[eid]
            new_start, new_end = _merge_date_range(
                match.get("date_start"), match.get("date_end"),
                ev.get("date_start"), ev.get("date_end"))
            first_seens = [v for v in (match.get("first_seen"), ev.get("first_seen")) if v]
            # タイトル系は正本(エイリアス書き換えを受けていない側)の表記を優先し、
            # 重複側の簡素な表記(例 "XXXV Forum Ekonomiczne")で上書きしない
            ev_is_alias = ev.pop("_from_alias", False)
            match_is_alias = match.get("_from_alias", False)
            for field, val in ev.items():
                if field in ("first_seen", "id", "source", "importance",
                             "date_start", "date_end"):
                    continue
                if (field in ("title", "title_ja", "title_short")
                        and ev_is_alias and not match_is_alias
                        and match.get(field) not in (None, "", "unknown")):
                    continue
                if val not in (None, "", "unknown", []):
                    match[field] = val
            if match_is_alias and not ev_is_alias:
                match.pop("_from_alias", None)
            match["importance"] = _merge_importance(match.get("importance"), ev.get("importance"))
            match["date_start"], match["date_end"] = new_start, new_end
            if first_seens:
                match["first_seen"] = min(first_seens)
            merged += 1
        else:
            by_id[eid] = ev
            order.append(eid)
    result = [by_id[i] for i in order]
    for ev in result:
        ev.pop("_from_alias", None)
    return result, merged


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


_ID16_RE = re.compile(r"^[0-9a-f]{16}$")


def load_aliases_for_embed():
    """ページに埋め込む「重複ID→正本ID」の対応表。ブラウザ側は共有リンクや
    localStorage に残った旧IDを正本IDへ引き直すためだけに使うので、キー・値とも
    16桁hexの str に一致するエントリだけを通す(それ以外は黙って捨てる)。
    キーを16桁hexに限ることで、埋め込んだオブジェクトリテラルに __proto__ 等の
    特殊キーが混入しないことも保証する。"""
    raw = load_json(ALIASES_FILE, {})
    out = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            if (isinstance(k, str) and isinstance(v, str)
                    and _ID16_RE.match(k) and _ID16_RE.match(v)):
                out[k] = v
    return out


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


def render_html(events, statuses, changelog=None):
    template = TEMPLATE_FILE.read_text(encoding="utf-8")
    events_sorted = [dict(e, url=safe_url(e.get("url"))) for e in
                     sorted(events, key=lambda e: (e["date_start"], e.get("title") or ""))]
    updated = datetime.now(TZ).strftime("%Y-%m-%d %H:%M (%Z)")
    if changelog is None:
        # 呼び出し元が update_changelog() を呼ばずに render_html() だけ叩いた場合の保険。
        # ファイルを読むだけで、プルーニング(古いエントリの削除)は行わない
        # (それは巡回時に update_changelog() 側の責務とする)。
        log = load_json(CHANGELOG_FILE, [])
        if not isinstance(log, list):
            log = []
        embed_cutoff = (TODAY - timedelta(days=CHANGELOG_EMBED_DAYS)).isoformat()
        changelog = sorted(
            (e for e in log if isinstance(e, dict) and valid_date(e.get("date"))
             and e["date"] >= embed_cutoff),
            key=lambda e: e["date"], reverse=True)
    # 置換はシングルパスで行う(データ内にプレースホルダ文字列を仕込む注入への対策)
    mapping = {
        "__EVENTS_JSON__": script_json(events_sorted),
        "__ALIASES_JSON__": script_json(load_aliases_for_embed()),
        "__STATUS_JSON__": script_json(sanitize_statuses(statuses)),
        "__SOURCES_JSON__": script_json(parse_sources()),
        "__CHANGELOG_JSON__": script_json(changelog),
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
        # importance 0(毎週型の定例研究セミナー等のマイクロイベント)は ICS に含めない。
        # 購読カレンダーに週次セミナーが溢れてノイズになるのを防ぐため
        # (Webの一覧では「すべて」フィルタで引き続き検索できる)。
        if ev.get("importance") == 0:
            continue
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
