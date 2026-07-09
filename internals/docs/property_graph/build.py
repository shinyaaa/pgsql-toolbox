#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
internals/docs/property_graph/ の全 HTML ページを生成するビルドスクリプト。

  python3 build.py

サイドバー TOC・ページ雛形・各章本文を一元管理し、chNN.html と index.html を出力する。
bodies.py に各章の本文 HTML を分離している。
"""
import os
from bodies import CHAPTERS, LEAD

SITE_TITLE = "PostgreSQL プロパティグラフ（SQL/PGQ）の内部構造"
VERSION_INFO = "PostgreSQL 19beta1 · 031904048aa · 2026-07-09 12:21"
FOOTER = ("The Internals of PostgreSQL 風・内部構造解説 / "
          "対象: PostgreSQL 19beta1 (SQL/PGQ パッチ) · shinyaaa/postgres")

HERE = os.path.dirname(os.path.abspath(__file__))

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{page_title} | {site_title} — {version}</title>
  <link rel="stylesheet" href="css/style.css">
  <script type="module">
    import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
    mermaid.initialize({{
      startOnLoad: true,
      theme: 'base',
      themeVariables: {{
        background:        '#ffffff',
        primaryColor:      '#dbeafe',
        primaryTextColor:  '#1a202c',
        primaryBorderColor:'#2b6cb0',
        lineColor:         '#4a5568',
        secondaryColor:    '#e2e8f0',
        tertiaryColor:     '#f7fafc',
        edgeLabelBackground: '#ffffff',
        clusterBkg:        '#f0f7ff',
        clusterBorder:     '#93c5fd',
      }},
      flowchart: {{ htmlLabels: true }},
    }});
  </script>
</head>
<body>
  <header class="site-header">
    <a href="index.html" class="site-title">{site_title}</a>
    <span class="version-badge">{version}</span>
  </header>
  <div class="layout">
    <nav class="sidebar">
      {sidebar}
    </nav>
    <main class="content">
      <article>
        <h1>{chapter_number}　{chapter_title}</h1>
        {chapter_body}
      </article>
      <nav class="pager">
        {pager}
      </nav>
    </main>
  </div>
  <footer class="site-footer">{footer}</footer>
</body>
</html>
"""

INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{site_title} — {version}</title>
  <link rel="stylesheet" href="css/style.css">
</head>
<body>
  <header class="site-header">
    <a href="index.html" class="site-title">{site_title}</a>
    <span class="version-badge">{version}</span>
  </header>
  <div class="layout">
    <nav class="sidebar">
      {sidebar}
    </nav>
    <main class="content">
      <div class="toc-hero">
        <h1>{site_title}</h1>
        <p class="version-hero">{version}</p>
        <p class="lead">{lead}</p>
      </div>
      <div class="toc-grid">
        {cards}
      </div>
    </main>
  </div>
  <footer class="site-footer">{footer}</footer>
</body>
</html>
"""


def chfile(n):
    return "ch%02d.html" % n


def build_sidebar(current_ch):
    items = []
    for ch in CHAPTERS:
        n = ch["num"]
        cls = ' class="current"' if n == current_ch else ""
        sects = []
        for sid, stitle in ch["sections"]:
            sects.append(
                '        <li><a href="%s#%s">%s</a></li>'
                % (chfile(n), sid, stitle)
            )
        items.append(
            '  <li%s>\n'
            '    <a class="chap-title" href="%s">第%d章 %s</a>\n'
            '    <ol class="sect">\n%s\n    </ol>\n'
            '  </li>'
            % (cls, chfile(n), n, ch["title"], "\n".join(sects))
        )
    return '<ol>\n' + "\n".join(items) + '\n</ol>'


def build_pager(idx):
    n = CHAPTERS[idx]["num"]
    parts = []
    if idx > 0:
        prev = CHAPTERS[idx - 1]
        parts.append(
            '<a class="prev" href="%s">\n'
            '  <span class="dir">← 前の章</span>\n'
            '  <span class="ttl">第%d章 %s</span>\n</a>'
            % (chfile(prev["num"]), prev["num"], prev["title"])
        )
    else:
        parts.append('<span class="pager-spacer" aria-hidden="true"></span>')

    parts.append(
        '<a class="up" href="index.html">\n'
        '  <span class="dir">↑ 目次</span>\n'
        '  <span class="ttl">トップページ</span>\n</a>'
    )

    if idx < len(CHAPTERS) - 1:
        nxt = CHAPTERS[idx + 1]
        parts.append(
            '<a class="next" href="%s">\n'
            '  <span class="dir">次の章 →</span>\n'
            '  <span class="ttl">第%d章 %s</span>\n</a>'
            % (chfile(nxt["num"]), nxt["num"], nxt["title"])
        )
    else:
        parts.append('<span class="pager-spacer" aria-hidden="true"></span>')

    return "\n        ".join(parts)


def main():
    for idx, ch in enumerate(CHAPTERS):
        html = PAGE_TEMPLATE.format(
            page_title="第%d章 %s" % (ch["num"], ch["title"]),
            site_title=SITE_TITLE,
            version=VERSION_INFO,
            sidebar=build_sidebar(ch["num"]),
            chapter_number="第%d章" % ch["num"],
            chapter_title=ch["title"],
            chapter_body=ch["body"].strip(),
            pager=build_pager(idx),
            footer=FOOTER,
        )
        path = os.path.join(HERE, chfile(ch["num"]))
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        print("wrote", path)

    cards = []
    for ch in CHAPTERS:
        cards.append(
            '<a class="toc-card" href="%s">\n'
            '  <span class="num">第%d章</span>\n'
            '  <span class="title">%s</span>\n'
            '  <span class="desc">%s</span>\n</a>'
            % (chfile(ch["num"]), ch["num"], ch["title"], ch["desc"])
        )
    index_html = INDEX_TEMPLATE.format(
        site_title=SITE_TITLE,
        version=VERSION_INFO,
        sidebar=build_sidebar(0),
        lead=LEAD.strip(),
        cards="\n        ".join(cards),
        footer=FOOTER,
    )
    path = os.path.join(HERE, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(index_html)
    print("wrote", path)


if __name__ == "__main__":
    main()
