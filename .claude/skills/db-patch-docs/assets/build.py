#!/usr/bin/env python3
"""パッチ解説ドキュメントの HTML を content.json から生成する。

    python3 build.py content.json --out ../../internals/patch_docs/<slug>

出力先に index.html と css/style.css を書き出す。テンプレートとスタイルは
このスクリプトと同じディレクトリ (スキルの assets/) にあるものを使う。

content.json の構造は SKILL.md と reference/content-schema.md を参照。
"""

import argparse
import html
import json
import random
import re
import shutil
import sys
import zlib
from pathlib import Path

ASSETS = Path(__file__).resolve().parent
STEPS = [
    ("problem", "問題", "何が足りなかったか"),
    ("design", "設計", "採った道と捨てた道"),
    ("code", "仕組み", "コードを読む"),
    ("gotchas", "注意", "落とし穴"),
    ("tests", "検証", "テストが固定していること"),
]

# 日本語の判定に使う (端末出力と地の文の切り分け)
JP = re.compile(r"[぀-ヿ一-鿿]")

# 解説中の選択肢参照。執筆時の原則は記号 (A〜D) で、これは必ず並べ替えに追随させる。
# 番号での参照も旧素材のために拾うが、参照先の選択肢と本文が似ている場合しか書き換えない
# (「3 が先に停止する」のような普通の数値を選択肢参照と誤認しないため)。
LETTER_RE = re.compile(r"選択肢\s*([A-D])")
_UNIT = r"(?!\s*(?:us|ms|s\b|ビット|バイト|倍|回|個|つ|行|件|本|問|MB|KB))"
NUM_RE = re.compile(
    r"選択肢\s*([0-4])"
    r"|(?:(?<=[、。（(])|(?<=^))\s*([1-4])" + _UNIT +
    r"(?=\s*(?:[がは]|のような|も\s*(?:誤|正|同|違)))"
    r"|(?<=も)([1-4])(?=も)"
    r"|(?<=やすい\s)([1-4])(?=\s*[はが])",
    re.M,
)
# 番号参照を書き換えるのに必要な、参照直後の文と選択肢本文の最低一致度
NUM_REF_MIN_SIMILARITY = 0.04


# --------------------------------------------------------------------------
# 入力の正規化
# --------------------------------------------------------------------------
def slugify(value, fallback):
    """id と URL に安全な形に落とす。"""
    out = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "")).strip("-")
    return out or fallback


def attr(s):
    """属性値としてエスケープする。"""
    return html.escape(s or "", quote=True)


def pick(d, *names, default=None):
    """フィールド名の揺れ (foo / foo_ja) を吸収して取り出す。"""
    for n in names:
        if n in d and d[n] not in (None, ""):
            return d[n]
        if n + "_ja" in d and d[n + "_ja"] not in (None, ""):
            return d[n + "_ja"]
    return default


class ContentError(Exception):
    """content.json の内容が生成できる形になっていない。"""


def normalize(doc):
    if not isinstance(doc, dict) or "patches" not in doc or not doc["patches"]:
        raise ContentError("content.json に patches が無い")
    if not doc.get("title"):
        raise ContentError("content.json に title が無い")
    for k, v in [("facts", doc.get("overview", {}).get("facts", []))]:
        for row in v:
            if not (isinstance(row, (list, tuple)) and len(row) == 2):
                raise ContentError(f"overview.{k} の各行は [見出し, 値] の 2 要素にする: {row!r}")
    patches = []
    for i, p in enumerate(doc["patches"], start=1):
        slug = slugify(pick(p, "slug"), f"patch{i:02d}")
        patches.append({
            "seq": pick(p, "seq") or f"{i:04d}",
            "slug": slug,
            "short": pick(p, "short", "label") or slug,
            "title": pick(p, "title"),
            "summary": pick(p, "summary"),
            "commit": pick(p, "commit", "sha", default=""),
            "subject": pick(p, "subject", default=""),
            "files": p.get("files"),
            "insertions": p.get("insertions"),
            "deletions": p.get("deletions"),
            "problem": {
                "narrative": pick(p.get("problem", {}), "narrative", default=""),
                "repro": pick(p.get("problem", {}), "repro", default=""),
            },
            "design": [{
                "decision": pick(d, "decision"),
                "rationale": pick(d, "rationale"),
                "rejected": pick(d, "rejected", default=""),
            } for d in p.get("design", [])],
            "diagram": pick(p, "diagram_mermaid", "diagram", default=""),
            "code": [{
                "caption": pick(c, "caption"),
                "code": c.get("code", ""),
                "explain": pick(c, "explain"),
            } for c in p.get("code_walkthrough", p.get("code", []))],
            "gotchas": [{
                "title": pick(g, "title"),
                "detail": pick(g, "detail"),
            } for g in p.get("gotchas", [])],
            "tests": [{
                "what": pick(t, "what"),
                "how": pick(t, "how"),
            } for t in p.get("tests", [])],
            "quiz": [_check_quiz(q, slug, n) for n, q in enumerate(p.get("quiz", []), 1)],
        })
    return {
        "title": doc["title"],
        "version_info": doc.get("version_info", ""),
        "series_info": doc.get("series_info", ""),
        "lead": doc.get("lead", ""),
        "overview": doc.get("overview", {}),
        "footer": doc.get("footer", ""),
        "patches": patches,
    }


def _check_quiz(q, slug, n):
    where = f"{slug} の設問 {n}"
    options = pick(q, "options", default=[])
    if not isinstance(options, list) or len(options) != 4:
        raise ContentError(f"{where}: 選択肢は 4 つにする (今は {len(options)} つ)")
    idx = q.get("correct_index")
    if not isinstance(idx, int) or not (0 <= idx < 4):
        raise ContentError(f"{where}: correct_index は 0〜3 の整数にする (今は {idx!r})")
    if not pick(q, "question") or not pick(q, "explain"):
        raise ContentError(f"{where}: question と explain は必須")
    return {"question": pick(q, "question"), "options": options,
            "correct_index": idx, "explain": pick(q, "explain")}


# --------------------------------------------------------------------------
# クイズ: 選択肢のシャッフルと解説内の参照解決
# --------------------------------------------------------------------------
def _bigrams(t):
    t = re.sub(r"\s+", "", t)
    return set(t[i:i + 2] for i in range(len(t) - 1))


def _similarity(clause, option):
    ob = _bigrams(option)
    return len(_bigrams(clause) & ob) / max(1, len(ob))


def _rewrite_refs(text, opts, correct_index, newpos, log, label, problems):
    """解説中の選択肢参照を、シャッフル後の記号に書き換える。

    記号 (A〜D) は執筆時の並びを指すものとして必ず追随させる。番号は旧素材のための
    互換で、参照直後の文が指し先の選択肢を言い換えている場合だけ書き換える。素材は
    0 始まりと 1 始まりが混ざりうるので、解説ごとに照合して流儀を決める。解説は誤答に
    ついて述べるのが通例なので、正解を指す読み方には減点する。
    """
    if not text:
        return text

    def clause_of(endpos):
        return re.split(r"[。\n]", text[endpos:])[0][:120]

    def emit(startpos, endpos, idx):
        letter = chr(65 + newpos[idx])
        log.append(f'    [{label}] 参照 -> {letter}: {opts[idx][:40]}')
        if text[endpos:endpos + 1] in "はがもをのとでに":
            letter += " "
        return "選択肢 " + letter

    # 1) 記号参照
    parts, last = [], 0
    for m in LETTER_RE.finditer(text):
        idx = ord(m.group(1)) - 65
        if idx >= len(opts):
            continue
        parts.append(text[last:m.start()])
        parts.append(emit(m.start(), m.end(), idx))
        last = m.end()
    parts.append(text[last:])
    text = "".join(parts)

    # 2) 番号参照 (旧素材の互換)
    refs = [(m.start(), m.end(), int(next(g for g in m.groups() if g)))
            for m in NUM_RE.finditer(text)]
    if not refs:
        return text

    best, best_score = 1, -1e9
    for offset in (1, 0):          # 同点なら 1 始まりを採る
        score, ok = 0.0, True
        for _, endpos, n in refs:
            idx = n - offset
            if not (0 <= idx < len(opts)):
                ok = False
                break
            score += _similarity(clause_of(endpos), opts[idx])
            if idx == correct_index:
                score -= 1.0
        if ok and score > best_score:
            best, best_score = offset, score

    parts, last = [], 0
    for startpos, endpos, n in refs:
        idx = n - best
        if not (0 <= idx < len(opts)) or \
           _similarity(clause_of(endpos), opts[idx]) < NUM_REF_MIN_SIMILARITY:
            # 選択肢の言い換えに見えない。ただの数値かもしれないので触らない。
            problems.append(f"番号での選択肢参照を解決できなかった ({label}): "
                            f"…{text[max(0, startpos - 12):endpos + 20]}… "
                            "記号 (A〜D) で書き直すこと")
            continue
        parts.append(text[last:startpos])
        parts.append(emit(startpos, endpos, idx))
        last = endpos
    parts.append(text[last:])
    return "".join(parts)


def shuffle_options(q, salt, log, problems, label):
    """正解位置を散らし、解説中の選択肢参照を新しい記号に書き換える。"""
    rng = random.Random(zlib.crc32(q["question"].encode("utf-8")) + salt)
    order = list(range(len(q["options"])))
    rng.shuffle(order)
    newpos = {old: new for new, old in enumerate(order)}
    opts = q["options"]
    out_q = dict(q)
    out_q["explain"] = _rewrite_refs(q["explain"], opts, q["correct_index"],
                                     newpos, log, label, problems)
    out_q["options"] = [opts[old] for old in order]
    out_q["correct_index"] = newpos[q["correct_index"]]
    return out_q


def answer_distribution_ok(answers):
    """記号の偏り (各 15〜35%) と同一記号の 3 連続を判定する。"""
    n = len(answers)
    if n < 4:
        return True
    lo, hi = n * 0.15, n * 0.35
    for letter in range(4):
        count = answers.count(letter)
        if count < lo or count > hi:
            return False
    run = 1
    for i in range(1, n):
        run = run + 1 if answers[i] == answers[i - 1] else 1
        if run >= 3:
            return False
    return True


def shuffle_document(patches, log, problems):
    """文書全体で正解位置の分布が規約を満たすまでシードを振り直す。"""
    for salt in range(64):
        trial_log, trial_problems = [], []
        shuffled = []
        for p in patches:
            for i, q in enumerate(p["quiz"]):
                shuffled.append((p, dict(shuffle_options(
                    q, salt, trial_log, trial_problems, f"{p['slug']} Q{i + 1}"))))
        answers = [q["correct_index"] for _, q in shuffled]
        if answer_distribution_ok(answers):
            log.extend(trial_log)
            problems.extend(trial_problems)
            return shuffled, salt
    # 規約を満たす並びが見つからない (設問数が少ないなど)
    log.extend(trial_log)
    problems.extend(trial_problems)
    problems.append("正解位置の分布が規約 (各記号 15〜35%、同一記号の 3 連続なし) を"
                    "満たす並びを見つけられなかった。設問数か設問内容を見直すこと")
    return shuffled, None


# --------------------------------------------------------------------------
# HTML 部品
# --------------------------------------------------------------------------
def e(s):
    return html.escape(s or "", quote=False)


PROMPT_RE = re.compile(r"^\s*(\$|#(?!#)|[\w.-]*=[#>]|>>>)\s")
# 「エラー: …」のようにプログラムが出す日本語行を地の文と誤認しないための目印
OUTPUT_HEAD_RE = re.compile(
    r"^\s*(?:[\w.\-/]+:|エラー|警告|注意|詳細|ヒント|ERROR|WARNING|NOTICE|DETAIL|HINT|LOG)")


def split_transcript(text):
    """(前置きの地の文, 端末出力, 後置きの地の文) に分ける。

    端末出力は最初のプロンプト行から始まり、地の文が再開する行で終わる。プロンプトが
    無い貼り付け (エラーメッセージだけ、など) は、複数行あるいは出力らしい行頭を持つ
    ならまとめて実行例として扱う。整形を失うより、そのまま見せるほうが安全である。
    """
    lines = (text or "").rstrip().split("\n")
    nonempty = [l for l in lines if l.strip()]
    starts = [i for i, l in enumerate(lines) if PROMPT_RE.match(l)]
    if not starts:
        looks_like_output = len(nonempty) > 1 or any(OUTPUT_HEAD_RE.match(l) for l in nonempty)
        if looks_like_output and nonempty:
            return "", "\n".join(lines).strip("\n"), ""
        return " ".join(l.strip() for l in nonempty), "", ""

    first = starts[0]
    last, prev_blank = first, False
    for i in range(first, len(lines)):
        stripped = lines[i].lstrip()
        if not stripped:
            prev_blank = True
            continue
        if not PROMPT_RE.match(lines[i]) and not OUTPUT_HEAD_RE.match(lines[i]):
            # 空行を挟んだ日本語、あるいは括弧書きの注記なら、そこから先は地の文
            if (prev_blank or stripped[0] in "（(") and JP.search(stripped):
                break
            if len(JP.findall(stripped)) >= 5 and not stripped.startswith(("|", "+", "-")):
                break
        prev_blank = False
        last = i

    def join(ls):
        return " ".join(l.strip() for l in ls if l.strip()).strip("()（） ")

    return (join(lines[:first]),
            "\n".join(lines[first:last + 1]).strip("\n"),
            join(lines[last + 1:]))


def term_block(text):
    lead, transcript, note = split_transcript(text)
    out = ""
    if lead:
        out += f"<p>{e(lead)}</p>\n"
    if transcript:
        out += ('<figure class="term">\n<figcaption>実行例</figcaption>\n'
                f"<pre><code>{html.escape(transcript)}</code></pre>\n</figure>\n")
    if note:
        out += f'<p class="code-note">{e(note)}</p>\n'
    return out


def code_block(caption, code, explain):
    return ('<figure class="code">\n'
            f"<figcaption>{e(caption)}</figcaption>\n"
            f"<pre><code>{html.escape(code)}</code></pre>\n</figure>\n"
            f'<p class="code-note">{e(explain)}</p>\n')


def diagram_block(src, caption=None):
    if not src or not src.strip():
        return ""
    body = src.replace("&", "&amp;").replace("&amp;lt;", "&lt;").replace("<", "&lt;")
    cap = f"<figcaption>{e(caption)}</figcaption>\n" if caption else ""
    return f'<figure>\n<pre class="mermaid">{body}</pre>\n{cap}</figure>\n'


def step_heading(mark, text, anchor):
    return f'<h3 class="step" id="{anchor}"><span class="step-mark">{mark}</span>{e(text)}</h3>\n'


# --------------------------------------------------------------------------
# 生成
# --------------------------------------------------------------------------
def render(doc, log, problems):
    sidebar, sections = [], []
    shuffled, salt = shuffle_document(doc["patches"], log, problems)
    if salt:
        log.append(f"  正解位置の分布を満たすため seed を {salt} ずらした")
    quiz_items = [dict(q, patch=p["short"], anchor=f"p-{p['slug']}", seq=p["seq"])
                  for p, q in shuffled]

    for p in doc["patches"]:
        pid = f"p-{p['slug']}"
        anchors = [(f"{pid}-{key}", label) for key, label, _ in STEPS]
        sidebar.append(
            f'        <li>\n'
            f'          <a class="chap-title" href="#{pid}">{p["seq"]} {e(p["short"])}</a>\n'
            f'          <ol class="sect">\n'
            + "".join(f'            <li><a href="#{a}">{lab}</a></li>\n' for a, lab in anchors)
            + "          </ol>\n        </li>\n")

        facts = []
        if p["commit"]:
            facts.append(f"<div><dt>コミット</dt><dd>{e(p['commit'])}</dd></div>")
        if p["subject"]:
            facts.append(f"<div><dt>件名</dt><dd>{e(p['subject'])}</dd></div>")
        if p["files"] is not None:
            facts.append(
                f"<div><dt>差分</dt><dd>{p['files']} files "
                f'<span class="plus">+{p["insertions"]}</span> '
                f'<span class="minus">&minus;{p["deletions"]}</span></dd></div>')

        design = "".join(
            '<div class="choice">\n'
            f'<p class="take"><span class="tag tag-take">採用</span>{e(d["decision"])}</p>\n'
            f'<p>{e(d["rationale"])}</p>\n'
            + (f'<p class="drop"><span class="tag tag-drop">見送り</span>{e(d["rejected"])}</p>\n'
               if d["rejected"] and d["rejected"].strip() not in ("なし", "-") else "")
            + "</div>\n"
            for d in p["design"])

        codes = "".join(code_block(c["caption"], c["code"], c["explain"]) for c in p["code"])
        gotchas = "".join(f'<li><h4>{e(g["title"])}</h4><p>{e(g["detail"])}</p></li>\n'
                          for g in p["gotchas"])
        tests = "".join(f'<li><h4>{e(t["what"])}</h4><p>{e(t["how"])}</p></li>\n'
                        for t in p["tests"])

        sections.append(f"""      <section class="patch" id="{pid}">
        <p class="eyebrow"><span class="seq">{p['seq']}</span><span class="sep">/</span><span>{e(p['short'])}</span></p>
        <h2>{e(p['title'])}</h2>
        <p class="lead">{e(p['summary'])}</p>
        <dl class="facts">{''.join(facts)}</dl>

{step_heading('問題', STEPS[0][2], f'{pid}-problem')}        <p>{e(p['problem']['narrative'])}</p>
{term_block(p['problem']['repro'])}
{step_heading('設計', STEPS[1][2], f'{pid}-design')}        <div class="choices">{design}</div>

{step_heading('仕組み', STEPS[2][2], f'{pid}-code')}{diagram_block(p['diagram'])}{codes}
{step_heading('注意', STEPS[3][2], f'{pid}-gotchas')}        <ul class="notes warn-list">{gotchas}</ul>

{step_heading('検証', STEPS[4][2], f'{pid}-tests')}        <ul class="notes ok-list">{tests}</ul>
      </section>
""")

    sidebar.append('        <li>\n          <a class="chap-title" href="#quiz">理解度チェック</a>\n        </li>\n')

    quiz_html = []
    for i, q in enumerate(quiz_items):
        opts = "".join(
            f'<button type="button" class="opt" data-q="{i}" data-o="{j}">'
            f'<span class="opt-key">{chr(65 + j)}</span>'
            f'<span class="opt-text">{e(o)}</span></button>\n'
            for j, o in enumerate(q["options"]))
        quiz_html.append(f"""        <article class="q" data-answer="{q['correct_index']}" data-anchor="{q['anchor']}" data-patch="{attr(q['patch'])}">
          <p class="q-meta"><span class="q-no">Q{i + 1:02d}</span><a href="#{q['anchor']}">{q['seq']} {e(q['patch'])}</a></p>
          <h4>{e(q['question'])}</h4>
          <div class="opts">{opts}</div>
          <div class="q-feedback" hidden aria-live="polite">
            <p class="verdict"></p>
            <p class="why">{e(q['explain'])}</p>
          </div>
        </article>
""")

    ov = doc["overview"]
    overview = ""
    if ov:
        rows = "".join(f"<tr><th>{e(k)}</th><td>{e(v)}</td></tr>" for k, v in ov.get("facts", []))
        overview = "      <h2>このドキュメントの読み方</h2>\n"
        if ov.get("reading"):
            overview += f"      <p>{e(ov['reading'])}</p>\n"
        if rows:
            overview += f"      <table>{rows}</table>\n"

    template = (ASSETS / "index-template.html").read_text(encoding="utf-8")
    return (template
            .replace("{{TITLE}}", e(doc["title"]))
            .replace("{{VERSION_INFO}}", e(doc["version_info"]))
            .replace("{{SERIES_INFO}}", e(doc["series_info"]))
            .replace("{{LEAD}}", e(doc["lead"]))
            .replace("{{SIDEBAR}}", "".join(sidebar))
            .replace("{{OVERVIEW}}", overview)
            .replace("{{PATCHES}}", "".join(sections))
            .replace("{{QUIZ}}", "".join(quiz_html))
            .replace("{{QUIZ_COUNT}}", str(len(quiz_items)))
            .replace("{{FOOTER}}", e(doc["footer"])))


# --------------------------------------------------------------------------
# 自己検査
# --------------------------------------------------------------------------
def check(page, doc):
    """生成物の整合を検査し、(問題, 警告) を返す。

    問題は生成を止める。警告は編集上の指針で、止めずに知らせる。
    """
    problems, warnings = [], []
    answers = re.findall(r'data-answer="(\d+)"', page)
    if len(answers) >= 8:
        spread = len(set(answers))
        if spread < 3:
            problems.append(f"正解位置の分布が偏っている (異なる位置が {spread} 種類しかない)")
    for art in re.findall(r'<article class="q".*?</article>', page, re.S):
        ans = int(re.search(r'data-answer="(\d+)"', art).group(1))
        exp = re.search(r'<p class="why">(.*?)</p>', art, re.S).group(1)
        for r in set(re.findall(r"選択肢 ([A-D])", exp)):
            if ord(r) - 65 == ans:
                problems.append("解説が正解の選択肢を誤答として参照している: "
                                + re.search(r"<h4>(.{0,40})", art).group(1))
        if re.search(r"選択肢\s*[0-9]", exp):
            problems.append("解説に番号のままの選択肢参照が残っている: "
                            + re.search(r"<h4>(.{0,40})", art).group(1))
        if len(re.findall(r'class="opt"', art)) != 4:
            problems.append("選択肢が 4 つでない: " + re.search(r"<h4>(.{0,40})", art).group(1))
        lens = [len(o) for o in re.findall(r'<span class="opt-text">(.*?)</span>', art, re.S)]
        if lens and max(lens) > 2.5 * max(1, min(lens)):
            warnings.append("選択肢の長さが揃っていない (最長が最短の 2.5 倍超): "
                            + re.search(r"<h4>(.{0,40})", art).group(1))
        anchor = re.search(r'data-anchor="([^"]+)"', art).group(1)
        if f'id="{anchor}"' not in page:
            problems.append(f"クイズのリンク先 #{anchor} が本文に無い")
    for tag in ("section", "article", "figure", "div", "ul", "li", "dl", "p", "h4"):
        opened = len(re.findall(rf"<{tag}[ >]", page))
        closed = page.count(f"</{tag}>")
        if opened != closed:
            problems.append(f"<{tag}> の開閉が合わない (open={opened} close={closed})")
    if "{{" in page:
        problems.append("テンプレートの置換漏れがある: "
                        + ", ".join(sorted(set(re.findall(r"\{\{[A-Z_]+\}\}", page)))))
    for p in doc["patches"]:
        for c in p["code"]:
            if len(c["code"].splitlines()) > 30:
                problems.append(f"コード断片が長すぎる ({p['slug']}: {c['caption']})")
    return problems, warnings


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("content", help="content.json のパス")
    ap.add_argument("--out", required=True, help="出力先ディレクトリ (internals/patch_docs/<slug>)")
    ap.add_argument("--quiet", action="store_true", help="参照解決のログを出さない")
    ap.add_argument("--force", action="store_true",
                    help="検査で問題が出ても書き出す (通常は使わない)")
    args = ap.parse_args()

    try:
        doc = normalize(json.loads(Path(args.content).read_text(encoding="utf-8")))
    except ContentError as err:
        print(f"content.json の内容に問題がある: {err}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as err:
        print(f"content.json を読めない: {err}", file=sys.stderr)
        return 2
    log, problems = [], []
    page = render(doc, log, problems)
    found, warnings = check(page, doc)
    problems += found

    if problems:
        print("検査で見つかった問題 (出力していない):", file=sys.stderr)
        for p in problems:
            print("  - " + p, file=sys.stderr)
        if not args.force:
            print("直してから再実行する。どうしても出力したいときは --force。", file=sys.stderr)
            return 1

    out = Path(args.out)
    (out / "css").mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page, encoding="utf-8")
    shutil.copy(ASSETS / "style.css", out / "css" / "style.css")
    # M19: 素材を成果物の隣に残し、編集して再生成できるようにする
    src = Path(args.content).resolve()
    if src != (out / "content.json").resolve():
        shutil.copy(src, out / "content.json")

    if log and not args.quiet:
        print("選択肢参照の解決:")
        print("\n".join(log))
    print(f"生成: {out/'index.html'} ({len(page):,} バイト, "
          f"{len(doc['patches'])} パッチ, {page.count('<article class=')} 問)")
    for w in warnings:
        print("  警告: " + w)
    print("検査: 問題なし" if not problems else "検査: 問題ありのまま --force で出力した")
    return 0


if __name__ == "__main__":
    sys.exit(main())
