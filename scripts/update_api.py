#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update.py: 【予備手段・API従量課金版】
Claude API を直接呼んで巡回・抽出・検索・再生成まで一括で行う。
通常運用(Claude Code Routines・定額課金枠)では使わない。
GitHub Actions で回したくなった場合のみ、optional/daily.yml と併せて使う。

依存: requests, beautifulsoup4, pyyaml / 環境変数 ANTHROPIC_API_KEY
"""

import json
import os
import re
import sys
import time
from urllib.parse import urljoin

import requests
import yaml
from bs4 import BeautifulSoup

from radar_lib import (ARCHIVE_FILE, DATA_FILE, ROOT, TODAY, load_json, merge,
                       render_html, render_ics, split_archive)

API_URL = "https://api.anthropic.com/v1/messages"
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

EVENT_SCHEMA_NOTE = """
各イベントは次のキーを持つJSONオブジェクトとする:
  "title": 原文タイトル(英語/ドイツ語のまま。翻訳しない)
  "title_ja": 日本語の短い訳題(30字以内)
  "organizer": 主催者名(原文)
  "date_start": "YYYY-MM-DD"
  "date_end": "YYYY-MM-DD" または開始日と同じ場合 null
  "time": 開始時刻がわかる場合 "HH:MM" (現地時間)、不明なら null
  "city": 開催都市 (例 "Frankfurt am Main")。オンラインのみなら "Online"
  "venue": 会場名(わかれば)、不明なら null
  "format": "onsite" / "online" / "hybrid" のいずれか。不明なら null
  "themes": 次のうち該当するもの全ての配列:
      "central_bank"  = 中央銀行・金融政策
      "real_economy"  = 実体経済(特にエネルギー/オイルショック、防衛支出、インフラ投資、景気・貿易)
      "fin_markets"   = 金融規制・金融監督・金融市場・金融安定
      "geopolitics"   = 地政学・安全保障(防衛・軍需産業、経済安全保障・制裁・輸出管理、エネルギー安全保障、紛争が経済・社会・人口動態に与える影響の研究、大型安全保障フォーラム)
      "climate_esg"   = 環境・ESG(サステナブルファイナンス、気候リスク規制・開示、カーボン市場・CBAM、エネルギー転換・気候政策、気候変動の経済影響)
  "fee": "free" / "paid" / "unknown"
  "open_to_public": 一般が申し込めるなら true、招待制なら false、不明なら null
  "registration_note": 申込に関する短い日本語メモ(例「要事前登録・無料」)。不明なら null
  "url": イベント詳細ページのURL(なければ掲載元ページのURL)
  "summary_ja": 内容の日本語要約(1〜2文)
"""

EXTRACTION_RULES = f"""
抽出ルール:
- 上記5テーマのいずれかに該当するイベントのみ抽出する。該当しないものは含めない。
- 開催地がドイツ国内、またはオンライン参加可能、または主催がECB/ドイツの機関のものに限る。
- {TODAY.isoformat()} より前に終了したイベントは含めない。
- セミナー/会議/講演/シンポジウム/ワークショップのみ。以下は除外:
  統計・報告書の公表予定、記者会見、美術展・博物館ツアー、学校向けワークショップ、
  教員研修、採用イベント、開催日未定のCall for Papers。
- 日付が読み取れないイベントは含めない。推測で日付を作らない。
- ページに書かれていない情報は null / "unknown" とする。捏造しない。
- 出力は JSON 配列のみ。前置き・後書き・コードフェンスは一切付けない。
- 該当イベントがなければ [] とだけ出力する。
"""


def call_claude(model, prompt, max_tokens=8000, tools=None, retries=3):
    body = {"model": model, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]}
    if tools:
        body["tools"] = tools
    headers = {"x-api-key": API_KEY, "anthropic-version": "2023-06-01",
               "content-type": "application/json"}
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.post(API_URL, headers=headers, json=body, timeout=600)
            if r.status_code in (429, 500, 502, 503, 529):
                last_err = f"HTTP {r.status_code}: {r.text[:200]}"
                time.sleep(20 * (attempt + 1))
                continue
            r.raise_for_status()
            data = r.json()
            return "\n".join(b.get("text", "") for b in data.get("content", [])
                             if b.get("type") == "text")
        except requests.RequestException as e:
            last_err = str(e)
            time.sleep(20 * (attempt + 1))
    raise RuntimeError(f"Claude API failed: {last_err}")


def parse_json_events(text):
    text = re.sub(r"```(?:json)?", "", text).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end <= start:
        return []
    try:
        out = json.loads(text[start:end + 1])
        return out if isinstance(out, list) else []
    except json.JSONDecodeError:
        return []


def fetch_page_text(url, max_chars):
    headers = {"User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) "
                              "seminar-radar/1.0 (personal event calendar)")}
    r = requests.get(url, headers=headers, timeout=45)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
        tag.decompose()
    for a in soup.find_all("a", href=True):
        label = a.get_text(" ", strip=True)
        if label:
            a.replace_with(f"{label} [{urljoin(url, a['href'])}]")
    text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n"))
    return re.sub(r"[ \t]{2,}", " ", text)[:max_chars]


def extract_events_from_source(src, cfg):
    text = fetch_page_text(src["url"], cfg["max_page_chars"])
    prompt = f"""以下は「{src['name']}」({src['url']}) のイベント一覧ページのテキストである。
今後開催されるセミナー・会議を抽出し、JSON配列で出力せよ。
{EVENT_SCHEMA_NOTE}
{EXTRACTION_RULES}

--- ページテキストここから ---
{text}
--- ページテキストここまで ---"""
    events = parse_json_events(call_claude(cfg["extraction_model"], prompt))
    for ev in events:
        ev["source"] = src["name"]
    return events[:40]


def discover_events(cfg, topics, known_titles):
    tools = [{"type": "web_search_20250305", "name": "web_search",
              "max_uses": cfg["max_searches_per_day"]}]
    known = "\n".join(f"- {t}" for t in sorted(known_titles)[:120])
    topics_text = "\n".join(f"{i+1}. {t}" for i, t in enumerate(topics))
    prompt = f"""あなたはドイツ・フランクフルト在勤のエコノミストのために、
今後4か月以内にドイツ国内(またはドイツの機関主催のオンライン)で開催される
セミナー・会議をweb検索で探すリサーチャーである。本日は {TODAY.isoformat()}。

探すテーマ:
{topics_text}

既に把握しているイベント(これらは出力に含めない):
{known}

web_search ツールを使って検索し(英語とドイツ語の両方のクエリを使うこと)、
見つかった新規イベントを JSON 配列で出力せよ。
{EVENT_SCHEMA_NOTE}
{EXTRACTION_RULES}
- 検索結果から開催日・場所が確認できたものだけを含める。
- 最終出力はJSON配列のみとする(検索の途中経過は書かない)。"""
    events = parse_json_events(
        call_claude(cfg["discovery_model"], prompt, max_tokens=12000, tools=tools))
    for ev in events:
        ev["source"] = "web検索(discovery)"
    return events[:30]


def main():
    if not API_KEY:
        sys.exit("環境変数 ANTHROPIC_API_KEY が設定されていません。")
    config = yaml.safe_load((ROOT / "sources.yaml").read_text(encoding="utf-8"))
    cfg = config["settings"]

    store = load_json(DATA_FILE, {"events": []})
    events = store.get("events", [])
    statuses, collected = [], []

    for src in config["sources"]:
        try:
            found = extract_events_from_source(src, cfg)
            collected += found
            statuses.append({"name": src["name"], "url": src["url"],
                             "ok": True, "found": len(found)})
            print(f"[OK]   {src['name']}: {len(found)} 件")
        except Exception as e:
            statuses.append({"name": src["name"], "url": src["url"],
                             "ok": False, "error": str(e)[:200]})
            print(f"[FAIL] {src['name']}: {e}", file=sys.stderr)

    try:
        known = {e.get("title", "") for e in events} | \
                {e.get("title", "") for e in collected}
        found = discover_events(cfg, config.get("discovery_topics", []), known)
        collected += found
        statuses.append({"name": "web検索(discovery)", "url": "",
                         "ok": True, "found": len(found)})
    except Exception as e:
        statuses.append({"name": "web検索(discovery)", "url": "",
                         "ok": False, "error": str(e)[:200]})

    events, added = merge(events, collected)
    events, to_archive = split_archive(events, cfg["archive_after_days"])

    if to_archive:
        arch = load_json(ARCHIVE_FILE, {"events": []})
        arch["events"] += to_archive
        ARCHIVE_FILE.write_text(json.dumps(arch, ensure_ascii=False, indent=1),
                                encoding="utf-8")

    DATA_FILE.write_text(json.dumps({"events": events}, ensure_ascii=False, indent=1),
                         encoding="utf-8")
    render_html(events, statuses)
    render_ics(events)
    print(f"完了: 新規 {added} 件 / 掲載中 {len(events)} 件 / アーカイブ {len(to_archive)} 件")


if __name__ == "__main__":
    main()
