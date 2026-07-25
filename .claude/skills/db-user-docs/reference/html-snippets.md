# HTML スニペット集（ユーザーガイドの本文部品）

`{{CHAPTER_BODY}}` や `{{SIDEBAR_TOC}}` 等に差し込む HTML の定型。`page-template.html` /
`index-template.html` と組み合わせて使う。クラス名は `assets/style.css` に対応している。

---

## 節見出し（アンカー付き）

サイドバーからジャンプできるよう、節には `id` を必ず付ける。

```html
<h2 id="sec-1-1">1.1　論理レプリケーションが解決する課題</h2>
<h3 id="sec-1-1-1">1.1.1　物理レプリケーションとの違い</h3>
```

## この章のゴール（章の冒頭に置く）

```html
<div class="goal">
  <strong>🎯 この章のゴール</strong>
  <ul>
    <li>パブリケーションとサブスクリプションの役割を説明できる</li>
    <li>1 テーブルを別インスタンスへ複製し、変更が伝わることを確認できる</li>
  </ul>
</div>
```

## 前提（章の冒頭、ゴールの次に置く）

```html
<div class="prereq">
  <strong>📋 前提</strong>
  <ul>
    <li>PostgreSQL 18 が 2 インスタンス（5432 / 5433）で起動している</li>
    <li><code>wal_level = logical</code> が設定済み（未設定なら 2.2 で設定する）</li>
    <li>第2章で作成した <code>shop</code> データベースを引き継ぐ</li>
  </ul>
</div>
```

## ハンズオン（番号付きステップ：入力と出力をセットで）

読者がそのまま実行できる手順。各ステップに「何をするか」の一言と、入力・期待出力を入れる。

```html
<div class="handson">
  <div class="handson-head">⌨️ ハンズオン: 発行側テーブルを複製する</div>
  <div class="handson-body">
    <ol class="steps">
      <li>
        <p>発行側（5432）で複製したいテーブルを含むパブリケーションを作る。</p>
        <div class="example">
          <span class="example-label">入力（psql :5432）</span>
          <pre><code>CREATE PUBLICATION shop_pub FOR TABLE items;</code></pre>
        </div>
        <div class="example">
          <span class="example-label out">出力</span>
          <pre><code>CREATE PUBLICATION</code></pre>
        </div>
      </li>
      <li>
        <p>購読側（5433）でサブスクリプションを作ると、初回コピーが自動で走る。</p>
        <div class="example">
          <span class="example-label">入力（psql :5433）</span>
          <pre><code>CREATE SUBSCRIPTION shop_sub
  CONNECTION 'host=localhost port=5432 dbname=shop'
  PUBLICATION shop_pub;</code></pre>
        </div>
        <div class="example">
          <span class="example-label out">出力</span>
          <pre><code>NOTICE:  created replication slot "shop_sub" on publisher
CREATE SUBSCRIPTION</code></pre>
        </div>
      </li>
    </ol>
  </div>
</div>
```

## 入力／出力の単発例（ハンズオン外でも使う）

```html
<div class="example">
  <span class="example-label">入力</span>
  <pre><code>SELECT * FROM pg_stat_subscription;</code></pre>
</div>

<div class="example">
  <span class="example-label out">出力</span>
  <pre><code> subid | subname  | pid  |  received_lsn  | latest_end_lsn
-------+----------+------+----------------+----------------
 16405 | shop_sub | 1234 | 0/1A2B3C0      | 0/1A2B3C0</code></pre>
</div>
```

出力の直後に「読み方」を一言添える。

```html
<p><code>received_lsn</code> と <code>latest_end_lsn</code> が一致していれば、購読側は
発行側に追いついている。</p>
```

## 落とし穴（操作の直後に置く）

```html
<div class="pitfall">
  <strong>⚠️ よくある落とし穴</strong>
  <code>CREATE SUBSCRIPTION</code> が固まる場合、購読側から発行側の 5432 へ
  接続できていない。<code>pg_hba.conf</code> の <code>replication</code> 行と
  ファイアウォールを確認する。
</div>
```

## ヒント（あると便利な補足）

```html
<div class="tip">
  <strong>💡 ヒント</strong>
  初回コピーを避けて既存データから始めたいときは
  <code>WITH (copy_data = false)</code> を付ける。
</div>
```

## チェックポイント（章の末尾に置く）

読者が自分の環境で確認できる、具体的なチェックリストにする。

```html
<div class="checkpoint">
  <strong>✅ チェックポイント</strong>
  <ul>
    <li>発行側で <code>items</code> に INSERT すると、購読側にも数秒以内に現れる</li>
    <li><code>pg_stat_subscription</code> に自分のサブスクリプションが1行表示される</li>
    <li>パブリケーション／サブスクリプションの役割を自分の言葉で説明できる</li>
  </ul>
</div>
```

## 図（Mermaid + キャプション）

使う人の視点で「流れ」を描く。

```html
<figure>
  <pre class="mermaid">
flowchart LR
    subgraph Pub["発行側 (:5432)"]
        T["items テーブル"]
        P["shop_pub"]
    end
    subgraph Sub["購読側 (:5433)"]
        S["shop_sub"]
        T2["items テーブル"]
    end
    T --> P -->|WAL の変更を送信| S --> T2
  </pre>
  <figcaption>図 1.1: パブリケーションから購読側テーブルへ変更が流れる</figcaption>
</figure>
```

状態遷移の例:

```html
<figure>
  <pre class="mermaid">
stateDiagram-v2
    [*] --> initializing: CREATE SUBSCRIPTION
    initializing --> copying: 初回データコピー
    copying --> streaming: コピー完了
    streaming --> [*]: DROP SUBSCRIPTION
  </pre>
  <figcaption>図 3.2: サブスクリプションのライフサイクル</figcaption>
</figure>
```

## まとめ・チートシート（最終章の早見表）

```html
<h2 id="sec-7-1">7.1　コマンド早見表</h2>
<table>
  <thead>
    <tr><th>やりたいこと</th><th>コマンド</th></tr>
  </thead>
  <tbody>
    <tr><td>パブリケーション作成</td><td><code>CREATE PUBLICATION 名 FOR TABLE …;</code></td></tr>
    <tr><td>サブスクリプション作成</td><td><code>CREATE SUBSCRIPTION 名 CONNECTION '…' PUBLICATION …;</code></td></tr>
    <tr><td>進捗確認</td><td><code>SELECT * FROM pg_stat_subscription;</code></td></tr>
    <tr><td>購読停止・削除</td><td><code>ALTER SUBSCRIPTION 名 DISABLE;</code> / <code>DROP SUBSCRIPTION 名;</code></td></tr>
  </tbody>
</table>
```

## サイドバー TOC（全ページ共通・現在位置をハイライト）

現在表示中の章 `<li>` に `class="current"`、現在節 `<a>` に `class="current"` を付ける。

```html
<ol>
  <li class="current">
    <a class="chap-title" href="ch01.html">第1章 この機能でできること</a>
    <ol class="sect">
      <li><a class="current" href="ch01.html#sec-1-1">1.1 解決する課題</a></li>
      <li><a href="ch01.html#sec-1-2">1.2 向き・不向き</a></li>
    </ol>
  </li>
  <li>
    <a class="chap-title" href="ch02.html">第2章 準備</a>
    <ol class="sect">
      <li><a href="ch02.html#sec-2-1">2.1 2 インスタンスを起動する</a></li>
    </ol>
  </li>
</ol>
```

## 前後ナビ（`{{PAGER}}`）

前後の章リンクに加え、中央に**トップページ（目次）へのリンク**を必ず置く。`prev`／`next` が無い章でも
中央リンクが中央に来るよう、欠けた側を `pager-spacer` で埋める（順序は prev → up → next）。

```html
<a class="prev" href="ch01.html">
  <span class="dir">← 前の章</span>
  <span class="ttl">第1章 この機能でできること</span>
</a>
<a class="up" href="index.html">
  <span class="dir">↑ 目次</span>
  <span class="ttl">トップページ</span>
</a>
<a class="next" href="ch03.html">
  <span class="dir">次の章 →</span>
  <span class="ttl">第3章 まず動かす</span>
</a>
```

先頭章では `prev` を、最終章では `next` を、それぞれ次のスペーサーに置き換える（中央リンクの中央寄せを保つため）。

```html
<span class="pager-spacer" aria-hidden="true"></span>
```

## トップページの章カード（`{{TOC_CARDS}}`）

```html
<a class="toc-card" href="ch01.html">
  <span class="num">第1章</span>
  <span class="title">この機能でできること</span>
  <span class="desc">論理レプリケーションで何が実現できるか、典型ユースケースと向き・不向きを掴む。</span>
</a>
```
