import ast
import json
import random
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import Mock, patch

import push_shit as ps
from tests.support import RepoCase


class SafetyTests(RepoCase):
    def test_gbk_console_runs_without_pythonutf8_workaround(self):
        result = self.cli(data="help\nquit\n",
                          extra={"PYTHONUTF8": "0", "PYTHONIOENCODING": "gbk"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("/help", result.stdout)

    def test_ghost_filename_collision_never_overwrites_existing_user_code(self):
        first = self.repo / "src/existing.py"
        fallback = self.repo / "src/existing_2.py"
        first.write_text("FIRST = 1\n", encoding="utf-8")
        fallback.write_text("USER = 2\n", encoding="utf-8")
        before = fallback.read_bytes()
        rng = Mock()
        rng.choice.return_value = "existing.py"
        rng.randint.return_value = 2
        with patch.object(ps, "pick_corner_dir", return_value="src"):
            result = ps.plant_ghost_code(str(self.repo), {"lang": "en"}, rng)
        self.assertEqual(fallback.read_bytes(), before)
        self.assertIsNone(result)

    def test_diary_filename_collision_never_overwrites_existing_user_notes(self):
        first = self.repo / "src/existing.md"
        fallback = self.repo / "src/existing-2.md"
        first.write_text("First note\n", encoding="utf-8")
        fallback.write_text("User note\n", encoding="utf-8")
        before = fallback.read_bytes()
        rng = Mock()
        rng.choice.return_value = "existing.md"
        rng.randint.return_value = 2
        with patch.object(ps, "pick_corner_dir", return_value="src"):
            result = ps.ensure_diary(str(self.repo), {"lang": "en"}, rng)
        self.assertEqual(fallback.read_bytes(), before)
        self.assertIsNone(result)

    def test_css_uses_standard_block_comment(self):
        self.assertEqual(ps.wrap_comment("style.css", "hello"), "/* hello */")

    def test_css_comment_cannot_close_early(self):
        comment = ps.wrap_comment("style.css", "ghost */ body{display:none} /*")
        self.assertTrue(comment.startswith("/* "))
        self.assertEqual(comment.count("*/"), 1)
        self.assertNotIn("\n", comment)

    def test_xml_comment_payload_remains_parseable(self):
        comment = ps.wrap_comment("config.xml", "bad -- payload --> trailing-")
        # Fixed test payload, no external input or entities.
        ET.fromstring("<root>" + comment + "</root>")

    def test_line_comment_payload_cannot_inject_executable_line(self):
        comment = ps.wrap_comment("app.py", "ghost\nraise Exception('injected')\r\x1b[2J")
        original = "VALUE = 42\n"
        self.assertEqual(ast.dump(ast.parse(original)),
                         ast.dump(ast.parse(comment + "\n" + original)))
        self.assertNotIn("\x1b", comment)

    def test_five_levels_preserve_original_python_and_protect_user_changes(self):
        baseline = ast.dump(ast.parse((self.repo / "src/app.py").read_text(encoding="utf-8")))
        ps.save_config(str(self.repo), {"lang": "zh", "probability": 1,
                                      "haunt_count": 0, "lifetime_hauntings": 0,
                                      "diary_path": None})
        (self.repo / "mine.txt").write_text("user staged\n", encoding="utf-8")
        self.git("add", "mine.txt")
        with patch.object(ps, "server_alive", return_value=False):
            for number in range(1, 6):
                cfg = ps.load_config(str(self.repo))
                sins = ps.collect_sins(str(self.repo), self.git("rev-parse", "HEAD"), ps.ZERO_SHA)
                result = ps._perform_haunting(str(self.repo), cfg, sins, random.Random(number))
                self.assertIsNotNone(result)
        self.assertEqual(ast.dump(ast.parse((self.repo / "src/app.py").read_text(encoding="utf-8"))), baseline)
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "mine.txt")
        self.assertIn(ps.TRAILER, self.git("log", "-1", "--format=%B"))
        current = ps.load_config(str(self.repo))
        assert current is not None
        self.assertTrue(current["diary_path"])
        with (self.repo / "src/app.py").open("a", encoding="utf-8") as stream:
            stream.write("# user dirty\n")
        before = (self.repo / "src/app.py").read_bytes()
        self.assertNotEqual(ps.pick_target(str(self.repo), ["src/app.py"], rng=random.Random(1)), "src/app.py")
        self.assertEqual((self.repo / "src/app.py").read_bytes(), before)

    def test_fail_open_bad_config_with_real_push(self):
        self.make_remote()
        self.install()
        config = self.repo / ".git/push-shit/config.json"
        config.write_text("{bad json", encoding="utf-8")
        result = self.run_process(["git", "push", "shit", "main"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.git("fsck", "--full")

    def test_exorcise_does_not_seed_or_commit_dirty_user_files(self):
        self.install()
        cfg = ps.load_config(str(self.repo))
        assert cfg is not None
        cfg["haunt_count"] = 1
        ps.save_config(str(self.repo), cfg)
        ps.ledger_append(str(self.repo), {"type": "whisper", "file": "src/app.py", "line": "# ghost"})
        for name in ("README.md", "src/app.py"):
            with (self.repo / name).open("a", encoding="utf-8") as stream:
                stream.write("# my uncommitted work\n")
        before = {name: (self.repo / name).read_bytes() for name in ("README.md", "src/app.py")}
        head = self.git("rev-parse", "HEAD")
        result = self.cli("exorcise")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD"), head)
        self.assertEqual(before, {name: (self.repo / name).read_bytes() for name in before})

    def test_nan_probability_skips_haunting_without_blocking_real_push(self):
        self.make_remote()
        self.install()
        cfg = ps.load_config(str(self.repo))
        assert cfg is not None
        cfg["probability"] = "NaN"
        ps.save_config(str(self.repo), cfg)
        before = self.git("rev-parse", "HEAD")
        result = self.run_process(["git", "push", "shit", "main"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)

    def test_invalid_count_identifies_the_bad_field(self):
        with self.assertRaisesRegex(ValueError, "haunt_count"):
            ps._state_brief(str(self.repo), {"haunt_count": "invalid"})

    def test_invalid_watch_interval_is_identified_before_spawn(self):
        with self.assertRaisesRegex(ValueError, "watch interval"):
            ps._spawn_watcher(str(self.repo), "invalid")

    def test_missing_git_directory_has_an_explicit_repository_error(self):
        with patch.object(ps, "git_dir", return_value=None), self.assertRaises(ValueError):
            ps.ps_dir(str(self.repo))

    def test_new_connection_file_is_not_installed_haunting_config(self):
        private = self.repo / ".git/push-shit"
        private.mkdir()
        (private / "connection.json").write_text(json.dumps({"endpoint": "http://127.0.0.1:1", "model": "x"}))
        self.assertIsNone(ps.load_config(str(self.repo)))


if __name__ == "__main__":
    unittest.main()
