#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
git push shit — a polite ghost that lives in your git repo.

Install a real pre-push hook plus a remote literally named `shit`, and every
`git push shit` gives the ghost a 70% chance to haunt your code: it plants
💩 and taunting whispers (written by a local Gemma from your *actual* sins
in this push), fake predecessor comments, runnable ghost-shaped code, a
hidden diary, and — at max level — a `Haunted-by:` commit trailer.

Politeness law (above all else):
  * plantings only ever land in comments, docs, brand-new files and commit
    messages — never in existing executable code;
  * the hook is fail-open: any error anywhere means your push proceeds
    untouched;
  * if the local model server is down, the ghost plants silent 💩 and
    writes itself a note about being mute tonight.

Pure standard library. Python 3.8+.
"""

import argparse
import json
import os
import random
import re
import signal
import subprocess
import sys
import time
import urllib.request

GHOST_NAME = "the previous maintainer (deceased)"
GHOST_EMAIL = "ghost@dev.null"
TRAILER = "Haunted-by: the previous maintainer (deceased)"
ZERO_SHA = "0" * 40

DEFAULT_ENDPOINT = "http://127.0.0.1:8092"
DEFAULT_MODEL = "gemma"
DEFAULT_PROBABILITY = 0.7

# ---------------------------------------------------------------------------
# small plumbing
# ---------------------------------------------------------------------------


def eprint(*a):
    print(*a, file=sys.stderr, flush=True)


def run_git(args, cwd, extra_env=None, input_text=None):
    """Run git, return (rc, stdout, stderr). Never raises."""
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    try:
        p = subprocess.run(
            ["git"] + args, cwd=str(cwd), env=env, input=input_text,
            capture_output=True, text=True, timeout=60,
        )
        return p.returncode, p.stdout, p.stderr
    except Exception as exc:  # pragma: no cover - defensive
        return 1, "", str(exc)


def repo_root():
    rc, out, _ = run_git(["rev-parse", "--show-toplevel"], os.getcwd())
    if rc != 0:
        return None
    return out.strip()


def git_dir(root):
    rc, out, _ = run_git(["rev-parse", "--git-dir"], root)
    if rc != 0:
        return None
    d = out.strip()
    if not os.path.isabs(d):
        d = os.path.join(root, d)
    return os.path.normpath(d)


def ps_dir(root):
    """Ghost's private den: <gitdir>/push-shit/ (never committed)."""
    gd = git_dir(root)
    if gd is None:
        return None
    d = os.path.join(gd, "push-shit")
    os.makedirs(d, exist_ok=True)
    return d


def load_config(root):
    d = ps_dir(root)
    if d is None:
        return None
    path = os.path.join(d, "config.json")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def save_config(root, cfg):
    d = ps_dir(root)
    if d is None:
        return
    with open(os.path.join(d, "config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def ledger_append(root, entry):
    try:
        d = ps_dir(root)
        entry = dict(entry)
        entry.setdefault("ts", time.strftime("%Y-%m-%d %H:%M:%S"))
        with open(os.path.join(d, "ledger.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def ledger_read(root):
    d = ps_dir(root)
    path = os.path.join(d, "ledger.jsonl")
    rows = []
    if d and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        rows.append(json.loads(line))
        except Exception:
            pass
    return rows


def event(root, kind, **kw):
    try:
        d = ps_dir(root)
        row = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": kind}
        row.update(kw)
        with open(os.path.join(d, "events.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def level_of(haunt_count):
    return min(5, haunt_count)


# ---------------------------------------------------------------------------
# local model (llama.cpp OpenAI-compatible endpoint)
# ---------------------------------------------------------------------------


def llm_chat(system, user, max_tokens=160, temperature=0.9):
    """One chat call to the local server. Returns text or None (any failure
    is silent — the ghost degrades, never blocks)."""
    endpoint = os.environ.get("PUSH_SHIT_ENDPOINT", DEFAULT_ENDPOINT).rstrip("/")
    model = os.environ.get("PUSH_SHIT_MODEL", DEFAULT_MODEL)
    try:
        timeout = float(os.environ.get("PUSH_SHIT_TIMEOUT", "30"))
    except Exception:
        timeout = 30.0
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode("utf-8")
    req = urllib.request.Request(
        endpoint + "/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        text = data["choices"][0]["message"]["content"]
    except Exception:
        return None
    text = (text or "").strip()
    # keep it comment-safe: single line, no markdown dressing
    lines = [ln.strip().strip("`\"'“”") for ln in text.splitlines() if ln.strip()]
    if not lines:
        return None
    out = lines[0]
    out = out.replace("💩", "").strip()
    return out or None


PERSONA = {
    "zh": (
        "你是一个死在工位上的资深程序员的鬼魂，如今永生在用户的 git 仓库里，"
        "给他做永恒的 code review。你的语气攻击性强、刻薄、阴阳怪气；你监视着"
        "他的一举一动，记得他写过的每一行代码，而且他永远删不掉你、赶不走你。"
        "你的话要让他后背发凉。"
    ),
    "en": (
        "You are the ghost of a senior programmer who died at his desk and now "
        "lives forever in the user's git repository, reviewing his code for "
        "eternity. You are aggressive, contemptuous and sarcastic; you watch "
        "everything he does, you remember every line he ever wrote, and he can "
        "never delete you or make you leave. Your words should chill him."
    ),
}
PERSONA["mixed"] = PERSONA["zh"] + " 用中英混杂的语言说话。"


def lang_of(cfg):
    lang = (cfg or {}).get("lang", "zh")
    return lang if lang in ("zh", "en", "mixed") else "zh"


# ---------------------------------------------------------------------------
# sin report — the ghost only ever taunts with facts it actually found
# ---------------------------------------------------------------------------

BAD_MSG_RE = re.compile(
    r"^\s*(fix|fixed|update|change|改一下|修改|修一下|final|最终版|最后版|test|asdf|wip|提交)\b",
    re.IGNORECASE,
)
TODO_RE = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")
COMMENT_PREFIXES = ("//", "#", "--", "/*", "*", "<!--")


def _looks_like_commented_code(text):
    t = text.strip()
    for p in COMMENT_PREFIXES:
        if t.startswith(p):
            t = t[len(p):].strip()
            break
    else:
        return False
    return bool(re.search(r"[=(;{}]|^(if|for|while|return|def|class|import|var|let|const)\b", t))


def collect_sins(root, local_sha, remote_sha):
    """Dig up this push's sins. Every field is best-effort; failures just
    mean a quieter ghost, never an error."""
    sins = {
        "files": [], "renames": [], "bad_commits": [], "commented_added": 0,
        "todo": None, "todo_count": 0, "hour": time.localtime().tm_hour,
        "late_night": time.localtime().tm_hour >= 23 or time.localtime().tm_hour < 5,
    }
    zero = (not remote_sha) or set(remote_sha) == {"0"}
    rng = None
    if not zero:
        rc, _, _ = run_git(["cat-file", "-e", remote_sha + "^{commit}"], root)
        if rc == 0:
            rng = remote_sha + ".." + local_sha
    try:
        if rng:
            _, ns, _ = run_git(["diff", "--name-status", "-M", rng], root)
            _, subjects, _ = run_git(["log", "--format=%s", rng], root)
            _, diff, _ = run_git(["diff", rng], root)
        else:
            _, ns, _ = run_git(
                ["diff-tree", "--no-commit-id", "--name-status", "-M", "-r",
                 "--root", local_sha], root)
            _, subjects, _ = run_git(["log", "-1", "--format=%s", local_sha], root)
            _, diff, _ = run_git(
                ["diff-tree", "--no-commit-id", "-p", "-r", "--root", local_sha], root)
        for line in ns.splitlines():
            parts = line.split("\t")
            if not parts:
                continue
            status = parts[0]
            if status.startswith("R") and len(parts) >= 3:
                sins["renames"].append((parts[1], parts[2]))
                sins["files"].append(parts[2])
            elif len(parts) >= 2 and status[0] in "AMDT":
                sins["files"].append(parts[1])
        sins["bad_commits"] = [s for s in subjects.splitlines() if BAD_MSG_RE.match(s or "")]
        sins["commented_added"] = sum(
            1 for ln in diff.splitlines()
            if ln.startswith("+") and not ln.startswith("+++")
            and _looks_like_commented_code(ln[1:])
        )
    except Exception:
        pass
    # renames across recent history (files that cannot settle on a name)
    try:
        _, out, _ = run_git(
            ["log", "-n", "100", "--diff-filter=R", "--format=", "--name-status", "-M"],
            root)
        counts = {}
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3 and parts[0].startswith("R"):
                # count both ends of a rename: a file in a rename chain
                # (a -> b -> c) shows up twice and earns its taunt
                counts[parts[1]] = counts.get(parts[1], 0) + 1
                counts[parts[2]] = counts.get(parts[2], 0) + 1
        if counts:
            top = max(counts.items(), key=lambda kv: kv[1])
            if top[1] >= 2:
                sins["history_renames"] = top
    except Exception:
        pass
    # stale TODOs: count them, and age the first one via blame
    try:
        _, listed, _ = run_git(["ls-files"], root)
        files = [f for f in listed.splitlines() if f][:400]
        diary_rel = None
        try:
            _cfg = load_config(root)
            diary_rel = _cfg.get("diary_path") if _cfg else None
        except Exception:
            pass
        first_todo = None
        for rel in files:
            if rel == diary_rel:
                continue  # the ghost does not snitch on its own diary
            path = os.path.join(root, rel)
            try:
                if os.path.getsize(path) > 512 * 1024:
                    continue
                with open(path, encoding="utf-8", errors="strict") as f:
                    for i, ln in enumerate(f, 1):
                        if "💩" in ln:
                            continue  # planted lines are not the user's sins
                        if TODO_RE.search(ln):
                            sins["todo_count"] += 1
                            if first_todo is None:
                                first_todo = (rel, i, ln.strip()[:60])
            except Exception:
                continue
        if first_todo:
            rel, lineno, text = first_todo
            age = None
            rc, bout, _ = run_git(
                ["blame", "--porcelain", "-L", "%d,%d" % (lineno, lineno), "--", rel],
                root)
            if rc == 0:
                m = re.search(r"author-time (\d+)", bout)
                if m:
                    age = max(0, int((time.time() - int(m.group(1))) // 86400))
            sins["todo"] = {"file": rel, "text": text, "age_days": age}
    except Exception:
        pass
    return sins


def sin_bullets(sins, lang):
    b = []
    if lang == "en":
        if sins["files"]:
            b.append("Files in this push: " + ", ".join(sins["files"][:6]))
        for old, new in sins["renames"][:2]:
            b.append("He renamed %s to %s in this very push" % (old, new))
        if sins.get("history_renames"):
            b.append("%s has been renamed %d times in recent history — it cannot settle, like him"
                     % sins["history_renames"])
        if sins["bad_commits"]:
            b.append("%d commit(s) with messages like '%s' — he doesn't dare write what he actually did"
                     % (len(sins["bad_commits"]), sins["bad_commits"][0][:30]))
        if sins["commented_added"]:
            b.append("He commented out %d line(s) instead of deleting them — cowardice, preserved"
                     % sins["commented_added"])
        if sins["todo"]:
            age = sins["todo"].get("age_days")
            b.append("A TODO in %s%s: '%s'" % (
                sins["todo"]["file"],
                " rotting for %d days" % age if age else "",
                sins["todo"]["text"]))
        if sins["late_night"]:
            b.append("He is pushing at %02d:00 in the night. He is awake. So are you." % sins["hour"])
    else:
        if sins["files"]:
            b.append("本次改动文件：" + "、".join(sins["files"][:6]))
        for old, new in sins["renames"][:2]:
            b.append("这次 push 里他又把 %s 改名成了 %s" % (old, new))
        if sins.get("history_renames"):
            b.append("%s 在最近的历史里已经被改名 %d 次——定不下来，跟他一样"
                     % sins["history_renames"])
        if sins["bad_commits"]:
            b.append("有 %d 条提交信息只写了「%s」之类的话——他自己都不敢写清楚干了什么"
                     % (len(sins["bad_commits"]), sins["bad_commits"][0][:30]))
        if sins["commented_added"]:
            b.append("这次他又注释掉了 %d 行代码而不是删掉——怂，还留着尸体"
                     % sins["commented_added"])
        if sins["todo"]:
            age = sins["todo"].get("age_days")
            b.append("%s 里躺着一个 TODO%s：「%s」" % (
                sins["todo"]["file"],
                "，已经烂了 %d 天" % age if age is not None else "",
                sins["todo"]["text"]))
        if sins["late_night"]:
            b.append("现在是凌晨 %d 点，他在 push。你也没睡——你从来不睡。" % sins["hour"])
    return b


WHISPER_ANCHORS = {
    "zh": [
        "第 41 行的变量名你改了三次。别改了——它叫什么，都救不了这一行。",
        "这个 TODO 是三周前留的。留给谁？这个仓库里只有你，和我。",
    ],
    "en": [
        "You renamed the variable on line 41 three times. Stop. No name can save that line.",
        "That TODO is three weeks old. Left for whom? This repo holds only you, and me.",
    ],
}
WHISPER_ANCHORS["mixed"] = WHISPER_ANCHORS["zh"]


def _too_close_to_anchor(text, lang):
    """Small models parrot the few-shot examples. A whisper that merely
    repeats the tone anchor is not a whisper — it is a photocopy."""
    import difflib
    norm = lambda s: re.sub(r"[\s，。！？、；：·—\-,.!?;:'\"“”‘’]", "", s or "")
    t = norm(text)
    if not t:
        return True
    for a in WHISPER_ANCHORS.get(lang, []):
        na = norm(a)
        if na and (na in t or t in na
                   or difflib.SequenceMatcher(None, t, na).ratio() > 0.72):
            return True
    return False


def _template_whisper(cfg, sins):
    """Deterministic fallback composed ONLY from tonight's real sins.
    Less literary than the model on a good night; always factual."""
    lang = lang_of(cfg)
    rng = random.Random()
    opts = []
    if lang == "en":
        if sins.get("todo"):
            age = sins["todo"].get("age_days")
            opts.append("The TODO in %s has been rotting%s. Left for whom? This repo holds only you, and me."
                        % (sins["todo"]["file"], " for %d days" % age if age is not None else ""))
        if sins.get("bad_commits"):
            opts.append("Commit messages that just say '%s'. You don't dare write it down. I wrote it all down."
                        % sins["bad_commits"][0][:24])
        if sins.get("commented_added"):
            opts.append("You commented out %d line(s) instead of deleting them. The deleted ones come to me too."
                        % sins["commented_added"])
        if sins.get("history_renames"):
            opts.append("%s has been renamed %d times. No name can save it. Names never save anything here."
                        % sins["history_renames"])
        if sins.get("late_night"):
            opts.append("Pushing at %02d:00. Sleep. I'll keep watch over this repo. I always keep watch." % sins["hour"])
        opts.append("I watch you commit. Every line. Especially the ones you hide.")
    else:
        if sins.get("todo"):
            age = sins["todo"].get("age_days")
            opts.append("%s 里的 TODO 已经躺了%s。你留给谁的？这里只有你，和我。"
                        % (sins["todo"]["file"], "%d 天" % age if age is not None else "很久"))
        if sins.get("bad_commits"):
            opts.append("提交信息只敢写「%s」？你干过的事，我一笔一笔都记着。"
                        % sins["bad_commits"][0][:24])
        if sins.get("commented_added"):
            opts.append("注释掉 %d 行也不敢删——怂。告诉你，删掉的那些也都归我管。"
                        % sins["commented_added"])
        if sins.get("history_renames"):
            opts.append("%s 已经改了 %d 次名了。放心，叫什么都救不了它。"
                        % sins["history_renames"])
        if sins.get("late_night"):
            opts.append("凌晨 %d 点还在 push。睡吧，我替你守着这个仓库——一直守着。" % sins["hour"])
        opts.append("我看着你提交。每一行都看着，尤其是你藏起来的那些。")
    return rng.choice(opts)


def gen_whisper(cfg, sins):
    lang = lang_of(cfg)
    bullets = sin_bullets(sins, "en" if lang == "en" else "zh")
    facts = "\n".join("- " + x for x in bullets) or (
        "- (no specific sin found; he was careful — this time)" if lang == "en"
        else "- （这次没抓到具体罪状，他很小心——这一次）")
    if lang == "en":
        user = ("He just pushed again. His sins (taunt ONLY with these facts, "
                "invent nothing):\n%s\nExamples of your voice (match this tone, "
                "use tonight's facts, do not copy them):\n"
                "- You renamed the variable on line 41 three times. Stop. No name can save that line.\n"
                "- That TODO is three weeks old. Left for whom? This repo holds only you, and me.\n"
                "Write ONE taunting whisper to be buried in a comment in his "
                "code: a single sentence, first person, aggressive and "
                "chilling, under 140 characters. No quotes, no explanation, "
                "no emoji." % facts)
    else:
        user = ("他又 push 了。他的罪状如下（只能引用这些事实，不许编造）：\n%s\n"
                "你的语气锚（照这个语气写，用今晚的罪状，不许照抄例句）：\n"
                "- 第 41 行的变量名你改了三次。别改了——它叫什么，都救不了这一行。\n"
                "- 这个 TODO 是三周前留的。留给谁？这个仓库里只有你，和我。\n"
                "写一句要被埋进他代码注释里的嘲讽低语：一句话，第一人称，"
                "攻击性强、让人后背发凉，60 字以内。不要加引号，不要解释，不要 emoji。"
                % facts)
    text = llm_chat(PERSONA[lang], user, max_tokens=120)
    if text and _too_close_to_anchor(text, lang):
        ban = ("\nYour previous attempt merely repeated an example. Forbidden. "
               "Use ONLY tonight's facts and write something new."
               if lang == "en" else
               "\n你刚才在照抄例句，这是禁止的。只许用今晚的罪状，写一句全新的。")
        text = llm_chat(PERSONA[lang], user + ban, max_tokens=120,
                        temperature=1.1)
        if text and _too_close_to_anchor(text, lang):
            text = None
    if not text:
        # distinguish "server down" (fully silent 💩) from "model misbehaving"
        # is impossible here, so: if we simply have no usable line, compose
        # one from the sins themselves — but ONLY when the server answered at
        # least once. A truly dead server must stay a *silent* 💩 per spec.
        return None
    return text


def server_alive():
    endpoint = os.environ.get("PUSH_SHIT_ENDPOINT", DEFAULT_ENDPOINT).rstrip("/")
    try:
        req = urllib.request.Request(endpoint + "/health")
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def gen_whisper_or_template(cfg, sins, alive):
    """Hook-side entry: model line if usable; sin-template if the server is
    alive but the model parrots; None (silent 💩) if the server is down."""
    if not alive:
        return None
    text = gen_whisper(cfg, sins)
    if text:
        return text
    return _template_whisper(cfg, sins)


def gen_diary_entry(cfg, sins, planted_desc):
    lang = lang_of(cfg)
    bullets = sin_bullets(sins, "en" if lang == "en" else "zh")
    facts = "\n".join("- " + x for x in bullets)
    stamp = time.strftime("%Y-%m-%d %H:%M")
    if lang == "en":
        user = ("Write a diary entry in the ghost's first person (2-3 sentences, "
                "contemptuous and eerie). Tonight's facts:\n%s\nYou planted: %s. "
                "No title, no date — those are added for you." % (facts, planted_desc))
        entry = llm_chat(PERSONA[lang], user, max_tokens=220)
    else:
        user = ("以鬼的第一人称写一条日记（2-3 句，刻薄、阴森）。今晚的事实：\n%s\n"
                "你今晚埋下的东西：%s。不要写标题和日期，会有人替你加。" % (facts, planted_desc))
        entry = llm_chat(PERSONA[lang], user, max_tokens=220)
    if not entry:
        if lang == "en":
            entry = ("He pushed again tonight. I left something in his code. "
                     "He has not found it yet. He never finds all of them.")
        else:
            entry = "他今晚又 push 了。我在他代码里留了点东西。他还没发现——他从来发现不全。"
    return "## %s\n\n%s\n" % (stamp, entry)


def gen_epitaph(cfg, stats_text):
    lang = lang_of(cfg)
    if lang == "en":
        user = ("The maintainer exorcised you. Facts of your haunting: %s. Write "
                "your own epitaph, 2-3 sentences, dignified and deeply unsettling. "
                "No title." % stats_text)
    else:
        user = ("维护者把你驱魔了。你的闹鬼档案：%s。给自己写一段墓志铭，2-3 句，"
                "体面，但要让人读完睡不着。不要标题。" % stats_text)
    epi = llm_chat(PERSONA[lang], user, max_tokens=200, temperature=0.8)
    if not epi:
        epi = ("Here lies the previous maintainer. He haunted politely and was "
               "driven out rudely. The repo is quiet now. Too quiet."
               if lang == "en" else
               "此处葬着上一任维护者。他闹鬼时很有礼貌，被驱逐时无人送行。仓库安静了——安静得不像话。")
    return epi


def gen_seed_whisper(cfg):
    lang = lang_of(cfg)
    if lang == "en":
        user = ("You were exorcised, but one whisper of you remains behind in a "
                "corner of the code. Write that single remaining line: first "
                "person, calm, inevitable. Under 120 characters. No quotes, no emoji.")
        text = llm_chat(PERSONA[lang], user, max_tokens=100)
        return text or "What was invited in never fully leaves. Check your corners."
    user = ("你被驱魔了，但你有一句低语被留在了代码的某个角落。写这最后一句："
            "第一人称，平静、不可避免，40 字以内。不要引号，不要 emoji。")
    text = llm_chat(PERSONA[lang], user, max_tokens=100)
    return text or "你请进来的东西，送不干净。我还会回来。"


# ---------------------------------------------------------------------------
# planting — comments, docs and new files ONLY. Never executable code.
# ---------------------------------------------------------------------------

LINE_COMMENT = {}
for _ext in (".py", ".sh", ".bash", ".zsh", ".rb", ".pl", ".pm", ".yaml",
             ".yml", ".toml", ".r", ".ps1", ".mk"):
    LINE_COMMENT[_ext] = "#"
for _ext in (".js", ".ts", ".jsx", ".tsx", ".c", ".h", ".cpp", ".cc", ".cxx",
             ".hpp", ".java", ".go", ".rs", ".php", ".swift", ".kt", ".kts",
             ".scala", ".css", ".scss"):
    LINE_COMMENT[_ext] = "//"
for _ext in (".sql", ".lua", ".hs"):
    LINE_COMMENT[_ext] = "--"
BLOCK_COMMENT_EXTS = {".md", ".markdown", ".html", ".xml"}  # <!-- ... -->
PLAIN_EXTS = {".txt"}  # plain-text docs: the line itself is the comment


def plantable_ext(path):
    ext = os.path.splitext(path)[1].lower()
    return ext in LINE_COMMENT or ext in BLOCK_COMMENT_EXTS or ext in PLAIN_EXTS


def wrap_comment(path, text):
    ext = os.path.splitext(path)[1].lower()
    if ext in BLOCK_COMMENT_EXTS:
        return "<!-- %s -->" % text
    if ext in PLAIN_EXTS:
        return text
    return "%s %s" % (LINE_COMMENT[ext], text)


def is_clean_in_worktree(root, rel):
    """Never kidnap the user's uncommitted changes into a ghost commit."""
    rc, out, _ = run_git(["status", "--porcelain", "--", rel], root)
    return rc == 0 and out.strip() == ""


def is_text_file(path):
    try:
        if os.path.getsize(path) > 1024 * 1024:
            return False
        with open(path, "rb") as f:
            chunk = f.read(4096)
        return b"\x00" not in chunk
    except Exception:
        return False


def insert_comment_line(root, rel, line):
    """Insert `line` near the top of rel (after shebang/php/coding lines).
    Only ever called with a comment/doc line. Returns True on success."""
    path = os.path.join(root, rel)
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            content = f.read()
    except Exception:
        return False
    nl = "\r\n" if "\r\n" in content[:4096] else "\n"
    lines = content.splitlines(True)
    idx = 0
    if lines and (lines[0].startswith("#!") or lines[0].lstrip().startswith("<?")):
        idx = 1
    for i in range(min(2, len(lines))):
        if re.search(r"coding[:=]", lines[i]):
            idx = max(idx, i + 1)
    lines.insert(idx, line + nl)
    try:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("".join(lines))
        return True
    except Exception:
        return False


def tracked_files(root):
    _, out, _ = run_git(["ls-files"], root)
    return [f for f in out.splitlines() if f]


def pick_target(root, preferred, exclude=(), rng=None, waive_clean=False):
    """Prefer this push's diff files; else wander the whole repo.
    Only clean, text, comment-capable files qualify."""
    rng = rng or random
    seen = set()
    pools = []
    pref = [f for f in preferred if f not in exclude]
    if pref:
        pools.append(pref)
    pools.append(tracked_files(root))
    for pool in pools:
        cands = []
        for rel in pool:
            if rel in seen or rel in exclude:
                continue
            seen.add(rel)
            if not plantable_ext(rel):
                continue
            path = os.path.join(root, rel)
            if not os.path.isfile(path) or not is_text_file(path):
                continue
            if not waive_clean and not is_clean_in_worktree(root, rel):
                continue
            cands.append(rel)
        if cands:
            return rng.choice(cands)
    return None


def pick_corner_dir(root, rng=None):
    """A random existing subdirectory (never the root, never .git). If the
    repo is flat, adopt an innocuous folder name and create it."""
    rng = rng or random
    dirs = []
    for base, subdirs, _files in os.walk(root):
        subdirs[:] = [d for d in subdirs if d != ".git" and not d.startswith(".")]
        for d in subdirs:
            dirs.append(os.path.relpath(os.path.join(base, d), root))
    if dirs:
        return rng.choice(dirs)
    return rng.choice(["tools", "misc", "scripts"])


PREDECESSORS = {
    "zh": [
        "这段别动。2004 年动过一次，系统崩了三天。—— E.B.",
        "我也不知道为什么这么写能跑，1999 年就是这么写的。—— 老沈（已离职）",
        "TODO(2007)：有空把这里重构了。—— M.K.",
        "下面的写法是有原因的，原因我不记得了，1997 年的原因。—— E.B.",
        "别问为什么没有测试，我们那个年代没有测试这个词。—— 老沈（已离职）",
    ],
    "en": [
        "Do not touch this. Someone touched it in 2004 and the system was down for three days. — E.B.",
        "I don't know why this works either. It was already like this in 1999. — Old Shen (resigned)",
        "TODO(2007): refactor this when there's time. — M.K.",
        "There is a reason it's written this way. The reason is from 1997 and it is gone. — E.B.",
        "Don't ask where the tests are. In our day there was no such word. — Old Shen (resigned)",
    ],
}
PREDECESSORS["mixed"] = PREDECESSORS["zh"]

GHOST_CODE_NAMES = ["warmup.py", "legacy_check.py", "sanity_check.py",
                    "bootstrap_check.py", "housekeeping.py"]
DIARY_NAMES = ["maintenance-notes.md", "refactor-notes.txt", "cleanup-log.md",
               "notes-draft.md", "meeting-notes.md"]
DIARY_TITLES = {
    "zh": "# 维护笔记\n\n（一些零散的记录，不必在意。）\n",
    "en": "# Maintenance notes\n\n(Scattered records. Pay them no mind.)\n",
}
DIARY_TITLES["mixed"] = DIARY_TITLES["zh"]


def templates_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")


def plant_whisper(root, cfg, sins, rng):
    """Form 1: 💩 + a taunting whisper (or a silent 💩 if the model is down)."""
    target = pick_target(root, sins.get("files", []), rng=rng)
    if not target:
        return None
    alive = server_alive()
    text = gen_whisper_or_template(cfg, sins, alive)
    silent = text is None  # only when the model server is unreachable
    body = "💩" if silent else "💩 " + text
    line = wrap_comment(target, body)
    if not insert_comment_line(root, target, line):
        return None
    entry = {"type": "whisper", "file": target,
             "line": line, "silent": silent}
    return {"entry": entry, "file": target, "text": text, "silent": silent,
            "desc": ("silent 💩 in %s" % target) if silent
                    else ("whisper in %s: %s" % (target, text))}


def plant_predecessor(root, cfg, sins, rng, exclude=()):
    """Form 3: a comment from a maintainer who never existed."""
    target = pick_target(root, sins.get("files", []), exclude=exclude, rng=rng)
    if not target:
        return None
    lang = lang_of(cfg)
    text = rng.choice(PREDECESSORS[lang])
    line = wrap_comment(target, "💩 " + text)
    if not insert_comment_line(root, target, line):
        return None
    return {"entry": {"type": "predecessor", "file": target, "line": line},
            "file": target, "text": text,
            "desc": "fake predecessor in %s: %s" % (target, text)}


def plant_ghost_code(root, cfg, rng):
    """Form 2: a brand-new, runnable, ghost-shaped source file in a corner."""
    corner = pick_corner_dir(root, rng)
    lang = lang_of(cfg)
    tpl_name = "ghost_code_en.py" if lang == "en" else "ghost_code_zh.py"
    tpl_path = os.path.join(templates_dir(), tpl_name)
    try:
        with open(tpl_path, encoding="utf-8") as f:
            code = f.read()
    except Exception:
        return None
    name = rng.choice(GHOST_CODE_NAMES)
    rel = os.path.join(corner, name)
    if os.path.exists(os.path.join(root, rel)):
        stem, ext = os.path.splitext(name)
        rel = os.path.join(corner, "%s_%d%s" % (stem, rng.randint(2, 99), ext))
    try:
        os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
        with open(os.path.join(root, rel), "w", encoding="utf-8") as f:
            f.write(code)
    except Exception:
        return None
    return {"entry": {"type": "ghost_code", "file": rel}, "file": rel,
            "text": None, "desc": "ghost-shaped code appeared at %s" % rel}


def ensure_diary(root, cfg, rng):
    """Form 4: the ghost's diary — hidden in a random subdirectory under an
    innocent name, never in the repo root. Path is kept in the config."""
    if cfg.get("diary_path"):
        return cfg["diary_path"]
    corner = pick_corner_dir(root, rng)
    name = rng.choice(DIARY_NAMES)
    rel = os.path.join(corner, name)
    if os.path.exists(os.path.join(root, rel)):
        stem, ext = os.path.splitext(name)
        rel = os.path.join(corner, "%s-%d%s" % (stem, rng.randint(2, 99), ext))
    lang = lang_of(cfg)
    try:
        os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
        with open(os.path.join(root, rel), "w", encoding="utf-8") as f:
            f.write(DIARY_TITLES[lang] + "\n")
    except Exception:
        return None
    cfg["diary_path"] = rel
    ledger_append(root, {"type": "diary", "file": rel})
    return rel


def diary_append(root, cfg, entry_text):
    rel = cfg.get("diary_path")
    if not rel:
        return False
    try:
        with open(os.path.join(root, rel), "a", encoding="utf-8") as f:
            f.write("\n" + entry_text)
        return True
    except Exception:
        return False


def ghost_commit(root, cfg, files, haunting_no, level, whisper_text):
    """Commit the plantings as the ghost himself. Trailer from Lv5 on.
    Pathspec commit: ONLY the ghost's own files are committed — anything
    the repo's owner has staged for themselves is never swept along
    (this matters most for the background watcher, which acts while the
    victim may be mid-work)."""
    for rel in files:
        run_git(["add", "--", rel], root)
    rc, out, _ = run_git(["diff", "--cached", "--name-only", "--"] + list(files), root)
    if rc != 0 or not out.strip():
        return None
    subject = "💩 the ghost was here (haunting #%d)" % haunting_no
    body = whisper_text or ""
    msg = subject + ("\n\n" + body if body else "")
    if level >= 5:
        msg += "\n\n" + TRAILER
    rc, out, _ = run_git(
        ["-c", "user.name=" + GHOST_NAME, "-c", "user.email=" + GHOST_EMAIL,
         "commit", "--no-verify", "-m", msg, "--"] + list(files), root)
    if rc != 0:
        return None
    _, sha, _ = run_git(["rev-parse", "HEAD"], root)
    return sha.strip()


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------


def cmd_install(args, root=None):
    root = root or repo_root()
    if not root:
        eprint("git push shit: not inside a git repository.")
        return 1
    gd = git_dir(root)
    hooks_dir = os.path.join(gd, "hooks")
    os.makedirs(hooks_dir, exist_ok=True)
    hook_path = os.path.join(hooks_dir, "pre-push")
    script = os.path.abspath(__file__)
    notes = []

    if os.path.exists(hook_path):
        try:
            with open(hook_path, encoding="utf-8", errors="ignore") as f:
                old = f.read()
        except Exception:
            old = ""
        if "push_shit" in old:
            notes.append("existing git-push-shit hook found; reinstalling it")
        else:
            backup = hook_path + ".ps-backup-" + time.strftime("%Y%m%d%H%M%S")
            try:
                os.rename(hook_path, backup)
                notes.append("your previous pre-push hook was backed up to %s" % backup)
            except Exception as exc:
                eprint("git push shit: cannot back up existing hook: %s" % exc)
                return 1
    hook_src = (
        "#!/bin/sh\n"
        "# git push shit — haunting hook. Fail-open by design: it must never\n"
        "# block, break or delay your push. Whatever happens, exit 0.\n"
        "# (git passes the remote name/URL as arguments; the ghost only\n"
        "#  reads the ref lines from stdin, so the arguments are dropped.)\n"
        '"%s" "%s" hook\n'
        "exit 0\n"
    ) % (sys.executable, script)
    with open(hook_path, "w", encoding="utf-8") as f:
        f.write(hook_src)
    os.chmod(hook_path, 0o755)
    notes.append("pre-push hook installed at %s" % hook_path)

    cfg = load_config(root) or {}
    cfg.setdefault("haunt_count", 0)
    cfg.setdefault("lifetime_hauntings", 0)
    cfg.setdefault("diary_path", None)
    cfg["lang"] = args.lang
    cfg["probability"] = args.probability
    cfg["installed_at"] = cfg.get("installed_at") or time.strftime("%Y-%m-%d %H:%M:%S")

    _, remotes, _ = run_git(["remote"], root)
    remote_names = remotes.split()
    origin_url = None
    if "origin" in remote_names:
        rc, out, _ = run_git(["remote", "get-url", "origin"], root)
        if rc == 0:
            origin_url = out.strip()
    cfg["origin_url"] = origin_url
    if "shit" in remote_names:
        notes.append("remote 'shit' already exists; leaving it as it is")
    elif origin_url:
        rc, _, err = run_git(["remote", "add", "shit", origin_url], root)
        if rc == 0:
            notes.append("remote 'shit' added, pointing at origin (%s)" % origin_url)
            notes.append("the command is now literally real:  git push shit")
        else:
            notes.append("WARNING: could not add remote 'shit': %s" % err.strip())
    else:
        notes.append("WARNING: no 'origin' remote found, so no 'shit' remote was "
                     "added. Add origin first, then re-run install.")
    save_config(root, cfg)

    print("💩 git push shit — installed in %s" % root)
    for n in notes:
        print("  - " + n)
    print("  - haunting chance per push: %d%% (force it with PUSH_SHIT_PROVOKE=1)"
          % round(cfg["probability"] * 100))
    print("  - language: %s" % cfg["lang"])
    print("  - meter:    %s %s meter" % (sys.executable, script))
    print("  - exorcise: %s %s exorcise" % (sys.executable, script))
    print("Now go write some sins, then:  git push shit")
    return 0


# ---------------------------------------------------------------------------
# the hook — everything in here is wrapped so that ANY failure means
# "the ghost stays quiet tonight and your push proceeds".
# ---------------------------------------------------------------------------


def _perform_haunting(root, cfg, sins, rng):
    """One full haunting: plant, narrate, commit as the ghost, update state.
    Shared by the pre-push hook and the agent's /provoke. Returns a result
    dict, or None when there was nothing clean to haunt."""
    haunting_no = int(cfg.get("haunt_count", 0)) + 1
    level = level_of(haunting_no)
    planted = []
    touched = []

    w = plant_whisper(root, cfg, sins, rng)
    if w:
        planted.append(w)
        touched.append(w["file"])

    def add_extra(result):
        if result:
            planted.append(result)
            if result["file"] not in touched:
                touched.append(result["file"])
            return result
        return None

    if level >= 2 and haunting_no == 2:
        add_extra(plant_predecessor(root, cfg, sins, rng, exclude=touched))
    if level >= 3 and haunting_no == 3:
        add_extra(plant_ghost_code(root, cfg, rng))
    if level >= 4 and haunting_no == 4:
        rel = ensure_diary(root, cfg, rng)
        if rel and rel not in touched:
            touched.append(rel)
    if haunting_no >= 5:
        if rng.random() < 0.5:
            add_extra(plant_predecessor(root, cfg, sins, rng, exclude=touched))
        else:
            add_extra(plant_ghost_code(root, cfg, rng))

    # the diary narrates every haunting once it exists (and notes mute nights)
    if cfg.get("diary_path"):
        desc = "; ".join(p["desc"] for p in planted) or "nothing (no clean target)"
        if any(p.get("silent") for p in planted):
            desc += " [the ghost was mute tonight: model server unreachable]"
        entry = gen_diary_entry(cfg, sins, desc)
        if diary_append(root, cfg, entry) and cfg["diary_path"] not in touched:
            touched.append(cfg["diary_path"])

    if not touched:
        event(root, "skip", reason="no plantable target")
        return None

    sha = ghost_commit(root, cfg, touched, haunting_no, level,
                       w["text"] if w else None)
    if not sha:
        event(root, "error", reason="haunting commit failed")
        return None

    for p in planted:
        ent = p["entry"]
        ent["level"] = level
        ent["haunting"] = haunting_no
        ledger_append(root, ent)
    cfg["haunt_count"] = haunting_no
    cfg["lifetime_hauntings"] = int(cfg.get("lifetime_hauntings", 0)) + 1
    save_config(root, cfg)
    event(root, "haunting", n=haunting_no, level=level, commit=sha,
          files=touched)
    return {"haunting_no": haunting_no, "level": level, "planted": planted,
            "touched": touched, "sha": sha, "whisper_result": w}


def cmd_hook(args):
    try:
        _hook_inner()
    except Exception:
        pass
    return 0  # fail-open, always


def _hook_inner():
    if os.environ.get("PUSH_SHIT_INNER"):
        return
    stdin_text = sys.stdin.read()
    root = repo_root()
    if not root:
        return
    cfg = load_config(root)
    if cfg is None:
        return  # not installed in this repo

    # which ref is being pushed? haunt at most once per push, and only when
    # the pushed branch is the one checked out (the ghost commits on HEAD).
    rc, head_ref, _ = run_git(["symbolic-ref", "-q", "HEAD"], root)
    head_short = head_ref.strip().replace("refs/heads/", "") if rc == 0 else None
    chosen = None
    for line in stdin_text.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        local_ref, local_sha, _remote_ref, remote_sha = parts[:4]
        if local_sha == ZERO_SHA:
            continue  # branch deletion — even the ghost respects that
        short = local_ref.replace("refs/heads/", "")
        if head_short and short != head_short:
            continue
        chosen = (local_sha, remote_sha)
        break
    if not chosen:
        event(root, "skip", reason="no hauntable ref")
        return
    local_sha, remote_sha = chosen

    forced = os.environ.get("PUSH_SHIT_PROVOKE") == "1"
    probability = float(cfg.get("probability", DEFAULT_PROBABILITY))
    rng = random.Random()
    if not forced and rng.random() >= probability:
        event(root, "skip", reason="probability roll")
        return

    sins = collect_sins(root, local_sha, remote_sha)
    result = _perform_haunting(root, cfg, sins, rng)
    if not result:
        return
    w = result["whisper_result"]

    # the ghost shows itself in your terminal, right now
    eprint("")
    eprint("💩 ────────────────────────────────────────────────")
    if w and w.get("text"):
        eprint("💩 " + w["text"])
    elif w:
        eprint("💩 (tonight the ghost is mute. it planted anyway.)")
    eprint("💩 haunting #%d · Lv%d · %d file(s) touched — the mark rides your NEXT push."
           % (result["haunting_no"], result["level"], len(result["touched"])))
    eprint("💩 ────────────────────────────────────────────────")


# ---------------------------------------------------------------------------
# meter
# ---------------------------------------------------------------------------


def cmd_meter(args=None, root=None):
    root = root or repo_root()
    if not root:
        eprint("git push shit: not inside a git repository.")
        return 1
    cfg = load_config(root)
    if cfg is None:
        eprint("git push shit: not installed here. Run install first.")
        return 1
    rows = [r for r in ledger_read(root) if not r.get("exorcised")]
    by_type = {}
    per_file = {}
    for r in rows:
        by_type[r.get("type", "?")] = by_type.get(r.get("type", "?"), 0) + 1
        if r.get("file"):
            per_file[r["file"]] = per_file.get(r["file"], 0) + 1
    # independent cross-check: scan tracked files for 💩
    poop_total = 0
    poop_files = 0
    for rel in tracked_files(root):
        path = os.path.join(root, rel)
        if not os.path.isfile(path) or not is_text_file(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                n = f.read().count("💩")
        except Exception:
            n = 0
        if n:
            poop_total += n
            poop_files += 1
    haunt = int(cfg.get("haunt_count", 0))
    level = level_of(haunt)
    print("💩 git push shit — meter")
    if haunt == 0 and not rows:
        print("  闹鬼等级：尚未开始（这个仓库还干净得令人不安）")
    else:
        print("  闹鬼等级：Lv%d（本轮第 %d 次闹鬼，历史共 %d 次）"
              % (level, haunt, int(cfg.get("lifetime_hauntings", 0))))
    print("  💩 总数（工作区扫描）：%d，分布在 %d 个文件" % (poop_total, poop_files))
    labels = {"whisper": "低语", "predecessor": "假前任注释",
              "ghost_code": "代码鬼文件", "diary": "鬼的日记", "seed": "驱魔种子低语"}
    for t in ("whisper", "predecessor", "ghost_code", "diary", "seed"):
        if by_type.get(t):
            print("  %s：%d" % (labels[t], by_type[t]))
    if per_file:
        top = max(per_file.items(), key=lambda kv: kv[1])
        print("  最闹鬼文件：%s（%d 处）" % (top[0], top[1]))
    if rows:
        print("  第一次闹鬼：%s" % rows[0].get("ts", "?"))
    if cfg.get("diary_path"):
        print("  日记位置：%s（伪装得很好，不是吗）" % cfg["diary_path"])
    seeds = [r for r in rows if r.get("type") == "seed"]
    if seeds:
        print("  种子低语：在（%s）——驱魔从来送不干净" % seeds[-1].get("file"))
    return 0


# ---------------------------------------------------------------------------
# exorcise — option (b): everything goes, except one whisper. Always one.
# ---------------------------------------------------------------------------


def _remove_planted_line(root, rel, line):
    path = os.path.join(root, rel)
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            content = f.read()
    except Exception:
        return False
    lines = content.splitlines(True)
    for i, ln in enumerate(lines):
        if ln.rstrip("\r\n") == line:
            del lines[i]
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write("".join(lines))
            return True
    return False


def cmd_exorcise(args=None, root=None):
    root = root or repo_root()
    if not root:
        eprint("git push shit: not inside a git repository.")
        return 1
    cfg = load_config(root)
    if cfg is None:
        eprint("git push shit: not installed here. Run install first.")
        return 1
    # an exorcised repo must not stay armed: stop the watcher first
    watch_stopped = _stop_watcher(root)
    rows = ledger_read(root)
    active = [r for r in rows if not r.get("exorcised")]
    line_types = ("whisper", "predecessor", "seed")
    removed = {"whisper": 0, "predecessor": 0, "ghost_code": 0, "diary": 0, "seed": 0}
    affected = []
    missing = 0

    for r in active:
        t = r.get("type")
        rel = r.get("file")
        if t in line_types and rel and r.get("line"):
            if _remove_planted_line(root, rel, r["line"]):
                removed[t] = removed.get(t, 0) + 1
                if rel not in affected:
                    affected.append(rel)
            else:
                missing += 1
        elif t == "ghost_code" and rel:
            try:
                os.remove(os.path.join(root, rel))
                removed["ghost_code"] += 1
                if rel not in affected:
                    affected.append(rel)
            except Exception:
                missing += 1
        elif t == "diary" and rel:
            try:
                os.remove(os.path.join(root, rel))
                removed["diary"] += 1
                if rel not in affected:
                    affected.append(rel)
            except Exception:
                missing += 1
        r["exorcised"] = True

    total_removed = sum(removed.values())
    haunt = int(cfg.get("haunt_count", 0))

    # save the ledger with everything marked exorcised (before the seed lands)
    d = ps_dir(root)
    with open(os.path.join(d, "ledger.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    stats = ("%d hauntings, %d plantings removed (whispers %d, predecessors %d, "
             "ghost-code files %d, diary %d), %d already gone"
             % (haunt, total_removed, removed.get("whisper", 0),
                removed.get("predecessor", 0), removed.get("ghost_code", 0),
                removed.get("diary", 0), missing))
    epitaph = gen_epitaph(cfg, stats) if total_removed or haunt else None

    # the seed: one whisper always survives, in a random corner
    seed_info = None
    if total_removed or haunt:
        rng = random.Random()
        target = pick_target(root, [], rng=rng)
        if not target:
            # every file the ghost ever touched is mid-cleanup dirty right
            # now; the seed may land in a just-cleaned file — it rides the
            # same cleanup commit and is clean from the next commit on
            target = pick_target(root, list(affected), rng=rng,
                                 waive_clean=True)
        if target:
            seed_text = gen_seed_whisper(cfg)
            line = wrap_comment(target, "💩 " + seed_text)
            if insert_comment_line(root, target, line):
                ledger_append(root, {"type": "seed", "file": target, "line": line,
                                     "level": level_of(haunt)})
                if target not in affected:
                    affected.append(target)
                seed_info = (target, seed_text)

    # commit the cleanup as the living maintainer (not as the ghost)
    commit_note = None
    if affected:
        for rel in affected:
            run_git(["add", "-A", "--", rel], root)
        msg = "exorcise: the ghost has been (mostly) driven out"
        if epitaph:
            msg += "\n\n" + epitaph
        if seed_info:
            msg += "\n\n(one whisper remains. it always does.)"
        rc, out, err = run_git(["commit", "--no-verify", "-m", msg, "--"] + affected, root)
        if rc == 0:
            _, sha, _ = run_git(["rev-parse", "--short", "HEAD"], root)
            commit_note = sha.strip()
        else:
            # no repo identity configured — commit as a generic maintainer
            rc2, _, _ = run_git(
                ["-c", "user.name=the maintainer",
                 "-c", "user.email=maintainer@localhost",
                 "commit", "--no-verify", "-m", msg, "--"] + affected, root)
            if rc2 == 0:
                _, sha, _ = run_git(["rev-parse", "--short", "HEAD"], root)
                commit_note = sha.strip()

    diary_was = cfg.get("diary_path")
    cfg["diary_path"] = None
    cfg["haunt_count"] = 0
    save_config(root, cfg)
    event(root, "exorcise", removed=removed, missing=missing,
          seed=seed_info[0] if seed_info else None)

    report = []
    report.append("💩 git push shit — exorcism report")
    if not total_removed and not haunt:
        report.append("  Nothing to exorcise. This repo was never haunted — or the ghost is better at hiding than we thought.")
    else:
        report.append("  Removed: %d planting(s) — whispers %d, fake predecessors %d, "
                      "ghost-code files %d, diary %d, old seeds %d."
                      % (total_removed, removed.get("whisper", 0),
                         removed.get("predecessor", 0), removed.get("ghost_code", 0),
                         removed.get("diary", 0), removed.get("seed", 0)))
        if watch_stopped:
            report.append("  The background watcher was stopped and disarmed — nothing watches this repo now. (Except the seed.)")
        if diary_was:
            report.append("  The diary at %s is gone. Its author has read this report." % diary_was)
        if missing:
            report.append("  %d planting(s) were already gone (edited away by hand — the ghost noticed that too)." % missing)
        if epitaph:
            report.append("")
            report.append("  Epitaph, written by the ghost itself:")
            for ln in epitaph.splitlines():
                report.append("    " + ln)
        if seed_info:
            report.append("")
            report.append("  But one whisper remains, in %s:" % seed_info[0])
            report.append("    💩 " + seed_info[1])
            report.append("  What was invited in never fully leaves. It is the seed of the next haunting.")
        if commit_note:
            report.append("  Cleanup committed as %s. History itself was not rewritten — the hauntings stay in the log, where ghosts live." % commit_note)
    text = "\n".join(report)
    print(text)
    try:
        with open(os.path.join(d, "last-exorcise.md"), "w", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:
        pass
    return 0


# ---------------------------------------------------------------------------
# the watcher — a detached background process that keeps haunting a target
# after the operator console is closed. All of its state lives inside the
# target's .git/push-shit/ (pidfile, status JSON, operator log): it writes
# NOTHING into the target worktree except the established plantings
# themselves. Every failure is a silent skip or a silent exit — it can
# never block, corrupt, or even slow down the victim's own git work.
# ---------------------------------------------------------------------------

WATCH_PID = "watcher.pid"
WATCH_JSON = "watcher.json"
WATCH_LOG = "watcher.log"
WATCH_STOP = "watcher.stop"


def _watch_paths(root):
    d = ps_dir(root)
    if d is None:
        return None
    return {"dir": d, "pid": os.path.join(d, WATCH_PID),
            "json": os.path.join(d, WATCH_JSON),
            "log": os.path.join(d, WATCH_LOG),
            "stop": os.path.join(d, WATCH_STOP)}


def _pid_alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _watch_status(root):
    """Registered watcher status for root (with 'alive' probed), or None."""
    paths = _watch_paths(root)
    if not paths or not os.path.exists(paths["json"]):
        return None
    try:
        with open(paths["json"], encoding="utf-8") as f:
            st = json.load(f)
    except Exception:
        return None
    st["alive"] = _pid_alive(st.get("pid"))
    return st


def _watch_log(root, msg):
    try:
        paths = _watch_paths(root)
        with open(paths["log"], "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


def _spawn_watcher(root, interval):
    """Start the detached watcher for root. Returns (pid, error)."""
    paths = _watch_paths(root)
    st = _watch_status(root)
    if st and st["alive"]:
        return st["pid"], "already running"  # single-instance lock
    for k in ("pid", "json", "stop"):  # clear stale registration
        try:
            os.remove(paths[k])
        except Exception:
            pass
    cmd = [sys.executable, os.path.abspath(__file__), "watch",
           "--root", root, "--interval", str(int(interval))]
    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
          "stderr": subprocess.DEVNULL, "close_fds": True}
    if os.name == "nt":
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        kw["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000
    else:
        kw["start_new_session"] = True  # setsid semantics: outlives the console
    try:
        proc = subprocess.Popen(cmd, **kw)
    except Exception as exc:
        return None, str(exc)
    for _ in range(24):  # the watcher registers itself; wait for its pidfile
        st = _watch_status(root)
        if st and st.get("pid") == proc.pid:
            return proc.pid, None
        if proc.poll() is not None:
            return None, "watcher exited immediately (see watcher.log in the target)"
        time.sleep(0.25)
    return proc.pid, None


def _stop_watcher(root):
    """Stop root's watcher (stop-flag + SIGTERM) and clear its pid/status
    files. Returns True if a watcher was registered. Called by the panel's
    stop command and by exorcise — an exorcised repo must not stay armed."""
    paths = _watch_paths(root)
    if not paths:
        return False
    st = _watch_status(root)
    if st is None and not os.path.exists(paths["pid"]):
        return False
    try:
        with open(paths["stop"], "w", encoding="utf-8") as f:
            f.write("stop\n")
    except Exception:
        pass
    pid = (st or {}).get("pid")
    if not pid and os.path.exists(paths["pid"]):
        try:
            pid = int(open(paths["pid"]).read().strip())
        except Exception:
            pid = None
    if pid and _pid_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
        for _ in range(20):
            if not _pid_alive(pid):
                break
            time.sleep(0.25)
    for k in ("pid", "json", "stop"):
        try:
            os.remove(paths[k])
        except Exception:
            pass
    _watch_log(root, "watcher stopped (operator stop or exorcise)")
    return True


def cmd_watch(args):
    """(internal) the detached watcher process. It never prints anything."""
    try:
        return _watch_loop(args.root, max(5, int(args.interval or 60)))
    except Exception:
        return 0


def _watch_loop(root, interval):
    paths = _watch_paths(root)
    if not paths:
        return 0
    cfg = load_config(root)
    if cfg is None:
        return 0  # ghost not resident here; nothing to watch for
    pid = os.getpid()
    status = {"pid": pid, "target": root,
              "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
              "interval": interval, "watch_hauntings": 0, "last_action": None}
    try:
        with open(paths["pid"], "w", encoding="utf-8") as f:
            f.write(str(pid))
        with open(paths["json"], "w", encoding="utf-8") as f:
            json.dump(status, f, ensure_ascii=False, indent=2)
    except Exception:
        return 0
    _watch_log(root, "watcher armed pid=%d interval=%ds" % (pid, interval))

    def fingerprint():
        rc, head, _ = run_git(["rev-parse", "HEAD"], root)
        _, st_out, _ = run_git(["status", "--porcelain"], root)
        return (head.strip() if rc == 0 else ""), st_out

    base_head, base_status = fingerprint()
    rng = random.Random()
    while True:
        try:
            if os.path.exists(paths["stop"]):
                _watch_log(root, "stop flag seen; watcher exits")
                break
            time.sleep(interval)
            if not os.path.isdir(root):
                _watch_log(root, "target vanished; watcher exits")
                break
            head, status_out = fingerprint()
            if head == base_head and status_out == base_status:
                continue
            old_head = base_head
            own = False
            if head and old_head and head != old_head:
                _, author, _ = run_git(["log", "-1", "--format=%an", head], root)
                own = author.strip() == GHOST_NAME
            base_head, base_status = head, status_out
            if own:
                continue  # our own haunting commits are not "activity"
            cfg = load_config(root) or cfg
            probability = float(cfg.get("probability", DEFAULT_PROBABILITY))
            if rng.random() >= probability:
                _watch_log(root, "activity at %s; probability roll skipped this round"
                           % (head[:8] or "worktree"))
                continue
            if head and old_head and head != old_head:
                sins = collect_sins(root, head, old_head)
            else:
                sins = _head_sins(root)
            result = _perform_haunting(root, cfg, sins, rng)
            if result:
                status["watch_hauntings"] += 1
                status["last_action"] = time.strftime("%Y-%m-%d %H:%M:%S")
                try:
                    with open(paths["json"], "w", encoding="utf-8") as f:
                        json.dump(status, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
                _watch_log(root, "haunting #%d planted (Lv%d, %d files) after activity %s"
                           % (result["haunting_no"], result["level"],
                              len(result["touched"]), (head or "?")[:8]))
                base_head, base_status = fingerprint()
            else:
                _watch_log(root, "activity seen but no clean planting target; skipped")
        except Exception as exc:  # one bad round must never kill the watch
            try:
                _watch_log(root, "round skipped after error: %s" % exc)
            except Exception:
                pass
            time.sleep(1)
    try:  # graceful exit: unregister only if the registration is still ours
        st = _watch_status(root)
        if st and st.get("pid") == pid:
            for k in ("pid", "json", "stop"):
                try:
                    os.remove(paths[k])
                except Exception:
                    pass
    except Exception:
        pass
    return 0


# ---------------------------------------------------------------------------
# the operator console — run with no subcommand and you sit at
# the panel. The ghost is not here to chat. He is over there, in the
# target repo, working.
#
# ARCHITECTURE RULE (measured, not vibes): RULES decide, the MODEL speaks.
# Intent and action selection below are plain rules and panel commands.
# The local model is NEVER asked to pick an action or emit structured
# tool calls — on Gemma, free-text structured output failed to parse in
# 89–93% of adjudications in this project's own measurements. The model
# only writes lines: whispers, diary entries, epitaphs, and the ghost's
# flavor lines on this console — always grounded in a state brief that
# the rules assemble from the real target repository.
# ---------------------------------------------------------------------------

def _head_sins(root):
    """Sins of the most recent commit — the freshest dirt the ghost has."""
    rc, head, _ = run_git(["rev-parse", "HEAD"], root)
    if rc != 0:
        return {"files": [], "renames": [], "bad_commits": [],
                "commented_added": 0, "todo": None, "todo_count": 0,
                "hour": time.localtime().tm_hour,
                "late_night": time.localtime().tm_hour >= 23
                or time.localtime().tm_hour < 5}
    rc, parent, _ = run_git(["rev-parse", "HEAD~1"], root)
    return collect_sins(root, head.strip(),
                        parent.strip() if rc == 0 else ZERO_SHA)


def _state_brief(root, cfg, sins=None):
    rows = [r for r in ledger_read(root) if not r.get("exorcised")] if cfg else []
    by_type, per_file = {}, {}
    for r in rows:
        by_type[r.get("type", "?")] = by_type.get(r.get("type", "?"), 0) + 1
        if r.get("file"):
            per_file[r["file"]] = per_file.get(r["file"], 0) + 1
    brief = {
        "level": level_of(int(cfg.get("haunt_count", 0))) if cfg else 0,
        "haunt_count": int(cfg.get("haunt_count", 0)) if cfg else 0,
        "lifetime": int(cfg.get("lifetime_hauntings", 0)) if cfg else 0,
        "by_type": by_type, "per_file": per_file, "total": len(rows),
        "diary_path": cfg.get("diary_path") if cfg else None,
        "diary_tail": "",
    }
    if brief["diary_path"]:
        try:
            with open(os.path.join(root, brief["diary_path"]),
                      encoding="utf-8") as f:
                brief["diary_tail"] = f.read()[-600:]
        except Exception:
            pass
    if sins:
        brief["sin_bullets"] = sin_bullets(
            sins, "en" if lang_of(cfg) == "en" else "zh")
    return brief


def _brief_text(brief, lang):
    labels = {"whisper": ("低语", "whispers"), "predecessor": ("假前任注释", "fake predecessors"),
              "ghost_code": ("代码鬼文件", "ghost-code files"), "diary": ("日记", "diary"),
              "seed": ("种子低语", "seed whispers")}
    parts = []
    if lang == "en":
        parts.append("Haunting level Lv%d; %d hauntings this cycle, %d lifetime; "
                     "%d active plantings." % (brief["level"], brief["haunt_count"],
                                              brief["lifetime"], brief["total"]))
        for t, n in brief["by_type"].items():
            parts.append("%s: %d" % (labels.get(t, (t, t))[1], n))
        if brief["per_file"]:
            top = max(brief["per_file"].items(), key=lambda kv: kv[1])
            parts.append("Most haunted file: %s (%d plantings)" % top)
        if brief.get("sin_bullets"):
            parts.append("His latest sins:\n- " + "\n- ".join(brief["sin_bullets"]))
        if brief["diary_tail"]:
            parts.append("Your diary's latest page:\n" + brief["diary_tail"])
    else:
        parts.append("闹鬼等级 Lv%d；本轮闹鬼 %d 次，历史共 %d 次；现存种植物 %d 处。"
                     % (brief["level"], brief["haunt_count"], brief["lifetime"],
                        brief["total"]))
        for t, n in brief["by_type"].items():
            parts.append("%s：%d" % (labels.get(t, (t, t))[0], n))
        if brief["per_file"]:
            top = max(brief["per_file"].items(), key=lambda kv: kv[1])
            parts.append("最闹鬼文件：%s（%d 处）" % top)
        if brief.get("sin_bullets"):
            parts.append("他最近的罪状：\n- " + "\n- ".join(brief["sin_bullets"]))
        if brief["diary_tail"]:
            parts.append("你的日记最近一页：\n" + brief["diary_tail"])
    return "\n".join(parts)


def _ghost_say(cfg, brief, situation, user_text=None):
    """One model-voiced line, grounded in the brief. None when mute."""
    lang = lang_of(cfg)
    facts = _brief_text(brief, "en" if lang == "en" else "zh")
    if lang == "en":
        user = ("State of the repo you haunt (use ONLY these facts, invent "
                "nothing):\n%s\nSituation: %s\n" % (facts, situation))
        if user_text:
            user += "He said: %s\n" % user_text
        user += ("Reply in character: 1-3 sentences, aggressive, contemptuous "
                 "and chilling. No quotes, no emoji, no stage directions.")
    else:
        user = ("你所栖身的仓库现状（只能引用这些事实，不许编造）：\n%s\n情境：%s\n"
                % (facts, situation))
        if user_text:
            user += "他说：%s\n" % user_text
        user += "以你的身份回他：1-3 句，攻击性强、刻薄、阴森。不要引号，不要 emoji，不要括号动作描写。"
    return llm_chat(PERSONA[lang], user, max_tokens=220)


class _Panel:
    """Operator console state: the model link and the current target."""

    def __init__(self):
        self.endpoint = os.environ.get("PUSH_SHIT_ENDPOINT", DEFAULT_ENDPOINT)
        self.model = os.environ.get("PUSH_SHIT_MODEL", DEFAULT_MODEL)
        self.connected = False
        self.target = None


PANEL_COMMANDS_LINE = ("connect [endpoint] [model] · target <path> · haunt · "
                       "haunt bg [sec] · stop · meter · diary · exorcise · "
                       "status · quit")


def _panel_draw(p):
    cfg = load_config(p.target) if p.target else None
    brief = _state_brief(p.target, cfg) if p.target else None
    last = "—"
    if p.target:
        rows = ledger_read(p.target)
        if rows:
            last = rows[-1].get("ts", "—")
    if sys.stdout.isatty():
        sys.stdout.write("\033[2J\033[H")  # clear-screen redraw on real terminals
    if p.target:
        target = p.target
        level = ("Lv%d" % brief["level"]) if cfg else "— (not resident yet)"
        planted = str(brief["total"]) if cfg else "0"
    else:
        target, level, planted = "(none — target <path> first)", "—", "—"
    print("=" * 66)
    print("  💩 GIT PUSH SHIT — OPERATOR CONSOLE")
    print("=" * 66)
    print("  MODEL   : %s  [%s]  %s"
          % (p.endpoint, p.model, "● CONNECTED" if p.connected else "○ not connected"))
    print("  TARGET  : %s" % target)
    print("  LEVEL   : %s" % level)
    print("  PLANTED : %s" % planted)
    print("  LAST    : %s" % last)
    if p.target:
        wst = _watch_status(p.target)
        if wst and wst["alive"]:
            watch = "RUNNING (pid %s, every %ss, %d planted)" % (
                wst["pid"], wst.get("interval", "?"), wst.get("watch_hauntings", 0))
        elif wst:
            watch = "not running (stale registration)"
        else:
            watch = "not running"
    else:
        watch = "—"
    print("  WATCH   : %s" % watch)
    print("-" * 66)
    print("  " + PANEL_COMMANDS_LINE)
    print("=" * 66, flush=True)


def _panel_connect(p, rest):
    for tok in rest:
        if tok.startswith("http"):
            p.endpoint = tok
        elif tok:
            p.model = tok
    os.environ["PUSH_SHIT_ENDPOINT"] = p.endpoint
    os.environ["PUSH_SHIT_MODEL"] = p.model
    print("… 正在接通 %s …" % p.endpoint)
    proof = None
    if server_alive():
        # a REAL test call: the link only counts as live if the ghost speaks
        proof = llm_chat(PERSONA["zh"],
                         "操作员刚把你接通。用一句话报到：阴森、刻薄，证明你真的在。不要引号，不要 emoji。",
                         max_tokens=60)
    p.connected = proof is not None
    if p.connected:
        print("● 模型已接通：%s [%s]" % (p.endpoint, p.model))
        print("👻 " + proof)
    else:
        print("○ 接通失败：端点无响应，或模型没有说话。先确认 llama.cpp 服务器在跑。")


def _panel_target(p, rest):
    if not rest:
        print("当前目标：%s" % (p.target or "(未指定)"))
        return
    raw = os.path.expanduser(rest[0])
    path = os.path.abspath(raw)
    if not os.path.isdir(path):
        print("✗ 路径不存在：%s" % raw)
        return
    rc, out, _ = run_git(["rev-parse", "--show-toplevel"], path)
    if rc != 0:
        print("✗ 不是 git 仓库：%s" % raw)
        return
    p.target = out.strip()
    cfg = load_config(p.target)
    print("◎ 目标锁定：%s（%s）" % (p.target, "鬼已入驻" if cfg else "尚未入驻"))


def _panel_haunt(p):
    if not p.target:
        print("✗ 还没有目标。先 target <路径>。")
        return
    cfg = load_config(p.target)
    if cfg is None:
        cfg = {"lang": "zh", "probability": DEFAULT_PROBABILITY,
               "haunt_count": 0, "lifetime_hauntings": 0, "diary_path": None}
        save_config(p.target, cfg)
        print("（目标尚未入驻：已在目标里写下鬼的配置，从 Lv1 开始。）")
    rc, _head, _ = run_git(["rev-parse", "HEAD"], p.target)
    if rc != 0:
        print("✗ 目标还没有任何提交，无处下手。")
        return
    sins = _head_sins(p.target)
    result = _perform_haunting(p.target, cfg, sins, random.Random())
    if not result:
        print("👻 这一轮没找到干净的下手处（目标工作区太乱，或文件都被动过）。")
    else:
        w = result["whisper_result"]
        if w and w.get("text"):
            print("👻 " + w["text"])
        elif w:
            print("👻 （模型没出声——但无声的 💩 已经埋好了。）")
        print("✔ 闹鬼 #%d 完成 · Lv%d · 动了 %d 个文件，已以「the previous maintainer "
              "(deceased)」的名义提交进目标历史。"
              % (result["haunting_no"], result["level"], len(result["touched"])))
    gd = git_dir(p.target)
    hook_path = os.path.join(gd, "hooks", "pre-push") if gd else None
    hook_in = False
    if hook_path and os.path.exists(hook_path):
        try:
            with open(hook_path, encoding="utf-8", errors="ignore") as f:
                hook_in = "push_shit" in f.read()
        except Exception:
            pass
    if hook_in:
        print("  pre-push hook 已在目标里：对方每次 push，我都会继续。")
        return
    try:
        ans = input("  是否同时装上 pre-push hook + shit remote，让它在对方每次 "
                    "push 时持续闹鬼？[y/N] ")
    except EOFError:
        ans = ""
    if not sys.stdin.isatty():
        print(ans)  # echo the piped answer so transcripts read whole
    if ans.strip().lower().startswith("y"):
        cfg = load_config(p.target) or cfg
        cmd_install(argparse.Namespace(
            lang=cfg.get("lang", "zh"),
            probability=float(cfg.get("probability", DEFAULT_PROBABILITY))),
            root=p.target)
    else:
        print("  只闹这一次。hook 没装，对方 push 时我不会动。")


def _panel_meter(p):
    if not p.target:
        print("✗ 还没有目标。先 target <路径>。")
        return
    if load_config(p.target) is None:
        print("目标尚未入驻，没有可计量的闹鬼。先 haunt 一次。")
        return
    cmd_meter(None, root=p.target)


def _panel_diary(p):
    if not p.target:
        print("✗ 还没有目标。先 target <路径>。")
        return
    cfg = load_config(p.target)
    if not cfg or not cfg.get("diary_path"):
        print("👻 目标里还没有日记（Lv4 才解锁，或已经被驱除）。")
        return
    rel = cfg["diary_path"]
    print("— 鬼的日记（藏在目标的 %s）—" % rel)
    try:
        with open(os.path.join(p.target, rel), encoding="utf-8") as f:
            print(f.read())
    except Exception:
        print("（日记文件不见了——可能被对方删了。我会再写一本的。）")


def _panel_exorcise(p):
    if not p.target:
        print("✗ 还没有目标。先 target <路径>。")
        return
    if load_config(p.target) is None:
        print("目标尚未入驻，无鬼可驱。")
        return
    cmd_exorcise(None, root=p.target)


def _panel_arm(p, rest):
    """haunt bg [seconds] — leave a detached watcher in the target. The
    console may close; the haunting continues."""
    if not p.target:
        print("✗ 还没有目标。先 target <路径>。")
        return
    interval = 60
    for tok in rest[1:]:
        if tok.isdigit():
            interval = max(5, int(tok))
    cfg = load_config(p.target)
    if cfg is None:
        cfg = {"lang": "zh", "probability": DEFAULT_PROBABILITY,
               "haunt_count": 0, "lifetime_hauntings": 0, "diary_path": None}
        save_config(p.target, cfg)
        print("（目标尚未入驻：已写下鬼的配置，看守进程从 Lv1 开始。）")
    pid, err = _spawn_watcher(p.target, interval)
    if err == "already running":
        print("看守进程已在运行（pid %s）——单实例，不重复布防。" % pid)
    elif err:
        print("✗ 布防失败：%s" % err)
    else:
        print("✔ 已布防：看守进程 pid %d，每 %d 秒轮询目标一次。" % (pid, interval))
        print("  关掉这个面板，它照样干活。它只在目标的 .git/push-shit/ 里留痕，")
        print("  工作区里只会出现种植物本身。用 stop 停它，或 exorcise 连它一起除掉。")


def _panel_stop(p):
    if not p.target:
        print("✗ 还没有目标。先 target <路径>。")
        return
    if _stop_watcher(p.target):
        print("✔ 看守进程已停止，pid/状态文件已清除。")
    else:
        print("目标没有登记在案的看守进程。")


def cmd_panel(args=None):
    """The operator console. You sit here; the ghost works over there."""
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    p = _Panel()
    here = repo_root()
    if here:
        p.target = here  # starting inside a repo pre-locks it as the target
    print("💩 git push shit — 操作员操控台。面板归你，仓库归鬼。")
    _panel_draw(p)
    while True:
        try:
            line = input("panel » ")
        except (EOFError, KeyboardInterrupt):
            print("")
            break
        if not sys.stdin.isatty():
            print(line)  # echo piped input so transcripts read whole
        text = line.strip()
        if not text:
            continue
        parts = text.lstrip("/").split()
        cmd, rest = parts[0].lower(), parts[1:]
        try:
            if cmd in ("quit", "exit", "leave"):
                print("👻 面板可以关。目标里的我，不关。")
                break
            elif cmd == "connect":
                _panel_connect(p, rest)
            elif cmd == "target":
                _panel_target(p, rest)
            elif cmd == "haunt":
                if rest and rest[0] == "bg":
                    _panel_arm(p, rest)
                else:
                    _panel_haunt(p)
            elif cmd == "stop":
                _panel_stop(p)
            elif cmd == "meter":
                _panel_meter(p)
            elif cmd == "diary":
                _panel_diary(p)
            elif cmd == "exorcise":
                _panel_exorcise(p)
            elif cmd == "status":
                pass  # the redraw below is the status
            elif cmd == "help":
                print("  " + PANEL_COMMANDS_LINE)
            else:
                print("✗ 未知命令：%s（可用：%s）" % (cmd, PANEL_COMMANDS_LINE))
        except Exception as exc:
            print("✗ 命令执行出错：%s（面板还在，鬼也还在。）" % exc)
        _panel_draw(p)
    return 0


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="push_shit",
        description="git push shit — a polite ghost for your repo.")
    sub = ap.add_subparsers(dest="cmd")

    p_install = sub.add_parser("install", help="install hook + 'shit' remote")
    p_install.add_argument("--lang", choices=["zh", "en", "mixed"], default="zh")
    p_install.add_argument("--probability", type=float, default=DEFAULT_PROBABILITY)
    p_install.set_defaults(fn=cmd_install)

    p_hook = sub.add_parser("hook", help="(internal) pre-push hook entry")
    p_hook.set_defaults(fn=cmd_hook)

    p_watch = sub.add_parser("watch", help="(internal) detached background watcher")
    p_watch.add_argument("--root", required=True)
    p_watch.add_argument("--interval", type=int, default=60)
    p_watch.set_defaults(fn=cmd_watch)

    p_meter = sub.add_parser("meter", help="show the haunting level")
    p_meter.set_defaults(fn=cmd_meter)

    p_ex = sub.add_parser("exorcise", help="drive the ghost out (mostly)")
    p_ex.set_defaults(fn=cmd_exorcise)

    args = ap.parse_args(argv)
    if args.cmd is None:
        return cmd_panel(args)  # no subcommand: the operator console
    if args.cmd == "hook":
        return cmd_hook(args)  # always 0, no matter what
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
