# PostgreSQL Development Toolbox

`~/pgsql` 配下の PostgreSQL 開発用 worktree を管理する CLI ツール群 + Web ダッシュボード。

## 機能

### CLI ツール (`bin/`)

- **`pg_init`** - worktree 作成・PostgreSQL ビルド・環境構築を一括実行
- **`pg_archive`** - worktree のアーカイブ (PG 停止、tmux 終了、git ブランチ削除)
- **`pg_status`** - 全 worktree のステータス一覧表示

### Web ダッシュボード

- **ブランチ一覧** - worktree の名前・ステータス・ポート番号を表形式で表示。ソート・フィルタ・検索に対応
- **ステータス管理** - active / archived
- **Worktree 作成** - フォームからブランチ名とベースブランチを指定して `pg_init` を実行
- **PostgreSQL 制御** - ダッシュボードから起動/停止
- **メーリングリスト URL / Commitfest URL** - 各ブランチにリンクを登録・表示
- **VSCode 起動リンク** - `vscode://file` プロトコルでソースディレクトリを直接開く
- **ノート** - 自由記述のメモ欄
- **アーカイブ** - ダッシュボードからワンクリックでアーカイブ

## 前提

- Python 3.10+
- Flask (`pip install flask`)
- git, gh (GitHub CLI), make, direnv, tmux

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

## ダッシュボード起動

systemd ユーザーサービスとして常駐する。

```bash
# 状態確認
systemctl --user status pgsql-toolbox

# 起動 / 停止 / 再起動
systemctl --user start pgsql-toolbox
systemctl --user stop pgsql-toolbox
systemctl --user restart pgsql-toolbox

# ログ確認
journalctl --user -u pgsql-toolbox -f
```

手動で起動する場合:

```bash
cd ~/git/pgsql-toolbox
python3 app.py
```

http://127.0.0.1:30001 でアクセス。

## 構成

```
pgsql-toolbox/
  app.py                # Flask バックエンド (API + SQLite)
  lib/
    config.py           # 共通定数
    db.py               # SQLite ヘルパー
    operations.py       # 共通操作 (archive, port_lock, pg_ctl)
    init.py             # pg_init ロジック
  bin/
    pg_init             # CLI: worktree 作成
    pg_archive          # CLI: アーカイブ
    pg_status           # CLI: ステータス表示
  templates/
    index.html          # シングルページフロントエンド
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
