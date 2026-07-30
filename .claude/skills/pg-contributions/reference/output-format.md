# 出力フォーマット

resume に貼れる形に整えるための規則。**着手前に必ず読む。**

## 出力先

`~/git/pgsql-toolbox/contributions/` 配下の Markdown ファイル。

```
contributions/
└── postgresql.md        # 既定。人物を分けるなら postgresql-<slug>.md
```

ディレクトリが無ければ作る。会話にも同じ内容を貼るが、**正となるのはファイル**。

## 基本形（既定）

1 テーマ = 1 箇条書き。テーマ名を素のテキストで書き、括弧内にコミットへのリンクを並べる。

```markdown
# PostgreSQL contributions — Shinya Kato

- Improvements of VACUUM logs ([dd3ae3783](https://git.postgresql.org/gitweb/?p=postgresql.git;a=commit;h=dd3ae3783...), [ad25744f4](...))
- statistics views ([deb674454](...), [f9a09aa29](...), [0d7895206](...))
- client tools ([2eb1fc8b1](...), [08951a7c9](...))
```

- リンク文字列は **素の短縮 9 桁ハッシュ**（バッククォートで囲まない）、リンク先は
  公式リポジトリの gitweb `https://git.postgresql.org/gitweb/?p=postgresql.git;a=commit;h=<フルハッシュ>`。
  GitHub ミラーは使わない。
  URL は `collect.py --md` / `--json` の出力からコピーする。**手で組み立てない**
  （`?` と `;` を含むので打ち間違えやすい）。
- ハッシュはカンマ + 半角スペース区切り、**新しい順**（コミット日の降順）。
- テーマ名は英語の名詞句。文にしない、末尾にピリオドを打たない。
- **1 コミットは 1 テーマにだけ置く。重複掲載しない。**（規則は次節）

## 装飾を付けない

Markdown の装飾はリンクだけ。**太字とハッシュのバッククォートは使わない。**
生成物は Web サイト（`shinyaaa.github.io` の Home など）や resume にそのまま貼られるため、
貼り先の見た目に合わない装飾が残ると毎回外す手間になる。

```
NG: - **statistics views** ([`deb674454`](...), [`f9a09aa29`](...))
OK: - statistics views ([deb674454](...), [f9a09aa29](...))
```

**識別子も囲まない。** GUC・カラム名・関数名・ツール名（`wal_fpi_bytes`、`psql`、
`file_fdw` など）がテーマ名に出てきても素のテキストで書く。一部だけ囲うと、
同じ行の並びで囲われていない識別子（`psql`, `pg_waldump` など）との差が目立つ。

```
NG: - WAL usage statistics (`wal_fpi_bytes`) (...)   ← 他のテーマの psql は素のまま
OK: - WAL usage statistics (wal_fpi_bytes) (...)
```

## 詳細版（コミット件数が多いとき / 依頼があったとき）

テーマを見出しにし、コミットごとに 1 行の箇条書きにする。subject をそのまま添える。

```markdown
## statistics views

- [deb674454](...) — Add pg_stat_progress_vacuum columns for ...
- [f9a09aa29](...) — Fix stats_fetch_consistency with stats for fixed-numbered objects
```

subject は**コミットのものをそのまま使う**。言い換えて盛らない。
どちらの形にするかはユーザーに確認する。既定は基本形。

## 重複させない：1 コミット 1 テーマ

複数のテーマに当てはまるコミットは必ず出る（VACUUM ログにも WAL 統計にも効く、など）。
**その場合は最も関連の深い 1 か所だけに置く。** 掲載ハッシュのユニーク数と収集件数が
一致することが、取りこぼしと二重計上の両方を防ぐ検算になる。

寄せ先は次の順で決める。

1. **具体的なテーマ > 汎用の受け皿。** 特定の機能シリーズ（例: `wal_fpi_bytes` を
   複数の面に通した一連の仕事）は、`statistics views` のような広いテーマより優先する。
   シリーズから 1 件抜くとシリーズが崩れるので、シリーズ側に残す。
2. **対象が限定されるテーマ > 一般的なテーマ。** VACUUM の進捗ビューは、
   進捗ビュー一般より `Vacuum observability` に置く。
3. **変更したコードの場所。** 1 と 2 で決まらないなら diff のパスで決める
   （`src/backend/replication/` 配下なら `Replication`）。

```
NG: statistics views (f9a09aa29, ...) と WAL statistics (f9a09aa29, ...) の両方に置く
OK: WAL statistics (f9a09aa29, ...) にだけ置き、statistics views からは外す
```

寄せた結果、あるテーマが 1〜2 件しか残らなくなったら、そのテーマ自体を畳んで
別テーマに統合するか、テーマの切り方を見直す。

## テーマの粒度

- 目安は **3〜8 テーマ**。resume の 1 ブロックとして読める量に収める。
- 1 テーマ 1 コミットは原則作らない。単独で強い成果（新機能・新ビュー）のときだけ許す。
  それ以外の余り物は `documentation fixes` のような受け皿テーマにまとめる。
- テーマは「読み手が価値を判断できる単位」で切る。ファイル名やディレクトリ名をそのまま
  テーマ名にしない。

```
NG: src/bin/psql (e2ce88b58, 3f238b882)
OK: psql tab-completion (e2ce88b58, 3f238b882)

NG: pgstat.c fix (235c09efb)
OK: statistics views (235c09efb, ...)
```

- `collect.py` の `areas` 列はあくまで**ヒント**。最終的なテーマ分けは subject と
  実際の変更内容から判断する。

## 並び順

テーマは **インパクトの大きい順**。同程度なら以下で決める。

1. 機能追加・挙動修正 > ドキュメント修正
2. author として入ったコミットが多いテーマ > reviewer だけのテーマ
3. コミット数の多い順

`documentation fixes` 系の受け皿テーマは最後に置く。

## 役割（author / reviewer）の扱い

`collect.py` は `Author:` / `Reviewed-by:` / `Reported-by:` トレーラから役割を判定する。
**author と reviewer を黙って混ぜない。** 既定は次のどちらかで、どちらにするかは
ユーザーに確認する。

**A. author のみ（既定）** — resume で「自分が書いた」と主張できる範囲だけ。

**B. セクションを分けて併記** — レビュー実績も見せたいとき。

```markdown
## Authored

- client tools ([2eb1fc8b1](...), [08951a7c9](...))

## Reviewed

- psql tab-completion ([9a6915257](...), [6afcab6ac](...), [4cbe57974](...))
```

役割が `mention` のコミット（トレーラに名前がなく本文で言及されているだけ）は
**既定では落とす**。拾う場合は `git show` で本文を読み、どう関わったか確認してから
扱いを決める。

## 末尾に付ける出典行

ファイルの最後に、どの時点の何を見たかを 1 行残す。

```markdown
---
Source: origin/master @ d4046a48053 (2026-07-19), 54 of 57 commits matching Shinya Kato.
```

掲載件数は**ユニークなハッシュの数**であり、テーマごとの件数の合計と一致する
（重複掲載しないため）。

## 書いてはいけないこと

- コミットから読み取れない評価（「性能が N% 改善」「大幅に」「劇的に」）。
- コミット数や規模の推測・水増し。件数は `collect.py` の出力そのまま。
- master 以外のブランチのバックパッチコミット。**同じ成果を二重に数えない。**
