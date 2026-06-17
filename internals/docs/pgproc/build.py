# -*- coding: utf-8 -*-
"""Generate the PGPROC internals documentation HTML pages."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "..", "..", "..", ".claude", "skills", "db-internals-docs", "assets")

SITE_TITLE = "PGPROC の内部構造"
VERSION_INFO = "PostgreSQL 19beta1 · 0131e8fc508 · 2026-06-17 06:41"
GH = "https://github.com/shinyaaa/postgres/blob/0131e8fc508ff8e10a6797bfe8043a0b9d34b30b"
FOOTER = ('The Internals of PostgreSQL 風の内部構造解説 · ' + VERSION_INFO +
          ' · ソース: <a href="https://github.com/shinyaaa/postgres">shinyaaa/postgres</a>')

# ---- Chapter / section structure ------------------------------------------
CHAPTERS = [
    ("PGPROCとは", [
        ("1-1", "1.1 PGPROCの役割"),
        ("1-2", "1.2 MyProc と ProcNumber"),
        ("1-3", "1.3 PGPROC を持つプロセスの種類"),
    ]),
    ("PGPROC構造体のレイアウト", [
        ("2-1", "2.1 バックエンドの識別情報"),
        ("2-2", "2.2 トランザクションとスナップショット"),
        ("2-3", "2.3 プロセス間シグナリングと待機"),
        ("2-4", "2.4 ロックマネージャ関連フィールド"),
    ]),
    ("ProcGlobal と共有メモリ配置", [
        ("3-1", "3.1 PROC_HDR と allProcs 配列"),
        ("3-2", "3.2 フリーリストとプロセス種別"),
        ("3-3", "3.3 密な並列配列とミラーリング"),
    ]),
    ("PGPROCのライフサイクル", [
        ("4-1", "4.1 共有メモリの確保"),
        ("4-2", "4.2 PGPROC の割り当て"),
        ("4-3", "4.3 ProcArray への登録"),
        ("4-4", "4.4 PGPROC の解放"),
    ]),
    ("PGPROCを介した協調動作", [
        ("5-1", "5.1 ヘビーウェイトロックの待機キュー"),
        ("5-2", "5.2 グループ XID クリア"),
        ("5-3", "5.3 ロックグループと並列クエリ"),
        ("5-4", "5.4 同期レプリケーションの待機"),
    ]),
    ("PGPROCを観察する", [
        ("6-1", "6.1 pg_stat_activity との対応"),
        ("6-2", "6.2 pg_locks と待機関係"),
        ("6-3", "6.3 待機イベントの確認"),
    ]),
]

CHAP_DESC = [
    "プロセスごとに共有メモリ上に確保される PGPROC 構造体の役割と、バックエンドとの対応関係を概観する。",
    "PGPROC のフィールドを識別情報・トランザクション・シグナリング・ロックの観点で分類して読み解く。",
    "全 PGPROC を束ねる PROC_HDR、フリーリスト、そして密にパックされたミラー配列の設計を解説する。",
    "共有メモリ確保から割り当て・ProcArray 登録・解放までの一連の流れを追う。",
    "待機キュー・グループ XID クリア・ロックグループ・同期レプリケーションなど協調動作の実装を見る。",
    "pg_stat_activity や pg_locks など、PGPROC の状態を外から観察する方法を示す。",
]


def page_title(i):
    return "第%d章 %s" % (i + 1, CHAPTERS[i][0])


def sidebar(cur_chap, cur_sec=None):
    out = ["<ol>"]
    for ci, (title, secs) in enumerate(CHAPTERS):
        chap_cls = ' class="current"' if ci == cur_chap else ""
        out.append('  <li%s>' % chap_cls)
        out.append('    <a class="chap-title" href="ch%02d.html">第%d章 %s</a>'
                   % (ci + 1, ci + 1, title))
        out.append('    <ol class="sect">')
        for sid, stext in secs:
            a_cls = ' class="current"' if (ci == cur_chap and sid == cur_sec) else ""
            out.append('      <li><a%s href="ch%02d.html#sec-%s">%s</a></li>'
                       % (a_cls, ci + 1, sid, stext))
        out.append('    </ol>')
        out.append('  </li>')
    out.append("</ol>")
    return "\n".join(out)


def pager(i):
    n = len(CHAPTERS)
    parts = []
    if i > 0:
        parts.append('<a class="prev" href="ch%02d.html">\n  <span class="dir">← 前の章</span>\n  <span class="ttl">%s</span>\n</a>' % (i, page_title(i - 1)))
    else:
        parts.append('<span class="pager-spacer" aria-hidden="true"></span>')
    parts.append('<a class="up" href="index.html">\n  <span class="dir">↑ 目次</span>\n  <span class="ttl">トップページ</span>\n</a>')
    if i < n - 1:
        parts.append('<a class="next" href="ch%02d.html">\n  <span class="dir">次の章 →</span>\n  <span class="ttl">%s</span>\n</a>' % (i + 2, page_title(i + 1)))
    else:
        parts.append('<span class="pager-spacer" aria-hidden="true"></span>')
    return "\n".join(parts)


# ---- Bodies are filled from BODIES dict (defined in bodies.py) -------------
from bodies import BODIES


import re

def _strip_comments(s):
    # Remove the leading documentation comment, which itself contains {{...}}
    # placeholder names and would otherwise be substituted too.
    return re.sub(r"<!--.*?-->", "", s, count=1, flags=re.DOTALL)


def build():
    tmpl = _strip_comments(open(os.path.join(ASSETS, "page-template.html"), encoding="utf-8").read())
    itmpl = _strip_comments(open(os.path.join(ASSETS, "index-template.html"), encoding="utf-8").read())

    for i, (title, secs) in enumerate(CHAPTERS):
        html = tmpl
        repl = {
            "{{SITE_TITLE}}": SITE_TITLE,
            "{{VERSION_INFO}}": VERSION_INFO,
            "{{PAGE_TITLE}}": page_title(i),
            "{{SIDEBAR_TOC}}": sidebar(i, secs[0][0] if False else None) if False else sidebar(i),
            "{{CHAPTER_NUMBER}}": "第%d章" % (i + 1),
            "{{CHAPTER_TITLE}}": title,
            "{{CHAPTER_BODY}}": BODIES[i],
            "{{PAGER}}": pager(i),
            "{{FOOTER}}": FOOTER,
        }
        for k, v in repl.items():
            html = html.replace(k, v)
        with open(os.path.join(HERE, "ch%02d.html" % (i + 1)), "w", encoding="utf-8") as f:
            f.write(html)

    # index
    cards = []
    for i, (title, secs) in enumerate(CHAPTERS):
        cards.append('<a class="toc-card" href="ch%02d.html">\n'
                     '  <span class="num">第%d章</span>\n'
                     '  <span class="title">%s</span>\n'
                     '  <span class="desc">%s</span>\n'
                     '</a>' % (i + 1, i + 1, title, CHAP_DESC[i]))
    lead = (
        "本ドキュメントは、PostgreSQL がプロセスごとに共有メモリ上へ確保する "
        "<code>PGPROC</code> 構造体の内部構造を、ソースコードを根拠に解き明かす技術解説である。"
        "<code>PGPROC</code> は、各バックエンドや補助プロセスが「いま何のトランザクションを実行し、"
        "どのロックを待ち、どのスナップショット地平を持つか」を他プロセスへ広告するための中核データ構造であり、"
        "MVCC・ロックマネージャ・スナップショット取得・同期レプリケーションといった PostgreSQL の根幹機能が "
        "ここに集約される。対象バージョンは <strong>PostgreSQL 19beta1</strong>。"
        "PostgreSQL のアーキテクチャに一通り触れたことのある開発者・運用者を想定読者とする。"
    )
    html = itmpl
    for k, v in {
        "{{SITE_TITLE}}": SITE_TITLE,
        "{{VERSION_INFO}}": VERSION_INFO,
        "{{LEAD}}": lead,
        "{{SIDEBAR_TOC}}": sidebar(-1),
        "{{TOC_CARDS}}": "\n".join(cards),
        "{{FOOTER}}": FOOTER,
    }.items():
        html = html.replace(k, v)
    with open(os.path.join(HERE, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print("done")


if __name__ == "__main__":
    build()
