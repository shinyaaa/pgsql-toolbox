#!/usr/bin/env python3
"""pgbench カスタムスクリプト実践ガイドのページ生成スクリプト。

    python3 build.py

を実行すると、このディレクトリに index.html と chNN.html を書き出す。
本文は bodies.py に置いてある。
"""
from pathlib import Path

from bodies import CHAPTERS

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent.parent.parent / ".claude" / "skills" / "db-user-docs" / "assets"

SITE_TITLE = "pgbench カスタムスクリプト実践ガイド"
VERSION_INFO = "PostgreSQL 18 · 2026-07-29"
AUDIENCE = (
    "対象: <code>pgbench -i</code> / <code>-c</code> / <code>-T</code> は使えるが、"
    "<code>-f</code> で自前のシナリオを書くのはこれからという方"
)
LEAD = (
    "組み込みの <code>tpcb-like</code> では測れないワークロードを、"
    "自分で書いたスクリプトで測れるようになるためのガイド。"
    "<code>\\set</code> と式・乱数分布・<code>\\gset</code>・条件分岐・パイプラインといった"
    "カスタムスクリプトの全機能を、実際に動く例と実測した出力で一つずつ確認していく。"
    "最後まで手を動かすと、読み書きを混ぜた現実的なワークロードを組み、"
    "スクリプト別・ステートメント別に結果を読み解けるようになる。"
    "所要時間の目安は 2〜3 時間。"
    "本文中の出力はすべて PostgreSQL 18.4 上で実際に実行して採取したもの（tps や latency は環境で変わる）。"
)
FOOTER = (
    "pgbench カスタムスクリプト実践ガイド — PostgreSQL 18.4 で実行して確認 / "
    "仕様は "
    '<a href="https://www.postgresql.org/docs/18/pgbench.html">公式ドキュメント pgbench</a>'
    " を参照"
)


def sidebar(current_ch: int | None) -> str:
    """全ページ共通のサイドバー TOC。現在章/節に class="current" を付ける。"""
    out = ["<ol>"]
    for ch in CHAPTERS:
        cls = ' class="current"' if ch["num"] == current_ch else ""
        out.append(f"  <li{cls}>")
        out.append(
            f'    <a class="chap-title" href="ch{ch["num"]:02d}.html">'
            f'第{ch["num"]}章 {ch["title"]}</a>'
        )
        out.append('    <ol class="sect">')
        for sid, stitle in ch["sections"]:
            out.append(f'      <li><a href="ch{ch["num"]:02d}.html#{sid}">{stitle}</a></li>')
        out.append("    </ol>")
        out.append("  </li>")
    out.append("</ol>")
    return "\n".join(out)


def pager(idx: int) -> str:
    """前後ナビ。順序は prev -> up -> next。欠けた側は spacer で埋める。"""
    spacer = '<span class="pager-spacer" aria-hidden="true"></span>'
    parts = []
    if idx > 0:
        p = CHAPTERS[idx - 1]
        parts.append(
            f'<a class="prev" href="ch{p["num"]:02d}.html">'
            f'<span class="dir">← 前の章</span>'
            f'<span class="ttl">第{p["num"]}章 {p["title"]}</span></a>'
        )
    else:
        parts.append(spacer)
    parts.append(
        '<a class="up" href="index.html">'
        '<span class="dir">↑ 目次</span>'
        '<span class="ttl">トップページ</span></a>'
    )
    if idx < len(CHAPTERS) - 1:
        n = CHAPTERS[idx + 1]
        parts.append(
            f'<a class="next" href="ch{n["num"]:02d}.html">'
            f'<span class="dir">次の章 →</span>'
            f'<span class="ttl">第{n["num"]}章 {n["title"]}</span></a>'
        )
    else:
        parts.append(spacer)
    return "\n        ".join(parts)


def load_template(name: str) -> str:
    """テンプレートを読み、先頭の説明コメントを落とす。

    テンプレート冒頭の <!-- ... --> には {{SITE_TITLE}} などの
    プレースホルダが説明として書かれている。そのまま置換すると
    本文がコメント内にも複製されてしまうため、先に取り除く。
    """
    text = (ASSETS / name).read_text(encoding="utf-8")
    start = text.find("<!--")
    end = text.find("-->", start)
    if start != -1 and end != -1:
        text = text[:start] + text[end + 3 :]
    return text.replace("\n\n\n", "\n")


def main() -> None:
    page_tpl = load_template("page-template.html")
    index_tpl = load_template("index-template.html")

    for idx, ch in enumerate(CHAPTERS):
        html = (
            page_tpl.replace("{{SITE_TITLE}}", SITE_TITLE)
            .replace("{{VERSION_INFO}}", VERSION_INFO)
            .replace("{{PAGE_TITLE}}", f'第{ch["num"]}章 {ch["title"]}')
            .replace("{{SIDEBAR_TOC}}", sidebar(ch["num"]))
            .replace("{{CHAPTER_NUMBER}}", f'第{ch["num"]}章')
            .replace("{{CHAPTER_TITLE}}", ch["title"])
            .replace("{{CHAPTER_BODY}}", ch["body"])
            .replace("{{PAGER}}", pager(idx))
            .replace("{{FOOTER}}", FOOTER)
        )
        (HERE / f'ch{ch["num"]:02d}.html').write_text(html, encoding="utf-8")

    cards = "\n        ".join(
        f'<a class="toc-card" href="ch{ch["num"]:02d}.html">'
        f'<span class="num">第{ch["num"]}章</span>'
        f'<span class="title">{ch["title"]}</span>'
        f'<span class="desc">{ch["desc"]}</span></a>'
        for ch in CHAPTERS
    )
    index = (
        index_tpl.replace("{{SITE_TITLE}}", SITE_TITLE)
        .replace("{{VERSION_INFO}}", VERSION_INFO)
        .replace("{{AUDIENCE}}", AUDIENCE)
        .replace("{{LEAD}}", LEAD)
        .replace("{{SIDEBAR_TOC}}", sidebar(None))
        .replace("{{TOC_CARDS}}", cards)
        .replace("{{FOOTER}}", FOOTER)
    )
    (HERE / "index.html").write_text(index, encoding="utf-8")
    print(f"generated index.html and {len(CHAPTERS)} chapter pages in {HERE}")


if __name__ == "__main__":
    main()
