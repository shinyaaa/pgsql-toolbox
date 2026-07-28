# PostgreSQL Development Toolbox

`~/pgsql` 配下の PostgreSQL 開発用 worktree を管理する CLI ツール群 + Web ダッシュボード + メーリングリスト検索 MCP サーバー。

## 機能

### CLI ツール (`bin/`)

- **`pg_init`** - worktree 作成・PostgreSQL ビルド・環境構築を一括実行
- **`pg_archive`** - worktree のアーカイブ (PG 停止、tmux 終了、git ブランチ削除)
- **`pg_status`** - 全 worktree のステータス一覧表示
- **`pg_mcp`** - メーリングリスト MCP サーバーの管理 (Docker Compose ラッパー)

### Web ダッシュボード

- **ブランチ一覧** - worktree の名前・ステータス・ポート番号を表形式で表示。ソート・フィルタ・検索に対応
- **ステータス管理** - active / archived
- **Worktree 作成** - フォームからブランチ名とベースブランチを指定して `pg_init` を実行
- **PostgreSQL 制御** - ダッシュボードから起動/停止
- **メーリングリスト URL / Commitfest URL** - 各ブランチにリンクを登録・表示
- **VSCode 起動リンク** - `vscode://file` プロトコルでソースディレクトリを直接開く
- **ノート** - 自由記述のメモ欄
- **アーカイブ** - ダッシュボードからワンクリックでアーカイブ

### ドキュメントサーバー (`internals/`)

生成した HTML ドキュメントを一覧・配信するサーバー (port 30002)。
一覧ページは以下の 3 つのタブに分かれており、各タブは対応するディレクトリを配信する。

| タブ | ディレクトリ | URL |
|------|--------------|-----|
| インターナルドキュメント | `internals/docs/<topic>/` | `/<topic>/` |
| ユーザドキュメント | `internals/user_docs/<topic>/` | `/user/<topic>/` |
| パッチ解説ドキュメント | `internals/patch_docs/<topic>/` | `/patch/<topic>/` |

`index.html` を持つサブディレクトリが自動的にタブ内のカードとして並ぶ。
選択したタブは URL のハッシュ (`#user` 等) と localStorage に保存される。

ヘッダの「更新」ボタン (`POST /api/pull`) は `git fetch origin` の後、
現在のブランチを追跡先へ fast-forward する。
ローカルのコミットや変更を書き換えることはなく、fast-forward できない場合
(分岐している / ローカル変更が競合 / 追跡ブランチなし / detached HEAD) は
その理由をボタン横に表示する。デフォルトブランチ以外をチェックアウトしている
場合はその旨も表示する (マージ済みのドキュメントが出てこない原因になるため)。
`user` と `patch` は URL プレフィックスとして予約されているため、
インターナルドキュメントのトピック名には使えない。

## 前提

- Python 3.10+
- Flask (`pip install flask`)
- git, gh (GitHub CLI), make, direnv, tmux
- Docker / Docker Compose (MCP サーバー用)

## CLI Usage

### pg_init - Worktree 作成

```bash
# インタラクティブモード
bin/pg_init

# ブランチ指定
bin/pg_init -b feat-my-feature

# ベースブランチも指定
bin/pg_init -b feat-my-feature -B REL_17_STABLE
```

実行内容:
1. フォークの upstream 同期 (`gh repo sync`)
2. ポート自動割当 (50000-59999)
3. git worktree 作成
4. PostgreSQL ビルド (`configure` + `make world`)
5. `.envrc` 作成 + `direnv allow`
6. `initdb` + PostgreSQL 起動
7. tmux セッション + Claude Code 起動

### pg_archive - Worktree アーカイブ

```bash
# 確認プロンプトあり
bin/pg_archive my-branch

# 確認スキップ
bin/pg_archive -y my-branch
```

### pg_status - ステータス一覧

```bash
# テーブル形式
bin/pg_status

# JSON 形式
bin/pg_status --json
```

出力例:

```
BRANCH                     PORT   PG    STATUS
master                     50000  up    active
feat-my-feature            50001  down  active
```

## MCP サーバー (メーリングリスト検索)

PostgreSQL メーリングリスト (pgsql-hackers, pgsql-bugs 等) の全文検索を提供する MCP サーバー。
Docker Compose で PostgreSQL 18 + FastMCP サーバーを起動する。

```bash
# mbox ダウンロード
bin/pg_mcp download pgsql-hackers 199706 202601

# 起動 + データ投入
bin/pg_mcp up
bin/pg_mcp ingest

# ステータス確認・ログ
bin/pg_mcp status
bin/pg_mcp logs
```

Claude Code に `.mcp.json` で自動登録される。詳細は `mcp/README.md` を参照。

## サービス管理

`pgsql-toolbox.target` で Dashboard・MCP サーバー・Internals の 3 サービスを一括管理する。

```bash
# 全サービス起動 / 停止
systemctl --user start pgsql-toolbox.target
systemctl --user stop pgsql-toolbox.target

# 全体ステータス
systemctl --user status pgsql-toolbox.target

# 個別サービス確認
systemctl --user status pgsql-toolbox.service    # Dashboard
systemctl --user status pgsql-ml-mcp.service     # MCP
systemctl --user status pgsql-internals.service  # Internals

# ログ確認
journalctl --user -u pgsql-toolbox -f            # Dashboard
journalctl --user -u pgsql-ml-mcp -f             # MCP
journalctl --user -u pgsql-internals -f          # Internals
```

各サービスを手動で起動する場合:

```bash
cd ~/git/pgsql-toolbox
python3 app.py            # Dashboard
python3 internals/app.py  # Internals
```

- Dashboard: http://127.0.0.1:30001
- Internals: http://127.0.0.1:30002

### systemd ユニット定義 (参考)

`~/.config/systemd/user/` 配下に以下のファイルを配置する。

`pgsql-toolbox.target`:

```ini
[Unit]
Description=pgsql-toolbox services (Dashboard + MCP)

[Install]
WantedBy=default.target
```

`pgsql-toolbox.service`:

```ini
[Unit]
Description=PostgreSQL Worktree Dashboard
PartOf=pgsql-toolbox.target
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/shinya/git/pgsql-toolbox
ExecStart=/usr/bin/python3 app.py
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=PATH=/home/shinya/.local/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=pgsql-toolbox.target
```

`pgsql-ml-mcp.service`:

```ini
[Unit]
Description=PostgreSQL Mailing List MCP Server
PartOf=pgsql-toolbox.target
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/shinya/git/pgsql-toolbox/mcp
ExecStart=/usr/bin/docker compose up
ExecStop=/usr/bin/docker compose down
Restart=on-failure
RestartSec=10

[Install]
WantedBy=pgsql-toolbox.target
```

`pgsql-internals.service`:

```ini
[Unit]
Description=PostgreSQL Internals Documentation Server
PartOf=pgsql-toolbox.target
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/shinya/git/pgsql-toolbox
ExecStart=/usr/bin/python3 internals/app.py
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=PATH=/home/shinya/.local/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=pgsql-toolbox.target
```

`pgsql-toolbox.service` の `PATH` に `~/.local/bin` を含めるのは、`pg_init` から `claude mcp add` を呼び出すため。

## 構成

```
pgsql-toolbox/
  app.py                # Flask バックエンド (API + SQLite) – Dashboard
  lib/
    config.py           # 共通定数
    db.py               # SQLite ヘルパー
    operations.py       # 共通操作 (archive, port_lock, pg_ctl)
    init.py             # pg_init ロジック
  bin/
    pg_init             # CLI: worktree 作成
    pg_archive          # CLI: アーカイブ
    pg_status           # CLI: ステータス表示
    pg_mcp              # CLI: MCP サーバー管理
  templates/
    index.html          # シングルページフロントエンド (Dashboard)
  internals/            # PostgreSQL ドキュメントサーバー (port 30002)
    app.py              # Flask サーバー – 各カテゴリのドキュメントを配信
    docs/               # インターナルドキュメント (URL: /<topic>/)
    user_docs/          # ユーザドキュメント (URL: /user/<topic>/)
    patch_docs/         # パッチ解説ドキュメント (URL: /patch/<topic>/)
    templates/
      index.html        # ドキュメント一覧ページ (3 カテゴリのタブ)
  mcp/                  # メーリングリスト検索 MCP サーバー
    docker-compose.yml  # Docker Compose 定義
    db/                 # PostgreSQL スキーマ・Dockerfile
    mcp-server/         # FastMCP サーバー
    ingester/           # mbox パーサー・取り込みパイプライン
    scripts/            # mbox ダウンロードスクリプト
    data/mbox/          # ダウンロードした mbox ファイル
  dashboard.db          # SQLite データベース (自動生成)
```

## API

| Method | Endpoint | 説明 |
|--------|----------|------|
| GET | `/api/branches` | 全ブランチ取得 (ディスク状態と同期) |
| PUT | `/api/branches/<name>` | ブランチ情報更新 (status, URL, notes) |
| DELETE | `/api/branches/<name>` | ダッシュボードからエントリ削除 |
| POST | `/api/branches/<name>/pg` | PostgreSQL 起動/停止 (`{"action": "start"\|"stop"}`) |
| GET | `/api/branches/<name>/pg` | PostgreSQL 稼働状態取得 |
| POST | `/api/branches/<name>/archive` | ブランチをアーカイブ |
| POST | `/api/pg_init` | pg_init 実行 (`{"branch": "...", "base_branch": "..."}`) |
| GET | `/api/pg_init` | pg_init タスク状態一覧 |
| GET | `/api/pg_init/<branch>` | 個別タスク状態取得 |
| GET | `/api/logs` | pg_init ログ一覧 (`?branch=` でフィルタ可) |
| GET | `/api/logs/<name>` | ログ内容取得 (`?tail=N` で末尾N行) |
| GET | `/api/statuses` | ステータス一覧取得 |
