#!/usr/bin/env python3
"""PostgreSQL リポジトリから特定人物のコントリビューションを収集する。

    python3 collect.py --name "Shinya Kato" --md

対象は pgsql-toolbox のサブモジュール ~/git/pgsql-toolbox/postgres の
origin/master のみ。バックパッチは stable ブランチ側にしか生えないので、
master に絞ることで重複は原理的に出ない。

コミットメッセージのトレーラ（Author: / Reviewed-by: / Reported-by: ...）を
解析して役割を判定し、変更ファイルから領域（area）を推定して一覧を出力する。
テーマへのグルーピングはこのスクリプトではやらない（モデルの仕事）。
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import OrderedDict

# pgsql-toolbox のサブモジュール。SKILL.md からの相対位置で解決する。
DEFAULT_REPO = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "..", "..", "..", "..", "postgres"))
DEFAULT_BASE_URL = ("https://git.postgresql.org/gitweb/"
                    "?p=postgresql.git;a=commit;h=")

# トレーラ名 -> 役割。上にあるものほど優先度が高い。
ROLE_TRAILERS = OrderedDict([
    ("author", "author"),
    ("co-authored-by", "author"),
    ("reviewed-by", "reviewer"),
    ("tested-by", "tester"),
    ("reported-by", "reporter"),
    ("diagnosed-by", "reporter"),
    ("suggested-by", "reporter"),
    ("bug", "reporter"),
])
ROLE_ORDER = ["author", "reviewer", "tester", "reporter", "mention"]

# 変更ファイルパス -> 領域ヒント。上から順に最初にマッチしたものを採用する。
AREA_RULES = [
    (r"^src/bin/psql/tab-complete\.c$", "psql tab-completion"),
    (r"^src/bin/psql/", "psql"),
    (r"^src/bin/scripts/([a-z_0-9]+)\.c$", r"client tool: \1"),
    (r"^src/bin/(?!scripts/)([a-z_0-9]+)/", r"client tool: \1"),
    (r"^src/backend/utils/activity/", "statistics (pgstat)"),
    (r"^src/backend/utils/adt/pgstatfuncs\.c$", "statistics views"),
    (r"^src/backend/catalog/system_views\.sql$", "system views"),
    (r"^src/backend/(commands/vacuum|access/heap/vacuumlazy)", "vacuum"),
    (r"^src/backend/commands/analyze\.c$", "vacuum/analyze"),
    (r"^src/backend/replication/", "replication"),
    (r"^src/backend/utils/misc/guc", "GUC"),
    (r"^contrib/([a-z_0-9]+)/", r"contrib/\1"),
    (r"^doc/src/sgml/", "documentation"),
    (r"^src/test/", "tests"),
]

REC = "\x1e"  # レコード区切り
FLD = "\x1f"  # フィールド区切り


def git(repo, *args):
    out = subprocess.run(
        ["git", "-C", repo, *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if out.returncode != 0:
        sys.exit("git %s failed:\n%s" % (" ".join(args), out.stderr.strip()))
    return out.stdout


def name_in(value, name):
    """トレーラ値（カンマ区切りの人名リスト）に name が含まれるか。"""
    low = value.lower()
    return name.lower() in low


def classify(body, name):
    """コミット本文から役割の集合を返す。"""
    roles = set()
    for line in body.splitlines():
        m = re.match(r"^([A-Za-z-]+):[ \t]*(.*)$", line.strip())
        if not m:
            continue
        key, value = m.group(1).lower(), m.group(2)
        role = ROLE_TRAILERS.get(key)
        if role and name_in(value, name):
            roles.add(role)
    if not roles:
        roles.add("mention")
    return sorted(roles, key=ROLE_ORDER.index)


def areas_of(files):
    found = []
    for path in files:
        for pattern, label in AREA_RULES:
            m = re.search(pattern, path)
            if m:
                label = re.sub(r"\\(\d)", lambda g: m.group(int(g.group(1))), label)
                if label not in found:
                    found.append(label)
                break
    return found


def discussion_of(body):
    m = re.search(r"^Discussion:\s*(\S+)", body, re.M)
    return m.group(1) if m else ""


def collect(repo, name, rev, abbrev):
    # REC は先頭に置く。--name-only の変更ファイル一覧は %B の後ろに続くので、
    # 区切りを末尾に置くとファイル一覧が次のレコードに混ざる。
    fmt = REC + FLD.join(["%H", "%h", "%ad", "%an", "%s", "%B"])
    raw = git(repo, "log", rev, "--grep=" + name, "--date=short",
              "--abbrev=%d" % abbrev, "--name-only", "--format=" + fmt)
    commits = []
    for chunk in raw.split(REC):
        if FLD not in chunk:
            continue
        parts = chunk.split(FLD)
        if len(parts) < 6:
            continue
        sha, short, date, committer, subject, tail = parts[:6]
        sha = sha.lstrip("\n")
        # tail = 本文 + 空行 + 変更ファイル一覧
        lines = tail.splitlines()
        files = [ln for ln in lines
                 if ln and "/" in ln and not re.match(r"^\s", ln)
                 and re.match(r"^[\w.\-]+(/[\w.\-]+)+$", ln)]
        body = tail
        commits.append({
            "sha": sha,
            "short": short,
            "date": date,
            "committer": committer,
            "subject": subject,
            "roles": classify(body, name),
            "backpatch": bool(re.search(r"^Backpatch-through:", body, re.M)),
            "discussion": discussion_of(body),
            "files": files,
            "areas": areas_of(files),
        })
    return commits


def dedupe(commits):
    """同一 subject のコミットを 1 件にまとめる（--rev で複数枝を見たとき用）。

    master だけを対象にするなら不要。バックパッチは stable ブランチ側にしか
    生えないので、master 単独なら重複はそもそも出ない。
    """
    seen = OrderedDict()
    for c in commits:
        key = (c["subject"], c["date"][:4])
        if key in seen:
            seen[key]["dupes"].append(c["short"])
            continue
        c["dupes"] = []
        seen[key] = c
    return list(seen.values())


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--repo", default=DEFAULT_REPO,
                   help="PostgreSQL リポジトリのパス (default: %s)" % DEFAULT_REPO)
    p.add_argument("--name", default="Shinya Kato",
                   help="検索する人名 (default: Shinya Kato)")
    p.add_argument("--rev", default="origin/master",
                   help="対象リビジョン (default: origin/master)。master のみを見る")
    p.add_argument("--abbrev", type=int, default=9,
                   help="短縮ハッシュの桁数 (default: 9)")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL,
                   help="コミット URL の前置き (default: %s)" % DEFAULT_BASE_URL)
    p.add_argument("--md", action="store_true",
                   help="Markdown の箇条書き（リンク付き）で出力する")
    p.add_argument("--json", action="store_true", help="JSON で出力する")
    p.add_argument("--roles", default="",
                   help="役割で絞る（カンマ区切り: author,reviewer,reporter,tester,mention）")
    p.add_argument("--dedupe", action="store_true",
                   help="同一 subject を 1 件に畳む。複数枝を見たときだけ使う")
    args = p.parse_args()

    repo = os.path.expanduser(args.repo)
    # サブモジュールでは .git はディレクトリではなくファイル。
    if not os.path.exists(os.path.join(repo, ".git")):
        sys.exit("not a git repository: %s" % repo)

    commits = collect(repo, args.name, args.rev, args.abbrev)
    if args.dedupe:
        commits = dedupe(commits)
    for c in commits:
        c["url"] = args.base_url + c["sha"]
    if args.roles:
        want = {r.strip() for r in args.roles.split(",") if r.strip()}
        commits = [c for c in commits if want & set(c["roles"])]

    if args.json:
        json.dump(commits, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return

    head = git(repo, "log", "-1", "--format=%h %ad %s", "--date=short", args.rev).strip()

    if args.md:
        print("<!-- repo=%s rev=%s (%s) name=%s commits=%d -->"
              % (repo, args.rev, head, args.name, len(commits)))
        for c in commits:
            print("- [%s](%s) %s — %s / %s"
                  % (c["short"], c["url"], c["subject"],
                     "/".join(c["roles"]), "; ".join(c["areas"]) or "-"))
        return

    print("# repo=%s rev=%s (%s)" % (repo, args.rev, head))
    print("# name=%s  commits=%d" % (args.name, len(commits)))
    print()
    print("\t".join(["short", "date", "roles", "areas", "subject", "url"]))
    for c in commits:
        print("\t".join([
            c["short"], c["date"], "/".join(c["roles"]),
            "; ".join(c["areas"]) or "-", c["subject"], c["url"],
        ]))


if __name__ == "__main__":
    main()
