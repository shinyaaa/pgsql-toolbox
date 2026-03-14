# データ投入設計

## 概要

mbox形式のメーリングリストアーカイブをパースし、メッセージ・スレッド構造・パッチデータをPostgreSQLに投入するバッチ処理パイプライン。Dockerコンテナとして実装し、`docker compose run --rm ingester`で実行する。

## パイプライン全体フロー

```
1. PostgreSQLに接続（リトライ付き）
2. /data/mbox/ 内のmboxファイルを列挙（ファイル名からリスト名を自動検出）
3. ingestion_logテーブルで取り込み済みファイルをスキップ
4. 未取り込みファイルごとに:
   a. mbox_parser.parse_mbox() でメッセージをパース
   b. thread_resolver.resolve_threads() でスレッド構造を解決
   c. db.insert_batch() でトランザクション内にDB投入（著者の自動解決を含む）
   d. db.record_ingestion() で取り込みログを記録
   e. db.classify_threads() で影響スレッドのステータスを分類
5. サマリー統計をログ出力して終了
```

## 依存ライブラリ

```
psycopg[binary]==3.2.*     # PostgreSQLアダプタ（同期API）
python-dateutil==2.9.*     # メールヘッダーの多様な日付形式のパース
```

stdlib: `mailbox`, `email`, `email.header`, `email.utils`, `re`, `os`, `logging`, `glob`

## ファイル構成

```
ingester/
├── Dockerfile
├── requirements.txt
└── src/
    ├── __init__.py
    ├── main.py              # エントリポイント・パイプライン制御
    ├── mbox_parser.py       # mboxパース・パッチ抽出
    ├── thread_resolver.py   # スレッド構造の解決
    ├── thread_classifier.py # スレッドステータス分類
    └── db.py                # DB投入（upsert）・著者解決
```

## mboxパーサー設計 (`mbox_parser.py`)

### 入出力

- **入力**: mboxファイルパス
- **出力**: メッセージ辞書のリスト

```python
# 1メッセージの構造
{
    "message_id": str,           # Message-IDヘッダー（角括弧除去）
    "parent_id": str | None,     # In-Reply-Toヘッダー
    "references": list[str],     # Referencesヘッダー（Message-IDのリスト）
    "sender": str,               # Fromヘッダー（RFC 2047デコード済み）
    "sent_at": datetime | None,  # Dateヘッダー
    "subject": str,              # Subjectヘッダー（RFC 2047デコード済み）
    "body": str,                 # プレーンテキスト本文（引用行除去済み）
    "body_raw": str,             # プレーンテキスト本文（引用行を含む元テキスト）
    "patches": list[dict],       # 抽出されたパッチデータ
}
```

### ヘッダーデコード

RFC 2047エンコードされたヘッダー（日本語やUTF-8含む）を`email.header.decode_header()`でデコード。文字コードが不明な場合は`utf-8`にフォールバック、デコード失敗時は`errors='replace'`で置換文字を使用。

### Message-ID処理

角括弧を除去して正規化: `<foo@bar.com>` → `foo@bar.com`。Message-IDがないメッセージはスキップ（ログ出力）。

### Referencesヘッダーパース

`<id1> <id2> <id3>`形式のスペース区切りMessage-IDリストをパース。正規表現`<[^>]+>`で抽出し、角括弧を除去してリストとして返す。

### 本文抽出

1. 非multipartメッセージ: `text/plain`ならそのペイロードを返す
2. multipartメッセージ: `walk()`で全パートを走査し、最初の**インライン**`text/plain`パートを返す（`Content-Disposition: attachment`のものはスキップ）

文字エンコーディングは`get_content_charset()`で取得し、不明な場合は`utf-8`にフォールバック。

### 日付パース

メールの日付ヘッダーは形式が多様なため、2段階でパース:
1. `python-dateutil`の`parser.parse()`（柔軟なパーサー）
2. フォールバック: `email.utils.parsedate_to_datetime()`（RFC 2822準拠）
3. 両方失敗: `None`を返す（ログ出力）

## パッチ抽出設計

### 抽出対象

| 種別 | 検出方法 | 優先度 |
|------|----------|--------|
| MIME添付パッチ | Content-Type: `text/x-patch`, `text/x-diff`, `application/x-patch`, `application/x-diff` | 高 |
| MIME添付ファイル | 拡張子: `.patch`, `.diff` | 高 |
| 本文内インラインdiff | `diff --git a/... b/...`パターン検出 | 低（添付がない場合のみ） |

### 抽出データ

```python
{
    "filename": str,        # 添付ファイル名 or "inline"
    "content_type": str,    # MIMEタイプ
    "files_changed": list,  # diff --git行から抽出したファイルパス
    "raw_diff": str,        # パッチの生テキスト
}
```

### 変更ファイルパスの抽出

`diff --git a/(.+?) b/(.+?)`の正規表現でファイルパスを抽出。重複を除去してリストにする。

### インラインdiff検出の条件

本文にパッチが埋め込まれているケースの誤検出を防ぐため、以下の**両方**を満たす場合のみパッチとして扱う:
1. `diff --git`ヘッダーパターンが本文に存在する
2. ファイルパスが1つ以上抽出できる

### 現在の制限事項

- 圧縮アーカイブ（`.tar.gz`）内のパッチは未対応
- パッチバージョン追跡（`[PATCH v2]`の対応付け）は未対応
- コミットメッセージの分離抽出は未対応

## スレッド解決設計 (`thread_resolver.py`)

### アルゴリズム

各メッセージに`thread_id`（スレッドルートのMessage-ID）を付与する。

```
1. Referencesヘッダーがある場合:
   → references[0]をthread_idとする（RFC 2822: 最初の要素がスレッドルート）

2. Referencesがなく、In-Reply-Toがある場合:
   → In-Reply-Toチェーンを辿り、最も古い祖先をthread_idとする
   → チェーンは現在バッチ内のメッセージのみ辿る

3. どちらもない場合:
   → 自身のMessage-IDをthread_idとする（スレッドルート）
```

**References[0]を使う理由**: In-Reply-Toチェーンは中間メッセージが欠損すると途切れるが、Referencesヘッダーは常にスレッドルートへの直接参照を保持している（RFC 2822仕様）。

### Subject正規化

スレッドのsubjectは`Re:`, `Fwd:`, `Fw:`等のプレフィックスを再帰的に除去して正規化する。

```
"Re: Re: [PATCH v3] Improve vacuum freeze" → "[PATCH v3] Improve vacuum freeze"
```

### 制限事項

- バッチ間のスレッド解決: 異なるmboxファイルに跨がるスレッドは、先にDB内の既存メッセージとの突合が必要。現在はReferences[0]に依存し、バッチ間の完全な解決は行わない。
- 取り込み期間より前に開始されたスレッド: thread_idがDB内に存在しないメッセージを参照する場合がある。threadsテーブルのthread_idは取り込み時に自動作成される。

## DB投入設計 (`db.py`)

### 冪等性の確保

- `ON CONFLICT (message_id) DO NOTHING`: 同じメッセージの重複投入を無視
- `ON CONFLICT (thread_id) DO UPDATE`: 同じスレッドの日付範囲・リスト名を更新
- `ingestion_log`テーブルで取り込み済みmboxファイルをスキップ

### トランザクション設計

mboxファイル1つ分を1トランザクションで投入する。

```
BEGIN;
  INSERT INTO threads ... ON CONFLICT DO UPDATE SET started_at=LEAST(...), ended_at=GREATEST(...), list_names=...;
  INSERT INTO messages ... ON CONFLICT DO NOTHING;  -- 全メッセージ
  INSERT INTO patches ...;                           -- 新規メッセージのパッチのみ
COMMIT;
INSERT INTO ingestion_log ...;  -- 取り込み完了を記録
```

パッチは親メッセージが新規投入された場合のみ挿入する（`rowcount > 0`チェック）。

### DB接続

`psycopg.connect()`で同期接続。Docker環境でのDB起動待ちのため、最大10回のリトライ（3秒間隔）を行う。

## mboxダウンロードスクリプト (`scripts/download_mbox.sh`)

### 仕様

```bash
./scripts/download_mbox.sh LIST_NAME START_YYYYMM END_YYYYMM [output_dir]
```

- **URL**: `https://www.postgresql.org/list/{LIST_NAME}/mbox/{LIST_NAME}.YYYYMM`
- 月次でループし、`curl -fSL -u archives:antispam`でダウンロード（Basic認証）
- 既存ファイルはスキップ（再ダウンロードしない）
- 出力先デフォルト: `./data/mbox/{LIST_NAME}/`

### 使用例

```bash
./scripts/download_mbox.sh pgsql-hackers 202401 202601
./scripts/download_mbox.sh pgsql-general 202401 202601
```

ファイルサイズは月あたり数MB〜数十MB。

## エッジケース対処

| ケース | 対処 |
|--------|------|
| Message-IDがないメッセージ | スキップ（ログ出力） |
| 不正な日付ヘッダー | `None`を格納（sent_atはNULLABLE） |
| 不明な文字エンコーディング | `errors='replace'`で置換文字を使用 |
| 大容量mboxファイル | `mailbox.mbox`はlazy読み込み（メモリに全件ロードしない） |
| Message-IDの重複（月跨ぎ） | `ON CONFLICT DO NOTHING`で安全にスキップ |
| Referencesが指す先がDBにない | threadsレコードを作成し、thread_idとして使用 |
| パッチが圧縮アーカイブ | 現在は無視 |

## Dockerfile

```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
CMD ["python", "-m", "src.main"]
```

`docker compose run --rm ingester`で実行。`/data/mbox`をread-onlyでbind mountする。
