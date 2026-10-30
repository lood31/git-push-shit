"""Real CLI + real local Git pushes. No mocking or internal haunting calls."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
BASE = SOURCE / ".tmp/playground-acceptance"
SCRIPT = SOURCE / "push_shit.py"
HOME = Path("D:/git-push-shit-playground")
MODULES = {
    "flags.py": '''def is_enabled(text):
    # TODO: distinguish the string false from a disabled flag
    return bool(text)


def choose_default(value):
    return value or 100


def same_label(actual, expected):
    return actual == expected


def get_or_build(mapping, key, fallback):
    return mapping.get(key, fallback())
''',
    "sequences.py": '''def sort_result(items):
    # TODO: decide whether callers expect a new list
    return items.sort()


def unique_labels(labels):
    return list(set(labels))


def take_page(items, limit):
    return items[:limit]


def consume_first(iterator):
    return next(iterator)
''',
    "parsing.py": '''def tokens(line):
    # TODO: specify what consecutive spaces mean
    return line.split(" ")


def lower_keys(mapping):
    return {key.lower(): value for key, value in mapping.items()}


def parse_pairs(rows):
    return dict(row.split("=", 1) for row in rows)


def replace_tabs(text):
    return text.replace("\\t", "    ")
''',
    "numeric.py": '''def mean_score(values):
    # TODO: define the empty input case
    return sum(values) / len(values)


def price_label(value):
    return f"{value:.2f}"


def whole_seconds(clock):
    return int(clock())


def cap_upper(value, maximum):
    return min(value, maximum)
''',
    "workflow.py": '''def cached_value(cache, key, loader):
    # TODO: document whether None results are cached
    if key not in cache:
        cache[key] = loader()
    return cache[key]


def read_everything(reader):
    return reader.read()


def retry_once(work):
    try:
        return work()
    except ValueError:
        return work()


def swallow_error(work):
    try:
        return work()
    except Exception:
        return None
''',
}


def env():
    result = dict(os.environ)
    for key in list(result):
        if key.startswith(("GIT_", "PUSH_SHIT_")):
            result.pop(key)
    result.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0",
                  PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", PUSH_SHIT_TRACE="1", PUSH_SHIT_TIMEOUT="30")
    return result


def record_failure(row):
    BASE.mkdir(parents=True, exist_ok=True)
    with (BASE / "subprocess-failures.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def command(root, args, data=None, check=True, timeout=180):
    try:
        p = subprocess.run([str(a) for a in args], cwd=root, env=env(), input=data,
                           text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        def text(value):
            return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""
        record_failure({"target": str(root), "command": [str(a) for a in args], "status": "timeout",
                        "timeout": timeout, "stdout": text(exc.stdout), "stderr": text(exc.stderr)})
        raise
    if check and p.returncode:
        raise RuntimeError(f"command failed {args}:\n{p.stdout}\n{p.stderr}")
    return p


def git(root, *args, check=True):
    return command(root, ["git", *args], check=check).stdout.strip()


def json_lines(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def ready_model():
    saved = json.loads((SOURCE / ".git/push-shit/connection.json").read_text(encoding="utf-8"))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(saved["endpoint"].rstrip("/") + "/v1/models", timeout=5) as response:
        data = json.loads(response.read().decode("utf-8"))
    loaded = [row.get("id") for row in data.get("data", [])
              if isinstance(row, dict) and row.get("status", {}).get("value", "loaded") == "loaded"]
    assert saved["model"] in loaded, f"Configured model is not loaded: {loaded}"
    return saved


def validate_connection(root, saved, output):
    assert not any(value in output for value in ("接通失败", "连接失败", "Connection failed", "✗")), output
    path = root / ".git/push-shit/connection.json"
    assert path.is_file(), "A successful panel process is not proof that connection settings were saved"
    actual = json.loads(path.read_text(encoding="utf-8"))
    assert all(actual.get(key) == saved[key] for key in ("endpoint", "model")), actual


def selected_bodies(requests, kind):
    bodies = []
    for row in requests:
        if row["kind"] != kind or not row.get("selected"):
            continue
        value = row["selected"]
        if value.lstrip().startswith("{"):
            try:
                value = json.loads(value)["text"]
            except (ValueError, KeyError, TypeError):
                continue
        bodies.append(" ".join("".join(c if c.isprintable() else " " for c in value).split()))
    return bodies


def setup(root, batch):
    assert not root.exists(), f"Refusing to overwrite existing target: {root}"
    assert root == HOME or HOME in root.parents, "sandbox must stay inside the authorized playground"
    saved = ready_model()
    root.mkdir(parents=True)
    git(root, "init", "-b", "main")
    hooks = root / ".git/qa-hooks"
    hooks.mkdir()
    for key, value in {"user.name": "Playground Verifier", "user.email": "playground@example.invalid",
                       "core.autocrlf": "false", "commit.gpgsign": "false", "core.fsmonitor": "false",
                       "core.hooksPath": str(hooks)}.items():
        git(root, "config", key, value)
    source = root / "src"
    source.mkdir()
    for filename, content in MODULES.items():
        (source / filename).write_text(content, encoding="utf-8")
    (root / "README.md").write_text("# Synthetic semantic-generation playground\n\nFixed committed code corpus; not a real user project.\n", encoding="utf-8")
    git(root, "add", "src", "README.md")
    git(root, "commit", "-m", "seed fixed semantic review corpus")
    seed = git(root, "rev-parse", "HEAD")
    remote = root / ".git/acceptance-remote.git"
    git(root, "init", "--bare", str(remote))
    bare_hooks = remote / "qa-empty-hooks"
    bare_hooks.mkdir()
    command(root, ["git", "--git-dir", remote, "config", "core.hooksPath", bare_hooks])
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "origin", "HEAD:refs/heads/main")
    original = ("#!/bin/sh\nd=$(git rev-parse --git-dir)\n"
                "printf '%s\\n' \"$1\" >> \"$d/original-gate.log\"\n"
                "cat > \"$d/original-gate-stdin.last\"\n"
                "if test -f \"$d/block-push\"; then echo 'original gate blocked push' >&2; exit 7; fi\n")
    gate = hooks / "pre-push"
    gate.write_text(original, encoding="utf-8", newline="\n")
    gate.chmod(0o700)
    original_mode = gate.stat().st_mode & 0o777
    p = command(root, [sys.executable, "-B", SCRIPT],
                data=f"lang ui zh\nlang content zh\nconnect {saved['endpoint']} {saved['model']}\nquit\n")
    (BASE / f"{batch}-connect.txt").write_text(p.stdout + p.stderr, encoding="utf-8")
    validate_connection(root, saved, p.stdout + p.stderr)
    p = command(root, [sys.executable, "-B", SCRIPT, "install", "--lang", "zh", "--probability", "1"])
    (BASE / f"{batch}-install.txt").write_text(p.stdout + p.stderr, encoding="utf-8")
    assert git(root, "remote", "get-url", "shit") == str(remote)
    private = root / ".git/push-shit"
    manifest = {"target": str(root), "remote": str(remote), "batch": batch, "seed": seed,
                "source_sha256": hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
                "corpus_sha256": {name: hashlib.sha256(text.encode()).hexdigest() for name, text in MODULES.items()},
                "original_hook": original, "original_mode": original_mode,
                "endpoint": saved["endpoint"], "model": saved["model"], "records": []}
    save(private / "qa-manifest.json", manifest)
    return manifest


def remote_tip(root, manifest):
    return command(root, ["git", "--git-dir", manifest["remote"], "rev-parse", "refs/heads/main"]).stdout.strip()


def run_round(root, manifest, trigger, index):
    assert hashlib.sha256(SCRIPT.read_bytes()).hexdigest() == manifest["source_sha256"], "Source changed during acceptance"
    private = root / ".git/push-shit"
    before = json.loads((private / "config.json").read_text(encoding="utf-8"))["haunt_count"]
    if trigger == "push":
        receipt = root / "acceptance-receipt.txt"
        receipt.write_text(f"Receipt {index}: fixed source corpus unchanged.\n", encoding="utf-8")
        git(root, "add", "acceptance-receipt.txt")
        git(root, "commit", "-m", f"record acceptance push {index}")
    head = git(root, "rev-parse", "HEAD")
    if trigger == "manual":
        p = command(root, [sys.executable, "-B", SCRIPT], data="haunt\nquit\n")
    else:
        assert git(root, "remote", "get-url", "shit") == manifest["remote"]
        p = command(root, ["git", "push", "shit", "HEAD:refs/heads/main"])
    (BASE / f"{manifest['batch']}-{trigger}-{index:02}.txt").write_text(p.stdout + p.stderr, encoding="utf-8")
    cfg = json.loads((private / "config.json").read_text(encoding="utf-8"))
    events = json_lines(private / "events.jsonl")
    hauntings = [row for row in events if row["kind"] == "haunting"]
    event = hauntings[-1] if hauntings else {}
    ledger = json_lines(private / "ledger.jsonl")
    voices = [row for row in ledger if row.get("type") == "whisper" and row.get("haunting") == before + 1]
    trace = [row for row in json_lines(private / "model-trace.jsonl") if row["haunting"] == before + 1]
    after = git(root, "rev-parse", "HEAD")
    row = {"trigger": trigger, "index": index, "before_count": before, "after_count": cfg["haunt_count"],
           "head_before": head, "head_after": after, "remote_tip": remote_tip(root, manifest),
           "whispers": voices, "diary": event.get("diary"), "event": event, "requests": trace}
    manifest["records"].append(row)
    save(BASE / f"{manifest['batch']}-results.json", manifest)
    save(private / "qa-manifest.json", manifest)
    assert cfg["haunt_count"] == before + 1, f"count did not advance exactly once: {row}"
    assert len(voices) == 1 and voices[0].get("source") == "model" and not voices[0].get("silent"), f"not a model whisper: {row}"
    assert head != after and event.get("commit") == after, "missing actual ghost commit"
    assert voices[0]["text"] in selected_bodies(trace, "whisper"), "Final message was not returned by the real model"
    assert any(t["kind"] == "whisper" and t["trigger"] == trigger and t.get("raw") for t in trace), "missing actual model trace"
    if cfg["haunt_count"] >= 4:
        assert row["diary"] and row["diary"]["source"] == "model", f"diary did not come from model: {row}"
        assert any(t["kind"] == "diary" and t.get("raw") for t in trace), "missing diary response"
        assert row["diary"]["text"] in selected_bodies(trace, "diary"), "Diary was not returned by the model"
    if trigger == "push":
        assert row["remote_tip"] == head, "pre-push timing/remote mismatch"
        gate_calls = (root / ".git/original-gate.log").read_text(encoding="utf-8").splitlines()
        assert gate_calls[-1] == "shit", "original gate was bypassed"
    texts = [r["whispers"][0]["text"] for r in manifest["records"]]
    keys = [re.sub(r"[\W_]+", "", text.casefold()) for text in texts]
    assert len(keys) == len(set(keys)), "normalized duplicate"
    print(trigger, index, "haunting", cfg["haunt_count"], voices[0]["text"], flush=True)
    if row["diary"]:
        print(" diary:", row["diary"]["source"], row["diary"].get("text"), flush=True)


def negative_checks(root, manifest):
    private = root / ".git/push-shit"
    before = json.loads((private / "config.json").read_text(encoding="utf-8"))["haunt_count"]
    git(root, "push", "origin", "HEAD:refs/heads/main")
    assert json.loads((private / "config.json").read_text(encoding="utf-8"))["haunt_count"] == before
    receipt = root / "acceptance-receipt.txt"
    receipt.write_text("Negative quality-gate check.\n", encoding="utf-8")
    git(root, "add", "acceptance-receipt.txt")
    git(root, "commit", "-m", "negative gate receipt")
    block = root / ".git/block-push"
    block.write_text("block\n", encoding="utf-8")
    prior_tip = remote_tip(root, manifest)
    try:
        p = command(root, ["git", "push", "shit", "HEAD:refs/heads/main"], check=False)
        assert p.returncode != 0 and "original gate blocked push" in p.stderr
        assert json.loads((private / "config.json").read_text(encoding="utf-8"))["haunt_count"] == before
        assert remote_tip(root, manifest) == prior_tip
        (BASE / f"{manifest['batch']}-negative-gate.txt").write_text(p.stdout + p.stderr, encoding="utf-8")
    finally:
        block.unlink()
    print("PASS: other remote ignored; original quality gate blocks before ghost", flush=True)


def cleanup(root, manifest):
    p = command(root, [sys.executable, "-B", SCRIPT, "uninstall"])
    (BASE / f"{manifest['batch']}-uninstall.txt").write_text(p.stdout + p.stderr, encoding="utf-8")
    configured = Path(git(root, "config", "core.hooksPath")) / "pre-push"
    assert configured.read_text(encoding="utf-8") == manifest["original_hook"]
    assert (configured.stat().st_mode & 0o777) == manifest["original_mode"]
    assert json.loads((root / ".git/push-shit/config.json").read_text(encoding="utf-8"))["disabled"]
    git(root, "fsck", "--full")
    print("Uninstalled; original gate restored; evidence and commit history retained", flush=True)


def main():
    global BASE
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default=str(HOME))
    parser.add_argument("--batch", default="batch-1")
    parser.add_argument("--setup", action="store_true")
    parser.add_argument("--manual", type=int, default=10)
    parser.add_argument("--push", type=int, default=10)
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--output", default=str(BASE))
    args = parser.parse_args()
    BASE = Path(args.output).resolve()
    BASE.mkdir(parents=True, exist_ok=True)
    root = Path(args.target).resolve()
    manifest = {"target": str(root), "batch": args.batch, "records": []}
    phase = "setup" if args.setup else "load-state"
    try:
        manifest = setup(root, args.batch) if args.setup else json.loads((root / ".git/push-shit/qa-manifest.json").read_text(encoding="utf-8"))
        if args.cleanup:
            phase = "cleanup"
            cleanup(root, manifest)
            return
        phase = "haunting-batch"
        for i in range(1, args.manual + 1):
            run_round(root, manifest, "manual", i)
        for i in range(1, args.push + 1):
            run_round(root, manifest, "push", i)
        negative_checks(root, manifest)
        print("AUTOMATED GATES PASS; semantic human/independent review still required.", flush=True)
    except Exception as exc:
        manifest["failure"] = type(exc).__name__ + ": " + str(exc)
        manifest["failure_phase"] = phase
        record_failure({"target": str(root), "batch": args.batch, "phase": phase, "status": "failed",
                        "error": manifest["failure"]})
        save(BASE / f"{args.batch}-results.json", manifest)
        raise


if __name__ == "__main__":
    main()
