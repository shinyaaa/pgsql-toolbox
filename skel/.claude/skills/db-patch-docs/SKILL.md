---
name: db-patch-docs
description: >-
  git のパッチシリーズ（コミット列）を、読んだ人がそのパッチをレビューできる状態になるまで
  解き明かす日本語の解説ドキュメントを生成し、pgsql-toolbox のドキュメントサーバー
  (port 30002) の「Patch」タブに載せる。各コミットを「問題 → 設計（採用と見送り）→
  仕組み（実コード＋図）→ 落とし穴 → テスト」で読み解き、末尾に即時採点つきの理解度チェックを置く。
  「このパッチの解説ドキュメントを作って」「パッチ解説ドキュメントを生成して」「コミットの解説を書いて」
  「パッチ読解ノート／レビュー用の資料を作って」「この数コミットを理解できる資料にして」といった依頼で起動する。
---

# db-patch-docs（worktree からの入口）

**本体は pgsql-toolbox 側にある。** このファイルは worktree のセッションから同じ依頼で
起動できるようにするための入口で、手順とスタイル規約は本体を読むこと。

```
~/git/pgsql-toolbox/.claude/skills/db-patch-docs/
├── SKILL.md                     ← 手順はこれに従う
├── assets/build.py              ← 生成器（HTML は手書きしない）
├── assets/{index-template.html,style.css}
└── reference/{style-guide.md,quiz-rules.md,content-schema.md}
```

## 進め方

1. `~/git/pgsql-toolbox/.claude/skills/db-patch-docs/SKILL.md` を読み、そのワークフローに従う。
   本文を書く前に `reference/style-guide.md` を、クイズを書く前に `reference/quiz-rules.md` を読む。
2. 解説対象のコミットは**この worktree**（今いるリポジトリ）から読む。`git show` と周辺コードで
   裏を取り、端末出力は実際に採取する。
3. 素材（`content.json`）はこの worktree の `work/tmp/` などに書き、生成物の置き場は
   **pgsql-toolbox 側** `~/git/pgsql-toolbox/internals/patch_docs/<slug>/`。
   build.py が素材を生成先にも残すので、次からは生成先のものを編集して再生成できる。

```sh
SKILL=~/git/pgsql-toolbox/.claude/skills/db-patch-docs
OUT=~/git/pgsql-toolbox/internals/patch_docs/<slug>
mkdir -p "$OUT"
python3 "$SKILL/assets/build.py" work/tmp/content.json --out "$OUT"
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:30002/patch/<slug>/
```

生成物は `http://127.0.0.1:30002/patch/<slug>/` で配信される（サーバの再起動は不要）。
`internals/` は git 管理下なので、確認できたら pgsql-toolbox 側でコミットする。
