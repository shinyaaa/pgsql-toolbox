# -*- coding: utf-8 -*-
"""
各章の本文 HTML と目次メタデータ。build.py がこれを読み込んでページを生成する。

GH: GitHub コードポインタのベース URL（PostgreSQL サブモジュールの固定コミット）。
"""

GH = "https://github.com/shinyaaa/postgres/blob/d15a6bc2e16d4b330d6d455e41ce1ab3395d8e03"

LEAD = """
<code>JSON_TABLE</code> は JSON ドキュメントをリレーションに変換する SQL/JSON 標準の機能である。
その中でも <strong>PLAN 句</strong>は、<code>NESTED COLUMNS</code> で表現される親子・兄弟のパスを
どのように結合して行を組み立てるかを制御する、内部構造がもっとも凝縮した部分にあたる。
本ドキュメントは PostgreSQL 20devel（<code>shinyaaa/postgres</code> サブモジュール）のソースコードを
主たる典拠として、PLAN 句の構文・意味論から、パーサが構築する実行木、そして実行器が行を
1 件ずつ生成するアルゴリズムまでを、図と実例で解き明かす。想定読者は PostgreSQL の内部実装に
関心のあるエンジニアで、SQL/JSON の基本的な構文は既知とする。
"""

# ---------------------------------------------------------------------------
# 第1章
# ---------------------------------------------------------------------------
CH1 = """
<p>
  本章では <code>JSON_TABLE</code> が JSON ドキュメントをどのように行の集合へ展開するのか、その
  基本モデルを確認する。とりわけ <code>NESTED COLUMNS</code> が登場したときに「どの行とどの行を
  組み合わせるか」という結合の問題が生じることを示し、それを制御するのが PLAN 句であることを
  導く。以降の章の前提となる用語と考え方をここで固める。
</p>

<h2 id="sec-1-1">1.1　JSON_TABLE とは何か</h2>
<p>
  <code>JSON_TABLE</code> は FROM 句に置かれ、1 つの JSON ドキュメント（<em>コンテキストアイテム</em>）を
  入力として受け取り、複数行・複数列のリレーションを生成する。パーサはこれを
  <code>TableFunc</code> ノード（<code>functype = TFT_JSON_TABLE</code>）へ変換する。変換の入口が
  <a href="%(GH)s/src/backend/parser/parse_jsontable.c#L84"><code>transformJsonTable()</code></a> で、
  コンテキストアイテムと行パターン式は <code>TableFunc.docexpr</code> に、各列を計算する式は
  <code>TableFunc.colvalexprs</code> に格納される。
</p>
<p>
  実行時には汎用の <code>TableFuncScan</code> ノードがこの <code>TableFunc</code> を駆動する。
  JSON_TABLE 固有の振る舞いは、コールバックの集合
  <a href="%(GH)s/src/backend/utils/adt/jsonpath_exec.c#L408"><code>JsonbTableRoutine</code></a>
  として実装されている。すなわち <code>SetDocument</code>（ドキュメント設定）、
  <code>FetchRow</code>（次の行を取り出す）、<code>GetValue</code>（列値を計算する）などである。
</p>

<h2 id="sec-1-2">1.2　PATH と行パターン</h2>
<p>
  <code>JSON_TABLE</code> の中心概念は<strong>行パターン（row pattern）</strong>である。ルートの
  <code>PATH</code> に書かれた jsonpath 式をコンテキストアイテムに適用した結果の各要素が、
  1 行に対応する。図 1.1 に最小の例を示す。
</p>

<div class="example">
  <span class="example-label">SQL</span>
  <pre><code>SELECT * FROM JSON_TABLE(
  '[{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]',
  '$[*]'
  COLUMNS (
    id   int  PATH '$.id',
    name text PATH '$.name'
  )
) jt;</code></pre>
</div>

<div class="example">
  <span class="example-label">実行結果</span>
  <pre><code> id | name
----+------
  1 | a
  2 | b
(2 rows)</code></pre>
</div>

<figure>
  <pre class="mermaid">
flowchart LR
    DOC["JSON 配列<br/>(コンテキストアイテム)"] --> PATH["行パターン path<br/>$[*]"]
    PATH --> R1["要素 0 → 行1"]
    PATH --> R2["要素 1 → 行2"]
    R1 --> C1["列 id / name を評価"]
    R2 --> C2["列 id / name を評価"]
  </pre>
  <figcaption>図 1.1: ルート path が生成する行パターンと列評価</figcaption>
</figure>

<p>
  各列の値は、その行の行パターン値を新たなコンテキストとして、列ごとの jsonpath
  （例: <code>$.id</code>）を評価して得る。列は種類ごとに <code>JSON_VALUE</code>／
  <code>JSON_QUERY</code>／<code>JSON_EXISTS</code> のいずれかへ変換される
  （<a href="%(GH)s/src/backend/parser/parse_jsontable.c#L483"><code>transformJsonTableColumn()</code></a>）。
</p>

<h2 id="sec-1-3">1.3　NESTED COLUMNS と PLAN の必要性</h2>
<p>
  行パターンの要素がさらに配列を内包するとき、<code>NESTED PATH ... COLUMNS (...)</code> を使って
  その内側の配列を展開できる。ここで初めて「結合」が問題になる。図 1.2 のように、親の 1 行に
  対して子の行が 0 個・1 個・複数個と変わりうるため、両者をどう組み合わせるかを決めなければ
  ならない。
</p>

<figure>
  <pre class="mermaid">
flowchart TB
    subgraph Parent["親 (NESTED でない列)"]
        P1["親行 A"]
        P2["親行 B"]
    end
    subgraph Child["子 (NESTED COLUMNS)"]
        A1["A の子 a1"]
        A2["A の子 a2"]
        B0["B の子 なし"]
    end
    P1 --> A1
    P1 --> A2
    P2 --> B0
  </pre>
  <figcaption>図 1.2: 親行ごとに子行数が異なる（B は子を持たない）</figcaption>
</figure>

<p>
  図 1.2 に示すように、親 A は子を 2 つ持ち、親 B は子を持たない。この状況で
  「B の行を結果に残すか（OUTER 相当）／捨てるか（INNER 相当）」、また複数の
  <code>NESTED</code> が兄弟として並ぶとき「それらを直積するか（CROSS）／継ぎ足すか（UNION）」を
  決める必要がある。これを制御するのが <strong>PLAN 句</strong>である。PostgreSQL の既定では、
  親子は OUTER 結合、兄弟は UNION 結合となる。次章でこの構文と意味論を詳しく見る。
</p>

<div class="note"><strong>メモ</strong>PLAN 句を書かない場合でも、内部的には必ず「既定のプラン」が
組み立てられる。つまり PLAN は<em>省略可能な明示</em>であって、結合戦略そのものは常に存在する。</div>
""" % {"GH": GH}

# ---------------------------------------------------------------------------
# 第2章
# ---------------------------------------------------------------------------
CH2 = """
<p>
  本章では PLAN 句の 2 つの書き方――具体的な結合を指定する <code>PLAN(...)</code> と、既定戦略だけを
  差し替える <code>PLAN DEFAULT(...)</code>――を、文法規則と意味論の両面から整理する。4 つの結合種別
  INNER / OUTER / UNION / CROSS がそれぞれ何を意味するかを明確にする。
</p>

<h2 id="sec-2-1">2.1　明示的 PLAN と PLAN DEFAULT</h2>
<p>
  文法上、PLAN 句は
  <a href="%(GH)s/src/backend/parser/gram.y#L15344"><code>json_table_plan_clause_opt</code></a>
  で定義される。取りうる形は次の 3 通りである。
</p>
<ul>
  <li><code>PLAN ( &lt;plan&gt; )</code> ―― パスの結合方法を名前付きで具体的に記述する（<em>明示プラン</em>）。</li>
  <li><code>PLAN DEFAULT ( &lt;choices&gt; )</code> ―― 既定の結合戦略だけを差し替える（<em>デフォルトプラン</em>）。</li>
  <li>省略 ―― プラン指定なし。内部的には「暗黙のデフォルトプラン」が使われる。</li>
</ul>
<p>
  明示プランは各パスに付けた<strong>名前</strong>で構造を記述する。たとえば
  <code>PLAN (root OUTER child)</code> のように、ルートパス名と子パス名を結合演算子でつなぐ。
  一方 <code>PLAN DEFAULT (INNER, UNION)</code> は個々のパス名を書かず、親子・兄弟の既定結合の種類だけを
  指定する。
</p>

<h2 id="sec-2-2">2.2　結合種別: INNER / OUTER / UNION / CROSS</h2>
<p>
  結合種別は
  <a href="%(GH)s/src/include/nodes/parsenodes.h#L2000"><code>JsonTablePlanJoinType</code></a>
  として、ビットフラグの列挙で定義される。
</p>

<div class="example">
  <span class="example-label">src/include/nodes/parsenodes.h</span>
  <pre><code>typedef enum JsonTablePlanJoinType
{
    JSTP_JOIN_INNER = 0x01,
    JSTP_JOIN_OUTER = 0x02,
    JSTP_JOIN_CROSS = 0x04,
    JSTP_JOIN_UNION = 0x08,
} JsonTablePlanJoinType;</code></pre>
</div>

<p>
  4 種は 2 つの軸に分かれる。<strong>親子（縦）方向</strong>は INNER か OUTER のいずれか、
  <strong>兄弟（横）方向</strong>は UNION か CROSS のいずれかである。
</p>
<ul>
  <li><strong>OUTER</strong>: 親行に対応する子行が無くても、親行を（子列を NULL にして）残す。</li>
  <li><strong>INNER</strong>: 子行が無い親行は結果から落とす。</li>
  <li><strong>UNION</strong>: 兄弟の <code>NESTED</code> 群を「継ぎ足し」で並べる。ある兄弟の行を出すとき、
      他の兄弟の列は NULL になる。</li>
  <li><strong>CROSS</strong>: 兄弟の <code>NESTED</code> 群の直積（デカルト積）を取る。</li>
</ul>

<figure>
  <pre class="mermaid">
flowchart TB
    ROOT["PLAN 結合種別"]
    ROOT --> V["親子方向"]
    ROOT --> H["兄弟方向"]
    V --> OUTER["OUTER: 子が無くても親を残す"]
    V --> INNER["INNER: 子が無い親を捨てる"]
    H --> UNION["UNION: 兄弟を継ぎ足す"]
    H --> CROSS["CROSS: 兄弟の直積を取る"]
  </pre>
  <figcaption>図 2.1: 結合種別の 2 軸（親子方向と兄弟方向）</figcaption>
</figure>

<p>
  図 2.1 のとおり、親子方向と兄弟方向は独立して選べる。明示プランでは
  <code>parent OUTER child</code> や <code>a UNION b</code> のように演算子で書き分け、
  デフォルトプランでは <code>DEFAULT(OUTER, UNION)</code> のようにカンマ区切りで両軸を指定する。
</p>

<h2 id="sec-2-3">2.3　文法規則とデフォルト</h2>
<p>
  明示プランの文法は、単純プラン（パス名）を起点に、外部結合・内部結合・和結合・直積結合を
  組み立てる規則からなる。
</p>

<div class="example">
  <span class="example-label">src/backend/parser/gram.y（抜粋）</span>
  <pre><code>json_table_plan_simple:  name
json_table_plan_outer:   json_table_plan_simple OUTER  json_table_plan_primary
json_table_plan_inner:   json_table_plan_simple INNER  json_table_plan_primary
json_table_plan_union:   json_table_plan_primary UNION json_table_plan_primary
json_table_plan_cross:   json_table_plan_primary CROSS json_table_plan_primary</code></pre>
</div>

<p>
  ここで OUTER/INNER の<strong>左辺は必ず単純プラン（パス名）</strong>である点に注意する。すなわち
  親子結合の親は 1 つの名前付きパスでなければならない。一方 UNION/CROSS は
  <code>json_table_plan_primary</code>（単純プラン、または括弧で囲んだプラン）どうしを結合するため、
  兄弟の入れ子構造を表現できる。これらの規則は最終的に
  <a href="%(GH)s/src/backend/nodes/makefuncs.c#L1005"><code>makeJsonTableJoinedPlan()</code></a>
  などを呼んで <code>JsonTablePlanSpec</code> ノードを構築する。
</p>

<p>
  デフォルトプランの選択肢は
  <a href="%(GH)s/src/backend/parser/gram.y#L15400"><code>json_table_default_plan_choices</code></a>
  で定義され、親子方向（INNER/OUTER）と兄弟方向（UNION/CROSS）を最大 1 つずつ指定できる。
  片方だけ指定した場合、もう片方は補完される。文法規則の還元アクションを読むと、
</p>
<ul>
  <li>親子方向だけ指定 → 兄弟方向は <code>JSTP_JOIN_UNION</code> を補う。</li>
  <li>兄弟方向だけ指定 → 親子方向は <code>JSTP_JOIN_OUTER</code> を補う。</li>
</ul>
<p>
  つまり PostgreSQL の<strong>既定は「親子 = OUTER、兄弟 = UNION」</strong>である。PLAN 句を完全に省略した
  場合もこの既定が適用される。SQL 標準に照らすと、この既定は標準が定める既定と一致する。
</p>

<div class="warn"><strong>注意</strong>トップレベルの <code>ON ERROR</code> は
<code>EMPTY [ARRAY]</code> か <code>ERROR</code> のみ許され、それ以外は
<a href="%(GH)s/src/backend/parser/parse_jsontable.c#L98"><code>transformJsonTable()</code></a>
の冒頭で構文エラーになる。PLAN とは独立した制約だが、JSON_TABLE 全体の妥当性検査の一部である。</div>
""" % {"GH": GH}

# ---------------------------------------------------------------------------
# 第3章
# ---------------------------------------------------------------------------
CH3 = """
<p>
  PLAN は 2 段階の内部表現を経る。パーサ前段が構文をそのまま写し取った
  <strong>未変換表現</strong> <code>JsonTablePlanSpec</code> と、意味解析を経て実行可能になった
  <strong>実行木</strong> <code>JsonTablePathScan</code>／<code>JsonTableSiblingJoin</code> である。
  本章はこの 2 表現の構造と、列との対応を押さえる。
</p>

<h2 id="sec-3-1">3.1　未変換表現: JsonTablePlanSpec</h2>
<p>
  PLAN 句の生の構文は
  <a href="%(GH)s/src/include/nodes/parsenodes.h#L2012"><code>JsonTablePlanSpec</code></a>
  に格納される。<code>plan_type</code> により 3 つの形を取る（
  <a href="%(GH)s/src/include/nodes/parsenodes.h#L1989"><code>JsonTablePlanType</code></a>）。
</p>

<div class="example">
  <span class="example-label">src/include/nodes/parsenodes.h（抜粋）</span>
  <pre><code>typedef struct JsonTablePlanSpec
{
    NodeTag     type;
    JsonTablePlanType plan_type;    /* DEFAULT / SIMPLE / JOINED */
    JsonTablePlanJoinType join_type;    /* JOINED のときの結合種別 */
    char       *pathname;           /* SIMPLE のときのパス名 */
    struct JsonTablePlanSpec *plan1;    /* JOINED の第1プラン */
    struct JsonTablePlanSpec *plan2;    /* JOINED の第2プラン */
    ParseLoc    location;
} JsonTablePlanSpec;</code></pre>
</div>

<ul>
  <li><code>JSTP_DEFAULT</code>: <code>PLAN DEFAULT(...)</code> または省略。<code>join_type</code> に既定の結合種別を保持。</li>
  <li><code>JSTP_SIMPLE</code>: 単一パス名を表す（<code>pathname</code> のみ有効）。</li>
  <li><code>JSTP_JOINED</code>: <code>plan1</code> と <code>plan2</code> を <code>join_type</code> で結合する二分木。</li>
</ul>
<p>
  <code>JSTP_JOINED</code> の <code>plan1</code>／<code>plan2</code> がさらに <code>JsonTablePlanSpec</code> を
  指すことで、<code>(a UNION b) CROSS c</code> のような入れ子を二分木として表せる。図 3.1 に構造を示す。
</p>

<figure>
  <pre class="mermaid">
flowchart TB
    J1["JSTP_JOINED<br/>join_type = CROSS"]
    J1 --> J2["JSTP_JOINED<br/>join_type = UNION"]
    J1 --> S3["JSTP_SIMPLE<br/>pathname = c"]
    J2 --> S1["JSTP_SIMPLE<br/>pathname = a"]
    J2 --> S2["JSTP_SIMPLE<br/>pathname = b"]
  </pre>
  <figcaption>図 3.1: <code>(a UNION b) CROSS c</code> の JsonTablePlanSpec 二分木</figcaption>
</figure>

<h2 id="sec-3-2">3.2　変換後の実行木: JsonTablePathScan と JsonTableSiblingJoin</h2>
<p>
  意味解析を経ると、PLAN は実行可能な木に変わる。基底クラスは抽象型
  <a href="%(GH)s/src/include/nodes/primnodes.h#L1903"><code>JsonTablePlan</code></a> で、
  具象は 2 種類である。
</p>
<ul>
  <li><a href="%(GH)s/src/include/nodes/primnodes.h#L1914"><code>JsonTablePathScan</code></a> ――
      1 つの jsonpath を評価して行パターンを生成し、必要なら子プランを持つ「スキャン」。</li>
  <li><a href="%(GH)s/src/include/nodes/primnodes.h#L1945"><code>JsonTableSiblingJoin</code></a> ――
      同じ親の下に並ぶ兄弟 <code>NESTED</code> 群を結合する「シブリング結合」。</li>
</ul>

<div class="example">
  <span class="example-label">src/include/nodes/primnodes.h（抜粋）</span>
  <pre><code>typedef struct JsonTablePathScan
{
    JsonTablePlan plan;
    JsonTablePath *path;        /* 評価する jsonpath */
    bool        errorOnError;   /* トップレベルの ERROR ON ERROR か */
    JsonTablePlan *child;       /* 子（NESTED）プラン、無ければ NULL */
    bool        outerJoin;      /* 子との結合が OUTER か INNER か */
    int         colMin;         /* このスキャンが計算する列の範囲 */
    int         colMax;
} JsonTablePathScan;

typedef struct JsonTableSiblingJoin
{
    JsonTablePlan plan;
    JsonTablePlan *lplan;       /* 左の兄弟プラン */
    JsonTablePlan *rplan;       /* 右の兄弟プラン */
    bool        cross;          /* CROSS(直積) か UNION か */
} JsonTableSiblingJoin;</code></pre>
</div>

<p>
  ここで重要なのは表現の非対称性である。<strong>親子（縦）方向</strong>は
  <code>JsonTablePathScan.child</code> と <code>outerJoin</code> フラグで表され、
  独立したノードを作らない。一方<strong>兄弟（横）方向</strong>は独立した
  <code>JsonTableSiblingJoin</code> ノードで表され、<code>cross</code> フラグで UNION/CROSS を区別する。
  <code>path</code> フィールドは
  <a href="%(GH)s/src/include/nodes/primnodes.h#L1888"><code>JsonTablePath</code></a>
  型で、コンパイル済みの <code>jsonpath</code> 定数とパス名を保持する。
</p>

<figure>
  <pre class="mermaid">
flowchart TB
    RootScan["JsonTablePathScan<br/>path = $ (ルート)<br/>outerJoin = true"]
    RootScan -->|child| Sib["JsonTableSiblingJoin<br/>cross = false (UNION)"]
    Sib -->|lplan| ScanA["JsonTablePathScan<br/>path = $.a"]
    Sib -->|rplan| ScanB["JsonTablePathScan<br/>path = $.b"]
  </pre>
  <figcaption>図 3.2: ルート直下に 2 つの兄弟 NESTED がある場合の実行木</figcaption>
</figure>

<h2 id="sec-3-3">3.3　列と行パターンの対応</h2>
<p>
  各 <code>JsonTablePathScan</code> は、自分が計算する非 NESTED 列の範囲を
  <code>colMin</code>／<code>colMax</code> で保持する。これは <code>TableFunc.colvalexprs</code>
  という<strong>全列を平坦に並べたリスト</strong>における 0 始まりの添字である。図 3.2 に示すように、
  親の列と各 NESTED の列は 1 本のリストに連結され、どのスキャンがどの区間を担当するかを
  <code>[colMin, colMax]</code> が指す。
</p>
<p>
  すべての列が NESTED（＝自スキャンが直接計算する列が無い）の場合、
  <code>colMin = colMax = -1</code> となる。この対応付けは
  <a href="%(GH)s/src/backend/parser/parse_jsontable.c#L269"><code>transformJsonTableColumns()</code></a>
  が列を追加しながら記録し、実行時に「行が確定したときどの列をどのスキャンから引くか」を
  決めるのに使われる（第 5 章で詳述）。
</p>
""" % {"GH": GH}

# ---------------------------------------------------------------------------
# 第4章
# ---------------------------------------------------------------------------
CH4 = """
<p>
  本章は、生の <code>JsonTablePlanSpec</code> と列定義から実行木を組み立てるパーサ変換を追う。
  中心は
  <a href="%(GH)s/src/backend/parser/parse_jsontable.c#L269"><code>transformJsonTableColumns()</code></a>
  と
  <a href="%(GH)s/src/backend/parser/parse_jsontable.c#L563"><code>transformJsonTableNestedColumns()</code></a>
  の相互再帰である。ここで PLAN の妥当性検査と、既定プランの木への展開が行われる。
</p>

<h2 id="sec-4-1">4.1　transformJsonTableColumns の全体像</h2>
<p>
  <code>transformJsonTableColumns()</code> は「あるパスとその配下の列集合」を受け取り、1 つの
  <code>JsonTablePathScan</code> を返す。処理の骨子は図 4.1 のとおりである。
</p>

<figure>
  <pre class="mermaid">
flowchart TB
    START["transformJsonTableColumns(planspec, columns, pathspec)"]
    START --> COLMIN["colMin = 現在の colvalexprs 長"]
    COLMIN --> CHECK{"planspec は<br/>DEFAULT か?"}
    CHECK -->|"デフォルト"| APPEND
    CHECK -->|"明示"| VALID["親子プランを検証<br/>パス名一致 / 子プラン検査"]
    VALID --> APPEND["appendJsonTableColumns<br/>(非 NESTED 列を追加)"]
    APPEND --> COLMAX["colMax を確定<br/>(全て NESTED なら -1)"]
    COLMAX --> NESTED["transformJsonTableNestedColumns<br/>(子プランを再帰生成)"]
    NESTED --> SCAN["makeJsonTablePathScan<br/>(JsonTablePathScan を構築)"]
  </pre>
  <figcaption>図 4.1: transformJsonTableColumns の処理フロー</figcaption>
</figure>

<p>
  まず <code>colMin</code> に現在の <code>colvalexprs</code> の長さを記録する。次に
  <a href="%(GH)s/src/backend/parser/parse_jsontable.c#L361"><code>appendJsonTableColumns()</code></a>
  が非 NESTED 列（<code>FOR ORDINALITY</code>・通常列・<code>EXISTS</code> 等）を変換して
  <code>colvalexprs</code> に追加する。追加後の長さと <code>colMin</code> を比べ、変化が無ければ
  「自分は直接の列を持たない」として <code>colMin = colMax = -1</code> とする。最後に子プランを
  再帰生成し、
  <a href="%(GH)s/src/backend/parser/parse_jsontable.c#L663"><code>makeJsonTablePathScan()</code></a>
  で <code>JsonTablePathScan</code> を組み立てる。
</p>
<p>
  <code>makeJsonTablePathScan()</code> は行パターン path 文字列を
  <code>jsonpath_in</code> でコンパイルして <code>Const</code> 化し、<code>outerJoin</code> を
  「デフォルトプラン、または <code>join_type</code> に <code>JSTP_JOIN_OUTER</code> ビットが立つ場合に真」と
  定める。ここが「既定が OUTER」を実装している箇所である。
</p>

<h2 id="sec-4-2">4.2　親子プランの検証</h2>
<p>
  明示プラン（非デフォルト）の場合、変換に先立って妥当性が検査される。
  <code>transformJsonTableColumns()</code> 内のロジックは次を要求する。
</p>
<ul>
  <li><code>JSTP_JOINED</code> の <code>join_type</code> は <strong>INNER か OUTER</strong> のいずれか
      （親子結合のみ、ここで UNION/CROSS は不可）。そうでなければ
      <em>「Expected INNER or OUTER.」</em> の構文エラー。</li>
  <li>親プラン（<code>plan1</code> または単純プラン）の <code>pathname</code> が、いま処理している
      <code>pathspec-&gt;name</code> と<strong>一致</strong>すること。不一致なら
      <em>「PATH name mismatch」</em> エラー。</li>
  <li>子プランは
      <a href="%(GH)s/src/backend/parser/parse_jsontable.c#L750"><code>validateJsonTableChildPlan()</code></a>
      でさらに検査する。</li>
</ul>
<p>
  <code>validateJsonTableChildPlan()</code> は、子プラン側のパス名を
  <a href="%(GH)s/src/backend/parser/parse_jsontable.c#L719"><code>collectSiblingPathsInJsonTablePlan()</code></a>
  で集め、実際の <code>NESTED</code> 列の集合と突き合わせる。次の 3 点を保証する。
</p>
<ol>
  <li>すべての NESTED 列がパス名を持つ（無名なら自動生成されるが、明示 PLAN からは参照不可）。</li>
  <li>すべての NESTED 列が、プラン側の兄弟ノードに対応先を持つ（無ければ
      <em>「PLAN clause for nested path ... was not found」</em>）。</li>
  <li>プラン側に余分・重複ノードが無い（あれば
      <em>「PLAN clause contains some extra or duplicate sibling nodes」</em>）。</li>
</ol>
<p>
  この検査により、明示 PLAN と実際の列構造の齟齬がパース時に確実に検出される。
</p>

<h2 id="sec-4-3">4.3　NESTED 列の再帰変換とシブリング結合</h2>
<p>
  子プランの生成は
  <a href="%(GH)s/src/backend/parser/parse_jsontable.c#L563"><code>transformJsonTableNestedColumns()</code></a>
  が担う。プラン種別ごとに分岐する。
</p>

<figure>
  <pre class="mermaid">
flowchart TB
    IN["transformJsonTableNestedColumns(planspec)"]
    IN --> D{"plan_type?"}
    D -->|"NULL / DEFAULT"| LOOP["NESTED 列を順に走査"]
    LOOP --> BUILD["各 NESTED を再帰変換し<br/>直前の兄弟と SiblingJoin で連結"]
    BUILD --> RET1["先頭は単独、以降は<br/>makeJsonTableSiblingJoin"]
    D -->|"SIMPLE"| FIND1["pathname で NESTED 列を検索"]
    D -->|"JOINED (INNER/OUTER)"| FIND2["plan1.pathname で NESTED 列を検索"]
    D -->|"JOINED (UNION/CROSS)"| REC["左右を再帰変換し<br/>SiblingJoin で結合"]
    FIND1 --> REC2["見つけた列を再帰変換"]
    FIND2 --> REC2
  </pre>
  <figcaption>図 4.2: transformJsonTableNestedColumns のプラン種別ごとの分岐</figcaption>
</figure>

<p>
  図 4.2 のとおり、<strong>デフォルトプラン</strong>では <code>columns</code> 中の <code>NESTED</code> 列を
  順に走査し、それぞれを再帰変換したうえで、直前までの結果と
  <a href="%(GH)s/src/backend/parser/parse_jsontable.c#L705"><code>makeJsonTableSiblingJoin()</code></a>
  で連結していく。連結時の <code>cross</code> は <code>planspec</code> の <code>join_type</code> に
  <code>JSTP_JOIN_CROSS</code> ビットが立っているかで決まる。つまり複数兄弟は左結合的に
  <code>SiblingJoin</code> の連鎖になる。
</p>
<p>
  <strong>SIMPLE / JOINED(INNER,OUTER)</strong> では、プランが名指しするパス名で対応する
  <code>NESTED</code> 列を
  <a href="%(GH)s/src/backend/parser/parse_jsontable.c#L536"><code>findNestedJsonTableColumn()</code></a>
  で探し、その列を再帰変換する。<strong>JOINED(UNION,CROSS)</strong> では <code>plan1</code>／<code>plan2</code>
  を個別に再帰変換し、<code>join_type</code> に応じて <code>cross</code> を立てた
  <code>SiblingJoin</code> にまとめる。こうして明示 PLAN の二分木が、実行木の
  <code>SiblingJoin</code> と <code>PathScan.child</code> の入れ子へ写し取られる。
</p>

<div class="info"><strong>関連</strong>ここで生成された <code>JsonTablePlan</code> の木は
<code>TableFunc.plan</code> に格納され、実行時に第 5 章の初期化ルーチンが解釈する。</div>
""" % {"GH": GH}

# ---------------------------------------------------------------------------
# 第5章
# ---------------------------------------------------------------------------
CH5 = """
<p>
  実行フェーズに移る。本章は、静的な実行木（<code>JsonTablePlan</code>）から、行を数える動的状態
  <a href="%(GH)s/src/backend/utils/adt/jsonpath_exec.c#L204"><code>JsonTablePlanState</code></a>
  の木を構築する初期化処理を扱う。ここで各列と、その値を供給するプラン状態が結び付けられる。
</p>

<h2 id="sec-5-1">5.1　JsonTablePlanState と JsonTableExecContext</h2>
<p>
  実行時、プラン木の各ノードには 1 つの <code>JsonTablePlanState</code> が対応する。これは
  jsonpath 評価の結果リストとその反復子、現在選択中の行パターン値、序数カウンタ、そして
  親・子・左右の兄弟へのポインタを保持する。
</p>

<div class="example">
  <span class="example-label">src/backend/utils/adt/jsonpath_exec.c（抜粋）</span>
  <pre><code>typedef struct JsonTablePlanState
{
    JsonTablePlan *plan;              /* 元のプランノード */
    JsonPath   *path;                 /* 評価する jsonpath (PathScan のみ) */
    MemoryContext mcxt;               /* 行パターン評価用コンテキスト */
    List       *args;                 /* PASSING 引数 */
    JsonValueList found;              /* jsonpath 結果リスト */
    JsonValueListIterator iter;       /* その反復子 */
    JsonTablePlanRowSource current;   /* 現在行の行パターン値 */
    int         ordinal;              /* ORDINALITY カウンタ */
    struct JsonTablePlanState *nested;   /* 子プラン状態 */
    struct JsonTablePlanState *left;     /* 左兄弟 */
    struct JsonTablePlanState *right;    /* 右兄弟 */
    struct JsonTablePlanState *parent;   /* 親プラン状態 */
    bool        cross;                /* SiblingJoin: 直積か */
    bool        outerJoin;            /* PathScan: 子との OUTER 結合か */
    bool        advanceNested;        /* 制御フラグ */
    bool        advanceRight;
    bool        reset;
} JsonTablePlanState;</code></pre>
</div>

<p>
  実行全体をまとめるのが
  <a href="%(GH)s/src/backend/utils/adt/jsonpath_exec.c#L256"><code>JsonTableExecContext</code></a>
  で、ルートのプラン状態 <code>rootplanstate</code> と、後述の
  <strong>列番号→プラン状態</strong>の対応表 <code>colplanstates</code> を持つ。<code>magic</code> 値で
  取り違えを検出する健全性チェックが入っている。
</p>

<h2 id="sec-5-2">5.2　JsonTableInitPlan による木の構築</h2>
<p>
  初期化の入口は
  <a href="%(GH)s/src/backend/utils/adt/jsonpath_exec.c#L4427"><code>JsonTableInitOpaque()</code></a>
  である。PASSING 引数を評価して <code>JsonPathVariable</code> のリストにし、
  <code>colplanstates</code> 配列を確保したうえで、
  <a href="%(GH)s/src/backend/utils/adt/jsonpath_exec.c#L4508"><code>JsonTableInitPlan()</code></a>
  を呼んでプラン状態木を再帰構築する。
</p>

<figure>
  <pre class="mermaid">
sequenceDiagram
    participant TFS as TableFuncScan
    participant IO as JsonTableInitOpaque
    participant IP as JsonTableInitPlan
    TFS->>IO: 初期化
    IO->>IO: PASSING 引数を評価
    IO->>IO: colplanstates 配列を確保
    IO->>IP: rootplan で再帰開始
    IP->>IP: PathScan なら mcxt 生成・path 展開
    IP->>IP: colMin..colMax を colplanstates に登録
    IP->>IP: child / left / right を再帰初期化
    IP-->>IO: rootplanstate
  </pre>
  <figcaption>図 5.1: 実行木の初期化シーケンス</figcaption>
</figure>

<p>
  <code>JsonTableInitPlan()</code> は、ノードが <code>JsonTablePathScan</code> なら
  <code>outerJoin</code> を写し、コンパイル済み jsonpath を <code>path</code> に展開し、行パターン評価専用の
  メモリコンテキスト <code>mcxt</code> を生成する。<code>JsonTableSiblingJoin</code> なら <code>cross</code>
  を写し、左右の子を再帰初期化する。親ポインタ <code>parent</code> は呼び出し時に渡される。
</p>

<h2 id="sec-5-3">5.3　列番号からプランへの対応表</h2>
<p>
  第 3 章で見た <code>colMin</code>／<code>colMax</code> はここで使われる。
  <code>JsonTableInitPlan()</code> は各 <code>PathScan</code> について
</p>

<div class="example">
  <span class="example-label">src/backend/utils/adt/jsonpath_exec.c（抜粋）</span>
  <pre><code>for (i = scan-&gt;colMin; i &gt;= 0 &amp;&amp; i &lt;= scan-&gt;colMax; i++)
    cxt-&gt;colplanstates[i] = planstate;</code></pre>
</div>

<p>
  として、自分が担当する列番号の位置に自身のプラン状態を書き込む。これにより、実行時に
  <a href="%(GH)s/src/backend/utils/adt/jsonpath_exec.c#L4826"><code>JsonTableGetValue()</code></a>
  が列番号 <code>colnum</code> を受け取ったとき、<code>colplanstates[colnum]</code> から
  「その列の値を供給する行パターンはどのプラン状態が保持しているか」を O(1) で引ける。
  <code>colMin = colMax = -1</code> のスキャン（自前の列を持たない）はこのループを 1 度も回さない。
</p>

<figure>
  <pre class="mermaid">
flowchart LR
    subgraph CVE["colvalexprs (全列を平坦化)"]
        C0["col0: 親.id"]
        C1["col1: 親.name"]
        C2["col2: 子.tag"]
    end
    subgraph CPS["colplanstates"]
        M0["[0] → 親 PathScan 状態"]
        M1["[1] → 親 PathScan 状態"]
        M2["[2] → 子 PathScan 状態"]
    end
    C0 -.-> M0
    C1 -.-> M1
    C2 -.-> M2
  </pre>
  <figcaption>図 5.2: 列番号からプラン状態への対応（colplanstates）</figcaption>
</figure>

<p>
  図 5.2 に示すように、親スキャンが列 0〜1 を、子スキャンが列 2 を担当する場合、
  <code>colplanstates</code> はそれぞれのプラン状態を指す。行が確定した後の列値取り出しは、
  この表を通じて「正しい階層の現在行」から計算される。
</p>
""" % {"GH": GH}

# ---------------------------------------------------------------------------
# 第6章
# ---------------------------------------------------------------------------
CH6 = """
<p>
  本章は JSON_TABLE PLAN の核心――行を 1 件ずつ生成するアルゴリズムを扱う。エントリポイントは
  <a href="%(GH)s/src/backend/utils/adt/jsonpath_exec.c#L4608"><code>JsonTablePlanNextRow()</code></a>
  で、これがプラン木を再帰的に駆動して、親子結合と兄弟結合を実現する。
</p>

<h2 id="sec-6-1">6.1　ドキュメント設定と行パターン評価</h2>
<p>
  スキャン開始時、<code>TableFuncScan</code> はコンテキストアイテムを評価して
  <a href="%(GH)s/src/backend/utils/adt/jsonpath_exec.c#L4559"><code>JsonTableSetDocument()</code></a>
  に渡す。これはルートのプラン状態に対し
  <a href="%(GH)s/src/backend/utils/adt/jsonpath_exec.c#L4572"><code>JsonTableResetRowPattern()</code></a>
  を呼び、<code>executeJsonPath()</code> で行パターン path を評価して結果リスト <code>found</code> を
  埋め、
  <a href="%(GH)s/src/backend/utils/adt/jsonpath_exec.c#L4870"><code>JsonTableRescan()</code></a>
  で反復子を先頭へ戻す。エラーが出ても <code>errorOnError</code> が偽なら結果を空にして続行する。
</p>
<p>
  以降、<code>TableFuncScan</code> は行が尽きるまで
  <a href="%(GH)s/src/backend/utils/adt/jsonpath_exec.c#L4810"><code>JsonTableFetchRow()</code></a>
  を繰り返し呼ぶ。これは単に <code>JsonTablePlanNextRow(rootplanstate)</code> を呼ぶだけである。
  1 行が確定するたびに
  <a href="%(GH)s/src/backend/utils/adt/jsonpath_exec.c#L4826"><code>JsonTableGetValue()</code></a>
  が各列について呼ばれ、<code>colplanstates</code> 経由で現在行の値を計算する。
</p>

<h2 id="sec-6-2">6.2　JsonTablePlanNextRow: 親子結合</h2>
<p>
  <code>JsonTablePlanNextRow()</code> はノード種別で二分岐する。<code>PathScan</code> 側（親子結合）の
  処理を図 6.1 に示す。
</p>

<figure>
  <pre class="mermaid">
flowchart TB
    START["JsonTablePlanNextRow (PathScan)"]
    START --> RESET{"reset フラグ?"}
    RESET -->|"真"| RR["親の現在行で<br/>行パターンを再評価"]
    RESET -->|"偽"| ADV
    RR --> ADV{"advanceNested?"}
    ADV -->|"真"| NEXTN["子の次行を取得<br/>あれば return true"]
    ADV -->|"偽"| LOOP
    NEXTN --> LOOP["ループ"]
    LOOP --> SCAN{"JsonTablePlanScanNextRow<br/>で次の行パターン?"}
    SCAN -->|"無"| RETF["return false"]
    SCAN -->|"有"| HASN{"子プランあり?"}
    HASN -->|"無"| RETT["return true"]
    HASN -->|"有"| RN["子をリセットし<br/>子の最初の行を取得"]
    RN --> J{"子行あり<br/>または outerJoin?"}
    J -->|"はい"| RETT
    J -->|"いいえ (INNER で子無し)"| LOOP
  </pre>
  <figcaption>図 6.1: PathScan における親子結合のループ</figcaption>
</figure>

<p>
  要点は、行パターン（親行）を 1 つ進めるたびに子プランをリセットして子の最初の行を取りに行く
  ところにある。子が行を返せば親×子の 1 行が確定する。子が空でも <code>outerJoin</code> が真なら、
  子列を NULL にして親行を出す（OUTER 結合）。<code>outerJoin</code> が偽（INNER）で子が空なら、
  その親行は捨てて次の親行へ進む――図 6.1 の左下ループがこれである。子の行送りは
  <a href="%(GH)s/src/backend/utils/adt/jsonpath_exec.c#L4712"><code>JsonTablePlanScanNextRow()</code></a>
  が担い、親行を新コンテキストとして子 path を再評価すること（
  <a href="%(GH)s/src/backend/utils/adt/jsonpath_exec.c#L4774"><code>JsonTableResetNestedPlan()</code></a>）で
  階層をまたぐ結合を実現する。
</p>

<h2 id="sec-6-3">6.3　シブリング結合: UNION と CROSS</h2>
<p>
  兄弟結合は <code>JsonTablePlanNextRow()</code> の <code>SiblingJoin</code> 側で処理される。
  <code>cross</code> フラグで挙動が大きく変わる。
</p>

<figure>
  <pre class="mermaid">
flowchart TB
    START["JsonTablePlanNextRow (SiblingJoin)"]
    START --> AR{"advanceRight?"}
    AR -->|"真"| RIGHT["右の次行を取得"]
    RIGHT --> RMORE{"右に行あり?"}
    RMORE -->|"有"| RETT["return true"]
    RMORE -->|"無"| CROSS1{"cross?"}
    CROSS1 -->|"真"| SETOUT["advanceRight=false<br/>(次の左行へ)"]
    CROSS1 -->|"偽 (UNION)"| RETF["return false"]
    AR -->|"偽"| OUTER["左の次行を取得"]
    SETOUT --> OUTER
    OUTER --> UMODE{"cross?"}
    UMODE -->|"偽 (UNION)"| UNIONLOGIC["左が尽きたら<br/>右へ切替えて継ぎ足す"]
    UMODE -->|"真 (CROSS)"| CROSSLOGIC["左1行ごとに<br/>右を先頭から走査"]
  </pre>
  <figcaption>図 6.2: SiblingJoin における UNION と CROSS の分岐</figcaption>
</figure>

<p>
  <strong>UNION</strong>（<code>cross = false</code>）では、まず左プランの行をすべて出し、左が尽きたら
  右プランへ切り替えて継ぎ足す。ある兄弟の行を出している間、もう一方の兄弟の列は現在行を持たず
  NULL になる。これが「兄弟を縦に並べる」既定の挙動である。
</p>
<p>
  <strong>CROSS</strong>（<code>cross = true</code>）では、左を 1 行進めるたびに右を先頭から走査し直し
  （<code>JsonTableRescan(right)</code>）、左×右の直積を生成する。左が尽きた時点で全体が終了する。
  実装上は <code>advanceRight</code> フラグで「いま右を送っている最中か／次の左へ移るか」を管理する。
</p>

<h2 id="sec-6-4">6.4　OUTER / INNER の意味論を実例で確認する</h2>
<p>
  親子結合の OUTER/INNER の違いを、子を持たない親を含むデータで観察する。
</p>

<div class="example">
  <span class="example-label">SQL（既定 = OUTER）</span>
  <pre><code>SELECT * FROM JSON_TABLE(
  '[{"k":"A","items":[10,20]}, {"k":"B","items":[]}]',
  '$[*]'
  COLUMNS (
    k text PATH '$.k',
    NESTED PATH '$.items[*]' COLUMNS (v int PATH '$')
  )
) jt;</code></pre>
</div>

<div class="example">
  <span class="example-label">実行結果</span>
  <pre><code> k | v
---+----
 A | 10
 A | 20
 B |
(3 rows)</code></pre>
</div>

<p>
  既定は OUTER なので、子を持たない <code>B</code> も <code>v</code> を NULL にして 1 行残る。ここで
  明示的に INNER を指定すると、
</p>

<div class="example">
  <span class="example-label">SQL（PLAN で INNER を指定）</span>
  <pre><code>SELECT * FROM JSON_TABLE(
  '[{"k":"A","items":[10,20]}, {"k":"B","items":[]}]',
  '$[*]' AS root
  COLUMNS (
    k text PATH '$.k',
    NESTED PATH '$.items[*]' AS items COLUMNS (v int PATH '$')
  )
  PLAN (root INNER items)
) jt;</code></pre>
</div>

<div class="example">
  <span class="example-label">実行結果</span>
  <pre><code> k | v
---+----
 A | 10
 A | 20
(2 rows)</code></pre>
</div>

<p>
  <code>B</code> は子行を持たないため INNER では脱落する。図 6.1 の左下ループ
  （<code>!advanceNested &amp;&amp; !outerJoin</code> のとき次の親行へ <code>continue</code>）が、
  まさにこの脱落を実装している。
</p>

<div class="note"><strong>メモ</strong>明示 PLAN でパス名を参照するには、ルート path と NESTED path に
<code>AS &lt;name&gt;</code> で名前を付ける必要がある。名前を省くと自動生成名（<code>json_table_path_N</code>）が
割り当てられ、明示 PLAN からは参照できない。</div>
""" % {"GH": GH}

# ---------------------------------------------------------------------------
# 第7章
# ---------------------------------------------------------------------------
CH7 = """
<p>
  最終章では、これまで見た内部構造を SQL の観察で裏付ける。デフォルトプランと明示プランの
  等価性、UNION と CROSS の違い、そして逆整形（deparse）やバージョン上の注意点を扱う。
</p>

<h2 id="sec-7-1">7.1　デフォルトプランの等価な明示形</h2>
<p>
  PLAN を省略したときの既定は「親子 = OUTER、兄弟 = UNION」だった。これは
  <code>PLAN DEFAULT (OUTER, UNION)</code> と等価であり、単一 NESTED なら
  <code>PLAN (root OUTER child)</code> とも等価である。次の 3 クエリは同じ結果を返す。
</p>

<div class="example">
  <span class="example-label">SQL（3 つは等価）</span>
  <pre><code>-- (1) PLAN 省略
... COLUMNS (k text PATH '$.k',
      NESTED PATH '$.items[*]' COLUMNS (v int PATH '$'))

-- (2) PLAN DEFAULT
... COLUMNS (...) PLAN DEFAULT (OUTER, UNION)

-- (3) 明示 PLAN
... '$[*]' AS root COLUMNS (k text PATH '$.k',
      NESTED PATH '$.items[*]' AS items COLUMNS (v int PATH '$'))
    PLAN (root OUTER items)</code></pre>
</div>

<p>
  内部的には、いずれも同型の <code>JsonTablePathScan</code>（<code>outerJoin = true</code>）＋子スキャンへ
  変換される。第 4 章で見た <code>makeJsonTablePathScan()</code> の
  <code>outerJoin = planspec == NULL || (join_type &amp; JSTP_JOIN_OUTER)</code> が、この等価性を生む。
</p>

<h2 id="sec-7-2">7.2　UNION と CROSS の違いを観察する</h2>
<p>
  兄弟 NESTED を 2 つ持つドキュメントで、既定（UNION）と CROSS を比べる。
</p>

<div class="example">
  <span class="example-label">SQL（既定 = UNION）</span>
  <pre><code>SELECT * FROM JSON_TABLE(
  '{"a":[1,2], "b":[9,8]}',
  '$'
  COLUMNS (
    NESTED PATH '$.a[*]' COLUMNS (x int PATH '$'),
    NESTED PATH '$.b[*]' COLUMNS (y int PATH '$')
  )
) jt;</code></pre>
</div>

<div class="example">
  <span class="example-label">実行結果（UNION: 継ぎ足し）</span>
  <pre><code> x | y
---+----
 1 |
 2 |
   | 9
   | 8
(4 rows)</code></pre>
</div>

<div class="example">
  <span class="example-label">SQL（PLAN DEFAULT で CROSS）</span>
  <pre><code>SELECT * FROM JSON_TABLE(
  '{"a":[1,2], "b":[9,8]}',
  '$'
  COLUMNS (
    NESTED PATH '$.a[*]' COLUMNS (x int PATH '$'),
    NESTED PATH '$.b[*]' COLUMNS (y int PATH '$')
  )
  PLAN DEFAULT (CROSS)
) jt;</code></pre>
</div>

<div class="example">
  <span class="example-label">実行結果（CROSS: 直積）</span>
  <pre><code> x | y
---+----
 1 | 9
 1 | 8
 2 | 9
 2 | 8
(4 rows)</code></pre>
</div>

<p>
  UNION は 2+2=4 行の継ぎ足し（他方の列は NULL）、CROSS は 2×2=4 行の直積となる。第 6 章の
  <code>JsonTableSiblingJoin</code> の <code>cross</code> フラグが、この 2 つの結果を切り替えている。
</p>

<h2 id="sec-7-3">7.3　逆整形とバージョン上の注意</h2>
<p>
  実行木からの逆整形（<code>pg_get_viewdef</code> 等での再表示）は
  <a href="%(GH)s/src/backend/utils/adt/ruleutils.c#L12682"><code>get_json_table_nested_columns()</code></a>
  などが担う。これは <code>JsonTablePathScan</code> と <code>JsonTableSiblingJoin</code> を辿り、
  <code>NESTED PATH ... COLUMNS (...)</code> の構造として復元する。PostgreSQL の逆整形は
  <strong>PLAN 句そのものを明示的に再生成せず</strong>、NESTED の入れ子構造として表現する点に注意する。
</p>

<div class="warn"><strong>注意</strong>PLAN 句の構文（明示 PLAN と PLAN DEFAULT）は SQL 標準に由来するが、
実装や既定の詳細はバージョンで差がありうる。本ドキュメントは PostgreSQL 20devel
（<code>shinyaaa/postgres</code>、コミット <code>d15a6bc2e16</code>）のソースに基づく。運用時は対象バージョンの
挙動を実測で確認することを勧める。</div>

<p>
  最後に PLAN 内部構造の全体像を、パース時から実行時までの一連の変換として図 7.1 にまとめる。
</p>

<figure>
  <pre class="mermaid">
flowchart LR
    SQL["PLAN 句<br/>(構文)"] --> SPEC["JsonTablePlanSpec<br/>(未変換木)"]
    SPEC --> TRANS["transformJsonTable*<br/>(検証と変換)"]
    TRANS --> TREE["JsonTablePathScan /<br/>JsonTableSiblingJoin<br/>(実行木)"]
    TREE --> INIT["JsonTableInitPlan<br/>(状態木を構築)"]
    INIT --> STATE["JsonTablePlanState<br/>(動的状態)"]
    STATE --> ROWS["JsonTablePlanNextRow<br/>(行を1件ずつ生成)"]
  </pre>
  <figcaption>図 7.1: PLAN 句が構文から行生成へ至る変換の全体像</figcaption>
</figure>

<p>
  PLAN 句は、SQL/JSON の宣言的な結合指定を、PostgreSQL の実行器が理解できる二分木と状態機械へ
  橋渡しする層である。親子は <code>PathScan.child</code>＋<code>outerJoin</code>、兄弟は
  <code>SiblingJoin.cross</code> という最小限の表現に落とし込み、
  <code>JsonTablePlanNextRow()</code> の再帰でネストしたループ結合を実現している――これが
  JSON_TABLE PLAN の内部構造の要諦である。
</p>
""" % {"GH": GH}


CHAPTERS = [
    {
        "num": 1,
        "title": "JSON_TABLE と行生成モデル",
        "desc": "JSON_TABLE が JSON を行に展開する仕組みと、NESTED COLUMNS が PLAN を必要とする理由を示す。",
        "sections": [
            ("sec-1-1", "1.1 JSON_TABLE とは何か"),
            ("sec-1-2", "1.2 PATH と行パターン"),
            ("sec-1-3", "1.3 NESTED COLUMNS と PLAN の必要性"),
        ],
        "body": CH1,
    },
    {
        "num": 2,
        "title": "PLAN 句の構文と意味論",
        "desc": "明示 PLAN と PLAN DEFAULT の書き方、INNER/OUTER/UNION/CROSS の意味と既定を整理する。",
        "sections": [
            ("sec-2-1", "2.1 明示的 PLAN と PLAN DEFAULT"),
            ("sec-2-2", "2.2 結合種別: INNER / OUTER / UNION / CROSS"),
            ("sec-2-3", "2.3 文法規則とデフォルト"),
        ],
        "body": CH2,
    },
    {
        "num": 3,
        "title": "PLAN を表す内部データ構造",
        "desc": "未変換の JsonTablePlanSpec と、実行木 JsonTablePathScan / JsonTableSiblingJoin を対比する。",
        "sections": [
            ("sec-3-1", "3.1 未変換表現: JsonTablePlanSpec"),
            ("sec-3-2", "3.2 変換後の実行木"),
            ("sec-3-3", "3.3 列と行パターンの対応"),
        ],
        "body": CH3,
    },
    {
        "num": 4,
        "title": "パーサによる PLAN の変換",
        "desc": "transformJsonTableColumns と NESTED 列の再帰変換、および PLAN の妥当性検査を追う。",
        "sections": [
            ("sec-4-1", "4.1 transformJsonTableColumns の全体像"),
            ("sec-4-2", "4.2 親子プランの検証"),
            ("sec-4-3", "4.3 NESTED 列の再帰変換とシブリング結合"),
        ],
        "body": CH4,
    },
    {
        "num": 5,
        "title": "実行器の初期化",
        "desc": "JsonTablePlanState 木の構築と、列番号からプラン状態への対応表 colplanstates を解説する。",
        "sections": [
            ("sec-5-1", "5.1 JsonTablePlanState と JsonTableExecContext"),
            ("sec-5-2", "5.2 JsonTableInitPlan による木の構築"),
            ("sec-5-3", "5.3 列番号からプランへの対応表"),
        ],
        "body": CH5,
    },
    {
        "num": 6,
        "title": "行生成アルゴリズム",
        "desc": "JsonTablePlanNextRow による親子結合・兄弟結合の再帰と、OUTER/INNER/UNION/CROSS の実装を追う。",
        "sections": [
            ("sec-6-1", "6.1 ドキュメント設定と行パターン評価"),
            ("sec-6-2", "6.2 JsonTablePlanNextRow: 親子結合"),
            ("sec-6-3", "6.3 シブリング結合: UNION と CROSS"),
            ("sec-6-4", "6.4 OUTER / INNER の意味論を実例で確認する"),
        ],
        "body": CH6,
    },
    {
        "num": 7,
        "title": "観察と検証",
        "desc": "デフォルトプランの等価性、UNION と CROSS の違い、逆整形とバージョン上の注意を実例で確認する。",
        "sections": [
            ("sec-7-1", "7.1 デフォルトプランの等価な明示形"),
            ("sec-7-2", "7.2 UNION と CROSS の違いを観察する"),
            ("sec-7-3", "7.3 逆整形とバージョン上の注意"),
        ],
        "body": CH7,
    },
]
