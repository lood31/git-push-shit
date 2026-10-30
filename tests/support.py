"""Isolated Git fixtures. Artifacts are retained, never recursively deleted."""

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import push_shit as ps

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "push_shit.py"


class RepoCase(unittest.TestCase):
    def setUp(self):
        self.env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1",
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0",
                        PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1",
                        PUSH_SHIT_ENDPOINT="http://127.0.0.1:1",
                        PUSH_SHIT_MODEL="test-model", PUSH_SHIT_TIMEOUT="0.2")
        self.envpatch = patch.dict(os.environ, self.env)
        self.envpatch.start()
        self.addCleanup(self.envpatch.stop)
        artifacts = ROOT / ".git" / "tdd-runs"
        artifacts.mkdir(exist_ok=True)
        self.repo = Path(tempfile.mkdtemp(prefix="case-", dir=artifacts))
        self.git("init", "-b", "main")
        self.git("config", "user.name", "TDD Test")
        self.git("config", "user.email", "test@localhost")
        self.git("config", "core.autocrlf", "false")
        (self.repo / "src").mkdir()
        (self.repo / "src/app.py").write_text(
            "#!/usr/bin/env python3\n# coding: utf-8\nVALUE = 42\nprint(VALUE)\n",
            encoding="utf-8")
        (self.repo / "README.md").write_text("# Test repo\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "initial")

    def run_process(self, args, data=None, extra=None):
        return subprocess.run([str(a) for a in args], cwd=self.repo,
                              input=data, text=True, encoding="utf-8",
                              errors="replace", capture_output=True, timeout=30,
                              env=dict(self.env, **(extra or {})), check=False)

    def git(self, *args):
        proc = self.run_process(["git", *args])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.strip()

    def cli(self, *args, data=None, extra=None):
        return self.run_process([sys.executable, "-B", SCRIPT, *args], data, extra)

    def install(self, probability=1):
        proc = self.cli("install", "--probability", str(probability))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc

    def hook(self):
        path = self.git("rev-parse", "--git-path", "hooks/pre-push")
        return Path(path) if Path(path).is_absolute() else self.repo / path

    def make_remote(self):
        remote = self.repo / ".git/local-remote.git"
        self.git("init", "--bare", str(remote))
        self.git("remote", "add", "origin", str(remote))
        return remote

    def panel(self, script):
        output = io.StringIO()
        lines = iter(script)
        with patch.object(ps, "repo_root", return_value=str(self.repo)), \
                patch("builtins.input", side_effect=lambda _prompt: next(lines)), \
                patch.object(ps.sys.stdin, "isatty", return_value=False), \
                contextlib.redirect_stdout(output):
            ps.cmd_panel()
        return output.getvalue()
