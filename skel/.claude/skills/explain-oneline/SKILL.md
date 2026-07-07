---
name: explain-oneline
description: >-
  Explain code line by line in Japanese (コードの逐行解説). Reads the user's IDE
  selection, or a function/file given as an argument, and outputs alternating
  small code blocks and concise Japanese explanations. Use whenever the user
  asks to walk through code in detail — "1行ずつ説明して", "このコードを解説して",
  "この関数何してるの", "explain this function line by line" — especially for
  PostgreSQL source code, where it also explains PG-specific concepts.
---

# Explain Code Line by Line

ユーザーが選択したコード、または引数で指定された関数・ファイルを1行ずつ日本語で説明する。

$ARGUMENTS

## Instructions

1. 説明対象を特定する。優先順位: (a) ユーザーの IDE 選択範囲、(b) 引数で指定されたコード（関数名、ファイルパス、`path:line` 形式など）。関数名だけが与えられた場合は Grep で定義を探す。どちらもない場合は、直前の会話で話題になっていたコードがあればそれを対象とし、なければ何を説明するか確認する
2. コード全体の要約を冒頭に1〜2文で述べる
3. コードブロックと説明を交互に出力する。各コードブロックは意味のまとまりごとに1〜3行程度にし、直後にその行が何をしているかを簡潔に日本語で説明する
4. 以下の点を意識する:
   - 変数宣言: 型と用途を説明
   - 制御構文: 条件分岐やループの目的を説明
   - 関数呼び出し: 呼び出し先の役割を簡潔に説明
   - マクロ/定数: 意味や値の背景を補足
   - ビット演算やポインタ操作: 何を実現しているか平易に説明
5. PostgreSQL 固有の概念（例: Datum, TupleDesc, LWLock, BRIN, WAL など）が出てきた場合は、初出時にその概念を1文で補足する

## Output format

以下の形をとる（説明はコードの「何を」だけでなく「なぜ」に触れると理解が深まる）:

````markdown
`RelationGetBufferForTuple` は、タプルを挿入できる空きスペースを持つバッファを探して返す関数。

```c
if (len > MaxHeapTupleSize)
    ereport(ERROR, ...);
```
挿入しようとするタプル長が1ページに収まる上限 `MaxHeapTupleSize` を超えていないか検査する。超過は TOAST 処理漏れなどの異常なのでエラーにする。

```c
saveFreeSpace = RelationGetTargetPageFreeSpace(relation, HEAP_DEFAULT_FILLFACTOR);
```
fillfactor 設定に基づき、ページに残しておくべき空き領域のバイト数を計算する。
````

長大な関数（数百行）の場合は、まず論理的なセクション分けを示してから各セクションを逐行解説し、定型的な繰り返し部分は適宜まとめてよい。
