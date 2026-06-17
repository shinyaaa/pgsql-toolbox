# -*- coding: utf-8 -*-
"""Generate the pgstat_get_beentry_by_proc_number internals doc site."""
import os, re

HERE = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(HERE, "..", "..", "..", ".claude", "skills", "db-internals-docs", "assets")

SITE_TITLE = "pgstat_get_beentry_by_proc_number の内部構造"
VERSION_INFO = "PostgreSQL 19beta1 · 0131e8fc508 · 2026-06-17 06:51"
FOOTER = ("pgstat_get_beentry_by_proc_number の内部構造 — "
          "PostgreSQL のソースコード (shinyaaa/postgres @0131e8fc508) を基に作成。"
          "本文中のコードリンクは当該コミットのパーマリンク。")
GH = "https://github.com/shinyaaa/postgres/blob/0131e8fc508ff8e10a6797bfe8043a0b9d34b30b"


def _strip_doc_comment(s):
    return re.sub(r"<!--.*?-->\n?", "", s, count=1, flags=re.DOTALL)


def page_tpl():
    with open(os.path.join(TPL, "page-template.html"), encoding="utf-8") as f:
        return _strip_doc_comment(f.read())


def index_tpl():
    with open(os.path.join(TPL, "index-template.html"), encoding="utf-8") as f:
        return _strip_doc_comment(f.read())


# ---- chapter definitions -------------------------------------------------
chapters = []


def ch(num, title, desc, sections, body):
    chapters.append(dict(num=num, title=title, desc=desc, sections=sections, body=body))


import bodies as B

ch(1, "バックエンドステータスと ProcNumber",
   "バックエンドの現在の活動を共有メモリに公示する仕組みと、エントリを指す ProcNumber、そして本関数の呼び出し階層を概観する。",
   [("sec-1-1", "1.1 バックエンドの「現在の活動」を共有する仕組み"),
    ("sec-1-2", "1.2 ProcNumber — エントリを指すインデックス"),
    ("sec-1-3", "1.3 関数の役割と呼び出し階層")],
   B.ch1)

ch(2, "データ構造",
   "活動エントリ PgBackendStatus、共有配列 BackendStatusArray、ローカルスナップショット LocalPgBackendStatus の三層を読む。",
   [("sec-2-1", "2.1 PgBackendStatus — 共有メモリ上の活動エントリ"),
    ("sec-2-2", "2.2 BackendStatusArray と NumBackendStatSlots"),
    ("sec-2-3", "2.3 LocalPgBackendStatus — ローカルスナップショット")],
   B.ch2)

ch(3, "ローカルスナップショットの構築",
   "pgstat_read_current_status が共有配列をローカルへコピーする過程と、changecount プロトコル・proc_number 順の保証を追う。",
   [("sec-3-1", "3.1 トランザクション内で一度だけコピーする"),
    ("sec-3-2", "3.2 changecount プロトコルによる無ロック読み取り"),
    ("sec-3-3", "3.3 有効エントリの抽出と proc_number 順の保証")],
   B.ch3)

ch(4, "検索の実装を読む",
   "本体三関数 pgstat_get_beentry_by_proc_number / local 版 / cmp_lbestatus による bsearch を読み、by_index との違いを整理する。",
   [("sec-4-1", "4.1 pgstat_get_beentry_by_proc_number"),
    ("sec-4-2", "4.2 pgstat_get_local_beentry_by_proc_number と bsearch"),
    ("sec-4-3", "4.3 by_index との違い")],
   B.ch4)

ch(5, "SQL 関数からの利用と権限",
   "pgstatfuncs.c での呼び出しパターン、HAS_PGSTAT_PERMISSIONS による権限チェックの責務、そして実行例での観察方法を示す。",
   [("sec-5-1", "5.1 pgstatfuncs.c での呼び出しパターン"),
    ("sec-5-2", "5.2 権限チェックは呼び出し側の責任"),
    ("sec-5-3", "5.3 実行例で観察する")],
   B.ch5)

ch(6, "まとめと注意点",
   "スナップショットの寿命、補助プロセスや無効な ProcNumber の扱いを整理し、本関数の要点をまとめる。",
   [("sec-6-1", "6.1 スナップショットの寿命"),
    ("sec-6-2", "6.2 補助プロセスと無効な ProcNumber"),
    ("sec-6-3", "6.3 まとめ")],
   B.ch6)


# ---- helpers -------------------------------------------------------------
def fname(num):
    return "ch%02d.html" % num


def sidebar(cur):
    out = ["<ol>"]
    for c in chapters:
        cls = ' class="current"' if c["num"] == cur else ""
        out.append('  <li%s>' % cls)
        out.append('    <a class="chap-title" href="%s">第%d章 %s</a>'
                   % (fname(c["num"]), c["num"], c["title"]))
        out.append('    <ol class="sect">')
        for sid, label in c["sections"]:
            out.append('      <li><a href="%s#%s">%s</a></li>' % (fname(c["num"]), sid, label))
        out.append('    </ol>')
        out.append('  </li>')
    out.append("</ol>")
    return "\n".join(out)


def pager(num):
    parts = []
    prev_c = next((c for c in chapters if c["num"] == num - 1), None)
    next_c = next((c for c in chapters if c["num"] == num + 1), None)
    if prev_c:
        parts.append('<a class="prev" href="%s">\n  <span class="dir">← 前の章</span>\n  <span class="ttl">第%d章 %s</span>\n</a>'
                     % (fname(prev_c["num"]), prev_c["num"], prev_c["title"]))
    else:
        parts.append('<span class="pager-spacer" aria-hidden="true"></span>')
    parts.append('<a class="up" href="index.html">\n  <span class="dir">↑ 目次</span>\n  <span class="ttl">トップページ</span>\n</a>')
    if next_c:
        parts.append('<a class="next" href="%s">\n  <span class="dir">次の章 →</span>\n  <span class="ttl">第%d章 %s</span>\n</a>'
                     % (fname(next_c["num"]), next_c["num"], next_c["title"]))
    else:
        parts.append('<span class="pager-spacer" aria-hidden="true"></span>')
    return "\n".join(parts)


# ---- render --------------------------------------------------------------
pt = page_tpl()
for c in chapters:
    html = (pt
            .replace("{{SITE_TITLE}}", SITE_TITLE)
            .replace("{{VERSION_INFO}}", VERSION_INFO)
            .replace("{{PAGE_TITLE}}", "第%d章 %s" % (c["num"], c["title"]))
            .replace("{{SIDEBAR_TOC}}", sidebar(c["num"]))
            .replace("{{CHAPTER_NUMBER}}", "第%d章" % c["num"])
            .replace("{{CHAPTER_TITLE}}", c["title"])
            .replace("{{CHAPTER_BODY}}", c["body"].strip())
            .replace("{{PAGER}}", pager(c["num"]))
            .replace("{{FOOTER}}", FOOTER)
            .replace("%%GH%%", GH))
    with open(os.path.join(HERE, fname(c["num"])), "w", encoding="utf-8") as f:
        f.write(html)

# index
cards = []
for c in chapters:
    cards.append('<a class="toc-card" href="%s">\n  <span class="num">第%d章</span>\n  <span class="title">%s</span>\n  <span class="desc">%s</span>\n</a>'
                 % (fname(c["num"]), c["num"], c["title"], c["desc"]))
lead = ("PostgreSQL の各バックエンドは「いま何をしているか」を共有メモリ上の "
        "<code>PgBackendStatus</code> に公示する。"
        "<code>pgstat_get_beentry_by_proc_number()</code> は、その中から指定した "
        "<em>ProcNumber</em> のエントリを一つ取り出す内部 API であり、"
        "<code>pg_stat_get_backend_*</code> 系の SQL 関数群を下支えする。"
        "本ドキュメントは PostgreSQL 19beta1 のソースコードを基に、関連するデータ構造、"
        "無ロックでのスナップショット構築、bsearch による検索、SQL 関数からの利用と権限までを順に解説する。"
        "共有メモリとトランザクション ID の基礎を持つ読者を想定する。")
it = (index_tpl()
      .replace("{{SITE_TITLE}}", SITE_TITLE)
      .replace("{{VERSION_INFO}}", VERSION_INFO)
      .replace("{{LEAD}}", lead)
      .replace("{{SIDEBAR_TOC}}", sidebar(-1))
      .replace("{{TOC_CARDS}}", "\n".join(cards))
      .replace("{{FOOTER}}", FOOTER)
      .replace("%%GH%%", GH))
with open(os.path.join(HERE, "index.html"), "w", encoding="utf-8") as f:
    f.write(it)

print("generated", len(chapters), "chapters + index")
