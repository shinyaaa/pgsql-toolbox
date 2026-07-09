# -*- coding: utf-8 -*-
"""property_graph ドキュメントの各章本文。build.py から読み込まれる。"""

GH = "https://github.com/shinyaaa/postgres/blob/031904048aa22e7c70dc8e9c170e2743f9b0f090"


def fn(path, line, label):
    """GitHub コードポインタ（行番号あり）を生成する。"""
    return '<a href="%s/%s#L%d"><code>%s</code></a>' % (GH, path, line, label)


def fnf(path, label):
    """GitHub コードポインタ（ファイルのみ）を生成する。"""
    return '<a href="%s/%s"><code>%s</code></a>' % (GH, path, label)


LEAD = """
プロパティグラフ（property graph）は、頂点（vertex）と辺（edge）にラベルとプロパティを
持たせたグラフデータモデルであり、SQL/PGQ（ISO/IEC 9075-16, SQL:2023 の一部）として
標準化されている。本ドキュメントは、SQL/PGQ を実装した PostgreSQL 19beta1
（<code>shinyaaa/postgres</code> フォーク）を題材に、<code>CREATE PROPERTY GRAPH</code> による
グラフ定義がどのようにシステムカタログへ格納され、<code>GRAPH_TABLE</code> クエリが
どのようにして通常のリレーショナルクエリへ<strong>書き換え</strong>られて実行されるのかを、
ソースコードに即して解説する。対象読者は PostgreSQL のパーサ・リライタの基本的な仕組みを
知っているエンジニアである。専用の実行器ノードは一切追加されておらず、グラフ照会機能の
本質が「クエリ書き換え」に凝縮されている点が最大の見どころである。
"""

# =========================================================================
CH1 = """
<p>
本章では、プロパティグラフとは何か、そして PostgreSQL がそれをどのような
オブジェクトとして扱うのかを俯瞰する。SQL/PGQ の 2 つの構成要素である
<code>CREATE PROPERTY GRAPH</code>（グラフの定義）と <code>GRAPH_TABLE</code>
（グラフの照会）の関係を押さえ、クエリ処理パイプライン全体のどこで何が起きるのかを
最初に地図として示す。以降の章はこの地図の各領域を掘り下げるものである。
</p>

<h2 id="sec-1-1">1.1　SQL/PGQ とプロパティグラフモデル</h2>
<p>
<dfn>プロパティグラフ（property graph）</dfn>は、<dfn>頂点（vertex, 別名ノード node）</dfn>と
<dfn>辺（edge, 別名リレーションシップ relationship）</dfn>からなるデータモデルである。
頂点と辺はまとめて<dfn>要素（element）</dfn>と呼ばれ、各要素は 1 つ以上の
<dfn>ラベル（label）</dfn>と、任意個の<dfn>プロパティ（property）</dfn>（名前付きの値）を持つ。
辺は必ず 1 つの始点頂点と 1 つの終点頂点を結ぶ。
</p>
<p>
<dfn>SQL/PGQ（SQL Property Graph Queries）</dfn>は、この考え方を SQL に取り込むための
標準規格 ISO/IEC 9075-16 であり、SQL:2023 の一部として定められている。PostgreSQL 本体には
まだ取り込まれていないが、本ドキュメントが対象とする <code>shinyaaa/postgres</code> フォークには
SQL/PGQ を実装するパッチ（コミット <code>SQL Property Graph Queries (SQL/PGQ)</code>）が
適用されており、<code>CREATE PROPERTY GRAPH</code> 文と、<code>SELECT</code> の
<code>GRAPH_TABLE</code> 句が利用できる。図 1.1 に示すように、プロパティグラフは
頂点・辺・ラベル・プロパティの 4 概念で構成される。
</p>

<figure>
  <pre class="mermaid">
flowchart LR
    subgraph V1["頂点 customers"]
        VL1["ラベル: customers"]
        VP1["プロパティ: customer_id, name, address"]
    end
    subgraph V2["頂点 orders"]
        VL2["ラベル: orders / lists"]
        VP2["プロパティ: order_id, ordered_when"]
    end
    V1 -- "辺 customer_orders<br/>(ラベル: customer_orders)" --> V2
  </pre>
  <figcaption>図 1.1: プロパティグラフの構成要素（頂点・辺・ラベル・プロパティ）</figcaption>
</figure>

<p>
重要なのは、グラフのデータそのものは<strong>通常のテーブル（あるいはビューや外部テーブル）に
格納されたまま</strong>だという点である。1 つの頂点／辺は 1 つのテーブルに対応し、
プロパティグラフの定義はそれらのテーブルをグラフ構造として「束ねる」役割だけを担う。
これは """ + fnf("doc/src/sgml/ref/create_property_graph.sgml", "create_property_graph.sgml") + """ の
Description に明記されている設計思想である。
</p>

<h2 id="sec-1-2">1.2　論理オブジェクトとしてのプロパティグラフ</h2>
<p>
<code>CREATE PROPERTY GRAPH</code> は物理的な実体を作らない。この点で
<code>CREATE VIEW</code> によく似ており、「照会されたときにだけ使われる構造」を
カタログに記録するにすぎない。プロパティグラフは <code>pg_class</code> 上の 1 タプルとして
表現され、その <code>relkind</code> は """ + fn("src/include/catalog/pg_class.h", 181, "RELKIND_PROPGRAPH") + """
（文字 <code>'g'</code>）である。
</p>
<p>
プロパティグラフはテーブルやビューと同じ名前空間を共有するため、同一スキーマ内で
他のリレーション（テーブル・ビュー・シーケンス等）と名前が衝突してはならない。また
プロパティグラフを直接 <code>SELECT</code> したり <code>INSERT</code> したりすることはできず、
<strong><code>GRAPH_TABLE</code> 句の中からのみ</strong>参照できる。次の例のように、
プロパティグラフを普通のテーブルのように扱おうとするとエラーになる。
</p>

<div class="example">
  <span class="example-label">SQL</span>
  <pre><code>SELECT * FROM myshop;          -- error
COPY myshop TO stdout;         -- error
INSERT INTO myshop VALUES (1); -- error</code></pre>
</div>

<div class="note"><strong>メモ</strong>
プロパティグラフは記憶域を持たないため、<code>UNLOGGED</code> を付けて作ることはできない。
一方、構成テーブルのいずれかが一時テーブルであれば、ビューと同様にプロパティグラフも
自動的に一時オブジェクトになる（<code>CreatePropGraph()</code> がその判定を行う）。
</div>

<h2 id="sec-1-3">1.3　クエリ処理パイプライン全体像</h2>
<p>
SQL/PGQ の実装で最も特徴的なのは、<strong>専用の実行器（executor）ノードが一切追加されて
いない</strong>ことである。グラフ照会の意味論は、すべて<strong>クエリ書き換え（rewrite）</strong>の
段階で通常のリレーショナル演算（結合・和集合）へと変換され、以降のプランナと実行器は
それを「ごく普通のサブクエリ」として扱う。図 1.2 にパイプライン全体を示す。
</p>

<figure>
  <pre class="mermaid">
flowchart TB
    A["SQL 文字列<br/>SELECT ... FROM GRAPH_TABLE (...)"] --> B
    B["構文解析 (gram.y)<br/>RangeGraphTable ノード生成"] --> C
    C["解析変換 (parse_clause.c / parse_graphtable.c)<br/>RTE_GRAPH_TABLE + GraphPattern"] --> D
    D["書き換え (rewriteGraphTable.c)<br/>RTE_SUBQUERY へ変換 / パスクエリの UNION"] --> E
    E["プランナ / 実行器<br/>通常のサブクエリとして処理"]
  </pre>
  <figcaption>図 1.2: GRAPH_TABLE を含むクエリの処理パイプライン</figcaption>
</figure>

<p>
各段階の担当は次のとおりである。第2章以降で順に掘り下げる。
</p>
<ul>
  <li><strong>構文解析</strong>: """ + fnf("src/backend/parser/gram.y", "gram.y") + """ が
    <code>GRAPH_TABLE (...)</code> を """ + fn("src/include/nodes/parsenodes.h", 721, "RangeGraphTable") + """
    という生（raw）ノードへ落とし込む。</li>
  <li><strong>解析変換</strong>: """ + fn("src/backend/parser/parse_clause.c", 938, "transformRangeGraphTable()") + """
    がプロパティグラフを開き、パターンと <code>COLUMNS</code> を変換して、範囲テーブルエントリ
    <code>RTE_GRAPH_TABLE</code> を作る（第4章）。</li>
  <li><strong>書き換え</strong>: """ + fn("src/backend/rewrite/rewriteGraphTable.c", 109, "rewriteGraphTable()") + """
    が <code>RTE_GRAPH_TABLE</code> を、辺と頂点の等結合とパスの和集合からなる
    <code>RTE_SUBQUERY</code> へ置き換える（第5・6章）。</li>
  <li><strong>プランナ／実行器</strong>: 置き換え後はグラフ固有の情報が消えているため、
    通常の SQL と全く同じ経路で最適化・実行される。</li>
</ul>

<p>
つまり本ドキュメントの核心は、<strong>「グラフ定義がどうカタログに入るか」（第2・3章）</strong>と、
<strong>「<code>GRAPH_TABLE</code> がどう解析され、どうリレーショナルクエリへ書き換えられるか」
（第4〜6章）</strong>の 2 点に集約される。
</p>
"""

# =========================================================================
CH2 = """
<p>
本章では <code>CREATE PROPERTY GRAPH</code> 文の構文と意味論を、
""" + fn("src/backend/commands/propgraphcmds.c", 104, "CreatePropGraph()") + """
の実装に沿って解説する。グラフをどう記述するか（頂点・辺・KEY・SOURCE/DESTINATION・
ラベル・プロパティ）と、定義が満たすべき一貫性制約、そして最終的にどうカタログへ
書き込まれるかを扱う。
</p>

<h2 id="sec-2-1">2.1　構文の全体像</h2>
<p>
<code>CREATE PROPERTY GRAPH</code> の構文骨格は次のとおりである。頂点テーブル群と
辺テーブル群を列挙し、各要素にラベルとプロパティを付与する。
</p>

<div class="example">
  <span class="example-label">構文</span>
  <pre><code>CREATE [ TEMP | TEMPORARY ] PROPERTY GRAPH name
    [ {VERTEX|NODE} TABLES ( vertex_table_definition [, ...] ) ]
    [ {EDGE|RELATIONSHIP} TABLES ( edge_table_definition [, ...] ) ]

vertex_table_definition:
    vertex_table_name [ AS alias ] [ KEY ( column [, ...] ) ]
        [ label_and_properties ]

edge_table_definition:
    edge_table_name [ AS alias ] [ KEY ( column [, ...] ) ]
        SOURCE [ KEY ( column [, ...] ) REFERENCES ] source_table [ ( column [, ...] ) ]
        DESTINATION [ KEY ( column [, ...] ) REFERENCES ] dest_table [ ( column [, ...] ) ]
        [ label_and_properties ]

label_and_properties:
    NO PROPERTIES | PROPERTIES ALL COLUMNS | PROPERTIES ( { expr [ AS name ] } [, ...] )
  | { { LABEL label | DEFAULT LABEL } [ ...properties... ] } [...]</code></pre>
</div>

<p>
<code>VERTEX</code> と <code>NODE</code>、<code>EDGE</code> と <code>RELATIONSHIP</code> は
それぞれ同義語である。文法規則は """ + fnf("src/backend/parser/gram.y", "gram.y") + """ の
<code>CreatePropGraphStmt</code> 生成規則に定義されている。
</p>

<h2 id="sec-2-2">2.2　頂点テーブル・辺テーブルと KEY / SOURCE / DESTINATION</h2>
<p>
各要素テーブルには<dfn>エイリアス（alias）</dfn>が付く。省略時はテーブル名がエイリアスになる。
エイリアスはグラフ定義内で一意でなければならず、同じテーブルを二度使う場合は明示的な
エイリアスで区別する。
</p>
<p>
<code>KEY</code> は、その要素テーブルの行を一意に識別する列の集合である。省略時は
テーブルの主キーが使われる（""" + fn("src/backend/commands/propgraphcmds.c", 324, "propgraph_element_get_key()") + """）。
辺テーブルは <code>SOURCE</code>／<code>DESTINATION</code> で始点・終点の頂点エイリアスを指定し、
<code>KEY (...) REFERENCES (...)</code> で辺側の列と頂点側の被参照列を結び付ける。
外部キー制約が既に存在すればそれが既定で使われる。図 2.1 にこの結び付きを示す。
</p>

<figure>
  <pre class="mermaid">
flowchart LR
    subgraph EDGE["辺テーブル e1 (KEY a,i)"]
        EK["SOURCE KEY (a) / DESTINATION KEY (i)"]
    end
    subgraph SRC["頂点テーブル t1 (KEY a)"]
        SK["被参照列 a"]
    end
    subgraph DST["頂点テーブル t2 (KEY i)"]
        DK["被参照列 i"]
    end
    SRC -- "SOURCE ... REFERENCES t1(a)" --> EDGE
    EDGE -- "DESTINATION ... REFERENCES t2(i)" --> DST
  </pre>
  <figcaption>図 2.1: 辺テーブルと始点・終点頂点テーブルの結び付き</figcaption>
</figure>

<div class="example">
  <span class="example-label">SQL</span>
  <pre><code>CREATE TABLE t1 (a int, b text);
CREATE TABLE t2 (i int PRIMARY KEY, j int, k int);
CREATE TABLE e1 (a int, i int, t text, PRIMARY KEY (a, i));

CREATE PROPERTY GRAPH g2
    VERTEX TABLES (t1 KEY (a), t2 DEFAULT LABEL)
    EDGE TABLES (
        e1  SOURCE KEY (a) REFERENCES t1 (a)
            DESTINATION KEY (i) REFERENCES t2 (i)
    );</code></pre>
</div>

<p>
始点・終点キーの結合には、両側の列の型に対応する<dfn>等価演算子（equality operator）</dfn>が
必要である。""" + fn("src/backend/commands/propgraphcmds.c", 371, "propgraph_edge_get_ref_keys()") + """
は、主キー／外部キー制約の検証（<code>ATAddForeignKeyConstraint()</code>）に倣って、
被参照側の頂点キーを左オペランド、参照側の辺キーを右オペランドとする等価演算子を
探し出し、見つからなければエラーとする。この演算子 OID は後述するとおりカタログに保存され、
書き換え時の結合条件生成に再利用される（第6章）。
</p>

<h2 id="sec-2-3">2.3　ラベルとプロパティ</h2>
<p>
各要素は<strong>少なくとも 1 つのラベル</strong>を持つ。既定のラベル名は要素テーブルの
エイリアスと同じで、これは <code>DEFAULT LABEL</code> と明示できる。あるいは
<code>LABEL &lt;name&gt;</code> で任意のラベル名を、複数個でも与えられる。ラベル名は
グラフ全体で一意である必要はなく、異なる要素に同じラベルを付けることには意味がある
（第6章の <code>l1</code> の例を参照）。
</p>
<p>
各ラベルは（空でもよい）プロパティのリストを持つ。既定ではテーブルの全列がプロパティとして
公開され、これは <code>PROPERTIES ALL COLUMNS</code> と明示できる。あるいは
<code>PROPERTIES ( expr [ AS name ] )</code> で式を列挙する。式が単純な列参照でない場合は
プロパティ名を明示しなければならない。
</p>

<div class="example">
  <span class="example-label">SQL</span>
  <pre><code>CREATE PROPERTY GRAPH g4
    VERTEX TABLES (
        t1 KEY (a) NO PROPERTIES,
        t2 DEFAULT LABEL PROPERTIES (i + j AS i_j, k),
        t3 KEY (x) LABEL t3l1 PROPERTIES (x, y AS yy)
                   LABEL t3l2 PROPERTIES (x, z AS zz)
    ) ...;</code></pre>
</div>

<h2 id="sec-2-4">2.4　一貫性チェック</h2>
<p>
プロパティグラフ定義は次の一貫性制約を満たさねばならない。これらは
""" + fn("src/backend/commands/propgraphcmds.c", 1051, "check_element_properties()") + """、
""" + fn("src/backend/commands/propgraphcmds.c", 1182, "check_element_label_properties()") + """、
""" + fn("src/backend/commands/propgraphcmds.c", 1276, "check_all_labels_properties()") + """
の 3 つが検証する。
</p>
<ul>
  <li><strong>同名ラベルはプロパティ集合が一致</strong>: 異なる要素に付いた同名ラベルは、
    プロパティの個数と名前が一致しなければならない。</li>
  <li><strong>同名プロパティは型が一致</strong>: どのラベル上にあるかによらず、同名プロパティは
    同じデータ型・型修飾子（typmod）・照合順序（collation）でなければならない。</li>
  <li><strong>同一要素・同名プロパティは式が一致</strong>: 1 つの要素の複数ラベルに同名プロパティが
    あるとき、その値式は一致していなければならない。</li>
</ul>

<div class="warn"><strong>注意</strong>
照合順序の不一致もエラーになる。例えば <code>text</code> 列と <code>text COLLATE "C"</code> 列を
同名プロパティに割り当てると失敗する。<code>b::varchar COLLATE "C"</code> のように明示的に
キャスト・照合指定して型と照合を揃える必要がある。
</div>

<h2 id="sec-2-5">2.5　カタログへの登録（CreatePropGraph）</h2>
<p>
""" + fn("src/backend/commands/propgraphcmds.c", 104, "CreatePropGraph()") + """ の処理の流れを
図 2.2 に示す。頂点情報・辺情報を <code>struct element_info</code> に集めてから、
<code>DefineRelation(..., RELKIND_PROPGRAPH, ...)</code> でプロパティグラフ本体の
<code>pg_class</code> エントリを作り、要素・ラベル・プロパティを各カタログへ挿入する。
</p>

<figure>
  <pre class="mermaid">
sequenceDiagram
    participant U as ユーザー
    participant C as CreatePropGraph()
    participant D as DefineRelation()
    participant I as insert_element_record() 他
    participant K as check_*_properties()
    U->>C: CREATE PROPERTY GRAPH ...
    C->>C: 頂点/辺を element_info に収集<br/>KEY・SOURCE/DEST キー・等価演算子を確定
    C->>D: relkind='g' の pg_class を作成
    D-->>C: プロパティグラフ OID
    C->>I: 頂点→辺の順に要素・ラベル・プロパティを挿入
    C->>C: CommandCounterIncrement()
    C->>K: 一貫性チェック
    K-->>U: 成功 / エラー
  </pre>
  <figcaption>図 2.2: CreatePropGraph() によるカタログ登録の流れ</figcaption>
</figure>

<p>
頂点を先に挿入するのは、辺レコードが始点・終点頂点の<strong>要素 OID</strong>を必要とするためである。
挿入後に <code>CommandCounterIncrement()</code> を呼んで、直後の一貫性チェックが挿入済みタプルを
見えるようにしている点にも注目したい。個々の挿入は
""" + fn("src/backend/commands/propgraphcmds.c", 612, "insert_element_record()") + """、
""" + fn("src/backend/commands/propgraphcmds.c", 745, "insert_label_record()") + """、
""" + fn("src/backend/commands/propgraphcmds.c", 823, "insert_property_records()") + """
が担当する。次章で、これらが書き込む先である 5 つのカタログを詳しく見る。
</p>

<div class="info"><strong>関連</strong>
定義済みグラフに要素やラベルを追加・削除する <code>ALTER PROPERTY GRAPH</code> は
""" + fn("src/backend/commands/propgraphcmds.c", 1291, "AlterPropGraph()") + """ が処理し、
同じ挿入・チェック関数群を再利用する。</div>
"""

# =========================================================================
CH3 = """
<p>
プロパティグラフの定義は、5 つの専用システムカタログに分割して格納される。本章では
各カタログの役割・列・索引を、ヘッダ定義に即して解説する。これらのカタログは
第5・6章の書き換え処理が参照する一次情報源であり、その構造を理解しておくことが
書き換えロジックを追う前提となる。
</p>

<h2 id="sec-3-1">3.1　カタログの全体像</h2>
<p>
図 3.1 に 5 カタログとその主要な参照関係を示す。中心は個々の要素（頂点／辺）を表す
<code>pg_propgraph_element</code> で、そこからラベル、プロパティ、そしてラベルとプロパティを
結ぶ関連テーブルが伸びる。すべての行が <code>pg_class</code> 上のプロパティグラフ OID
（<code>pgXpgid</code> 列）を通じて 1 つのグラフに属する。
</p>

<figure>
  <pre class="mermaid">
flowchart TB
    PGC["pg_class (relkind='g')<br/>プロパティグラフ本体"]
    ELEM["pg_propgraph_element<br/>要素 = 頂点/辺"]
    LABEL["pg_propgraph_label<br/>ラベル"]
    ELABEL["pg_propgraph_element_label<br/>要素とラベルの関連 (M:N)"]
    PROP["pg_propgraph_property<br/>プロパティ (名前と型)"]
    LPROP["pg_propgraph_label_property<br/>ラベル別プロパティ値式"]
    PGC --> ELEM
    PGC --> LABEL
    PGC --> PROP
    ELEM --> ELABEL
    LABEL --> ELABEL
    ELABEL --> LPROP
    PROP --> LPROP
  </pre>
  <figcaption>図 3.1: プロパティグラフ関連カタログの関係</figcaption>
</figure>

<h2 id="sec-3-2">3.2　pg_propgraph_element — 要素テーブル</h2>
<p>
""" + fn("src/include/catalog/pg_propgraph_element.h", 30, "pg_propgraph_element") + """
は 1 つの頂点または辺を 1 行で表す。主な列は次のとおり。
</p>
<figure>
  <pre class="mermaid">
flowchart LR
    subgraph E["pg_propgraph_element"]
        direction TB
        A["oid : 要素 OID"]
        B["pgepgid : 所属グラフ (pg_class)"]
        C["pgerelid : 実体テーブル (pg_class)"]
        D["pgealias : エイリアス"]
        F["pgekind : 'v'=頂点 / 'e'=辺"]
        G["pgesrcvertexid / pgedestvertexid : 辺の始点/終点要素"]
        H["pgekey[] : キー列番号"]
        I2["pgesrckey[]/pgesrcref[]/pgesrceqop[] : 始点結合情報"]
        J["pgedestkey[]/pgedestref[]/pgedesteqop[] : 終点結合情報"]
    end
  </pre>
  <figcaption>図 3.2: pg_propgraph_element の主な列</figcaption>
</figure>
<p>
<code>pgekind</code> は <code>PGEKIND_VERTEX ('v')</code> か <code>PGEKIND_EDGE ('e')</code> を取る。
辺の場合のみ、始点・終点頂点の<strong>要素 OID</strong>（<code>pgesrcvertexid</code>,
<code>pgedestvertexid</code>）と、結合に使う 3 組の配列——辺側キー列番号（<code>pgesrckey</code>）、
頂点側被参照列番号（<code>pgesrcref</code>）、等価演算子 OID（<code>pgesrceqop</code>）——が
埋まる。この「キー列・被参照列・演算子」の三つ組が、第6章で辺-頂点結合条件を組み立てる
ための材料になる。<code>(pgepgid, pgealias)</code> に一意索引があり、エイリアスでの検索を支える。
</p>

<h2 id="sec-3-3">3.3　pg_propgraph_label と pg_propgraph_element_label</h2>
<p>
""" + fn("src/include/catalog/pg_propgraph_label.h", 29, "pg_propgraph_label") + """ は、
あるグラフ（<code>pglpgid</code>）に定義されたラベル名（<code>pgllabel</code>）を 1 行で表す。
ラベルと要素は多対多の関係にあり、これを仲介するのが
""" + fn("src/include/catalog/pg_propgraph_element_label.h", 29, "pg_propgraph_element_label") + """
である。1 行が「ラベル <code>pgellabelid</code> が要素 <code>pgelelid</code> に付いている」ことを表す。
</p>
<p>
このカタログには <code>pgellabelid</code> 単独の索引
（<code>PropgraphElementLabelLabelIndexId</code>）があり、「あるラベルを持つ要素をすべて集める」
という第5章の中心処理を効率化している。
</p>

<h2 id="sec-3-4">3.4　pg_propgraph_property と pg_propgraph_label_property</h2>
<p>
""" + fn("src/include/catalog/pg_propgraph_property.h", 29, "pg_propgraph_property") + """ は、
グラフ内のプロパティを名前（<code>pgpname</code>）・型（<code>pgptypid</code>）・
型修飾子（<code>pgptypmod</code>）・照合順序（<code>pgpcollation</code>）で 1 行に表す。
プロパティの<strong>型情報</strong>はここに一元化されており、2.4 節の型一貫性チェックの拠り所となる。
</p>
<p>
実際の<strong>値の式</strong>は、ラベルごとに異なりうるため別カタログ
""" + fn("src/include/catalog/pg_propgraph_label_property.h", 29, "pg_propgraph_label_property") + """
に置かれる。1 行が「要素ラベル <code>plpellabelid</code> におけるプロパティ <code>plppropid</code> の
値式は <code>plpexpr</code> である」ことを表す。<code>plpexpr</code> は
<code>pg_node_tree</code> 型で、実体テーブルの列を参照する式ツリーがシリアライズされている。
書き換え時にはこの式を取り出して実際の <code>Var</code> に貼り込む（第5章）。
</p>

<div class="note"><strong>メモ</strong>
プロパティ「名前・型」（<code>pg_propgraph_property</code>）と、ラベル別の「値式」
（<code>pg_propgraph_label_property</code>）を分離していることが、
「同名プロパティは同型でなければならないが、ラベルによって値式は異なりうる」という
SQL/PGQ の意味論を素直にカタログ構造へ落とし込んでいる。</div>

<h2 id="sec-3-5">3.5　pg_get_propgraphdef で定義を復元する</h2>
<p>
分散して格納された定義は、<code>pg_get_propgraphdef(regclass)</code> で元の
<code>CREATE PROPERTY GRAPH</code> 文へ逆整形（reverse-parse）できる。<code>\\dG</code>／
<code>\\dG+</code> といった psql メタコマンドや <code>pg_dump</code> もこの関数を利用する。
</p>
<div class="example">
  <span class="example-label">SQL</span>
  <pre><code>SELECT pg_get_propgraphdef('g5'::regclass);</code></pre>
</div>
<div class="example">
  <span class="example-label">実行結果（抜粋）</span>
  <pre><code>CREATE PROPERTY GRAPH g5
    VERTEX TABLES (
        t11 ...,
        t12 ...
    )
    EDGE TABLES (
        t13 ... SOURCE KEY (d) REFERENCES t11 (a) ...
                DESTINATION KEY (e) REFERENCES t12 (b) ...
    )</code></pre>
</div>
"""

# =========================================================================
CH4 = """
<p>
ここからはグラフの<strong>照会</strong>側に移る。本章では <code>SELECT</code> の
<code>GRAPH_TABLE</code> 句がどう構文解析され、どのようなパースツリーになり、
解析変換でどう意味づけされるかを追う。書き換え（第5章）の入力となるデータ構造を
ここで固める。
</p>

<h2 id="sec-4-1">4.1　GRAPH_TABLE 構文と MATCH パターン</h2>
<p>
<code>GRAPH_TABLE</code> は <code>FROM</code> 句に置ける表関数風の構文で、
<code>MATCH</code> でパスパターンを、<code>COLUMNS</code> で射影する式を指定する。
</p>
<div class="example">
  <span class="example-label">SQL</span>
  <pre><code>SELECT customer_name
FROM GRAPH_TABLE (myshop
    MATCH (c IS customers WHERE c.address = 'US')
          -[IS customer_orders]->(o IS orders)
    COLUMNS (c.name AS customer_name));</code></pre>
</div>
<p>
パスパターンは<dfn>要素パターン（element pattern）</dfn>の並びである。頂点パターンは
括弧 <code>( )</code>、辺パターンは角括弧と矢印
<code>-[ ]-&gt;</code>（右向き）／<code>&lt;-[ ]-</code>（左向き）／<code>-[ ]-</code>（両方向）で書く。
各パターンには変数名（<code>c</code>）、ラベル式（<code>IS customers</code>、選言 <code>IS a|b</code>）、
要素内 <code>WHERE</code> 句を付けられる。頂点から頂点への辺は <code>-&gt;</code> のように
角括弧を省略した略記も許される。
</p>

<h2 id="sec-4-2">4.2　パースツリー（RangeGraphTable / GraphPattern / GraphElementPattern）</h2>
<p>
""" + fnf("src/backend/parser/gram.y", "gram.y") + """ の生成規則
<code>GRAPH_TABLE '(' qualified_name MATCH graph_pattern COLUMNS '(' labeled_expr_list ')' ')'</code>
は、図 4.1 のパースツリーを組み立てる。頂点となるのが
""" + fn("src/include/nodes/parsenodes.h", 721, "RangeGraphTable") + """ で、グラフ名・
""" + fn("src/include/nodes/parsenodes.h", 1028, "GraphPattern") + """・<code>COLUMNS</code> のリストを保持する。
</p>

<figure>
  <pre class="mermaid">
flowchart TB
    RGT["RangeGraphTable<br/>graph_name / columns / alias"]
    GP["GraphPattern<br/>path_pattern_list / whereClause"]
    PP["path_pattern (List)<br/>= 1 本のパス"]
    GEP1["GraphElementPattern<br/>kind=VERTEX_PATTERN"]
    GEP2["GraphElementPattern<br/>kind=EDGE_PATTERN_RIGHT"]
    GEP3["GraphElementPattern<br/>kind=VERTEX_PATTERN"]
    RGT --> GP
    GP --> PP
    PP --> GEP1
    PP --> GEP2
    PP --> GEP3
  </pre>
  <figcaption>図 4.1: GRAPH_TABLE のパースツリー</figcaption>
</figure>

<p>
""" + fn("src/include/nodes/parsenodes.h", 1048, "GraphElementPattern") + """ の
<code>kind</code> は """ + fn("src/include/nodes/parsenodes.h", 1035, "GraphElementPatternKind") + """
列挙型で、<code>VERTEX_PATTERN</code> / <code>EDGE_PATTERN_LEFT</code> /
<code>EDGE_PATTERN_RIGHT</code> / <code>EDGE_PATTERN_ANY</code> / <code>PAREN_EXPR</code> を取る。
辺かどうかの判定にはマクロ <code>IS_EDGE_PATTERN()</code> が使われる。各パターンは変数名
（<code>variable</code>）、ラベル式（<code>labelexpr</code>）、<code>WHERE</code> 句
（<code>whereClause</code>）、量指定子（<code>quantifier</code>）を持つ。
</p>

<h2 id="sec-4-3">4.3　解析変換の流れ</h2>
<p>
""" + fn("src/backend/parser/parse_clause.c", 938, "transformRangeGraphTable()") + """ が変換の
入口である。処理は次の順で進む。
</p>
<ol>
  <li>グラフ名を <code>parserOpenPropGraph()</code> で開き、グラフ OID を
    <code>GraphTableParseState</code> に記録する。</li>
  <li><code>p_lateral_active</code> を立てる。<code>GRAPH_TABLE</code> の中からは外側の
    <code>FROM</code> 項目を横（lateral）参照できるためである。</li>
  <li>""" + fn("src/backend/parser/parse_graphtable.c", 383, "transformGraphPattern()") + """ で
    パターンを変換する。</li>
  <li><code>COLUMNS</code> の各式を <code>transformExpr()</code> で変換し、ターゲットリストを作る。
    式が単純なプロパティ参照でない場合は明示的な列名が必須。</li>
  <li><code>addRangeTableEntryForGraphTable()</code> で <code>RTE_GRAPH_TABLE</code> を生成する。</li>
</ol>
<p>
パターン変換は
""" + fn("src/backend/parser/parse_graphtable.c", 328, "transformPathPatternList()") + """ →
""" + fn("src/backend/parser/parse_graphtable.c", 270, "transformPathTerm()") + """ →
""" + fn("src/backend/parser/parse_graphtable.c", 238, "transformGraphElementPattern()") + """
と降りていく。<code>transformPathTerm()</code> は、パスが辺で始まる・辺で終わる・頂点が
隣接するといった構文的に不正な並びをここで弾く。
</p>
<div class="warn"><strong>注意</strong>
<code>transformPathPatternList()</code> は、要素パターンの <code>WHERE</code> 句が
まだ変換されていない段階で、パス中の全変数を先に <code>GraphTableParseState.variables</code> へ
集めておく。これにより要素の <code>WHERE</code> 句からの前方参照を検出できるようにしている。
</div>

<h2 id="sec-4-4">4.4　変数・ラベル・プロパティ参照の解決</h2>
<p>
<code>c.name</code> のような参照は、構文上はただの <code>ColumnRef</code>（<var>変数</var>.<var>プロパティ</var>）
として現れる。""" + fn("src/backend/parser/parse_graphtable.c", 78, "transformGraphTablePropertyRef()") + """
がこれを解釈し、第 1 フィールドがパターン中の変数であり、第 2 フィールドがグラフの
プロパティとして解決できれば、
""" + fn("src/include/nodes/primnodes.h", 2189, "GraphPropertyRef") + """ ノードへ変換する。
プロパティ OID・型・型修飾子・照合順序を <code>pg_propgraph_property</code> から引いて格納する。
</p>
<p>
ラベル式（<code>IS customers</code> や <code>IS a|b</code>）は
""" + fn("src/backend/parser/parse_graphtable.c", 165, "transformLabelExpr()") + """ が処理し、
各ラベル名を """ + fn("src/include/nodes/primnodes.h", 2179, "GraphLabelRef") + """（ラベル OID を保持）に、
選言を <code>BoolExpr</code> の木に変換する。名前が解決できなければエラーとなる。
</p>
<div class="note"><strong>メモ</strong>
要素パターン内の <code>WHERE</code> 句では、その要素自身の変数しか参照できない
（<em>non-local element variable reference is not supported</em>）。一方で、外側テーブルの列を
横参照することは可能で、プロパティ参照と外側列参照が同名の場合は<strong>プロパティ参照が優先</strong>される。
この優先順位は <code>GRAPH_TABLE</code> をラテラル結合として扱うことで実現されている。
</div>
"""

# =========================================================================
CH5 = """
<p>
本章がドキュメントの核心である。解析変換で得た <code>RTE_GRAPH_TABLE</code> を、
""" + fn("src/backend/rewrite/rewriteGraphTable.c", 109, "rewriteGraphTable()") + """ が
どのようにして辺と頂点の等結合からなる通常のサブクエリへ書き換えるのかを、
1 本のパス（単一パス）を例に段階的に追う。ラベル選言による複数パスと UNION は第6章で扱う。
</p>

<h2 id="sec-5-1">5.1　書き換えの起点</h2>
<p>
書き換えは、リライタ本体 """ + fnf("src/backend/rewrite/rewriteHandler.c", "rewriteHandler.c") + """ が
範囲テーブルを走査して <code>RTE_GRAPH_TABLE</code> を見つけたときに
<code>rewriteGraphTable()</code> を呼ぶことで始まる。この関数は次の 3 手で RTE を
<strong>その場で</strong>書き換える。
</p>
<ol>
  <li>パスパターンから<strong>パスクエリのリスト</strong>を生成する
    （""" + fn("src/backend/rewrite/rewriteGraphTable.c", 174, "generate_queries_for_path_pattern()") + """）。</li>
  <li>それらを <strong>UNION ALL</strong> で束ねて 1 つの <code>Query</code> にする
    （""" + fn("src/backend/rewrite/rewriteGraphTable.c", 619, "generate_union_from_pathqueries()") + """）。</li>
  <li>RTE の種別を <code>RTE_SUBQUERY</code> へ変え、<code>subquery</code> に上記クエリを差し込み、
    <code>lateral = true</code> にする。グラフ固有フィールドは <code>NULL</code> でクリアする。</li>
</ol>
<p>
これで RTE は「ラテラルなサブクエリ」に化ける。以降のプランナ・実行器はグラフのことを
一切知らずに処理できる。
</p>

<h2 id="sec-5-2">5.2　path_factor と path_element</h2>
<p>
書き換えロジックは 2 つの内部構造体を軸に進む。
</p>
<ul>
  <li><strong>""" + fn("src/backend/rewrite/rewriteGraphTable.c", 57, "path_factor") + """</strong>:
    パス中の 1 つの「位置」を表す。非循環パスでは 1 要素パターンに対応する。<code>kind</code>・
    <code>variable</code>・<code>labelexpr</code>・<code>whereClause</code>、パス内での位置
    <code>factorpos</code>、そして辺の場合の隣接頂点へのリンク <code>src_pf</code>／<code>dest_pf</code>
    を持つ。</li>
  <li><strong>""" + fn("src/backend/rewrite/rewriteGraphTable.c", 79, "path_element") + """</strong>:
    1 つの path_factor のラベル式が解決した<strong>具体的な要素</strong>を表す。要素 OID・
    実体テーブル OID、辺なら始点・終点頂点 OID と結合条件（<code>src_quals</code>／
    <code>dest_quals</code>）を持つ。</li>
</ul>
<p>
つまり path_factor は「パターン上の位置」、path_element は「その位置に当てはまる実要素」であり、
1 つの path_factor は複数の path_element を生みうる（ラベルが複数要素に付いている場合）。
</p>

<h2 id="sec-5-3">5.3　パスの列挙（K-partite グラフの DFS）</h2>
<p>
""" + fn("src/backend/rewrite/rewriteGraphTable.c", 174, "generate_queries_for_path_pattern()") + """
は、まずパターン中の要素パターン列を path_factor のリストに変換し、隣接する頂点と辺の
リンク（<code>src_pf</code>／<code>dest_pf</code>）を張る。次に各 path_factor について、
そのラベル式を満たす要素を集めて path_element のリストを作る
（""" + fn("src/backend/rewrite/rewriteGraphTable.c", 906, "get_path_elements_for_path_factor()") + """）。
</p>
<p>
図 5.1 に示すように、K 個の要素パターンからなるパスパターンは、各パターンが要素の集合を
持つ <strong>K 部グラフ（K-partite graph）</strong>とみなせる。1 本の具体的なパスは、
各パターンから 1 要素ずつ選んだ組み合わせであり、可能なパスの総数は要素数の積になる。
これを深さ優先探索（DFS）で列挙するのが
""" + fn("src/backend/rewrite/rewriteGraphTable.c", 361, "generate_queries_for_path_pattern_recurse()") + """
である。
</p>

<figure>
  <pre class="mermaid">
flowchart LR
    subgraph P0["パターン0 (頂点 a)"]
        E00["要素 v1"]
        E01["要素 v2"]
    end
    subgraph P1["パターン1 (辺 b)"]
        E10["要素 e1_2"]
    end
    subgraph P2["パターン2 (頂点 c)"]
        E20["要素 v2"]
        E21["要素 v3"]
    end
    E00 --> E10
    E01 --> E10
    E10 --> E20
    E10 --> E21
  </pre>
  <figcaption>図 5.1: パスパターンを K 部グラフとみなし、各層から 1 要素ずつ選んでパスを作る</figcaption>
</figure>

<p>
DFS が末端に達するたびに、そのとき選ばれている要素の並び（1 本のパス）を
""" + fn("src/backend/rewrite/rewriteGraphTable.c", 418, "generate_query_for_graph_path()") + """
へ渡して 1 つのクエリを作る。辺が隣接頂点を実際には結んでいない組み合わせは
「壊れたパス」として捨てられ（<code>NULL</code> を返す）、クエリは作られない。
</p>

<h2 id="sec-5-4">5.4　1 本のパスから 1 クエリを生成する</h2>
<p>
""" + fn("src/backend/rewrite/rewriteGraphTable.c", 418, "generate_query_for_graph_path()") + """
は、与えられた 1 本のパスから <code>SELECT</code> クエリを組み立てる。生成物は次の 3 要素からなる。
</p>
<ul>
  <li><strong>FROM リスト</strong>: パス中の各要素の実体テーブルに対する <code>RangeTblEntry</code>。
    <code>path_factor.factorpos + 1</code> が各 RTE の <code>rtindex</code> になるよう、
    要素の順に追加される。</li>
  <li><strong>WHERE（qual）</strong>: (a) 辺と隣接頂点を結ぶ等結合条件、(b) 各要素の
    <code>WHERE</code> 句、(c) <code>GRAPH_TABLE</code> 全体の <code>WHERE</code> 句、の論理積。</li>
  <li><strong>ターゲットリスト</strong>: <code>COLUMNS</code> の各式。</li>
</ul>
<p>
辺-頂点の結合条件は、5.2 節で述べたとおり path_element 生成時に
""" + fn("src/backend/rewrite/rewriteGraphTable.c", 765, "create_pe_for_element()") + """ が
あらかじめ組み立てておいた <code>src_quals</code>／<code>dest_quals</code> を使う（詳細は第6章）。
</p>
<p>
一方、<code>COLUMNS</code> や <code>WHERE</code> に現れる <code>GraphPropertyRef</code>（プロパティ参照）は、
""" + fn("src/backend/rewrite/rewriteGraphTable.c", 1021, "replace_property_refs_mutator()") + """ が
実際の列参照へ<strong>展開</strong>する。手順はこうだ。参照された変数（path_element）に対応する
ラベル群をたどり、そのプロパティの値式（<code>pg_propgraph_label_property.plpexpr</code>）を
カタログから取り出し、式中の <code>Var</code> の <code>varno</code> をこの要素の <code>rtindex</code>
（= <code>factorpos + 1</code>）へ付け替える（<code>ChangeVarNodes()</code>）。図 5.2 に流れを示す。
</p>

<figure>
  <pre class="mermaid">
flowchart TB
    A["GraphPropertyRef (c.name)"] --> B{"変数 c に対応する<br/>path_element を特定"}
    B --> C["要素に紐づくラベルをたどり<br/>プロパティ値式 plpexpr を取得"]
    C --> D["式中の Var の varno を<br/>factorpos+1 に付け替え"]
    D --> E["実体テーブルの列参照 (Var) へ置換"]
  </pre>
  <figcaption>図 5.2: プロパティ参照から実列参照への展開</figcaption>
</figure>

<p>
プロパティがその要素のどのラベルにも値式を持たない場合でも、パターンが選んだ
いずれかのラベルにそのプロパティが関連していれば、SQL/PGQ 標準（6.5 節）に従って
<code>NULL</code> 定数へ展開される。どのラベルとも無関係なプロパティを参照した場合にのみ
エラーとなる。最後に、参照された列に <code>SELECT</code> 権限フラグを立てる処理があり、
これは「プロパティグラフ所有者ではなく<strong>実行ユーザー</strong>の権限で基底表へアクセスする」
という設計（<code>SECURITY INVOKER</code> なビューに相当）を裏付けている。
</p>
"""

# =========================================================================
CH6 = """
<p>
第5章では 1 本のパスがどう 1 クエリになるかを見た。本章では、ラベル選言によって
複数のパスが生じる場合の <strong>UNION</strong>、辺-頂点の<strong>結合条件生成</strong>の詳細、
そして<strong>双方向辺・循環パターン・空パス</strong>という特殊ケースの扱いを見る。
</p>

<h2 id="sec-6-1">6.1　複数パスと UNION ALL</h2>
<p>
1 つの要素パターンがラベル選言（<code>IS a|b</code>）を持ったり、ラベルが複数の要素に
付いていたりすると、5.3 節の DFS は<strong>複数のパスクエリ</strong>を生成する。これらは
""" + fn("src/backend/rewrite/rewriteGraphTable.c", 619, "generate_union_from_pathqueries()") + """ が
<strong>UNION ALL</strong> で束ねる。図 6.1 のように、各パスクエリがサブクエリとなり、
<code>SetOperationStmt</code> の木として再帰的に連結される
（""" + fn("src/backend/rewrite/rewriteGraphTable.c", 696, "generate_setop_from_pathqueries()") + """）。
</p>

<figure>
  <pre class="mermaid">
flowchart TB
    PP["パスパターン (ラベル選言あり)"] --> Q1["パスクエリ1<br/>customers-customer_orders-orders"]
    PP --> Q2["パスクエリ2<br/>customers-customer_wishlists-wishlists"]
    Q1 --> U["UNION ALL<br/>(SetOperationStmt)"]
    Q2 --> U
    U --> R["1 つの RTE_SUBQUERY"]
  </pre>
  <figcaption>図 6.1: ラベル選言から生じた複数パスクエリの UNION ALL</figcaption>
</figure>

<p>
パスクエリが 1 本しかないときは UNION を作らずそのまま使う。UNION の外側クエリの
ターゲットリストは、代表クエリの列名と、集合演算が算出した共通の型・照合順序から
組み立てられる。
</p>

<h2 id="sec-6-2">6.2　辺-頂点リンク qual の生成</h2>
<p>
辺が隣接頂点を結ぶ等結合条件は
""" + fn("src/backend/rewrite/rewriteGraphTable.c", 1168, "build_edge_vertex_link_quals()") + """ が
生成する。3.2 節で述べたカタログの三つ組——辺側キー列（<code>pgesrckey</code>）、
頂点側被参照列（<code>pgesrcref</code>）、等価演算子 OID（<code>pgesrceqop</code>）——を
配列として取り出し、列ごとに <code>OpExpr</code>（等価比較）を組み立てる。
</p>
<p>
主キー／外部キーの qual と同じ流儀で、<strong>被参照側（頂点キー）を左オペランド、
参照側（辺キー）を右オペランド</strong>とし、必要なら型キャストを挿入する。照合順序も
その場で割り当てるため、書き換え後に改めて照合を付与する必要がない。これらの qual は
第5章の <code>create_pe_for_element()</code> が path_element 生成時に一度だけ作り、
同じ要素が複数パスに現れても使い回す。
</p>

<h2 id="sec-6-3">6.3　双方向辺（EDGE_PATTERN_ANY）</h2>
<p>
<code>-[ ]-</code> のように向きを指定しない辺は、<strong>両方向の辺に一致</strong>する。
""" + fn("src/backend/rewrite/rewriteGraphTable.c", 418, "generate_query_for_graph_path()") + """ は、
まず「始点=src, 終点=dest」の向きで qual を作り、<code>EDGE_PATTERN_ANY</code> の場合は
始点と終点を入れ替えた qual も作って、両者を <strong>OR</strong> で結ぶ。入れ替えは
<code>ChangeVarNodes()</code> で qual 中の <code>varno</code> を付け替えることで実現する。
</p>
<div class="note"><strong>メモ</strong>
始点テーブルと終点テーブルが同一（自己ループ的な辺）のとき、どちらの向きの qual も
成立しうるため OR による表現が必要になる。図 6.2 に概念を示す。
</div>

<figure>
  <pre class="mermaid">
flowchart LR
    A["頂点 v (varno=1)"] -- "qual: 正方向<br/>src=v AND dest=w" --> B["頂点 w (varno=3)"]
    B -. "qual: 逆方向 (varno 入替)<br/>src=w AND dest=v" .-> A
  </pre>
  <figcaption>図 6.2: 双方向辺は正逆両方向の結合条件を OR で結ぶ</figcaption>
</figure>

<h2 id="sec-6-4">6.4　循環パターンと同一変数の併合</h2>
<p>
<code>(a)-&gt;(b)-&gt;(a)</code> のように同じ変数名が複数回現れるパターンは<strong>循環パス</strong>を表す。
""" + fn("src/backend/rewrite/rewriteGraphTable.c", 174, "generate_queries_for_path_pattern()") + """ は、
同名変数の要素パターンを<strong>1 つの path_factor に併合</strong>する。併合時には両者の
<code>WHERE</code> 句を <code>AND</code> で連結する。
</p>
<div class="warn"><strong>注意（未対応の組み合わせ）</strong>
併合される 2 つの要素パターンが<strong>ともにラベル式を持つ</strong>場合、本来はラベルの論理積を
取る必要があるが、これは未対応でエラーになる（一方だけがラベル式を持つ場合は
そのラベル式が使われる）。また、同名の<strong>辺</strong>変数が複数の頂点対を結ぶような
「辺・頂点が繰り返し現れるウォーク」も未対応で、<em>an edge cannot connect more than two
vertices even in a cyclic pattern</em> というエラーになる。
</div>

<h2 id="sec-6-5">6.5　空パスパターン</h2>
<p>
あるパスパターンが<strong>1 本もパスを生まない</strong>——どの要素パターンも要素を持たない、
あるいは辺が隣接頂点を結べない——場合、
""" + fn("src/backend/rewrite/rewriteGraphTable.c", 581, "generate_query_for_empty_path_pattern()") + """ が
<strong>1 行も返さないダミークエリ</strong>を作る。<code>WHERE</code> を定数 <code>false</code> にし、
ターゲットリストは <code>COLUMNS</code> と同じ列を<strong>すべて NULL 定数</strong>で埋める。
こうすることで、結果が空でも列の型・数は <code>GRAPH_TABLE</code> の宣言どおりに保たれ、
上位クエリのプランが破綻しない。
</p>
<div class="example">
  <span class="example-label">SQL（辺の総数を数える空パターンの活用）</span>
  <pre><code>SELECT count(*) FROM GRAPH_TABLE (g1 MATCH ()-[]->() COLUMNS (1 AS one));</code></pre>
</div>
"""

# =========================================================================
CH7 = """
<p>
最終章では、これまでの内部動作を踏まえ、実際に動く完全な例を示し、書き換え結果を
自分の目で確認する方法、周辺機能（権限・ビュー・準備文）との相互作用、そして現時点の
実装上の制限をまとめる。
</p>

<h2 id="sec-7-1">7.1　完全な例: myshop グラフ</h2>
<p>
リグレッションテスト """ + fnf("src/test/regress/sql/graph_table.sql", "graph_table.sql") + """ の
<code>myshop</code> グラフは、EC サイトを模したグラフである（図 7.1）。顧客・注文・
ウィッシュリスト・商品を頂点とし、それらの関連を辺で結ぶ。
</p>

<figure>
  <pre class="mermaid">
flowchart LR
    C["customers"] -- customer_orders --> O["orders"]
    C -- customer_wishlists --> W["wishlists"]
    O -- order_items --> P["products"]
    W -- wishlist_items --> P
  </pre>
  <figcaption>図 7.1: myshop プロパティグラフの構造</figcaption>
</figure>

<div class="example">
  <span class="example-label">SQL</span>
  <pre><code>SELECT * FROM GRAPH_TABLE (myshop
    MATCH (c IS customers)-[IS cust_lists]->(l IS lists)-[IS list_items]->(p IS products)
    COLUMNS (c.name AS customer_name, p.name AS product_name, l.list_type))
ORDER BY customer_name, product_name, list_type;</code></pre>
</div>
<p>
ここで <code>lists</code> は <code>orders</code> と <code>wishlists</code> の両頂点に、
<code>cust_lists</code>／<code>list_items</code> は複数の辺に共有されたラベルである。
第6章で見たとおり、共有ラベルは複数のパスクエリを生み、それらが UNION されて 1 つの結果になる。
</p>

<h2 id="sec-7-2">7.2　書き換え結果を観察する</h2>
<p>
<code>GRAPH_TABLE</code> をビューに包むと、<code>pg_get_viewdef()</code> や
<code>EXPLAIN</code> を通じて、書き換え後の姿——すなわち辺と頂点の結合と、
共有ラベルによる <code>UNION ALL</code>——を間接的に観察できる。
</p>
<div class="example">
  <span class="example-label">SQL</span>
  <pre><code>CREATE VIEW vg1 AS
    SELECT * FROM GRAPH_TABLE (g1 MATCH () COLUMNS (1 AS one));
EXPLAIN SELECT * FROM GRAPH_TABLE (myshop
    MATCH (c IS customers)-[IS customer_orders]->(o IS orders)
    COLUMNS (c.name));</code></pre>
</div>
<p>
プランには <code>GRAPH_TABLE</code> という語は現れず、対象テーブル（<code>customers</code>,
<code>customer_orders</code>, <code>orders</code>）の結合として現れる。これが
「専用実行器を持たない」という設計の直接の帰結である。
</p>

<h2 id="sec-7-3">7.3　権限・ビュー・準備文との相互作用</h2>
<ul>
  <li><strong>権限</strong>: 基底表へのアクセスは<strong>実行ユーザー</strong>の権限で判定される
    （<code>SECURITY INVOKER</code> 相当）。プロパティグラフと基底表の双方に適切な権限が必要。
    これは第5章の <code>selectedCols</code> 設定に対応する。</li>
  <li><strong>ビュー・関数への埋め込み</strong>: <code>GRAPH_TABLE</code> はビュー定義や
    SQL/PL/pgSQL 関数、サブクエリ、<code>LATERAL</code> 結合の中に自由に置ける。ビューが
    参照するラベルやプロパティを <code>ALTER PROPERTY GRAPH ... DROP</code> しようとすると、
    依存関係により拒否される。</li>
  <li><strong>準備文とキャッシュ無効化</strong>: <code>PREPARE</code> 済みの文があっても、
    <code>ALTER PROPERTY GRAPH</code> による定義変更は次回実行時に反映される。カタログ変更が
    プランキャッシュを無効化するためである。</li>
</ul>

<h2 id="sec-7-4">7.4　現在の実装上の制限</h2>
<p>
本実装（PostgreSQL 19beta1 の SQL/PGQ パッチ）には、パーサや書き換えロジックが明示的に
弾く未対応機能がいくつかある。主なものを挙げる。
</p>
<ul>
  <li><strong>量指定子</strong>（<code>-&gt;{1,2}</code> のような可変長パス）は未対応
    （<em>element pattern quantifier is not supported</em>）。</li>
  <li><strong>入れ子パスパターン</strong>（<code>PAREN_EXPR</code>）は未対応。</li>
  <li><strong>1 つの GRAPH_TABLE に複数のパスパターン</strong>（カンマ区切り）は未対応。</li>
  <li><strong>GRAPH_TABLE 内のサブクエリ</strong>は未対応
    （<em>subqueries within GRAPH_TABLE reference are not supported</em>）。</li>
  <li><strong>非局所の要素変数参照</strong>（要素 <code>WHERE</code> から他要素の参照）は不可。</li>
  <li><strong>隣接する頂点パターン</strong>や、辺で始まる／終わるパスは構文的に不正。</li>
  <li>同名変数の併合における<strong>ラベル式の論理積</strong>、および同名辺による
    <strong>頂点の再併合を伴うウォーク</strong>は未対応。</li>
</ul>

<div class="info"><strong>まとめ</strong>
SQL/PGQ のグラフ照会は、<code>GRAPH_TABLE</code> を<strong>辺-頂点等結合とパスの UNION</strong>へ
書き換えるという一点に集約されている。カタログ（第3章）が定義を保持し、解析変換（第4章）が
パターンを意味づけし、書き換え（第5・6章）がそれを普通の SQL に翻訳する。専用実行器を
持たないこの設計は、既存のプランナ・実行器・権限・依存関係の仕組みをそのまま活用できる
点で、PostgreSQL への機能追加として極めて理にかなっている。</div>
"""

CHAPTERS = [
    {
        "num": 1, "title": "プロパティグラフ概論",
        "desc": "SQL/PGQ とは何か、プロパティグラフの論理オブジェクトとしての性質、そしてクエリ処理パイプライン全体像を俯瞰する。",
        "sections": [
            ("sec-1-1", "1.1 SQL/PGQ とプロパティグラフモデル"),
            ("sec-1-2", "1.2 論理オブジェクトとしてのプロパティグラフ"),
            ("sec-1-3", "1.3 クエリ処理パイプライン全体像"),
        ],
        "body": CH1,
    },
    {
        "num": 2, "title": "グラフの定義: CREATE PROPERTY GRAPH",
        "desc": "構文・頂点/辺・KEY・SOURCE/DESTINATION・ラベルとプロパティ・一貫性チェック、そしてカタログ登録の流れを解説する。",
        "sections": [
            ("sec-2-1", "2.1 構文の全体像"),
            ("sec-2-2", "2.2 頂点・辺と KEY / SOURCE / DESTINATION"),
            ("sec-2-3", "2.3 ラベルとプロパティ"),
            ("sec-2-4", "2.4 一貫性チェック"),
            ("sec-2-5", "2.5 カタログへの登録"),
        ],
        "body": CH2,
    },
    {
        "num": 3, "title": "システムカタログ",
        "desc": "定義を格納する 5 つの pg_propgraph_* カタログの役割・列・索引と、pg_get_propgraphdef による復元を詳解する。",
        "sections": [
            ("sec-3-1", "3.1 カタログの全体像"),
            ("sec-3-2", "3.2 pg_propgraph_element"),
            ("sec-3-3", "3.3 label と element_label"),
            ("sec-3-4", "3.4 property と label_property"),
            ("sec-3-5", "3.5 pg_get_propgraphdef"),
        ],
        "body": CH3,
    },
    {
        "num": 4, "title": "GRAPH_TABLE の構文解析",
        "desc": "MATCH パターンの構文、RangeGraphTable/GraphPattern/GraphElementPattern のパースツリー、解析変換と参照解決を追う。",
        "sections": [
            ("sec-4-1", "4.1 GRAPH_TABLE 構文と MATCH パターン"),
            ("sec-4-2", "4.2 パースツリー"),
            ("sec-4-3", "4.3 解析変換の流れ"),
            ("sec-4-4", "4.4 変数・ラベル・プロパティ参照の解決"),
        ],
        "body": CH4,
    },
    {
        "num": 5, "title": "GRAPH_TABLE の書き換え",
        "desc": "RTE_GRAPH_TABLE をリレーショナルなサブクエリへ変換する中核。path_factor/path_element、パス列挙、クエリ生成を解剖する。",
        "sections": [
            ("sec-5-1", "5.1 書き換えの起点"),
            ("sec-5-2", "5.2 path_factor と path_element"),
            ("sec-5-3", "5.3 パスの列挙 (DFS)"),
            ("sec-5-4", "5.4 1 パスから 1 クエリを生成"),
        ],
        "body": CH5,
    },
    {
        "num": 6, "title": "複数パス・UNION・循環パターン",
        "desc": "ラベル選言による複数パスの UNION、辺-頂点結合条件の生成、双方向辺・循環パターン・空パスの扱いを掘り下げる。",
        "sections": [
            ("sec-6-1", "6.1 複数パスと UNION ALL"),
            ("sec-6-2", "6.2 辺-頂点リンク qual の生成"),
            ("sec-6-3", "6.3 双方向辺"),
            ("sec-6-4", "6.4 循環パターンと同一変数の併合"),
            ("sec-6-5", "6.5 空パスパターン"),
        ],
        "body": CH6,
    },
    {
        "num": 7, "title": "実践: 観察と制限事項",
        "desc": "myshop グラフの完全例、書き換え結果の観察方法、権限・ビュー・準備文との相互作用、そして現在の実装上の制限をまとめる。",
        "sections": [
            ("sec-7-1", "7.1 完全な例: myshop グラフ"),
            ("sec-7-2", "7.2 書き換え結果を観察する"),
            ("sec-7-3", "7.3 権限・ビュー・準備文との相互作用"),
            ("sec-7-4", "7.4 現在の実装上の制限"),
        ],
        "body": CH7,
    },
]
