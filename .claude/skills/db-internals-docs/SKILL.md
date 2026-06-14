---
name: db-internals-docs
description: >-
  指定された技術トピック（PostgreSQL や各種データベース・システムソフトウェアの内部構造）について、
  The Internals of PostgreSQL (interdb.jp/pg) 風の日本語技術ドキュメントを静的HTMLサイトとして生成する。
  章→節の階層構造、サイドバー目次と前後ナビ、Mermaid 図、SQL/実行例を備えた読み物形式のドキュメントを
  作りたいときに使う。「○○の内部構造を解説するドキュメント／サイトを作って」「interdb 風の解説を書いて」
  といった依頼で起動する。
---

# db-internals-docs

PostgreSQL をはじめとするデータベース／システムソフトウェアの**内部構造**を、図と実例で
解き明かす日本語技術ドキュメントを、**静的HTMLサイト**として生成するスキル。
The Internals of PostgreSQL（https://www.interdb.jp/pg/）のスタイルを範にとる。

## 成果物の形

`pgsql-toolbox/internals/docs/<トピックslug>/` 以下に生成する。
生成したドキュメントは pgsql-toolbox リポジトリで git 管理され、
`http://127.0.0.1:30002/<slug>/` で閲覧できる。

```
internals/docs/<slug>/
├── index.html        ← トップページ（リード文＋章カード目次）
├── ch01.html         ← 第1章
├── ch02.html         ← 第2章
├── …
└── css/style.css     ← スタイルシート（assets/style.css をコピー）
```

- 各ページは左に**共通サイドバー目次**、本文末に**前後ナビ**を持つ。
- 図は **Mermaid**（CDN 読み込み）で描き、`図 N.M: 説明` のキャプションを付ける。
- 本文は日本語・常体。SQL/シェルの実行例とその出力をセットで示す。

## 前提リソース

このスキルディレクトリ内の以下を必ず参照・利用する。

- `assets/style.css` … 完成済みスタイルシート。**そのまま `css/style.css` にコピー**する（編集不要）。
- `assets/page-template.html` … 章ページの雛形（`{{...}}` を置換）。
- `assets/index-template.html` … トップページの雛形。
- `reference/style-guide.md` … 章構成・文体・図の使い分けの指針。**着手前に必ず読む**。
- `reference/html-snippets.md` … 図・例・TOC・ナビ等の HTML 部品集。本文組み立て時に参照。

## PostgreSQL ソースコードの利用

このプロジェクトには `postgres/` サブモジュール（`https://github.com/shinyaaa/postgres`）が含まれている。
**調査の主要ソースはこのサブモジュールのソースコードとする。**

### サブモジュールの確認

作業を開始する前に、サブモジュールが初期化済みかを確認する。

```sh
ls postgres/src/backend/
```

ファイルが存在しない場合は以下を実行して初期化する。

```sh
git submodule update --init --recursive
```

### 調査方法

- 構造体・型定義は `postgres/src/include/` 以下を `Grep` で検索し、定義ファイルを特定する。
- 関数の実装は `postgres/src/backend/` 以下を `Grep` で検索し、`Read` で内容を確認する。
- ソースのコメント（`/* ... */`）は実装意図の一次情報であり、積極的に本文に反映する。
- **推測で書かない**：ソースで確認できた事実のみを本文に反映し、未確認の点は「詳細は未調査」と明示する。

## ワークフロー

### 0. リソース確認・サブモジュール最新化

`reference/style-guide.md` と `reference/html-snippets.md` を読み、スタイルとHTML部品を把握する。

次に、サブモジュールを**必ず最新化**してから作業を開始する。

```sh
git submodule update --remote postgres
```

最新化後、ドキュメントに埋め込む `{{VERSION_INFO}}` と GitHub コードリンク用のベース URL を確定する。

```sh
# コミットハッシュ（短縮形）— {{VERSION_INFO}} 用
git -C postgres rev-parse --short HEAD

# コミットハッシュ（フル） — GitHub URL 用
git -C postgres rev-parse HEAD

# PostgreSQL バージョン（configure.ac から取得）
grep 'AC_INIT' postgres/configure.ac

# 作成日時（ローカル時刻）
date '+%Y-%m-%d %H:%M'
```

`{{VERSION_INFO}}` の形式は `"PostgreSQL <version> · <hash> · <date>"` とする。  
例: `"PostgreSQL 18beta1 · 79c65b9 · 2026-06-14 18:30"`  
この値は全ページの `<title>` タグとヘッダバッジ、トップページの `<p class="version-hero">` に表示される。

GitHub コードポインタのベース URL（以降 `{{GITHUB_BASE}}` と表記）:

```
https://github.com/shinyaaa/postgres/blob/<フルハッシュ>
```

例: `https://github.com/shinyaaa/postgres/blob/79c65b9d97f4a3b2c1e0d8f6a5b4c3d2e1f0a9b8`

### 1. 要件確認
ユーザーから次を確認する（不明点のみ簡潔に質問。妥当な既定があれば提案して進める）。
- **トピック**（例: 「PostgreSQL のバッファマネージャ」「MVCC と可視性判定」「WAL とリカバリ」）
- **対象バージョン**（例: PostgreSQL 16）。明示なければ最新安定版を仮定し冒頭に明記。
- **想定読者と深さ**（概説 / 実装詳細まで）。
- **章数の目安**（既定: 4〜8章）。
- **出力先**（既定: `internals/docs/<slug>/`）。

### 2. 調査
`postgres/` サブモジュールのソースコードを主軸に調査する。

1. **構造体・定数** — `Grep` でキーワードを `postgres/src/include/` 以下から検索し、ヘッダを特定・`Read` する。
2. **実装** — 主要関数を `postgres/src/backend/` 以下で `Grep` し、処理の流れを `Read` で把握する。
3. **ソースコメント** — `/* ... */` ブロックは実装意図の一次情報。本文に積極的に引用・反映する。
4. **補完** — ソースだけでは不明な仕様・歴史的背景は Web 検索や公式ドキュメントで補う。

推測で書かず、確認できた事実を基に記述する。未確認の点は本文中で明示する。

#### コードポインタの確定

調査中、本文で言及する関数・構造体・マクロ・ファイルのすべてについて、**定義行番号を確定**しておく。

```sh
# 関数定義の行番号を確認する例
grep -n 'SubTransSetParent' postgres/src/backend/access/transam/subtrans.c

# 構造体定義の行番号を確認する例
grep -n 'typedef.*SlruCtlData' postgres/src/include/access/slru.h
```

リンク URL の形式: `{{GITHUB_BASE}}/<ファイルのサブモジュール相対パス>#L<行番号>`  
例: `https://github.com/shinyaaa/postgres/blob/<フルハッシュ>/src/backend/access/transam/subtrans.c#L42`

HTML スニペットは `reference/html-snippets.md` の「コードポインタ」節を参照。

### 3. 目次設計
`style-guide.md` の構成原則に従い、**章→節**の目次を作る。
- 「基礎概念 → データ構造 → 動作 → 具体例 → 応用・注意」の順で積み上げる。
- 各章にタイトル・1行説明・節リスト（`N.1`, `N.2`…）を割り当てる。
- 確定した目次をユーザーに提示し、合意を得てから本文生成へ進む。

### 4. 共通パーツ生成
- **サイドバー TOC**（`html-snippets.md` 参照）の HTML を1つ作り、全ページで使い回す。
  各ページ生成時に、現在の章 `<li>` と節 `<a>` に `class="current"` を付けたバリエーションにする。
- `css/style.css` を `assets/style.css` のコピーで用意する。

### 5. 各章ページ生成
`assets/page-template.html` をベースに、章ごとに `chNN.html`（ゼロ埋め2桁）を生成する。
1章の本文は `style-guide.md` の「1ページの典型パターン」に従う:
概要 → データ構造の図 → 処理フローの図 → SQL/実行例 → ソース言及 → 注意点。
- 節見出しには `id="sec-N-M"` を付け、サイドバーから飛べるようにする。
- 図は本文から必ず「図 N.M に示すように…」と参照する。
- `{{PAGER}}` に前後章リンクと、中央のトップページ（目次）リンクを入れる（順序は prev → up → next）。先頭章は prev を、末尾章は next を、それぞれ `pager-spacer` に置き換えて中央リンクの中央寄せを保つ。
- **関数名・構造体名・ファイル名を本文中で言及するとき、できるだけ GitHub コードポインタを付ける**（`html-snippets.md` の「コードポインタ」節を参照）。行番号が確定していない場合はファイルリンクだけでもよい。

**章を書き終えたら、ファイルに書き出す前に必ず 5a を実施する。**

### 5a. Mermaid 構文チェック（各章・書き出し前に必須）

章内のすべての `<pre class="mermaid">` ブロックを1つずつ確認する。
以下の項目を**すべてパスしてから**ファイルに書き出す。

| チェック項目 | 良い例 | NG 例 |
|---|---|---|
| ノードIDは英数字・アンダースコアのみ | `buf_tag` | `buf tag`、`buf(tag)` |
| 日本語はラベル内のみ | `A["バッファ"]` | `バッファ["..."]` |
| 矢印の種類がダイアグラム型と一致 | flowchart で `-->` | flowchart で `->>` |
| `subgraph` に対応する `end` がある | `subgraph X\n...\nend` | `end` 抜け |
| 同一ダイアグラム内でノードIDが重複しない | — | `A` が2箇所で定義 |
| 括弧・クォートが対応して閉じている | `["label"]` | `["label"` |

問題が見つかった場合は修正してから次の章へ進む。

### 6. トップページ生成
`assets/index-template.html` をベースに `index.html` を生成。リード文（概要・対象読者・
前提バージョン）と、全章ぶんの章カード（`html-snippets.md` 参照）を並べる。

### 7. 検証
- すべての内部リンク（サイドバー・前後ナビ・章カード・節アンカー）が実在ファイル／idを指すか確認。
- 章・節・図番号が連番で本文参照と一致しているか確認。
- Mermaid 図の数とキャプション番号が本文参照と一致しているか確認。
- 簡易チェック例:
  ```sh
  # 章ファイルの一覧と、index からの参照漏れ確認の目安
  ls internals/docs/<slug>/ch*.html
  grep -o 'href="ch[0-9]*\.html' internals/docs/<slug>/index.html | sort -u

  # 全章の Mermaid ブロック数を確認
  grep -c 'class="mermaid"' internals/docs/<slug>/ch*.html
  ```
- 可能なら `python3 -m http.server` でローカル表示確認を案内する。

## 重要な原則

- **正確性最優先**: 内部構造の記述は調査で裏付ける。創作で埋めない。
- **図を惜しまない**: データ構造と処理の流れは文章より図で示す（interdb の核）。
- **再現可能な例**: SQL/シェル例は前提込みで、読者が手元で再現できる形にする。
- **一貫性**: 番号体系・リンク・スタイルを全ページで揃える。`style.css` は編集せずそのまま使う。
- **段階的合意**: 目次を提示して合意を得てから本文を書く。大量生成の手戻りを防ぐ。
