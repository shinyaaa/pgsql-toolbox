# -*- coding: utf-8 -*-
"""Generate the ComputeXidHorizons internals doc site."""
import os, re

HERE = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(HERE, "..", "..", "..", ".claude", "skills", "db-internals-docs", "assets")

SITE_TITLE = "ComputeXidHorizons の内部構造"
VERSION_INFO = "PostgreSQL 19beta1 · 0131e8fc508 · 2026-06-16 12:29"
FOOTER = "ComputeXidHorizons の内部構造 — PostgreSQL のソースコード (shinyaaa/postgres @0131e8fc508) を基に作成。本文中のコードリンクは当該コミットのパーマリンク。"
GH = "https://github.com/shinyaaa/postgres/blob/0131e8fc508ff8e10a6797bfe8043a0b9d34b30b"

def _strip_doc_comment(s):
    # テンプレート冒頭の説明コメントは {{...}} トークンを含むため、
    # 置換前に取り除く（DOCTYPE 宣言の直後の最初の <!-- ... --> を削除）。
    return re.sub(r"<!--.*?-->\n?", "", s, count=1, flags=re.DOTALL)

def page_tpl():
    with open(os.path.join(TPL, "page-template.html"), encoding="utf-8") as f:
        return _strip_doc_comment(f.read())

def index_tpl():
    with open(os.path.join(TPL, "index-template.html"), encoding="utf-8") as f:
        return _strip_doc_comment(f.read())

# ---- chapter definitions -------------------------------------------------
# each: (num, title, desc, sections=[(id, label)], body)
chapters = []

def ch(num, title, desc, sections, body):
    chapters.append(dict(num=num, title=title, desc=desc, sections=sections, body=body))

# bodies are defined in separate module to keep this file readable
import bodies as B

ch(1, "XID ホライズンの背景と必要性",
   "MVCC と不要タプル、可視性判定の下界としての oldest xmin、そして ComputeXidHorizons が担う役割を整理する。",
   [("sec-1-1", "1.1 MVCC と不要タプル"),
    ("sec-1-2", "1.2 下界としての oldest xmin"),
    ("sec-1-3", "1.3 GetSnapshotData が正確値をやめた理由"),
    ("sec-1-4", "1.4 ComputeXidHorizons の位置づけ")],
   B.ch1)

ch(2, "ComputeXidHorizonsResult — 計算される地平線たち",
   "結果を格納する構造体 ComputeXidHorizonsResult の全フィールドと、リレーション種別ごとに地平線が分かれる理由を読む。",
   [("sec-2-1", "2.1 4種のリレーションと地平線"),
    ("sec-2-2", "2.2 構造体の全フィールド"),
    ("sec-2-3", "2.3 地平線の大小関係")],
   B.ch2)

ch(3, "ComputeXidHorizons の実装を読む",
   "ProcArrayLock の取得、latestCompletedXid + 1 による初期化、ProcArray の走査、リカバリとスロットの反映までを追う。",
   [("sec-3-1", "3.1 ロックと初期値"),
    ("sec-3-2", "3.2 ProcArray の走査"),
    ("sec-3-3", "3.3 フラグとデータベースの考慮"),
    ("sec-3-4", "3.4 リカバリと KnownAssignedXids"),
    ("sec-3-5", "3.5 スロットの反映と整合性検証")],
   B.ch3)

ch(4, "GlobalVisState と近似境界",
   "正確な計算を避けるための近似境界 definitely_needed / maybe_needed と、GlobalVisTest* による可視性判定の仕組みを解説する。",
   [("sec-4-1", "4.1 二つの境界"),
    ("sec-4-2", "4.2 GetSnapshotData による更新"),
    ("sec-4-3", "4.3 GlobalVisTest* による判定"),
    ("sec-4-4", "4.4 再計算のヒューリスティック")],
   B.ch4)

ch(5, "ホライズンの利用者たち",
   "VACUUM・pg_subtrans の切り詰め・hot_standby_feedback という三つの利用者が、どの地平線をどう使い分けるかを見る。",
   [("sec-5-1", "5.1 VACUUM の刈り取り境界"),
    ("sec-5-2", "5.2 pg_subtrans の切り詰め"),
    ("sec-5-3", "5.3 hot_standby_feedback")],
   B.ch5)

ch(6, "ホライズンを観察する",
   "backend_xmin やレプリケーションスロットを通じて地平線の動きを観察し、巻き戻りや長時間トランザクションの影響を確認する。",
   [("sec-6-1", "6.1 backend_xmin を覗く"),
    ("sec-6-2", "6.2 スロットによる引き戻し"),
    ("sec-6-3", "6.3 巻き戻りと運用上の注意")],
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
            .replace("{{FOOTER}}", FOOTER))
    with open(os.path.join(HERE, fname(c["num"])), "w", encoding="utf-8") as f:
        f.write(html)

# index
cards = []
for c in chapters:
    cards.append('<a class="toc-card" href="%s">\n  <span class="num">第%d章</span>\n  <span class="title">%s</span>\n  <span class="desc">%s</span>\n</a>'
                 % (fname(c["num"]), c["num"], c["title"], c["desc"]))
lead = ("不要になったタプルをいつ削除してよいか — PostgreSQL の MVCC はこの判断を "
        "<em>XID ホライズン（地平線）</em> に委ねている。"
        "<code>ComputeXidHorizons()</code> は ProcArray を一度走査し、VACUUM の刈り取り境界、"
        "<code>pg_subtrans</code> の切り詰め点、ホットスタンバイフィードバックの xmin といった複数の地平線を"
        "まとめて算出する中核関数である。本ドキュメントは PostgreSQL 19beta1 のソースコードを基に、"
        "この関数が計算する各地平線の意味、実装、近似境界 <code>GlobalVisState</code> との関係、"
        "そして利用者と観察方法までを解説する。MVCC とトランザクション ID の基礎を持つ読者を想定する。")
it = (index_tpl()
      .replace("{{SITE_TITLE}}", SITE_TITLE)
      .replace("{{VERSION_INFO}}", VERSION_INFO)
      .replace("{{LEAD}}", lead)
      .replace("{{SIDEBAR_TOC}}", sidebar(-1))
      .replace("{{TOC_CARDS}}", "\n".join(cards))
      .replace("{{FOOTER}}", FOOTER))
with open(os.path.join(HERE, "index.html"), "w", encoding="utf-8") as f:
    f.write(it)

print("generated", len(chapters), "chapters + index")
