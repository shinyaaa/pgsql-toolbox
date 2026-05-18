---
name: explain-oneline
description: Explain selected code line by line in Japanese. Reads the user's IDE selection or a specified function/file and provides a concise explanation for each line.
---

# Explain Code Line by Line

ユーザーが選択したコード、または引数で指定された関数・ファイルを1行ずつ日本語で説明する。

$ARGUMENTS

## Instructions

1. ユーザーの IDE 選択範囲、または引数で指定されたコード（関数名、ファイルパスなど）を読み取る
2. コードブロックと説明を交互に出力する。各コードブロックは1〜3行程度にし、直後にその行が何をしているかを簡潔に日本語で説明する
3. 以下の点を意識する:
   - 変数宣言: 型と用途を説明
   - 制御構文: 条件分岐やループの目的を説明
   - 関数呼び出し: 呼び出し先の役割を簡潔に説明
   - マクロ/定数: 意味や値の背景を補足
   - ビット演算やポインタ操作: 何を実現しているか平易に説明
4. PostgreSQL 固有の概念（例: Datum, TupleDesc, LWLock, BRIN, WAL など）が出てきた場合は、その概念を補足する
5. コード全体の要約は冒頭に1文で述べ、その後に行ごとの説明を続ける
