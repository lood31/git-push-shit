import argparse
import ast
import contextlib
import io
import random
import unittest
from unittest.mock import patch

import push_shit as ps
from tests.support import RepoCase


class HookTests(RepoCase):
    def test_relative_and_absolute_hooks_path_are_respected(self):
        for value in ("my-hooks", str(self.repo / "absolute hooks")):
            with self.subTest(value=value):
                self.git("config", "core.hooksPath", value)
                self.install()
                self.assertTrue(self.hook().is_file(), str(self.hook()))
                self.assertIn("push_shit", self.hook().read_text(encoding="utf-8"))

    def test_original_gate_exit_code_and_stdin_are_preserved(self):
        self.make_remote()
        hook = self.hook()
        hook.write_text('#!/bin/sh\nprintf "%s\\n" "$1" > gate-remote.txt\ncat > gate-stdin.txt\nexit 7\n', encoding="utf-8")
        hook.chmod(0o755)
        self.install()
        before = self.git("rev-parse", "HEAD")
        result = self.run_process(["git", "push", "shit", "main"])
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.repo / "gate-remote.txt").read_text().strip(), "shit")
        self.assertIn(before, (self.repo / "gate-stdin.txt").read_text())
        self.assertEqual(self.git("rev-parse", "HEAD"), before)

    def test_origin_push_does_not_haunt_but_shit_push_does(self):
        self.make_remote()
        self.install()
        before = self.git("rev-parse", "HEAD")
        origin = self.run_process(["git", "push", "origin", "main"])
        self.assertEqual(origin.returncode, 0, origin.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        haunted = self.run_process(["git", "push", "shit", "main"])
        # Up-to-date pushes have no ref lines; make a user commit first.
        self.assertEqual(haunted.returncode, 0, haunted.stderr)
        (self.repo / "README.md").write_text("# Update\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-m", "user update")
        before = self.git("rev-parse", "HEAD")
        haunted = self.run_process(["git", "push", "shit", "main"])
        self.assertEqual(haunted.returncode, 0, haunted.stderr)
        self.assertNotEqual(self.git("rev-parse", "HEAD"), before)

    def test_explicit_head_refspec_triggers_the_checked_out_branch(self):
        self.make_remote()
        self.install()
        before = self.git("rev-parse", "HEAD")
        result = self.run_process(["git", "push", "shit", "HEAD:refs/heads/main"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(self.git("rev-parse", "HEAD"), before)
        cfg = ps.load_config(str(self.repo))
        assert cfg is not None
        self.assertEqual(cfg["haunt_count"], 1)

    def test_reinstall_does_not_nest_or_lose_original_hook(self):
        self.make_remote()
        hook = self.hook()
        original = '#!/bin/sh\necho gate >> gate-count.txt\ncat > /dev/null\nexit 0\n'
        hook.write_text(original, encoding="utf-8")
        hook.chmod(0o755)
        self.install(probability=0)
        self.install(probability=0)
        result = self.run_process(["git", "push", "shit", "main"])
        self.assertEqual(result.returncode, 0, result.stderr)
        gate = self.repo / "gate-count.txt"
        self.assertTrue(gate.exists(), "original hook must still execute")
        self.assertEqual(gate.read_text().splitlines(), ["gate"])

    def test_uninstall_restores_original_and_removes_owned_remote(self):
        self.make_remote()
        original = '#!/bin/sh\n# original quality gate\nexit 0\n'
        self.hook().write_text(original, encoding="utf-8")
        self.hook().chmod(0o755)
        self.install()
        result = self.cli("uninstall")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.hook().read_text(encoding="utf-8"), original)
        self.assertNotIn("shit", self.git("remote").splitlines())
        self.assertIn("origin", self.git("remote").splitlines())
        # Repeated uninstall must not touch the restored gate.
        self.assertEqual(self.cli("uninstall").returncode, 0)
        self.assertEqual(self.hook().read_text(encoding="utf-8"), original)

    def test_uninstall_keeps_preexisting_or_modified_remote(self):
        self.make_remote()
        self.git("remote", "add", "shit", "user-owned-remote")
        self.install()
        result = self.cli("uninstall")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git("remote", "get-url", "shit"), "user-owned-remote")

    def test_uninstall_cleans_without_seed_and_preserves_staged_work(self):
        self.install()
        with patch.object(ps, "server_alive", return_value=False):
            sins = ps.collect_sins(str(self.repo), self.git("rev-parse", "HEAD"), ps.ZERO_SHA)
            cfg = ps.load_config(str(self.repo))
            result = ps._perform_haunting(str(self.repo), cfg, sins, random.Random(0))
        self.assertIsNotNone(result)
        (self.repo / "mine.txt").write_text("user staged\n")
        self.git("add", "mine.txt")
        result = self.cli("uninstall")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(not r.get("exorcised") for r in ps.ledger_read(str(self.repo))))
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "mine.txt")
        self.assertFalse(self.hook().exists())
        cfg = ps.load_config(str(self.repo))
        self.assertTrue(cfg is None or cfg.get("disabled"))

    def test_five_real_pushes_then_uninstall_clean_all_forms_and_keep_user_index(self):
        self.make_remote()
        self.install()
        app = self.repo / "src/app.py"
        baseline = ast.dump(ast.parse(app.read_text(encoding="utf-8")))
        for number in range(1, 6):
            result = self.run_process(["git", "push", "shit", "main"])
            self.assertEqual(result.returncode, 0, result.stderr)
            cfg = ps.load_config(str(self.repo))
            assert cfg is not None
            self.assertEqual(cfg["haunt_count"], number)
        rows = ps.ledger_read(str(self.repo))
        self.assertTrue({"whisper", "predecessor", "ghost_code", "diary"} <= {r["type"] for r in rows})
        generated = [self.repo / r["file"] for r in rows if r["type"] in ("ghost_code", "diary")]
        (self.repo / "mine.txt").write_text("staged by user\n", encoding="utf-8")
        self.git("add", "mine.txt")
        result = self.cli("uninstall")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all(not path.exists() for path in generated))
        self.assertFalse(any(not r.get("exorcised") for r in ps.ledger_read(str(self.repo))))
        self.assertEqual(ast.dump(ast.parse(app.read_text(encoding="utf-8"))), baseline)
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "mine.txt")
        self.assertFalse(self.hook().exists())
        self.assertNotIn("shit", self.git("remote").splitlines())
        self.git("fsck", "--full")

    def test_unexpected_hook_error_is_logged_but_still_fails_open(self):
        args = argparse.Namespace(remote_name="shit")
        with patch.object(ps, "_hook_inner", side_effect=RuntimeError("unexpected test failure")), \
                self.assertLogs("push_shit", level="DEBUG") as captured:
            self.assertEqual(ps.cmd_hook(args), 0)
        self.assertIn("unexpected test failure", "\n".join(captured.output))

    def test_failed_install_restores_the_original_quality_gate(self):
        original = "#!/bin/sh\n# original quality gate\nexit 7\n"
        self.hook().write_text(original, encoding="utf-8")
        args = argparse.Namespace(lang="zh", probability=1)
        with patch.object(ps.os, "chmod", side_effect=OSError("permission denied")), \
                contextlib.redirect_stderr(io.StringIO()), \
                contextlib.redirect_stdout(io.StringIO()):
            result = ps.cmd_install(args, root=str(self.repo))
        self.assertEqual(result, 1)
        self.assertEqual(self.hook().read_text(encoding="utf-8"), original)

    def test_uninstall_preserves_modified_owned_remote_and_hook(self):
        self.make_remote()
        self.install()
        self.git("remote", "set-url", "shit", "new-user-remote")
        with self.hook().open("a", encoding="utf-8") as stream:
            stream.write("# user custom extension\n")
        content = self.hook().read_bytes()
        result = self.cli("uninstall")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.hook().read_bytes(), content)
        self.assertEqual(self.git("remote", "get-url", "shit"), "new-user-remote")
        cfg = ps.load_config(str(self.repo))
        assert cfg is not None
        self.assertTrue(cfg["disabled"])

    def test_exorcise_explicitly_warns_it_is_not_uninstall(self):
        self.install()
        result = self.cli("exorcise")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("uninstall", result.stdout)


if __name__ == "__main__":
    unittest.main()
