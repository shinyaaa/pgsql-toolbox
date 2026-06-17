# -*- coding: utf-8 -*-
"""Chapter bodies for the PGPROC internals documentation."""

GH = "https://github.com/shinyaaa/postgres/blob/0131e8fc508ff8e10a6797bfe8043a0b9d34b30b"


def L(path, line, text):
    """Code pointer anchor."""
    return '<a href="%s/%s#L%d"><code>%s</code></a>' % (GH, path, line, text)


def F(path, text):
    return '<a href="%s/%s"><code>%s</code></a>' % (GH, path, text)


PROC_H = "src/include/storage/proc.h"
PROC_C = "src/backend/storage/lmgr/proc.c"
PARRAY_C = "src/backend/storage/ipc/procarray.c"
PNUM_H = "src/include/storage/procnumber.h"

# ===========================================================================
CH1 = """
<p>
  PostgreSQL はマルチプロセス構成のデータベースである。クライアント接続ごとに
  バックエンドプロセスが 1 つ割り当てられ、さらにチェックポインタや WAL ライタ、
  自動バキュームワーカーといった補助プロセスが並走する。これらのプロセスは
  独立したアドレス空間を持つが、トランザクションの可視性判定やロックの調停を
  行うには、互いの状態を覗き合う必要がある。その「覗き合うための窓口」が
  本章で扱う %s 構造体である。
</p>

<h2 id="sec-1-1">1.1　PGPROCの役割</h2>
<p>
  %s は <strong>プロセスごとの共有メモリ上のデータ構造（per-process shared
  memory data structure）</strong>である。各プロセスは自分専用の PGPROC を 1 つ持ち、
  そこに「現在実行中のトランザクション ID」「スナップショットの xmin」「待機中の
  ロック」「ステータスフラグ」などを書き込む。これらは共有メモリ上にあるため、
  他のプロセスからも読み取れる。つまり PGPROC は、各プロセスが自分の状態を
  クラスタ全体へ<strong>広告（advertise）</strong>するための掲示板として働く。
</p>
<p>
  proc.h 冒頭のコメントはこの構造体を端的にこう説明している。「各バックエンドは
  共有メモリ中に PGPROC 構造体を持つ。また、新しいバックエンドに再割り当てされる
  ために現在未使用の PGPROC 構造体のリストも存在する」。この二点 ―
  <em>プロセスと一対一で対応すること</em>と<em>使い回されること</em> ―
  が PGPROC の本質である。
</p>

<figure>
  <pre class="mermaid">
flowchart LR
    subgraph procs["プロセス (独立アドレス空間)"]
        BE1["バックエンド A"]
        BE2["バックエンド B"]
        CKPT["チェックポインタ"]
    end
    subgraph shmem["共有メモリ"]
        P1["PGPROC[0]"]
        P2["PGPROC[1]"]
        P3["PGPROC[k]"]
    end
    BE1 -->|MyProc| P1
    BE2 -->|MyProc| P2
    CKPT -->|MyProc| P3
    BE2 -.読み取り.-> P1
    CKPT -.読み取り.-> P1
  </pre>
  <figcaption>図 1.1: 各プロセスは自分の PGPROC へ状態を書き込み、他プロセスはそれを読み取る</figcaption>
</figure>

<p>
  図 1.1 に示すように、各プロセスは <code>MyProc</code> ポインタを通じて自分の
  PGPROC を更新する。一方で、スナップショットを取得するバックエンドや可視性を
  判定する処理は、全プロセスの PGPROC（正確には後述する密な配列）を走査して
  「いま走っているトランザクション」を把握する。
</p>

<h2 id="sec-1-2">1.2　MyProc と ProcNumber</h2>
<p>
  各プロセスは、自分の PGPROC を指すグローバル変数 %s を持つ。バックエンドが
  起動して PGPROC を確保すると、以後はこの <code>MyProc-&gt;xid</code> のように
  自分の状態へアクセスする。自分自身のフィールドの多くはロックなしで読み書き
  できる点が、後述する性能設計の要になっている。
</p>
<p>
  PGPROC の配列上の位置は %s 型（実体は <code>int</code>）で表現される。
  これは「アクティブなバックエンドまたは補助プロセスを一意に識別する」番号で、
  0 から始まる。プロセスと PGPROC を相互変換するマクロが proc.h に定義されている。
</p>

<div class="example">
  <span class="example-label">proc.h — ProcNumber と PGPROC の相互変換</span>
  <pre><code>#define GetPGProcByNumber(n)    (&amp;ProcGlobal-&gt;allProcs[(n)])
#define GetNumberFromPGProc(proc) ((proc) - &amp;ProcGlobal-&gt;allProcs[0])</code></pre>
</div>

<p>
  %s が示すとおり、ProcNumber は単に <code>allProcs</code> 配列の添字に過ぎない。
  自分の番号は <code>MyProcNumber</code> に保持され、PGPROC 確保時に
  <code>GetNumberFromPGProc(MyProc)</code> で求められる。ProcNumber は
  プロセス終了後に別プロセスへ再利用される点に注意が必要である。
</p>
<div class="note"><strong>メモ</strong>ProcNumber は inval.c がメッセージ中に 3 バイト符号付き整数として
格納する都合上、2<sup>23</sup>-1 を超えられないという制約がある（%s）。</div>

<h2 id="sec-1-3">1.3　PGPROC を持つプロセスの種類</h2>
<p>
  PGPROC は通常のバックエンドだけが持つわけではない。%s のコメントによれば、
  確保すべき PGPROC には <strong>6 つの用途（consumer）</strong>がある。各 PGPROC は
  いずれか一つの用途に専属し、グループ間を移動しない。
</p>

<figure>
  <pre class="mermaid">
flowchart TB
    TOTAL["TotalProcs 個の PGPROC"]
    TOTAL --> A["(1) 通常バックエンド<br/>MaxConnections"]
    TOTAL --> B["(2) autovacuum + 特殊ワーカー"]
    TOTAL --> C["(3) バックグラウンドワーカー"]
    TOTAL --> D["(4) WAL センダ"]
    TOTAL --> E["(5) 補助プロセス<br/>NUM_AUXILIARY_PROCS"]
    TOTAL --> F["(6) プリペアドトランザクション<br/>max_prepared_xacts"]
  </pre>
  <figcaption>図 1.2: PGPROC を消費する 6 つの用途</figcaption>
</figure>

<p>
  図 1.2 のうち (1)〜(4) は「フルバックエンド」（トランザクションを実行でき、
  ヘビーウェイトロックを取得できる）であり、専用のフリーリストから割り当てられる。
  (5) の補助プロセス（バックグラウンドライタ、チェックポインタ、WAL ライタ、
  WAL サマライザ、アーカイバ、起動プロセス、WAL レシーバ、I/O ワーカー）は
  トランザクションを実行しないため数が固定で、フリーリストを使わず線形探索で
  割り当てられる。(6) のプリペアドトランザクションは、twophase.c が用意する
  <strong>ダミー PGPROC</strong> である。
</p>
<div class="info"><strong>関連</strong>ダミー PGPROC は <code>pid == 0</code> であることで実プロセスと区別できる。
これは準備済みトランザクションを「まだ走っているもの」として ProcArray に
見せかけ、ロック保持を正しく表示するための仕掛けである。詳細は
<a href="ch04.html">第4章</a>で扱う。</div>
""" % (
    L(PROC_H, 184, "PGPROC"),
    L(PROC_H, 184, "PGPROC"),
    L(PROC_H, 388, "MyProc"),
    L(PNUM_H, 24, "ProcNumber"),
    L(PROC_H, 510, "GetPGProcByNumber()"),
    F(PNUM_H, "procnumber.h"),
    L(PROC_C, 147, "ProcGlobalShmemRequest()"),
)

# ===========================================================================
CH2 = """
<p>
  本章では %s 構造体の主要フィールドを、ソース上のコメント区切りに沿って
  カテゴリ別に読み解く。PGPROC は性能のためキャッシュライン境界に整列
  （<code>alignas(PG_CACHE_LINE_SIZE)</code>）されており、フィールドは
  「バックエンド識別」「トランザクションとスナップショット」「プロセス間
  シグナリング」「LWLock 待機」「ロックマネージャ」「同期レプリケーション」
  「グループ処理」「ステータス報告」のブロックに整理されている。
</p>

<figure>
  <pre class="mermaid">
classDiagram
    class PGPROC {
        +int pid
        +BackendType backendType
        +Oid databaseId
        +Oid roleId
        +int pgxactoff
        +uint8 statusFlags
        +VirtualTransactionId vxid
        +TransactionId xid
        +TransactionId xmin
        +XidCacheStatus subxidStatus
        +XidCache subxids
        +Latch procLatch
        +PGSemaphore sem
        +LOCK waitLock
        +PGPROC lockGroupLeader
        +XLogRecPtr waitLSN
    }
  </pre>
  <figcaption>図 2.1: PGPROC の代表的フィールド（抜粋）</figcaption>
</figure>

<h2 id="sec-2-1">2.1　バックエンドの識別情報</h2>
<p>
  図 2.1 の上半分は、起動後ほとんど変化しない識別情報である。
  <code>pid</code> はプロセス ID（プリペアドトランザクションのダミーでは 0）、
  <code>backendType</code> はプロセス種別を表す。<code>databaseId</code> と
  <code>roleId</code> は接続中のデータベースとロールの OID で、起動初期は 0 である。
</p>
<p>
  識別情報のうち特に重要なのが <code>pgxactoff</code> である。これは
  「ProcGlobal の各配列へのオフセット」で、自分のデータがミラーされている
  密な配列の添字を指す。<code>pgxactoff</code> は ProcArray への追加・削除で
  変化しうるため、参照には ProcArrayLock または XidGenLock が必要である
  （第3章で詳述）。<code>statusFlags</code> は自動バキューム中・VACUUM 中などを
  表すビット群で、%s に定義がある。
</p>

<h2 id="sec-2-2">2.2　トランザクションとスナップショット</h2>
<p>
  PGPROC の中核がこのブロックである。<code>vxid</code> は実行中トップレベル
  トランザクションの仮想 XID（<code>procNumber</code> と <code>lxid</code> の組）で、
  ひとまとまりとして原子的に代入できないため、あえて分割して扱う設計になっている。
</p>
<ul>
  <li><code>xid</code> — 実行中トップレベルトランザクションの XID。割り当て済みの場合のみ有効。
      <code>ProcGlobal-&gt;xids[pgxactoff]</code> にミラーされる。</li>
  <li><code>xmin</code> — このトランザクション開始時点での最小実行中 XID。
      VACUUM は <code>xid &gt;= xmin</code> で削除されたタプルを除去してはならない。</li>
  <li><code>subxidStatus</code> / <code>subxids</code> — サブトランザクション XID の
      キャッシュ。最大 %s（=64）個まで保持し、あふれた場合は <code>overflowed</code>
      フラグが立つ。</li>
</ul>
<p>
  サブトランザクションキャッシュの型は %s と %s である。すべての PGPROC の
  キャッシュがあふれていなければ、「PGPROC 配列のどこにも載っていない XID は
  実行中ではない」と判断でき、<code>pg_subtrans</code> を引く必要がなくなる。
  これが 64 という上限を設けてキャッシュする理由である。
</p>

<div class="example">
  <span class="example-label">proc.h — サブトランザクションキャッシュ</span>
  <pre><code>#define PGPROC_MAX_CACHED_SUBXIDS 64    /* XXX guessed-at value */

typedef struct XidCacheStatus {
    uint8 count;        /* キャッシュ済み subxid 数 */
    bool  overflowed;   /* PGPROC->subxids があふれたか */
} XidCacheStatus;

struct XidCache {
    TransactionId xids[PGPROC_MAX_CACHED_SUBXIDS];
};</code></pre>
</div>

<h2 id="sec-2-3">2.3　プロセス間シグナリングと待機</h2>
<p>
  プロセス同士を起こし合うための道具立てがこのブロックにある。
  <code>procLatch</code> は汎用ラッチ（イベント待機の通知機構）、
  <code>sem</code> は「眠るための 1 つのセマフォ」である。バックエンドが
  ロックやイベントを待つときはこれらの上でブロックし、他プロセスが
  シグナルを送って起こす。
</p>
<p>
  <code>delayChkptFlags</code> はチェックポイントの進行を一時的に遅延させる
  ためのビット群で、%s に <code>DELAY_CHKPT_START</code> /
  <code>DELAY_CHKPT_COMPLETE</code> / <code>DELAY_CHKPT_IN_COMMIT</code> が
  定義されている。WAL ログ対象の変更がディスクへ確実に反映される前に
  チェックポイントが完了してしまうのを防ぐための仕組みである。
</p>
<p>
  続く LWLock 待機ブロックには <code>lwWaiting</code>、<code>lwWaitMode</code>、
  <code>lwWaitLink</code> があり、軽量ロック（LWLock）やバッファコンテンツロックの
  待ち行列に自分を繋ぐために使う。バックエンドは同時に両種のロックを待つことが
  ないため、これらは共用されている。条件変数待機用の <code>cvWaitLink</code> も
  ここに置かれる。
</p>

<h2 id="sec-2-4">2.4　ロックマネージャ関連フィールド</h2>
<p>
  ヘビーウェイトロック（テーブルロック等）に関わるフィールド群である。
  待機中は <code>waitLock</code>（待っているロックオブジェクト）と
  <code>waitProcLock</code>（保持者ごとの情報）が設定され、<code>waitLink</code> で
  ロックの待ち行列に並ぶ。<code>waitLockMode</code> は要求中のロックモード、
  <code>heldLocks</code> はすでに保持しているロックのビットマスクである。
  待機状態は %s 型の <code>waitStatus</code> で表される。
</p>
<p>
  <code>myProcLocks[NUM_LOCK_PARTITIONS]</code> は、このバックエンドが保持・待機する
  すべての PROCLOCK を、ロックのパーティション番号別に繋いだリストである。
  さらに「ファストパスロック」用の <code>fpLockBits</code> / <code>fpRelId</code> /
  <code>fpVXIDLock</code> などがあり、弱いリレーションロック
  （AccessShareLock など）をメインのロックテーブルではなく PGPROC 側に記録して
  ロックマネージャの LWLock 競合を緩和する。最後に、並列クエリで使う
  ロックグループ用フィールド（<code>lockGroupLeader</code> ほか）が並ぶ。
  これらの協調動作は<a href="ch05.html">第5章</a>で扱う。
</p>
<div class="note"><strong>メモ</strong>ファストパスロックのグループ数はバックエンドあたり可変で、
<code>max_locks_per_transaction</code> に基づいて
<code>InitializeFastPathLocks()</code> が決定する。配列が可変長のため、
これらは PGPROC 本体ではなく別の共有メモリ領域に確保される（第3章）。</div>
""" % (
    L(PROC_H, 184, "PGPROC"),
    L(PROC_H, 61, "PROC_IS_AUTOVACUUM ほか"),
    L(PROC_H, 43, "PGPROC_MAX_CACHED_SUBXIDS"),
    L(PROC_H, 45, "XidCacheStatus"),
    L(PROC_H, 53, "XidCache"),
    L(PROC_H, 145, "proc.h"),
    L(PROC_H, 149, "ProcWaitStatus"),
)

# ===========================================================================
CH3 = """
<p>
  個々の PGPROC は単独で存在するのではなく、クラスタ全体で 1 つの
  %s 構造体に束ねられている。本章では、全 PGPROC を統括する PROC_HDR、
  プロセス種別ごとのフリーリスト、そして PGPROC の一部フィールドを別途
  「密にパックした配列」へミラーする設計を解説する。
</p>

<h2 id="sec-3-1">3.1　PROC_HDR と allProcs 配列</h2>
<p>
  クラスタには %s が指す <code>ProcGlobal</code> がただ一つ存在する。
  その先頭フィールド <code>allProcs</code> が、全 PGPROC を並べた配列の本体である。
  <code>allProcCount</code> はその長さ（ただしプリペアドトランザクション分は除く）を表す。
  <a href="ch01.html#sec-1-2">1.2 節</a>で見た <code>GetPGProcByNumber()</code> は、
  この <code>allProcs</code> を ProcNumber で添字参照するだけのマクロであった。
</p>

<figure>
  <pre class="mermaid">
flowchart TB
    subgraph PH["PROC_HDR (ProcGlobal)"]
        AP["allProcs ->"]
        XS["xids[] ->"]
        SS["subxidStates[] ->"]
        SF["statusFlags[] ->"]
        FREE["freeProcs / autovacFreeProcs<br/>bgworkerFreeProcs / walsenderFreeProcs"]
    end
    subgraph ARR["共有メモリ上の配列"]
        AllProcs["PGPROC[0] PGPROC[1] ... PGPROC[TotalProcs-1]"]
        Dense["xids / subxidStates / statusFlags (密配列)"]
    end
    AP --> AllProcs
    XS --> Dense
    SS --> Dense
    SF --> Dense
  </pre>
  <figcaption>図 3.1: PROC_HDR が allProcs 配列と密な並列配列を統括する</figcaption>
</figure>

<p>
  図 3.1 のとおり、PROC_HDR は PGPROC 本体の配列に加えて、後述する 3 本の
  「密配列」へのポインタ、プロセス種別ごとのフリーリスト、そしてグループ処理用の
  アトミック変数や補助プロセスのスロット番号（<code>walwriterProc</code>、
  <code>checkpointerProc</code>）を保持する。フリーリストを守る
  <code>freeProcsLock</code> がスピンロックなのは、LWLock の獲得自体が PGPROC と
  セマフォの存在に依存しており、PGPROC を配るこの段階では LWLock を使えないためである。
</p>

<h2 id="sec-3-2">3.2　フリーリストとプロセス種別</h2>
<p>
  <a href="ch01.html#sec-1-3">1.3 節</a>で見た用途のうち、フルバックエンド系は
  4 本のフリーリストで管理される。共有メモリ初期化時、各 PGPROC は添字の範囲に
  応じてどれか一つのリストへ繋がれ、自分の所属リストを <code>procgloballist</code> に
  記録する。
</p>

<div class="example">
  <span class="example-label">proc.c — ProcGlobalShmemInit() でのフリーリスト振り分け（要約）</span>
  <pre><code>if (i &lt; MaxConnections)
    /* 通常バックエンド → freeProcs */
else if (i &lt; MaxConnections + autovacuum_worker_slots + NUM_SPECIAL_WORKER_PROCS)
    /* autovacuum / 特殊ワーカー → autovacFreeProcs */
else if (i &lt; ... + max_worker_processes)
    /* バックグラウンドワーカー → bgworkerFreeProcs */
else if (i &lt; MaxBackends)
    /* WAL センダ → walsenderFreeProcs */</code></pre>
</div>

<p>
  このように添字の区画とフリーリストが一対一で対応しているため、起動時に
  どのリストから引いたかでプロセス種別が確定する。%s は同じ条件分岐で
  「自分がどのリストから取るべきか」を選び、整合性を <code>Assert</code> で
  検証している。補助プロセス（<code>MaxBackends</code> 以降の領域）はフリーリストを
  使わず、%s が線形探索で空きスロットを探す。
</p>

<h2 id="sec-3-3">3.3　密な並列配列とミラーリング</h2>
<p>
  PGPROC の一部フィールド ― <code>xid</code>、<code>subxidStatus</code>、
  <code>statusFlags</code> ― は、PROC_HDR の <code>xids[]</code>、
  <code>subxidStates[]</code>、<code>statusFlags[]</code> という<strong>密にパックした
  配列</strong>へ二重に保持される。これらの配列は <code>pgxactoff</code> で添字され、
  ProcArray に登録済みの PGPROC の分だけが詰めて並ぶ（未使用スロットが
  混ざる allProcs と対照的）。
</p>

<figure>
  <pre class="mermaid">
flowchart LR
    subgraph backend["バックエンド自身"]
        own["MyProc->xid<br/>(ロック不要で参照)"]
    end
    subgraph dense["密配列 (pgxactoff で添字)"]
        d0["xids[0]"]
        d1["xids[1]"]
        d2["xids[2]"]
    end
    own -. ProcArrayLock 保持時に同期 .-> d1
    scan["GetSnapshotData()<br/>全件走査"] --> d0
    scan --> d1
    scan --> d2
  </pre>
  <figcaption>図 3.2: PGPROC 本体と密配列の二重保持（ミラーリング）</figcaption>
</figure>

<p>
  なぜ二重に持つのか。proc.h の長大なコメントが理由を 3 つ挙げる。第一に、
  できるだけタイトなループでデータを走査できるようにするため。第二に、
  頻繁に変わるデータ（<code>xmin</code> など）の更新が、あまり変わらないデータ
  （<code>xid</code>、<code>statusFlags</code>）のキャッシュラインを無効化しないように
  するため。第三に、頻繁にアクセスされるデータを可能な限り少ないキャッシュ
  ラインへ凝縮するためである。
</p>
<p>
  使い分けの原則はこうである。<strong>単一バックエンドのデータを見るときは
  PGPROC 本体</strong>を（自分の値なら多くの場合ロックなしで安全に読める）、
  <strong>多数のエントリを走査するときは密配列</strong>を見る。図 3.2 のように、
  自バックエンドのコミット/アボート判定では PGPROC 本体を確認することで、
  他コアが触る密配列のキャッシュラインを汚さずに済む。
</p>
<div class="warn"><strong>注意</strong><code>pgxactoff</code> で添字される密配列の値は、
<strong>必ず ProcArrayLock か XidGenLock を保持して</strong>アクセスしなければならない。
ProcArrayAdd / ProcArrayRemove によって他メンバーの <code>pgxactoff</code> が
並行して変化しうるためである。両方の値はミラーされている間、整合的に
維持しなければならない。</div>
""" % (
    L(PROC_H, 444, "PROC_HDR"),
    L(PROC_H, 503, "ProcGlobal"),
    L(PROC_C, 392, "InitProcess()"),
    L(PROC_C, 618, "InitAuxiliaryProcess()"),
)

# ===========================================================================
CH4 = """
<p>
  PGPROC は postmaster 起動時に共有メモリ上へまとめて確保され、各プロセスの
  起動・終了に応じて貸し出し・返却される。本章ではこのライフサイクルを、
  確保 → 割り当て → ProcArray 登録 → 解放の順に追う。
</p>

<figure>
  <pre class="mermaid">
stateDiagram-v2
    [*] --> 確保済み: ProcGlobalShmemInit()
    確保済み --> フリーリスト: フリーリストへ push
    フリーリスト --> 割当済み: InitProcess() が pop
    割当済み --> ProcArray登録: InitProcessPhase2()
    ProcArray登録 --> 解放中: バックエンド終了
    解放中 --> フリーリスト: ProcKill() が push
    フリーリスト --> [*]
  </pre>
  <figcaption>図 4.1: PGPROC のライフサイクル状態遷移</figcaption>
</figure>

<h2 id="sec-4-1">4.1　共有メモリの確保</h2>
<p>
  必要な PGPROC の総数は %s で計算される。
  <code>TotalProcs = MaxBackends + NUM_AUXILIARY_PROCS + max_prepared_xacts</code>
  であり、PGPROC 本体に加えて密配列 3 本ぶんの共有メモリも同時に予約される。
</p>
<p>
  実際の初期化は %s が行う。この関数は、フリーリストの初期化、allProcs と
  密配列の領域切り出し、バックエンドあたりのセマフォ作成、そして各 PGPROC の
  共通初期化（ファストパス配列の割り当て、ラッチ・セマフォ・<code>fpInfoLock</code> の
  セットアップ、<code>myProcLocks[]</code> の初期化）を行う。セマフォを起動時に
  まとめて確保するのは、カーネルのセマフォ上限超過を「あとで」ではなく「すぐに」
  検知させるためである。
</p>
<div class="info"><strong>関連</strong>各 PGPROC はこのループの末尾でいずれかのフリーリストへ
push される（<a href="ch03.html#sec-3-2">3.2 節</a>）。プリペアドトランザクション用の
PGPROC だけは <code>TwoPhaseShmemInit()</code> が別途フリーリストに繋ぐ。</div>

<h2 id="sec-4-2">4.2　PGPROC の割り当て</h2>
<p>
  バックエンドは起動時に %s を呼び、自分の種別に対応するフリーリストから
  PGPROC を 1 つ取り出して <code>MyProc</code> にセットする。リストが空なら
  「sorry, too many clients already」エラーになる ― これが接続数上限を
  検知する地点の一つである。
</p>

<div class="example">
  <span class="example-label">proc.c — InitProcess() のフリーリスト選択（要約）</span>
  <pre><code>if (AmAutoVacuumWorkerProcess() || AmSpecialWorkerProcess())
    procgloballist = &amp;ProcGlobal-&gt;autovacFreeProcs;
else if (AmBackgroundWorkerProcess())
    procgloballist = &amp;ProcGlobal-&gt;bgworkerFreeProcs;
else if (AmWalSenderProcess())
    procgloballist = &amp;ProcGlobal-&gt;walsenderFreeProcs;
else
    procgloballist = &amp;ProcGlobal-&gt;freeProcs;
...
MyProc = dlist_container(PGPROC, freeProcsLink,
                         dlist_pop_head_node(procgloballist));
MyProcNumber = GetNumberFromPGProc(MyProc);</code></pre>
</div>

<p>
  PGPROC を取得した後、<code>InitProcess()</code> は <code>xid</code>、<code>xmin</code>、
  <code>pid</code>、<code>vxid</code> などほぼ全フィールドを初期値にリセットし、
  共有ラッチの所有権を取得して（<code>OwnLatch</code> → <code>SwitchToSharedLatch</code>）、
  終了時クリーンアップとして <code>ProcKill</code> を登録する。補助プロセスは
  代わりに %s を呼び、フリーリストではなく線形探索で空きスロットを得る。
</p>

<h2 id="sec-4-3">4.3　ProcArray への登録</h2>
<p>
  PGPROC を確保しただけでは、まだ他プロセスから「実行中トランザクション」として
  見えない。%s が %s を呼び、PGPROC を共有 ProcArray に追加して初めて可視になる。
  この関数は <strong>ProcArrayLock と XidGenLock の両方を排他で</strong>取得する
  （この順序が重要）。
</p>
<p>
  ProcArrayAdd は、参照局所性を高めるため配列を PGPROC ポインタ順にソート状態で
  保つ。挿入位置を見つけたら、それ以降の <code>pgprocnos</code> と 3 本の密配列を
  <code>memmove</code> で 1 つずらし、新しいエントリを書き込み、後続すべての
  <code>pgxactoff</code> を振り直す。これが「ProcArrayAdd/Remove で pgxactoff が
  変化する」（<a href="ch03.html#sec-3-3">3.3 節</a>の注意）の正体である。
  ロックは取得と逆順（XidGenLock → ProcArrayLock）で解放される。
</p>

<h2 id="sec-4-4">4.4　PGPROC の解放</h2>
<p>
  バックエンド終了時には、登録の逆順で後始末が行われる。まず
  <code>RemoveProcFromArray</code>（内部で %s）が PGPROC を ProcArray から外し、
  続いて %s が PGPROC をフリーリストへ返す。
</p>
<p>
  <code>ProcKill()</code> は、保持中の LWLock の解放、同期レプリケーション
  リストからの離脱、共有ラッチの返却（<code>DisownLatch</code>）などを行う。
  特に注意深いのが<strong>ロックグループからの離脱</strong>である。自分が
  グループのリーダーかフォロワーか、最後のメンバーかどうかに応じて、自分自身と
  リーダーのどちらをフリーリストへ戻すかを決める。リーダーが先に抜けても
  PGPROC は最後のフォロワーが返すまで解放されない。
</p>
<div class="warn"><strong>注意</strong><code>DisownLatch()</code> は PGPROC がフリーリストへ
載るより前に行わなければならない。さもないと、空いたスロットを pop した新しい
バックエンドが <code>OwnLatch()</code> で「まだ所有されているラッチ」に出くわして
PANIC する。解放処理の順序にはこうした制約が織り込まれている。</div>
""" % (
    L(PROC_C, 147, "ProcGlobalShmemRequest()"),
    L(PROC_C, 221, "ProcGlobalShmemInit()"),
    L(PROC_C, 392, "InitProcess()"),
    L(PROC_C, 618, "InitAuxiliaryProcess()"),
    L(PROC_C, 583, "InitProcessPhase2()"),
    L(PARRAY_C, 464, "ProcArrayAdd()"),
    L(PARRAY_C, 561, "ProcArrayRemove()"),
    L(PROC_C, 924, "ProcKill()"),
)

# ===========================================================================
CH5 = """
<p>
  PGPROC は単なる状態の掲示板にとどまらず、プロセス同士が待ち合わせ・起こし合う
  ための<strong>連結リストのノード</strong>としても機能する。本章では PGPROC を
  介した代表的な 4 つの協調動作を見る。
</p>

<h2 id="sec-5-1">5.1　ヘビーウェイトロックの待機キュー</h2>
<p>
  あるロックを取得できないバックエンドは、ロックオブジェクトの待ち行列
  （<code>lock-&gt;waitProcs</code>）に自分の PGPROC を繋いで眠る。キューへの参加は
  %s が、実際のスリープは %s が担う。待機中、PGPROC の <code>waitLock</code> /
  <code>waitProcLock</code> / <code>waitLockMode</code> が設定され、<code>waitLink</code> が
  キュー内の位置を表す。
</p>

<figure>
  <pre class="mermaid">
flowchart LR
    LOCK["LOCK オブジェクト"]
    LOCK --> WQ["waitProcs (待ち行列)"]
    WQ --> P1["PGPROC A<br/>waitLink"]
    P1 --> P2["PGPROC B<br/>waitLink"]
    P2 --> P3["PGPROC C<br/>waitLink"]
  </pre>
  <figcaption>図 5.1: ロックの待ち行列に PGPROC が waitLink で連なる</figcaption>
</figure>

<p>
  図 5.1 のように待機者は双方向リンクリストで繋がれる。ロックが解放されると
  <code>ProcLockWakeup()</code> がキューを走査し、取得可能になった待機者の PGPROC を
  <code>ProcWakeup()</code> で起こす。各 PGPROC の <code>sem</code> セマフォと
  <code>waitStatus</code>（<code>PROC_WAIT_STATUS_OK</code> など）が、この
  起こし合いの同期点になる。デッドロック検出やロックタイムアウトも、この
  待機の仕組みの上に実装されている。
</p>

<h2 id="sec-5-2">5.2　グループ XID クリア</h2>
<p>
  多数のバックエンドが同時にコミットすると、コミット完了時に ProcArrayLock を
  排他取得して <code>xid</code> をクリアする処理が激しく競合する。これを緩和するのが
  %s による<strong>グループ XID クリア</strong>である。
</p>
<p>
  ProcArrayLock をすぐ取れないバックエンドは、自分を「XID クリア待ちリスト」へ
  アトミックに連結する（PROC_HDR の <code>procArrayGroupFirst</code> を CAS で更新し、
  PGPROC の <code>procArrayGroupNext</code> でリストを繋ぐ）。リストが空でなければ
  自分はフォロワーとして眠り、リーダーに任せる。リストが空だった最初の 1 人が
  <strong>リーダー</strong>となり、ロックを 1 回だけ取得して全メンバーの XID を
  まとめてクリアし、各メンバーのセマフォを上げて起こす。
</p>

<figure>
  <pre class="mermaid">
sequenceDiagram
    participant F as フォロワー
    participant G as procArrayGroupFirst
    participant L as リーダー
    F->>G: CAS で自分を先頭に連結
    Note over F: nextidx != INVALID なので<br/>セマフォで眠る
    L->>G: exchange で全リストを取得
    L->>L: ProcArrayLock を1回取得
    L->>L: 各メンバーの XID をクリア
    L-->>F: セマフォを上げて起こす
  </pre>
  <figcaption>図 5.2: グループ XID クリアの流れ</figcaption>
</figure>

<p>
  図 5.2 のとおり、ロックの取得回数を「メンバー数 × 1」から「1」へ削減できる。
  同種の仕組みは clog（トランザクション状態）の更新にもあり、PGPROC の
  <code>clogGroupMember</code> / <code>clogGroupNext</code> 系フィールドと PROC_HDR の
  <code>clogGroupFirst</code> がそれを担う。
</p>

<h2 id="sec-5-3">5.3　ロックグループと並列クエリ</h2>
<p>
  並列クエリでは、リーダーと並列ワーカーが互いのロックを「敵」と見なさない
  よう、<strong>ロックグループ</strong>を組む。PGPROC の <code>lockGroupLeader</code>
  （自分がメンバーならリーダーを指す）、<code>lockGroupMembers</code>（自分が
  リーダーならメンバー一覧）、<code>lockGroupLink</code>（メンバーとしての連結）が
  これを表現する。
</p>

<figure>
  <pre class="mermaid">
flowchart TB
    LEADER["PGPROC リーダー<br/>lockGroupMembers"]
    LEADER --> M1["PGPROC ワーカー1<br/>lockGroupLeader -> リーダー"]
    LEADER --> M2["PGPROC ワーカー2<br/>lockGroupLeader -> リーダー"]
    M1 -.lockGroupLink.-> LEADER
    M2 -.lockGroupLink.-> LEADER
  </pre>
  <figcaption>図 5.3: ロックグループのリーダーとメンバーの関係</figcaption>
</figure>

<p>
  図 5.3 の関係は、リーダーの PGPROC をキーにした
  <code>LockHashPartitionLockByProc</code> で保護される。<code>BecomeLockGroupLeader()</code>
  と <code>BecomeLockGroupMember()</code> でグループを構成し、ロックマネージャは
  同一グループのメンバーが保持するロックを競合と見なさない。
  <a href="ch04.html#sec-4-4">4.4 節</a>で触れたとおり、グループの解体は
  PGPROC 解放の順序に微妙な制約を課す。
</p>

<h2 id="sec-5-4">5.4　同期レプリケーションの待機</h2>
<p>
  同期レプリケーションでは、コミットしたバックエンドが「自分の LSN がスタンバイへ
  反映される」まで待つ。PGPROC の <code>waitLSN</code>（待っている LSN）、
  <code>syncRepState</code>（待機状態）、<code>syncRepLinks</code>（同期レプリ待ち
  行列のリンク）がこれを表す。バックエンドは自分を待ち行列へ繋いで眠り、
  WAL センダがスタンバイからの応答を受けて該当 LSN 以下の待機者を起こす。
</p>
<div class="note"><strong>メモ</strong><code>syncRepState</code> は所有プロセスと WAL センダ
以外が触ってはならず、<code>syncRepLinks</code> は SyncRepLock 保持中のみ操作できる。
このように PGPROC の各フィールドには、それぞれ固有のアクセス規約が定められている。</div>
""" % (
    L(PROC_C, 1179, "JoinWaitQueue()"),
    L(PROC_C, 1348, "ProcSleep()"),
    L(PARRAY_C, 784, "ProcArrayGroupClearXid()"),
)

# ===========================================================================
CH6 = """
<p>
  PGPROC は共有メモリ上の C 構造体だが、その内容の多くは SQL から観察できる。
  本章では代表的なシステムビューと PGPROC フィールドの対応を示し、内部状態を
  手元で確かめる方法を紹介する。
</p>

<h2 id="sec-6-1">6.1　pg_stat_activity との対応</h2>
<p>
  <code>pg_stat_activity</code> の各行は、概ね 1 つの PGPROC（とそれに紐づく
  バックエンド状態）に対応する。<code>pid</code> は PGPROC の <code>pid</code>、
  <code>datid</code> / <code>usesysid</code> は <code>databaseId</code> / <code>roleId</code>、
  <code>backend_type</code> は <code>backendType</code> に由来する。
  <code>backend_xid</code> と <code>backend_xmin</code> は、まさに PGPROC の
  <code>xid</code> と <code>xmin</code> である。
</p>

<div class="example">
  <span class="example-label">SQL — 実行中トランザクションの xid / xmin を見る</span>
  <pre><code>SELECT pid, backend_type, state, backend_xid, backend_xmin
FROM pg_stat_activity
WHERE backend_xid IS NOT NULL OR backend_xmin IS NOT NULL;</code></pre>
</div>

<div class="example">
  <span class="example-label">実行結果（例）</span>
  <pre><code>  pid  | backend_type   | state  | backend_xid | backend_xmin
-------+----------------+--------+-------------+--------------
 41210 | client backend | active |         812 |          812
 41215 | client backend | idle   |             |          809</code></pre>
</div>

<p>
  <code>backend_xmin</code> はバキュームの地平に直結する。古いスナップショットを
  握ったまま放置されたセッションがあると、その PGPROC の <code>xmin</code> が
  小さいままになり、デッドタプルを回収できなくなる ―
  PGPROC を観察することは、こうした「VACUUM が効かない」問題の診断に役立つ。
</p>

<h2 id="sec-6-2">6.2　pg_locks と待機関係</h2>
<p>
  <code>pg_locks</code> は、各 PGPROC が保持・待機するロックを行として見せる。
  <code>granted = false</code> の行は、その PGPROC が
  <a href="ch05.html#sec-5-1">5.1 節</a>の待ち行列で眠っていることを意味する。
  PostgreSQL 9.6 以降は <code>pg_blocking_pids()</code> で、ある PID をブロックして
  いる PID 群を直接得られる。
</p>

<div class="example">
  <span class="example-label">SQL — ロック待ちのセッションとブロック元を調べる</span>
  <pre><code>SELECT a.pid, a.wait_event_type, a.wait_event,
       pg_blocking_pids(a.pid) AS blocked_by
FROM pg_stat_activity a
WHERE cardinality(pg_blocking_pids(a.pid)) &gt; 0;</code></pre>
</div>

<p>
  内部的には <code>pg_blocking_pids()</code> が PGPROC の待ち行列と保持ロックを
  たどって、誰が誰を待たせているかを再構成している。並列クエリのロックグループ
  （<a href="ch05.html#sec-5-3">5.3 節</a>）も考慮されるため、ワーカーをブロック
  している相手はリーダーの PID として報告される。
</p>

<h2 id="sec-6-3">6.3　待機イベントの確認</h2>
<p>
  PGPROC の <code>wait_event_info</code> は、そのプロセスが「いま何を待っているか」を
  表すコードである。<code>pg_stat_activity</code> の <code>wait_event_type</code> /
  <code>wait_event</code> 列はこれを人間可読な名前に変換したものだ。
  たとえば<a href="ch05.html#sec-5-2">5.2 節</a>のグループ XID クリアで眠る
  プロセスは <code>ProcArrayGroupUpdate</code> という待機イベントを報告する。
</p>

<div class="example">
  <span class="example-label">SQL — 待機イベントの分布を集計する</span>
  <pre><code>SELECT wait_event_type, wait_event, count(*)
FROM pg_stat_activity
WHERE wait_event IS NOT NULL
GROUP BY 1, 2
ORDER BY 3 DESC;</code></pre>
</div>

<p>
  このように、PGPROC のフィールドはほぼそのまま運用上の観測点になっている。
  構造体の意味を理解しておくと、<code>pg_stat_activity</code> や <code>pg_locks</code> の
  各列が「共有メモリ上のどのフィールドを映したものか」が腑に落ち、性能問題や
  ロック競合の診断が格段に進めやすくなる。
</p>
<div class="info"><strong>まとめ</strong>PGPROC は、プロセスごとの状態広告・プロセス間の
待ち合わせ・スナップショットの基盤という 3 つの顔を持つ共有メモリ構造体である。
その設計（ミラー配列・フリーリスト・グループ処理）は、多数のプロセスが
高頻度でアクセスする中での競合とキャッシュ効率を徹底的に意識したものになっている。</div>
"""

BODIES = [CH1, CH2, CH3, CH4, CH5, CH6]
