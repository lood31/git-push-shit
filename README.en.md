# git push shit

**A polite ghost that lives in your Git repository.**

It leaves code-review asides, notes from fictional predecessors, ghost-shaped source files, and a diary. It can sign its own commits, appear on demand, or haunt the repository after selected pushes and background activity.

**[中文](README.md) · [English](README.en.md)**

> This is a developer toy, not a trustworthy code reviewer. Use it only in repositories you own or are explicitly authorized to modify, and try a sandbox first. It changes files and creates Git commits. The model can also be wrong.

## Features

| Feature | What it does |
| --- | --- |
| Operator console | Select a repository, connect a model, inspect state and control hauntings without clearing terminal history |
| Manual haunting | `haunt` plants one round and creates a commit; automatic triggering is optional |
| Push trigger | Once installed, only pushes to the remote named `shit` can trigger the ghost |
| Background watcher | `haunt bg` starts a detached process that watches repository activity and applies the configured probability |
| Chinese / English / mixed | Independent UI and content preferences; bilingual generated content is available |
| Local model connection | OpenAI-compatible chat endpoints, model discovery, useful connection errors and per-target settings |
| Content variety | Committed-code context, rotating observations, and recent duplicate/near-duplicate checks |
| Honest provenance | Distinguishes model output, template fallback and silence; optional raw request tracing |
| Exorcism and uninstall | Clean up registered plantings, leave a fictional seed, or disable automation and restore the original hook |

### Five forms of haunting

The level increases with successful haunting rounds, up to Lv5:

1. **Lv1 · Whispers:** short comments based on repository material, or a silent 💩 when the model is unavailable.
2. **Lv2 · Fictional predecessors:** legacy-style notes from maintainers who never existed, not impersonations of real people.
3. **Lv3 · Ghost-shaped code:** a new source file arranged as a ghost silhouette. The tool does not run it for you.
4. **Lv4 · Diary:** short field notes in a subdirectory, readable from the console.
5. **Lv5 · Commit signature:** planting commits use the ghost's author identity and a `Haunted-by` trailer.

Rules control structure, paths and Git operations. The model writes prose; it does not execute arbitrary commands.

## Requirements

- **Python 3.10+**. Runtime dependencies are standard-library only.
- **Git** with `git hook run --to-stdin` support.
- Optionally, a local chat service with an **OpenAI-compatible API**. Code-context requests also require `response_format: json_object` support.

This version was exercised on Windows with Python 3.13 and Git 2.55. Python 3.10 syntax was checked; that is not a claim of runtime coverage across all Python versions or operating systems.

```bash
git clone https://github.com/lood31/git-push-shit.git
cd git-push-shit
python push_shit.py
```

Use `python3` instead of `python` where your system requires it.

## Quick start: try a manual haunting first

In the console, **select a disposable target repository first**. Do not accidentally haunt the tool's own source checkout:

```text
target "D:/my-test-project"
lang en
connect http://127.0.0.1:8092
/help haunt
haunt
meter
diary
```

Enter these at `panel »`, not directly in your shell.

- Replace the endpoint with your actual running service. The tool does not download or start models.
- Omitting the model ID discovers candidates through `/v1/models`. Multiple candidates require an explicit selection.
- The connected state requires a successful chat response, not just a health check.
- The first `haunt` may ask whether to install the automatic hook. **The default is n.** Leave it off for manual-only use.
- Diaries begin at Lv4; having no diary during the first few rounds is normal.

An explicit model and a `/v1` URL work too:

```text
connect http://127.0.0.1:8092/v1 your-model-id
```

The default endpoint is `http://127.0.0.1:8092` and the default model name is `gemma`. These are defaults, not assumptions about your service.

## Console commands

| Command | Purpose |
| --- | --- |
| `help`, `/help` | All command guidance; `/help <command>` includes examples and side effects |
| `target <path>` | Select a Git repository; quote paths containing spaces |
| `connect [endpoint] [model]` | Connect, validate and save the current target's model settings |
| `lang` | Inspect UI and content languages |
| `lang zh` / `lang en` | Change both UI and content |
| `lang mixed` | Change content only to bilingual output |
| `lang ui zh\|en` | Change UI only |
| `lang content zh\|en\|mixed` | Change generated content only |
| `haunt` | Plant one round and commit it |
| `haunt bg [sec]` | Start detached watching; default 60 seconds, minimum 5 |
| `stop` | Stop the target watcher, without uninstalling its hook |
| `meter` | Inspect level, counts and planting statistics |
| `diary` | Read an existing diary |
| `exorcise` | Clean registered plantings and try to leave one safe seed; **not an uninstall** |
| `uninstall` | Stop watching, clean registered content, disable automation and restore the original hook; no new seed |
| `status` | Append the full status panel |
| `quit` / `exit` / `leave` | Exit the console; **does not stop a watcher or uninstall a hook** |

Settings live in the target's `.git/push-shit/`. Language, connection and installation state are separate. Changing languages does not install hooks, start watchers or create commits. Without a target, UI changes can be temporary; content changes and persistence require a target repository.

## Enable automatic push triggering

Select the target and connect a model in the console, then opt into hook installation when asked. Alternatively, run this from the **target repository directory**:

```bash
python /path/to/git-push-shit/push_shit.py install --lang en --probability 0.7
git remote -v
git push shit HEAD:main
```

On Windows, an example is `python "D:/tools/git-push-shit/push_shit.py" install --lang en`.

- `install` creates a pre-push wrapper. If it needs to create `shit`, it uses the target's `origin` URL. **Inspect your remotes before pushing.** Existing user remotes are not silently rewritten.
- The default automatic probability is `0.7`. Manual `haunt` attempts do not depend on that probability.
- Only a `shit` push triggers the ghost. Pushing to `origin` or another remote does not.
- **A new ghost commit travels on the next push.** Git has already selected the current push's refs before the hook runs. The tool does not recursively push new commits or rewrite history.
- Background watching is independent of the hook. Closing the window does not stop it; use `stop` or `uninstall`.

## Exorcism is not uninstall

| Action | Stops watcher | Cleans registered plantings | Leaves a new seed | Later `shit` pushes can haunt |
| --- | --- | --- | --- | --- |
| `stop` | Yes | No | No | Yes, if installed |
| `exorcise` | Yes | Yes, preserving user edits | Tries to | Yes, if installed |
| `uninstall` | Yes | Yes, preserving user edits | No | No |

User-modified content, modified hooks/remotes and uncertain ownership are retained with a notice. Only an unchanged remote known to have been created by this tool is removed. Existing commit history is not deleted or rewritten. Cleanup may create a new cleanup commit, so inspect the resulting diff too.

## Model behavior and limitations

### Reducing repetition

- Context comes from **committed Git objects**, not dirty working files.
- Rules prefer recently unreviewed behaviors rather than merely changing paths, function names or technical-debt metaphors.
- The last **30 successful, non-silent main annotations** form the duplicate window. Exorcised history remains useful.
- Normalization, similarity and shorter-text overlap checks reject copies and obvious near-duplicates.
- A main annotation has at most 3 model requests sharing a decreasing timeout budget. Mixed output can combine two genuine model clauses. Diaries have their own bounded retries, provenance and recent-history checks.
- Known incomplete diary output, such as unclosed inline code, is rejected instead of counting a half-sentence as success.

**There is no guarantee of a new meaning every time, or permanent uniqueness.** These are local heuristics, not a general semantic deduplicator. Limited material, the history window and model capability can still lead to repetition, fallback or skipped output.

### Provenance is explicit

The interface labels `[model]` and `[template]`, localized in Chinese. An unavailable model retains the silent 💩 behavior. Templates, silence and skipped output are not counted as successful model generation.

Code-context replies use `reference`, `observation` and `text`. References are checked against source material, but **observation is also model-authored and does not certify the final text**. Both annotations and diaries prioritize facts, with humor optional; this is an instruction, not a correctness guarantee.

> The model may misunderstand return values, exceptions, types and evaluation order. Do not change production code based on its comments or treat them as reliable review findings.

### Timeouts are not a hard wall-clock deadline

`PUSH_SHIT_TIMEOUT` defaults to 30 seconds and controls the remaining request timeout budget. It does not provide strict total-duration cancellation against pathological slow-drip HTTP responses. Diaries, health checks and Git operations are also separate; a complete haunting is not promised to finish within that budget.

## Safety and privacy

- **Original quality gates run first.** Existing pre-push hook arguments, input and failures are preserved, including target `core.hooksPath` setups. Haunting does not bypass the original gate.
- After that gate succeeds, ghost failures are fail-open so a model failure alone does not block a normal push.
- Rules constrain planting locations and forms, preserve existing filenames and user changes, and retain uncertain ownership. The model cannot choose arbitrary Git or system commands.
- Material collection has size/count limits and sensitive-content filters, but **cannot guarantee detection of every secret**. Use trusted endpoints and be careful with business code or credentials.
- `PUSH_SHIT_TRACE=1` optionally records actual prompts, raw replies and trigger metadata in the target's `.git/push-shit/model-trace.jsonl`. **Off by default.** Logs contain code and model output; do not publish business repository traces.
- No automatic model downloads, model-server startup, remote pushes or history rewriting.

## Development and verification

Run the standard-library regression suite:

```bash
python -B -m unittest discover -s tests -v
```

Optional static checks:

```bash
python -m pip install ruff
python -m ruff check .
git diff --check
```

The current version passed 151 tests. One local, consecutive acceptance batch also completed **10 manual haunts + 10 real pushes to a local remote**: all 20 main annotations and 17 diaries were model-sourced, with independent text review supporting the content-difference and completeness gates. Three English and three mixed annotations were tested separately.

**That sample is not a guarantee of future uniqueness or factual correctness.** Template seed/epitaph output was not counted as model success.

The reusable live runner is `python -B -m tests.playground_qa --help`. It currently targets the authorized Windows sandbox `D:/git-push-shit-playground`, requires working connection settings saved in the source checkout, and creates synthetic repositories, a local bare remote, hooks and commits. Do not point it at a business repository. Uninstall through the same runner using `--cleanup --target <path>`. A successful automated run still requires reading the actual text; IDs, unique strings and exit codes do not prove semantic differences.

Private plans, transcripts and raw model replies live under `.tmp/` and are not published with the source.

## License

[MIT](LICENSE). Originally built for DEV's *Ghost in the Machine* challenge.
