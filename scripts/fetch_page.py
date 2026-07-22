#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_page.py: JS描画が必要なページをヘッドレスChromium(Playwright)で
レンダリングし、本文テキスト(またはHTML)を標準出力に出すCLIツール。

curl/WebFetch では取得できない(ボット対策・JSでイベント一覧を後から
描画する等の)ソースの巡回に使う。

使い方:
    python3 scripts/fetch_page.py <URL> [--wait MS] [--max-chars N] [--html]

オプション:
    --wait MS        ページ読み込み後にレンダリング完了を待つ時間(ミリ秒)。既定 2500
    --max-chars N    出力する文字数の上限。既定 30000
    --html           innerText の代わりにページのHTML全体を出力する

終了コード:
    0  … 成功
    1  … ページ取得・レンダリングに失敗(Cloudflare等のブロックを含む)
    2  … playwright が未インストール
"""

import argparse
import os
import sys

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print(
        "playwright がインストールされていません。"
        "pip install playwright を実行せよ"
        "(ブラウザのダウンロードは不要。playwright install は実行しないこと)。",
        file=sys.stderr,
    )
    sys.exit(2)

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

FALLBACK_EXECUTABLE_PATH = "/opt/pw-browsers/chromium"


def parse_args():
    parser = argparse.ArgumentParser(description="JS描画ページを取得して本文テキストを出力する")
    parser.add_argument("url", help="取得するURL")
    parser.add_argument("--wait", type=int, default=2500,
                         help="読み込み後の待機時間(ミリ秒、既定2500)")
    parser.add_argument("--max-chars", type=int, default=30000,
                         help="出力する文字数の上限(既定30000)")
    parser.add_argument("--html", action="store_true",
                         help="innerTextではなくページのHTML全体を出力する")
    return parser.parse_args()


def launch_browser(p):
    # クラウド実行環境では外向きHTTPSが環境プロキシ(HTTPS_PROXY)経由に限られる。
    # Chromiumは環境変数のプロキシ設定を確実には拾わないため、明示的に渡す。
    # プロキシのTLS再終端CAはOS側のNSSストアに登録済みなので追加設定は不要。
    kwargs = {"headless": True}
    proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy_url:
        kwargs["proxy"] = {"server": proxy_url}
    try:
        return p.chromium.launch(**kwargs)
    except Exception:
        return p.chromium.launch(executable_path=FALLBACK_EXECUTABLE_PATH, **kwargs)


def main():
    args = parse_args()

    try:
        with sync_playwright() as p:
            browser = launch_browser(p)
            try:
                context = browser.new_context(user_agent=DEFAULT_UA)
                page = context.new_page()
                page.goto(args.url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(args.wait)

                if args.html:
                    content = page.content()
                else:
                    content = page.evaluate("document.body.innerText")
            finally:
                browser.close()
    except Exception as e:
        print(f"ページの取得に失敗しました: {e}", file=sys.stderr)
        sys.exit(1)

    if content is None:
        content = ""
    if len(content) > args.max_chars:
        content = content[: args.max_chars]

    print(content)


if __name__ == "__main__":
    main()
