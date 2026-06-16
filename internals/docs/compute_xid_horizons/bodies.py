# -*- coding: utf-8 -*-
"""Chapter bodies for the ComputeXidHorizons doc. Plain HTML strings."""

GH = "https://github.com/shinyaaa/postgres/blob/0131e8fc508ff8e10a6797bfe8043a0b9d34b30b"

def fn(path, line, label):
    if line:
        return '<a href="%s/%s#L%d"><code>%s</code></a>' % (GH, path, line, label)
    return '<a href="%s/%s"><code>%s</code></a>' % (GH, path, label)

PROC = "src/backend/storage/ipc/procarray.c"
README = "src/backend/access/transam/README"

# 短縮: 主要シンボルへのリンク
L_compute   = fn(PROC, 1674, "ComputeXidHorizons()")
L_result    = fn(PROC, 196, "ComputeXidHorizonsResult")
L_gvstate   = fn(PROC, 184, "GlobalVisState")
L_getnonrem = fn(PROC, 1943, "GetOldestNonRemovableTransactionId()")
L_getrun    = fn(PROC, 1972, "GetOldestTransactionIdConsideredRunning()")
L_getrepl   = fn(PROC, 1985, "GetReplicationHorizons()")
L_kindforrel= fn(PROC, 1909, "GlobalVisHorizonKindForRel()")
L_testfor   = fn(PROC, 4105, "GlobalVisTestFor()")
L_shouldupd = fn(PROC, 4145, "GlobalVisTestShouldUpdate()")
L_applyupd  = fn(PROC, 4164, "GlobalVisUpdateApply()")
L_gvupdate  = fn(PROC, 4203, "GlobalVisUpdate()")
L_isremfull = fn(PROC, 4225, "GlobalVisTestIsRemovableFullXid()")
L_isremxid  = fn(PROC, 4268, "GlobalVisTestIsRemovableXid()")
L_fullxidrel= fn(PROC, 4352, "FullXidRelativeTo()")
L_kaxmin    = fn(PROC, 5215, "KnownAssignedXidsGetOldestXmin()")
L_readme    = '<a href="%s/%s#L296"><code>access/transam/README</code></a>' % (GH, README)

# =========================================================================
ch1 = r"""
<p>
  PostgreSQL の追記型ストレージでは、行を更新・削除しても古いバージョン（タプル）は即座に消えず、
  「もう誰からも見えない」と確定したときに初めて <strong>VACUUM</strong> が回収する。
  その「誰からも見えない」を判定する境界が <strong>XID ホライズン（地平線, horizon）</strong> であり、
  本章ではなぜこの境界が必要で、""" + L_compute + r""" がそこで何を担うのかを概観する。
</p>

<h2 id="sec-1-1">1.1　MVCC と不要タプル</h2>
<p>
  多版型同時実行制御（Multiversion Concurrency Control, MVCC）では、各タプルに挿入トランザクションの
  <code>xmin</code> と削除トランザクションの <code>xmax</code> が刻まれる。あるタプルが不要（dead）になるのは、
  それを削除したトランザクションがコミット済みで、かつ <strong>実行中のどのスナップショットからも見えなくなった</strong>
  ときである。逆に言えば、いま動いているトランザクションのうち最も古いものが見ている地点より新しい変更は、
  まだ消してはならない。
</p>
<figure>
  <pre class="mermaid">
flowchart LR
    A["タプル v1<br/>xmin=100, xmax=150"] -->|UPDATE 150| B["タプル v2<br/>xmin=150"]
    A -. "xmax=150 はコミット済み" .-> C{"v1 は除去可能か?"}
    C -->|"古いスナップショットが<br/>まだ v1 を見るかも"| D["保持"]
    C -->|"誰も v1 を見ない"| E["除去可"]
  </pre>
  <figcaption>図 1.1: 削除済みタプル v1 を除去してよいかは「最古の観測者」が決める</figcaption>
</figure>
<p>
  図 1.1 に示すように、v1 の除去可否は「v1 を見うる最古のトランザクション」が存在するかどうかに帰着する。
  この最古の地点を XID で表したものが地平線である。
</p>

<h2 id="sec-1-2">1.2　下界としての oldest xmin</h2>
<p>
  各バックエンドは自分のスナップショットの最小 xmin を <code>MyProc-&gt;xmin</code> に公示する
  （生きたスナップショットを持たないときは 0）。システム全体の地平線は、原理的には全バックエンドの
  有効な <code>xmin</code> の最小値である。""" + L_readme + r""" はこの計算が満たすべき正確性を次のように述べる。
</p>
<div class="note"><strong>READMEより</strong>
  ComputeXidHorizons は ProcArrayLock を<em>共有</em>ロックで取りながら有効な xmin の MIN() を取る。
  その際、まだ xmin を設定していない開始直後のトランザクションが後から自分より小さい xmin を
  設定してしまわないよう、<strong>実行中のすべての XID も MIN() の対象に含める</strong>。これにより、
  並行する GetSnapshotData が後で見る最小 xmin を、こちらが過大評価することはない。
</div>
<p>
  実行中トランザクションが一つも無い場合は <code>latestCompletedXid + 1</code> を下界として用いる。
  これは「これ以降に ProcArray へ現れうる XID の下限」であり、XidGenLock による
  インターロック（新しい XID は ProcArray へ格納してから可視になる）によって保証される。
</p>

<h2 id="sec-1-3">1.3　GetSnapshotData が正確値をやめた理由</h2>
<p>
  PostgreSQL 14 より前は、スナップショット取得 <code>GetSnapshotData()</code> のたびに正確な oldest xmin を
  計算していた。しかし xmin は xid よりはるかに頻繁に変化するため、全バックエンドの xmin を毎回読むと
  キャッシュラインの奪い合い（ping-pong）が激しく、性能が出ない。そこで現在の <code>GetSnapshotData()</code> は
  正確な地平線を計算せず、<strong>近似的な閾値</strong>だけを更新する（第4章）。正確な値が要るときにだけ
  """ + L_compute + r""" を呼ぶ、という二段構えになっている。
</p>
<figure>
  <pre class="mermaid">
flowchart TB
    GSD["GetSnapshotData()<br/>(高頻度・性能重視)"] --> APX["近似境界<br/>GlobalVisState を更新"]
    APX --> TEST["GlobalVisTest*()<br/>大半はここで判定"]
    TEST -->|"境界の中間でグレー"| CXH["ComputeXidHorizons()<br/>(正確だが高コスト)"]
    CXH --> APX
  </pre>
  <figcaption>図 1.2: 高頻度の近似更新と、必要時のみの正確計算という二段構え</figcaption>
</figure>
<p>
  図 1.2 のとおり、ホライズン計算は「速いが粗い経路」と「遅いが正確な経路」に分離されている。
  """ + L_compute + r""" は後者の中心にあり、VACUUM や <code>pg_subtrans</code> 切り詰めなど、
  正確さが要る場面から呼び出される。
</p>

<h2 id="sec-1-4">1.4　ComputeXidHorizons の位置づけ</h2>
<p>
  """ + L_compute + r""" は <code>storage/ipc/procarray.c</code> に置かれた静的関数で、
  単一の構造体 """ + L_result + r""" に複数の地平線をまとめて書き込む。直接の呼び出し口は次の三つの
  ラッパ関数（および近似境界更新用の内部関数）である。
</p>
<ul>
  <li>""" + L_getnonrem + r"""　— VACUUM が、どのリレーションの不要タプルを保持すべきかを決める。</li>
  <li>""" + L_getrun + r"""　— <code>pg_subtrans</code> をどこまで切り詰めてよいかを決める。</li>
  <li>""" + L_getrepl + r"""　— hot_standby_feedback で上流へ送る xmin / catalog_xmin を決める。</li>
</ul>
<p>
  次章では、これらが取り出す """ + L_result + r""" の各フィールドが何を意味するのかを一つずつ見ていく。
</p>
"""

# =========================================================================
ch2 = r"""
<p>
  """ + L_compute + r""" の出力は構造体 """ + L_result + r""" 一つに集約される。
  本章はそのフィールドを、リレーション種別ごとに地平線が分かれる理由とともに読み解く。
</p>

<h2 id="sec-2-1">2.1　4種のリレーションと地平線</h2>
<p>
  「あるトランザクションの効果が全員に見えなくなった」と判断できる条件は、対象リレーションの
  到達範囲によって変わる。たとえば別データベースのユーザテーブルは現在のバックエンドからは触れないので、
  そのテーブル向けの地平線は他データベースのスナップショットを無視してよい。
  """ + L_gvstate + r""" のコメントは、この観点から4種の状態を区別する。
</p>
<figure>
  <pre class="mermaid">
flowchart TB
    subgraph K["考慮する観測者の範囲（広い→狭い）"]
        S["SHARED（共有テーブル）<br/>全DBのスナップショット<br/>+ slot xmin + slot catalog_xmin"]
        C["CATALOG（カタログ）<br/>現DBのスナップショット<br/>+ slot xmin + slot catalog_xmin"]
        D["DATA（通常テーブル）<br/>現DBのスナップショット<br/>+ slot xmin"]
        T["TEMP（一時テーブル）<br/>自セッションのみ"]
    end
    S --> C --> D --> T
  </pre>
  <figcaption>図 2.1: リレーション種別ごとに考慮すべき観測者の範囲が異なる</figcaption>
</figure>
<p>
  図 2.1 のように、共有テーブル（SHARED）が最も保守的で多くの観測者を考慮し、一時テーブル（TEMP）が
  最も積極的に刈り取れる。どのリレーションがどの種別になるかは """ + L_kindforrel + r""" が決める（第5章）。
</p>

<h2 id="sec-2-2">2.2　構造体の全フィールド</h2>
<p>
  """ + L_result + r""" のフィールドは大きく「補助情報」と「地平線」に分かれる。
</p>
<figure>
  <pre class="mermaid">
classDiagram
    class ComputeXidHorizonsResult {
        +FullTransactionId latest_completed
        +TransactionId slot_xmin
        +TransactionId slot_catalog_xmin
        +TransactionId oldest_considered_running
        +TransactionId shared_oldest_nonremovable
        +TransactionId shared_oldest_nonremovable_raw
        +TransactionId catalog_oldest_nonremovable
        +TransactionId data_oldest_nonremovable
        +TransactionId temp_oldest_nonremovable
    }
  </pre>
  <figcaption>図 2.2: ComputeXidHorizonsResult のフィールド一覧</figcaption>
</figure>
<p>図 2.2 の各フィールドの意味は次のとおり（ソースのコメントに基づく）。</p>
<ul>
  <li><code>latest_completed</code>: ロック保持時点の <code>latestCompletedXid</code>（64bit）。近似境界を 64bit 化する基準に使う。</li>
  <li><code>slot_xmin</code> / <code>slot_catalog_xmin</code>: レプリケーションスロットが要求する xmin と catalog_xmin。</li>
  <li><code>oldest_considered_running</code>: <strong>いずれかのバックエンドがまだ実行中とみなしうる</strong>最古の XID。
      VACUUM 中のプロセスも含める点が可視性用の地平線と異なる。主に <code>pg_subtrans</code> を
      どこまで切り詰めてよいかの判断に使う。</li>
  <li><code>shared_oldest_nonremovable</code>: 共有テーブルで保持が必要な最古 XID（スロットの catalog_xmin も反映）。</li>
  <li><code>shared_oldest_nonremovable_raw</code>: 上記からスロットの catalog_xmin 影響を除いたもの。
      hot_standby_feedback で catalog_xmin を別送するために使う。</li>
  <li><code>catalog_oldest_nonremovable</code>: 非共有カタログテーブル向けの地平線。</li>
  <li><code>data_oldest_nonremovable</code>: 通常のユーザ定義テーブル向けの地平線。</li>
  <li><code>temp_oldest_nonremovable</code>: 自セッションの一時テーブル向けの地平線。</li>
</ul>
<div class="info"><strong>関連</strong>
  <code>oldest_considered_running</code> が VACUUM 中のプロセスまで含めるのは、VACUUM が可視性判定のために
  <code>pg_subtrans</code> を参照する可能性があるからである。詳細は
  <a href="ch05.html#sec-5-2">5.2 pg_subtrans の切り詰め</a>を参照。
</div>

<h2 id="sec-2-3">2.3　地平線の大小関係</h2>
<p>
  これらの地平線には不変条件があり、""" + L_compute + r""" の末尾で <code>Assert</code> により検証される。
  もっとも古い（小さい）のが <code>oldest_considered_running</code> で、もっとも新しい（大きい・積極的に刈れる）
  方向へ向かって SHARED → CATALOG/DATA → TEMP と並ぶ。
</p>
<figure>
  <pre class="mermaid">
flowchart LR
    OCR["oldest_considered_running"] --> SH["shared_oldest_nonremovable"]
    SH --> CAT["catalog_oldest_nonremovable"]
    SH --> DAT["data_oldest_nonremovable"]
    OCR --> TMP["temp_oldest_nonremovable"]
  </pre>
  <figcaption>図 2.3: 矢印の元は「より古い（先行する）」ことを表す不変条件</figcaption>
</figure>
<p>
  図 2.3 の関係（A → B は <code>TransactionIdPrecedesOrEquals(A, B)</code>）は、
  <code>oldest_considered_running</code> がすべての地平線以下であることを保証する。これは、どの地平線で
  刈り取りを判断する場面でも <code>pg_subtrans</code> 参照が依然として可能であることを意味する。
</p>
"""

# =========================================================================
ch3 = r"""
<p>
  本章は """ + L_compute + r""" の本体を上から順に追う。処理は「ProcArrayLock 共有取得 →
  初期化 → ProcArray 走査 → ロック解放 → スロット反映と検証」という流れで進む。
</p>

<h2 id="sec-3-1">3.1　ロックと初期値</h2>
<p>
  関数はまず <code>ProcArrayLock</code> を <strong>共有モード（LW_SHARED）</strong>で取得し、
  <code>latest_completed</code> に <code>TransamVariables-&gt;latestCompletedXid</code> を取り込む。
  続いて MIN() 計算の初期値を <code>latestCompletedXid + 1</code> に設定する。
</p>
<div class="example">
  <span class="example-label">procarray.c（抜粋・初期化部）</span>
  <pre><code>initial = XidFromFullTransactionId(h-&gt;latest_completed);
TransactionIdAdvance(initial);          /* = latestCompletedXid + 1 */

h-&gt;oldest_considered_running = initial;
h-&gt;shared_oldest_nonremovable = initial;
h-&gt;data_oldest_nonremovable  = initial;

if (TransactionIdIsValid(MyProc-&gt;xid))
    h-&gt;temp_oldest_nonremovable = MyProc-&gt;xid;
else
    h-&gt;temp_oldest_nonremovable = initial;</code></pre>
</div>
<p>
  一時テーブルの地平線だけは初期値が異なる。一時テーブルを変更できるのは自セッションだけなので、
  自分が XID を持つならそれを、持たないなら <code>latestCompletedXid + 1</code> を初期値にすれば十分である。
  スロット xmin（<code>replication_slot_xmin</code> / <code>replication_slot_catalog_xmin</code>）も
  このロック保持区間で読み取る。
</p>

<h2 id="sec-3-2">3.2　ProcArray の走査</h2>
<p>
  次に ProcArray のすべてのエントリを走査し、各プロセスの <code>xid</code> と <code>xmin</code> を読む。
  <code>UINT32_ACCESS_ONCE</code> で一度だけ読むのは、ロックなしで更新されうる XID フィールドを
  一貫して扱うためである（READMEの指摘どおり）。
</p>
<div class="example">
  <span class="example-label">procarray.c（抜粋・走査ループ）</span>
  <pre><code>xid  = UINT32_ACCESS_ONCE(other_xids[index]);
xmin = UINT32_ACCESS_ONCE(proc-&gt;xmin);

/* xmin と xid の古い方を採用（xid はあるが xmin 未設定の場合に備える） */
xmin = TransactionIdOlder(xmin, xid);
if (!TransactionIdIsValid(xmin))
    continue;            /* どちらも無効ならこのプロセスは影響しない */

h-&gt;oldest_considered_running =
    TransactionIdOlder(h-&gt;oldest_considered_running, xmin);</code></pre>
</div>
<p>
  ここで <code>xmin</code> と <code>xid</code> の<strong>古い方</strong>を採るのが要点である。1.2 で見たとおり、
  まだ xmin を設定していないが xid を持つトランザクションが、後から小さい xmin を設定しうる。
  両方を MIN() に含めることで過大評価を防いでいる。<code>oldest_considered_running</code> は、
  この段階で<strong>どのプロセスも除外せず</strong>更新される。
</p>

<h2 id="sec-3-3">3.3　フラグとデータベースの考慮</h2>
<p>
  可視性用の地平線（shared / data）は、VACUUM 中・論理デコード中のプロセスをスキップする。
  ステータスフラグ <code>PROC_IN_VACUUM</code> / <code>PROC_IN_LOGICAL_DECODING</code> がそれを示す。
</p>
<figure>
  <pre class="mermaid">
flowchart TB
    P["各 PGPROC エントリ"] --> X{"xmin/xid 有効?"}
    X -->|"いいえ"| SKIP["スキップ"]
    X -->|"はい"| OCR["oldest_considered_running を更新"]
    OCR --> V{"VACUUM or<br/>論理デコード中?"}
    V -->|"はい"| NEXT["次のエントリへ"]
    V -->|"いいえ"| SH["shared_oldest_nonremovable を更新"]
    SH --> DB{"同一DB / MyDatabaseId 未設定 /<br/>AFFECTS_ALL_HORIZONS / リカバリ?"}
    DB -->|"はい"| DAT["data_oldest_nonremovable を更新"]
    DB -->|"いいえ"| NEXT
  </pre>
  <figcaption>図 3.1: 1エントリあたりの地平線更新の判定フロー</figcaption>
</figure>
<p>
  図 3.1 のとおり、<code>shared</code> は全データベースのバックエンドを考慮するが、<code>data</code> は原則として
  同一データベース（<code>proc-&gt;databaseId == MyDatabaseId</code>）のみを考慮する。ただし次の場合は例外的に
  <code>data</code> にも含める。
</p>
<ul>
  <li><code>MyDatabaseId</code> が未設定（起動中のバックエンド）。過度に積極的な地平線で必要なデータを刈らないため。</li>
  <li><code>PROC_AFFECTS_ALL_HORIZONS</code> が立つプロセス（hot standby feedback 由来で、特定 DB に紐づかない）。</li>
  <li>リカバリ中。XID は <code>KnownAssignedXids</code> 機構で一括管理され、DB 別の正確な地平線を出せないため。</li>
</ul>

<h2 id="sec-3-4">3.4　リカバリと KnownAssignedXids</h2>
<p>
  リカバリ（スタンバイ）中は、プライマリから送られてくる実行中 XID が ProcArray ではなく
  <code>KnownAssignedXids</code> 配列で追跡される。そこでロック保持中に
  """ + L_kaxmin + r""" でその最古値を取得し、ロック解放後に各地平線へ反映する。
</p>
<div class="example">
  <span class="example-label">procarray.c（抜粋・リカバリ反映）</span>
  <pre><code>if (in_recovery)
    kaxmin = KnownAssignedXidsGetOldestXmin();

LWLockRelease(ProcArrayLock);   /* 以降はロック不要 */

if (in_recovery)
{
    h-&gt;oldest_considered_running =
        TransactionIdOlder(h-&gt;oldest_considered_running, kaxmin);
    h-&gt;shared_oldest_nonremovable =
        TransactionIdOlder(h-&gt;shared_oldest_nonremovable, kaxmin);
    h-&gt;data_oldest_nonremovable =
        TransactionIdOlder(h-&gt;data_oldest_nonremovable, kaxmin);
    /* 一時テーブルはリカバリ中にアクセスできない */
}</code></pre>
</div>
<p>
  共有状態から取るべき情報はここまでで、残りの計算はロックなしで行える。早めにロックを解放することで
  ProcArrayLock の競合を抑えている。
</p>

<h2 id="sec-3-5">3.5　スロットの反映と整合性検証</h2>
<p>
  ロック解放後、レプリケーションスロットの xmin を地平線へ反映する。<code>slot_xmin</code> は shared と data の
  両方へ、<code>slot_catalog_xmin</code> は shared と catalog へ適用する。catalog と data の唯一の違いが
  「スロットの catalog_xmin を適用するか否か」である点に注意したい。
</p>
<div class="example">
  <span class="example-label">procarray.c（抜粋・スロット反映）</span>
  <pre><code>/* data/shared にスロット xmin を反映 */
h-&gt;shared_oldest_nonremovable =
    TransactionIdOlder(h-&gt;shared_oldest_nonremovable, h-&gt;slot_xmin);
h-&gt;data_oldest_nonremovable =
    TransactionIdOlder(h-&gt;data_oldest_nonremovable, h-&gt;slot_xmin);

/* catalog_xmin 適用前の値を raw として退避（feedback 用） */
h-&gt;shared_oldest_nonremovable_raw = h-&gt;shared_oldest_nonremovable;
h-&gt;shared_oldest_nonremovable =
    TransactionIdOlder(h-&gt;shared_oldest_nonremovable, h-&gt;slot_catalog_xmin);
h-&gt;catalog_oldest_nonremovable =
    TransactionIdOlder(h-&gt;data_oldest_nonremovable, h-&gt;slot_catalog_xmin);</code></pre>
</div>
<p>
  スロットによって地平線が <code>oldest_considered_running</code> より古くまで引き戻される可能性があるため、
  続いて <code>oldest_considered_running</code> を各地平線以下になるよう修正し、最後に 2.3 で述べた
  大小関係を一連の <code>Assert</code> で検証する。仕上げに """ + L_applyupd + r""" を呼び、
  近似境界 """ + L_gvstate + r""" を更新する（第4章）。
</p>
<div class="warn"><strong>注意</strong>
  これらの <code>Assert</code> はアサーション有効ビルドでのみ働く。本番ビルドでは検査されないが、
  不変条件としてコードの前提を表しているため、変更時の指針になる。
</div>
"""

# =========================================================================
ch4 = r"""
<p>
  1.3 で触れたとおり、性能のため正確なホライズン計算は常時は行わない。代わりに """ + L_gvstate + r"""
  という<strong>近似境界</strong>を持ち、大半の可視性判定をそれで済ませる。本章はこの仕組みを読む。
</p>

<h2 id="sec-4-1">4.1　二つの境界</h2>
<p>
  """ + L_gvstate + r""" は二つの <code>FullTransactionId</code> を持つ。32bit ではなく 64bit を使うのは、
  境界が古くなったときの周回（wraparound）を避けるためである。
</p>
<figure>
  <pre class="mermaid">
flowchart LR
    subgraph Axis["XID 軸（左ほど古い）"]
        direction LR
        OLD["…古い"] --> MN["maybe_needed"] --> MID["（グレーゾーン）"] --> DN["definitely_needed"] --> NEW["新しい…"]
    end
  </pre>
  <figcaption>図 4.1: maybe_needed 未満は除去可、definitely_needed 以上は実行中とみなす</figcaption>
</figure>
<p>図 4.1 のとおり、ある XID に対する判定は次の三つに分かれる。</p>
<ul>
  <li><code>XID &lt; maybe_needed</code>: 確実に全員に見えない → <strong>除去可能</strong>。</li>
  <li><code>XID &gt;= definitely_needed</code>: まだ実行中とみなされる可能性が高い → <strong>除去不可</strong>。</li>
  <li>その中間（グレーゾーン）: 必要なら """ + L_compute + r""" を呼んで境界を更新し再判定する。</li>
</ul>

<h2 id="sec-4-2">4.2　GetSnapshotData による更新</h2>
<p>
  <code>maybe_needed</code> は、""" + L_compute + r""" 末尾の """ + L_applyupd + r""" によって
  各リレーション種別の <code>*_oldest_nonremovable</code> から計算される。
  <code>FullXidRelativeTo()</code> を使い 64bit 化しているのが """ + L_fullxidrel + r""" である。
</p>
<div class="example">
  <span class="example-label">procarray.c（抜粋・GlobalVisUpdateApply）</span>
  <pre><code>GlobalVisSharedRels.maybe_needed =
    FullXidRelativeTo(horizons-&gt;latest_completed,
                      horizons-&gt;shared_oldest_nonremovable);
/* catalog / data / temp も同様 */

/* 長時間Txでは以前 running 扱いだった Tx が消えていることがあるので
   definitely_needed が maybe_needed より古くならないよう引き上げる */
GlobalVisSharedRels.definitely_needed =
    FullTransactionIdNewer(GlobalVisSharedRels.maybe_needed,
                           GlobalVisSharedRels.definitely_needed);</code></pre>
</div>
<p>
  <code>definitely_needed</code> は通常の <code>GetSnapshotData()</code> 経路で「実行中とみなすべき XID の上限」
  として進む一方、ここで <code>maybe_needed</code> を下回らないよう引き上げられる。両境界は単調に新しい方へ
  動こうとする。
</p>

<h2 id="sec-4-3">4.3　GlobalVisTest* による判定</h2>
<p>
  実際の除去可否判定は """ + L_isremfull + r""" が担う。引数の XID が <code>maybe_needed</code> 未満なら即 true、
  <code>definitely_needed</code> 以上なら即 false、中間なら（許可されていれば）境界を更新して再判定する。
</p>
<figure>
  <pre class="mermaid">
sequenceDiagram
    participant V as VACUUM/HOT
    participant T as GlobalVisTestIsRemovableFullXid
    participant U as GlobalVisUpdate → ComputeXidHorizons
    V->>T: この fxid は除去可能か?
    alt fxid < maybe_needed
        T-->>V: true（除去可）
    else fxid >= definitely_needed
        T-->>V: false（保持）
    else グレーゾーン
        T->>U: 境界を再計算（allow_update 時）
        U-->>T: maybe_needed/definitely_needed 更新
        T-->>V: fxid < maybe_needed ?
    end
  </pre>
  <figcaption>図 4.2: GlobalVisTestIsRemovableFullXid の判定経路</figcaption>
</figure>
<p>
  図 4.2 のグレーゾーン処理が、近似と正確計算をつなぐ要である。32bit XID 版の
  """ + L_isremxid + r""" は """ + L_fullxidrel + r""" で 64bit 化してから本体を呼ぶ。
  どのリレーションのどの <code>GlobalVisState</code> を使うかは """ + L_testfor + r""" が選ぶ。
</p>

<h2 id="sec-4-4">4.4　再計算のヒューリスティック</h2>
<p>
  正確計算は高コストなので、グレーゾーンに入っても無制限には再計算しない。""" + L_shouldupd + r"""
  が次の条件で再計算の要否を判断する。
</p>
<ul>
  <li>まだ一度も更新していない（<code>ComputeXidHorizonsResultLastXmin</code> が無効）なら更新する。</li>
  <li><code>maybe_needed &gt;= definitely_needed</code>（境界が重なっている）なら更新しても益が薄いので更新しない。</li>
  <li>最後の更新以降に <code>RecentXmin</code> が変化していなければ、最古の実行中 Tx が終わっていない可能性が高く、更新を見送る。</li>
</ul>
<p>
  すなわち「直近のスナップショットの xmin が動いたとき」に限って正確計算を許す。これにより、地平線が
  進む見込みの薄い局面での無駄な ProcArray 走査を抑えている。
</p>
"""

# =========================================================================
ch5 = r"""
<p>
  本章は """ + L_compute + r""" を呼ぶ三つの公開ラッパを取り上げ、それぞれがどの地平線を
  どう使うのかを見る。リレーション種別の選択 """ + L_kindforrel + r""" も併せて確認する。
</p>

<h2 id="sec-5-1">5.1　VACUUM の刈り取り境界</h2>
<p>
  VACUUM は """ + L_getnonrem + r""" を呼び、対象リレーションに応じた地平線を受け取る。
  種別の判定は """ + L_kindforrel + r""" が行う。
</p>
<div class="example">
  <span class="example-label">procarray.c（抜粋・GlobalVisHorizonKindForRel）</span>
  <pre><code>if (rel == NULL || rel-&gt;rd_rel-&gt;relisshared || RecoveryInProgress())
    return VISHORIZON_SHARED;
else if (IsCatalogRelation(rel) || RelationIsAccessibleInLogicalDecoding(rel))
    return VISHORIZON_CATALOG;
else if (!RELATION_IS_LOCAL(rel))
    return VISHORIZON_DATA;
else
    return VISHORIZON_TEMP;</code></pre>
</div>
<p>
  <code>rel</code> が <code>NULL</code> のときは最も保守的な SHARED が返る。実際 <code>vacuum.c</code> では、
  個々のテーブル用に <code>OldestXmin = GetOldestNonRemovableTransactionId(rel)</code> を、
  新しい <code>relfrozenxid</code> 下限の算出には <code>GetOldestNonRemovableTransactionId(NULL)</code> を
  使い分けている。
</p>
<figure>
  <pre class="mermaid">
flowchart TB
    REL["対象リレーション"] --> KIND["GlobalVisHorizonKindForRel()"]
    KIND -->|SHARED| A["shared_oldest_nonremovable"]
    KIND -->|CATALOG| B["catalog_oldest_nonremovable"]
    KIND -->|DATA| C["data_oldest_nonremovable"]
    KIND -->|TEMP| D["temp_oldest_nonremovable"]
  </pre>
  <figcaption>図 5.1: リレーション種別から返す地平線へのマッピング</figcaption>
</figure>

<h2 id="sec-5-2">5.2　pg_subtrans の切り詰め</h2>
<p>
  <code>pg_subtrans</code>（サブトランザクションの親子関係を記録する SLRU）は、どこまで切り詰めてよいかに
  別の地平線を使う。可視性判定用ではなく """ + L_getrun + r""" が返す
  <code>oldest_considered_running</code> である。チェックポイント／リスタートポイント処理で
  <code>TruncateSUBTRANS(GetOldestTransactionIdConsideredRunning())</code> として呼ばれる
  （<code>xlog.c</code>）。
</p>
<div class="info"><strong>関連</strong>
  なぜ可視性用の地平線では駄目なのか。VACUUM 中のバックエンドは自分の xmin より新しい行が消えても
  困らない（だから shared/data 地平線では除外される）が、可視性判定のために <code>pg_subtrans</code> を
  参照する。よって <code>oldest_considered_running</code> は VACUUM 中プロセスも含めて算出され、
  これらが参照しうる範囲の <code>pg_subtrans</code> を残す。詳細は <a href="ch02.html#sec-2-2">2.2</a> を参照。
</div>

<h2 id="sec-5-3">5.3　hot_standby_feedback</h2>
<p>
  スタンバイは、自分のクエリが必要とするタプルをプライマリが消さないよう、xmin を上流へ送る
  （hot_standby_feedback）。walsender はそのために """ + L_getrepl + r""" を呼ぶ。
</p>
<div class="example">
  <span class="example-label">procarray.c（抜粋・GetReplicationHorizons）</span>
  <pre><code>ComputeXidHorizons(&amp;horizons);

/* shared_oldest_nonremovable ではなく raw を使う。
   data テーブルをより積極的に刈れるよう catalog_xmin を別送するため。 */
*xmin         = horizons.shared_oldest_nonremovable_raw;
*catalog_xmin = horizons.slot_catalog_xmin;</code></pre>
</div>
<p>
  ここで <code>shared_oldest_nonremovable</code> ではなく 3.5 で退避した
  <code>shared_oldest_nonremovable_raw</code> を使うのが肝心である。catalog_xmin を分けて送ることで、
  上流はカタログテーブルにアクセスするときだけその制限を適用でき、通常テーブルの不要タプルを
  より積極的に回収できる。
</p>
"""

# =========================================================================
ch6 = r"""
<p>
  最後に、ホライズンの動きを <code>psql</code> から観察する。""" + L_compute + r""" の結果は直接は
  覗けないが、その入力である各バックエンドの xmin/xid やスロットの xmin を通じて挙動を確認できる。
  以下の例は単一インスタンスで再現できる。
</p>

<h2 id="sec-6-1">6.1　backend_xmin を覗く</h2>
<p>
  あるセッションで（リピータブルリードの）スナップショットを保持すると、その xmin が
  <code>pg_stat_activity.backend_xmin</code> に現れる。これは """ + L_compute + r""" が MIN() を
  取る対象そのものである。
</p>
<div class="example">
  <span class="example-label">セッションA</span>
  <pre><code>BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT 1;          -- ここでスナップショットが確定する</code></pre>
</div>
<div class="example">
  <span class="example-label">セッションB（観察）</span>
  <pre><code>SELECT pid, state, backend_xmin
FROM pg_stat_activity
WHERE backend_xmin IS NOT NULL;</code></pre>
</div>
<div class="example">
  <span class="example-label">実行結果</span>
  <pre><code>  pid  | state               | backend_xmin
-------+---------------------+--------------
 28714 | idle in transaction |          742</code></pre>
</div>
<p>
  この <code>backend_xmin</code>（742）が生きている間、742 以降に削除されたタプルは VACUUM で回収されない。
  セッションA を <code>COMMIT</code> すると <code>backend_xmin</code> が消え、地平線が前進する。
</p>

<h2 id="sec-6-2">6.2　スロットによる引き戻し</h2>
<p>
  レプリケーションスロットは <code>xmin</code> / <code>catalog_xmin</code> を保持し、3.5 で見たとおり地平線を
  古い方へ引き戻す。物理スロットや論理スロットを作ると <code>pg_replication_slots</code> で確認できる。
</p>
<div class="example">
  <span class="example-label">SQL</span>
  <pre><code>SELECT slot_name, slot_type, xmin, catalog_xmin
FROM pg_replication_slots;</code></pre>
</div>
<div class="example">
  <span class="example-label">実行結果</span>
  <pre><code> slot_name | slot_type | xmin | catalog_xmin
-----------+-----------+------+--------------
 logical1  | logical   |      |          738</code></pre>
</div>
<p>
  論理スロットは <code>catalog_xmin</code>（738）を保持する。これが
  <code>shared_oldest_nonremovable</code> / <code>catalog_oldest_nonremovable</code> に反映され、カタログの
  不要タプルが 738 まで保持される。一方 <code>shared_oldest_nonremovable_raw</code> はこの影響を受けないため、
  通常テーブルはより積極的に刈れる（5.3）。
</p>

<h2 id="sec-6-3">6.3　巻き戻りと運用上の注意</h2>
<p>
  """ + L_compute + r""" のコメントは、計算値が<strong>呼び出しのたびに後退（巻き戻り）しうる</strong>ことを
  明言している。たとえば現在のデータベースに実行中 Tx が無ければ data 地平線は
  <code>latestCompletedXid</code> になるが、その後に開始した Tx の xmin が他データベースの古い Tx を含めば、
  次回はより小さい値が返る。これは保守的（古い側に倒す）であり安全だが、地平線が単調増加だと仮定して
  はならない。
</p>
<div class="warn"><strong>注意</strong>
  <ul>
    <li><strong>長時間トランザクション・放置された idle in transaction</strong>: その <code>backend_xmin</code> が
        地平線を押し下げ、テーブル膨張（bloat）を招く。<code>pg_stat_activity</code> で監視する。</li>
    <li><strong>取り残されたレプリケーションスロット</strong>: 消費されないスロットの <code>xmin</code> /
        <code>catalog_xmin</code> は無期限に地平線を引き戻す。不要なスロットは削除する。</li>
    <li><strong>walsender 由来の後退</strong>: スタンバイのフィードバックにより地平線が後退しうる。
        スロットを使わない場合、walsender が継続稼働している間しかデータは保護されない。</li>
  </ul>
</div>
<p>
  以上を通じて、""" + L_compute + r""" は「誰が何を見ているか」を ProcArray・KnownAssignedXids・
  スロットから集約し、VACUUM・<code>pg_subtrans</code>・レプリケーションという異なる目的に対して、
  それぞれ適切に保守的な地平線を一度の走査で供給する中核であることが分かる。
</p>
"""
