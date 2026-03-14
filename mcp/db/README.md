# DB設計

## 概要

PostgreSQL 18をDockerコンテナとして運用する。メーリングリストのメッセージ・スレッド構造・パッチデータ・著者情報をリレーショナルに保存し、tsvector（自然言語検索）+ pg_trgm（識別子検索）を提供する。

## ER図

```
┌─────────────────┐     ┌─────────────────────────────┐
│    authors      │     │      author_emails          │
├─────────────────┤     ├─────────────────────────────┤
│ author_id  [PK] │◀──┐ │ email        [PK]           │
│ display_name    │   └─│ author_id    [FK] → authors  │
│ is_committer    │     └─────────────────────────────┘
└────────┬────────┘
         │ 1
         │
         │ *
┌────────┴────────────────────────────────┐   ┌─────────────────┐
│            messages                     │   │    threads      │
├─────────────────────────────────────────┤   ├─────────────────┤
│ message_id  [PK]                        │   │ thread_id  [PK] │
│ list_name                               │   │ subject         │
│ thread_id   [FK] → threads              │ *▶│ status          │
│ parent_id                               │   │ list_names []   │
│ sender                                  │   │ started_at      │
│ author_id   [FK] → authors              │   │ ended_at        │
│ sent_at                                 │   └─────────────────┘
│ subject                                 │
│ body                                    │
│ body_raw                                │
│ body_tsv    (GENERATED)                 │
└──────────────┬──────────────────────────┘
               │ 1
               │
               │ *
┌──────────────┴──────────────────────────┐
│           patches                       │
├─────────────────────────────────────────┤
│ patch_id      [PK] SERIAL              │
│ message_id    [FK] → messages           │
│ filename                                │
│ content_type                            │
│ files_changed  TEXT[]                   │
│ raw_diff                                │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│         ingestion_log                   │
├─────────────────────────────────────────┤
│ mbox_file      [PK]                     │
│ message_count                           │
│ ingested_at                             │
└─────────────────────────────────────────┘
```

- **authors 1 ← * author_emails**: 1人の著者に複数のメールアドレスが紐づく
- **authors 1 ← * messages**: 1人の著者が複数のメッセージを投稿する
- **threads 1 ← * messages**: 1つのスレッドに複数のメッセージが属する
- **messages 1 ← * patches**: 1つのメッセージに複数のパッチが添付される場合がある
- **ingestion_log**: 他テーブルとのリレーションなし（取り込み管理用の独立テーブル）

## 主要な設計判断

### パッチを本文から分離する理由

diff形式のテキストは全文検索の精度を下げるため、patchesテーブルに分離する。検索時はメタデータ（`files_changed`）で絞り込み、必要時に`raw_diff`を取得する2段階方式とする。

### tsvector vs pg_trgm の使い分け

PostgreSQLメーリングリストの検索では**自然言語**と**識別子**の両方が不可欠なため、2方式を併用する。

| 方式 | マッチ単位 | 得意なクエリ |
|------|-----------|-------------|
| tsvector | 単語 | 自然言語（「vacuum freezeの性能改善」）。ステミング・ランキング（`ts_rank_cd`）・スニペット（`ts_headline`）が使える |
| pg_trgm | 文字3-gram | 識別子（`heapam_tuple`, `nbtinsert.c`, `ExecInitNode`）。tsvectorの単語境界マッチでは`heapam_tuple`で`heapam_tuple_insert`を見つけられない |

MCPサーバーがクエリの性質を自動判定し、適切な方式を選択する（詳細は`mcp-server/README.md`を参照）。

### websearch_to_tsquery の採用理由

`plainto_tsquery`ではなく`websearch_to_tsquery`を採用する理由:
- LLMがフレーズ・OR・NOTを含む精密なクエリを構築できる
- Google風の構文でtool descriptionに自然に記述できる
- 構文エラー時は`plainto_tsquery`にフォールバック

## インデックス戦略

| インデックス | 種別 | 用途 |
|-------------|------|------|
| `idx_messages_tsv` | GIN (tsvector) | `body_tsv @@ websearch_to_tsquery(...)` — 自然言語全文検索 |
| `idx_messages_body_trgm` | GIN (pg_trgm) | `body ILIKE '%heapam_tuple%'` — 識別子の部分文字列検索 |
| `idx_messages_thread` | B-tree | スレッド内全メッセージ取得 |
| `idx_messages_sent_at` | B-tree | 期間絞り込み |
| `idx_messages_sender` | B-tree | 送信者検索 |
| `idx_messages_author` | B-tree | 著者ID検索 |
| `idx_messages_parent` | B-tree | 親子関係の辿り |
| `idx_messages_list_name` | B-tree | メーリングリスト名での絞り込み |
| `idx_authors_display_name` | GIN (pg_trgm) | 著者名のトライグラム検索 |
| `idx_author_emails_author` | B-tree | メールアドレス→著者の逆引き |
| `idx_threads_status` | B-tree | ステータスでの絞り込み |
| `idx_threads_started_at` | B-tree | スレッド開始日での絞り込み |
| `idx_threads_ended_at` | B-tree | スレッド終了日での絞り込み |
| `idx_threads_list_names` | GIN (array) | メーリングリスト名でのスレッド絞り込み |
| `idx_patches_message` | B-tree | パッチ→メッセージの結合 |
| `idx_patches_files` | GIN (array) | `files_changed @> ARRAY['src/...']` — 変更ファイルパス検索 |

## 初期化スクリプト

| ファイル | 内容 |
|----------|------|
| `init/01_extensions.sql` | `CREATE EXTENSION IF NOT EXISTS pg_trgm` |
| `init/02_schema.sql` | テーブル・インデックス定義 |
| `init/03_committers.sql` | コミッター一覧の初期データ投入 |

`docker-entrypoint-initdb.d`により初回起動時のみアルファベット順で実行される。スキーマ変更は`init/02_schema.sql`を直接編集しDBを再作成する（開発中のため）。
