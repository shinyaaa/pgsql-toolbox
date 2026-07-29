# content.json のスキーマ

`assets/build.py` が読む素材ファイルの形式。日本語の本文はすべて常体で書く。
キー名は `foo` でも `foo_ja` でもよい（build.py が吸収する）。

```json
{
  "title": "pgbench 5パッチ精読ノート",
  "version_info": "PostgreSQL 20devel · e395fbd32a0 · 2026-07-28",
  "series_info": "postgres / src/bin/pgbench — patch series 0001–0005",
  "lead": "このノートが何を解き明かすか。2〜3 文。",
  "overview": {
    "reading": "シリーズ内での各パッチの位置づけと、全章に共通する土台を示す 1〜2 段落。",
    "facts": [["ベースコミット", "e395fbd32a0"], ["TAP テスト", "871 passed, 0 failed"]]
  },
  "footer": "ブランチ名やパッチの入手方法など 1 行。",
  "patches": [
    {
      "seq": "0001",
      "slug": "gset-null",
      "short": "\\gset の NULL",
      "title": "章タイトル（コミット件名の翻案でよい）",
      "summary": "3〜4 文の要約。何を変えたか、なぜそう変えたか。",
      "commit": "cb24dfdf151",
      "subject": "Make pgbench \\gset and \\aset store SQL NULL as the null value",
      "files": 3, "insertions": 117, "deletions": 3,

      "problem": {
        "narrative": "パッチ前に何が起きていたか。2〜4 文。",
        "repro": "$ で始まる端末セッション。前後に地の文を置いてよい（build.py が分離する）。"
      },

      "design": [
        {
          "decision": "採用した設計。",
          "rationale": "なぜそれで正しいのか。",
          "rejected": "却下した案と、それがなぜ壊れるか。無ければ空文字列。"
        }
      ],

      "diagram_mermaid": "flowchart TD\n  A[\"...\"] --> B[\"...\"]",

      "code_walkthrough": [
        {
          "caption": "src/bin/pgbench/pgbench.c / readCommandResponse()",
          "code": "コミット後のファイルからの逐語引用（20 行程度まで、タブ保持）",
          "explain": "なぜこの順序・この位置なのか。"
        }
      ],

      "gotchas": [{ "title": "短い見出し", "detail": "踏む条件と結果。" }],
      "tests":   [{ "what": "何を固定しているか", "how": "どのテストがどう検証するか" }],

      "quiz": [
        {
          "question": "設問。",
          "options": ["A の文", "B の文", "C の文", "D の文"],
          "correct_index": 0,
          "explain": "正解の理由と、最も紛らわしい誤答がなぜ違うか。"
        }
      ]
    }
  ]
}
```

## 生成器が面倒を見ること（素材側で気にしなくてよいこと）

- **選択肢のシャッフル**: `correct_index` は素材の並びに対する 0 始まりで書けばよい。build.py が設問ごとに決定的にシャッフルし、正解位置を散らす。
- **解説中の選択肢参照**: **記号 (A〜D) で書く**。素材の並びに対する記号でよく、build.py が
  シャッフル後の記号へ書き換える。番号での参照も旧素材のために解決するが、参照直後の文が
  その選択肢を言い換えていないと解決できず、生成が止まる。
- **端末出力と地の文の分離**: `problem.repro` は端末セッションの前後に説明文を含めてよい。build.py が最初のプロンプト行から地の文が再開する行までを実行例ブロックに切り出し、残りを段落にする。
- **`rejected` の省略**: `"なし"` や `"-"` を入れると見送り欄そのものを出さない。
- **素材の複製**: build.py は入力の `content.json` を出力先にも残すので、次回からは出力先の
  ものを編集して再生成できる。
- **HTML エスケープ**: `code` と `repro` はそのまま書く。エスケープは build.py が行う。Mermaid のラベル内の `<` は build.py が実体参照にする。

## 生成器が検査すること

`build.py` は生成後に自己検査を行い、問題があれば標準エラーへ出して終了コード 1 を返す。

- 正解位置の分布 (各記号 15〜35%、同一記号の 3 連続なし。設問が 4 問未満なら検査しない)
- 解説が正解の選択肢を誤答として参照していないか
- 番号のままの選択肢参照が残っていないか
- 選択肢が 4 つで correct_index が範囲内か (素材読み込み時、終了コード 2)
- クイズのリンク先アンカーが本文にあるか
- タグの開閉が合っているか、テンプレートの置換漏れがないか
- コード片が 30 行を超えていないか

問題が見つかったときは**何も書き出さずに終了する** (終了コード 1)。警告 (選択肢の長さなど) は
生成を止めない。どうしても出力したいときだけ `--force` を使う。
