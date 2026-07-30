---
name: pg-contributions
description: >-
  pgsql-toolbox のサブモジュール postgres/ の master から、指定した人物
  （既定は Shinya Kato）のコントリビューションを収集し、resume / 職務経歴書に貼れる
  テーマ別の Markdown を contributions/ 配下に書き出す。
  `git log --grep="<名前>"` を起点に Author / Reviewed-by / Reported-by を判定し、
  コミットへのリンク付きで「テーマ名 (ハッシュ, ...)」の箇条書きにまとめる。
  「PostgreSQL へのコントリビューションをまとめて」「resume 用に貢献一覧を作って」
  「自分のコミットを整理して」といった依頼で起動する。
  ドキュメントを生成する db-internals-docs / db-user-docs / db-patch-docs とは別物で、
  HTML もドキュメントサーバーへの配置も伴わない。
---

# pg-contributions

PostgreSQL 本体への貢献を、resume に貼れる粒度でまとめるスキル。
成果物は Markdown 1 枚であって、ドキュメントサイトではない。HTML は作らないし、
`internals/` 配下にも何も置かない（そこは [db-internals-docs] などの担当）。

やることは 3 つ。**収集**（git log から機械的に集める）、**検証**（役割と内容を確認する）、
**テーマ分け**（読み手が価値を判断できる単位に束ねる）。1 番目は `assets/collect.py` に
任せ、モデルの仕事は 2 番目と 3 番目に集中する。

## 対象リポジトリ：サブモジュールの master のみ

**このリポジトリのサブモジュール `~/git/pgsql-toolbox/postgres` を使う。**
`~/git/postgres` など他のクローンは見ない（`collect.py` の既定もサブモジュール）。

**見るのは `origin/master` だけ。** バックパッチされたコミットは stable ブランチ側に
別ハッシュで生えるので、`--all` で拾うと同じ成果が枝の数だけ重複する
（実測で 22 件 → 51 件に膨らむ）。master に絞ることで重複は原理的に発生しない。
`--rev=--all` は使わない。

## 成果物の形

`~/git/pgsql-toolbox/contributions/postgresql.md`（既定）。テーマごとの箇条書きで、
各コミットは **git.postgresql.org の gitweb** にリンクする。

```markdown
# PostgreSQL contributions — Shinya Kato

- Improvements of VACUUM logs ([dd3ae3783](https://git.postgresql.org/gitweb/?p=postgresql.git;a=commit;h=dd3ae3783...), [ad25744f4](...))
- statistics views ([deb674454](...), [f9a09aa29](...), [0d7895206](...))
- client tools ([2eb1fc8b1](...), [08951a7c9](...))
```

- 1 テーマ 1 箇条書き、括弧内は短縮 9 桁ハッシュのリンクを新しい順に列挙。
- **装飾はリンクだけ。太字もバッククォートも使わない**（ハッシュも、テーマ名に出てくる
  `wal_fpi_bytes` や `psql` のような識別子も素のテキストで書く）。生成物は Web サイトや
  resume にそのまま貼られるので、リンク以外の装飾を持ち込まない
  （`reference/output-format.md` の「装飾を付けない」節）。
- **1 コミットは 1 テーマにだけ置く。** 複数に当てはまるものは最も関連の深い方へ寄せる。
- 詳しい規則（出力先・詳細版の形・粒度・並び順・author と reviewer の分け方）は
  `reference/output-format.md`。
- 同じ内容を会話にも貼るが、**正となるのはファイル**。

## 前提リソース

- `reference/output-format.md` — 出力の規則。**着手前に必ず読む。**
- `assets/collect.py` — 収集スクリプト。git log の解析・役割判定・領域推定・
  バックパッチ重複の除去まで行う。**手で git log を叩いて集計し直さない。**

```sh
SKILL=~/git/pgsql-toolbox/.claude/skills/pg-contributions
python3 "$SKILL/assets/collect.py" --help
```

主なオプション:

| オプション | 既定 | 用途 |
|---|---|---|
| `--repo` | `pgsql-toolbox/postgres` | サブモジュールを自動解決。通常は指定しない |
| `--name` | `Shinya Kato` | 検索する人名 |
| `--rev` | `origin/master` | 対象リビジョン。**master 以外に広げない** |
| `--roles` | （なし） | `author` / `reviewer` / `reporter` / `tester` / `mention` で絞る |
| `--md` | オフ | リンク付き Markdown 箇条書き（1 コミット 1 行）で出力 |
| `--json` | オフ | ファイル一覧・Discussion URL・コミット URL 込みの構造化出力 |
| `--base-url` | git.postgresql.org の gitweb | コミットリンクの前置き |
| `--abbrev` | `9` | 短縮ハッシュの桁数 |
| `--dedupe` | オフ | 同一 subject を畳む。master のみなら不要 |

## 正確性の担保：一次情報はコミットだけ

resume に載る主張なので、**裏の取れないことは書かない。**

- テーマ名も補足も、コミットの subject と実際の diff から書く。記憶で補わない。
- 「性能が N% 改善」「大規模な機能追加」のような、コミットから読み取れない評価を足さない。
- 役割の判定は `Author:` / `Reviewed-by:` トレーラが根拠。迷ったら `git show` で本文を読む。
- ハッシュは必ず `collect.py` の出力からコピーする。**手で書き写さない**（1 文字違えば
  存在しないコミットになる）。

## ワークフロー

### 0. 要件確認

不明点のみ簡潔に質問する。妥当な既定があれば提案して進める。

- 対象人名（既定 `Shinya Kato`）
- **author のみか、reviewer も含めるか**（既定は author のみ。`reference/output-format.md` の A / B）
- 基本形か詳細版か（既定は基本形）
- 出力言語（既定は英語。resume が日本語なら日本語）
- 出力先ファイル名（既定 `contributions/postgresql.md`）

リポジトリは聞かない。**サブモジュール固定**。

### 1. サブモジュールの鮮度を確認する

サブモジュールが古いと、最近のコミットが丸ごと欠ける。**必ず先に確認する。**

```sh
PG=~/git/pgsql-toolbox/postgres
git -C "$PG" log -1 --date=short --format='%h %ad %s' origin/master
```

最新コミットが数か月以上前なら、そのまま進めずユーザーに伝える。fetch は
ネットワークとリポジトリ状態を触るので、**実行前に許可を取る**。

```sh
git -C "$PG" fetch origin      # 許可を得てから
```

fetch しない場合は、「この時点までの履歴に基づく」と成果物の末尾に明示する。
サブモジュールの `HEAD` は detached なことがあるので、**必ず `origin/master` を見る**
（ローカルの `master` ブランチは遅れていることがある）。

### 2. 収集する

```sh
SKILL=~/git/pgsql-toolbox/.claude/skills/pg-contributions
python3 "$SKILL/assets/collect.py"            # TSV（一覧把握用）
python3 "$SKILL/assets/collect.py" --md       # リンク付き Markdown（貼り付け元）
```

TSV で `short / date / roles / areas / subject / url` が出る。件数が想定と大きく違う場合は
`--name` の表記ゆれ（`Kato, Shinya` など）を疑い、別表記でも引いて突き合わせる。

```sh
git -C "$PG" log --grep="Kato" --oneline origin/master | wc -l
```

**`--rev` は既定の `origin/master` のまま触らない。** `--all` に広げるとバックパッチの
重複で母数が数倍に膨らむ（実測 22 → 51）。同じ成果を二重に数えないための制約であって、
取りこぼし対策ではない。

### 3. 中身を確認する

一覧の subject だけでテーマを決めない。判断が付かないコミットは diff を見る。

```sh
git -C "$PG" show --stat <sha>
git -C "$PG" show <sha> | head -80
```

確認すべきもの:

- `roles` が `mention` のもの → 本文でどう言及されているか読む。既定では**落とす**。
- `roles` に `author` と `reviewer` が両方付くもの → どちらの側に載せるか決める。
- `areas` が `-` のもの → 変更ファイルから手で領域を判断する。
- subject が汎用的すぎるもの（`Fix some inconsistencies with ...`）→ diff で実体を掴む。

### 4. テーマに束ねる

`reference/output-format.md` の規則に従って 3〜8 テーマに分ける。

- `areas` 列は出発点であって答えではない。同じ `documentation` でも、
  内容が統計ビューの説明ならそちらのテーマに入れてよい。
- **1 コミットは 1 テーマにだけ置く。** 複数に当てはまるものは
  「具体的なテーマ > 汎用の受け皿」「対象が限定される方 > 一般的な方」
  「それでも決まらなければ diff のパス」の順で寄せ先を決める
  （`reference/output-format.md` の「重複させない」節）。
- どのテーマにも収まらない小粒な修正は受け皿テーマ（`documentation fixes` など）に集める。

**テーマ案をユーザーに提示して合意を得てから最終形を書く。**
テーマ名と所属コミットの対応表を一度出し、寄せ方の希望を聞く。

### 5. 書き出す

```sh
mkdir -p ~/git/pgsql-toolbox/contributions
```

`contributions/postgresql.md` に `reference/output-format.md` の形式で書く。

- ハッシュと URL は `collect.py --md` の出力から機械的に持ってくる。
  **URL を手で組み立てない。**
- 末尾に出典行（対象リビジョン・そのハッシュと日付・マッチ件数・fetch したか）を残す。
- 同じ内容を会話にもコードブロックで貼る。

### 6. 検証する

**3 つとも通ること。** 1 つでも落ちたら該当行を作り直す。

```sh
F=~/git/pgsql-toolbox/contributions/postgresql.md
SKILL=~/git/pgsql-toolbox/.claude/skills/pg-contributions
grep -o '\[[0-9a-f]\{9\}\](' "$F" | tr -d '[](' | sort > /tmp/pgc-listed.txt

# (1) 重複掲載ゼロ — 出力があれば二重計上
uniq -d /tmp/pgc-listed.txt

# (2) 取りこぼしゼロ — 掲載ユニーク数と収集件数が一致するか
sort -u /tmp/pgc-listed.txt | wc -l
python3 "$SKILL/assets/collect.py" --roles author,reviewer | tail -n +5 | wc -l

# (3) 全ハッシュが origin/master に実在するか
sort -u /tmp/pgc-listed.txt | while read h; do
  git -C "$PG" log -1 --format="%h %s" "$h" origin/master >/dev/null 2>&1 \
    || echo "MISSING: $h"
done
```

(1) は 1 コミット 1 テーマの検算。(2) が一致しなければどこかのコミットが
どのテーマにも入っていない。(3) の `MISSING` は、打ち間違いか、stable ブランチの
バックパッチが紛れ込んでいるかのどちらか。`--roles` は実際に使った役割に合わせる。

## 重要な原則

- **裏取り最優先**: コミットから読み取れないことは書かない。効果や規模を推測で盛らない。
- **役割を混ぜない**: author と reviewer を黙って同じ括弧に入れない。既定は author のみ。
- **1 コミット 1 テーマ**: 重複掲載しない。掲載ハッシュのユニーク数と収集件数が一致する
  ことを検算に使う。
- **粒度は読み手基準**: ディレクトリ構造ではなく、価値が伝わる単位でテーマを切る。
- **master だけを見る**: 対象はサブモジュールの `origin/master`。バックパッチを枝ごとに
  数えない。
- **手集計しない**: 収集は `collect.py` に任せ、モデルは判断だけを担う。
- **ドキュメントは作らない**: HTML 生成もドキュメントサーバーへの配置もこのスキルの仕事ではない。

[db-internals-docs]: ../db-internals-docs/SKILL.md
