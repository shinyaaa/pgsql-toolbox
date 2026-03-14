# PostgreSQL Mailing List MCP Search Server

PostgreSQL開発者がPostgreSQLメーリングリスト（pgsql-hackers, pgsql-bugs, pgsql-committers, pgsql-docs等）の過去の議論・パッチレビュー・技術的決定を、Claude CodeやCodexから自律的に検索できるシステム。MCPサーバーとして実装し、内部で全文検索（tsvector + pg_trgm）を実行する。複数のメーリングリストを横断検索、またはリスト名で絞り込み検索が可能。

## アーキテクチャ

```
Claude Code / Codex
    │  MCP (Streamable HTTP / stdio)
    ▼
┌─────────────┐     ┌──────────────────┐
│ mcp-server  │────▶│  PostgreSQL 18   │
│ (FastMCP)   │     │  + tsvector/GIN  │
│ port 40000   │     │  + pg_trgm       │
└─────────────┘     └──────────────────┘
                           ▲
┌─────────────┐            │
│  ingester   │────────────┘
│ (バッチ実行) │
└─────────────┘
       ▲
┌──────┴──────┐
│  data/mbox/ │
└─────────────┘
  ← download_mbox.sh
```

| コンテナ   | ベースイメージ     | 役割                  | ライフサイクル |
| ---------- | ------------------ | --------------------- | -------------- |
| db         | `postgres:18`      | PostgreSQL + 全文検索 | 常駐           |
| mcp-server | `python:3.13-slim` | MCPプロトコルサーバー | 常駐           |
| ingester   | `python:3.13-slim` | mboxパース・DB投入    | バッチ実行     |

`docker compose up -d`でdb + mcp-serverが起動し、ingesterは`docker compose run --rm ingester`で明示的に実行する。

## セットアップ

### 1. mbox ファイルのダウンロード

PostgreSQL公式アーカイブからmbox形式で月次ダウンロードする。

- **URL**: `https://www.postgresql.org/list/{LIST_NAME}/mbox/{LIST_NAME}.YYYYMM`
- **形式**: mbox（Python stdlib `mailbox.mbox`で直接パース可能）
- **複数リスト対応**: ファイル名（例: `pgsql-hackers.202601`）からリスト名を自動検出

```bash
# Usage: ./scripts/download_mbox.sh LIST_NAME START_YYYYMM END_YYYYMM
./scripts/download_mbox.sh pgsql-bugs 199811 202601
./scripts/download_mbox.sh pgsql-committers 200004 202601
./scripts/download_mbox.sh pgsql-docs 199806 202601
./scripts/download_mbox.sh pgsql-hackers 199706 202601
```

> **注意**: サーバー側で認証やレート制限がある場合、スクリプトによるダウンロードが失敗することがあります。その場合はブラウザから手動でダウンロードし、`data/mbox/{LIST_NAME}/` ディレクトリに `{LIST_NAME}.YYYYMM` の形式で配置してください。

### 2. DB 起動とデータ投入

```bash
docker compose up -d db
docker compose run --rm ingester

# 投入結果を確認
docker compose exec db psql -U hackers -d pgsql_hackers \
  -c "SELECT count(*) FROM messages; SELECT count(*) FROM patches;"
```

### DB の再構成（全データ消去）

スキーマ変更時など、既存データを全て消去してDBを一から再構成する場合:

```bash
docker compose down
docker volume rm pgsql-ml-mcp_pgdata
docker compose up -d db
docker compose run --rm ingester
```

### 3. MCP サーバーの起動

```bash
docker compose up -d
```

MCP エンドポイントは `http://localhost:40000/mcp`。

### 4. Claude Code への登録

```bash
claude mcp add --transport http pgsql-ml-mcp http://localhost:40000/mcp
```

登録後、Claude Code から自然に検索が利用できる：

> "pgsql-hackers で vacuum freeze に関する議論を検索して"
> "pgsql-bugs でレプリケーションに関するバグ報告を探して"

## MCP ツール

### list_mailing_lists

取り込み済みのメーリングリスト一覧をメッセージ数・日付範囲とともに返す。

### search_messages

メッセージを検索する。クエリの種類を自動判定し、適切な検索方式を選択する。

| クエリ種別 | 検索方式              | 例                                                   |
| ---------- | --------------------- | ---------------------------------------------------- |
| 自然言語   | tsvector（全文検索）  | `vacuum freeze`, `WAL performance`                   |
| 識別子     | pg_trgm（部分文字列） | `heapam_tuple_insert`, `ExecInitNode`, `nbtinsert.c` |

**パラメータ:**
- `query` (string, 必須) - 検索クエリ
- `list_name` (string, オプション) - メーリングリスト名で絞り込み（例: `pgsql-hackers`）。省略時は全リスト横断検索
- `author` (string, オプション) - 著者名またはメールアドレスで絞り込み（部分一致、大文字小文字不問）
- `limit` (int, 1-50, デフォルト 10) - 最大取得件数
- `offset` (int, デフォルト 0) - ページネーション用オフセット

### get_message

message_id を指定してメッセージの全文を取得する。

**パラメータ:**
- `message_id` (string, 必須) - メッセージの Message-ID

### search_patches

パッチをファイルパス、関数名、キーワードで検索する。

**パラメータ:**
- `query` (string, 必須) - ファイルパス・関数名・キーワード
- `list_name` (string, オプション) - メーリングリスト名で絞り込み。省略時は全リスト横断検索
- `limit` (int, 1-50, デフォルト 10) - 最大取得件数
- `offset` (int, デフォルト 0) - ページネーション用オフセット

### get_patch

patch_id を指定してパッチの生 diff を取得する。

**パラメータ:**
- `patch_id` (int, 必須) - パッチ ID

### get_thread

スレッド内の全メッセージを時系列で取得する。長大なスレッドはコンテキストウィンドウに収まるよう自動的に本文が切り詰められる。

**パラメータ:**
- `thread_id` (string, 必須) - スレッド ID


## 技術選択の根拠

### MCP + 全文検索

MCP（Model Context Protocol）はClaude Code/Codexがデータソースにアクセスするインターフェース（プロトコル）。MCPサーバーが全文検索エンジン（tsvector + pg_trgm）を内部に持ち、LLMが自律的にキーワードを選択して検索する構成。

### ローカルDB（vs. ネットワーク）

メーリングリストのメッセージは不変（イミュータブル）であり、一度取り込めば更新不要。

| 観点         | ネットワーク       | ローカルDB                 |
| ------------ | ------------------ | -------------------------- |
| 鮮度         | 常に最新           | 取り込みパイプラインに依存 |
| レイテンシ   | 遅い               | 速い                       |
| 信頼性       | 外部依存           | 自己完結                   |
| インデックス | 都度構築は非現実的 | 事前構築可能               |

差分取り込みパイプラインで鮮度の問題も解決できる。

### リレーショナル（vs. KVS）

メールには豊富なメタデータがある（Message-ID, In-Reply-To, References, From, Date, Subject）。スレッド再構成、著者・時系列フィルタリングなど構造化クエリの需要が高く、KVSでは非効率。PostgreSQLの開発補助にPostgreSQLを使うのは自然であり、tsvector・pg_trgmも統一的に扱える。

### tsvector + pg_trgm 併用

PostgreSQLメーリングリストの検索には性質の異なる2種類のクエリがあり、それぞれ最適な検索方式が異なる。

| 方式                  | 得意なクエリ             | 例                                                   |
| --------------------- | ------------------------ | ---------------------------------------------------- |
| tsvector（単語単位）  | 自然言語による議論の検索 | 「vacuum freezeの性能改善」「WAL書き込みの議論」     |
| pg_trgm（部分文字列） | 識別子・コード要素の検索 | `heapam_tuple_insert`, `nbtinsert.c`, `ExecInitNode` |

**tsvector**はステミング（`improving` → `improve`にマッチ）、ストップワード除去、ランキング（`ts_rank_cd`）、スニペット生成（`ts_headline`）を提供する。自然言語の検索に最適。

**pg_trgm**は文字の3-gram（トライグラム）による部分文字列マッチを提供する。`heapam`で`heapam_tuple_insert`にヒットし、`ExecInit`で`ExecInitNode`や`ExecInitExpr`にマッチする。PostgreSQL開発メーリングリストでは関数名・ファイル名・GUCパラメータ名の検索が非常に重要であり、tsvectorの単語単位マッチでは不十分なため、pg_trgmを併用する。

**ベクトル検索（pgvector）は不採用**: pgsql-hackersの検索は用語ベースのクエリが圧倒的に多く（関数名、ファイル名、GUCパラメータ、具体的な概念名）、意味的な類似検索の恩恵が少ない。また利用者がLLMであるため、適切なキーワードの選択やクエリの言い換えが自律的に可能。embedding生成のAPIコスト・レイテンシ・外部依存を排除し、完全にセルフコンテインドなシステムとする。

## ディレクトリ構成

```
pgsql-ml-mcp/
├── scripts/       # mboxダウンロードスクリプト
├── db/            # PostgreSQL設定・スキーマ
├── mcp-server/    # MCPプロトコルサーバー
├── ingester/      # mboxパース・DB投入
└── data/          # mboxファイル（.gitignore）
```

## 検証手順

```bash
# 1. DB起動
docker compose up -d db

# 2. データ取得（1ヶ月分で動作確認）
./scripts/download_mbox.sh pgsql-hackers 202601 202601

# 3. データ投入
docker compose run --rm ingester

# 4. MCPサーバー起動・確認
docker compose up -d mcp-server
curl -X POST http://localhost:40000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# 5. Claude Code統合
claude mcp add --transport http pgsql-ml-mcp http://localhost:40000/mcp
# Claude Codeで: "Search pgsql-hackers for discussions about vacuum freeze"
```

## 技術スタック

- **DB**: PostgreSQL 18 + pg_trgm
- **MCP サーバー**: Python 3.13 + [FastMCP](https://github.com/modelcontextprotocol/python-sdk) (mcp[cli])
- **DB ドライバ**: psycopg 3（MCP サーバー: async / ingester: sync）
- **コンテナ**: Docker Compose（マルチアーキテクチャ対応）

## ライセンス

PostgreSQL License
