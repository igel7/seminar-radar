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
import shutil
import subprocess
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


def ensure_proxy_ca_in_nss():
    """クラウド実行環境の外向きプロキシはTLSを再終端するため、Chromiumが
    そのCAを信用できないと接続に失敗する。curl等はCA環境変数で対応済みだが
    ChromiumはNSSストア($HOME/.pki/nssdb)しか見ないので、プロキシCAの登録を
    試みる。certutilが無い等で失敗しても続行する(best effort)。"""
    for ca in ("/root/.ccr/agent-proxy-ca.crt", os.environ.get("NODE_EXTRA_CA_CERTS")):
        if ca and os.path.isfile(ca):
            break
    else:
        return
    if not shutil.which("certutil"):
        return
    nssdb = os.path.join(os.path.expanduser("~"), ".pki", "nssdb")
    try:
        os.makedirs(nssdb, exist_ok=True)
        db = "sql:" + nssdb
        if not os.path.exists(os.path.join(nssdb, "cert9.db")):
            subprocess.run(["certutil", "-d", db, "-N", "--empty-password"],
                           check=False, capture_output=True, timeout=30)
        subprocess.run(["certutil", "-d", db, "-A", "-t", "C,,",
                        "-n", "agent-proxy-ca", "-i", ca],
                       check=False, capture_output=True, timeout=30)
    except Exception:
        pass


def launch_browser(p, proxy_url):
    kwargs = {"headless": True}
    if proxy_url:
        kwargs["proxy"] = {"server": proxy_url}
    try:
        return p.chromium.launch(**kwargs)
    except Exception:
        return p.chromium.launch(executable_path=FALLBACK_EXECUTABLE_PATH, **kwargs)


def try_fetch(p, args, proxy_url, ignore_tls):
    browser = launch_browser(p, proxy_url)
    try:
        context = browser.new_context(user_agent=DEFAULT_UA,
                                      ignore_https_errors=ignore_tls)
        page = context.new_page()
        page.goto(args.url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(args.wait)
        if args.html:
            return page.content()
        text = page.evaluate("document.body.innerText")
        return text if text is not None else ""
    finally:
        browser.close()


def main():
    args = parse_args()
    ensure_proxy_ca_in_nss()

    # Chromiumは環境変数のプロキシ設定を確実には拾わないため明示的に渡す。
    # それでも環境によりプロキシとの相性問題(TLS再終端の信用不可、透過
    # プロキシ等)があるので、駄目なら順にフォールバックする:
    #   1. 明示プロキシ + TLS検証あり
    #   2. 明示プロキシ + TLS検証なし(プロキシCAを信用できない場合の最終手段。
    #      経路上のMITMはサンドボックス自身のプロキシのみで、用途は公開ページの
    #      読み取り専用のため許容する)
    #   3. プロキシ指定なし(透過プロキシ環境向け)+ TLS検証あり
    #   4. プロキシ指定なし + TLS検証なし
    proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    attempts = [(proxy_url, False), (proxy_url, True)] if proxy_url else []
    attempts += [(None, False), (None, True)]

    content = None
    errors = []
    with sync_playwright() as p:
        for purl, ignore_tls in attempts:
            try:
                content = try_fetch(p, args, purl, ignore_tls)
                break
            except Exception as e:
                errors.append(
                    f"[proxy={'明示' if purl else 'なし'}, "
                    f"TLS検証={'なし' if ignore_tls else 'あり'}] {e}")

    if content is None:
        print("ページの取得に失敗しました:\n  " + "\n  ".join(errors),
              file=sys.stderr)
        sys.exit(1)

    if len(content) > args.max_chars:
        content = content[: args.max_chars]

    print(content)


if __name__ == "__main__":
    main()
