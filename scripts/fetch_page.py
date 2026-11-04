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
    3  … Chromium のサンドボックスを有効にできない(降格不可など。描画を諦める)

セキュリティ上の前提(SECURITY_NOTES.md 2):
    巡回先は信頼できない HTML なので、
      1. 描画に使うブラウザは毎回 Chrome for Testing の最新安定版(headless shell)に揃える
         (Playwright 同梱の版は安定版より古い開発スナップショットなので使わない)。
      2. Chromium のサンドボックスを有効にする。Playwright は既定で無効(--no-sandbox)にし、
         root では Chromium 自身がサンドボックス起動を拒否するため、root で動く環境では
         専用の非 root ユーザーに降格して自分自身を再実行する。
    サンドボックスを有効にできない環境(root のまま降格できない等)では、保護なしで
    描画せず終了コード 3 で諦める(fetch_all.py は通常取得に戻し、その旨を notes に載せる)。
    検証用: SR_NO_BROWSER_DOWNLOAD=1(ブラウザをダウンロードしない)。
"""

import argparse
import json
import os
import pwd
import shutil
import stat
import subprocess
import sys
import urllib.request
import zipfile

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    # 2026-10-20: クラウド環境のうち片方は playwright の Python パッケージだけが無い
    # (ブラウザ本体 /opt/pw-browsers/chromium は同梱)。日次の fetch_all.py から呼ばれても
    # 止まらないよう、一度だけ pip でパッケージを入れて再試行する(ブラウザはダウンロードしない)。
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                        "playwright"], check=True, timeout=180,
                       env={**os.environ, "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD": "1"},
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        from playwright.sync_api import sync_playwright
    except Exception:
        print(
            "playwright がインストールされていません(自動導入も失敗)。"
            "pip install playwright を実行せよ"
            "(ブラウザのダウンロードは不要。playwright install は実行しないこと)。",
            file=sys.stderr,
        )
        sys.exit(2)

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)

FALLBACK_EXECUTABLE_PATH = "/opt/pw-browsers/chromium"

BROWSERS_DIR = (os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
                or os.path.expanduser("~/.cache/ms-playwright"))

# Chrome for Testing の公式メタデータ(Google が公開。安定版の版番号と配布 URL が載る)
CFT_VERSIONS_URL = ("https://googlechromelabs.github.io/chrome-for-testing/"
                    "last-known-good-versions-with-downloads.json")
CFT_DIR_PREFIX = "cft-headless-shell-"
CFT_EXE_RELPATH = os.path.join("chrome-headless-shell-linux64", "chrome-headless-shell")

# 降格先のユーザー(無ければ useradd で作る)
SANDBOX_USER = os.environ.get("SR_SANDBOX_USER", "sr-chromium")
# 親(root)→子(降格後)に渡す環境変数
ENV_CHILD = "SR_SANDBOX_CHILD"
ENV_BROWSER_EXE = "SR_BROWSER_EXE"
ENV_PROXY_CA = "SR_PROXY_CA"

PROXY_CA_CANDIDATES = ("/root/.ccr/agent-proxy-ca.crt",)


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


def log(msg):
    print(f"fetch_page: {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# プロキシ CA
# ---------------------------------------------------------------------------

def find_proxy_ca():
    for ca in (os.environ.get(ENV_PROXY_CA),) + PROXY_CA_CANDIDATES + \
              (os.environ.get("NODE_EXTRA_CA_CERTS"),):
        if ca and os.path.isfile(ca) and os.access(ca, os.R_OK):
            return ca
    return None


def ensure_proxy_ca_in_nss():
    """クラウド実行環境の外向きプロキシはTLSを再終端するため、Chromiumが
    そのCAを信用できないと接続に失敗する。curl等はCA環境変数で対応済みだが
    ChromiumはNSSストア($HOME/.pki/nssdb)しか見ないので、プロキシCAの登録を
    試みる。certutilが無い等で失敗しても続行する(best effort)。"""
    ca = find_proxy_ca()
    if not ca or not shutil.which("certutil"):
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


# ---------------------------------------------------------------------------
# ブラウザの用意(Chrome for Testing 最新安定版 → Playwright 既定版 → 同梱版)
# ---------------------------------------------------------------------------

def _make_world_readable(path):
    """降格後のユーザーが読める・実行できるようにする(root で呼ぶ)。失敗しても続行。"""
    try:
        for root, dirs, files in os.walk(path):
            for d in dirs:
                p = os.path.join(root, d)
                os.chmod(p, os.stat(p).st_mode | 0o555)
            for f in files:
                p = os.path.join(root, f)
                m = os.stat(p).st_mode
                os.chmod(p, m | 0o444 | (0o111 if m & 0o100 else 0))
        os.chmod(path, os.stat(path).st_mode | 0o555)
    except Exception:
        pass


def _extract_zip(zpath, dest):
    """zip を dest に展開する。実行ビットを保持し、dest の外に出る名前は捨てる。"""
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            name = info.filename
            if not name or name.startswith("/") or ".." in name.split("/"):
                continue
            target = os.path.join(dest, name)
            if info.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            mode = (info.external_attr >> 16) & 0o777
            if mode:
                os.chmod(target, mode)


def _installed_cft():
    """既に展開済みの Chrome for Testing のうち最新の版の実行ファイル。無ければ None。"""
    try:
        names = sorted((n for n in os.listdir(BROWSERS_DIR) if n.startswith(CFT_DIR_PREFIX)),
                       key=lambda n: [int(x) if x.isdigit() else 0
                                      for x in n[len(CFT_DIR_PREFIX):].split(".")])
    except OSError:
        return None
    for n in reversed(names):
        exe = os.path.join(BROWSERS_DIR, n, CFT_EXE_RELPATH)
        if os.access(exe, os.X_OK):
            return exe
    return None


def ensure_cft_stable():
    """Chrome for Testing の最新安定版 headless shell を用意し、実行ファイルのパスを返す。

    毎回メタデータ(小さな JSON)を見て、その版が未展開ならダウンロードする(約 130 MB・
    10〜20 秒。コンテナは使い捨てなので日次 1 回)。ダウンロードできない環境では展開済みの
    最新版、それも無ければ None を返す(呼び出し側が Playwright 既定版→同梱版に戻る)。"""
    if os.environ.get("SR_NO_BROWSER_DOWNLOAD"):
        return _installed_cft()
    try:
        with urllib.request.urlopen(CFT_VERSIONS_URL, timeout=20) as r:
            meta = json.load(r)
        stable = meta["channels"]["Stable"]
        version = stable["version"]
        url = next(d["url"] for d in stable["downloads"]["chrome-headless-shell"]
                   if d["platform"] == "linux64")
    except Exception as e:
        log(f"Chrome for Testing のメタデータ取得に失敗({e.__class__.__name__})。展開済みの版を探す")
        return _installed_cft()
    dest = os.path.join(BROWSERS_DIR, CFT_DIR_PREFIX + version)
    exe = os.path.join(dest, CFT_EXE_RELPATH)
    if os.access(exe, os.X_OK):
        return exe
    tmp = dest + ".tmp"
    zpath = dest + ".zip"
    try:
        os.makedirs(BROWSERS_DIR, exist_ok=True)
        shutil.rmtree(tmp, ignore_errors=True)
        with urllib.request.urlopen(url, timeout=60) as r, open(zpath, "wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
        _extract_zip(zpath, tmp)
        if not os.path.isfile(os.path.join(tmp, CFT_EXE_RELPATH)):
            raise RuntimeError("展開後に実行ファイルが見つからない")
        os.chmod(os.path.join(tmp, CFT_EXE_RELPATH), 0o755)
        os.replace(tmp, dest)
        _make_world_readable(dest)
        log(f"Chrome for Testing 安定版 {version} を導入した")
        return exe
    except Exception as e:
        log(f"Chrome for Testing 安定版 {version} の導入に失敗({e.__class__.__name__}: {e})")
        shutil.rmtree(tmp, ignore_errors=True)
        return _installed_cft()
    finally:
        try:
            os.remove(zpath)
        except OSError:
            pass


INSTALL_MARKER = os.path.join(BROWSERS_DIR, ".seminar-radar-install-attempted")


def ensure_current_browser():
    """Chrome for Testing が使えないときの次善: Playwright が期待する版の Chromium
    (headless shell)が無ければ 1 回だけダウンロードする(約 280 MB・10 秒前後)。
    ダウンロードできない環境(Codex Cloud 等)では失敗を記録して同梱版に戻る。"""
    if os.environ.get("SR_NO_BROWSER_DOWNLOAD") or os.path.exists(INSTALL_MARKER):
        return
    try:
        os.makedirs(os.path.dirname(INSTALL_MARKER), exist_ok=True)
        open(INSTALL_MARKER, "w").close()      # 失敗しても同じセッションで再試行しない
        env = {k: v for k, v in os.environ.items() if k != "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"}
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium-headless-shell"],
                       check=False, timeout=240, env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 非 root ユーザーへの降格(サンドボックス有効化のため)
# ---------------------------------------------------------------------------

def _ensure_user(name):
    try:
        return pwd.getpwnam(name)
    except KeyError:
        pass
    if not shutil.which("useradd"):
        return None
    r = subprocess.run(["useradd", "-m", "-s", "/usr/sbin/nologin", name],
                       capture_output=True, timeout=30)
    if r.returncode != 0:
        return None
    try:
        return pwd.getpwnam(name)
    except KeyError:
        return None


def reexec_unprivileged(argv):
    """root で動いているなら、ブラウザを用意した上で専用ユーザーに降格して自分を再実行する。
    子の終了コードを返す。準備のどこかで失敗したら None(呼び出し側は描画を諦める)。"""
    if os.geteuid() != 0 or os.environ.get(ENV_CHILD):
        return None
    if not shutil.which("setpriv"):
        log("setpriv が無いため降格できない")
        return None
    exe = ensure_cft_stable()
    if exe is None:
        ensure_current_browser()           # Playwright 既定版を root のうちに用意しておく
    pw = _ensure_user(SANDBOX_USER)
    if pw is None:
        log(f"ユーザー {SANDBOX_USER} を用意できないため降格できない")
        return None
    home = pw.pw_dir
    try:
        os.makedirs(home, exist_ok=True)
        os.chown(home, pw.pw_uid, pw.pw_gid)
        # 降格後も読めるように、ブラウザ置き場・このスクリプト・プロキシ CA を揃える
        try:
            os.chmod(BROWSERS_DIR, os.stat(BROWSERS_DIR).st_mode | 0o555)
        except OSError:
            pass
        script = os.path.join(home, "fetch_page.py")
        shutil.copyfile(os.path.abspath(__file__), script)
        os.chown(script, pw.pw_uid, pw.pw_gid)
        env = {
            "HOME": home,
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "LANG": "C.UTF-8",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
            "PLAYWRIGHT_BROWSERS_PATH": BROWSERS_DIR,
            "SR_NO_BROWSER_DOWNLOAD": "1",      # 子はダウンロードしない(書き込めない)
            ENV_CHILD: "1",
        }
        for k in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy",
                  "NO_PROXY", "no_proxy", "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"):
            if k in os.environ:
                env[k] = os.environ[k]
        if exe:
            env[ENV_BROWSER_EXE] = exe
        ca = find_proxy_ca()
        if ca:
            ca_copy = os.path.join(home, "agent-proxy-ca.crt")
            shutil.copyfile(ca, ca_copy)
            os.chown(ca_copy, pw.pw_uid, pw.pw_gid)
            env[ENV_PROXY_CA] = ca_copy
    except Exception as e:
        log(f"降格の準備に失敗({e.__class__.__name__}: {e})")
        return None
    cmd = ["setpriv", f"--reuid={pw.pw_uid}", f"--regid={pw.pw_gid}", "--init-groups",
           "--", sys.executable, script] + list(argv)
    try:
        r = subprocess.run(cmd, env=env)
    except Exception as e:
        log(f"降格した再実行に失敗({e.__class__.__name__}: {e})")
        return None
    return r.returncode


# ---------------------------------------------------------------------------
# 起動と取得
# ---------------------------------------------------------------------------

def browser_candidates():
    """試す順: 明示された実行ファイル(親が用意した CfT 安定版)→ 展開済み CfT →
    Playwright 既定版(None)→ 同梱版。"""
    cands = []
    for exe in (os.environ.get(ENV_BROWSER_EXE), _installed_cft()):
        if exe and os.access(exe, os.X_OK) and exe not in cands:
            cands.append(exe)
    cands.append(None)
    if os.access(FALLBACK_EXECUTABLE_PATH, os.X_OK):
        cands.append(FALLBACK_EXECUTABLE_PATH)
    return cands


class LaunchFailed(Exception):
    """ブラウザ自体が起動できない(ページ側の失敗と区別する)。"""


def launch_browser(p, proxy_url):
    kwargs = {"headless": True, "chromium_sandbox": True}
    if proxy_url:
        kwargs["proxy"] = {"server": proxy_url}
    last = None
    for exe in browser_candidates():
        try:
            if exe is None:
                try:
                    return p.chromium.launch(**kwargs)
                except Exception:
                    ensure_current_browser()
                    return p.chromium.launch(**kwargs)
            return p.chromium.launch(executable_path=exe, **kwargs)
        except Exception as e:
            last = e
            log(f"起動に失敗(exe={exe or 'playwright既定'}): "
                f"{str(e).splitlines()[0][:160]}")
    raise LaunchFailed(str(last) if last else "起動できるブラウザが無い")


def try_fetch(p, args, proxy_url, ignore_tls):
    browser = launch_browser(p, proxy_url)
    try:
        log(f"Chromium {browser.version} sandbox=on uid={os.geteuid()}")
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
    rc = reexec_unprivileged(sys.argv[1:])
    if rc is not None:
        sys.exit(rc)

    args = parse_args()
    if os.geteuid() == 0:
        # root では Chromium がサンドボックス起動を拒否する。保護なしで描画はしない。
        log("サンドボックスを有効にできない(root のまま降格できなかった)ため Chromium 描画を諦める")
        sys.exit(3)
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
            except LaunchFailed as e:
                # サンドボックス有効で起動できないなら、無効にして試さず諦める
                log(f"サンドボックス有効でブラウザを起動できないため Chromium 描画を諦める: {e}")
                sys.exit(3)
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
