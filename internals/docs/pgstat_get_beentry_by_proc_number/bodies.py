# -*- coding: utf-8 -*-
"""Chapter bodies for the pgstat_get_beentry_by_proc_number internals doc.

本文 HTML 中の `%%GH%%` は build.py が GitHub パーマリンクのベース URL に置換する。
"""

ch1 = r"""
<p>
  PostgreSQL の各バックエンドは、自分が「いま何をしているか」を共有メモリ上の
  <a href="%%GH%%/src/include/utils/backend_status.h#L98"><code>PgBackendStatus</code></a> エントリに公示している。
  <code>pg_stat_activity</code> をはじめとする <code>pg_stat_get_backend_*</code> 系の関数群は、
  この共有領域を読み取って一行ずつ値を返す。その「特定のバックエンドのエントリを一つ取り出す」という
  共通操作を一手に引き受けるのが、本ドキュメントで読み解く
  <a href="%%GH%%/src/backend/utils/activity/backend_status.c#L1162"><code>pgstat_get_beentry_by_proc_number()</code></a> である。
  本章では、この関数が属するバックエンドステータス機構の全体像と、引数となる <code>ProcNumber</code> の意味を概観する。
</p>

<div class="note"><strong>メモ</strong>バックエンドステータス機構（<code>backend_status.c</code>）は、
プロセスの「現在の活動」を即時に見せる仕組みであり、累積統計システム（<code>pgstat.c</code> 系）とは別物である。
両者はしばしば「pgstat」という接頭辞を共有するため混同されやすいが、本関数は前者に属する。</div>

<h2 id="sec-1-1">1.1　バックエンドの「現在の活動」を共有する仕組み</h2>
<p>
  個々のバックエンドは、状態が変わるたびに自分専用の <code>PgBackendStatus</code> エントリを更新する。
  PID・データベース OID・接続ユーザ・現在の状態（idle / active 等）・実行中のクエリ文字列・トランザクション開始時刻
  などがここに書き込まれる。これらのエントリは固定長配列
  <a href="%%GH%%/src/backend/utils/activity/backend_status.c#L52"><code>BackendStatusArray</code></a> として
  共有メモリ上に確保され、すべてのバックエンドから読み取れる。
</p>
<p>
  書き手は自分のエントリだけを更新し、読み手は配列全体を走査する。ロックを取らずにこの読み書きを成立させるため、
  各エントリには更新世代カウンタ <code>st_changecount</code> が置かれている（詳細は第3章）。
</p>
<figure>
  <pre class="mermaid">
flowchart TB
    subgraph SHM["共有メモリ"]
        direction TB
        BSA["BackendStatusArray[]<br/>PgBackendStatus の固定長配列"]
    end
    BE1["バックエンド A<br/>(ProcNumber=0)"] -->|"自分の活動を書き込む"| BSA
    BE2["バックエンド B<br/>(ProcNumber=1)"] -->|"自分の活動を書き込む"| BSA
    AUX["補助プロセス<br/>(checkpointer 等)"] -->|"書き込む"| BSA
    READER["読み手バックエンド<br/>pg_stat_activity を実行"] -->|"配列全体を読む"| BSA
  </pre>
  <figcaption>図 1.1: 各プロセスは自分のエントリを書き、読み手は配列全体を走査する</figcaption>
</figure>
<p>
  図 1.1 に示すように、読み手は「ある特定のバックエンドのエントリ」を頻繁に必要とする。
  その取り出しを担うのが本関数であり、引数として渡されるのが次節の <code>ProcNumber</code> である。
</p>

<h2 id="sec-1-2">1.2　ProcNumber — エントリを指すインデックス</h2>
<p>
  <a href="%%GH%%/src/include/storage/procnumber.h#L24"><code>ProcNumber</code></a> は単なる <code>int</code> の型エイリアスで、
  プロセスごとに割り当てられる 0 始まりの番号である。無効値は
  <a href="%%GH%%/src/include/storage/procnumber.h#L26"><code>INVALID_PROC_NUMBER</code></a>（= -1）で表す。
  重要なのは、<strong><code>BackendStatusArray</code> のインデックスがそのまま当該バックエンドの <code>ProcNumber</code> に一致する</strong>
  という設計である。<a href="%%GH%%/src/include/utils/backend_status.h#L98"><code>PgBackendStatus</code></a> の定義コメントも
  「構造体は ProcNumber に従って割り当てられる」と明記している。
</p>
<figure>
  <pre class="mermaid">
flowchart LR
    P0["ProcNumber 0"] --> S0["BackendStatusArray[0]"]
    P1["ProcNumber 1"] --> S1["BackendStatusArray[1]"]
    P2["ProcNumber 2"] --> S2["BackendStatusArray[2]"]
    PN["ProcNumber n"] --> SN["BackendStatusArray[n]"]
  </pre>
  <figcaption>図 1.2: ProcNumber は BackendStatusArray の添字そのものである</figcaption>
</figure>
<p>
  図 1.2 に示すように、ProcNumber が分かればエントリの位置は添字計算だけで定まる。
  ただし本関数が探索するのは生の共有配列ではなく、後述するローカルスナップショット（圧縮済みの配列）であるため、
  添字の直接参照ではなく二分探索を用いる（第4章）。配列の総スロット数は
  <a href="%%GH%%/src/backend/utils/activity/backend_status.c#L37"><code>NumBackendStatSlots</code></a>
  = <code>MaxBackends + NUM_AUXILIARY_PROCS</code> で、通常のバックエンドに加えて
  checkpointer などの補助プロセスのぶんも確保される。
</p>

<h2 id="sec-1-3">1.3　関数の役割と呼び出し階層</h2>
<p>
  本関数のシグネチャは次のとおりで、<code>backend_status.h</code> に宣言されている
  （<a href="%%GH%%/src/include/utils/backend_status.h#L334">L334</a>）。
</p>
<div class="example">
  <span class="example-label">宣言 (backend_status.h)</span>
  <pre><code>extern PgBackendStatus *pgstat_get_beentry_by_proc_number(ProcNumber procNumber);</code></pre>
</div>
<p>
  役割は単純で、「与えられた <code>ProcNumber</code> に対応する <code>PgBackendStatus</code> を返す。
  該当セッションが存在しなければ <code>NULL</code> を返す」である。ただしその内部では、
  共有メモリのローカルコピー作成（<a href="%%GH%%/src/backend/utils/activity/backend_status.c#L784"><code>pgstat_read_current_status()</code></a>）と、
  ローカル版を返す下請け関数（<a href="%%GH%%/src/backend/utils/activity/backend_status.c#L1188"><code>pgstat_get_local_beentry_by_proc_number()</code></a>）が連携する。
  全体像は図 1.3 のとおりである。
</p>
<figure>
  <pre class="mermaid">
flowchart TB
    SQL["SQL 関数<br/>pg_stat_get_backend_pid 等"] --> GBE["pgstat_get_beentry_by_proc_number()"]
    GBE --> GLBE["pgstat_get_local_beentry_by_proc_number()"]
    GLBE --> RCS["pgstat_read_current_status()<br/>共有 → ローカルへコピー"]
    GLBE --> BS["bsearch() で proc_number 検索"]
    GBE -->|"&amp;ret->backendStatus<br/>または NULL"| SQL
  </pre>
  <figcaption>図 1.3: SQL 関数から本関数を経て二分探索に至る呼び出し階層</figcaption>
</figure>
<p>
  次章では、この流れに登場する三つのデータ構造 — 共有メモリ上の <code>PgBackendStatus</code>、その配列
  <code>BackendStatusArray</code>、そしてローカルスナップショットを包む <code>LocalPgBackendStatus</code> — を順に見ていく。
</p>
"""

ch2 = r"""
<p>
  本関数を理解する鍵は、<strong>共有メモリ上の実体</strong>と<strong>トランザクションローカルのスナップショット</strong>という
  二層構造にある。本章では、活動エントリそのものである
  <a href="%%GH%%/src/include/utils/backend_status.h#L98"><code>PgBackendStatus</code></a>、
  それを並べた共有配列 <code>BackendStatusArray</code>、
  そしてローカルコピーに追加情報を足すラッパ
  <a href="%%GH%%/src/include/utils/backend_status.h#L249"><code>LocalPgBackendStatus</code></a> の三つを順に読む。
</p>

<h2 id="sec-2-1">2.1　PgBackendStatus — 共有メモリ上の活動エントリ</h2>
<p>
  <a href="%%GH%%/src/include/utils/backend_status.h#L98"><code>PgBackendStatus</code></a> は、一つのバックエンドの「現在の活動」を表す構造体である。
  主なフィールドを図 2.1 に示す。先頭の <code>st_changecount</code> は無ロック読み取りのための世代カウンタ、
  <code>st_procpid</code> は当該スロットが使用中か否かを示す要となるフィールドで、
  <strong><code>st_procpid &gt; 0</code> のときのみエントリは有効</strong>である。
</p>
<figure>
  <pre class="mermaid">
classDiagram
    class PgBackendStatus {
        int st_changecount
        int st_procpid
        BackendType st_backendType
        TimestampTz st_proc_start_timestamp
        TimestampTz st_xact_start_timestamp
        Oid st_databaseid
        Oid st_userid
        char* st_clienthostname
        BackendState st_state
        char* st_appname
        char* st_activity_raw
        int64 st_query_id
        int64 st_plan_id
    }
  </pre>
  <figcaption>図 2.1: PgBackendStatus の主なフィールド（抜粋）</figcaption>
</figure>
<p>
  <code>st_activity_raw</code> はクエリ文字列を保持するが、書き込み頻度を優先してマルチバイト文字の途中で
  切り詰められている可能性がある。表示側で正しく整形するため
  <a href="%%GH%%/src/backend/utils/activity/backend_status.c#L1254"><code>pgstat_clip_activity()</code></a> を通す決まりになっている。
  なお <code>st_clienthostname</code> や <code>st_appname</code> はポインタ型であり、実体は別の共有バッファに置かれている点に注意する
  （この事実は第3章のコピー処理で効いてくる）。
</p>

<h2 id="sec-2-2">2.2　BackendStatusArray と NumBackendStatSlots</h2>
<p>
  これらのエントリは固定長配列
  <a href="%%GH%%/src/backend/utils/activity/backend_status.c#L52"><code>BackendStatusArray</code></a> として共有メモリに確保される。
  要素数は <a href="%%GH%%/src/backend/utils/activity/backend_status.c#L37"><code>NumBackendStatSlots</code></a> で、定義は次のとおり。
</p>
<div class="example">
  <span class="example-label">定義 (backend_status.c)</span>
  <pre><code>#define NumBackendStatSlots (MaxBackends + NUM_AUXILIARY_PROCS)</code></pre>
</div>
<p>
  通常のバックエンドぶん（<code>MaxBackends</code>）に加え、checkpointer・background writer・WAL writer といった
  補助プロセスぶん（<a href="%%GH%%/src/include/storage/proc.h#L533"><code>NUM_AUXILIARY_PROCS</code></a>）が上乗せされる。
  1.2 節で述べたとおり、配列の添字は当該プロセスの <code>ProcNumber</code> に一致する。
  したがって配列は ProcNumber 昇順に並んでおり、この性質が後の二分探索を可能にする。
</p>

<h2 id="sec-2-3">2.3　LocalPgBackendStatus — ローカルスナップショット</h2>
<p>
  本関数が実際に返すのは、共有配列そのものへのポインタではなく、トランザクションローカルにコピーした
  スナップショットの一要素である。そのコピーを表すのが
  <a href="%%GH%%/src/include/utils/backend_status.h#L249"><code>LocalPgBackendStatus</code></a> で、
  先頭メンバに <code>PgBackendStatus</code> を丸ごと持ち、さらにローカルで計算した追加情報を足している。
</p>
<figure>
  <pre class="mermaid">
classDiagram
    class LocalPgBackendStatus {
        PgBackendStatus backendStatus
        ProcNumber proc_number
        TransactionId backend_xid
        TransactionId backend_xmin
        int backend_subxact_count
        bool backend_subxact_overflowed
    }
    LocalPgBackendStatus o-- PgBackendStatus : backendStatus
  </pre>
  <figcaption>図 2.2: LocalPgBackendStatus は PgBackendStatus を包み、proc_number と XID 情報を足す</figcaption>
</figure>
<p>
  図 2.2 に示すように、ヘッダのコメントは、共有メモリの構造体に手を加えずに値を追加できるよう、あえてローカル側を別構造体にしている、
  と説明する。追加フィールドのうち <code>backend_xid</code> / <code>backend_xmin</code> /
  <code>backend_subxact_count</code> / <code>backend_subxact_overflowed</code> は、共有エントリには無い情報で、
  スナップショット構築時に <code>ProcArray</code> から別途取得される（第3章）。
  そして本関数の探索キーとなる <code>proc_number</code> もこの構造体に保持される。
</p>
<div class="info"><strong>関連</strong>追加情報の取得には
<a href="%%GH%%/src/backend/storage/ipc/procarray.c#L3112"><code>ProcNumberGetTransactionIds()</code></a> が使われる。
このため <code>local</code> 版（<code>pgstat_get_local_beentry_by_proc_number()</code>）は XID 情報まで必要とする呼び出し側に向く。</div>
"""

ch3 = r"""
<p>
  本関数は探索の前に必ず
  <a href="%%GH%%/src/backend/utils/activity/backend_status.c#L784"><code>pgstat_read_current_status()</code></a> を呼ぶ。
  この関数は共有メモリの <code>BackendStatusArray</code> をトランザクションローカルへコピーし、
  有効なエントリだけを詰め直した <code>localBackendStatusTable</code> を作る。
  本章では、このコピーが「いつ」「どのように安全に」行われ、なぜ結果が <code>proc_number</code> 昇順になるのかを読む。
</p>

<h2 id="sec-3-1">3.1　トランザクション内で一度だけコピーする</h2>
<p>
  <a href="%%GH%%/src/backend/utils/activity/backend_status.c#L784"><code>pgstat_read_current_status()</code></a> は冒頭で
  <code>localBackendStatusTable</code> が既に存在すれば即座に戻る。
</p>
<div class="example">
  <span class="example-label">先頭のガード (backend_status.c)</span>
  <pre><code>if (localBackendStatusTable)
    return;                  /* already done */</code></pre>
</div>
<p>
  つまりスナップショットはトランザクション（厳密にはスナップショットの寿命）ごとに一度だけ作られ、
  同一トランザクション内で本関数を何度呼んでも同じ静止画を見ることになる。
  このローカル表は専用メモリコンテキスト <code>backendStatusSnapContext</code> 上に確保され、
  トランザクションの終了時に
  <a href="%%GH%%/src/backend/utils/activity/backend_status.c#L501"><code>pgstat_clear_backend_activity_snapshot()</code></a> が
  コンテキストを破棄して <code>localBackendStatusTable</code> を <code>NULL</code> に戻す。
  次回の要求で改めて新しいスナップショットが読み直される。
</p>

<h2 id="sec-3-2">3.2　changecount プロトコルによる無ロック読み取り</h2>
<p>
  コピーはロックを取らずに行われる。書き手は自分のエントリを変更する前後で <code>st_changecount</code> を
  インクリメントし、読み手はコピーの前後でこのカウンタを読んで突き合わせる。
  前後の値が一致し、かつ偶数であればコピーは整合していると判断できる。
  奇数や不一致なら、書き込み途中に出くわしたとみなして読み直す。
  判定は <a href="%%GH%%/src/include/utils/backend_status.h#L236"><code>pgstat_read_activity_complete()</code></a> マクロが担う。
</p>
<figure>
  <pre class="mermaid">
sequenceDiagram
    participant R as 読み手 (read_current_status)
    participant E as 共有エントリ (PgBackendStatus)
    R->>E: before = st_changecount (read barrier)
    R->>E: エントリをローカルへ memcpy
    R->>E: after = st_changecount (read barrier)
    alt before == after かつ 偶数
        R->>R: コピー確定 → 次のエントリへ
    else 不一致 または 奇数
        R->>R: CHECK_FOR_INTERRUPTS 後にやり直し
    end
  </pre>
  <figcaption>図 3.1: st_changecount による楽観的・無ロックのエントリ読み取り</figcaption>
</figure>
<p>
  図 3.1 のループは <code>for (;;)</code> で書かれ、確定するまで繰り返される。
  無限ループに陥らないよう、各反復で <code>CHECK_FOR_INTERRUPTS()</code> を挟む。
  ポインタ型フィールド（<code>st_appname</code> 等）は <code>memcpy</code> 後に <code>strcpy</code> で別バッファへ複写し、
  ローカル側のポインタをローカルバッファへ向け直す。文字列末尾には必ず <code>\0</code> があるため、
  並行更新中でも <code>strcpy</code> は安全に終端する、とソースコメントは述べる。
</p>

<h2 id="sec-3-3">3.3　有効エントリの抽出と proc_number 順の保証</h2>
<p>
  共有配列の全スロット <code>0 .. NumBackendStatSlots-1</code> を走査するが、
  ローカル表に取り込むのは <code>st_procpid &gt; 0</code> の有効エントリだけである。
  取り込む際、そのスロットの添字 <code>procNumber</code> をそのまま <code>localentry-&gt;proc_number</code> に記録し、
  併せて <a href="%%GH%%/src/backend/storage/ipc/procarray.c#L3112"><code>ProcNumberGetTransactionIds()</code></a> で
  XID・xmin・サブトランザクション情報を取得して埋める。
</p>
<div class="example">
  <span class="example-label">有効エントリの取り込み (backend_status.c)</span>
  <pre><code>/* Only valid entries get included into the local array */
if (localentry-&gt;backendStatus.st_procpid &gt; 0)
{
    /*
     * The BackendStatusArray index is exactly the ProcNumber of the
     * source backend.  Note that this means localBackendStatusTable
     * is in order by proc_number.
     */
    localentry-&gt;proc_number = procNumber;
    ProcNumberGetTransactionIds(procNumber, ...);
    localentry++;
    localNumBackends++;
}</code></pre>
</div>
<p>
  ここがソースコードで最も重要なコメントである。元配列の添字が ProcNumber に等しく、
  走査を添字昇順で行うため、有効エントリだけを前詰めしてできた <code>localBackendStatusTable</code> も
  自然と <strong><code>proc_number</code> 昇順</strong>になる。図 3.2 にこの圧縮の様子を示す。
</p>
<figure>
  <pre class="mermaid">
flowchart LR
    subgraph SRC["BackendStatusArray (疎)"]
        A0["[0] pid&gt;0 PN=0"]
        A1["[1] pid=0 空き"]
        A2["[2] pid&gt;0 PN=2"]
        A3["[3] pid&gt;0 PN=3"]
        A4["[4] pid=0 空き"]
    end
    subgraph DST["localBackendStatusTable (密)"]
        B0["proc_number=0"]
        B1["proc_number=2"]
        B2["proc_number=3"]
    end
    A0 --> B0
    A2 --> B1
    A3 --> B2
  </pre>
  <figcaption>図 3.2: 空きスロットを除いて前詰めしても proc_number 昇順は保たれる</figcaption>
</figure>
<p>
  この昇順という不変条件が、次章の二分探索（<code>bsearch</code>）の前提となる。
  有効エントリ数は <code>localNumBackends</code> に記録され、<code>bsearch</code> の要素数として使われる。
</p>
"""

ch4 = r"""
<p>
  ここまでで、探索対象である <code>proc_number</code> 昇順のローカル表が用意できた。本章では、その表から
  目的のエントリを取り出す本体三関数 —
  <a href="%%GH%%/src/backend/utils/activity/backend_status.c#L1162"><code>pgstat_get_beentry_by_proc_number()</code></a>、
  <a href="%%GH%%/src/backend/utils/activity/backend_status.c#L1188"><code>pgstat_get_local_beentry_by_proc_number()</code></a>、
  比較関数 <a href="%%GH%%/src/backend/utils/activity/backend_status.c#L1139"><code>cmp_lbestatus()</code></a> —
  を読み、添字版 <code>by_index</code> との違いを整理する。
</p>

<h2 id="sec-4-1">4.1　pgstat_get_beentry_by_proc_number</h2>
<p>
  本関数の実装はごく短い。下請けの <code>local</code> 版を呼び、結果があればその先頭メンバ
  <code>backendStatus</code> へのポインタを返すだけである。
</p>
<div class="example">
  <span class="example-label">実装 (backend_status.c)</span>
  <pre><code>PgBackendStatus *
pgstat_get_beentry_by_proc_number(ProcNumber procNumber)
{
    LocalPgBackendStatus *ret = pgstat_get_local_beentry_by_proc_number(procNumber);

    if (ret)
        return &amp;ret-&gt;backendStatus;

    return NULL;
}</code></pre>
</div>
<p>
  追加の XID 情報まで要らず、共有エントリ相当の値だけが欲しい呼び出し側はこちらを使う。
  XID・xmin・サブトランザクション情報まで要る呼び出し側は、<code>local</code> 版を直接呼ぶ（5.1 節参照）。
</p>

<h2 id="sec-4-2">4.2　pgstat_get_local_beentry_by_proc_number と bsearch</h2>
<p>
  実際の探索を行うのが
  <a href="%%GH%%/src/backend/utils/activity/backend_status.c#L1188"><code>pgstat_get_local_beentry_by_proc_number()</code></a> である。
  まずスナップショットを用意し、検索キーの <code>proc_number</code> を立て、標準ライブラリの <code>bsearch()</code> で
  ローカル表を二分探索する。
</p>
<div class="example">
  <span class="example-label">実装 (backend_status.c)</span>
  <pre><code>LocalPgBackendStatus *
pgstat_get_local_beentry_by_proc_number(ProcNumber procNumber)
{
    LocalPgBackendStatus key;

    pgstat_read_current_status();

    /*
     * Since the localBackendStatusTable is in order by proc_number, we can
     * use bsearch() to search it efficiently.
     */
    key.proc_number = procNumber;
    return bsearch(&amp;key, localBackendStatusTable, localNumBackends,
                   sizeof(LocalPgBackendStatus), cmp_lbestatus);
}</code></pre>
</div>
<p>
  比較関数 <a href="%%GH%%/src/backend/utils/activity/backend_status.c#L1139"><code>cmp_lbestatus()</code></a> は、
  二つの要素の <code>proc_number</code> の差を返すだけの素直な実装である。
</p>
<div class="example">
  <span class="example-label">比較関数 (backend_status.c)</span>
  <pre><code>static int
cmp_lbestatus(const void *a, const void *b)
{
    const LocalPgBackendStatus *lbestatus1 = (const LocalPgBackendStatus *) a;
    const LocalPgBackendStatus *lbestatus2 = (const LocalPgBackendStatus *) b;

    return lbestatus1-&gt;proc_number - lbestatus2-&gt;proc_number;
}</code></pre>
</div>
<figure>
  <pre class="mermaid">
flowchart TB
    START["pgstat_get_local_beentry_by_proc_number(PN)"] --> RCS["pgstat_read_current_status()<br/>(未取得ならスナップショット作成)"]
    RCS --> KEY["key.proc_number = PN"]
    KEY --> BS["bsearch(key, localBackendStatusTable,<br/>localNumBackends, cmp_lbestatus)"]
    BS --> HIT{"一致あり?"}
    HIT -->|"はい"| RET["LocalPgBackendStatus* を返す"]
    HIT -->|"いいえ"| NUL["NULL を返す"]
  </pre>
  <figcaption>図 4.1: スナップショット取得から二分探索までの流れ</figcaption>
</figure>
<p>
  図 4.1 のとおり、3.3 節で保証した昇順のおかげで線形走査ではなく <code>O(log n)</code> の二分探索が使える。
  該当 <code>ProcNumber</code> のセッションが存在しなければ <code>bsearch</code> は <code>NULL</code> を返し、
  それがそのまま上位へ伝播する。
</p>

<h2 id="sec-4-3">4.3　by_index との違い</h2>
<p>
  紛らわしい兄弟関数に
  <a href="%%GH%%/src/backend/utils/activity/backend_status.c#L1219"><code>pgstat_get_local_beentry_by_index()</code></a> がある。
  名前は似ているが、引数の意味がまったく異なる。
</p>
<figure>
  <pre class="mermaid">
flowchart LR
    subgraph BY_PN["by_proc_number"]
        K1["引数 = ProcNumber"]
        K1 --> M1["bsearch で proc_number 一致を探す"]
    end
    subgraph BY_IDX["by_index"]
        K2["引数 = 1始まりの配列添字"]
        K2 --> M2["localBackendStatusTable[idx-1] を直接返す"]
    end
  </pre>
  <figcaption>図 4.2: by_proc_number は ProcNumber で探索、by_index は 1 始まり添字で直接参照</figcaption>
</figure>
<p>
  図 4.2 に示すように、<code>by_index</code> はローカル表の <strong>1 始まりの添字</strong>を受け取り、範囲外なら <code>NULL</code> を返す。
  全バックエンドを <code>1 .. pgstat_fetch_stat_numbackends()</code> で順に列挙する
  <code>pg_stat_get_activity</code> のような用途に向く。一方 <code>by_proc_number</code> は、
  特定の ProcNumber を狙い撃ちで引くための関数である。両者のヘッダコメントは互いに
  「これは <code>by_index</code> とは違う」「これは <code>by_proc_number</code> とは違う」と明示し合っている。
</p>
"""

ch5 = r"""
<p>
  本関数は内部 API であり、最終的には SQL から呼べる <code>pg_stat_get_backend_*</code> 系関数を支える。
  本章では <a href="%%GH%%/src/backend/utils/adt/pgstatfuncs.c"><code>pgstatfuncs.c</code></a> での具体的な呼び出しパターンと、
  見落としやすい権限チェックの責務、そして実際に値を観察する方法を示す。
</p>

<h2 id="sec-5-1">5.1　pgstatfuncs.c での呼び出しパターン</h2>
<p>
  最も典型的なのは
  <a href="%%GH%%/src/backend/utils/adt/pgstatfuncs.c#L722"><code>pg_stat_get_backend_pid()</code></a> で、
  引数の ProcNumber でエントリを引き、無ければ <code>NULL</code>、あれば該当フィールドを返す。
</p>
<div class="example">
  <span class="example-label">実装 (pgstatfuncs.c)</span>
  <pre><code>Datum
pg_stat_get_backend_pid(PG_FUNCTION_ARGS)
{
    int32       procNumber = PG_GETARG_INT32(0);
    PgBackendStatus *beentry;

    if ((beentry = pgstat_get_beentry_by_proc_number(procNumber)) == NULL)
        PG_RETURN_NULL();

    PG_RETURN_INT32(beentry-&gt;st_procpid);
}</code></pre>
</div>
<p>
  同じ骨格で <a href="%%GH%%/src/backend/utils/adt/pgstatfuncs.c#L735"><code>pg_stat_get_backend_dbid()</code></a>、
  <a href="%%GH%%/src/backend/utils/adt/pgstatfuncs.c#L748"><code>pg_stat_get_backend_userid()</code></a>、
  <a href="%%GH%%/src/backend/utils/adt/pgstatfuncs.c#L796"><code>pg_stat_get_backend_activity()</code></a> などが実装される。
  返したいフィールドが <code>st_databaseid</code> や <code>st_userid</code> に変わるだけである。図 5.1 にこの呼び出しの流れを示す。
  一方、サブトランザクション情報のように <code>LocalPgBackendStatus</code> の追加フィールドが必要な
  <a href="%%GH%%/src/backend/utils/adt/pgstatfuncs.c#L760"><code>pg_stat_get_backend_subxact()</code></a> は、
  <code>local</code> 版 <code>pgstat_get_local_beentry_by_proc_number()</code> を直接呼ぶ。
</p>
<figure>
  <pre class="mermaid">
sequenceDiagram
    participant U as ユーザ (SQL)
    participant F as pg_stat_get_backend_pid()
    participant G as pgstat_get_beentry_by_proc_number()
    participant L as localBackendStatusTable
    U->>F: SELECT ... (procNumber)
    F->>G: procNumber
    G->>L: bsearch (初回はスナップショット作成)
    L-->>G: PgBackendStatus* または NULL
    G-->>F: 同上
    F-->>U: st_procpid または NULL
  </pre>
  <figcaption>図 5.1: SQL 関数から本関数を経て値が返るまで</figcaption>
</figure>

<h2 id="sec-5-2">5.2　権限チェックは呼び出し側の責任</h2>
<p>
  本関数のヘッダコメントは <strong>「呼び出し側が、このユーザに情報（特にクエリ文字列）を見せてよいか確認する責任を負う」</strong>
  と明記している。つまり本関数自体は権限を一切判定しない。判定は SQL 関数側で、マクロ
  <a href="%%GH%%/src/backend/utils/adt/pgstatfuncs.c#L39"><code>HAS_PGSTAT_PERMISSIONS()</code></a> を使って行う。
</p>
<div class="example">
  <span class="example-label">権限マクロ (pgstatfuncs.c)</span>
  <pre><code>#define HAS_PGSTAT_PERMISSIONS(role) \
    (has_privs_of_role(GetUserId(), ROLE_PG_READ_ALL_STATS) || \
     has_privs_of_role(GetUserId(), role))</code></pre>
</div>
<p>
  たとえば <code>pg_stat_get_backend_activity()</code> は、エントリを引いた後に
  <code>HAS_PGSTAT_PERMISSIONS(beentry-&gt;st_userid)</code> を確認し、権限が無ければ
  <code>&lt;insufficient privilege&gt;</code> を返す。<code>pg_read_all_stats</code> ロールを持つか、
  対象バックエンドの所有ユーザ自身であれば、クエリ文字列まで閲覧できる。
</p>
<div class="warn"><strong>注意</strong>本関数を新しい内部コードから直接利用する場合、
権限チェックを忘れると他ユーザのクエリ文字列を露出させうる。チェックは利用側で必ず行う。</div>

<h2 id="sec-5-3">5.3　実行例で観察する</h2>
<p>
  これらの SQL 関数は <code>ProcNumber</code> を引数に取る。<code>pg_stat_activity</code> から目的のバックエンドの
  ProcNumber を得て、個別関数で値を引いてみる。
</p>
<div class="example">
  <span class="example-label">SQL</span>
  <pre><code>-- いま動いているバックエンドの ProcNumber を確認する
SELECT pid, backend_type, state
FROM pg_stat_activity
WHERE backend_type = 'client backend';</code></pre>
</div>
<div class="example">
  <span class="example-label">SQL</span>
  <pre><code>-- ProcNumber 2 のバックエンドの PID・DB・ユーザ・クエリを引く
SELECT pg_stat_get_backend_pid(2)      AS pid,
       pg_stat_get_backend_dbid(2)     AS dbid,
       pg_stat_get_backend_userid(2)   AS userid,
       pg_stat_get_backend_activity(2) AS query;</code></pre>
</div>
<div class="example">
  <span class="example-label">実行結果（例）</span>
  <pre><code>  pid  | dbid  | userid |              query
-------+-------+--------+----------------------------------
 48213 | 16384 |     10 | SELECT pg_stat_get_backend_pid(2) ...</code></pre>
</div>
<p>
  存在しない ProcNumber を渡すと、<code>bsearch</code> が空振りし各関数は <code>NULL</code>（活動文字列は
  <code>&lt;backend information not available&gt;</code>）を返す。
  同一トランザクション内では 3.1 節のスナップショットが固定されるため、複数関数を一度に呼んでも
  矛盾のない同一時点の値が得られる。
</p>
"""

ch6 = r"""
<p>
  最終章では、本関数を使う／読むうえで押さえておきたい振る舞いを整理する。
  スナップショットの寿命、補助プロセスや無効な ProcNumber の扱い、そして全体のまとめである。
</p>

<h2 id="sec-6-1">6.1　スナップショットの寿命</h2>
<p>
  3.1 節で見たとおり、本関数が参照するローカル表はトランザクション内で一度だけ作られ、
  その後は同じ静止画を返し続ける。これは「同じクエリ内では各バックエンドの状態が一貫して見える」という
  利点である反面、<strong>リアルタイムの最新値ではない</strong>ことを意味する。
  本当にいまこの瞬間の活動を共有配列から直接読みたい特殊用途（デッドロック報告など）には、
  スナップショットを介さない
  <a href="%%GH%%/src/backend/utils/activity/backend_status.c#L961"><code>pgstat_get_backend_current_activity()</code></a> が別途用意されている。
  両者の使い分けを図 6.1 に示す。
</p>
<figure>
  <pre class="mermaid">
flowchart TB
    NEED{"必要なのは?"}
    NEED -->|"一貫したスナップショット<br/>(pg_stat_activity 等)"| SNAP["pgstat_get_beentry_by_proc_number<br/>→ ローカル表 (静止画)"]
    NEED -->|"いま現在の生の値<br/>(デッドロック報告)"| LIVE["pgstat_get_backend_current_activity<br/>→ 共有配列を直接走査"]
  </pre>
  <figcaption>図 6.1: スナップショット経由の本関数と、生の共有配列を読む関数の使い分け</figcaption>
</figure>

<h2 id="sec-6-2">6.2　補助プロセスと無効な ProcNumber</h2>
<p>
  <code>NumBackendStatSlots</code> には補助プロセスぶんのスロットも含まれるため（2.2 節）、
  本関数は client backend だけでなく checkpointer などのエントリも引ける。
  渡した ProcNumber に対応するスロットが未使用（<code>st_procpid == 0</code>）であれば、
  そのスロットはそもそもローカル表に取り込まれていないため（3.3 節）、<code>bsearch</code> は一致を見つけられず
  <code>NULL</code> を返す。<code>INVALID_PROC_NUMBER</code>（-1）のような範囲外の値でも、
  単に該当なしとして <code>NULL</code> が返るだけで、エラーにはならない。
</p>
<div class="note"><strong>メモ</strong>呼び出し側は戻り値の <code>NULL</code> を必ず確認する必要がある。
<code>pgstatfuncs.c</code> の各関数はいずれも <code>== NULL</code> を最初に判定し、<code>PG_RETURN_NULL()</code> や
代替文字列でフォールバックしている。</div>

<h2 id="sec-6-3">6.3　まとめ</h2>
<p>
  本ドキュメントで読み解いた要点を整理する。
</p>
<ul>
  <li><a href="%%GH%%/src/backend/utils/activity/backend_status.c#L1162"><code>pgstat_get_beentry_by_proc_number()</code></a> は、
      <code>ProcNumber</code> から <code>PgBackendStatus</code> を引く内部 API で、<code>pg_stat_get_backend_*</code> 系関数の土台である。</li>
  <li>探索対象は共有メモリの生配列ではなく、トランザクションローカルに作られる
      <code>localBackendStatusTable</code>（<code>LocalPgBackendStatus</code> の配列）である。</li>
  <li>このローカル表は <code>BackendStatusArray</code> の添字（= ProcNumber）昇順を引き継ぐため、
      <code>bsearch()</code> による <code>O(log n)</code> 検索が成立する。</li>
  <li>スナップショット構築は <code>st_changecount</code> プロトコルで無ロックに行われ、トランザクション内で一度だけ実行される。</li>
  <li>権限チェックは本関数の責務ではなく、呼び出し側が <code>HAS_PGSTAT_PERMISSIONS()</code> で行う。</li>
</ul>
<p>
  小さな関数だが、その背後には「共有メモリの無ロック読み取り」「ローカルスナップショットの一貫性」
  「ProcNumber を添字とする設計」という、PostgreSQL のバックエンドステータス機構の要が凝縮されている。
</p>
"""
