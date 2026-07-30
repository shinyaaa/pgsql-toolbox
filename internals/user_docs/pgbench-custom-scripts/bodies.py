"""pgbench カスタムスクリプト実践ガイドの本文。

CHAPTERS の各要素は build.py がそのままテンプレートへ差し込む。
本文中の出力例は PostgreSQL 18.4 上で実際に実行して採取したもの。
"""

CH01 = r"""
<div class="goal">
  <strong>🎯 この章のゴール</strong>
  <ul>
    <li>組み込みスクリプトで測れること・測れないことを説明できる</li>
    <li>カスタムスクリプトが「SQL・メタコマンド・変数」の3要素でできていることを理解する</li>
    <li><code>-f</code> と <code>-b</code>、および重み付けの関係を図で説明できる</li>
  </ul>
</div>

<div class="prereq">
  <strong>📋 前提</strong>
  <ul>
    <li>PostgreSQL 18 の <code>pgbench</code> が使えること（第2章で確認する）</li>
    <li><code>pgbench -i</code> でテーブルを初期化し、<code>-c</code> / <code>-T</code> で回した経験があること</li>
  </ul>
</div>

<h2 id="sec-1-1">1.1　組み込みスクリプトの限界</h2>

<p>
pgbench には3つの組み込みスクリプトが入っている。<code>-b list</code> で一覧できる。
</p>

<div class="example">
  <span class="example-label">入力（シェル）</span>
  <pre><code>pgbench -b list</code></pre>
</div>
<div class="example">
  <span class="example-label out">出力</span>
  <pre><code>Available builtin scripts:
      tpcb-like: &lt;builtin: TPC-B (sort of)&gt;
  simple-update: &lt;builtin: simple update&gt;
    select-only: &lt;builtin: select only&gt;</code></pre>
</div>

<p>
中身は <code>--show-script</code> で読める。既定で使われる <code>tpcb-like</code> は次のとおり。
</p>

<div class="example">
  <span class="example-label">入力（シェル）</span>
  <pre><code>pgbench --show-script=tpcb-like</code></pre>
</div>
<div class="example">
  <span class="example-label out">出力</span>
  <pre><code>-- tpcb-like: &lt;builtin: TPC-B (sort of)&gt;
\set aid random(1, 100000 * :scale)
\set bid random(1, 1 * :scale)
\set tid random(1, 10 * :scale)
\set delta random(-5000, 5000)
BEGIN;
UPDATE pgbench_accounts SET abalance = abalance + :delta WHERE aid = :aid;
SELECT abalance FROM pgbench_accounts WHERE aid = :aid;
UPDATE pgbench_tellers SET tbalance = tbalance + :delta WHERE tid = :tid;
UPDATE pgbench_branches SET bbalance = bbalance + :delta WHERE bid = :bid;
INSERT INTO pgbench_history (tid, bid, aid, delta, mtime) VALUES (:tid, :bid, :aid, :delta, CURRENT_TIMESTAMP);
END;</code></pre>
</div>

<p>
この出力自体が、カスタムスクリプトの完全なお手本になっている。<code>\set</code> で変数を作り、
<code>:aid</code> のように SQL へ埋め込み、<code>BEGIN;</code> 〜 <code>END;</code> で1トランザクションにまとめる、
という構造がそのまま自分のスクリプトでも使える。
</p>

<p>
一方で、組み込みスクリプトには次の限界がある。実務で測りたいものはたいていこの外側にある。
</p>

<table>
  <thead>
    <tr><th>測りたいもの</th><th>組み込みで測れるか</th></tr>
  </thead>
  <tbody>
    <tr><td>自分のアプリのテーブル・インデックスに対する負荷</td><td>測れない（<code>pgbench_*</code> 固定）</td></tr>
    <tr><td>読み 9 : 書き 1 のような現実的な比率</td><td>測れない（1スクリプト固定）</td></tr>
    <tr><td>ホットスポットのある偏ったアクセス</td><td>測れない（一様乱数のみ）</td></tr>
    <tr><td>前のクエリの結果を次のクエリに使う多段処理</td><td>測れない</td></tr>
    <tr><td>クライアントごとに違う振る舞い</td><td>測れない</td></tr>
    <tr><td>パイプライン（往復削減）の効果</td><td>測れない</td></tr>
  </tbody>
</table>

<p>
これらはすべて、<code>-f</code> でスクリプトファイルを渡すカスタムスクリプトで実現できる。
本ガイドはその書き方を扱う。
</p>

<h2 id="sec-1-2">1.2　カスタムスクリプトの構成要素</h2>

<p>
スクリプトファイルは次の3種類の行でできている。
</p>

<ol>
  <li><strong>SQL コマンド</strong> — セミコロンで終端する。複数行にまたがってよい。</li>
  <li><strong>メタコマンド</strong> — <code>\</code>（バックスラッシュ）で始まり、pgbench 自身が解釈する。
      <code>\set</code>、<code>\if</code>、<code>\gset</code> など。原則1行で終わる。</li>
  <li><strong>コメントと空行</strong> — <code>--</code> で始まる行と空行は無視される。</li>
</ol>

<p>
そして SQL の中には <code>:変数名</code> の形で変数を埋め込める。図 1.1 のように、
pgbench はメタコマンドを自分で処理し、SQL だけをサーバへ送る。
</p>

<figure>
  <pre class="mermaid">
flowchart LR
    F["スクリプトファイル<br/>(-f で指定)"] --> P["pgbench"]
    P -->|"メタコマンドは<br/>自分で処理"| V["変数テーブル<br/>:aid, :delta ..."]
    V -->|":変数 を値に置換"| P
    P -->|"SQL だけを送信"| S["PostgreSQL サーバ"]
    S -->|"結果"| P
    P --> R["レポート<br/>tps / latency"]
  </pre>
  <figcaption>図 1.1: メタコマンドは pgbench 側で処理され、SQL だけがサーバへ送られる</figcaption>
</figure>

<div class="tip">
  <strong>💡 ヒント</strong>
  変数名に使えるのは英字（非ラテン文字も可）・数字・アンダースコアで、先頭は数字以外。
  1つの SQL 文の中で使える変数は最大 255 個まで。
</div>

<h2 id="sec-1-3">1.3　実行の全体像と重み付け</h2>

<p>
pgbench にとっての<strong>1トランザクション＝スクリプトファイル1回の実行</strong>である。
スクリプトの中に <code>BEGIN;</code> / <code>END;</code> が無くても、pgbench は1回の実行を
1トランザクションとして数える（その場合、各 SQL が個別に自動コミットされる）。
</p>

<p>
<code>-f</code> と <code>-b</code> は<strong>何度でも指定でき</strong>、それぞれに
<code>@数値</code> で重みを付けられる。クライアントは毎回、重みに比例した確率でスクリプトを1本選び、
それを最後まで実行する。図 1.2 がその流れである。
</p>

<figure>
  <pre class="mermaid">
flowchart TD
    Start["クライアントがトランザクションを開始"] --> Pick{"重みに応じて<br/>スクリプトを1本選ぶ"}
    Pick -->|"重み 9"| A["ro.sql を最後まで実行"]
    Pick -->|"重み 1"| B["rw.sql を最後まで実行"]
    A --> Count["1トランザクションとして計上"]
    B --> Count
    Count --> Start
  </pre>
  <figcaption>図 1.2: 重み付き複数スクリプトの選択（<code>-f ro.sql@9 -f rw.sql@1</code> の場合）</figcaption>
</figure>

<p>
図 1.2 のように重みを付ければ「読み 90% ・書き 10%」といった比率を再現できる。
重みを省略すると 1 とみなされるので、<code>-f a.sql -f b.sql</code> なら 50:50 になる。
実際の指定方法と結果の読み方は第6章で扱う。
</p>

<div class="pitfall">
  <strong>⚠️ よくある落とし穴</strong>
  <code>@</code> の前後に空白を入れてはいけない。<code>-f ro.sql @9</code> のように離すと、
  <code>@9</code> が接続先データベース名として解釈されてしまう。<code>-f ro.sql@9</code> と続けて書く。
</div>

<div class="checkpoint">
  <strong>✅ チェックポイント</strong>
  <ul>
    <li><code>pgbench -b list</code> と <code>pgbench --show-script=tpcb-like</code> が実行できた</li>
    <li>スクリプトファイルが「SQL・メタコマンド・コメント」で構成されると説明できる</li>
    <li>「1トランザクション＝スクリプト1回の実行」であることを説明できる</li>
    <li><code>-f a.sql@9 -f b.sql@1</code> がどういう比率になるか答えられる</li>
  </ul>
</div>
"""

CH02 = r"""
<div class="goal">
  <strong>🎯 この章のゴール</strong>
  <ul>
    <li>この先すべての章で使う <code>bench</code> データベースを用意できる</li>
    <li>接続情報を環境変数にまとめ、以降のコマンドを短く書けるようにする</li>
    <li>スクリプトファイルの置き場所と、実行コマンドの基本形を決める</li>
  </ul>
</div>

<div class="prereq">
  <strong>📋 前提</strong>
  <ul>
    <li>PostgreSQL 18 のサーバが起動しており、テーブルを作成できる権限のあるユーザで接続できること</li>
    <li><code>pgbench</code> と <code>psql</code> にパスが通っていること</li>
  </ul>
</div>

<h2 id="sec-2-1">2.1　バージョンと接続を確認する</h2>

<p>
まず <code>pgbench</code> のバージョンを確認する。本ガイドは PostgreSQL 18 を対象にしている。
</p>

<div class="example">
  <span class="example-label">入力（シェル）</span>
  <pre><code>pgbench --version</code></pre>
</div>
<div class="example">
  <span class="example-label out">出力</span>
  <pre><code>pgbench (PostgreSQL) 18.4</code></pre>
</div>

<p>
以降のコマンドを短く保つため、接続情報を環境変数に入れておく。
値は自分の環境に合わせて読み替える。
</p>

<div class="example">
  <span class="example-label">入力（シェル）</span>
  <pre><code>export PGHOST=localhost
export PGPORT=5432
export PGUSER=postgres</code></pre>
</div>

<p>
サーバのバージョンも確認しておく。クライアント側の <code>pgbench</code> とサーバの
メジャーバージョンは揃っているほうが、機能差による混乱がない。
</p>

<div class="example">
  <span class="example-label">入力（シェル）</span>
  <pre><code>psql -tAc 'SELECT version();'</code></pre>
</div>
<div class="example">
  <span class="example-label out">出力</span>
  <pre><code>PostgreSQL 18.4 on x86_64-pc-linux-gnu, compiled by gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0, 64-bit</code></pre>
</div>

<div class="tip">
  <strong>💡 ヒント</strong>
  メタコマンドはバージョンによって使えるものが違う。<code>\syncpipeline</code> は PostgreSQL 17 以降、
  <code>permute()</code> 関数は 15 以降で追加された。古いサーバ／クライアントを相手にするときは、
  該当の章で注記しているバージョン条件を確認する。
</div>

<h2 id="sec-2-2">2.2　ベンチマーク用データベースを初期化する</h2>

<p>
第3章以降で使うデータベースを作り、<code>pgbench -i</code> で標準テーブルを投入する。
スケールファクタは 10（<code>pgbench_accounts</code> が 100 万行）にする。
</p>

<div class="handson">
  <div class="handson-head">⌨️ ハンズオン: bench データベースを作る</div>
  <div class="handson-body">
    <ol class="steps">
      <li>
        <p>データベースを作成する。</p>
        <div class="example">
          <span class="example-label">入力（シェル）</span>
          <pre><code>createdb bench</code></pre>
        </div>
        <div class="example">
          <span class="example-label out">出力</span>
          <pre><code>（成功時は何も出力されない）</code></pre>
        </div>
      </li>
      <li>
        <p>スケールファクタ 10 で標準テーブルを初期化する。</p>
        <div class="example">
          <span class="example-label">入力（シェル）</span>
          <pre><code>pgbench -i -s 10 bench</code></pre>
        </div>
        <div class="example">
          <span class="example-label out">出力（抜粋）</span>
          <pre><code>dropping old tables...
NOTICE:  table "pgbench_accounts" does not exist, skipping
NOTICE:  table "pgbench_branches" does not exist, skipping
NOTICE:  table "pgbench_history" does not exist, skipping
NOTICE:  table "pgbench_tellers" does not exist, skipping
creating tables...
generating data (client-side)...
100000 of 1000000 tuples (10%) of pgbench_accounts done (elapsed 0.02 s, remaining 0.22 s)
...
1000000 of 1000000 tuples (100%) of pgbench_accounts done (elapsed 2.14 s, remaining 0.00 s)
vacuuming...
creating primary keys...
done in 3.90 s (drop tables 0.00 s, create tables 0.01 s, client-side generate 2.92 s, vacuum 0.21 s, primary keys 0.77 s).</code></pre>
        </div>
      </li>
      <li>
        <p>行数を確認する。<code>-s 10</code> なら <code>pgbench_accounts</code> は 100 万行になる。</p>
        <div class="example">
          <span class="example-label">入力（シェル）</span>
          <pre><code>psql -d bench -c 'SELECT count(*) FROM pgbench_accounts;'</code></pre>
        </div>
        <div class="example">
          <span class="example-label out">出力</span>
          <pre><code>  count
---------
 1000000
(1 row)</code></pre>
        </div>
      </li>
    </ol>
  </div>
</div>

<p>
<code>NOTICE: table ... does not exist, skipping</code> は初回実行時に必ず出る。
削除対象が無いだけなので問題ない。
</p>

<div class="pitfall">
  <strong>⚠️ 破壊的操作に注意</strong>
  <code>pgbench -i</code> は既存の <code>pgbench_accounts</code> / <code>pgbench_branches</code> /
  <code>pgbench_history</code> / <code>pgbench_tellers</code> を<strong>削除してから作り直す</strong>。
  本番や共有のデータベースに対して実行しないこと。専用のデータベースを用意する。
</div>

<h2 id="sec-2-3">2.3　作業ディレクトリと実行の基本形</h2>

<p>
スクリプトファイルを置く作業ディレクトリを決めておく。以降の章では、このディレクトリで
スクリプトを作成し、そこから <code>pgbench</code> を実行する前提で書く。
</p>

<div class="example">
  <span class="example-label">入力（シェル）</span>
  <pre><code>mkdir -p ~/pgbench-work
cd ~/pgbench-work</code></pre>
</div>

<p>
カスタムスクリプトを実行するコマンドの基本形は次のとおり。本ガイドではこの形を繰り返し使う。
</p>

<div class="example">
  <span class="example-label">入力（シェル）</span>
  <pre><code>pgbench -n -f スクリプト.sql -s 10 -c 4 -j 2 -T 10 -r bench</code></pre>
</div>

<table>
  <thead>
    <tr><th>オプション</th><th>意味</th><th>カスタムスクリプトでの注意</th></tr>
  </thead>
  <tbody>
    <tr><td><code>-n</code></td><td>実行前の VACUUM を省略</td>
        <td>自前テーブルを使うなら必須。<code>pgbench_*</code> が無いとエラーになるため</td></tr>
    <tr><td><code>-f</code></td><td>スクリプトファイルを指定</td><td>複数指定可。<code>@重み</code> を付けられる</td></tr>
    <tr><td><code>-s</code></td><td><code>:scale</code> の値を指定</td>
        <td><strong><code>-f</code> では自動検出されない</strong>。3.4 節で詳述</td></tr>
    <tr><td><code>-c</code></td><td>同時クライアント数</td><td>—</td></tr>
    <tr><td><code>-j</code></td><td>pgbench 側のスレッド数</td><td>クライアント数が多いときは増やす</td></tr>
    <tr><td><code>-T</code></td><td>実行秒数</td><td><code>-t</code>（回数指定）とは排他</td></tr>
    <tr><td><code>-r</code></td><td>ステートメント別のレポートを出す</td><td>スクリプトのどこが遅いかを見る</td></tr>
  </tbody>
</table>

<div class="pitfall">
  <strong>⚠️ よくある落とし穴</strong>
  <p>pgbench は実行前に <code>pgbench_branches</code> / <code>pgbench_tellers</code> /
  <code>pgbench_history</code> を VACUUM しようとする。
  自前のテーブルだけを使うスクリプトでこれらが存在しないと、次のエラーが出る。</p>
  <div class="example">
    <span class="example-label out">出力</span>
    <pre><code>starting vacuum...pgbench: error: ERROR:  relation "pgbench_branches" does not exist
pgbench: detail: (ignoring this error and continuing anyway)</code></pre>
  </div>
  <p><code>ignoring this error and continuing anyway</code> とあるとおり、
  <strong>これは致命的ではなく、計測自体は最後まで走って終了ステータスも 0 になる</strong>。
  とはいえ実行のたびにエラーが並ぶのは紛らわしく、無駄な VACUUM も走る。
  カスタムスクリプトでは <code>-n</code> を付ける習慣にしておくとよい。</p>
</div>

<div class="checkpoint">
  <strong>✅ チェックポイント</strong>
  <ul>
    <li><code>pgbench --version</code> が 18 系を返す</li>
    <li><code>bench</code> データベースがあり、<code>pgbench_accounts</code> が 100 万行ある</li>
    <li><code>PGHOST</code> / <code>PGPORT</code> / <code>PGUSER</code> を設定し、<code>psql -d bench</code> で接続できる</li>
    <li>作業ディレクトリを作り、そこに移動した</li>
  </ul>
</div>
"""

CH03 = r"""
<div class="goal">
  <strong>🎯 この章のゴール</strong>
  <ul>
    <li>最小のカスタムスクリプトを書いて <code>-f</code> で実行できる</li>
    <li>実行結果の各行が何を意味するか読める</li>
    <li><code>-r</code> でステートメント単位に分解して、どこが遅いか特定できる</li>
    <li><code>:scale</code> が自動では設定されないことを、実測で確認できる</li>
  </ul>
</div>

<div class="prereq">
  <strong>📋 前提</strong>
  <ul>
    <li>第2章で作った <code>bench</code> データベース（<code>-s 10</code> で初期化済み）</li>
    <li>作業ディレクトリにいること（<code>cd ~/pgbench-work</code>）</li>
    <li><code>PGHOST</code> / <code>PGPORT</code> / <code>PGUSER</code> が設定済みであること</li>
  </ul>
</div>

<h2 id="sec-3-1">3.1　最小のカスタムスクリプトを書いて動かす</h2>

<p>
まず「ランダムな口座を1件 SELECT する」だけのスクリプトを書く。これが最小の end-to-end 例になる。
</p>

<div class="handson">
  <div class="handson-head">⌨️ ハンズオン: 最初のカスタムスクリプト</div>
  <div class="handson-body">
    <ol class="steps">
      <li>
        <p><code>myselect.sql</code> を作成する。1行目がメタコマンド、3行目が SQL である。</p>
        <div class="example">
          <span class="example-label">入力（シェル）</span>
          <pre><code>cat &gt; myselect.sql &lt;&lt;'EOF'
-- 口座を1件ランダムに引く
\set aid random(1, 100000 * :scale)
SELECT abalance FROM pgbench_accounts WHERE aid = :aid;
EOF</code></pre>
        </div>
      </li>
      <li>
        <p>まず 10 トランザクションだけ実行して、動くことを確かめる。</p>
        <div class="example">
          <span class="example-label">入力（シェル）</span>
          <pre><code>pgbench -n -f myselect.sql -t 10 bench</code></pre>
        </div>
        <div class="example">
          <span class="example-label out">出力</span>
          <pre><code>pgbench (18.4)
transaction type: myselect.sql
scaling factor: 1
query mode: simple
number of clients: 1
number of threads: 1
maximum number of tries: 1
number of transactions per client: 10
number of transactions actually processed: 10/10
number of failed transactions: 0 (0.000%)
latency average = 0.310 ms
initial connection time = 3.171 ms
tps = 3224.766204 (without initial connection time)</code></pre>
        </div>
      </li>
    </ol>
  </div>
</div>

<p>
<code>number of transactions actually processed: 10/10</code> と
<code>number of failed transactions: 0</code> が出ていれば成功である。
</p>

<h2 id="sec-3-2">3.2　出力を読む</h2>

<p>
出力の各行の意味は次のとおり。カスタムスクリプトで特に注目すべき行を太字にしてある。
</p>

<table>
  <thead>
    <tr><th>行</th><th>意味</th></tr>
  </thead>
  <tbody>
    <tr><td><code>transaction type</code></td>
        <td><strong>使われたスクリプト名</strong>。<code>-f</code> ならファイル名、組み込みなら <code>&lt;builtin: ...&gt;</code></td></tr>
    <tr><td><code>scaling factor</code></td>
        <td><strong><code>:scale</code> に入る値</strong>。<code>-f</code> のときは <code>-s</code> を渡さないと 1 のまま（3.4 節）</td></tr>
    <tr><td><code>query mode</code></td><td>プロトコル。<code>-M</code> で simple / extended / prepared を選ぶ</td></tr>
    <tr><td><code>maximum number of tries</code></td><td><code>--max-tries</code> の値。1 なら再試行しない</td></tr>
    <tr><td><code>actually processed</code></td>
        <td><strong>実際に完了した数 / 予定数</strong>。分子が小さければ途中で abort している</td></tr>
    <tr><td><code>failed transactions</code></td><td>直列化エラー・デッドロックで失敗した数</td></tr>
    <tr><td><code>latency average</code></td><td>1トランザクション（＝スクリプト1回）の平均所要時間</td></tr>
    <tr><td><code>initial connection time</code></td><td>接続確立にかかった時間。tps の計算からは除外される</td></tr>
    <tr><td><code>tps</code></td><td>1秒あたりのトランザクション数。<strong>スクリプト1回が1トランザクション</strong></td></tr>
  </tbody>
</table>

<div class="pitfall">
  <strong>⚠️ よくある落とし穴</strong>
  tps は「SQL 文の実行回数」ではなく「<strong>スクリプトの実行回数</strong>」である。
  1本のスクリプトに SELECT を10個書けば、同じサーバ負荷でも tps は約 1/10 に見える。
  スクリプト構成が違うもの同士で tps を直接比べてはいけない。
</div>

<h2 id="sec-3-3">3.3　<code>-r</code> でステートメント単位に分解する</h2>

<p>
<code>-r</code> を付けると、スクリプトの各行ごとの平均レイテンシが出る。
どのメタコマンド・どの SQL が時間を食っているかがひと目でわかる。
</p>

<div class="example">
  <span class="example-label">入力（シェル）</span>
  <pre><code>pgbench -n -f myselect.sql -c 4 -T 5 -r bench</code></pre>
</div>
<div class="example">
  <span class="example-label out">出力</span>
  <pre><code>pgbench (18.4)
transaction type: myselect.sql
scaling factor: 1
query mode: simple
number of clients: 4
number of threads: 1
maximum number of tries: 1
duration: 5 s
number of transactions actually processed: 135408
number of failed transactions: 0 (0.000%)
latency average = 0.147 ms
initial connection time = 10.985 ms
tps = 27140.364317 (without initial connection time)
statement latencies in milliseconds and failures:
         0.000           0 \set aid random(1, 100000 * :scale)
         0.137           0 SELECT abalance FROM pgbench_accounts WHERE aid = :aid;</code></pre>
</div>

<p>
最後のブロックが <code>-r</code> による追加出力である。左から
<strong>平均レイテンシ（ミリ秒）</strong>、<strong>失敗回数</strong>、<strong>コマンドの中身</strong>。
<code>\set</code> は pgbench 内部で完結するので 0.000 ms、
サーバへの往復がある SELECT が 0.137 ms を占めている。
</p>

<div class="tip">
  <strong>💡 ヒント</strong>
  <code>--max-tries</code> が 1 以外のときは、失敗回数の右に<strong>再試行回数</strong>の列が増え、
  見出しも <code>statement latencies in milliseconds, failures and retries:</code> に変わる。
  列数が変わるので、出力をスクリプトで解析するときは見出し行で判別する。
</div>

<div class="pitfall">
  <strong>⚠️ 計測オーバーヘッド</strong>
  <code>-r</code> はステートメントごとに時刻を取るため、それ自体が実行を遅くする。
  最終的な tps を報告するときは <code>-r</code> 無しで測り直す。
  <code>-r</code> の有無で tps を比べれば、オーバーヘッドがどれくらいか自分の環境で確認できる。
</div>

<h2 id="sec-3-4">3.4　<code>:scale</code> の罠</h2>

<p>
3.1 の出力をもう一度見てほしい。<code>-s 10</code> で初期化したのに
<code>scaling factor: 1</code> と表示されていた。これは表示だけの問題ではなく、
スクリプト中の <code>:scale</code> が実際に 1 になっている。
</p>

<p>
<strong>組み込みスクリプトは <code>pgbench_branches</code> の行数からスケールを自動検出するが、
<code>-f</code> のカスタムスクリプトは検出しない。</strong>
pgbench は自前スクリプトがどのテーブルを使うか知らないためである。
図 3.1 がその分かれ道である。
</p>

<figure>
  <pre class="mermaid">
flowchart TD
    Start["pgbench 起動"] --> Q1{"-s を指定したか"}
    Q1 -->|"はい"| Use["指定した値を :scale に使う"]
    Q1 -->|"いいえ"| Q2{"スクリプトの種類"}
    Q2 -->|"組み込み (-b)"| Auto["pgbench_branches の<br/>行数から自動検出"]
    Q2 -->|"カスタム (-f)"| One[":scale は 1 のまま"]
    Auto --> Use
    One --> Warn["触る範囲が狭まり<br/>数字が良く出すぎる"]
  </pre>
  <figcaption>図 3.1: <code>:scale</code> の値が決まる経路。<code>-f</code> で <code>-s</code> を省くと 1 になる</figcaption>
</figure>

<div class="handson">
  <div class="handson-head">⌨️ ハンズオン: 触られる範囲が変わることを確かめる</div>
  <div class="handson-body">
    <ol class="steps">
      <li>
        <p>引いた <code>aid</code> を記録するテーブルとスクリプトを用意する。</p>
        <div class="example">
          <span class="example-label">入力（シェル）</span>
          <pre><code>psql -q -d bench -c 'DROP TABLE IF EXISTS touched;
  CREATE UNLOGGED TABLE touched(kind text, aid int);'

cat &gt; touch.sql &lt;&lt;'EOF'
\set aid random(1, 100000 * :scale)
INSERT INTO touched VALUES (:kind, :aid);
EOF</code></pre>
        </div>
      </li>
      <li>
        <p><code>-s</code> 無しと <code>-s 10</code> 付きで、それぞれ 3000 回実行する。</p>
        <div class="example">
          <span class="example-label">入力（シェル）</span>
          <pre><code>pgbench -n -f touch.sql -t 3000 -D kind="'no_s'"   bench &gt; /dev/null
pgbench -n -f touch.sql -t 3000 -D kind="'with_s'" -s 10 bench &gt; /dev/null</code></pre>
        </div>
      </li>
      <li>
        <p>触られた <code>aid</code> の範囲を比べる。</p>
        <div class="example">
          <span class="example-label">入力（シェル）</span>
          <pre><code>psql -d bench -c 'SELECT kind, min(aid), max(aid), count(*)
  FROM touched GROUP BY kind ORDER BY kind;'</code></pre>
        </div>
        <div class="example">
          <span class="example-label out">出力</span>
          <pre><code>  kind  | min |  max   | count
--------+-----+--------+-------
 no_s   |  30 |  99998 |  3000
 with_s | 789 | 999968 |  3000
(2 rows)</code></pre>
        </div>
      </li>
    </ol>
  </div>
</div>

<p>
<code>-s</code> 無しでは <code>aid</code> が 10 万までしか出ておらず、100 万行のうち
先頭 10% しか触っていない。テーブル全体ではなく先頭だけを繰り返し読むので、
その部分だけが共有バッファに乗り、<strong>実際より良い数字が出てしまう</strong>。
</p>

<div class="pitfall">
  <strong>⚠️ 最重要の落とし穴</strong>
  カスタムスクリプトで <code>:scale</code> を使うなら、<code>-s</code> を<strong>必ず明示する</strong>。
  値は初期化時の <code>-s</code> と揃える。揃っているかどうかは、実行直後の
  <code>scaling factor:</code> 行で毎回確認する習慣にするとよい。
</div>

<div class="tip">
  <strong>💡 ヒント</strong>
  そもそも <code>:scale</code> に頼らず、範囲を <code>-D</code> で明示的に渡す書き方もある。
  <code>\set aid random(1, :nrows)</code> と書いて <code>-D nrows=1000000</code> で渡せば、
  スケールの取り違えは起きない。自前スキーマを測るときはこちらのほうが確実である。
</div>

<div class="checkpoint">
  <strong>✅ チェックポイント</strong>
  <ul>
    <li><code>myselect.sql</code> を <code>-f</code> で実行し、<code>10/10</code> 完了を確認した</li>
    <li>出力の <code>transaction type</code> / <code>scaling factor</code> / <code>tps</code> の意味を説明できる</li>
    <li><code>-r</code> を付けて、SELECT 行に時間が集中していることを確認した</li>
    <li><code>-s</code> の有無で <code>max(aid)</code> が 10 倍変わることを自分の環境で再現した</li>
  </ul>
</div>
"""

CH04 = r"""
<div class="goal">
  <strong>🎯 この章のゴール</strong>
  <ul>
    <li><code>\set</code> の式で計算・比較・条件式を書き、<code>debug()</code> で値を確認できる</li>
    <li>自動変数（<code>:client_id</code> など）と <code>-D</code> を使い分けられる</li>
    <li>用途に応じて4つの乱数分布を選べる</li>
    <li><code>permute()</code> で「偏りは保ったまま、場所の相関だけ壊す」ことができる</li>
  </ul>
</div>

<div class="prereq">
  <strong>📋 前提</strong>
  <ul>
    <li>第3章までの環境（<code>bench</code> データベース、作業ディレクトリ）を引き継ぐ</li>
    <li>第3章で作った <code>myselect.sql</code> があること</li>
  </ul>
</div>

<h2 id="sec-4-1">4.1　<code>\set</code> と式の評価</h2>

<p>
<code>\set 変数名 式</code> で変数に値を入れる。式には整数・浮動小数・真偽値・<code>NULL</code>、
変数参照、演算子、関数呼び出し、SQL の <code>CASE</code> 式が書ける。
評価は<strong>すべて pgbench 側</strong>で行われ、サーバへは送られない。
</p>

<p>
式の結果を確かめたいときは <code>debug()</code> 関数を使う。引数をそのまま返しつつ、
値と型を標準エラー出力へ書き出す。
</p>

<div class="handson">
  <div class="handson-head">⌨️ ハンズオン: 式の評価結果を覗く</div>
  <div class="handson-body">
    <ol class="steps">
      <li>
        <p>いろいろな式を書いた <code>expr.sql</code> を作る。</p>
        <div class="example">
          <span class="example-label">入力（シェル）</span>
          <pre><code>cat &gt; expr.sql &lt;&lt;'EOF'
\set i 3 + 4 * 2
\set d double(:i) / 4
\set b :i &gt; 10
\set n CASE WHEN :i &gt; 100 THEN 1 ELSE NULL END
\set dummy debug(:i)
\set dummy debug(:d)
\set dummy debug(:b)
\set dummy debug(:n)
SELECT 1;
EOF</code></pre>
        </div>
      </li>
      <li>
        <p>1トランザクションだけ実行する。</p>
        <div class="example">
          <span class="example-label">入力（シェル）</span>
          <pre><code>pgbench -n -f expr.sql -t 1 bench</code></pre>
        </div>
        <div class="example">
          <span class="example-label out">出力（先頭部分）</span>
          <pre><code>pgbench (18.4)
debug(script=0,command=5): int 11
debug(script=0,command=6): double 2.75
debug(script=0,command=7): boolean true
debug(script=0,command=8): null
transaction type: expr.sql
scaling factor: 1
...</code></pre>
        </div>
      </li>
    </ol>
  </div>
</div>

<p>
<code>command=5</code> はスクリプト内の何番目のコマンドかを示す（1 始まり）。
型が <code>int</code> / <code>double</code> / <code>boolean</code> / <code>null</code> と
表示されるので、意図した型になっているかを確認できる。
<code>3 + 4 * 2</code> が 11 になっていることから、演算子の優先順位が SQL と同じであることもわかる。
</p>

<p>
使える演算子は SQL とほぼ同じで、優先順位・結合則も SQL に準じる。
</p>

<table>
  <thead>
    <tr><th>種類</th><th>演算子</th><th>備考</th></tr>
  </thead>
  <tbody>
    <tr><td>算術</td><td><code>+</code> <code>-</code> <code>*</code> <code>/</code> <code>%</code></td>
        <td>整数同士の <code>/</code> は整数除算。オーバーフローはエラーになる</td></tr>
    <tr><td>比較</td><td><code>=</code> <code>&lt;&gt;</code> <code>&lt;</code> <code>&lt;=</code> <code>&gt;</code> <code>&gt;=</code></td>
        <td>結果は boolean</td></tr>
    <tr><td>論理</td><td><code>AND</code> <code>OR</code> <code>NOT</code></td><td>—</td></tr>
    <tr><td>ビット</td><td><code>&amp;</code> <code>|</code> <code>#</code> <code>~</code> <code>&lt;&lt;</code> <code>&gt;&gt;</code></td>
        <td><code>#</code> は XOR</td></tr>
    <tr><td>NULL 判定</td><td><code>IS NULL</code> <code>IS NOT NULL</code> <code>ISNULL</code> <code>NOTNULL</code></td><td>—</td></tr>
  </tbody>
</table>

<div class="tip">
  <strong>💡 ヒント</strong>
  条件判定では<strong>0 以外の数値が真、0 と NULL が偽</strong>として扱われる。
  <code>\if</code> の条件式もこの規則に従う。
</div>

<p>
式が長いときは、行末にバックスラッシュを置いて次の行へ続けられる。
</p>

<div class="example">
  <span class="example-label">入力（スクリプト内）</span>
  <pre><code>\set aid (1021 * random(1, 100000 * :scale)) % \
           (100000 * :scale) + 1</code></pre>
</div>

<h2 id="sec-4-2">4.2　自動変数と <code>-D</code></h2>

<p>
何も設定しなくても、次の4つの変数は最初から使える。
</p>

<table>
  <thead>
    <tr><th>変数</th><th>意味</th></tr>
  </thead>
  <tbody>
    <tr><td><code>:client_id</code></td><td>クライアントセッションを識別する番号。<strong>0 始まり</strong></td></tr>
    <tr><td><code>:scale</code></td><td>スケールファクタ。<code>-f</code> では <code>-s</code> を渡さないと 1（3.4 節）</td></tr>
    <tr><td><code>:default_seed</code></td><td><code>hash()</code> と <code>permute()</code> が既定で使う種</td></tr>
    <tr><td><code>:random_seed</code></td><td>乱数生成器の種。<code>--random-seed</code> で指定できる</td></tr>
  </tbody>
</table>

<div class="example">
  <span class="example-label">入力（シェル）</span>
  <pre><code>cat &gt; vars.sql &lt;&lt;'EOF'
\set dummy debug(:client_id)
\set dummy debug(:scale)
\set dummy debug(:default_seed)
\set dummy debug(:random_seed)
SELECT 1;
EOF

pgbench -n -f vars.sql -t 1 -c 2 -s 10 --random-seed=42 bench</code></pre>
</div>
<div class="example">
  <span class="example-label out">出力（先頭部分）</span>
  <pre><code>pgbench: setting random seed to 42
pgbench (18.4)
debug(script=0,command=1): int 0
debug(script=0,command=2): int 10
debug(script=0,command=3): int 4482733528210176216
debug(script=0,command=4): int 42
debug(script=0,command=1): int 1
debug(script=0,command=2): int 10
debug(script=0,command=3): int 4482733528210176216
debug(script=0,command=4): int 42</code></pre>
</div>

<p>
<code>-c 2</code> なので2クライアント分の出力が出ており、<code>:client_id</code> だけが
0 と 1 で異なる。<code>:scale</code> は <code>-s 10</code> を渡したので 10 になっている。
<code>:client_id</code> を使えば、クライアントごとに違うデータ範囲を触らせるといったことができる。
</p>

<div class="example">
  <span class="example-label">入力（スクリプト内）</span>
  <pre><code>-- クライアントごとに担当するテナントを変える
\set tenant :client_id % 8 + 1</code></pre>
</div>

<p>
自分で決めた変数は <code>-D 名前=値</code> でコマンドラインから渡せる。
これは <code>\set</code> より優先され、自動変数も上書きできる。
</p>

<div class="example">
  <span class="example-label">入力（シェル）</span>
  <pre><code>cat &gt; dvar.sql &lt;&lt;'EOF'
\set dummy debug(:nrows)
SELECT count(*) FROM pgbench_accounts WHERE aid &lt;= :nrows;
EOF

pgbench -n -f dvar.sql -t 1 -D nrows=500 bench</code></pre>
</div>
<div class="example">
  <span class="example-label out">出力（先頭部分）</span>
  <pre><code>pgbench (18.4)
debug(script=0,command=1): int 500
transaction type: dvar.sql
scaling factor: 1
...</code></pre>
</div>

<div class="pitfall">
  <strong>⚠️ 文字列を渡すとき</strong>
  <code>-D</code> の値は SQL へそのまま埋め込まれる。文字列を渡したいときは
  <code>-D kind="'no_s'"</code> のように<strong>SQL のクォートを値の中に含める</strong>必要がある。
  引用符を付け忘れると、識別子とみなされて
  <code>ERROR:  column "no_s" does not exist</code> になる。
</div>

<div class="pitfall">
  <strong>⚠️ セキュリティ上の注意</strong>
  変数は文字列として SQL に埋め込まれるだけで、エスケープはされない。
  外部から与えられた信用できない値を <code>-D</code> に渡さないこと。
</div>

<h2 id="sec-4-3">4.3　乱数分布を選ぶ</h2>

<p>
アクセス先の選び方は測定結果を大きく左右する。pgbench には4つの分布が用意されている。
</p>

<table>
  <thead>
    <tr><th>関数</th><th>分布</th><th>パラメータ</th><th>向いている場面</th></tr>
  </thead>
  <tbody>
    <tr><td><code>random(lb, ub)</code></td><td>一様</td><td>なし</td>
        <td>全体を均等に触る。キャッシュに乗りにくい最悪ケース寄り</td></tr>
    <tr><td><code>random_exponential(lb, ub, p)</code></td><td>指数</td><td><code>p &gt; 0</code></td>
        <td>下限側に偏らせる。<code>p</code> が大きいほど急峻</td></tr>
    <tr><td><code>random_gaussian(lb, ub, p)</code></td><td>正規</td><td><code>p &gt;= 2.0</code></td>
        <td>中央付近に集中させる</td></tr>
    <tr><td><code>random_zipfian(lb, ub, p)</code></td><td>Zipf</td><td><code>1.001 &lt;= p &lt;= 1000</code></td>
        <td>「一部が極端に人気」を再現。実サービスに近いことが多い</td></tr>
  </tbody>
</table>

<p>
図 4.1 を目安に選ぶとよい。
</p>

<figure>
  <pre class="mermaid">
flowchart TD
    Q1{"アクセスに<br/>偏りがあるか"} -->|"ない"| U["random()<br/>一様分布"]
    Q1 -->|"ある"| Q2{"偏りの形は"}
    Q2 -->|"少数のキーが<br/>極端に人気"| Z["random_zipfian()"]
    Q2 -->|"新しいデータほど<br/>よく読まれる"| E["random_exponential()"]
    Q2 -->|"中央値付近に集中"| G["random_gaussian()"]
    Z --> P{"人気キーが<br/>物理的に隣接すると<br/>都合が悪いか"}
    E --> P
    P -->|"はい"| PM["permute() を重ねる"]
    P -->|"いいえ"| Done["そのまま使う"]
  </pre>
  <figcaption>図 4.1: 乱数分布の選び方</figcaption>
</figure>

<p>
分布の違いは、実際に値を記録して数えるのが一番わかりやすい。
</p>

<div class="handson">
  <div class="handson-head">⌨️ ハンズオン: 一様分布と Zipf 分布を数えて比べる</div>
  <div class="handson-body">
    <ol class="steps">
      <li>
        <p>引いた値を記録するテーブルを作る。</p>
        <div class="example">
          <span class="example-label">入力（シェル）</span>
          <pre><code>psql -q -d bench -c 'DROP TABLE IF EXISTS dist_log;
  CREATE UNLOGGED TABLE dist_log(kind text, v int);'</code></pre>
        </div>
      </li>
      <li>
        <p>一様分布・Zipf 分布・Zipf + <code>permute()</code> の3本のスクリプトを作る。</p>
        <div class="example">
          <span class="example-label">入力（シェル）</span>
          <pre><code>cat &gt; dist_uniform.sql &lt;&lt;'EOF'
\set v random(1, 100)
INSERT INTO dist_log VALUES ('uniform', :v);
EOF

cat &gt; dist_zipfian.sql &lt;&lt;'EOF'
\set v random_zipfian(1, 100, 1.5)
INSERT INTO dist_log VALUES ('zipfian', :v);
EOF

cat &gt; dist_permuted.sql &lt;&lt;'EOF'
\set r random_zipfian(1, 100, 1.5)
\set v 1 + permute(:r, 100)
INSERT INTO dist_log VALUES ('permuted', :v);
EOF</code></pre>
        </div>
      </li>
      <li>
        <p>それぞれ 10000 回実行する。種を固定して再現性を持たせる。</p>
        <div class="example">
          <span class="example-label">入力（シェル）</span>
          <pre><code>for k in uniform zipfian permuted; do
  pgbench -n -f dist_$k.sql -t 10000 --random-seed=42 bench &gt; /dev/null
done</code></pre>
        </div>
      </li>
      <li>
        <p>それぞれの上位5値と出現回数を数える。</p>
        <div class="example">
          <span class="example-label">入力（シェル）</span>
          <pre><code>psql -d bench -c "
SELECT kind, v, count(*) AS n
FROM dist_log
WHERE (kind, v) IN (
  SELECT kind, v FROM (
    SELECT kind, v, count(*),
           row_number() OVER (PARTITION BY kind ORDER BY count(*) DESC) rn
    FROM dist_log GROUP BY kind, v) t WHERE rn &lt;= 5)
GROUP BY kind, v ORDER BY kind, n DESC;"</code></pre>
        </div>
        <div class="example">
          <span class="example-label out">出力</span>
          <pre><code>   kind   | v  |  n
----------+----+------
 permuted | 48 | 4108
 permuted | 20 | 1423
 permuted | 75 |  803
 permuted | 11 |  498
 permuted | 26 |  379
 uniform  | 16 |  123
 uniform  | 39 |  122
 uniform  | 40 |  116
 uniform  | 65 |  116
 uniform  | 57 |  116
 zipfian  |  1 | 4108
 zipfian  |  2 | 1423
 zipfian  |  3 |  803
 zipfian  |  4 |  498
 zipfian  |  5 |  379
(15 rows)</code></pre>
        </div>
      </li>
    </ol>
  </div>
</div>

<p>
読み方は次のとおり。<code>uniform</code> は 10000 回 ÷ 100 種 = 100 回前後に揃っており、
どの値も同じくらい出ている。<code>zipfian</code> は値 1 だけで 4108 回、
つまり全体の 41% を占め、以降 1423 → 803 → 498 と急速に減っている。
</p>

<h2 id="sec-4-4">4.4　<code>permute()</code> で相関を断つ</h2>

<p>
前節の出力で <code>zipfian</code> と <code>permuted</code> を見比べてほしい。
出現回数の列は <strong>4108 / 1423 / 803 / 498 / 379 と完全に同じ</strong>である。
違うのは、その回数を受け取る値が
<code>1, 2, 3, 4, 5</code> から <code>48, 20, 75, 11, 26</code> へ散らばっている点だけである。
</p>

<p>
これが <code>permute(i, size [, seed])</code> の働きである。
<code>0</code> 以上 <code>size</code> 未満の整数を疑似ランダムに並べ替え、
<code>i</code> がその並べ替え後で何番目に来るかを返す。ハッシュ関数と違い
<strong>衝突も抜けもない</strong>ため、偏りの度合いはそのままに、
どの値が人気になるかだけを変えられる。
</p>

<figure>
  <pre class="mermaid">
flowchart LR
    R["random_zipfian(1, size, 1.07)<br/>1 に強く偏った値"] --> PM["permute(:r, size)"]
    PM --> K["散らばった値<br/>偏りの度合いは同じ"]
    K --> SQL["WHERE id = :k"]
  </pre>
  <figcaption>図 4.2: 偏りを保ったまま、アクセス先の位置だけを散らす</figcaption>
</figure>

<p>
なぜこれが必要か。<code>random_zipfian(1, 1000000, 1.07)</code> をそのまま主キーに使うと、
人気の行は <code>id</code> が 1, 2, 3… の行、つまり<strong>物理的に先頭に固まっている行</strong>になる。
主キーが連番で挿入順と一致していれば、人気行は同じページに集まり、
現実にはあり得ないほどキャッシュ効率が良くなってしまう。
図 4.2 のように <code>permute()</code> を挟むと、人気行がテーブル全体へ散る。
</p>

<div class="example">
  <span class="example-label">入力（スクリプト内）</span>
  <pre><code>-- 一部のアカウントに負荷が集中する、SNS 的なワークロード
\set size 1000000
\set r random_zipfian(1, :size, 1.07)
\set k 1 + permute(:r, :size)
SELECT abalance FROM pgbench_accounts WHERE aid = :k;</code></pre>
</div>

<div class="tip">
  <strong>💡 ヒント</strong>
  <code>permute()</code> の並べ替えは <code>seed</code> で決まり、既定は <code>:default_seed</code>。
  同じ種なら毎回同じ並びになるので、実行間で結果を比較できる。
  逆に、独立した複数の偏りが欲しいときは
  <code>permute(:r, :size, :default_seed + 1)</code> のように種をずらす。
</div>

<div class="pitfall">
  <strong>⚠️ 添字のずれに注意</strong>
  <code>permute()</code> が返すのは <code>[0, size)</code> の値である。
  主キーが 1 始まりなら <code>1 + permute(...)</code> と <strong>+1 が要る</strong>。
  忘れると <code>aid = 0</code> を引き続けて 0 行ヒットになり、
  「速いが何も読んでいない」測定になる。
</div>

<div class="checkpoint">
  <strong>✅ チェックポイント</strong>
  <ul>
    <li><code>debug()</code> で式の値と型を確認できた</li>
    <li><code>:client_id</code> が <code>-c 2</code> のとき 0 と 1 になることを確認した</li>
    <li>一様分布と Zipf 分布で、上位値の出現回数がまったく違うことを再現した</li>
    <li><code>permute()</code> が「出現回数は同じまま値だけ散らす」ことを出力で確認した</li>
  </ul>
</div>
"""

CH05 = r"""
<div class="goal">
  <strong>🎯 この章のゴール</strong>
  <ul>
    <li><code>\gset</code> でクエリ結果を変数に取り込み、次のクエリで使える</li>
    <li><code>\if</code> でトランザクションの中身を条件で切り替えられる</li>
    <li><code>\sleep</code> / <code>\shell</code> / <code>\setshell</code> の使いどころがわかる</li>
    <li>パイプラインを使い、往復削減の効果を実測できる</li>
  </ul>
</div>

<div class="prereq">
  <strong>📋 前提</strong>
  <ul>
    <li>第4章までの環境を引き継ぐ（<code>bench</code> データベース、作業ディレクトリ）</li>
    <li><code>\syncpipeline</code> は PostgreSQL 17 以降で使える。それ以前では
        <code>\startpipeline</code> と <code>\endpipeline</code> のみ</li>
  </ul>
</div>

<h2 id="sec-5-1">5.1　<code>\gset</code> / <code>\aset</code> — クエリ結果を変数に取り込む</h2>

<p>
ここまでの変数はすべて pgbench 側で作った値だった。<code>\gset</code> を使うと、
<strong>サーバから返ってきた値</strong>を変数に取り込める。
「読んだ結果を使って次を決める」という多段の処理が書けるようになる。
</p>

<p>
使い方は、SQL の終端のセミコロンを <code>\gset</code> に<strong>置き換える</strong>こと。
返ってきた行の各列が、列名と同じ名前の変数になる。図 5.1 がその流れである。
</p>

<figure>
  <pre class="mermaid">
flowchart LR
    Q["SELECT abalance ... \gset"] -->|"送信"| S["サーバ"]
    S -->|"1行を返す"| G["\gset が列名で変数を作る"]
    G --> V[":abalance"]
    V --> Q2["次の SQL で :abalance を使う"]
  </pre>
  <figcaption>図 5.1: <code>\gset</code> はクエリ結果の列を同名の変数にする</figcaption>
</figure>

<div class="handson">
  <div class="handson-head">⌨️ ハンズオン: 読んだ値を次のクエリに使う</div>
  <div class="handson-body">
    <ol class="steps">
      <li>
        <p><code>gset.sql</code> を作る。SELECT の末尾がセミコロンではなく <code>\gset</code> であることに注意。</p>
        <div class="example">
          <span class="example-label">入力（シェル）</span>
          <pre><code>cat &gt; gset.sql &lt;&lt;'EOF'
\set aid random(1, 100000)
SELECT abalance FROM pgbench_accounts WHERE aid = :aid \gset
\set dummy debug(:abalance)
-- 前段の結果を次のクエリに使う
SELECT count(*) FROM pgbench_accounts WHERE abalance = :abalance;
EOF</code></pre>
        </div>
      </li>
      <li>
        <p>2トランザクション実行する。</p>
        <div class="example">
          <span class="example-label">入力（シェル）</span>
          <pre><code>pgbench -n -f gset.sql -t 2 --random-seed=42 bench</code></pre>
        </div>
        <div class="example">
          <span class="example-label out">出力（先頭部分）</span>
          <pre><code>pgbench: setting random seed to 42
pgbench (18.4)
debug(script=0,command=3): int 0
debug(script=0,command=3): int 0
transaction type: gset.sql
scaling factor: 1
...</code></pre>
        </div>
      </li>
    </ol>
  </div>
</div>

<p>
<code>:abalance</code> に 0 が入っている。初期化直後の <code>pgbench_accounts.abalance</code> は
全行 0 なので、これは期待どおりの結果である。
</p>

<p>
列名以外の名前にしたい場合や、複数のクエリをまとめたい場合は次のように書く。
<code>\;</code> で区切ると複数クエリを1回で送れる。
</p>

<div class="example">
  <span class="example-label">入力（シェル）</span>
  <pre><code>cat &gt; aset.sql &lt;&lt;'EOF'
SELECT 1 \;
SELECT 2 AS two, 3 AS three \gset p_
SELECT 4 AS four \; SELECT 5 AS five \aset
\set dummy debug(:p_two)
\set dummy debug(:p_three)
\set dummy debug(:four)
\set dummy debug(:five)
EOF

pgbench -n -f aset.sql -t 1 bench</code></pre>
</div>
<div class="example">
  <span class="example-label out">出力（先頭部分）</span>
  <pre><code>pgbench (18.4)
debug(script=0,command=3): int 2
debug(script=0,command=4): int 3
debug(script=0,command=5): int 4
debug(script=0,command=6): int 5
transaction type: aset.sql
query mode: simple
...</code></pre>
</div>

<p>
この例でわかることは3つある。
</p>
<ul>
  <li><code>\gset p_</code> のように<strong>プレフィックス</strong>を付けると、変数名は
      <code>:p_two</code> / <code>:p_three</code> になる。</li>
  <li><code>\gset</code> は <strong>直前のクエリだけ</strong>を対象にする。
      <code>SELECT 1 \;</code> の結果は捨てられている。</li>
  <li><code>\aset</code> は <code>\;</code> で連結した<strong>すべてのクエリ</strong>を対象にする。
      だから <code>:four</code> と <code>:five</code> の両方が取れている。</li>
</ul>

<table>
  <thead>
    <tr><th></th><th><code>\gset</code></th><th><code>\aset</code></th></tr>
  </thead>
  <tbody>
    <tr><td>対象</td><td>直前の1クエリ</td><td>連結されたすべてのクエリ</td></tr>
    <tr><td>0 行だったとき</td><td><strong>エラーで abort</strong></td><td>代入しない（変数は未定義のまま）</td></tr>
    <tr><td>複数行だったとき</td><td><strong>エラーで abort</strong></td><td>最後の行が残る</td></tr>
  </tbody>
</table>

<div class="pitfall">
  <strong>⚠️ よくある落とし穴</strong>
  <code>\gset</code> は行数に厳格である。0 行でも複数行でも即座に abort する。
  <div class="example">
    <span class="example-label out">出力</span>
    <pre><code>pgbench: error: client 0 script 0 command 0 query 0: expected one row, got 0
pgbench: error: Run was aborted; the above results are incomplete.</code></pre>
  </div>
  必ず 1 行返る保証がないなら、<code>LIMIT 1</code> を付けるか、
  行が無いこともあり得るなら <code>\aset</code> を使って変数の有無で判定する。
</div>

<h2 id="sec-5-2">5.2　<code>\if</code> で条件分岐する</h2>

<p>
<code>\if</code> / <code>\elif</code> / <code>\else</code> / <code>\endif</code> で、
実行する SQL を条件で切り替えられる。条件式は <code>\set</code> と同じ式が書け、
0 以外が真、0 と NULL が偽になる。入れ子にもできる。
</p>

<p>
これを使うと、1本のスクリプトの中で読み書きの比率を作れる。
（複数ファイルを重み付けする方法との使い分けは 6.1 節で述べる。）
</p>

<div class="example">
  <span class="example-label">入力（シェル）</span>
  <pre><code>cat &gt; ifelse.sql &lt;&lt;'EOF'
\set r random(1, 100)
\if :r &lt;= 80
  SELECT abalance FROM pgbench_accounts WHERE aid = :r;
\else
  UPDATE pgbench_accounts SET abalance = abalance + 1 WHERE aid = :r;
\endif
EOF

pgbench -n -f ifelse.sql -t 100 -r --random-seed=42 bench</code></pre>
</div>
<div class="example">
  <span class="example-label out">出力（末尾）</span>
  <pre><code>tps = 3424.774821 (without initial connection time)
statement latencies in milliseconds and failures:
         0.000           0 \set r random(1, 100)
         0.000           0 \if :r &lt;= 80
         0.120           0 SELECT abalance FROM pgbench_accounts WHERE aid = :r;
         0.000           0 \else
         1.067           0 UPDATE pgbench_accounts SET abalance = abalance + 1 WHERE aid = :r;
         0.001           0 \endif</code></pre>
</div>

<p>
<code>-r</code> の出力には両方の分岐が並ぶ。ここで表示される値は
<strong>実際に実行されたときだけの平均</strong>である。
つまり SELECT は 0.120 ms、UPDATE は 1.067 ms で、
UPDATE のほうが約9倍重いことがわかる。実行されなかった回はこの平均に含まれない。
</p>

<div class="pitfall">
  <strong>⚠️ 分岐の実行回数はレポートに出ない</strong>
  <code>-r</code> はレイテンシと失敗数しか出さないので、
  「SELECT が何回・UPDATE が何回実行されたか」はこの出力からは読み取れない。
  比率まで確認したいなら、複数ファイル＋重み付け（6.1 節）にしたほうが、
  スクリプト別レポートに実行回数と比率が出るぶん確実である。
</div>

<h2 id="sec-5-3">5.3　<code>\sleep</code> / <code>\shell</code> / <code>\setshell</code></h2>

<p>
<code>\sleep</code> はクライアントの思考時間（think time）を再現する。
単位は <code>us</code> / <code>ms</code> / <code>s</code> で、省略すると秒になる。
待ち時間には整数か、整数値を持つ変数を指定できる。
</p>

<p>
<code>\setshell</code> はシェルコマンドを実行して、その<strong>標準出力の整数</strong>を変数に入れる。
<code>\shell</code> は同じことをして結果を捨てる。
</p>

<div class="example">
  <span class="example-label">入力（シェル）</span>
  <pre><code>cat &gt; shell.sql &lt;&lt;'EOF'
\setshell n expr 10 + 5
\set dummy debug(:n)
\shell echo "hello from shell" &gt;&amp;2
\sleep 10 ms
SELECT 1;
EOF

pgbench -n -f shell.sql -t 1 bench</code></pre>
</div>
<div class="example">
  <span class="example-label out">出力（先頭部分）</span>
  <pre><code>pgbench (18.4)
debug(script=0,command=2): int 15
hello from shell
transaction type: shell.sql
scaling factor: 1
query mode: simple
...</code></pre>
</div>

<p>
<code>expr 10 + 5</code> の出力 15 が <code>:n</code> に入っている。
引数にコロンで始まる文字列を<strong>そのまま</strong>渡したいときは、
<code>::literal</code> のようにコロンを2つ重ねる。
</p>

<div class="pitfall">
  <strong>⚠️ 性能への影響</strong>
  <code>\setshell</code> / <code>\shell</code> はトランザクションごとにプロセスを起動するため非常に重い。
  <code>\sleep</code> も、その間クライアントは何もしない。
  どちらも tps を直接押し下げるので、スループットを測る本番計測では使わないこと。
  用途はセットアップや、意図的に間隔を空けたい負荷の再現に限る。
</div>

<h2 id="sec-5-4">5.4　パイプラインで往復を減らす</h2>

<p>
通常、pgbench は SQL を1つ送るたびに結果を待つ。
<code>\startpipeline</code> と <code>\endpipeline</code> で囲むと、
囲まれた SQL を<strong>まとめて送ってから</strong>結果を受け取る。
ネットワーク往復（RTT）が支配的なワークロードでは効果が大きい。図 5.2 がその違いである。
</p>

<figure>
  <pre class="mermaid">
sequenceDiagram
    participant C as pgbench
    participant S as サーバ
    Note over C,S: パイプラインなし（往復4回）
    C->>S: SELECT 1
    S-->>C: 結果
    C->>S: SELECT 2
    S-->>C: 結果
    Note over C,S: パイプラインあり（往復1回）
    C->>S: SELECT 1, SELECT 2 をまとめて送信
    S-->>C: 結果をまとめて返す
  </pre>
  <figcaption>図 5.2: パイプラインは結果を待たずに次の文を送る</figcaption>
</figure>

<div class="handson">
  <div class="handson-head">⌨️ ハンズオン: パイプラインの効果を測る</div>
  <div class="handson-body">
    <ol class="steps">
      <li>
        <p>同じ4本の SELECT を、パイプラインなし／ありで用意する。</p>
        <div class="example">
          <span class="example-label">入力（シェル）</span>
          <pre><code>cat &gt; nopipe.sql &lt;&lt;'EOF'
\set aid random(1, 100000)
SELECT abalance FROM pgbench_accounts WHERE aid = :aid;
SELECT abalance FROM pgbench_accounts WHERE aid = :aid + 1;
SELECT abalance FROM pgbench_accounts WHERE aid = :aid + 2;
SELECT abalance FROM pgbench_accounts WHERE aid = :aid + 3;
EOF

cat &gt; pipe.sql &lt;&lt;'EOF'
\set aid random(1, 100000)
\startpipeline
SELECT abalance FROM pgbench_accounts WHERE aid = :aid;
SELECT abalance FROM pgbench_accounts WHERE aid = :aid + 1;
SELECT abalance FROM pgbench_accounts WHERE aid = :aid + 2;
SELECT abalance FROM pgbench_accounts WHERE aid = :aid + 3;
\endpipeline
EOF</code></pre>
        </div>
      </li>
      <li>
        <p>両方を <code>-M extended</code> で実行して比べる。</p>
        <div class="example">
          <span class="example-label">入力（シェル）</span>
          <pre><code>pgbench -n -f nopipe.sql -M extended -c 1 -T 5 bench
pgbench -n -f pipe.sql   -M extended -c 1 -T 5 bench</code></pre>
        </div>
        <div class="example">
          <span class="example-label out">出力（該当行を抜粋）</span>
          <pre><code># nopipe.sql
latency average = 0.534 ms
tps = 1871.926382 (without initial connection time)

# pipe.sql
latency average = 0.230 ms
tps = 4355.363051 (without initial connection time)</code></pre>
        </div>
      </li>
    </ol>
  </div>
</div>

<p>
同じ4本の SELECT にもかかわらず、レイテンシが 0.534 ms から 0.230 ms へ、
tps は約 2.3 倍になった。これは同一ホスト内の接続での結果である。
ネットワーク越し（RTT が大きい環境）ほど差は広がる。
</p>

<p>
パイプラインの途中で同期を取りたいときは <code>\syncpipeline</code>（PostgreSQL 17 以降）を挟む。
パイプラインを終わらせずに sync メッセージだけを送る。
</p>

<div class="example">
  <span class="example-label">入力（シェル）</span>
  <pre><code>cat &gt; sync.sql &lt;&lt;'EOF'
\startpipeline
SELECT 1;
\syncpipeline
SELECT 2;
\endpipeline
EOF

pgbench -n -f sync.sql -M extended -t 1 -r bench</code></pre>
</div>
<div class="example">
  <span class="example-label out">出力（末尾）</span>
  <pre><code>statement latencies in milliseconds and failures:
         0.001           0 \startpipeline
         0.000           0 SELECT 1;
         0.003           0 \syncpipeline
         0.000           0 SELECT 2;
         0.394           0 \endpipeline</code></pre>
</div>

<p>
注目すべきは、個々の <code>SELECT</code> が 0.000 ms で、
<code>\endpipeline</code> に 0.394 ms が計上されている点である。
パイプライン中の SQL は送信するだけで結果を待たないため、
<strong>待ち時間はすべて <code>\endpipeline</code> にまとまる</strong>。
パイプライン内では、どの文が遅いかを <code>-r</code> で切り分けることはできない。
</p>

<div class="pitfall">
  <strong>⚠️ パイプラインの2大制約</strong>
  <p>1つ目。パイプラインは<strong>拡張プロトコルが必須</strong>である。
  <code>-M simple</code>（既定）のまま実行すると即座に abort する。
  <code>-M extended</code> か <code>-M prepared</code> を指定する。</p>
  <div class="example">
    <span class="example-label out">出力</span>
    <pre><code>pgbench: error: client 0 aborted in command 1 (startpipeline) of script 0; cannot use pipeline mode with the simple query protocol</code></pre>
  </div>
  <p>2つ目。パイプライン内では <code>\gset</code> / <code>\aset</code> が<strong>使えない</strong>。
  結果を受け取る時点ではまだ値が返っていないためである。</p>
  <div class="example">
    <span class="example-label out">出力</span>
    <pre><code>pgbench: error: client 0 aborted in command 1 (gset) of script 0; \gset is not allowed in pipeline mode</code></pre>
  </div>
</div>

<div class="checkpoint">
  <strong>✅ チェックポイント</strong>
  <ul>
    <li><code>\gset</code> で取り込んだ <code>:abalance</code> を次のクエリで使えた</li>
    <li><code>\gset</code> と <code>\aset</code> の、0 行・複数行のときの違いを説明できる</li>
    <li><code>\if</code> の両分岐が <code>-r</code> の出力に並ぶことを確認した</li>
    <li>パイプラインあり／なしで tps が変わることを自分の環境で再現した</li>
    <li>パイプラインで <code>-M simple</code> を使うとどうなるか説明できる</li>
  </ul>
</div>
"""

CH06 = r"""
<div class="goal">
  <strong>🎯 この章のゴール</strong>
  <ul>
    <li>複数スクリプトを重み付けで混ぜ、読み書き比率を再現できる</li>
    <li>スクリプト別レポートを読み、狙った比率になったか検証できる</li>
    <li><code>-M</code> でプロトコルを変えて比較できる</li>
    <li>ログを取り、後から分布や時系列を分析できる</li>
  </ul>
</div>

<div class="prereq">
  <strong>📋 前提</strong>
  <ul>
    <li>第5章までの環境を引き継ぐ</li>
    <li><code>bench</code> は <code>-s 10</code> で初期化済み。以降 <code>-s 10</code> を明示して実行する</li>
  </ul>
</div>

<h2 id="sec-6-1">6.1　複数スクリプトを重み付けで混ぜる</h2>

<p>
現実のワークロードは「読みが大半、書きが少し」であることが多い。
これを再現するには、読み用と書き用のスクリプトを別ファイルにして、
<code>-f ファイル@重み</code> で比率を指定する。
</p>

<div class="handson">
  <div class="handson-head">⌨️ ハンズオン: 読み 9 : 書き 1 のワークロード</div>
  <div class="handson-body">
    <ol class="steps">
      <li>
        <p>読み取り専用のスクリプトを作る。</p>
        <div class="example">
          <span class="example-label">入力（シェル）</span>
          <pre><code>cat &gt; ro.sql &lt;&lt;'EOF'
\set aid random(1, 100000 * :scale)
SELECT abalance FROM pgbench_accounts WHERE aid = :aid;
EOF</code></pre>
        </div>
      </li>
      <li>
        <p>更新用のスクリプトを作る。<code>\gset</code> で更新後の残高を受け取り、
           それを履歴に記録する多段処理にしてある。</p>
        <div class="example">
          <span class="example-label">入力（シェル）</span>
          <pre><code>cat &gt; rw.sql &lt;&lt;'EOF'
\set aid random(1, 100000 * :scale)
\set delta random(-5000, 5000)
BEGIN;
UPDATE pgbench_accounts SET abalance = abalance + :delta WHERE aid = :aid
  RETURNING abalance \gset
INSERT INTO pgbench_history (tid, bid, aid, delta, mtime)
  VALUES (1, 1, :aid, :delta, CURRENT_TIMESTAMP);
END;
EOF</code></pre>
        </div>
      </li>
      <li>
        <p>9 : 1 の重みで 10 秒間実行する。</p>
        <div class="example">
          <span class="example-label">入力（シェル）</span>
          <pre><code>pgbench -n -f ro.sql@9 -f rw.sql@1 -s 10 -c 4 -j 2 -T 10 -r bench</code></pre>
        </div>
      </li>
    </ol>
  </div>
</div>

<div class="tip">
  <strong>💡 <code>\if</code> と重み付けの使い分け</strong>
  1本のスクリプト内で <code>\if</code> を使っても比率は作れる（5.2 節）。
  違いは<strong>レポートの粒度</strong>である。ファイルを分けて重みを付けると、
  スクリプトごとに実行回数・比率・レイテンシ・tps が個別に出る。
  比率そのものを検証したいなら、ファイルを分けるほうがよい。
  一方、同じトランザクションの中で分岐したい場合（例: 在庫があれば購入、なければ何もしない）は
  <code>\if</code> でなければ書けない。
</div>

<h2 id="sec-6-2">6.2　スクリプト別レポートを読む</h2>

<p>
複数スクリプトを指定すると、全体のサマリの後にスクリプトごとの内訳が続く。
図 6.1 のように、レポートは3階層になっている。
</p>

<figure>
  <pre class="mermaid">
flowchart TD
    Run["pgbench -f ro.sql@9 -f rw.sql@1 -r"] --> All["全体サマリ<br/>合計 tps / 平均レイテンシ"]
    All --> S1["SQL script 1: ro.sql<br/>重み・実測比率・tps・レイテンシ"]
    All --> S2["SQL script 2: rw.sql<br/>重み・実測比率・tps・レイテンシ"]
    S1 --> D1["-r による<br/>ステートメント別レイテンシ"]
    S2 --> D2["-r による<br/>ステートメント別レイテンシ"]
  </pre>
  <figcaption>図 6.1: 複数スクリプト実行時のレポート構造</figcaption>
</figure>

<div class="example">
  <span class="example-label out">出力</span>
  <pre><code>pgbench (18.4)
transaction type: multiple scripts
scaling factor: 10
query mode: simple
number of clients: 4
number of threads: 2
maximum number of tries: 1
duration: 10 s
number of transactions actually processed: 128323
number of failed transactions: 0 (0.000%)
latency average = 0.312 ms
initial connection time = 4.882 ms
tps = 12832.788929 (without initial connection time)
SQL script 1: ro.sql
 - weight: 9 (targets 90.0% of total)
 - 115594 transactions (90.1% of total)
 - number of transactions actually processed: 115594 (tps = 11559.840430)
 - number of failed transactions: 0 (0.000%)
 - latency average = 0.156 ms
 - latency stddev = 0.091 ms
 - statement latencies in milliseconds and failures:
         0.001           0 \set aid random(1, 100000 * :scale)
         0.156           0 SELECT abalance FROM pgbench_accounts WHERE aid = :aid;
SQL script 2: rw.sql
 - weight: 1 (targets 10.0% of total)
 - 12718 transactions (9.9% of total)
 - number of transactions actually processed: 12718 (tps = 1271.848457)
 - number of failed transactions: 0 (0.000%)
 - latency average = 1.646 ms
 - latency stddev = 2.083 ms
 - statement latencies in milliseconds and failures:
         0.001           0 \set aid random(1, 100000 * :scale)
         0.000           0 \set delta random(-5000, 5000)
         0.089           0 BEGIN;
         0.184           0 UPDATE pgbench_accounts SET abalance = abalance + :delta WHERE aid = :aid
         0.144           0 INSERT INTO pgbench_history (tid, bid, aid, delta, mtime)
         1.228           0 END;</code></pre>
</div>

<p>
読みどころは次の3点である。
</p>

<ul>
  <li><strong><code>weight: 9 (targets 90.0% of total)</code> と実測の <code>90.1%</code> が一致している。</strong>
      狙った比率で動いたことがここで検証できる。ずれが大きいときは実行時間が短すぎる。</li>
  <li><strong>レイテンシはスクリプトごとに大きく違う。</strong>
      読みは 0.156 ms、書きは 1.646 ms で約10倍。全体平均の 0.312 ms は
      両者を混ぜた値なので、これだけ見ても実態はわからない。内訳を見ることが重要である。</li>
  <li><strong><code>rw.sql</code> では <code>END;</code>（コミット）が 1.228 ms で最も重い。</strong>
      UPDATE 自体は 0.184 ms なので、時間の大半は WAL の書き出しに使われている。
      ここが支配的なら、チューニングすべきはクエリではなくストレージや
      <code>synchronous_commit</code> といった設定である。</li>
</ul>

<div class="pitfall">
  <strong>⚠️ ステートメントの表示は1行目だけ</strong>
  上の <code>rw.sql</code> の内訳で <code>UPDATE ... WHERE aid = :aid</code> や
  <code>INSERT INTO pgbench_history (tid, bid, aid, delta, mtime)</code> が
  途中で切れているのは、複数行にまたがる SQL の<strong>先頭行だけが表示される</strong>ためである。
  レポートを見やすくしたいなら、1文を1行に収めて書くとよい。
</div>

<h2 id="sec-6-3">6.3　プロトコルを変えて比較する</h2>

<p>
<code>-M</code> で、SQL の送り方を3つから選べる。
同じスクリプトでも結果が変わるため、アプリの実装に合わせて選ぶ必要がある。
</p>

<table>
  <thead>
    <tr><th>モード</th><th>動作</th><th>対応するアプリ実装</th></tr>
  </thead>
  <tbody>
    <tr><td><code>simple</code>（既定）</td><td>変数を展開した SQL 文字列をそのまま送る</td>
        <td>文字列を組み立てて実行するだけの実装</td></tr>
    <tr><td><code>extended</code></td><td>パラメータを分離して送る。毎回パースされる</td>
        <td>プレースホルダを使うが文を再利用しない実装</td></tr>
    <tr><td><code>prepared</code></td><td>1回だけ prepare し、以降は再利用する</td>
        <td>プリペアドステートメントをキャッシュする実装</td></tr>
  </tbody>
</table>

<div class="example">
  <span class="example-label">入力（シェル）</span>
  <pre><code>for m in simple extended prepared; do
  echo "== $m"
  pgbench -n -f ro.sql -s 10 -M $m -c 4 -j 2 -T 8 bench | grep -E '^tps|^latency average'
done</code></pre>
</div>
<div class="example">
  <span class="example-label out">出力（整形して抜粋）</span>
  <pre><code>simple    latency average = 0.153 ms   tps = 26084.337402
extended  latency average = 0.163 ms   tps = 24478.960416
prepared  latency average = 0.109 ms   tps = 36568.177193</code></pre>
</div>

<p>
はっきりしているのは <code>prepared</code> が速いことで、
<code>simple</code> の約 1.4 倍の tps が出ている。毎回のパースとプラン作成が省けるためである。
</p>

<p>
一方、<code>simple</code> と <code>extended</code> の差はこの程度のクエリでは小さく、
<strong>実行するたびに順位が入れ替わる</strong>。手元で同じ計測を繰り返したところ、
<code>extended</code> が <code>simple</code> をわずかに上回る回もあった。
この2つの優劣を判断するには、より長い計測時間と複数回の試行が要る。
逆に言えば、<code>prepared</code> の差はそうした試行を経ても揺るがないほど大きい、ということである。
</p>

<div class="pitfall">
  <strong>⚠️ 数字の比較はプロトコルを揃えて</strong>
  <code>-M</code> の違いだけで tps は 1.5 倍変わり得る。
  設定変更やバージョン間の比較をするときは、必ず同じ <code>-M</code> で測る。
  そして、報告するときはどのモードで測ったかを併記する。
  パイプラインを使うスクリプトでは <code>-M simple</code> が使えないので（5.4 節）、
  比較対象も <code>extended</code> 以上に揃える必要がある。
</div>

<h2 id="sec-6-4">6.4　ログを取って分析する</h2>

<p>
<code>-P 秒</code> を付けると、実行中の進捗が定期的に表示される。
長時間の計測でウォームアップの終わりを見極めるのに使う。
</p>

<div class="example">
  <span class="example-label">入力（シェル）</span>
  <pre><code>pgbench -n -f ro.sql -s 10 -c 2 -T 4 -P 1 bench</code></pre>
</div>
<div class="example">
  <span class="example-label out">出力（進捗行のみ）</span>
  <pre><code>progress: 1.0 s, 14777.1 tps, lat 0.126 ms stddev 0.432, 0 failed
progress: 2.0 s, 15210.3 tps, lat 0.122 ms stddev 0.043, 0 failed
progress: 3.0 s, 14782.0 tps, lat 0.126 ms stddev 0.034, 0 failed
progress: 4.0 s, 13874.5 tps, lat 0.133 ms stddev 0.087, 0 failed</code></pre>
</div>

<p>
1秒目の stddev だけ 0.432 と大きい。接続直後でキャッシュが温まっていないためである。
この区間を計測から外したいなら、実行時間を長くして相対的な影響を薄める。
</p>

<p>
<code>-l</code> を付けると、1トランザクション1行のログファイルが作られる。
ファイル名は <code>pgbench_log.<em>PID</em></code>（<code>--log-prefix</code> で変更可）。
<code>-j</code> が2以上なら、スレッドごとに
<code>pgbench_log.<em>PID</em>.<em>連番</em></code> が追加で作られる。
</p>

<div class="example">
  <span class="example-label">入力（シェル）</span>
  <pre><code>pgbench -n -f ro.sql@9 -f rw.sql@1 -s 10 -c 2 -T 3 -l --log-prefix=mix_log bench
head -5 mix_log.*</code></pre>
</div>
<div class="example">
  <span class="example-label out">出力</span>
  <pre><code>0 1 2350 0 1785332426 296009
1 1 2320 0 1785332426 296024
0 2 221 0 1785332426 296246
1 2 191 0 1785332426 296249
0 3 165 0 1785332426 296415</code></pre>
</div>

<table>
  <thead>
    <tr><th>列</th><th>名前</th><th>意味</th></tr>
  </thead>
  <tbody>
    <tr><td>1</td><td><code>client_id</code></td><td>クライアント番号</td></tr>
    <tr><td>2</td><td><code>transaction_no</code></td><td>そのクライアントの何番目のトランザクションか</td></tr>
    <tr><td>3</td><td><code>time</code></td><td>所要時間（<strong>マイクロ秒</strong>）</td></tr>
    <tr><td>4</td><td><code>script_no</code></td><td><strong>使われたスクリプト番号（0 始まり）</strong></td></tr>
    <tr><td>5</td><td><code>time_epoch</code></td><td>完了時刻（Unix 時刻・秒）</td></tr>
    <tr><td>6</td><td><code>time_us</code></td><td>完了時刻の秒未満（マイクロ秒）</td></tr>
  </tbody>
</table>

<p>
第4列の <code>script_no</code> があるので、スクリプト別にレイテンシ分布を出せる。
上の出力の1行目は <code>script_no = 0</code>、所要時間 2350 マイクロ秒（2.35 ms）である。
</p>

<div class="tip">
  <strong>💡 ヒント</strong>
  <code>--rate</code> を付けると <code>schedule_lag</code> 列が、
  <code>--max-tries</code> を 1 以外にすると <code>retries</code> 列が末尾に増える。
  列位置を決め打ちで解析するときは、実行に使ったオプションとセットで管理する。
</div>

<p>
1行ずつでは多すぎる場合は <code>--aggregate-interval=秒</code> を使う。
指定秒ごとに1行へ集約される。
</p>

<div class="example">
  <span class="example-label">入力（シェル）</span>
  <pre><code>pgbench -n -f ro.sql -s 10 -c 2 -T 5 -l --aggregate-interval=1 --log-prefix=agg_log bench
cat agg_log.*</code></pre>
</div>
<div class="example">
  <span class="example-label out">出力</span>
  <pre><code>1785332429 10111 1301812 183985372 63 2079 0 0 0 0 0 0 0 0 0
1785332430 15426 1859925 242831475 62 2014 0 0 0 0 0 0 0 0 0
1785332431 16234 1861686 225733800 62 1296 0 0 0 0 0 0 0 0 0
1785332432 15147 1853918 244925040 61 2112 0 0 0 0 0 0 0 0 0
1785332433 15277 1852031 246182137 62 2183 0 0 0 0 0 0 0 0 0</code></pre>
</div>

<p>
先頭から順に <code>interval_start</code>（Unix 時刻）、<code>num_transactions</code>、
<code>sum_latency</code>、<code>sum_latency_2</code>（レイテンシの二乗和）、
<code>min_latency</code>、<code>max_latency</code>、以降は <code>--rate</code> 用の遅延と
失敗・再試行のカウンタが続く。
平均レイテンシは <code>sum_latency / num_transactions</code> で求まる。
2行目なら 1859925 / 15426 ≒ 120 マイクロ秒である。
</p>

<div class="checkpoint">
  <strong>✅ チェックポイント</strong>
  <ul>
    <li><code>-f ro.sql@9 -f rw.sql@1</code> を実行し、実測比率が 90% 前後になった</li>
    <li>スクリプト別レポートで、読みと書きのレイテンシ差を確認した</li>
    <li><code>-M prepared</code> が <code>-M simple</code> より速いことを再現した</li>
    <li><code>-l</code> のログを開き、第4列でスクリプトを見分けられた</li>
  </ul>
</div>
"""

CH07 = r"""
<div class="goal">
  <strong>🎯 この章のゴール</strong>
  <ul>
    <li>pgbench のエラーメッセージから原因を切り分けられる</li>
    <li>起動時エラーと実行中 abort を区別して対処できる</li>
    <li>「数字は出たが信用できない」パターンを見抜ける</li>
  </ul>
</div>

<div class="prereq">
  <strong>📋 前提</strong>
  <ul>
    <li>第6章までの環境を引き継ぐ</li>
  </ul>
</div>

<h2 id="sec-7-1">7.1　エラーの切り分け方</h2>

<p>
pgbench のエラーは、出るタイミングで大きく2つに分かれる。
図 7.1 の順に切り分けると早い。
</p>

<figure>
  <pre class="mermaid">
flowchart TD
    E["エラーが出た"] --> Q1{"ファイル名と<br/>行番号が出ているか"}
    Q1 -->|"はい"| Parse["構文エラー<br/>7.2 節へ"]
    Q1 -->|"いいえ"| Q2{"client N aborted<br/>と出ているか"}
    Q2 -->|"はい"| Run["実行中の中断<br/>7.3 節へ"]
    Q2 -->|"いいえ"| Conn["接続・ファイルの問題<br/>7.2 節へ"]
  </pre>
  <figcaption>図 7.1: エラーメッセージからの切り分け</figcaption>
</figure>

<p>
起動時のエラーは<strong>スクリプトを1回も実行せずに</strong>終わる。
実行中の abort は、途中まで動いてから止まるので
<code>number of transactions actually processed: 0/1</code> のような
不完全な結果が併せて表示され、最後に
<code>Run was aborted; the above results are incomplete.</code> が出る。
</p>

<h2 id="sec-7-2">7.2　起動時に失敗する</h2>

<p>
スクリプトが読み込めない・解釈できない場合のエラーである。
</p>

<h3 id="sec-7-2-1">ファイルが見つからない</h3>
<div class="example">
  <span class="example-label out">出力</span>
  <pre><code>pgbench: error: could not open file "nosuch.sql": No such file or directory</code></pre>
</div>
<p>
パスの誤りか、作業ディレクトリの取り違え。<code>ls</code> で確認する。
</p>

<h3 id="sec-7-2-2">メタコマンドの構文エラー</h3>
<div class="example">
  <span class="example-label">入力（<code>bad1.sql</code>）</span>
  <pre><code>\set x 1 +
SELECT 1;</code></pre>
</div>
<div class="example">
  <span class="example-label out">出力</span>
  <pre><code>pgbench: error: bad1.sql:1: syntax error in command "set"
\set x 1 +
          ^ error found here</code></pre>
</div>
<p>
<strong>ファイル名と行番号、そして問題箇所を指す <code>^</code> が出る</strong>ので原因は明確である。
式が途中で終わっている、括弧が閉じていない、といった単純な誤りが大半。
</p>

<div class="pitfall">
  <strong>⚠️ 継続行のバックスラッシュ</strong>
  式を複数行に分けるときは行末にバックスラッシュを置くが、
  その後ろに<strong>空白があってはいけない</strong>。見た目では気付きにくく、
  <code>syntax error in command "set"</code> になる。
</div>

<h2 id="sec-7-3">7.3　実行中に abort する</h2>

<p>
スクリプトの解釈は通ったが、実行中に止まるケース。以下は実際のメッセージである。
</p>

<h3 id="sec-7-3-1">SQL の構文エラー（セミコロン忘れ）</h3>
<div class="example">
  <span class="example-label">入力（<code>bad2.sql</code>）</span>
  <pre><code>SELECT 1
SELECT 2;</code></pre>
</div>
<div class="example">
  <span class="example-label out">出力</span>
  <pre><code>pgbench: error: client 0 script 0 aborted in command 0 query 0: ERROR:  syntax error at or near "2"
pgbench: error: Run was aborted; the above results are incomplete.</code></pre>
</div>
<p>
PostgreSQL 9.6 以降、SQL の終端は<strong>セミコロン</strong>である。改行では区切られない。
上の例は <code>SELECT 1 SELECT 2;</code> という1文としてサーバへ送られている。
</p>

<h3 id="sec-7-3-2">未定義の変数</h3>
<div class="example">
  <span class="example-label out">出力</span>
  <pre><code>pgbench: error: client 0 script 0 aborted in command 0 query 0: ERROR:  syntax error at or near ":"</code></pre>
</div>
<p>
未定義の変数は展開されず、<code>:nosuchvar</code> という文字列のままサーバへ送られる。
そのため「未定義変数」とは言われず、<strong>SQL の構文エラーとして現れる</strong>。
<code>:</code> の近くで構文エラーが出たら、まず変数名の綴りと
<code>-D</code> の渡し忘れを疑う。
</p>

<h3 id="sec-7-3-3">トランザクションを閉じずに終わる</h3>
<div class="example">
  <span class="example-label">入力（<code>noend.sql</code>）</span>
  <pre><code>BEGIN;
SELECT 1;</code></pre>
</div>
<div class="example">
  <span class="example-label out">出力</span>
  <pre><code>pgbench: error: client 0 aborted: end of script reached without completing the last transaction</code></pre>
</div>
<p>
<code>BEGIN;</code> を書いたら、必ず <code>END;</code>（または <code>COMMIT;</code>）で閉じる。
<code>\if</code> の分岐の片方にだけ <code>END;</code> を書いてしまう、という形で混入しやすい。
</p>

<h3 id="sec-7-3-4">その他の頻出エラー</h3>
<table>
  <thead>
    <tr><th>メッセージ</th><th>原因と対処</th></tr>
  </thead>
  <tbody>
    <tr>
      <td><code>expected one row, got 0</code></td>
      <td><code>\gset</code> の対象が0行。条件を見直すか <code>\aset</code> にする（5.1 節）</td>
    </tr>
    <tr>
      <td><code>expected one row, got 2</code></td>
      <td><code>\gset</code> の対象が複数行。<code>LIMIT 1</code> を付ける</td>
    </tr>
    <tr>
      <td><code>cannot use pipeline mode with the simple query protocol</code></td>
      <td><code>-M extended</code> か <code>-M prepared</code> を付ける（5.4 節）</td>
    </tr>
    <tr>
      <td><code>\gset is not allowed in pipeline mode</code></td>
      <td>パイプラインの外へ出す（5.4 節）</td>
    </tr>
    <tr>
      <td><code>relation "pgbench_branches" does not exist</code><br>
          （<code>ignoring this error and continuing anyway</code> が続く）</td>
      <td>実行前 VACUUM の対象が無いだけ。<strong>計測は中断されない</strong>。
          出力を静かにするには <code>-n</code> を付ける（2.3 節）</td>
    </tr>
  </tbody>
</table>

<h2 id="sec-7-4">7.4　数字が信用できないとき</h2>

<p>
エラーは出ないが結果が誤っている、というのが最も危険である。
チェックリストとして使ってほしい。
</p>

<table>
  <thead>
    <tr><th>症状</th><th>疑うこと</th></tr>
  </thead>
  <tbody>
    <tr>
      <td>tps が異様に高い</td>
      <td><strong><code>-s</code> の指定漏れ</strong>で狭い範囲しか触っていない（3.4 節）。
          <code>scaling factor:</code> 行を確認する。
          あるいは <code>permute()</code> の <code>+1</code> 忘れで 0 行ヒットになっている（4.4 節）</td>
    </tr>
    <tr>
      <td>実行のたびに結果がぶれる</td>
      <td>実行時間が短すぎる。<strong>数分以上</strong>回す。
          autovacuum やチェックポイントの影響も受ける</td>
    </tr>
    <tr>
      <td>回すたびに遅くなっていく</td>
      <td>更新系スクリプトで不要行が蓄積している。
          計測の前に <code>pgbench -i</code> で作り直すか、実行間隔を揃える</td>
    </tr>
    <tr>
      <td>クライアントを増やしても tps が伸びない</td>
      <td>サーバではなく <strong>pgbench 側が頭打ち</strong>の可能性。
          <code>-j</code> を増やす。それでも伸びなければ別ホストから実行する</td>
    </tr>
    <tr>
      <td>スクリプトを変えたら tps が激減した</td>
      <td>1スクリプトあたりの SQL 本数が増えていないか。
          tps はスクリプト実行回数であり、SQL 実行回数ではない（3.2 節）</td>
    </tr>
    <tr>
      <td>更新が異常に競合する</td>
      <td><code>-c</code> が <code>-s</code> より大きいと
          <code>pgbench_branches</code> の同じ行を奪い合う。<code>-s</code> を <code>-c</code> 以上にする</td>
    </tr>
  </tbody>
</table>

<div class="pitfall">
  <strong>⚠️ 数秒の計測を信じない</strong>
  公式ドキュメントも明記しているが、<strong>数秒で終わる計測結果は信用してはいけない</strong>。
  <code>-T</code> で最低でも数分は回し、複数回実行して再現するか確かめる。
  本ガイドの例が <code>-T 5</code> や <code>-t 10</code> と短いのは、
  動作を確認するための例だからである。実際の計測では時間を延ばすこと。
</div>

<div class="checkpoint">
  <strong>✅ チェックポイント</strong>
  <ul>
    <li>起動時エラーと実行中 abort を、メッセージから区別できる</li>
    <li><code>:</code> の近くの構文エラーを見たら変数名を疑える</li>
    <li><code>expected one row, got 0</code> の対処を2通り挙げられる</li>
    <li>tps が異様に高いとき、最初に <code>scaling factor:</code> 行を確認できる</li>
  </ul>
</div>
"""

CH08 = r"""
<div class="goal">
  <strong>🎯 この章のゴール</strong>
  <ul>
    <li>メタコマンド・関数・オプションを一覧から引ける</li>
    <li>カスタムスクリプトを書くときの手順を型として持てる</li>
  </ul>
</div>

<h2 id="sec-8-1">8.1　メタコマンド早見表</h2>

<table>
  <thead>
    <tr><th>メタコマンド</th><th>用途</th><th>注意</th></tr>
  </thead>
  <tbody>
    <tr><td><code>\set 変数 式</code></td><td>式を評価して変数に代入</td><td>評価は pgbench 側。行末 <code>\</code> で継続</td></tr>
    <tr><td><code>SQL \gset [接頭辞]</code></td><td>直前クエリの列を変数に</td><td><strong>1行ちょうど</strong>でないと abort。パイプライン内不可</td></tr>
    <tr><td><code>SQL \aset [接頭辞]</code></td><td>連結クエリ全部の列を変数に</td><td>0行なら代入なし、複数行なら最後の行。パイプライン内不可</td></tr>
    <tr><td><code>\if 式</code> / <code>\elif</code> / <code>\else</code> / <code>\endif</code></td>
        <td>条件分岐</td><td>0 と NULL が偽、それ以外が真。入れ子可</td></tr>
    <tr><td><code>\sleep 数 [us|ms|s]</code></td><td>思考時間の再現</td><td>単位省略時は秒。tps を下げる</td></tr>
    <tr><td><code>\setshell 変数 コマンド</code></td><td>シェルの出力（整数）を変数に</td><td>非常に重い。計測中は避ける</td></tr>
    <tr><td><code>\shell コマンド</code></td><td>シェル実行（結果は捨てる）</td><td>同上</td></tr>
    <tr><td><code>\startpipeline</code></td><td>パイプライン開始</td><td><strong><code>-M extended</code> 以上が必須</strong></td></tr>
    <tr><td><code>\syncpipeline</code></td><td>途中で sync を送る</td><td>PostgreSQL 17 以降</td></tr>
    <tr><td><code>\endpipeline</code></td><td>パイプライン終了</td><td>待ち時間はここに計上される</td></tr>
  </tbody>
</table>

<h2 id="sec-8-2">8.2　関数早見表</h2>

<table>
  <thead>
    <tr><th>関数</th><th>戻り値</th><th>説明</th></tr>
  </thead>
  <tbody>
    <tr><td><code>random(lb, ub)</code></td><td>integer</td><td>一様分布</td></tr>
    <tr><td><code>random_exponential(lb, ub, p)</code></td><td>integer</td><td>指数分布。<code>p &gt; 0</code>、大きいほど下限寄り</td></tr>
    <tr><td><code>random_gaussian(lb, ub, p)</code></td><td>integer</td><td>正規分布。<code>p &gt;= 2.0</code>、大きいほど中央寄り</td></tr>
    <tr><td><code>random_zipfian(lb, ub, p)</code></td><td>integer</td><td>Zipf 分布。<code>1.001 &lt;= p &lt;= 1000</code></td></tr>
    <tr><td><code>permute(i, size [, seed])</code></td><td>integer</td><td><code>[0, size)</code> の疑似ランダム置換。衝突・抜けなし</td></tr>
    <tr><td><code>hash(v [, seed])</code></td><td>integer</td><td><code>hash_murmur2</code> の別名</td></tr>
    <tr><td><code>hash_murmur2(v [, seed])</code></td><td>integer</td><td>MurmurHash2</td></tr>
    <tr><td><code>hash_fnv1a(v [, seed])</code></td><td>integer</td><td>FNV-1a</td></tr>
    <tr><td><code>debug(v)</code></td><td>入力と同型</td><td>標準エラーへ型と値を出力し、引数をそのまま返す</td></tr>
    <tr><td><code>abs(v)</code></td><td>入力と同型</td><td>絶対値</td></tr>
    <tr><td><code>int(v)</code> / <code>double(v)</code></td><td>integer / double</td><td>型変換</td></tr>
    <tr><td><code>greatest(...)</code> / <code>least(...)</code></td><td>可変</td><td>最大 / 最小</td></tr>
    <tr><td><code>exp(v)</code> / <code>ln(v)</code> / <code>sqrt(v)</code> / <code>pi()</code></td><td>double</td><td>数学関数</td></tr>
    <tr><td><code>pow(x, y)</code> / <code>power(x, y)</code></td><td>double</td><td>べき乗</td></tr>
    <tr><td><code>mod(a, b)</code></td><td>integer</td><td>剰余</td></tr>
  </tbody>
</table>

<p>
演算子は SQL とほぼ同じものが使える（4.1 節の表を参照）。
関数と多くの演算子は、<code>NULL</code> を入力すると <code>NULL</code> を返す。
</p>

<h2 id="sec-8-3">8.3　オプション早見表</h2>

<table>
  <thead>
    <tr><th>やりたいこと</th><th>オプション</th></tr>
  </thead>
  <tbody>
    <tr><td>スクリプトを指定する</td><td><code>-f ファイル</code>（<code>@重み</code> を付けられる）</td></tr>
    <tr><td>組み込みスクリプトを使う</td><td><code>-b 名前[@重み]</code>、一覧は <code>-b list</code></td></tr>
    <tr><td>組み込みの中身を見る</td><td><code>--show-script=名前</code></td></tr>
    <tr><td><strong><code>:scale</code> を設定する</strong></td><td><code>-s 数</code>（<code>-f</code> では必須）</td></tr>
    <tr><td>変数を渡す</td><td><code>-D 名前=値</code>（文字列は <code>-D k="'v'"</code>）</td></tr>
    <tr><td>実行前 VACUUM を省く</td><td><code>-n</code>（カスタムスクリプトでは基本的に付ける）</td></tr>
    <tr><td>同時実行数・スレッド数</td><td><code>-c 数</code> / <code>-j 数</code></td></tr>
    <tr><td>実行時間・回数</td><td><code>-T 秒</code> / <code>-t 回数</code></td></tr>
    <tr><td>プロトコルを変える</td><td><code>-M simple|extended|prepared</code></td></tr>
    <tr><td>ステートメント別レポート</td><td><code>-r</code></td></tr>
    <tr><td>進捗を表示</td><td><code>-P 秒</code></td></tr>
    <tr><td>トランザクションログ</td><td><code>-l</code>（<code>--log-prefix=名前</code> で接頭辞変更）</td></tr>
    <tr><td>ログを集約する</td><td><code>--aggregate-interval=秒</code></td></tr>
    <tr><td>乱数の種を固定</td><td><code>--random-seed=整数</code></td></tr>
    <tr><td>目標スループットを決める</td><td><code>-R 数</code></td></tr>
    <tr><td>直列化・デッドロックで再試行</td><td><code>--max-tries=数</code></td></tr>
  </tbody>
</table>

<h2 id="sec-8-4">8.4　スクリプトを書くときの型</h2>

<p>
最後に、カスタムスクリプトで計測するときの手順をまとめる。図 8.1 の順に進めると、
本ガイドで挙げた落とし穴をおおむね避けられる。
</p>

<figure>
  <pre class="mermaid">
flowchart TD
    S1["1. 測りたいトランザクションを1本の SQL 列として書く"] --> S2["2. 可変部分を \set と :変数 に置き換える"]
    S2 --> S3["3. -t 10 で動作確認<br/>scaling factor 行を必ず見る"]
    S3 --> S4["4. -r でどの文が重いか確認"]
    S4 --> S5["5. 比率が要るなら<br/>ファイルを分けて @重み"]
    S5 --> S6["6. -T で数分回す<br/>-M を揃えて複数回"]
    S6 --> S7["7. -l のログを保存し<br/>条件とセットで記録"]
  </pre>
  <figcaption>図 8.1: カスタムスクリプトで計測するときの手順</figcaption>
</figure>

<p>
繰り返しになるが、特に忘れやすいのは次の3点である。
</p>

<ol>
  <li><strong><code>-s</code> を明示する。</strong> <code>-f</code> では <code>:scale</code> が
      自動設定されない。実行のたびに <code>scaling factor:</code> 行で確認する（3.4 節）。</li>
  <li><strong><code>-n</code> を付ける。</strong> 自前テーブルだけを使うなら実行前 VACUUM は失敗する（2.3 節）。</li>
  <li><strong>tps はスクリプト実行回数である。</strong> スクリプト構成が違うもの同士を比べない（3.2 節）。</li>
</ol>

<div class="tip">
  <strong>💡 さらに詳しく</strong>
  各オプションの完全な仕様、失敗と再試行（<code>--max-tries</code>）の詳細、
  テーブルアクセスメソッドの指定などは
  <a href="https://www.postgresql.org/docs/18/pgbench.html">公式ドキュメントの pgbench</a>
  を参照してほしい。
</div>

<div class="checkpoint">
  <strong>✅ チェックポイント</strong>
  <ul>
    <li>測りたいワークロードを、自分でスクリプトに落とせる</li>
    <li>結果を見て、どのステートメントが支配的か指摘できる</li>
    <li>他人の計測結果を見たとき、<code>-s</code> / <code>-M</code> / 実行時間を確認できる</li>
  </ul>
</div>
"""

CHAPTERS = [
    {
        "num": 1,
        "title": "カスタムスクリプトでできること",
        "desc": "組み込みスクリプトの限界を確認し、カスタムスクリプトの構成要素と重み付けの全体像をつかむ。",
        "sections": [
            ("sec-1-1", "1.1 組み込みスクリプトの限界"),
            ("sec-1-2", "1.2 カスタムスクリプトの構成要素"),
            ("sec-1-3", "1.3 実行の全体像と重み付け"),
        ],
        "body": CH01,
    },
    {
        "num": 2,
        "title": "準備",
        "desc": "以降すべての章で使う bench データベースを用意し、実行コマンドの基本形を決める。",
        "sections": [
            ("sec-2-1", "2.1 バージョンと接続を確認する"),
            ("sec-2-2", "2.2 ベンチマーク用データベースを初期化する"),
            ("sec-2-3", "2.3 作業ディレクトリと実行の基本形"),
        ],
        "body": CH02,
    },
    {
        "num": 3,
        "title": "まず動かす（最短ルート）",
        "desc": "最小のスクリプトを書いて実行し、出力の読み方と :scale の罠を実測で確認する。",
        "sections": [
            ("sec-3-1", "3.1 最小のカスタムスクリプトを書いて動かす"),
            ("sec-3-2", "3.2 出力を読む"),
            ("sec-3-3", "3.3 -r でステートメント単位に分解する"),
            ("sec-3-4", "3.4 :scale の罠"),
        ],
        "body": CH03,
    },
    {
        "num": 4,
        "title": "変数と式を使いこなす",
        "desc": "\\set の式・自動変数・4つの乱数分布・permute() を、debug() と実測で確かめながら覚える。",
        "sections": [
            ("sec-4-1", "4.1 \\set と式の評価"),
            ("sec-4-2", "4.2 自動変数と -D"),
            ("sec-4-3", "4.3 乱数分布を選ぶ"),
            ("sec-4-4", "4.4 permute() で相関を断つ"),
        ],
        "body": CH04,
    },
    {
        "num": 5,
        "title": "メタコマンドで制御する",
        "desc": "\\gset で結果を受け取り、\\if で分岐し、パイプラインで往復を減らす。",
        "sections": [
            ("sec-5-1", "5.1 \\gset / \\aset"),
            ("sec-5-2", "5.2 \\if で条件分岐する"),
            ("sec-5-3", "5.3 \\sleep / \\shell / \\setshell"),
            ("sec-5-4", "5.4 パイプラインで往復を減らす"),
        ],
        "body": CH05,
    },
    {
        "num": 6,
        "title": "実践：現実的なワークロードを組む",
        "desc": "読み9:書き1のミックスを組み、スクリプト別レポート・プロトコル比較・ログ分析まで通す。",
        "sections": [
            ("sec-6-1", "6.1 複数スクリプトを重み付けで混ぜる"),
            ("sec-6-2", "6.2 スクリプト別レポートを読む"),
            ("sec-6-3", "6.3 プロトコルを変えて比較する"),
            ("sec-6-4", "6.4 ログを取って分析する"),
        ],
        "body": CH06,
    },
    {
        "num": 7,
        "title": "つまずきポイントと対処",
        "desc": "実際のエラーメッセージから原因を切り分け、「数字が信用できない」パターンを見抜く。",
        "sections": [
            ("sec-7-1", "7.1 エラーの切り分け方"),
            ("sec-7-2", "7.2 起動時に失敗する"),
            ("sec-7-3", "7.3 実行中に abort する"),
            ("sec-7-4", "7.4 数字が信用できないとき"),
        ],
        "body": CH07,
    },
    {
        "num": 8,
        "title": "まとめとチートシート",
        "desc": "メタコマンド・関数・オプションの早見表と、計測手順の型。",
        "sections": [
            ("sec-8-1", "8.1 メタコマンド早見表"),
            ("sec-8-2", "8.2 関数早見表"),
            ("sec-8-3", "8.3 オプション早見表"),
            ("sec-8-4", "8.4 スクリプトを書くときの型"),
        ],
        "body": CH08,
    },
]
