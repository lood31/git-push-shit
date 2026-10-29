# git push shit

**A ghost that lives in your git repo — and yes, the command is literal.**

Install it in a repository, add a remote named `shit`, and `git push shit`
does exactly what it says: every push, a dead senior maintainer who never
left the codebase plants 💩 in your comments — taunting whispers generated
by a local LLM, armed with a rap sheet of your real sins (the TODO you
abandoned 44 days ago, the variable you renamed three times, the commit
you just called `fix`). The haunting escalates. It keeps a diary. It signs
its commits. You can measure it. You can exorcise it. Mostly.

Built for DEV's *Ghost in the Machine* challenge: the ghost's voice is a
local open-weight model (Gemma via llama.cpp). Its brain, however, is
rules — see *Design* below for why, with receipts.

## The operator console

You don't chat with the ghost. You *operate* on it, from a terminal panel:

```
==================================================================
  💩 GIT PUSH SHIT — OPERATOR CONSOLE
==================================================================
  MODEL   : http://127.0.0.1:8092  [gemma]  ● CONNECTED
  TARGET  : /path/to/victim-repo
  LEVEL   : Lv3
  PLANTED : 5
  LAST    : 2026-10-29 00:45:46
  WATCH   : RUNNING (pid 6823, every 5s, 1 planted)
------------------------------------------------------------------
  connect [endpoint] [model] · target <path> · haunt ·
  haunt bg [sec] · stop · meter · diary · exorcise · status · quit
==================================================================
```

- `connect` — point it at your local llama.cpp server (tested with a
  real call; the light only turns green when the model answers).
- `target <path>` — aim at a project. A teammate's repo is the classic.
- `haunt` — plant one haunting right now, and optionally arm the
  pre-push hook so the ghost keeps working on every push.
- `haunt bg [sec]` — leave a **detached watcher**: close the terminal,
  the ghost stays. It polls the target, and when the victim commits,
  it rolls the dice and plants — silently, windowless.
- `meter` — the shit-meter: totals by form, most haunted file, level.
- `diary` — read the ghost's diary (it is not in the repo root; find it).
- `exorcise` — remove everything, stop the watcher, receive an epitaph
  written by the ghost itself. One whisper always survives. It is the
  seed of the next haunting.

Non-interactive subcommands (`install`, `meter`, `exorcise`, `watch`)
exist for the hook and for scripting.

## The five forms of shit

1. **Whispers** (Lv1) — taunting comments in the ghost's voice, generated
   by the local model from a *sin report* extracted from your diff and
   history: renames, commented-out code, `fix` / `final-v3` commit
   messages, TODO ages, the hour you push at.
2. **Fake predecessors** (Lv2) — legacy comments from maintainers who
   never existed: `// There is a reason it's written this way. The
   reason is from 1997 and it is gone. — E.B.`
3. **Ghost-shaped code** (Lv3) — real, runnable source code typeset into
   a ghost silhouette, IOCCC-style, planted as a new file in a random
   corner. Run it and it speaks.
4. **The ghost's diary** (Lv4) — a first-person sighting log disguised as
   an unremarkable notes file in a random subdirectory. Never the root.
5. **Commit signature** (Lv5) — planting commits authored by
   `the previous maintainer (deceased)`, carrying the trailer
   `Haunted-by: the previous maintainer (deceased)`.

Language is configurable (`zh` / `en` / `mixed`): the ghost taunts in
the tongue you fear most.

## The polite ghost (auditable in one file)

The whole tool is a single Python file, standard library only — read it
and check the promise yourself:

- It only ever writes **comments, docs, new files, and commit messages**.
  It never modifies existing executable code.
- The hook **fails open**: any error, and your push proceeds untouched.
  The watcher likewise skips a round rather than ever jamming a repo.
- No model server? The ghost plants silent 💩 and notes its mute night
  in the diary. The haunting degrades; it does not die.

## Design: decisions by rules, voice by the model

This is deliberate, and it is measured, not vibes. In a separate research
project we benchmarked small local models (Gemma 3 1B/4B, Qwen2.5-1.5B)
as free-text adjudicators over structured memory operations: parse
failure rates were **0.89–0.93** across three models and two frozen
prompt versions — each model failed differently. So in this tool the
model never decides anything structural. Rules decide *what* happens;
the model only decides *how cruelly to say it*.

## Requirements & quick start

- Python 3.10+, git. Optional but recommended: a local llama.cpp server
  (`llama-server`) with an open-weight chat model.
- Clone this repo, then:

```bash
python3 push_shit.py            # open the operator console
# or, in the repo you want haunted:
python3 /path/to/push_shit.py install
git push shit                   # literal. enjoy.
```

State lives under the target's `.git/push-shit/` (config, ledger,
watcher). Nothing is written outside the target repo and its `.git`.

*For pranking only repos you own or teammates who will forgive you.
The ghost is patient; make sure your friendships are too.*
