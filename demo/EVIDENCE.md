# Acceptance evidence — git push shit

Phase-3 verification by the project lead, 2026-10-29, on this VM.
Model for all live voice generation: Gemma 3 1B (Q4_K_M) via llama.cpp
on `http://127.0.0.1:8092` (the product targets the user's local Gemma
3 4B; the 1B was the validation stand-in). Two staged victim repos:
`demo/victim` (builder's demo, sins staged: `fix` / `最终版` commits,
an ancient TODO) and `/tmp/accept1/victim` + `/tmp/accept2/victim`
(lead's independent runs).

## 1. Operator console (lead's run, verbatim excerpts)

```
panel » connect
● 模型已接通：http://127.0.0.1:8092 [gemma]
panel » target /tmp/accept1/victim
◎ 目标锁定：/tmp/accept1/victim（尚未入驻）
panel » haunt
👻 凌晨 0 点还在 push。睡吧，我替你守着这个仓库——一直守着。
✔ 闹鬼 #1 完成 · Lv1 · 动了 1 个文件，已以「the previous maintainer (deceased)」的名义提交
panel » haunt   → #2 · Lv2（低语 + 假前任）
panel » haunt   → #3 · Lv3（+ 代码鬼 src/legacy_check.py）
panel » haunt   → #4 · Lv4（+ 日记，藏在 src/refactor-notes.txt）
panel » haunt   → #5 · Lv5（+ commit 署名）
```

Meter at Lv5: `💩 总数 10，分布在 5 个文件 · 低语 6 · 假前任注释 2 ·
代码鬼文件 2 · 鬼的日记 1 · 最闹鬼文件：src/app.py（3 处）`.

Lv5 planting commit body (the trailer the builder's demo never reached):

```
💩 the ghost was here (haunting #5)

我看着你提交。每一行都看着，尤其是你藏起来的那些。

Haunted-by: the previous maintainer (deceased)
```

Planted whispers are comment-syntax aware: `# …` in Python,
`<!-- … -->` in Markdown. The fake predecessor, verbatim:
`# 💩 下面的写法是有原因的，原因我不记得了，1997 年的原因。—— E.B.`
The ghost-shaped code (`docs/housekeeping.py` in demo/victim) runs:
`python3 docs/housekeeping.py` → `我从未离开这个仓库，我看着你每一次提交`, exit 0.

## 2. The literal command (victim's own terminal)

```
$ PUSH_SHIT_PROVOKE=1 git push shit main
💩 src/app.py 里的 TODO 已经躺了0 天。你留给谁的？这里只有你，和我。
💩 haunting #7 · Lv5 · 3 file(s) touched — the mark rides your NEXT push.
   c61e2aa..bff1b98  main -> main        (push exit 0 — fail-open intact)
```
The hook plants a ghost-authored commit locally; it reaches the remote
with the following push (remote log shows ghost commits for #1–#6).

## 3. Background watcher (panel closed throughout)

```
✔ 已布防：看守进程 pid 6823，每 5 秒轮询目标一次。   (panel quit here)
2026-10-29 00:49:28 watcher armed pid=6823 interval=5s
2026-10-29 00:49:33 activity at 4a5c4642; probability roll skipped this round
2026-10-29 00:50:41 haunting #8 planted (Lv5, 3 files) after activity f884cf4f
```
The victim's own two commits triggered detection; the first roll
skipped (70% rule), the second planted ghost commit `f6a5c3b`.

## 4. Exorcise (option b — the ghost resists)

```
💩 git push shit — exorcism report
  Removed: 11 planting(s) — whispers 5, fake predecessors 2, ghost-code files 3, diary 1, old seeds 0.
  The background watcher was stopped and disarmed — nothing watches this repo now. (Except the seed.)
  The diary at src/refactor-notes.txt is gone. Its author has read this report.
  Epitaph, written by the ghost itself:
    8 hauntings, 11 plantings removed. 他的代码如同腐烂的树叶，被我不断地挖掘，直到彻底枯萎。
  Cleanup committed as cc17b08. History itself was not rewritten.
```
Watcher process confirmed dead; pid/status files cleared.

## 5. Defect found in acceptance and fixed

First exorcise left **no seed** although the report claimed one: the
seed's target picker demanded a worktree-clean file, but at that moment
every file the ghost had ever touched was mid-cleanup dirty, so no
candidate qualified in a small repo. Fix (in `push_shit.py`): if no
clean target exists, the seed may land in a just-cleaned file with the
cleanliness check waived (it rides the same cleanup commit). Re-test on
a fresh repo (`/tmp/accept2/victim`): after exorcise exactly one 💩
line remains, ledger holds one `seed` record:

```
src/app.py:1:# 💩 你以为你摆弄的是代码？这地方，是我的记忆，你永远无法解脱。
  Removed: 3 planting(s) — whispers 2, fake predecessors 1 …
  What was invited in never fully leaves. It is the seed of the next haunting.
```

## 6. Builder demo state

`demo/victim` retains the builder's staged run: hauntings #1–#4 (Lv4),
ghost commits in history, diary at `docs/notes-draft.md`, ghost code at
`docs/housekeeping.py`, full ledger in `.git/push-shit/`. Its leftover
watcher was stopped after acceptance. Note: the builder's completion
report claimed a `Haunted-by:` trailer in the remote log; the artifacts
show the demo never passed Lv4 — the trailer itself was verified
working in §1 above. Trust artifacts, not reports.
