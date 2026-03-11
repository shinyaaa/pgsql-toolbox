# PostgreSQL Worktree Dashboard

`~/pgsql` 配下の PostgreSQL 開発用 worktree を管理するローカル Web ダッシュボード。

## 機能

- **ブランチ一覧** - worktree の名前・ステータス・ポート番号を表形式で表示。ソート・フィルタ・検索に対応
- **ステータス管理** - active / review / submitted / committed / archived / abandoned の 6 種類
- **Worktree 作成** - フォームからブランチ名とベースブランチを指定し `pg_init` を直接実行
- **メーリングリスト URL** - 各ブランチに pgsql-hackers 等の ML リンクを登録・表示
- **Commitfest URL** - 各ブランチに Commitfest エントリの URL を登録・表示
- **VSCode 起動リンク** - `vscode://file` プロトコルでソースディレクトリを直接 VSCode で開く
- **ノート** - 自由記述のメモ欄
- **Remove** - ディスク上に存在しないエントリをダッシュボードから削除

## 前提

- Python 3.9+
- Flask (`pip install flask`)
- `~/git/settings/bin/pg_init` が存在すること

## 起動

systemd ユーザーサービスとして常駐する。

```bash
# 状態確認
systemctl --user status pgsql-dashboard

# 起動 / 停止 / 再起動
systemctl --user start pgsql-dashboard
systemctl --user stop pgsql-dashboard
systemctl --user restart pgsql-dashboard

# ログ確認
journalctl --user -u pgsql-dashboard -f
```

手動で起動する場合:

```bash
cd ~/git/pgsql-dashboard
python3 app.py
```

http://127.0.0.1:30001 でアクセス。

## 構成

```
pgsql-dashboard/
  app.py              # Flask バックエンド (API + SQLite)
  templates/
    index.html         # シングルページフロントエンド
  dashboard.db         # SQLite データベース (自動生成)
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
