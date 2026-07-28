#!/usr/bin/env python3
"""Build the RLS user guide (rls-guide) static site from the db-user-docs templates.

Run:  python3 build.py
Outputs index.html + ch01..ch07.html next to this file. Re-run to regenerate.
All command outputs embedded below were captured from a live PostgreSQL run.
Bodies are assembled by concatenation (not f-strings) so that command outputs can
contain literal newlines and braces (e.g. the {public} role array) verbatim.
"""
import re
from pathlib import Path

HERE = Path(__file__).parent
SKILL = HERE.parents[2] / ".claude" / "skills" / "db-user-docs" / "assets"

SITE_TITLE = "行レベルセキュリティ（RLS）実践ガイド"
VERSION_INFO = "PostgreSQL 18"
AUDIENCE = "対象: SQL は書けるが、行レベルセキュリティ（RLS）はこれから使う人"
FOOTER = ("行レベルセキュリティ（RLS）実践ガイド — 実行例はローカルの PostgreSQL ビルドで検証"
          "（RLS は 9.5 以降で共通の挙動）")

CHAPTERS = [
    ("RLS でできること", "行単位でアクセスを絞る仕組みと、GRANT との違い・使いどころを掴む。", [
        ("1-1", "行レベルセキュリティとは"),
        ("1-2", "GRANT（権限）との違いと関係"),
        ("1-3", "典型的なユースケース"),
    ]),
    ("準備", "検証用のデータベース・ロール・サンプルテーブルをコピペで用意する。", [
        ("2-1", "検証用データベースとロールを作る"),
        ("2-2", "サンプルテーブルと権限"),
        ("2-3", "SET ROLE で別ユーザーを演じる"),
    ]),
    ("まず動かす（最短ルート）", "RLS を有効化して 1 つポリシーを作り、見え方が変わることを確認する。", [
        ("3-1", "RLS を有効化して最初のポリシーを作る"),
        ("3-2", "ユーザーごとに見える行が変わる"),
        ("3-3", "設定を確認する"),
    ]),
    ("ポリシーを正しく書く", "USING と WITH CHECK、コマンド別・ロール別、PERMISSIVE と RESTRICTIVE を使い分ける。", [
        ("4-1", "USING と WITH CHECK"),
        ("4-2", "コマンド別・ロール別のポリシー"),
        ("4-3", "PERMISSIVE と RESTRICTIVE"),
    ]),
    ("実践：マルチテナントを作る", "接続プール前提で、セッション変数によるテナント分離を組む。", [
        ("5-1", "セッション変数でテナントを切り替える"),
        ("5-2", "接続プール前提の設計"),
        ("5-3", "実行計画で確認する"),
    ]),
    ("つまずきポイントと対処", "所有者バイパス・デフォルト拒否・GRANT との二層など、はまりどころを潰す。", [
        ("6-1", "所有者・スーパーユーザはバイパスする"),
        ("6-2", "デフォルト拒否とポリシーの抜け"),
        ("6-3", "GRANT との二層構造"),
        ("6-4", "パフォーマンスの注意"),
    ]),
    ("まとめとチートシート", "コマンド早見表と、導入前の設計チェックリスト。", [
        ("7-1", "コマンド早見表"),
        ("7-2", "設計チェックリスト"),
    ]),
]


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def io(label, code, out=False):
    """入力／出力の .example ブロック（code は実行時の生テキスト、改行そのまま）。"""
    cls = "example-label out" if out else "example-label"
    return ('<div class="example"><span class="' + cls + '">' + label + '</span>'
            '<pre><code>' + esc(code) + '</code></pre></div>')


def J(*parts):
    return "".join(parts)


def sidebar(cur):
    items = []
    for i, (title, _desc, secs) in enumerate(CHAPTERS):
        n = i + 1
        li = ' class="current"' if i == cur else ""
        sect = "\n".join(
            '      <li><a href="ch%02d.html#sec-%s">%s %s</a></li>'
            % (n, sid, sid.replace("-", "."), stitle)
            for sid, stitle in secs
        )
        items.append(
            '  <li%s>\n'
            '    <a class="chap-title" href="ch%02d.html">第%d章 %s</a>\n'
            '    <ol class="sect">\n%s\n    </ol>\n'
            '  </li>' % (li, n, n, title, sect)
        )
    return "<ol>\n" + "\n".join(items) + "\n</ol>"


def pager(cur):
    parts = []
    if cur > 0:
        pt = CHAPTERS[cur - 1][0]
        parts.append('<a class="prev" href="ch%02d.html">'
                     '<span class="dir">← 前の章</span>'
                     '<span class="ttl">第%d章 %s</span></a>' % (cur, cur, pt))
    else:
        parts.append('<span class="pager-spacer" aria-hidden="true"></span>')
    parts.append('<a class="up" href="index.html">'
                 '<span class="dir">↑ 目次</span>'
                 '<span class="ttl">トップページ</span></a>')
    if cur < len(CHAPTERS) - 1:
        nt = CHAPTERS[cur + 1][0]
        parts.append('<a class="next" href="ch%02d.html">'
                     '<span class="dir">次の章 →</span>'
                     '<span class="ttl">第%d章 %s</span></a>' % (cur + 2, cur + 2, nt))
    else:
        parts.append('<span class="pager-spacer" aria-hidden="true"></span>')
    return "\n        ".join(parts)


# --- 章本文 -----------------------------------------------------------------
BODIES = {}

BODIES[1] = J("""
<div class="goal">
  <strong>🎯 この章のゴール</strong>
  <ul>
    <li>行レベルセキュリティ（RLS）が「何を」守るのかを説明できる</li>
    <li>GRANT による権限制御との違いと、両者の関係を説明できる</li>
    <li>自分のケースで RLS が向くかどうかを判断できる</li>
  </ul>
</div>

<h2 id="sec-1-1">1.1　行レベルセキュリティとは</h2>
<p>
  行レベルセキュリティ（Row Level Security, RLS）は、<strong>同じテーブルの中で、ユーザーごとに
  「見える行・操作できる行」を自動的に絞り込む</strong>仕組みである。テーブルに
  <strong>ポリシー</strong>（行を許可する条件式）を付けておくと、以降その表への
  <code>SELECT</code> / <code>INSERT</code> / <code>UPDATE</code> / <code>DELETE</code> に
  条件が自動で挿入され、条件に合う行だけが対象になる。
</p>
<p>
  ポイントは<strong>アプリ側で <code>WHERE owner = ...</code> を毎回書かなくてよい</strong>こと。
  条件の付け忘れがセキュリティ事故に直結する世界で、絞り込みをデータベース側に一元化できる。
</p>
<figure>
  <pre class="mermaid">
flowchart LR
    U["ユーザーのクエリ"]
    G{"テーブル権限 GRANT はあるか"}
    R{"行ポリシーを満たすか"}
    OUT["返る行"]
    DENY["権限エラー"]
    U --> G
    G -->|なし| DENY
    G -->|あり| R
    R -->|満たす行だけ| OUT
  </pre>
  <figcaption>図 1.1: クエリは「テーブル権限（GRANT）」と「行ポリシー（RLS）」の 2 段の関門を通る</figcaption>
</figure>
<p>図 1.1 のように、RLS は GRANT の<strong>後段</strong>で効く。まず GRANT でそのテーブルを触れるかが
  決まり、触れる場合に RLS が「どの行か」を絞る。</p>

<h2 id="sec-1-2">1.2　GRANT（権限）との違いと関係</h2>
<p>両者はレイヤーが違う。RLS は GRANT を置き換えるものではなく、<strong>上に重ねる</strong>ものである。</p>
<table>
  <thead><tr><th></th><th>GRANT（権限）</th><th>RLS（行レベル）</th></tr></thead>
  <tbody>
    <tr><td>絞る単位</td><td>テーブル・列（縦）</td><td>行（横）</td></tr>
    <tr><td>問い</td><td>この表を触ってよいか</td><td>このユーザーにどの行を見せるか</td></tr>
    <tr><td>書き方</td><td><code>GRANT SELECT ON t TO r;</code></td><td><code>CREATE POLICY … ON t USING (…);</code></td></tr>
    <tr><td>既定</td><td>付与しなければ触れない</td><td>有効化してポリシーが無ければ全行拒否</td></tr>
  </tbody>
</table>
<div class="note">
  <strong>関係の要点</strong>
  RLS で行を見せたくても、そもそも <code>GRANT SELECT</code> が無ければ表自体を読めない。
  逆に <code>GRANT</code> があっても、RLS が有効なら条件に合う行しか返らない。両方を通った行だけが結果になる。
</div>

<h2 id="sec-1-3">1.3　典型的なユースケース</h2>
<ul>
  <li><strong>所有者ベース</strong>：各行に持ち主がいて、本人（と管理者）だけが見られる。例：文書・タスク・通知。</li>
  <li><strong>マルチテナント</strong>：1 つのテーブルに複数テナントのデータが同居し、テナントをまたいで見えてはいけない。</li>
  <li><strong>部門・地域スコープ</strong>：自分の部門／担当地域の行だけを見せる。</li>
</ul>
<p>本ガイドでは、まず<strong>所有者ベース</strong>で最短の動作を体験し（第2〜4章）、続いて実務で多い
  <strong>マルチテナント</strong>を接続プール前提で組む（第5章）。最後にはまりどころを潰す（第6章）。</p>

<div class="checkpoint">
  <strong>✅ チェックポイント</strong>
  <ul>
    <li>RLS が絞るのは「行」で、GRANT が絞るのは「テーブル・列」だと言える</li>
    <li>GRANT を通った後に RLS が効く、という順序を説明できる</li>
    <li>自分が守りたい対象が「所有者ベース」か「マルチテナント」か見当がつく</li>
  </ul>
</div>
""")

BODIES[2] = J("""
<div class="goal">
  <strong>🎯 この章のゴール</strong>
  <ul>
    <li>以降の章をそのまま再現できる、検証用のデータベースとロールを用意する</li>
    <li><code>SET ROLE</code> で「別のユーザーになりきって」動作を確かめられるようになる</li>
  </ul>
</div>
<div class="prereq">
  <strong>📋 前提</strong>
  <ul>
    <li>PostgreSQL に<strong>スーパーユーザ</strong>（または <code>CREATEDB</code> と <code>CREATEROLE</code> 権限を持つロール）で接続できる</li>
    <li><code>psql</code> が使える（他のクライアントでも SQL は同じ）</li>
  </ul>
</div>
<p>この章で作る環境を第6章まで使い回す。まっさらな状態から始めたいので、専用のデータベースを 1 つ用意する。</p>

<h2 id="sec-2-1">2.1　検証用データベースとロールを作る</h2>
<p>専用データベース <code>rlsguide</code> と、登場人物となる 3 つのロールを作る。<code>LOGIN</code> を付けるのは、
  あとで「そのユーザーとして」動作を確かめるためである。</p>
<div class="handson">
  <div class="handson-head">⌨️ ハンズオン: データベースとロールを作る</div>
  <div class="handson-body">
    <ol class="steps">
      <li>
        <p>スーパーユーザで接続し、専用データベースを作る。</p>
""", io("入力（psql）", "CREATE DATABASE rlsguide;"),
   io("出力", "CREATE DATABASE", out=True), """
      </li>
      <li>
        <p>作った <code>rlsguide</code> に接続し直し、3 つのロールを作る。</p>
""", io("入力（psql: rlsguide）",
        "CREATE ROLE rlsguide_alice   LOGIN;\n"
        "CREATE ROLE rlsguide_bob     LOGIN;\n"
        "CREATE ROLE rlsguide_manager LOGIN;"),
   io("出力", "CREATE ROLE\nCREATE ROLE\nCREATE ROLE", out=True), """
      </li>
    </ol>
  </div>
</div>
<div class="tip">
  <strong>💡 ヒント</strong>
  <code>psql</code> なら <code>\\c rlsguide</code> で接続先データベースを切り替えられる。以降のコマンドは
  すべて <code>rlsguide</code> データベース上で実行する。
</div>

<h2 id="sec-2-2">2.2　サンプルテーブルと権限</h2>
<p>所有者ベースの題材として、文書テーブル <code>documents</code> を作る。<code>owner</code> 列には
  「その行の持ち主のロール名」を入れる。<code>DEFAULT current_user</code> にしておくと、
  誰かが行を追加したとき自動でその人が持ち主になる。</p>
<div class="handson">
  <div class="handson-head">⌨️ ハンズオン: テーブル・権限・初期データ</div>
  <div class="handson-body">
    <ol class="steps">
      <li>
        <p>テーブルを作る。</p>
""", io("入力",
        "CREATE TABLE documents (\n"
        "    id     int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,\n"
        "    owner  text NOT NULL DEFAULT current_user,\n"
        "    title  text NOT NULL\n"
        ");"),
   io("出力", "CREATE TABLE", out=True), """
      </li>
      <li>
        <p>3 つのロールにテーブル操作権限を与える（RLS は権限の<strong>上</strong>に乗るので、まず GRANT が要る）。</p>
""", io("入力",
        "GRANT SELECT, INSERT, UPDATE, DELETE ON documents\n"
        "    TO rlsguide_alice, rlsguide_bob, rlsguide_manager;\n"
        "GRANT USAGE, SELECT ON SEQUENCE documents_id_seq\n"
        "    TO rlsguide_alice, rlsguide_bob, rlsguide_manager;"),
   io("出力", "GRANT\nGRANT", out=True), """
      </li>
      <li>
        <p>初期データを 3 行入れる（この時点では RLS 未設定なので誰でも全行見える）。</p>
""", io("入力",
        "INSERT INTO documents (owner, title) VALUES\n"
        "  ('rlsguide_alice', 'Alice の企画書'),\n"
        "  ('rlsguide_alice', 'Alice の日報'),\n"
        "  ('rlsguide_bob',   'Bob のメモ');"),
   io("出力", "INSERT 0 3", out=True), """
      </li>
    </ol>
  </div>
</div>

<h2 id="sec-2-3">2.3　SET ROLE で別ユーザーを演じる</h2>
<p>RLS の効果は「誰として実行したか」で変わる。ログインし直さなくても、<code>SET ROLE</code> で
  現在のロールを切り替えれば、そのユーザーとしての見え方を確認できる。元に戻すのは <code>RESET ROLE</code>。</p>
""", io("入力", "SET ROLE rlsguide_alice;\nSELECT current_user;"),
   io("出力",
      "  current_user\n"
      "----------------\n"
      " rlsguide_alice\n"
      "(1 row)", out=True), """
<div class="pitfall">
  <strong>⚠️ よくある落とし穴</strong>
  <code>SET ROLE</code> は<strong>そのセッションの間だけ</strong>有効で、接続を切ると元に戻る。また
  スーパーユーザや<strong>テーブルの所有者</strong>に切り替えて確認すると、RLS を素通りして全行見えてしまう
  （理由は第6章）。動作確認は必ず <code>rlsguide_alice</code> のような<strong>一般ロール</strong>で行う。
</div>

<div class="checkpoint">
  <strong>✅ チェックポイント</strong>
  <ul>
    <li><code>rlsguide</code> データベースに <code>documents</code> テーブルがあり、3 行入っている</li>
    <li><code>SET ROLE rlsguide_alice;</code> のあと <code>SELECT current_user;</code> が <code>rlsguide_alice</code> を返す</li>
    <li>ここまで RLS はまだ有効化していない（＝いま alice は 3 行すべて見える）</li>
  </ul>
</div>
""")

BODIES[3] = J("""
<div class="goal">
  <strong>🎯 この章のゴール</strong>
  <ul>
    <li>テーブルの RLS を有効化し、最初のポリシーを 1 つ作れる</li>
    <li>alice と bob で「見える行」が変わることを、自分の目で確認できる</li>
    <li>いま何が設定されているかを <code>\\d</code> と <code>pg_policies</code> で確認できる</li>
  </ul>
</div>
<div class="prereq">
  <strong>📋 前提</strong>
  第2章の <code>documents</code> テーブル（3 行）と 3 ロールをそのまま使う。
</div>

<h2 id="sec-3-1">3.1　RLS を有効化して最初のポリシーを作る</h2>
<p>RLS は 2 段階で使う。<strong>(1) テーブルで有効化</strong>し、<strong>(2) 許可する行の条件（ポリシー）</strong>を作る。
  ここでは「<code>owner</code> 列が自分のロール名と一致する行だけ許可」という条件にする。</p>
<div class="handson">
  <div class="handson-head">⌨️ ハンズオン: 有効化＋最初のポリシー</div>
  <div class="handson-body">
    <ol class="steps">
      <li>
        <p>テーブルで RLS を有効化する。</p>
""", io("入力", "ALTER TABLE documents ENABLE ROW LEVEL SECURITY;"),
   io("出力", "ALTER TABLE", out=True), """
      </li>
      <li>
        <p>「持ち主本人だけ」を許可するポリシーを作る。<code>current_user</code> は実行中のロール名を返す。</p>
""", io("入力", "CREATE POLICY owner_can_see ON documents\n    USING (owner = current_user);"),
   io("出力", "CREATE POLICY", out=True), """
      </li>
    </ol>
  </div>
</div>
<p>これだけで、以降 <code>documents</code> への読み書きに <code>owner = current_user</code> が自動で挿し込まれる。</p>

<h2 id="sec-3-2">3.2　ユーザーごとに見える行が変わる</h2>
<p>同じ <code>SELECT * FROM documents</code> が、実行するロールによって違う結果を返す。</p>
""", io("入力（alice）", "SET ROLE rlsguide_alice;\nSELECT * FROM documents ORDER BY id;"),
   io("出力",
      " id |     owner      |     title\n"
      "----+----------------+----------------\n"
      "  1 | rlsguide_alice | Alice の企画書\n"
      "  2 | rlsguide_alice | Alice の日報\n"
      "(2 rows)", out=True),
   io("入力（bob）", "SET ROLE rlsguide_bob;\nSELECT * FROM documents ORDER BY id;"),
   io("出力",
      " id |    owner     |   title\n"
      "----+--------------+------------\n"
      "  3 | rlsguide_bob | Bob のメモ\n"
      "(1 row)", out=True), """
<p>alice は自分の 2 行だけ、bob は自分の 1 行だけになった。アプリで <code>WHERE</code> を書かなくても、
  データベースが自動で絞っている。</p>
<div class="pitfall">
  <strong>⚠️ よくある落とし穴</strong>
  同じ問い合わせを<strong>スーパーユーザ</strong>や<strong>テーブル所有者</strong>で実行すると、RLS を
  素通りして 3 行すべて返る。「絞られない！」の多くはこれが原因。動作確認は一般ロールで行う（詳細は第6章）。
</div>
""", io("入力（所有者/スーパーユーザ）", "RESET ROLE;   -- 例: スーパーユーザ shinya に戻る\nSELECT * FROM documents ORDER BY id;"),
   io("出力",
      " id |     owner      |     title\n"
      "----+----------------+----------------\n"
      "  1 | rlsguide_alice | Alice の企画書\n"
      "  2 | rlsguide_alice | Alice の日報\n"
      "  3 | rlsguide_bob   | Bob のメモ\n"
      "(3 rows)", out=True), """

<h2 id="sec-3-3">3.3　設定を確認する</h2>
<p>いまテーブルに何が設定されているかは、次の 2 つで確認できる。</p>
""", io("入力", "\\d documents"),
   io("出力",
      "                        Table \"public.documents\"\n"
      " Column |  Type   | Collation | Nullable |           Default\n"
      "--------+---------+-----------+----------+------------------------------\n"
      " id     | integer |           | not null | generated always as identity\n"
      " owner  | text    |           | not null | CURRENT_USER\n"
      " title  | text    |           | not null |\n"
      "Indexes:\n"
      "    \"documents_pkey\" PRIMARY KEY, btree (id)\n"
      "Policies:\n"
      "    POLICY \"owner_can_see\"\n"
      "      USING ((owner = CURRENT_USER))", out=True), """
<p>末尾の <code>Policies:</code> に付いているポリシーが並ぶ。より詳しく見るならビュー <code>pg_policies</code>。</p>
""", io("入力", "SELECT policyname, permissive, roles, cmd, qual, with_check\n  FROM pg_policies WHERE tablename = 'documents';"),
   io("出力",
      "  policyname   | permissive |  roles   | cmd |          qual          | with_check\n"
      "---------------+------------+----------+-----+------------------------+------------\n"
      " owner_can_see | PERMISSIVE | {public} | ALL | (owner = CURRENT_USER) |\n"
      "(1 row)", out=True), """
<p>読み方：<code>cmd = ALL</code>（全操作対象）、<code>roles = {public}</code>（全ロール対象）、
  <code>qual</code> が読み取り条件（USING）。<code>with_check</code> は空で、これは「書き込み条件を別に
  指定していない」ことを表す（次章）。</p>

<div class="checkpoint">
  <strong>✅ チェックポイント</strong>
  <ul>
    <li>alice で <code>SELECT</code> すると 2 行、bob だと 1 行になる</li>
    <li><code>\\d documents</code> の <code>Policies:</code> に <code>owner_can_see</code> が表示される</li>
    <li>スーパーユーザ／所有者で実行すると全行見えてしまう理由を、第6章で確認する予定だと分かっている</li>
  </ul>
</div>
""")

BODIES[4] = J("""
<div class="goal">
  <strong>🎯 この章のゴール</strong>
  <ul>
    <li>読み取り条件（<code>USING</code>）と書き込み条件（<code>WITH CHECK</code>）を使い分けられる</li>
    <li>コマンド別（<code>FOR</code>）・ロール別（<code>TO</code>）にポリシーを絞れる</li>
    <li>PERMISSIVE（OR 結合）と RESTRICTIVE（AND 結合）の違いを説明できる</li>
  </ul>
</div>
<div class="prereq">
  <strong>📋 前提</strong>
  第3章の <code>documents</code>（RLS 有効・<code>owner_can_see</code> ポリシーあり）を引き継ぐ。
</div>

<h2 id="sec-4-1">4.1　USING と WITH CHECK</h2>
<p>ポリシーの条件式には 2 種類ある。役割がはっきり違う。</p>
<ul>
  <li><strong><code>USING</code></strong>：<strong>すでにある行</strong>に対する条件。<code>SELECT</code> で見えるか、
    <code>UPDATE</code>/<code>DELETE</code> の対象にできるかを決める。</li>
  <li><strong><code>WITH CHECK</code></strong>：<strong>これから書く行</strong>に対する条件。<code>INSERT</code> と、
    <code>UPDATE</code> 後の新しい値が許されるかを決める。</li>
</ul>
<figure>
  <pre class="mermaid">
flowchart TB
    Q["クエリ"] --> K{"操作の種類"}
    K -->|既存行を読む・選ぶ| U["USING 式で判定"]
    K -->|新しい行を書く| W["WITH CHECK 式で判定"]
    U --> RES["見える・操作できる行"]
    W --> OK["書き込みの可否"]
  </pre>
  <figcaption>図 4.1: USING は「既存行」、WITH CHECK は「新しい行」に効く</figcaption>
</figure>
<p>図 4.1 のとおり、<code>owner_can_see</code> は <code>USING</code> だけを指定した。<code>WITH CHECK</code> を
  省くと、<strong><code>USING</code> の式が書き込みにも流用される</strong>。つまり alice は「自分名義の行」しか
  書けない。試してみる。</p>
""", io("入力（alice: 自分名義で追加）", "SET ROLE rlsguide_alice;\nINSERT INTO documents (title) VALUES ('Alice の見積');"),
   io("出力", "INSERT 0 1", out=True),
   io("入力（alice: bob 名義で追加を試みる）", "INSERT INTO documents (owner, title) VALUES ('rlsguide_bob', 'なりすまし');"),
   io("出力", 'ERROR:  new row violates row-level security policy for table "documents"', out=True), """
<p>他人名義の <code>INSERT</code> は <code>WITH CHECK</code>（ここでは <code>USING</code> の流用）に弾かれる。
  <code>UPDATE</code> でも同じで、見えない行は対象にならず（0 行）、自分の行でも<strong>他人名義に書き換える</strong>
  ことはできない。</p>
""", io("入力（alice: 見えない bob の行を更新）", "UPDATE documents SET title = '書き換え' WHERE title = 'Bob のメモ';"),
   io("出力", "UPDATE 0", out=True),
   io("入力（alice: 自分の行を bob 名義へ）", "UPDATE documents SET owner = 'rlsguide_bob' WHERE title = 'Alice の日報';"),
   io("出力", 'ERROR:  new row violates row-level security policy for table "documents"', out=True), """
<div class="tip">
  <strong>💡 ヒント</strong>
  読み取りと書き込みで条件を変えたいときは両方を明記する：
  <code>CREATE POLICY p ON t USING (読める条件) WITH CHECK (書ける条件);</code>。
  <code>INSERT</code> 専用ポリシーには <code>USING</code> が無く <code>WITH CHECK</code> だけを書く。
</div>

<h2 id="sec-4-2">4.2　コマンド別・ロール別のポリシー</h2>
<p>ポリシーは <code>FOR</code> で対象コマンドを、<code>TO</code> で対象ロールを絞れる。例として、
  <strong>manager は全行を閲覧できるが変更はできない</strong>ようにする。<code>FOR SELECT</code> と
  <code>TO rlsguide_manager</code> で「manager の読み取りだけ」を許可する。</p>
""", io("入力", "CREATE POLICY manager_reads_all ON documents\n    FOR SELECT TO rlsguide_manager\n    USING (true);"),
   io("出力", "CREATE POLICY", out=True),
   io("入力（manager で全件閲覧）", "SET ROLE rlsguide_manager;\nSELECT id, owner, title FROM documents ORDER BY id;"),
   io("出力",
      " id |     owner      |     title\n"
      "----+----------------+----------------\n"
      "  1 | rlsguide_alice | Alice の企画書\n"
      "  2 | rlsguide_alice | Alice の日報\n"
      "  3 | rlsguide_bob   | Bob のメモ\n"
      "  4 | rlsguide_alice | Alice の見積\n"
      "(4 rows)", out=True),
   io("入力（manager で変更を試みる）", "UPDATE documents SET title = 'x' WHERE id = 1;"),
   io("出力", "UPDATE 0", out=True), """
<p>manager には <code>SELECT</code> 用ポリシーしか無いので、<code>UPDATE</code> は対象行ゼロ（変更用の許可が無い）。
  読み取りと変更を別々に許可できることが分かる。</p>

<h2 id="sec-4-3">4.3　PERMISSIVE と RESTRICTIVE</h2>
<p>複数のポリシーが同じ操作に当たるとき、既定の <strong>PERMISSIVE</strong> は <strong>OR</strong> で足し合わされる
  （どれか 1 つを満たせば許可）。上の manager の例では、<code>owner_can_see</code>（自分の行）と
  <code>manager_reads_all</code>（全行）が OR 結合し、manager は全行見えた。</p>
<p>一方 <strong>RESTRICTIVE</strong> ポリシーは <strong>AND</strong> で必須条件を足す（<code>AS RESTRICTIVE</code>）。
  「タイトルが <code>[secret]</code> で始まる行は誰にも見せない」を全体に重ねてみる。</p>
""", io("入力",
        "INSERT INTO documents (owner, title)\n"
        "    VALUES ('rlsguide_alice', '[secret] Alice の給与');\n"
        "CREATE POLICY hide_secret ON documents AS RESTRICTIVE\n"
        "    USING (title NOT LIKE '[secret]%');"),
   io("出力", "INSERT 0 1\nCREATE POLICY", out=True),
   io("入力（alice）", "SET ROLE rlsguide_alice;\nSELECT id, owner, title FROM documents ORDER BY id;"),
   io("出力",
      " id |     owner      |     title\n"
      "----+----------------+----------------\n"
      "  1 | rlsguide_alice | Alice の企画書\n"
      "  2 | rlsguide_alice | Alice の日報\n"
      "  4 | rlsguide_alice | Alice の見積\n"
      "(3 rows)", out=True), """
<p>alice が持ち主の <code>[secret]</code> 行（id 5）は、本人にも見えなくなった。RESTRICTIVE は
  「PERMISSIVE で許可された結果に、<strong>さらに必ず満たすべき条件</strong>を AND する」と理解するとよい。</p>
<div class="note">
  <strong>まとめ</strong>
  最終的に行が見える条件は <code>(PERMISSIVE のどれか) AND (RESTRICTIVE のすべて)</code>。
  PERMISSIVE が 1 つも無いと、その操作は<strong>全拒否</strong>になる（第6章）。
</div>

<div class="checkpoint">
  <strong>✅ チェックポイント</strong>
  <ul>
    <li>alice は他人名義の <code>INSERT</code>／自分の行の名義変更に失敗する（WITH CHECK）</li>
    <li>manager は全行 <code>SELECT</code> できるが <code>UPDATE</code> は 0 行</li>
    <li>RESTRICTIVE を足すと、PERMISSIVE で許可された行がさらに絞られる</li>
  </ul>
</div>
""")

BODIES[5] = J("""
<div class="goal">
  <strong>🎯 この章のゴール</strong>
  <ul>
    <li>接続プールのように「単一の DB ロールで複数テナントを扱う」構成で RLS を効かせられる</li>
    <li>セッション変数（<code>current_setting</code>）でテナントを切り替えられる</li>
    <li>ポリシーが実行計画に入っていることを <code>EXPLAIN</code> で確認できる</li>
  </ul>
</div>
<div class="prereq">
  <strong>📋 前提</strong>
  同じ <code>rlsguide</code> データベースを使う。ここではテナント分離という別パターンなので、新しいテーブル
  <code>orders</code> を作る。
</div>

<h2 id="sec-5-1">5.1　セッション変数でテナントを切り替える</h2>
<p>実務のアプリは、ユーザーごとに DB ロールを分けず、<strong>アプリ共通の 1 ロール</strong>で接続することが多い
  （接続プールのため）。その場合 <code>current_user</code> では誰か区別できない。代わりに、リクエストごとに
  <strong>セッション変数</strong>へテナント ID を入れ、ポリシーからそれを参照する。</p>
<div class="handson">
  <div class="handson-head">⌨️ ハンズオン: テナント分離テーブル</div>
  <div class="handson-body">
    <ol class="steps">
      <li>
        <p>テナント列を持つ <code>orders</code> を作り、権限を与えて 2 テナント分のデータを入れる。</p>
""", io("入力",
        "CREATE TABLE orders (id int, tenant_id int, item text);\n"
        "GRANT SELECT ON orders TO rlsguide_alice;\n"
        "INSERT INTO orders VALUES\n"
        "  (1,100,'apple'), (2,100,'banana'), (3,200,'cherry');"),
   io("出力", "CREATE TABLE\nGRANT\nINSERT 0 3", out=True), """
      </li>
      <li>
        <p>RLS を有効化し、「セッション変数 <code>app.tenant_id</code> と一致する行だけ」を許可する。</p>
""", io("入力",
        "ALTER TABLE orders ENABLE ROW LEVEL SECURITY;\n"
        "CREATE POLICY tenant_isolation ON orders\n"
        "    USING (tenant_id = current_setting('app.tenant_id')::int);"),
   io("出力", "ALTER TABLE\nCREATE POLICY", out=True), """
      </li>
    </ol>
  </div>
</div>
<p><code>app.tenant_id</code> のような「ドット付きの独自変数」は、拡張設定パラメータとして自由に使える。
  リクエスト処理の冒頭でこの値をセットするのが基本の型になる。</p>
""", io("入力（テナント100 として）", "SET ROLE rlsguide_alice;\nSET app.tenant_id = '100';\nSELECT * FROM orders ORDER BY id;"),
   io("出力",
      " id | tenant_id |  item\n"
      "----+-----------+--------\n"
      "  1 |       100 | apple\n"
      "  2 |       100 | banana\n"
      "(2 rows)", out=True),
   io("入力（テナント200 に切り替え）", "SET app.tenant_id = '200';\nSELECT * FROM orders ORDER BY id;"),
   io("出力",
      " id | tenant_id |  item\n"
      "----+-----------+--------\n"
      "  3 |       200 | cherry\n"
      "(1 row)", out=True), """
<p>同じロール・同じ SQL でも、セッション変数を変えるだけで見える行が切り替わった。</p>

<h2 id="sec-5-2">5.2　接続プール前提の設計</h2>
<p>接続プールでは接続が使い回されるため、前のリクエストの値が残ると<strong>テナント越境</strong>になる。
  型として次を守る。</p>
<ul>
  <li>リクエストの<strong>最初</strong>にテナント ID をセットし、トランザクション内なら <code>SET LOCAL</code> を使う
    （トランザクション終了で自動的に元へ戻り、他リクエストへ漏れない）。</li>
  <li>変数が<strong>未設定</strong>だと <code>current_setting('app.tenant_id')</code> はエラーになる。安全側（何も見せない）に
    倒すなら第2引数付きの <code>current_setting('app.tenant_id', true)</code> で欠損を <code>NULL</code> にし、
    <code>NULL</code> は条件を満たさない＝0 行、という設計にできる。</li>
  <li>アプリ接続ロールに <code>BYPASSRLS</code> やスーパーユーザを<strong>使わない</strong>（第6章）。</li>
</ul>
<div class="pitfall">
  <strong>⚠️ よくある落とし穴</strong>
  <code>SET</code>（<code>LOCAL</code> なし）はセッション全体に残る。接続プールでこれを使うと、次に同じ接続を
  借りたリクエストへ値が漏れる。プール環境では原則 <code>SET LOCAL</code>（トランザクション単位）にする。
</div>

<h2 id="sec-5-3">5.3　実行計画で確認する</h2>
<p>ポリシーは「クエリに条件を足す」実装なので、<code>EXPLAIN</code> を見ると <code>Filter</code> として
  入っているのが分かる。効いているかの確認に使える。</p>
""", io("入力", "SET ROLE rlsguide_alice;\nSET app.tenant_id = '100';\nEXPLAIN (COSTS OFF) SELECT * FROM orders;"),
   io("出力",
      "                                QUERY PLAN\n"
      "---------------------------------------------------------------------------\n"
      " Seq Scan on orders\n"
      "   Filter: (tenant_id = (current_setting('app.tenant_id'::text))::integer)\n"
      "(2 rows)", out=True), """
<p><code>Filter:</code> にポリシーの式がそのまま現れている。RLS が「見えているつもりで見えていない」ときは、
  まずここに条件が入っているかを確認するとよい。</p>

<div class="checkpoint">
  <strong>✅ チェックポイント</strong>
  <ul>
    <li><code>SET app.tenant_id</code> の値を変えると、同じ SQL の結果が切り替わる</li>
    <li>接続プールでは <code>SET LOCAL</code> を使う理由を説明できる</li>
    <li><code>EXPLAIN</code> の <code>Filter</code> にポリシーの式が現れることを確認した</li>
  </ul>
</div>
""")

BODIES[6] = J("""
<div class="goal">
  <strong>🎯 この章のゴール</strong>
  <ul>
    <li>「RLS を設定したのに絞られない／全部拒否される」の原因を切り分けられる</li>
    <li>所有者・スーパーユーザのバイパスと <code>FORCE</code> の関係を説明できる</li>
    <li>GRANT と RLS の二層を意識して設計できる</li>
  </ul>
</div>
<div class="prereq">
  <strong>📋 前提</strong>
  同じ <code>rlsguide</code> データベース。6.1 では所有権を確かめるため、新しいテーブル <code>notes</code> を
  管理者が作り、所有権をアプリ用ロールへ移す。
</div>

<h2 id="sec-6-1">6.1　所有者・スーパーユーザはバイパスする</h2>
<p>もっとも多いはまりどころ。<strong>スーパーユーザ</strong>、<strong><code>BYPASSRLS</code> 属性を持つロール</strong>、
  そして<strong>テーブルの所有者</strong>は、既定で RLS を<strong>素通り</strong>する。第3章で所有者/スーパーユーザが
  全行見えたのはこのため。</p>
<figure>
  <pre class="mermaid">
flowchart TB
    Q["行にアクセス"] --> S{"スーパーユーザ か BYPASSRLS か"}
    S -->|はい| BYPASS["ポリシー無視・全行アクセス"]
    S -->|いいえ| O{"テーブル所有者 か"}
    O -->|はい かつ FORCE なし| BYPASS
    O -->|いいえ または FORCE あり| APPLY["ポリシー適用"]
  </pre>
  <figcaption>図 6.1: 誰が RLS をバイパスするか</figcaption>
</figure>
<p>図 6.1 のとおり、所有者のバイパスは <code>FORCE ROW LEVEL SECURITY</code> で止められる。アプリの
  接続ロールが<strong>その表の所有者</strong>を兼ねるとき（よくある）に効いてくる。実演する。</p>
<div class="handson">
  <div class="handson-head">⌨️ ハンズオン: 所有者バイパスと FORCE</div>
  <div class="handson-body">
    <ol class="steps">
      <li>
        <p>管理者がテーブルを作り、所有権をアプリ用ロール <code>rlsguide_app</code> に移す。RLS も有効化する。</p>
""", io("入力",
        "CREATE ROLE rlsguide_app LOGIN;\n"
        "CREATE TABLE notes (owner text NOT NULL DEFAULT current_user, body text);\n"
        "ALTER TABLE notes OWNER TO rlsguide_app;\n"
        "INSERT INTO notes(owner, body)\n"
        "    VALUES ('rlsguide_alice','a-note'), ('rlsguide_bob','b-note');\n"
        "ALTER TABLE notes ENABLE ROW LEVEL SECURITY;\n"
        "CREATE POLICY p ON notes USING (owner = current_user);"),
   io("出力", "CREATE ROLE\nCREATE TABLE\nALTER TABLE\nINSERT 0 2\nALTER TABLE\nCREATE POLICY", out=True), """
      </li>
      <li>
        <p>所有者 <code>rlsguide_app</code> で読むと、RLS 有効なのに全行見える（＝バイパス）。</p>
""", io("入力", "SET ROLE rlsguide_app;\nSELECT * FROM notes ORDER BY owner;"),
   io("出力",
      "     owner      |  body\n"
      "----------------+--------\n"
      " rlsguide_alice | a-note\n"
      " rlsguide_bob   | b-note\n"
      "(2 rows)", out=True), """
      </li>
      <li>
        <p><code>FORCE</code> を付けると、所有者にもポリシーが効く（<code>owner = rlsguide_app</code> の行は無いので 0 行）。</p>
""", io("入力", "RESET ROLE;\nALTER TABLE notes FORCE ROW LEVEL SECURITY;\nSET ROLE rlsguide_app;\nSELECT * FROM notes ORDER BY owner;"),
   io("出力", " owner | body\n-------+------\n(0 rows)", out=True), """
      </li>
    </ol>
  </div>
</div>
<div class="tip">
  <strong>💡 ヒント</strong>
  「動作確認は一般ロールで」「アプリ接続ロールは非スーパーユーザ・<code>BYPASSRLS</code> なし」「所有者を兼ねるなら
  <code>FORCE</code>」を守ると、バイパス由来の事故はほぼ防げる。
</div>

<h2 id="sec-6-2">6.2　デフォルト拒否とポリシーの抜け</h2>
<p>逆に「全部見えない／書けない」もよくある。RLS を有効化して<strong>ポリシーを 1 つも作らない</strong>と、
  一般ロールにとっては<strong>全行拒否</strong>になる（PERMISSIVE が無い＝許可が 0）。</p>
""", io("入力",
        "CREATE TABLE t_denied (id int, memo text);\n"
        "GRANT SELECT, INSERT ON t_denied TO rlsguide_alice;\n"
        "INSERT INTO t_denied VALUES (1,'x'), (2,'y');\n"
        "ALTER TABLE t_denied ENABLE ROW LEVEL SECURITY;   -- ポリシー無し"),
   io("出力", "CREATE TABLE\nGRANT\nINSERT 0 2\nALTER TABLE", out=True),
   io("入力（alice）", "SET ROLE rlsguide_alice;\nSELECT * FROM t_denied;"),
   io("出力", " id | memo\n----+------\n(0 rows)", out=True), """
<p>同様に <code>INSERT</code> も許可が無いので弾かれる。</p>
""", io("入力（alice）", "INSERT INTO t_denied VALUES (3,'z');"),
   io("出力", 'ERROR:  new row violates row-level security policy for table "t_denied"', out=True), """
<p>操作ごとに PERMISSIVE ポリシーが要る、と覚える。<code>SELECT</code> は見えるのに <code>INSERT</code> だけ弾かれる
  ときは、<code>INSERT</code> 用（<code>WITH CHECK</code>）のポリシー漏れを疑う。</p>

<h2 id="sec-6-3">6.3　GRANT との二層構造</h2>
<p>RLS は GRANT の<strong>後</strong>に効く（第1章 図 1.1）。よって次の切り分けができる。</p>
<table>
  <thead><tr><th>症状</th><th>疑うところ</th></tr></thead>
  <tbody>
    <tr><td><code>permission denied for table …</code></td><td>GRANT 不足（RLS 以前の問題）</td></tr>
    <tr><td>行が 1 つも返らない</td><td>ポリシー無し（デフォルト拒否）／条件が厳しすぎ</td></tr>
    <tr><td>全行返ってしまう</td><td>所有者・スーパーユーザ・<code>BYPASSRLS</code> でのバイパス</td></tr>
    <tr><td><code>new row violates row-level security policy</code></td><td><code>WITH CHECK</code>（または流用された <code>USING</code>）に不適合</td></tr>
  </tbody>
</table>

<h2 id="sec-6-4">6.4　パフォーマンスの注意</h2>
<ul>
  <li>ポリシーの式は<strong>全行に評価される</strong>。<code>USING</code> で参照する列（例 <code>tenant_id</code>、
    <code>owner</code>）には<strong>インデックス</strong>を張り、式がインデックスを使える形（列 = 定数/変数）に保つ。</li>
  <li>ポリシー内で<strong>サブクエリ</strong>（別表を引く等）を書くと行ごとに評価されがち。重い場合は
    <code>current_setting</code> やマッピングの工夫で定数化を検討する。</li>
  <li><code>EXPLAIN</code>（第5章 5.3）で <code>Filter</code> とインデックス利用を確認する。</li>
</ul>

<div class="checkpoint">
  <strong>✅ チェックポイント</strong>
  <ul>
    <li>「全行見える」ときにバイパス（所有者・スーパーユーザ・<code>BYPASSRLS</code>）を疑える</li>
    <li>所有者を兼ねる接続には <code>FORCE ROW LEVEL SECURITY</code> が要ると分かる</li>
    <li>「1 行も出ない」ときにポリシー漏れ（デフォルト拒否）を疑える</li>
    <li>エラーメッセージから GRANT 層と RLS 層を切り分けられる</li>
  </ul>
</div>
""")

BODIES[7] = J("""
<div class="goal">
  <strong>🎯 この章のゴール</strong>
  <ul>
    <li>RLS のコマンドを早見表で引けるようにする</li>
    <li>導入前に確認すべき点をチェックリストで押さえる</li>
  </ul>
</div>

<h2 id="sec-7-1">7.1　コマンド早見表</h2>
<table>
  <thead><tr><th>やりたいこと</th><th>コマンド</th></tr></thead>
  <tbody>
    <tr><td>RLS を有効化</td><td><code>ALTER TABLE t ENABLE ROW LEVEL SECURITY;</code></td></tr>
    <tr><td>所有者にも適用（バイパス停止）</td><td><code>ALTER TABLE t FORCE ROW LEVEL SECURITY;</code></td></tr>
    <tr><td>読み取りポリシー</td><td><code>CREATE POLICY p ON t USING (条件);</code></td></tr>
    <tr><td>読み書きで条件を分ける</td><td><code>CREATE POLICY p ON t USING (読める条件) WITH CHECK (書ける条件);</code></td></tr>
    <tr><td>コマンド別</td><td><code>CREATE POLICY p ON t FOR SELECT USING (…);</code>（<code>INSERT</code>/<code>UPDATE</code>/<code>DELETE</code>/<code>ALL</code>）</td></tr>
    <tr><td>ロール別</td><td><code>CREATE POLICY p ON t TO some_role USING (…);</code></td></tr>
    <tr><td>必須条件を足す（AND）</td><td><code>CREATE POLICY p ON t AS RESTRICTIVE USING (…);</code></td></tr>
    <tr><td>ポリシー変更／削除</td><td><code>ALTER POLICY p ON t USING (…);</code> / <code>DROP POLICY p ON t;</code></td></tr>
    <tr><td>設定を確認</td><td><code>\\d t</code> / <code>SELECT * FROM pg_policies WHERE tablename='t';</code></td></tr>
    <tr><td>効いているか確認</td><td><code>EXPLAIN (COSTS OFF) SELECT * FROM t;</code>（<code>Filter</code> を見る）</td></tr>
    <tr><td>一時的に無効化</td><td><code>ALTER TABLE t DISABLE ROW LEVEL SECURITY;</code></td></tr>
    <tr><td>セッション変数を使う</td><td><code>SET LOCAL app.tenant_id = '100';</code> ＋ <code>current_setting('app.tenant_id', true)</code></td></tr>
  </tbody>
</table>
<div class="note">
  <strong>可視性の最終式</strong>
  ある操作で行が通るのは <code>(GRANT がある) AND (PERMISSIVE のどれか) AND (RESTRICTIVE のすべて)</code>。
  PERMISSIVE が 1 つも無ければ全拒否。
</div>

<h2 id="sec-7-2">7.2　設計チェックリスト</h2>
<div class="checkpoint">
  <strong>✅ 導入前チェック</strong>
  <ul>
    <li>絞りたいのは「行」か？（テーブル・列単位なら GRANT で足りる）</li>
    <li>行の所属をどの列で判定するか決めた（<code>owner</code> / <code>tenant_id</code> など）。その列にインデックスがある</li>
    <li>操作ごと（SELECT/INSERT/UPDATE/DELETE）に必要なポリシーを洗い出した（デフォルト拒否対策）</li>
    <li>書き込みに独自条件が要るなら <code>WITH CHECK</code> を明記した</li>
    <li>アプリの接続ロールは<strong>非スーパーユーザ・<code>BYPASSRLS</code> なし</strong></li>
    <li>接続ロールが対象表の<strong>所有者</strong>を兼ねるなら <code>FORCE</code> を付けた</li>
    <li>接続プールなら <code>SET LOCAL</code> でテナントを設定し、未設定時は 0 行に倒す設計にした</li>
    <li>一般ロールで動作確認した（所有者・スーパーユーザで確認していない）</li>
  </ul>
</div>
<p>ここまで確認できれば、RLS の基本的な設計・実装・切り分けはひととおり自分でできる。あとは対象テーブルに
  合わせてポリシーを足していくだけである。</p>
<div class="note">
  <strong>内部の仕組みを知りたい人へ</strong>
  ポリシーがどのようにプランへ組み込まれるか等の実装詳細は、同じ一覧にある内部構造ドキュメント
  （<code>rls</code> / <code>role-membership-acl</code>）を参照するとよい。
</div>
""")


def build():
    # テンプレートの著者向け HTML コメントには {{PLACEHOLDER}} の説明が含まれるため、
    # 置換前に取り除く（残すと本文がコメント内にも二重挿入される）。
    comment = re.compile(r"<!--.*?-->", re.DOTALL)
    page_tpl = comment.sub("", (SKILL / "page-template.html").read_text(encoding="utf-8"), count=1)
    index_tpl = comment.sub("", (SKILL / "index-template.html").read_text(encoding="utf-8"), count=1)

    for i, (title, _desc, _secs) in enumerate(CHAPTERS):
        n = i + 1
        html = page_tpl
        repl = {
            "SITE_TITLE": SITE_TITLE,
            "VERSION_INFO": VERSION_INFO,
            "PAGE_TITLE": "第%d章 %s" % (n, title),
            "SIDEBAR_TOC": sidebar(i),
            "CHAPTER_NUMBER": "第%d章" % n,
            "CHAPTER_TITLE": title,
            "CHAPTER_BODY": BODIES[n].strip(),
            "PAGER": pager(i),
            "FOOTER": FOOTER,
        }
        for k, v in repl.items():
            html = html.replace("{{" + k + "}}", v)
        (HERE / ("ch%02d.html" % n)).write_text(html, encoding="utf-8")

    cards = []
    for i, (title, desc, _secs) in enumerate(CHAPTERS):
        n = i + 1
        cards.append(
            '<a class="toc-card" href="ch%02d.html">\n'
            '  <span class="num">第%d章</span>\n'
            '  <span class="title">%s</span>\n'
            '  <span class="desc">%s</span>\n'
            '</a>' % (n, n, title, desc)
        )
    lead = ("PostgreSQL の行レベルセキュリティ（RLS）を、実際に <code>psql</code> で動かしながら身につける実践ガイド。"
            "所有者ベースの最小例からマルチテナント、はまりどころまでを、"
            "<strong>入力と実行結果をセット</strong>で追う。上から順にコマンドを打っていけば、"
            "RLS の設計・実装・トラブル切り分けの 8 割を自力でこなせるようになる。"
            "所要時間の目安は 40〜60 分。掲載コマンド・出力はローカルの PostgreSQL ビルドで検証済み"
            "（RLS は PostgreSQL 9.5 以降で共通の挙動）。")
    html = index_tpl
    repl = {
        "SITE_TITLE": SITE_TITLE,
        "VERSION_INFO": VERSION_INFO,
        "AUDIENCE": AUDIENCE,
        "LEAD": lead,
        "SIDEBAR_TOC": sidebar(-1),
        "TOC_CARDS": "\n        ".join(cards),
        "FOOTER": FOOTER,
    }
    for k, v in repl.items():
        html = html.replace("{{" + k + "}}", v)
    (HERE / "index.html").write_text(html, encoding="utf-8")

    print("built index.html + ch01..ch%02d.html" % len(CHAPTERS))


if __name__ == "__main__":
    build()
