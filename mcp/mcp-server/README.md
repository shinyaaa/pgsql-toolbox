# MCPサーバー設計

## 概要

Claude Code/CodexからPostgreSQLメーリングリストを検索するためのMCPサーバー。FastMCP（Python公式SDK）で実装し、Streamable HTTPトランスポートでDockerコンテナとして常駐する。

## 使用SDK・ライブラリ

```
mcp[cli]==1.26.*       # MCP Python SDK（FastMCP統合）
psycopg[binary]==3.2.* # PostgreSQLアダプタ
psycopg_pool==3.2.*    # 非同期接続プール
```

- **FastMCP**: Python公式SDKに統合されたフレームワーク。デコレータでツール定義、型ヒントとdocstringからスキーマを自動生成。
- **psycopg_pool.AsyncConnectionPool**: MCPサーバーのasyncツールハンドラから非同期にDB接続を使用。min_size=2, max_size=10（シングルユーザー想定）。

## ファイル構成

```
mcp-server/
├── Dockerfile
├── requirements.txt
└── src/
    ├── __init__.py
    ├── db.py          # 非同期DB接続プール・検索クエリ
    └── server.py      # FastMCPツール定義・エントリポイント
```

## トランスポート

### Streamable HTTP（デフォルト）

Dockerコンテナとの相性が良い。ポート40000でリッスンし、`/mcp`エンドポイントで通信する。

```bash
# Claude Codeからの接続
claude mcp add --transport http pgsql-ml-mcp http://localhost:40000/mcp
```

### stdio（代替）

`docker exec -i`経由でstdioトランスポートも使用可能。

```bash
claude mcp add pgsql-ml-mcp -- docker exec -i -e MCP_TRANSPORT=stdio pgsql-ml-mcp-mcp-server-1 python -m src.server
```

### 切り替え

環境変数`MCP_TRANSPORT`で制御。デフォルトは`streamable-http`。

## ツール一覧

| ツール | 機能 |
|--------|------|
| `list_mailing_lists` | 取り込み済みメーリングリスト一覧の取得 |
| `search_messages` | 自然言語・識別子でメッセージ検索（自動判定） |
| `get_message` | message_idでメッセージ全文取得 |
| `search_patches` | ファイルパス・関数名・キーワードでパッチ検索 |
| `get_patch` | 特定パッチの生diff取得 |
| `get_thread` | スレッド内全メッセージを時系列取得 |

### tool descriptionの設計方針

LLMはtool descriptionを読んでツールの選択・引数の構成を決定する。メーリングリスト検索の有用性はdescriptionの品質に直結するため、以下を徹底する:

1. **ツールが何を検索するか**を明示（「PostgreSQL mailing list archive」）
2. **クエリ構文**を例示付きで記述（フレーズ、OR、NOT）
3. **返却フィールド**を列挙し、次のアクションを示唆
4. **hintフィールド**で次に取るべきアクションをLLMに誘導

## ツール定義

### search_messages

メーリングリストメッセージの検索。クエリの性質に応じて2つの検索モードを自動選択する。

**パラメータ:**

| 名前 | 型 | デフォルト | 説明 |
|------|-----|-----------|------|
| `query` | str | (必須) | 検索クエリ |
| `list_name` | str | "" | メーリングリスト名で絞り込み。空文字で全リスト横断検索 |
| `author` | str | "" | 著者名またはメールアドレスで絞り込み（部分一致、大文字小文字不問）。空文字で全著者 |
| `limit` | int | 10 | 最大結果数（1〜50） |
| `offset` | int | 0 | ページネーション用オフセット |

**検索方式の自動判定:**

1. **pg_trgm（部分文字列検索）**: クエリが以下のパターンにマッチする場合
   - `snake_case`: `[a-z]_[a-z]`（例: `heapam_tuple_insert`）
   - `CamelCase`: `[A-Z][a-z]+[A-Z]`（例: `ExecInitNode`）
   - ファイルパス: `\.\w+` で終わる（例: `nbtinsert.c`）

2. **tsvector（自然言語検索）**: 上記パターンにマッチしない場合

**tsvector検索時のクエリ構文（websearch）:**
- 単語: `vacuum` → vacuumを含むメッセージ
- フレーズ: `"vacuum freeze"` → 完全一致
- AND（デフォルト）: `vacuum autovacuum` → 両方を含む
- OR: `vacuum OR autovacuum` → いずれかを含む
- NOT: `-autovacuum vacuum` → vacuumを含むがautovacuumを含まない

**返却フォーマット:**

```json
{
  "total_results": 5,
  "search_mode": "tsvector",
  "messages": [
    {
      "message_id": "abc123@postgresql.org",
      "list_name": "pgsql-hackers",
      "subject": "Re: Improve vacuum freeze performance",
      "sender": "Tom Lane <tgl@sss.pgh.pa.us>",
      "date": "2026-01-15T14:32:00-04:00",
      "thread_id": "root456@postgresql.org",
      "thread_status": "committed",
      "relevance": 0.8234,
      "snippet": "...the <b>vacuum</b> <b>freeze</b> operation should be..."
    }
  ],
  "hint": "Use get_message with a message_id to read the full message body."
}
```

`search_mode`フィールド: `"tsvector"` または `"trigram"`。

**検索SQL（tsvector — 自然言語）:**

```sql
SELECT
    m.message_id, m.list_name, m.subject, m.sender, m.sent_at,
    m.thread_id, t.status AS thread_status,
    ts_rank_cd(m.body_tsv, websearch_to_tsquery('english', $1)) AS rank,
    ts_headline('english', m.body,
        websearch_to_tsquery('english', $1),
        'MaxWords=60, MinWords=20, MaxFragments=3') AS snippet
FROM messages m
LEFT JOIN threads t ON m.thread_id = t.thread_id
WHERE m.body_tsv @@ websearch_to_tsquery('english', $1)
ORDER BY rank DESC, m.sent_at DESC
LIMIT $2 OFFSET $3
```

**検索SQL（pg_trgm — 識別子）:**

```sql
SELECT
    m.message_id, m.list_name, m.subject, m.sender, m.sent_at,
    m.thread_id, t.status AS thread_status,
    similarity(m.body, $1) AS rank,
    substring(m.body FROM greatest(1, position(lower($1) in lower(m.body)) - 100)
              FOR 200 + length($1)) AS snippet
FROM messages m
LEFT JOIN threads t ON m.thread_id = t.thread_id
WHERE m.body ILIKE '%' || $1 || '%'
ORDER BY rank DESC, m.sent_at DESC
LIMIT $2 OFFSET $3
```

### get_message

message_idで特定メッセージの全文を取得。

**パラメータ:**

| 名前 | 型 | 説明 |
|------|-----|------|
| `message_id` | str | 取得するメッセージのMessage-ID |

**返却フォーマット:**

```json
{
  "message_id": "abc123@postgresql.org",
  "list_name": "pgsql-hackers",
  "thread_id": "root456@postgresql.org",
  "parent_id": "parent789@postgresql.org",
  "subject": "Re: Improve vacuum freeze performance",
  "sender": "Tom Lane <tgl@sss.pgh.pa.us>",
  "date": "2026-01-15T14:32:00-04:00",
  "thread_subject": "Improve vacuum freeze performance",
  "thread_status": "committed",
  "body": "Full message body text...",
  "body_truncated": false,
  "patch_count": 2,
  "hint": "This message has 2 patch(es). Use search_patches... Use get_thread..."
}
```

### search_patches

パッチファイルの検索。ファイル名、変更ファイルパス、diff内容を横断検索する。

**パラメータ:**

| 名前 | 型 | デフォルト | 説明 |
|------|-----|-----------|------|
| `query` | str | (必須) | ファイルパス・関数名・キーワード |
| `list_name` | str | "" | メーリングリスト名で絞り込み |
| `limit` | int | 10 | 最大結果数（1〜50） |
| `offset` | int | 0 | ページネーション用オフセット |

**検索SQL:**

```sql
SELECT p.patch_id, p.message_id, m.list_name, p.filename, p.files_changed,
       m.subject, m.sender, m.sent_at,
       substring(p.raw_diff FROM 1 FOR 500) AS diff_preview
FROM patches p
JOIN messages m ON p.message_id = m.message_id
WHERE EXISTS (SELECT 1 FROM unnest(p.files_changed) f WHERE f ILIKE '%' || $1 || '%')
   OR p.filename ILIKE '%' || $1 || '%'
   OR p.raw_diff ILIKE '%' || $1 || '%'
ORDER BY m.sent_at DESC
LIMIT $2 OFFSET $3
```

**返却フォーマット:**

```json
{
  "total_results": 3,
  "patches": [
    {
      "patch_id": 42,
      "message_id": "abc123@postgresql.org",
      "list_name": "pgsql-hackers",
      "filename": "v2-0001-improve-vacuum.patch",
      "files_changed": ["src/backend/access/heap/vacuumlazy.c"],
      "subject": "Re: [PATCH v2] Improve vacuum freeze",
      "sender": "...",
      "date": "...",
      "diff_preview": "diff --git a/src/backend/..."
    }
  ],
  "hint": "Use get_patch with a patch_id to retrieve the full diff."
}
```

### get_patch

patch_idで特定パッチの生diffを取得。

**パラメータ:**

| 名前 | 型 | 説明 |
|------|-----|------|
| `patch_id` | int | パッチID |

**返却フォーマット:**

```json
{
  "patch_id": 42,
  "message_id": "abc123@postgresql.org",
  "list_name": "pgsql-hackers",
  "filename": "v2-0001-improve-vacuum.patch",
  "content_type": "text/x-patch",
  "files_changed": ["src/backend/access/heap/vacuumlazy.c"],
  "subject": "...",
  "sender": "...",
  "date": "...",
  "raw_diff": "diff --git a/...\n--- a/...\n+++ b/...\n@@ ...",
  "diff_truncated": false,
  "hint": "Use get_message with message_id to see the discussion context."
}
```

raw_diffは最大20,000文字で切り詰め。`diff_truncated: true`で通知。

### get_thread

スレッド内の全メッセージを時系列で取得。コンテキストウィンドウ管理付き。

**パラメータ:**

| 名前 | 型 | 説明 |
|------|-----|------|
| `thread_id` | str | スレッドID（ルートメッセージのMessage-ID） |

**コンテキストウィンドウ管理:**

スレッドが長大な場合、LLMのコンテキストウィンドウを圧迫しないよう本文を自動的に切り詰める:

- **最近20%のメッセージ（最低3件）**: body最大2,000文字
- **古いメッセージ**: body最大200文字
- 全体が30,000文字を超える場合: 古いメッセージのbodyをさらに100文字に切り詰め
- 各メッセージに`body_truncated`フラグを付与

**返却フォーマット:**

```json
{
  "thread_id": "root456@postgresql.org",
  "subject": "Improve vacuum freeze performance",
  "status": "committed",
  "list_names": ["pgsql-hackers"],
  "started_at": "2026-01-01T10:00:00-04:00",
  "ended_at": "2026-01-20T15:30:00-04:00",
  "message_count": 15,
  "messages": [
    {
      "message_id": "...",
      "list_name": "pgsql-hackers",
      "parent_id": null,
      "subject": "Improve vacuum freeze performance",
      "sender": "...",
      "date": "...",
      "body": "I propose to improve...",
      "body_truncated": false,
      "body_length": 1234,
      "patch_count": 1
    }
  ],
  "hint": "Use get_message with a message_id to read any message's full body."
}
```

## コンテキストウィンドウ管理

### 本文切り詰め（get_message）

`get_message`は本文を最大12,000文字で切り詰める。

- 12,000文字 ≈ 3,000トークン
- `body_truncated: true`フラグで切り詰めを通知
- LLMのコンテキストウィンドウを圧迫しない

### Diff切り詰め（get_patch）

`get_patch`はraw_diffを最大20,000文字で切り詰める。

- `diff_truncated: true`フラグで切り詰めを通知

### スレッド切り詰め（get_thread）

`get_thread`はスレッド全体を最大30,000文字に収める。

- 最近のメッセージにbody予算を多く割り当て
- 古いメッセージはメタデータ+短いプレビューのみ
- 各メッセージの`body_length`で元の長さを通知

### スニペット長

`search_messages`のスニペットは`MaxWords=60, MaxFragments=3`で生成。1件あたり約200〜300文字。10件返しても3,000文字程度。

### 結果件数制限

`limit`パラメータの上限を50件に制限。デフォルト10件。

## エラーハンドリング

### websearch_to_tsquery構文エラー

LLMが不正なクエリ構文を生成した場合、`plainto_tsquery`にフォールバックする。

```python
try:
    results = await search_with_websearch(query)
except Exception:
    results = await search_with_plainto(query)
```

### メッセージ/パッチ/スレッド未検出

該当なしの場合、エラーメッセージとhintを返す。

```json
{
  "error": "Message not found: abc123@postgresql.org",
  "hint": "Double-check the message_id from search results."
}
```

## Dockerfile

```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
CMD ["python", "-m", "src.server"]
```

デフォルトでStreamable HTTPトランスポート（port 40000）で起動する。

## LLM利用シナリオ例

```
ユーザー: "PostgreSQLのvacuum freezeの最近の議論を教えて"

1. Claude Code → search_messages(query="vacuum freeze", limit=10)
   → search_mode: "tsvector"
2. 結果のsnippetを確認し、最も関連性の高いmessage_idを選択
3. Claude Code → get_message(message_id="...")
4. 全文を読み、ユーザーへの回答を合成
```

```
ユーザー: "Tom LaneがB-treeのnbtinsert.cについて何と言っていたか"

1. Claude Code → search_messages(query="nbtinsert.c B-tree", author="Tom Lane")
   → 著者フィルタ + トピック検索
2. 結果からスレッドを特定
3. Claude Code → get_thread(thread_id="...")
   → スレッド全体の議論を時系列で確認
4. 議論の要約を作成
```

```
ユーザー: "nbtinsert.cを変更したパッチを見せて"

1. Claude Code → search_patches(query="nbtinsert.c")
   → ファイルパス検索
2. 結果からパッチを選択
3. Claude Code → get_patch(patch_id=42)
   → 生diffを確認
4. Claude Code → get_message(message_id="...")
   → パッチの議論コンテキストを確認
```

```
ユーザー: "heapam_tuple_insertの実装を変更した議論"

1. Claude Code → search_messages(query="heapam_tuple_insert")
   → 自動判定: snake_caseパターン → pg_trgm検索
2. 部分一致でheapam_tuple_insert, heapam_tuple_insert_speculative等にもヒット
3. Claude Code → get_message(message_id="...") で詳細確認
```
